import requests
import base64
import json
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Optional
import time # Added for retry delay

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
    """
    Fetches order details from GHL.
    It first looks for the latest transaction for the contact.
    If found, it uses the transaction's entityId (orderId) to fetch the full order details.
    Includes a retry mechanism for the transaction lookup.
    """
    if not all([PSF_ACCESS_TOKEN, PSF_LOCATION_ID]):
        print("ERROR: PSF_ACCESS_TOKEN or PSF_LOCATION_ID is not set in .env file.")
        return None
    headers = {"Authorization": f"Bearer {PSF_ACCESS_TOKEN}", "Version": "2021-07-28", "Accept": "application/json"}

    # GHL Step 1/2 - Searching for latest transaction
    print(f"INFO: GHL Step 1/2 - Initiating search for latest transaction for contact: {contact_id}")
    transactions_endpoint = f"{GHL_API_BASE_URL}/payments/transactions"
    trans_params = {
        "contactId": contact_id,
        "altId": PSF_LOCATION_ID,
        "altType": "location",
        "limit": 1,
        "sortBy": "createdAt",
        "order": "desc"
    }
    
    order_id = None
    transaction_id_for_logging = None 

    for attempt in range(retries):
        print(f"INFO: GHL Step 1/2 - Attempt {attempt + 1}/{retries} for transaction lookup...")
        try:
            response = requests.get(transactions_endpoint, headers=headers, params=trans_params)
            response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
            transactions_data = response.json()
            transactions = transactions_data.get("data", [])

            if transactions:
                transaction = transactions[0]
                transaction_id_for_logging = transaction.get('_id')
                order_id = transaction.get('entityId')
                
                if order_id:
                    print(f"INFO: GHL Step 1/2 - Success on attempt {attempt + 1}: Found transaction {transaction_id_for_logging}, linked to Order ID: {order_id}")
                    break # Exit retry loop if successful
                else:
                    print(f"WARNING: GHL Step 1/2 - Attempt {attempt + 1}: Transaction {transaction_id_for_logging} found, but it has no associated entityId (Order ID).")
            else: # No transactions found
                print(f"WARNING: GHL Step 1/2 - Attempt {attempt + 1}: No transactions found for contact {contact_id}.")

            if attempt < retries - 1:
                print(f"INFO: Waiting {delay_seconds} seconds before next attempt...")
                time.sleep(delay_seconds)
            else: # Last attempt
                if not transactions:
                    print(f"ERROR: GHL Step 1/2 - Failed to find any transactions for contact {contact_id} after {retries} attempts.")
                elif not order_id:
                     print(f"ERROR: GHL Step 1/2 - Found transaction(s) (e.g., {transaction_id_for_logging}) but none had a valid Order ID after {retries} attempts.")
                return None 

        except requests.exceptions.HTTPError as http_err:
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: HTTPError during transaction lookup: {http_err}")
            if http_err.response.status_code in [401, 403]: # Non-transient auth errors
                print("ERROR: Authentication or Authorization error. Please check PSF_ACCESS_TOKEN and permissions.")
                return None # No point in retrying auth errors
            # For other HTTP errors (e.g., 5xx), retry might help
        except requests.exceptions.RequestException as req_err: # Catches other network errors (DNS, connection timeout, etc.)
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: RequestException during transaction lookup: {req_err}")
        except json.JSONDecodeError as json_err:
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: Failed to decode JSON response during transaction lookup: {json_err}")
            print(f"Response text: {response.text[:200]}...") # Log part of the problematic response
        except Exception as e: 
            print(f"ERROR: GHL Step 1/2 - Attempt {attempt + 1}: Unexpected error during transaction lookup: {e}")
        
        # If any error occurred and we are not yet on the last attempt, wait and retry
        if attempt < retries - 1:
            print(f"INFO: Waiting {delay_seconds} seconds before next attempt due to previous error or missing data...")
            time.sleep(delay_seconds)
        elif order_id is None : # If it's the last attempt and we still don't have an order_id
            print(f"ERROR: GHL Step 1/2 - All {retries} attempts failed to secure an Order ID.")
            return None


    if not order_id:
        print(f"ERROR: GHL Step 1/2 - Ultimately failed to obtain an Order ID for contact {contact_id} after all attempts.")
        return None

    # GHL Step 2/2 - Fetching full order details for Order ID
    print(f"INFO: GHL Step 2/2 - Fetching full order details for Order ID: {order_id}")
    order_endpoint = f"{GHL_API_BASE_URL}/payments/orders/{order_id}"
    order_params = {"altId": PSF_LOCATION_ID, "altType": "location"}
    try:
        response = requests.get(order_endpoint, headers=headers, params=order_params)
        response.raise_for_status()
        order_data = response.json()
        print("INFO: GHL Step 2/2 - Successfully fetched final order data.")
        return order_data
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: GHL Step 2/2 - HTTPError during GHL order lookup for order {order_id}: {http_err}")
        if http_err.response is not None:
            print(f"Response status: {http_err.response.status_code}, Response text: {http_err.response.text[:200]}...")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: GHL Step 2/2 - RequestException during GHL order lookup for order {order_id}: {req_err}")
        return None
    except json.JSONDecodeError as json_err:
        print(f"ERROR: GHL Step 2/2 - Failed to decode JSON response for order {order_id}: {json_err}")
        print(f"Response text: {response.text[:200]}...")
        return None
    except Exception as e:
        print(f"ERROR: GHL Step 2/2 - Unexpected error during GHL order lookup for order {order_id}: {e}")
        return None

def map_ghl_order_to_wms_payload(ghl_order_data: dict) -> Optional[OngoingWMSOrderPayload]:
    # ... (rest of the function remains the same) ...
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
                "countryCode": contact_snapshot.get("country", "N/A"), # Still assuming GHL provides 2-letter code
                "email": contact_snapshot.get("email"),
                "mobilePhone": contact_snapshot.get("phone"),
            },
            "orderLines": line_items_for_wms_data,
            "wayOfDeliveryType": "B2C-Parcel",
        }
        wms_payload_model = OngoingWMSOrderPayload(**payload_data)
        print(f"INFO: Successfully mapped GHL order {order_id_from_ghl} to Pydantic WMS model.")
        return wms_payload_model
    except Exception as e: 
        print(f"ERROR: Pydantic validation error during mapping GHL order {order_id_from_ghl}: {e}")
        return None


def create_ongoing_order(wms_payload_model: OngoingWMSOrderPayload) -> bool:
    # ... (function remains the same) ...
    print(f"INFO: Sending Pydantic model payload to Ongoing WMS for order: {wms_payload_model.orderNumber}")
    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header: return False

    orders_endpoint = f"{BASE_API_URL}orders"
    headers = {"Authorization": auth_header, "Content-Type": "application/json", "Accept": "application/json"}

    try:
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