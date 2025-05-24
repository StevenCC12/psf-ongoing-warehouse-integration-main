import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
print("INFO: Loaded environment variables.")

# --- Configuration ---
GHL_API_KEY = os.getenv("GHL_API_KEY")
PSF_LOCATION_ID = os.getenv("PSF_LOCATION_ID")
GHL_API_BASE_URL = "https://services.leadconnectorhq.com"

def find_latest_transaction():
    """
    Finds the latest transaction for a specific contact to get the real Order ID.
    """
    print("\n--- Searching for a Transaction, not an Order ---")
    
    if not all([GHL_API_KEY, PSF_LOCATION_ID]):
        print("CRITICAL ERROR: GHL_API_KEY or PSF_LOCATION_ID is not set in your .env file.")
        return

    # Using the confirmed contact ID
    test_contact_id = "HldJrxw4vrfuBdKZf0p4"
    print(f"INFO: Querying for transactions for Contact ID: {test_contact_id}")

    # NEW: Using the /payments/transactions endpoint
    endpoint = f"{GHL_API_BASE_URL}/payments/transactions"
    headers = {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Version": "2021-07-28",
        "Accept": "application/json"
    }

    # Querying the transaction endpoint for our specific contact
    params = {
        "contactId": test_contact_id,
        "altId": PSF_LOCATION_ID,
        "altType": "location",
        "limit": 5, 
        "sortBy": "createdAt",
        "order": "desc"
    }

    print(f"INFO: Making API call to: GET {endpoint}")
    print(f"INFO: Using parameters: {params}")

    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        transactions = data.get("data", []) # The docs say the array is named "data"

        if transactions:
            print(f"\nSUCCESS! Found {len(transactions)} recent transaction(s).")
            print("--- Details of the most recent transaction: ---")
            
            most_recent_transaction = transactions[0]
            print(json.dumps(most_recent_transaction, indent=2))
            
            # --- Verification Step ---
            print("\n--- Verifying Key Data ---")
            transaction_id = most_recent_transaction.get('_id')
            entity_type = most_recent_transaction.get('entityType')
            entity_id = most_recent_transaction.get('entityId') # This is the Order ID!
            status = most_recent_transaction.get('status')
            
            print(f"Transaction ID: {transaction_id}")
            print(f"Transaction Status: {status}")
            print(f"Associated Entity Type: {entity_type}")
            print(f"Associated Entity ID (The Order ID): {entity_id}  <-- THIS IS THE REAL ORDER ID")

        else:
            print("\nINFO: The API call was successful, but no transactions were found for this contact.")

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error: {http_err}")
        print(f"  Response Text: {response.text}")
    except Exception as err:
        print(f"ERROR: An unexpected error occurred: {err}")

if __name__ == "__main__":
    find_latest_transaction()