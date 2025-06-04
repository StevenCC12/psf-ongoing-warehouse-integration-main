import requests
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()

# --- Ongoing WMS Configuration ---
ONGOING_USERNAME = os.getenv("ONGOING_USERNAME")
ONGOING_PASSWORD = os.getenv("ONGOING_PASSWORD")
ONGOING_GOODS_OWNER_ID_STR = os.getenv("ONGOING_GOODS_OWNER_ID")
ONGOING_WAREHOUSE_NAME = os.getenv("ONGOING_WAREHOUSE_NAME")
ONGOING_API_SERVER = os.getenv("ONGOING_API_SERVER", "api.ongoingsystems.se")
BASE_API_URL = f"https://{ONGOING_API_SERVER}/{ONGOING_WAREHOUSE_NAME}/api/v1/"

# Using your preferred variable names now
PSF_ACCESS_TOKEN = os.getenv("PSF_ACCESS_TOKEN") 
PSF_LOCATION_ID = os.getenv("PSF_LOCATION_ID")

def get_ongoing_auth_header(username, password):
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

def create_or_update_article_in_ongoing(article_data_payload: dict):
    if not ONGOING_GOODS_OWNER_ID_STR:
        print("CRITICAL ERROR: ONGOING_GOODS_OWNER_ID is not set.")
        return False
        
    try:
        # goodsOwnerId is part of the payload itself for this endpoint
        pass 
    except ValueError:
        # This check is now implicitly handled by the payload construction
        pass

    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header:
        return False

    article_number_in_payload = article_data_payload.get("articleNumber")
    if not article_number_in_payload:
        print("ERROR: articleNumber is a required field in the article_data_payload.")
        return False

    article_endpoint = f"{BASE_API_URL}articles" 
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"\nINFO: Attempting to create/update article: {article_number_in_payload}")
    print(f"INFO: Requesting URL: PUT {article_endpoint}")
    print(f"INFO: Payload: {json.dumps(article_data_payload, indent=2)}")

    try:
        response = requests.put(article_endpoint, headers=headers, data=json.dumps(article_data_payload))
        response.raise_for_status() 
        
        print(f"INFO: API Call Successful! Status Code: {response.status_code}")
        try:
            response_data = response.json()
            print("INFO: Response from server:")
            print(json.dumps(response_data, indent=2))
        except json.JSONDecodeError:
            print("INFO: No JSON content in response. Article creation/update likely successful.")
        return True

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error during article creation/update: {http_err}")
        if hasattr(http_err, 'response') and http_err.response is not None:
            print(f"  Status Code: {http_err.response.status_code}")
            print(f"  Response Text: {http_err.response.text}")
        return False
    except Exception as err:
        print(f"ERROR: An unexpected error occurred: {err}")
        return False

if __name__ == "__main__":
    print("--- Ongoing WMS Article Management Script ---")
    
    # Data for our book, as if fetched from GHL (once productType is fixed there)
    # and mapped to Ongoing WMS API field names based on OpenAPI spec.
    
    goods_owner_id_int = 0
    try:
        goods_owner_id_int = int(ONGOING_GOODS_OWNER_ID_STR)
    except (ValueError, TypeError):
        print(f"CRITICAL ERROR: ONGOING_GOODS_OWNER_ID ('{ONGOING_GOODS_OWNER_ID_STR}') is not a valid integer for the payload.")
        exit()

    # This is the payload we will send, structured according to PostArticleModel
    ongoing_article_payload_to_send = {
        "goodsOwnerId": goods_owner_id_int, # Required
        "articleNumber": "PSF-BOOK-001",    # Required
        "articleName": "Lyckas på Amazon (OpenAPI Updated)", # From GHL product name
        "description": "The definitive guide to succeeding on Amazon, now with OpenAPI precision!", # From GHL product desc
        "unitCode": "st",                   # Swedish "styck" = "piece"
        "isStockArticle": True,             # Crucial: Yes, we track stock for this
        "isActive": True,                   # Yes, it's an active product
        "barCodeInfo": {
            "barCode": ""                   # Optional: Add your EAN/UPC here if you have one
        },
        "weight": 0.733,                    # In KG (as per your GHL product, verify unit with WMS)
        "length": 23.2,                     # In CM (verify unit with WMS)
        "width": 15.7,                      # In CM (verify unit with WMS)
        "height": 2.3,                      # In CM (verify unit with WMS)
        # "volume": calculated_or_from_ghl, # Optional, WMS might calculate it
        "countryOfOriginCode": "SE",        # Example: Sweden
        # "statisticsNumber": "YOUR_COMMODITY_CODE", # Optional: For customs
        # "stockLimit": 10,                 # Optional: Reorder point
        # "netWeight": 0.700                # Optional: If different from gross weight
    }
    
    if create_or_update_article_in_ongoing(ongoing_article_payload_to_send):
        print("\nSUCCESS: Article was successfully created/updated in Ongoing WMS.")
        print("Next step: Ask your warehouse admin to add stock to this article (PSF-BOOK-001).")
    else:
        print("\nFAILURE: Article could not be created/updated.")
    
    print("\nScript execution finished.")