import requests
import base64
import json
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Optional
import time

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


# --- Pydantic Models ---
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
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v

# --- Functions ---

def get_ongoing_auth_header(username, password):
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

def get_ghl_order_details(contact_id: str, retries: int = 3, delay_seconds: int = 20) -> dict | None:
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in .env file.")
        return None
    headers = {"Authorization": f"Bearer {PSF_ACCESS_TOKEN}", "Version": "2021-07-28", "Accept": "application/json"}

    print(f"INFO: GHL Step 1/2 - Initiating search for latest transaction for contact: {contact_id}")
    transactions_endpoint = f"{GHL_API_BASE_URL}/payments/transactions"
    trans_params = {"contactId": contact_id, "altId": PSF_LOCATION_ID, "altType": "location", "limit": 1, "sortBy": "createdAt", "order": "desc"}
    
    order_id = None
    transaction_id_for_logging = None

    for attempt in range(retries):
        print(f"INFO: GHL Step 1/2 - Attempt {attempt + 1}/{retries} for transaction lookup...")
        try:
            response = requests.get(transactions_endpoint, headers=headers, params=trans_params)
            response.raise_for_status()
            transactions_data = response.json()
            transactions = transactions_data.get("data", [])

            if transactions:
                transaction = transactions[0]
                transaction_id_for_logging = transaction.get('_id')
                order_id = transaction.get('entityId')
                
                if order_id:
                    print(f"INFO: GHL Step 1/2 - Success on attempt {attempt + 1}: Found transaction {transaction_id_for_logging}, linked to Order ID: {order_id}")
                    break
                else:
                    print(f"WARNING: GHL Step 1/2 - Attempt {attempt + 1}: Transaction {transaction_id_for_logging} found, but it has no associated entityId (Order ID).")
            else:
                print(f"WARNING: GHL Step 1/2 - Attempt {attempt + 1}: No transactions found for contact {contact_id}.")

            if attempt < retries - 1:
                print(f"INFO: Waiting {delay_seconds} seconds before next attempt...")
                time.sleep(delay_seconds)
            else:
                if not transactions:
                    print(f"ERROR: GHL Step 1/2 - Failed to find any transactions for contact {contact_id} after {retries} attempts.")
                elif not order_id:
                     print(f"ERROR: GHL Step 1/2 - Found transaction(s) (e.g., {transaction_id_for_logging}) but none had a valid Order ID after {retries} attempts.")
                return None

        except requests.exceptions.RequestException as req_err:
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: RequestException during transaction lookup: {req_err}")
        except Exception as e:
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: Unexpected error during transaction lookup: {e}")
        
        if attempt < retries - 1:
            print(f"INFO: Waiting {delay_seconds} seconds before next attempt due to previous error or missing data...")
            time.sleep(delay_seconds)
        elif order_id is None:
            print(f"ERROR: GHL Step 1/2 - All {retries} attempts failed to secure an Order ID.")
            return None

    if not order_id:
        return None

    print(f"INFO: GHL Step 2/2 - Fetching full order details for Order ID: {order_id}")
    order_endpoint = f"{GHL_API_BASE_URL}/payments/orders/{order_id}"
    order_params = {"altId": PSF_LOCATION_ID, "altType": "location"}
    try:
        response = requests.get(order_endpoint, headers=headers, params=order_params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"ERROR during GHL order lookup: {e}")
        return None

def map_ghl_order_to_wms_payload(ghl_order_data: dict) -> Optional[OngoingWMSOrderPayload]:
    if not ghl_order_data or not ghl_order_data.get("_id"):
        return None

    order_id_from_ghl = ghl_order_data.get("_id")
    contact_snapshot = ghl_order_data.get("contactSnapshot", {})
    items = ghl_order_data.get("items", [])
    if not items:
        return None

    line_items_for_wms_data = []
    for item in items:
        price_details = item.get("price", {})
        sku = price_details.get("sku")
        if not sku:
            continue
        quantity = int(item.get("qty", 1))
        unit_price = float(price_details.get("amount", 0))
        
        line_items_for_wms_data.append({
            "articleNumber": sku,
            "numberOfItems": quantity,
            "articleName": item.get("name", "N/A"),
            "customerLinePrice": round(unit_price * quantity, 2)
        })
    
    if not line_items_for_wms_data:
        return None

    try:
        goods_owner_id_int = int(ONGOING_GOODS_OWNER_ID_STR)
    except (ValueError, TypeError):
        return None

    try:
        payload_data = {
            "goodsOwnerId": goods_owner_id_int,
            "orderNumber": f"PSF-{order_id_from_ghl}",
            "deliveryDate": (date.today() + timedelta(days=1)),
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
        }
        return OngoingWMSOrderPayload(**payload_data)
    except Exception as e:
        print(f"ERROR: Pydantic validation error: {e}")
        return None

def create_ongoing_order(wms_payload_model: OngoingWMSOrderPayload) -> bool:
    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header: return False

    orders_endpoint = f"{BASE_API_URL}orders"
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}

    try:
        response = requests.put(orders_endpoint, headers=headers, data=wms_payload_model.model_dump_json())
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"ERROR: Failed to create order in Ongoing WMS: {e}")
        return False