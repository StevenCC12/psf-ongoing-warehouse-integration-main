import requests
import base64
import json
import os

# Attempt to load environment variables from .env file
try:
    from dotenv import load_dotenv
    if load_dotenv():
        print("INFO: Loaded environment variables from .env file.")
    else:
        print("INFO: No .env file found or it was empty, relying on system environment variables.")
except ImportError:
    print("INFO: python-dotenv library not found. Relying on system environment variables.")

# --- Configuration (Store these in your .env file or system environment) ---
ONGOING_USERNAME = os.getenv("ONGOING_USERNAME")
ONGOING_PASSWORD = os.getenv("ONGOING_PASSWORD")
ONGOING_GOODS_OWNER_ID = os.getenv("ONGOING_GOODS_OWNER_ID") # This is an integer, but read as string from env
ONGOING_WAREHOUSE_NAME = os.getenv("ONGOING_WAREHOUSE_NAME") # The {warehouse} part of the URL
ONGOING_API_SERVER = os.getenv("ONGOING_API_SERVER", "api.ongoingsystems.se") # Default to production server

# Construct the Base API URL
if not ONGOING_WAREHOUSE_NAME:
    print("CRITICAL ERROR: ONGOING_WAREHOUSE_NAME environment variable is not set.")
    exit()

# Check if it's a demo system URL structure if needed, for now assuming production or that ONGOING_API_SERVER handles it
BASE_API_URL = f"https://{ONGOING_API_SERVER}/{ONGOING_WAREHOUSE_NAME}/api/v1/"


def get_ongoing_auth_header(username, password):
    """Generates the Basic Authentication header for Ongoing WMS API."""
    if not username or not password:
        print("ERROR: Ongoing WMS Username or Password not provided.")
        return None
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_credentials}"

def test_ongoing_api_connection(goods_owner_id_str):
    """
    Tests the API connection by attempting to fetch a list of articles (or another simple GET request).
    """
    if not all([ONGOING_USERNAME, ONGOING_PASSWORD, goods_owner_id_str]):
        print("ERROR: Missing credentials (username, password, or goodsOwnerId) for API test.")
        return False

    auth_header = get_ongoing_auth_header(ONGOING_USERNAME, ONGOING_PASSWORD)
    if not auth_header:
        return False

    try:
        goods_owner_id = int(goods_owner_id_str) # GoodsOwnerId is usually an integer
    except ValueError:
        print(f"ERROR: ONGOING_GOODS_OWNER_ID ('{goods_owner_id_str}') is not a valid integer.")
        return False

    # Example endpoint: Get articles (SKUs) for the goods owner.
    # This endpoint usually supports pagination. For a simple test, we might get the first few.
    # According to common REST patterns, it might be /articles or /articles?goodsOwnerId=...
    # The provided docs mention "By making a GET request to the /articles endpoint, you will receive information..."
    # And "If there are too many objects which match your filter... if the goods owner has 100 000 articles and you try to fetch them all with GetInventoryByQuery..."
    # Let's assume /articles requires goodsOwnerId as a query parameter.
    
    articles_endpoint = f"{BASE_API_URL}articles"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json"
        # Content-Type is not needed for GET requests without a body
    }
    params = {
        "goodsOwnerId": goods_owner_id,
        "pageSize": 5 # Requesting only a few items for a test
    }

    print(f"\nINFO: Attempting to test API connection by fetching articles...")
    print(f"INFO: Requesting URL: GET {articles_endpoint} with params {params}")

    try:
        response = requests.get(articles_endpoint, headers=headers, params=params)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        
        print(f"INFO: API Test Connection Successful! Status Code: {response.status_code}")
        articles_data = response.json()
        print("INFO: Successfully fetched article data (sample):")
        if isinstance(articles_data, list) and articles_data: # Often /articles returns a list
            for i, article in enumerate(articles_data[:2]): # Print first 2 articles
                print(f"  Article {i+1}: {json.dumps(article, indent=2)}")
        elif isinstance(articles_data, dict) and "articles" in articles_data : # Sometimes it's nested
             for i, article in enumerate(articles_data["articles"][:2]):
                print(f"  Article {i+1}: {json.dumps(article, indent=2)}")
        else:
            print(json.dumps(articles_data, indent=2)) # Print whatever structure it is

        return True

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error during API test: {http_err}")
        if hasattr(response, 'status_code'): print(f"  Status Code: {response.status_code}")
        if hasattr(response, 'text'): print(f"  Response Text: {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Request error during API test: {req_err}")
    except json.JSONDecodeError as json_err:
        print(f"ERROR: JSON decode error during API test: {json_err}")
        if hasattr(response, 'text'): print(f"  Response Text was: {response.text}")
    except Exception as err:
        print(f"ERROR: An unexpected error occurred during API test: {err}")

    return False

if __name__ == "__main__":
    print("--- Ongoing WMS API Connection Test Script ---")
    if not ONGOING_GOODS_OWNER_ID:
        print("CRITICAL ERROR: ONGOING_GOODS_OWNER_ID environment variable is not set.")
    else:
        if test_ongoing_api_connection(ONGOING_GOODS_OWNER_ID):
            print("\nSUCCESS: API authentication and basic data retrieval appear to be working.")
            print("You can now proceed to build functions for creating orders.")
        else:
            print("\nFAILURE: Could not successfully connect to or retrieve data from the Ongoing WMS API.")
            print("Please check your credentials, Goods Owner ID, Warehouse Name, and API server settings.")
    
    print("\nScript execution finished.")