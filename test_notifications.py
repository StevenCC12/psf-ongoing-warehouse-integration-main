import os
import requests
import json
import base64
from datetime import date, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
# 1. IMPORTANT: Replace this with your own GHL Contact ID
YOUR_CONTACT_ID = "HxtEIMhtLvNhkqNQIWym"

# 2. Test details
TEST_REMARK = "Test for email, phone and automatic notifications"
PRIZE_SKU = "PSF-BOOK-001"
PRIZE_NAME = "Lyckas på Amazon (Test Order)"

# --- SCRIPT-SPECIFIC FUNCTION ---
def get_ghl_contact_details(contact_id: str) -> dict | None:
    """Fetches the full details for a single contact from GHL."""
    print(f"INFO: GHL - Fetching details for contact: {contact_id}")
    psf_access_token = os.getenv("PSF_ACCESS_TOKEN")
    if not psf_access_token:
        print("ERROR: PSF_ACCESS_TOKEN is not set in .env file.")
        return None
    
    headers = {"Authorization": f"Bearer {psf_access_token}", "Version": "2021-07-28"}
    endpoint = f"https://services.leadconnectorhq.com/contacts/{contact_id}"

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        contact_data = response.json().get("contact")
        print(f"SUCCESS: GHL - Successfully fetched details for contact {contact_id}")
        return contact_data
    except Exception as e:
        print(f"ERROR: GHL - Could not fetch contact details for {contact_id}: {e}")
        return None

def get_ongoing_auth_header(username, password):
    """Encodes Ongoing WMS credentials for Basic Authentication."""
    if not username or not password:
        return None
    credentials = f"{username}:{password}"
    return f"Basic {base64.b64encode(credentials.encode('utf-8')).decode('utf-8')}"

def get_country_code(country_name: str | None) -> str:
    """A simple country code converter."""
    # This can be expanded if needed
    country_map = {"sweden": "SE", "united states": "US"}
    if not country_name:
        return "N/A"
    if len(country_name) == 2 and country_name.isalpha():
        return country_name.upper()
    return country_map.get(country_name.lower(), "N/A")

def run():
    print("--- Starting notification test script ---")

    if YOUR_CONTACT_ID == "PASTE_YOUR_GHL_CONTACT_ID_HERE":
        print("\nERROR: Please replace the placeholder with your actual GHL Contact ID.")
        return

    # 1. Get your contact details from GHL
    contact = get_ghl_contact_details(YOUR_CONTACT_ID)
    if not contact:
        print("--- Script finished: Could not retrieve contact details ---")
        return
        
    # 2. Build the WMS Order Payload with advanced notification settings
    try:
        iso_country_code = get_country_code(contact.get("country"))
        
        order_payload_data = {
            "goodsOwnerId": int(os.getenv("ONGOING_GOODS_OWNER_ID")),
            "orderNumber": f"TEST-{YOUR_CONTACT_ID[:8]}",
            "deliveryDate": (date.today() + timedelta(days=1)).isoformat(),
            "orderRemark": TEST_REMARK,
            "customerPrice": 0.00,
            "currency": "SEK",
            "consignee": {
                "customerNumber": f"GHL-{YOUR_CONTACT_ID}",
                "name": f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                "address1": contact.get("address1"),
                "address2": contact.get("address2"),
                "postCode": contact.get("postalCode"),
                "city": contact.get("city"),
                "countryCode": iso_country_code,
                "advanced": {
                    "smsNotification": {
                        "toBeNotified": True,
                        "value": contact.get("phone")
                    },
                    "emailNotification": {
                        "toBeNotified": True,
                        "value": contact.get("email")
                    }
                }
            },
            "orderLines": [{
                "rowNumber": 1,
                "articleNumber": PRIZE_SKU,
                "numberOfItems": 1,
                "articleName": PRIZE_NAME,
                "customerLinePrice": 0.00
            }],
            "wayOfDeliveryType": "B2C-Parcel"
        }
        
    except Exception as e:
        print(f"SKIPPING: Could not create the payload. Error: {e}")
        return

    # 3. Create the order in Ongoing
    print(f"INFO: Attempting to create test order for {contact.get('firstName')}")
    
    auth_header = get_ongoing_auth_header(os.getenv("ONGOING_USERNAME"), os.getenv("ONGOING_PASSWORD"))
    if not auth_header:
        print("ERROR: Could not get Ongoing auth header. Exiting.")
        return
        
    orders_endpoint = f"https://{os.getenv('ONGOING_API_SERVER')}/{os.getenv('ONGOING_WAREHOUSE_NAME')}/api/v1/orders"
    headers = {"Authorization": auth_header, "Content-Type": "application/json", "Accept": "application/json"}
    payload_json = json.dumps(order_payload_data)
    
    print(f"DEBUG: Sending this payload to Ongoing WMS:\n{payload_json}")

    try:
        response = requests.put(orders_endpoint, headers=headers, data=payload_json)
        response.raise_for_status()
        print(f"\nSUCCESS! Order {order_payload_data['orderNumber']} was created in Ongoing WMS.")
        print("Please check the Ongoing UI to confirm the details are correct.")
    except requests.exceptions.HTTPError as http_err:
        print(f"\nERROR: Failed to create order in Ongoing WMS: {http_err}")
        print(f"  Response Status: {http_err.response.status_code}")
        print(f"  Response Text: {http_err.response.text}")
    except Exception as e:
        print(f"\nERROR: An unexpected error occurred: {e}")

    print("\n--- Script finished ---")

if __name__ == "__main__":
    run()