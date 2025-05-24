import requests
import base64
import json
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator, EmailStr # Import more from Pydantic
from typing import List, Optional # For type hinting

load_dotenv()

# --- Configurations (using your preferred names) ---
ONGOING_USERNAME = os.getenv("ONGOING_USERNAME")
ONGOING_PASSWORD = os.getenv("ONGOING_PASSWORD")
ONGOING_GOODS_OWNER_ID_STR = os.getenv("ONGOING_GOODS_OWNER_ID")
ONGOING_WAREHOUSE_NAME = os.getenv("ONGOING_WAREHOUSE_NAME")
ONGOING_API_SERVER = os.getenv("ONGOING_API_SERVER", "api.ongoingsystems.se")
BASE_API_URL = f"https://{ONGOING_API_SERVER}/{ONGOING_WAREHOUSE_NAME}/api/v1/"

PSF_ACCESS_TOKEN = os.getenv("PSF_ACCESS_TOKEN")
PSF_LOCATION_ID = os.getenv("PSF_LOCATION_ID")
GHL_API_BASE_URL = "https://services.leadconnectorhq.com"


# --- Pydantic Models for Ongoing WMS Payload ---
class OngoingWMSConsignee(BaseModel):
    name: str
    address: str
    address2: Optional[str] = None
    postCode: str
    city: str
    countryCode: str # Should be ISO 2-letter
    email: Optional[EmailStr] = None # Pydantic validates email format
    mobilePhone: Optional[str] = None

class OngoingWMSOrderLine(BaseModel):
    articleNumber: str
    numberOfItems: int = Field(gt=0) # Must be greater than 0
    articleName: str
    customerLinePrice: float # Total price for this line (unit price * quantity)

class OngoingWMSOrderPayload(BaseModel):
    goodsOwnerId: int
    orderNumber: str
    deliveryDate: date # Pydantic handles date objects
    orderRemark: Optional[str] = None
    customerPrice: Optional[float] = None # Overall order total
    currency: Optional[str] = Field(None, min_length=3, max_length=3) # e.g., "SEK"
    consignee: OngoingWMSConsignee
    orderLines: List[OngoingWMSOrderLine] = Field(min_length=1) # Must have at least one order line
    wayOfDeliveryType: Optional[str] = "B2C-Parcel"

    @validator('deliveryDate', pre=True, always=True)
    def format_delivery_date(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v

# --- Functions ---

def get_ongoing_auth_header(username, password):
    # ... (no changes to this function)
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

def get_ghl_order_details(contact_id: str) -> dict | None:
    # ... (no changes to the core logic of this function, it still returns a dict)
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in .env file.")
        return None
    headers = {"Authorization": f"Bearer {PSF_ACCESS_TOKEN}", "Version": "2021-07-28", "Accept": "application/json"}
    print(f"INFO: GHL Step 1/2 - Searching for latest transaction for contact: {contact_id}")
    transactions_endpoint = f"{GHL_API_BASE_URL}/payments/transactions"
    trans_params = {"contactId": contact_id, "altId": PSF_LOCATION_ID, "altType": "location", "limit": 1, "sortBy": "createdAt", "order": "desc"}
    try:
        response = requests.get(transactions_endpoint, headers=headers, params=trans_params)
        response.raise_for_status()
        transactions_data = response.json()
        transactions = transactions_data.get("data", [])
        if not transactions:
            print(f"WARNING: No transactions found for contact {contact_id}.")
            return None
        transaction = transactions[0]
        order_id = transaction.get('entityId')
        if not order_id:
            print(f"WARNING: Transaction {transaction.get('_id')} found, but it has no associated entityId (Order ID).")
            return None
        print(f"INFO: GHL Step 1/2 - Found transaction {transaction.get('_id')}, linked to Order ID: {order_id}")
    except Exception as e:
        print(f"ERROR during GHL transaction lookup: {e}")
        return None
    print(f"INFO: GHL Step 2/2 - Fetching full order details for Order ID: {order_id}")
    order_endpoint = f"{GHL_API_BASE_URL}/payments/orders/{order_id}"
    order_params = {"altId": PSF_LOCATION_ID, "altType": "location"}
    try:
        response = requests.get(order_endpoint, headers=headers, params=order_params)
        response.raise_for_status()
        order_data = response.json()
        print("INFO: GHL Step 2/2 - Successfully fetched final order data.")
        return order_data
    except Exception as e:
        print(f"ERROR during GHL order lookup: {e}")
        return None

def map_ghl_order_to_wms_payload(ghl_order_data: dict) -> Optional[OngoingWMSOrderPayload]:
    print("INFO: Mapping GHL order data to Ongoing WMS payload format...")
    if not ghl_order_data or not ghl_order_data.get("_id"):
        print("ERROR: Invalid or empty ghl_order_data received for mapping.")
        return None

    order_id_from_ghl = ghl_order_data.get("_id")
    contact_snapshot = ghl_order_data.get("contactSnapshot", {})
    items = ghl_order_data.get("items", [])

    if not items:
        print(f"WARNING: Order {order_id_from_ghl} from GHL contains no line items.")
        return None

    line_items_for_wms_data = []
    for item in items:
        price_details = item.get("price", {})
        sku = price_details.get("sku")
        if not sku:
            print(f"WARNING: Line item '{item.get('name')}' in GHL order {order_id_from_ghl} is missing an SKU. Skipping.")
            continue
        try:
            quantity = int(item.get("qty", 1))
            if quantity <= 0: quantity = 1
        except (ValueError, TypeError): quantity = 1
        try:
            unit_price = float(price_details.get("amount", 0))
        except (ValueError, TypeError): unit_price = 0.0
        
        line_items_for_wms_data.append({
            "articleNumber": sku,
            "numberOfItems": quantity,
            "articleName": item.get("name", "N/A"),
            "customerLinePrice": round(unit_price * quantity, 2)
        })
    
    if not line_items_for_wms_data:
        print(f"ERROR: No valid line items with SKUs could be mapped for GHL order {order_id_from_ghl}.")
        return None

    try:
        goods_owner_id_int = int(ONGOING_GOODS_OWNER_ID_STR)
    except (ValueError, TypeError):
        print(f"CRITICAL ERROR: ONGOING_GOODS_OWNER_ID ('{ONGOING_GOODS_OWNER_ID_STR}') is not a valid integer.")
        return None

    try:
        # Create the Pydantic model instance. This will validate the data.
        payload_data = {
            "goodsOwnerId": goods_owner_id_int,
            "orderNumber": f"PSF-{order_id_from_ghl}",
            "deliveryDate": (date.today() + timedelta(days=1)), # Pydantic will handle date to str
            "orderRemark": ghl_order_data.get("notes") or f"Order from PSF: {order_id_from_ghl}",
            "customerPrice": ghl_order_data.get("amount"),
            "currency": ghl_order_data.get("currency", "SEK").upper(),
            "consignee": {
                "name": f"{contact_snapshot.get('firstName', '')} {contact_snapshot.get('lastName', '')}".strip(),
                "address": contact_snapshot.get("address1", "N/A"),
                "address2": contact_snapshot.get("address2"),
                "postCode": contact_snapshot.get("postalCode", "N/A"),
                "city": contact_snapshot.get("city", "N/A"),
                "countryCode": contact_snapshot.get("country", "N/A"),
                "email": contact_snapshot.get("email"),
                "mobilePhone": contact_snapshot.get("phone"),
            },
            "orderLines": line_items_for_wms_data,
            "wayOfDeliveryType": "B2C-Parcel",
        }
        wms_payload_model = OngoingWMSOrderPayload(**payload_data)
        print(f"INFO: Successfully mapped GHL order {order_id_from_ghl} to Pydantic WMS model.")
        return wms_payload_model
    except Exception as e: # Pydantic's ValidationError is a subclass of Exception
        print(f"ERROR: Pydantic validation error during mapping GHL order {order_id_from_ghl}: {e}")
        return None


def create_ongoing_order(wms_payload_model: OngoingWMSOrderPayload) -> bool: # Takes the Pydantic model
    print(f"INFO: Sending Pydantic model payload to Ongoing WMS for order: {wms_payload_model.orderNumber}")
    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header: return False

    orders_endpoint = f"{BASE_API_URL}orders"
    headers = {"Authorization": auth_header, "Content-Type": "application/json", "Accept": "application/json"}

    try:
        # Serialize the Pydantic model to JSON for the request
        # Pydantic V2 uses model_dump_json(). If using Pydantic V1, it's .json()
        response = requests.put(orders_endpoint, headers=headers, data=wms_payload_model.model_dump_json(by_alias=True))
        response.raise_for_status()
        print(f"SUCCESS: Order {wms_payload_model.orderNumber} created/updated in Ongoing WMS. Status: {response.status_code}")
        try:
            print("Ongoing WMS Response:", response.json())
        except json.JSONDecodeError:
            print("Ongoing WMS Response: (No JSON content)")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Failed to create order in Ongoing WMS: {http_err}")
        print(f"  WMS Response Status: {http_err.response.status_code}")
        print(f"  WMS Response Text: {http_err.response.text}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error sending order to Ongoing WMS: {e}")
        return False