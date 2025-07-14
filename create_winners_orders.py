import os
import requests
import json
from datetime import date, timedelta
from dotenv import load_dotenv

# Import the necessary functions and models from wms_service
from wms_service import (
    create_ongoing_order,
    OngoingWMSOrderPayload,
    get_country_code
)

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
# 1. Add the GHL Contact IDs for the winners here
WINNER_CONTACT_IDS = [
    "hGQSTibUpurKuZdmZXFF",
    "eWGw3DSfHMnvmDLPZLja",
    "SN5b9U2aUdyOwlFowu56",
    # "CONTACT_ID_WINNER_4" # Add the 4th winner ID here
]

# 2. Configure the prize details
PRIZE_SKU = "PSF-BOOK-001"
PRIZE_NAME = "Lyckas på Amazon (Webinar Winner)"
PRIZE_QUANTITY = 1
PRIZE_PRICE = 0.00


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


def run():
    print("--- Starting script to create orders for webinar winners ---")

    if not WINNER_CONTACT_IDS or "CONTACT_ID_WINNER_1" in WINNER_CONTACT_IDS:
        print("\nERROR: Please add the real GHL Contact IDs to the WINNER_CONTACT_IDS list.")
        return

    goods_owner_id = int(os.getenv("ONGOING_GOODS_OWNER_ID"))

    for contact_id in WINNER_CONTACT_IDS:
        print(f"\n--- Processing winner with Contact ID: {contact_id} ---")

        # 1. Get contact details from GHL
        contact = get_ghl_contact_details(contact_id)
        if not contact:
            print(f"SKIPPING: Could not retrieve details for contact {contact_id}.")
            continue
            
        # 2. Manually build the WMS Order Payload
        try:
            iso_country_code = get_country_code(contact.get("country"))
            
            # This is the full payload for the order, including the advanced consignee details
            order_payload_data = {
                "goodsOwnerId": goods_owner_id,
                "orderNumber": f"WINNER-{contact_id[:8]}", # Create a unique order number
                "deliveryDate": (date.today() + timedelta(days=1)),
                "orderRemark": "Webinar book winner",
                "customerPrice": PRIZE_PRICE,
                "currency": "SEK",
                "consignee": {
                    "customerNumber": f"GHL-{contact_id}",
                    "name": f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                    "address1": contact.get("address1"),
                    "address2": contact.get("address2"),
                    "postCode": contact.get("postalCode"),
                    "city": contact.get("city"),
                    "countryCode": iso_country_code,
                    # --- NEW: Advanced notification settings ---
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
                    "numberOfItems": PRIZE_QUANTITY,
                    "articleName": PRIZE_NAME,
                    "customerLinePrice": PRIZE_PRICE
                }],
                "wayOfDeliveryType": "B2C-Parcel"
            }
            # We can't use the Pydantic model from the main service file anymore
            # because it's structured differently for this manual script.
            # We will send the dictionary directly as JSON.
            
        except Exception as e:
            print(f"SKIPPING: Could not create the payload for contact {contact_id}. Error: {e}")
            continue

        # 3. Create the order in Ongoing
        print(f"INFO: Attempting to create order for {contact.get('firstName')}")
        # Manually call the order creation part since Pydantic model isn't used
        auth_header = get_ongoing_auth_header(os.getenv("ONGOING_USERNAME"), os.getenv("ONGOING_PASSWORD"))
        if not auth_header:
            print("ERROR: Could not get Ongoing auth header. Skipping.")
            continue
            
        orders_endpoint = f"https://{os.getenv('ONGOING_API_SERVER')}/{os.getenv('ONGOING_WAREHOUSE_NAME')}/api/v1/orders"
        headers = {"Authorization": auth_header, "Content-Type": "application/json", "Accept": "application/json"}
        payload_json = json.dumps(order_payload_data)
        
        print(f"DEBUG: Sending this payload to Ongoing WMS:\n{payload_json}")

        try:
            response = requests.put(orders_endpoint, headers=headers, data=payload_json)
            response.raise_for_status()
            print(f"SUCCESS: Order {order_payload_data['orderNumber']} created/updated in Ongoing WMS. Status: {response.status_code}")
        except requests.exceptions.HTTPError as http_err:
            print(f"ERROR: Failed to create order in Ongoing WMS: {http_err}")
            print(f"  WMS Response Status: {http_err.response.status_code}")
            print(f"  WMS Response Text: {http_err.response.text}")
        except Exception as e:
            print(f"ERROR: Unexpected error sending order to Ongoing WMS: {e}")


    print("\n--- Script finished ---")

# We need to add this helper function here for the script to be self-contained
def get_ongoing_auth_header(username, password):
    if not username or not password:
        return None
    credentials = f"{username}:{password}"
    return f"Basic {base64.b64encode(credentials.encode('utf-8')).decode('utf-8')}"

if __name__ == "__main__":
    import base64 # Add import for the helper function
    run()