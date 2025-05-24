import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
print("INFO: Loaded environment variables.")

# --- Configuration ---
PSF_ACCESS_TOKEN = os.getenv("PSF_ACCESS_TOKEN")
PSF_LOCATION_ID = os.getenv("PSF_LOCATION_ID")
GHL_API_BASE_URL = "https://services.leadconnectorhq.com"

def get_order_by_id():
    """
    Takes a specific Order ID and fetches its full details.
    """
    print("\n--- Fetching Specific Order Details by ID ---")
    
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("CRITICAL ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in your .env file.")
        return

    # The Order ID we discovered from the transaction's 'entityId' field
    order_id_to_find = "6830449a06795494b03d4599"
    print(f"INFO: Querying for Order ID: {order_id_to_find}")

    # NEW: Using the /payments/orders/{orderId} endpoint
    endpoint = f"{GHL_API_BASE_URL}/payments/orders/{order_id_to_find}"
    headers = {
        "Authorization": f"Bearer {PSF_ACCESS_TOKEN}",
        "Version": "2021-07-28",
        "Accept": "application/json"
    }

    # As per the docs, this endpoint also requires altId and altType as query parameters
    params = {
        "altId": PSF_LOCATION_ID,
        "altType": "location",
    }

    print(f"INFO: Making API call to: GET {endpoint}")

    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        
        # The docs for this endpoint don't nest the result in a "data" or "order" key
        # It seems the response body *is* the order object.
        order_data = response.json()

        print(f"\nSUCCESS! Found the specific order.")
        print("--- Full Order Details ---")
        print(json.dumps(order_data, indent=2))
        
        # --- Final Verification ---
        print("\n--- Verifying Line Item and SKU ---")
        items = order_data.get('items', [])
        if items:
            print(f"Found {len(items)} line item(s).")
            for i, item in enumerate(items):
                # The 'product' object within the item should have what we need
                product_details = item.get('product', {})
                print(f"  Item {i+1}:")
                print(f"    Name: {product_details.get('name')}")
                print(f"    SKU: {product_details.get('sku')}  <-- SHOULD BE PSF-BOOK-001")
        else:
            print("WARNING: Order details contain no line items.")


    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error: {http_err}")
        print(f"  Response Text: {response.text}")
    except Exception as err:
        print(f"ERROR: An unexpected error occurred: {err}")

if __name__ == "__main__":
    get_order_by_id()