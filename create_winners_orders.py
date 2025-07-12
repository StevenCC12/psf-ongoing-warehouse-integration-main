import os
from datetime import date, timedelta
from wms_service import (
    get_ghl_contact_details,
    create_or_update_consignee,
    create_ongoing_order,
    OngoingWMSOrderPayload,
    get_country_code
)

# --- CONFIGURATION ---
# 1. Add the GHL Contact IDs for the four winners here
WINNER_CONTACT_IDS = [
    "CONTACT_ID_WINNER_1",
    "CONTACT_ID_WINNER_2",
    "CONTACT_ID_WINNER_3",
    "CONTACT_ID_WINNER_4"
]

# 2. Configure the prize details
PRIZE_SKU = "PSF-BOOK-001"
PRIZE_NAME = "Lyckas på Amazon (Webinar Winner)"
PRIZE_QUANTITY = 1
PRIZE_PRICE = 0.00

def run():
    print("--- Starting script to create orders for webinar winners ---")

    if "CONTACT_ID_WINNER_1" in WINNER_CONTACT_IDS:
        print("\nERROR: Please replace the placeholder Contact IDs in the WINNER_CONTACT_IDS list.")
        return

    for contact_id in WINNER_CONTACT_IDS:
        print(f"\n--- Processing winner with Contact ID: {contact_id} ---")

        # 1. Get contact details from GHL
        contact = get_ghl_contact_details(contact_id)
        if not contact:
            print(f"SKIPPING: Could not retrieve details for contact {contact_id}.")
            continue

        # 2. Create the consignee record in Ongoing
        iso_country_code = get_country_code(contact.get("country"))
        consignee_payload = {
            "name": f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
            "address": contact.get("address1"),
            "address2": contact.get("address2"),
            "postCode": contact.get("postalCode"),
            "city": contact.get("city"),
            "countryCode": iso_country_code,
            "email": contact.get("email"),
            "mobilePhone": contact.get("phone")
        }
        
        if not create_or_update_consignee(contact_id, consignee_payload):
            print(f"SKIPPING: Failed to create consignee record for contact {contact_id}.")
            continue
            
        # 3. Manually build the WMS Order Payload
        try:
            order_payload_data = {
                "goodsOwnerId": int(os.getenv("ONGOING_GOODS_OWNER_ID")),
                "orderNumber": f"WINNER-{contact_id[:8]}", # Create a unique order number
                "deliveryDate": (date.today() + timedelta(days=1)),
                "orderRemark": "Webinar book winner",
                "customerPrice": PRIZE_PRICE,
                "currency": "SEK",
                "consignee": consignee_payload,
                "orderLines": [{
                    "rowNumber": 1,
                    "articleNumber": PRIZE_SKU,
                    "numberOfItems": PRIZE_QUANTITY,
                    "articleName": PRIZE_NAME,
                    "customerLinePrice": PRIZE_PRICE
                }]
            }
            wms_payload_model = OngoingWMSOrderPayload(**order_payload_data)
        except Exception as e:
            print(f"SKIPPING: Could not create Pydantic model for contact {contact_id}. Error: {e}")
            continue

        # 4. Create the order in Ongoing
        print(f"INFO: Attempting to create order for {contact.get('firstName')}")
        create_ongoing_order(wms_payload_model)

    print("\n--- Script finished ---")

if __name__ == "__main__":
    run()