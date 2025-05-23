import requests
import base64
import json
import os
import uuid
from datetime import date, timedelta

# --- Configuration (From your .env file) ---
# (This section remains unchanged)
ONGOING_USERNAME = os.getenv("ONGOING_USERNAME")
ONGOING_PASSWORD = os.getenv("ONGOING_PASSWORD")
ONGOING_GOODS_OWNER_ID = os.getenv("ONGOING_GOODS_OWNER_ID")
ONGOING_WAREHOUSE_NAME = os.getenv("ONGOING_WAREHOUSE_NAME")
ONGOING_API_SERVER = os.getenv("ONGOING_API_SERVER", "api.ongoingsystems.se")

# Construct the Base API URL
if not ONGOING_WAREHOUSE_NAME:
    print("CRITICAL ERROR: ONGOING_WAREHOUSE_NAME environment variable is not set.")
    exit()

BASE_API_URL = f"https://{ONGOING_API_SERVER}/{ONGOING_WAREHOUSE_NAME}/api/v1/"

def get_ongoing_auth_header(username, password):
    # (This function remains unchanged)
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

def create_ongoing_order(psf_order_data):
    # (This section is the same as the last version)
    if not all([ONGOING_USERNAME, ONGOING_PASSWORD, ONGOING_GOODS_OWNER_ID]):
        print("ERROR: Missing credentials for API call.")
        return False

    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header:
        return False
        
    goods_owner_id = int(ONGOING_GOODS_OWNER_ID)
    
    order_number = psf_order_data.get("orderNumber")
    if not order_number:
        print("ERROR: orderNumber is a mandatory field.")
        return False

    shipping_addr = psf_order_data.get("shipping_address", {})
    consignee = {
        "name": f"{shipping_addr.get('firstName', '')} {shipping_addr.get('lastName', '')}".strip(),
        "address": shipping_addr.get("address1"),
        "address2": shipping_addr.get("address2"),
        "postCode": shipping_addr.get("zip"),
        "city": shipping_addr.get("city"),
        "countryCode": shipping_addr.get("countryCode"),
        "email": shipping_addr.get("email"),
        "mobilePhone": shipping_addr.get("phone"),
    }
    
    order_lines = []
    for i, item in enumerate(psf_order_data.get("line_items", [])):
        order_lines.append({
            "rowNumber": i + 1,
            "articleNumber": item.get("sku"),
            "numberOfItems": item.get("quantity"),
            "articleName": item.get("name"),
            "customerLinePrice": item.get("price"),
        })

    order_payload = {
        "goodsOwnerId": goods_owner_id,
        "orderNumber": order_number,
        "deliveryDate": (date.today() + timedelta(days=1)).isoformat(),
        "orderRemark": psf_order_data.get("note"),
        "deliveryInstruction": psf_order_data.get("shippingMethodTitle"),
        "consignee": consignee,
        "orderLines": order_lines,
        "wayOfDeliveryType": "B2C-Parcel",
        "customerPrice": psf_order_data.get("totalPrice"),
        "currency": psf_order_data.get("currency"),
    }

    orders_endpoint = f"{BASE_API_URL}orders"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"\nINFO: Attempting to create/update order: {order_number}")
    # FINAL CHANGE: We use the PUT method on the general /orders endpoint.
    print(f"INFO: Requesting URL: PUT {orders_endpoint}")
    # print(f"INFO: Payload: {json.dumps(order_payload, indent=2)}") # Uncomment for debugging

    try:
        # FINAL CHANGE: Use PUT to create or update the order.
        response = requests.put(orders_endpoint, headers=headers, data=json.dumps(order_payload))
        response.raise_for_status()
        
        print(f"INFO: API Call Successful! Status Code: {response.status_code}")
        try:
            response_data = response.json()
            print("INFO: Response from server:")
            print(json.dumps(response_data, indent=2))
        except json.JSONDecodeError:
            print("INFO: No JSON content in response. Order creation successful.")

        return True

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error during order creation: {http_err}")
        if hasattr(response, 'status_code'): print(f"  Status Code: {response.status_code}")
        if hasattr(response, 'text'): print(f"  Response Text: {response.text}")
    except Exception as err:
        print(f"ERROR: An unexpected error occurred during order creation: {err}")

    return False

if __name__ == "__main__":
    # (This section remains unchanged)
    print("--- Ongoing WMS Order Creation Script ---")
    
    sample_psf_order = {
        "orderNumber": f"PSF-{uuid.uuid4().hex[:8]}", 
        "note": "Customer requested gift wrapping if possible.",
        "shippingMethodTitle": "Standard Shipping",
        "totalPrice": 29.99,
        "currency": "USD",
        "shipping_address": {
            "firstName": "John",
            "lastName": "Doe",
            "address1": "123 Main Street",
            "address2": "Apt 4B",
            "zip": "10001",
            "city": "New York",
            "countryCode": "US",
            "email": "john.doe@example.com",
            "phone": "+15551234567"
        },
        "line_items": [
            {
                "sku": "PSF-BOOK-001",
                "name": "The Ultimate Guide to Funnels",
                "quantity": 1,
                "price": 29.99
            }
        ]
    }
    
    if create_ongoing_order(sample_psf_order):
        print("\nSUCCESS: The order was successfully sent to Ongoing WMS.")
    else:
        print("\nFAILURE: The order could not be sent to Ongoing WMS.")
    
    print("\nScript execution finished.")