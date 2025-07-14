import requests
import base64
import json
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Optional
import time

# ... (Configurations and country mapping are the same) ...
load_dotenv()

# --- Configurations ---
ONGOING_USERNAME = os.getenv("ONGOING_USERNAME")
ONGOING_PASSWORD = os.getenv("ONGOING_PASSWORD")
ONGOING_GOODS_OWNER_ID_STR = os.getenv("ONGOING_GOODS_OWNER_ID")
ONGOING_WAREHOUSE_NAME = os.getenv("ONGOING_WAREHOUSE_NAME")
ONGOING_API_SERVER = os.getenv("ONGOING_API_SERVER", "api.ongoingsystems.se")
BASE_API_URL = f"https://{ONGOING_API_SERVER}/{ONGOING_WAREHOUSE_NAME}/api/v1/"

PSF_ACCESS_TOKEN = os.getenv("PSF_ACCESS_TOKEN")
PSF_LOCATION_ID = os.getenv("PSF_LOCATION_ID")
GHL_API_BASE_URL = "https://services.leadconnectorhq.com"

# --- Country Code Mapping ---
COUNTRY_CODE_MAP = {
    "sweden": "SE", "united states": "US", "united kingdom": "GB",
    "norway": "NO", "denmark": "DK", "finland": "FI", "germany": "DE",
}

def get_country_code(country_name: str | None) -> str:
    if not country_name: return "N/A"
    if len(country_name) == 2 and country_name.isalpha(): return country_name.upper()
    return COUNTRY_CODE_MAP.get(country_name.lower(), "N/A")


# --- Pydantic Models (No changes) ---
class OngoingWMSConsignee(BaseModel):
    name: str
    address: str
    address2: Optional[str] = None
    postCode: str
    city: str
    countryCode: str
    email: Optional[EmailStr] = None
    mobilePhone: Optional[str] = None

class OngoingWMSOrderLine(BaseModel):
    rowNumber: int
    articleNumber: str
    numberOfItems: int = Field(gt=0)
    articleName: str
    customerLinePrice: float

class OngoingWMSOrderPayload(BaseModel):
    goodsOwnerId: int
    orderNumber: str
    deliveryDate: date
    orderRemark: Optional[str] = None
    customerPrice: Optional[float] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    consignee: OngoingWMSConsignee
    orderLines: List[OngoingWMSOrderLine] = Field(min_length=1)
    wayOfDeliveryType: Optional[str] = "B2C-Parcel"

    @validator('deliveryDate', pre=True, always=True)
    def format_delivery_date(cls, v):
        if isinstance(v, str): return date.fromisoformat(v)
        return v

# --- Functions ---

def get_ongoing_auth_header(username, password):
    # ... (no changes)
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

# --- NEW FUNCTION ---
def create_or_update_consignee(ghl_contact_id: str, consignee_data: dict) -> bool:
    """Creates or updates a customer record in Ongoing WMS."""
    print("INFO: Attempting to create or update customer in Ongoing WMS...")
    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header: return False

    # --- FIXED: Corrected the API endpoint from /consignees to /customers ---
    customer_endpoint = f"{BASE_API_URL}customers"
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    
    # --- FIXED: Changed payload keys to match the /customers endpoint ---
    payload = {
        "goodsOwnerId": int(ONGOING_GOODS_OWNER_ID_STR),
        "customerNumber": f"GHL-{ghl_contact_id}", # Use GHL Contact ID as the unique identifier
        "customerName": consignee_data.get("name"),
        "address": consignee_data.get("address"),
        "address2": consignee_data.get("address2"),
        "postCode": consignee_data.get("postCode"),
        "city": consignee_data.get("city"),
        "countryCode": consignee_data.get("countryCode"),
        "telephone": consignee_data.get("mobilePhone"),
        "email": consignee_data.get("email")
    }
    
    print(f"DEBUG: Sending this payload to Ongoing WMS /customers:\n{json.dumps(payload, indent=2)}")

    try:
        # Use the corrected endpoint
        response = requests.put(customer_endpoint, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        print(f"SUCCESS: Customer GHL-{ghl_contact_id} created/updated in Ongoing WMS. Status: {response.status_code}")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Failed to create/update customer in Ongoing WMS: {http_err}")
        print(f"  WMS Response Status: {http_err.response.status_code}")
        print(f"  WMS Response Text: {http_err.response.text}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error sending customer to Ongoing WMS: {e}")
        return False

def get_ghl_order_details(contact_id: str, retries: int = 3, delay_seconds: int = 20) -> dict | None:
    # ... (no changes)
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in .env file.")
        return None
    headers = {"Authorization": f"Bearer {PSF_ACCESS_TOKEN}", "Version": "2021-07-28", "Accept": "application/json"}
    print(f"INFO: GHL Step 1/2 - Initiating search for latest transaction for contact: {contact_id}")
    transactions_endpoint = f"{GHL_API_BASE_URL}/payments/transactions"
    trans_params = {"contactId": contact_id, "altId": PSF_LOCATION_ID, "altType": "location", "limit": 1, "sortBy": "createdAt", "order": "desc"}
    order_id = None
    for attempt in range(retries):
        print(f"INFO: GHL Step 1/2 - Attempt {attempt + 1}/{retries} for transaction lookup...")
        try:
            response = requests.get(transactions_endpoint, headers=headers, params=trans_params)
            response.raise_for_status()
            transactions = response.json().get("data", [])
            if transactions:
                order_id = transactions[0].get('entityId')
                if order_id:
                    print(f"INFO: GHL Step 1/2 - Success on attempt {attempt + 1}: Found transaction {transactions[0].get('_id')}, linked to Order ID: {order_id}")
                    break
            print(f"WARNING: GHL Step 1/2 - Attempt {attempt + 1}: No valid transaction/orderId found.")
            if attempt < retries - 1: time.sleep(delay_seconds)
        except Exception as e:
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1: time.sleep(delay_seconds)
    if not order_id:
        print(f"ERROR: GHL Step 1/2 - Failed to find an Order ID for contact {contact_id} after {retries} attempts.")
        return None
    print(f"INFO: GHL Step 2/2 - Fetching full order details for Order ID: {order_id}")
    order_endpoint = f"{GHL_API_BASE_URL}/payments/orders/{order_id}"
    order_params = {"altId": PSF_LOCATION_ID, "altType": "location"}
    try:
        response = requests.get(order_endpoint, headers=headers, params=order_params)
        response.raise_for_status()
        print("INFO: GHL Step 2/2 - Successfully fetched final order data.")
        return response.json()
    except Exception as e:
        print(f"ERROR during GHL order lookup: {e}")
        return None


def map_ghl_order_to_wms_payload(ghl_order_data: dict) -> Optional[OngoingWMSOrderPayload]:
    # ... (no changes to the logic here, it's already correct) ...
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
    for index, item in enumerate(items):
        sku = item.get("price", {}).get("sku")
        if not sku:
            print(f"WARNING: Line item '{item.get('name')}' in GHL order {order_id_from_ghl} is missing an SKU. Skipping.")
            continue
        line_items_for_wms_data.append({
            "rowNumber": index + 1,
            "articleNumber": sku,
            "numberOfItems": int(item.get("qty", 1)),
            "articleName": item.get("name", "N/A"),
            "customerLinePrice": round(float(item.get("price", {}).get("amount", 0)) * int(item.get("qty", 1)), 2)
        })

    if not line_items_for_wms_data:
        print(f"ERROR: No valid line items with SKUs could be mapped for GHL order {order_id_from_ghl}.")
        return None
    try:
        goods_owner_id_int = int(ONGOING_GOODS_OWNER_ID_STR)
    except (ValueError, TypeError):
        print(f"CRITICAL ERROR: ONGOING_GOODS_OWNER_ID ('{ONGOING_GOODS_OWNER_ID_STR}') is not a valid integer.")
        return None

    country_from_ghl = contact_snapshot.get("country")
    iso_country_code = get_country_code(country_from_ghl)
    print(f"INFO: Converted country '{country_from_ghl}' to ISO code '{iso_country_code}'.")
    
    try:
        payload_data = {
            "goodsOwnerId": goods_owner_id_int, "orderNumber": f"PSF-{order_id_from_ghl}",
            "deliveryDate": (date.today() + timedelta(days=1)),
            "orderRemark": ghl_order_data.get("notes") or f"Order from PSF: {order_id_from_ghl}",
            "customerPrice": ghl_order_data.get("amount"), "currency": ghl_order_data.get("currency", "SEK").upper(),
            "consignee": {
                "name": f"{contact_snapshot.get('firstName', '')} {contact_snapshot.get('lastName', '')}".strip(),
                "address": contact_snapshot.get("address1", "N/A"), "address2": contact_snapshot.get("address2"),
                "postCode": contact_snapshot.get("postalCode", "N/A"), "city": contact_snapshot.get("city", "N/A"),
                "countryCode": iso_country_code, "email": contact_snapshot.get("email"), "mobilePhone": contact_snapshot.get("phone"),
            },
            "orderLines": line_items_for_wms_data, "wayOfDeliveryType": "B2C-Parcel",
        }
        wms_payload_model = OngoingWMSOrderPayload(**payload_data)
        print(f"INFO: Successfully mapped GHL order {order_id_from_ghl} to Pydantic WMS model.")
        return wms_payload_model
    except Exception as e:
        print(f"ERROR: Pydantic validation error during mapping GHL order {order_id_from_ghl}: {e}")
        return None
    

def get_ghl_contact_details(contact_id: str) -> dict | None:
    """Fetches the full details for a single contact from GHL."""
    print(f"INFO: GHL - Fetching details for contact: {contact_id}")
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in .env file.")
        return None
    
    headers = {"Authorization": f"Bearer {PSF_ACCESS_TOKEN}", "Version": "2021-07-28"}
    endpoint = f"{GHL_API_BASE_URL}/contacts/{contact_id}"

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        contact_data = response.json().get("contact")
        print(f"SUCCESS: GHL - Successfully fetched details for contact {contact_id}")
        return contact_data
    except Exception as e:
        print(f"ERROR: GHL - Could not fetch contact details for {contact_id}: {e}")
        return None


def create_ongoing_order(wms_payload_model: OngoingWMSOrderPayload) -> bool:
    print(f"INFO: Sending Pydantic model payload to Ongoing WMS for order: {wms_payload_model.orderNumber}")
    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header: return False

    orders_endpoint = f"{BASE_API_URL}orders"
    headers = {"Authorization": auth_header, "Content-Type": "application/json", "Accept": "application/json"}
    
    payload_json = wms_payload_model.model_dump_json(by_alias=True)
    print(f"DEBUG: Sending this payload to Ongoing WMS:\n{payload_json}")

    try:
        response = requests.put(orders_endpoint, headers=headers, data=payload_json)
        response.raise_for_status()
        print(f"SUCCESS: Order {wms_payload_model.orderNumber} created/updated in Ongoing WMS. Status: {response.status_code}")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: Failed to create order in Ongoing WMS: {http_err}")
        print(f"  WMS Response Status: {http_err.response.status_code}")
        print(f"  WMS Response Text: {http_err.response.text}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error sending order to Ongoing WMS: {e}")
        return False