import requests
import os
import json
from dotenv import load_dotenv # Import load_dotenv

# --- Configuration ---
# Load environment variables from the .env file into the environment
load_dotenv() 

GHL_TOKEN = os.getenv("GHL_PRIVATE_TOKEN")
LOCATION_ID = os.getenv("PSF_LOCATION_ID")

# GHL API v2 Base URL (LeadConnector is the underlying platform for GHL)
BASE_URL = "https://services.leadconnectorhq.com"

# GHL API Version Header (Use the version relevant to the endpoints you're calling)
# Check GHL documentation for the latest stable version if needed.
API_VERSION = "2021-07-28" 

# --- Helper Function to Make API Calls ---
def make_ghl_request(endpoint, method="GET", params=None, data=None):
    """ Makes a request to the GHL API. (Error handling remains the same) """
    if not GHL_TOKEN:
        print("Error: GHL_PRIVATE_TOKEN not found.")
        print("Please ensure you have a .env file in the same directory as the script")
        print("and it contains the line: GHL_PRIVATE_TOKEN='your_actual_token_here'")
        return None
    
    # <<< Add check for LOCATION_ID >>>
    if not LOCATION_ID or LOCATION_ID == "YOUR_LOCATION_ID_HERE":
        print("Error: LOCATION_ID is not set in the script.")
        print("Please replace 'YOUR_LOCATION_ID_HERE' with your actual GHL Location ID.")
        return None

    url = BASE_URL + endpoint
    headers = {
        "Authorization": f"Bearer {GHL_TOKEN}", 
        "Version": API_VERSION,
        "Accept": "application/json", 
        "Content-Type": "application/json" 
    }

    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, params=params, json=data)
        else:
            print(f"Error: Unsupported HTTP method '{method}'")
            return None

        response.raise_for_status() 

        if response.text:
            return response.json()
        else:
            print(f"Request successful (Status {response.status_code}), but no content returned.")
            return None 

    except requests.exceptions.RequestException as e:
        print(f"Error making API request to {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                # <<< Try to get more detail from 403 specifically >>>
                if e.response.status_code == 403:
                     print("Received 403 Forbidden. Check:")
                     print("  1. Is the LOCATION_ID correct?")
                     print(f"     (Using LOCATION_ID: {LOCATION_ID})")
                     print("  2. Does your Private Integration token have the 'View Payment Orders' scope enabled?")
                     print("  3. Are the altId and altType parameters correct for this endpoint?")
                print(f"Response body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response body (non-JSON): {e.response.text}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}")
        print(f"Response text: {response.text}")
        return None

# --- Example Usage: Fetching Orders ---
def get_all_orders(limit=20):
    """ Fetches orders from GHL, now including required parameters. """
    endpoint = "/payments/orders" 
    
    # <<< Include required parameters altId and altType >>>
    params = {
        "limit": limit,
        "altId": LOCATION_ID,  # Required Location ID
        "altType": "location"  # Required Type
        # Add other optional filters as needed:
        # "status": "paid", 
        # "startAt": "YYYY-MM-DD", 
    }
    
    print(f"Fetching orders from endpoint: {endpoint} with params: {params}")
    orders_data = make_ghl_request(endpoint, method="GET", params=params)
    return orders_data

# --- Main Execution ---
if __name__ == "__main__":
    print("Attempting to fetch GHL Orders using token from .env file...")
    
    # First check if LOCATION_ID is set before proceeding
    if not LOCATION_ID or LOCATION_ID == "YOUR_LOCATION_ID_HERE":
        print("\nPlease set the LOCATION_ID variable in the script before running.")
    else:
        orders_response = get_all_orders(limit=5) 

        if orders_response:
            print("\n--- Successfully fetched orders ---")
            orders_list = orders_response.get('orders') 
            if orders_list is not None and isinstance(orders_list, list):
                 print(f"Found {len(orders_list)} order(s).")
                 if orders_list:
                     print("\n--- Details of the first order: ---")
                     print(json.dumps(orders_list[0], indent=2)) 
            else:
                 print("\n--- Full Response (structure might differ): ---")
                 print(json.dumps(orders_response, indent=2))
        else:
            print("\n--- Failed to fetch orders ---")
