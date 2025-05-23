import requests
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# --- Pydantic Models ---

class ArticleDefinition(BaseModel):
    """Pydantic model for article definition in Ongoing WMS"""
    articleNumber: str
    articleName: str
    description: Optional[str] = None
    productCode: Optional[str] = None
    unit: str = "st"  # Default unit as per WooCommerce example
    weight: Optional[float] = None
    classes: Optional[List[str]] = None
    linkToPicture: Optional[str] = None
    isStockArticle: bool = True
    barCode: Optional[str] = None


class ShippingAddress(BaseModel):
    """Pydantic model for shipping address"""
    name: str
    address1: str
    address2: Optional[str] = ""
    address3: Optional[str] = ""
    postCode: str
    city: str
    countryCode: str
    remark: Optional[str] = ""
    email: Optional[str] = ""
    telephone: Optional[str] = ""
    doorCode: Optional[str] = ""


class OrderLine(BaseModel):
    """Pydantic model for order line"""
    articleNumber: str
    numberOfItems: int
    comment: Optional[str] = None
    linePrice: Optional[float] = None
    currencyCode: Optional[str] = None


class Order(BaseModel):
    """Pydantic model for order in Ongoing WMS"""
    orderNumber: str
    deliveryDate: str
    orderRemark: Optional[str] = ""
    orderLines: List[OrderLine]
    delivery: ShippingAddress


class InventoryItem(BaseModel):
    """Pydantic model for inventory item"""
    articleNumber: str
    available: int
    reserved: int
    inStock: int


# --- Main Integration Class ---

class OngoingWMSIntegration:
    def __init__(self, api_key=None, api_secret=None, base_url="https://api.ongoingworks.com"):
        """
        Initialize the Ongoing WMS Integration
        
        Parameters:
        api_key (str): Your Ongoing WMS API key
        api_secret (str): Your Ongoing WMS API secret
        base_url (str): Base URL for Ongoing WMS API
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self._get_auth_token()}" if api_key and api_secret else None
        }
    
    def _get_auth_token(self):
        """Generate Base64 auth token from API key and secret"""
        import base64
        auth_string = f"{self.api_key}:{self.api_secret}"
        return base64.b64encode(auth_string.encode()).decode()
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """
        Make an API request to Ongoing WMS
        
        Parameters:
        method (str): HTTP method (GET, PUT, POST, DELETE)
        endpoint (str): API endpoint
        data (dict): Request body data
        params (dict): Query parameters
        
        Returns:
        dict: Response data or None if error
        """
        url = f"{self.base_url}{endpoint}"
        
        if self.headers["Authorization"] is None and (self.api_key and self.api_secret):
            self.headers["Authorization"] = f"Basic {self._get_auth_token()}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=self.headers, json=data, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.headers, json=data, params=params)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=self.headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code in [200, 201]:
                return response.json() if response.content else None
            else:
                print(f"Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Exception occurred: {str(e)}")
            return None

    # --- Article Management ---
    
    def create_or_update_article(self, article_data: Dict[str, Any]) -> Dict:
        """
        Create or update an article in Ongoing WMS
        
        Parameters:
        article_data (dict): GHL product data
        
        Returns:
        dict: Response from Ongoing WMS API
        """
        # Transform GHL product data to Ongoing WMS format
        ongoing_article = self._transform_article(article_data)
        
        # Send to Ongoing WMS
        return self._make_request("PUT", "/api/v1/articles", data=ongoing_article)
    
    def _transform_article(self, ghl_product: Dict[str, Any]) -> Dict:
        """
        Transform GHL product to Ongoing WMS article format
        Based on WooCommerce field mapping
        
        Parameters:
        ghl_product (dict): Product data from GHL
        
        Returns:
        dict: Article data in Ongoing WMS format
        """
        # Create ArticleDefinition using Pydantic model
        article_def = ArticleDefinition(
            articleNumber=ghl_product.get('sku', ''),  # Required field
            articleName=ghl_product.get('name', ''),   # Required field
            description=ghl_product.get('description', ''),
            productCode=str(ghl_product.get('id', '')),
            weight=ghl_product.get('weight'),
            # Map additional fields as needed
            linkToPicture=ghl_product.get('image_url'),
            barCode=ghl_product.get('barcode')
        )
        
        # Convert to dict for API request
        return article_def.model_dump(exclude_none=True)

    # --- Order Management ---
    
    def create_or_update_order(self, order_data: Dict[str, Any]) -> Dict:
        """
        Create or update an order in Ongoing WMS
        
        Parameters:
        order_data (dict): Order data from GHL
        
        Returns:
        dict: Response from Ongoing WMS API
        """
        # Transform GHL order data to Ongoing WMS format
        ongoing_order = self._transform_order(order_data)
        
        # Send to Ongoing WMS
        return self._make_request("PUT", "/api/v1/orders", data=ongoing_order)
    
    def _transform_order(self, ghl_order: Dict[str, Any]) -> Dict:
        """
        Transform GHL order to Ongoing WMS format
        
        Parameters:
        ghl_order (dict): Order data from GHL
        
        Returns:
        dict: Order data in Ongoing WMS format
        """
        # Extract customer information
        customer_info = ghl_order.get('customer', {})
        shipping_address = ghl_order.get('shipping_address', {})
        
        # Extract order items and create OrderLine objects
        order_lines = []
        for item in ghl_order.get('items', []):
            order_line = OrderLine(
                articleNumber=item.get('sku', ''),
                numberOfItems=int(item.get('quantity', 1)),
                comment=item.get('name', '')
            )
            order_lines.append(order_line)
        
        # Create shipping address
        delivery = ShippingAddress(
            name=shipping_address.get('name', ''),
            address1=shipping_address.get('address', ''),
            address2=shipping_address.get('address2', ''),
            postCode=shipping_address.get('zip', ''),
            city=shipping_address.get('city', ''),
            countryCode=shipping_address.get('country', 'US'),
            remark=shipping_address.get('notes', ''),
            email=customer_info.get('email', ''),
            telephone=customer_info.get('phone', '')
        )
        
        # Create the order
        order = Order(
            orderNumber=ghl_order.get('internal_order_id', ''),
            deliveryDate=datetime.now().strftime("%Y-%m-%d"),
            orderRemark=ghl_order.get('notes', ''),
            orderLines=[line.model_dump(exclude_none=True) for line in order_lines],
            delivery=delivery.model_dump(exclude_none=True)
        )
        
        # Convert to dict for API request
        return order.model_dump(exclude_none=True)
    
    def get_order_status(self, order_number: str) -> Dict:
        """
        Get order status from Ongoing WMS
        
        Parameters:
        order_number (str): Order number to check
        
        Returns:
        dict: Order status information
        """
        return self._make_request("GET", f"/api/v1/orders/{order_number}")

    # --- Inventory Management ---
    
    def get_stock_levels(self, article_numbers: Optional[List[str]] = None) -> List[Dict]:
        """
        Get current stock levels from Ongoing WMS
        
        Parameters:
        article_numbers (list): List of article numbers to check stock for
        
        Returns:
        list: Stock levels for requested articles
        """
        params = {}
        if article_numbers:
            params['articleNumbers'] = ','.join(article_numbers)
        
        return self._make_request("GET", "/api/v1/articles/inventory", params=params)
    
    def get_article(self, article_number: str) -> Dict:
        """
        Get article information from Ongoing WMS
        
        Parameters:
        article_number (str): Article number to get
        
        Returns:
        dict: Article information
        """
        return self._make_request("GET", f"/api/v1/articles/{article_number}")


# --- WebHook Handler for GHL ---

class GHLWebhookHandler:
    """
    Handler for GHL webhooks to process events and send to Ongoing WMS
    """
    
    def __init__(self, ongoing_integration):
        """
        Initialize the webhook handler
        
        Parameters:
        ongoing_integration (OngoingWMSIntegration): Ongoing WMS integration instance
        """
        self.ongoing = ongoing_integration
    
    def handle_order_created(self, webhook_data: Dict[str, Any]) -> Dict:
        """
        Handle order created webhook from GHL
        
        Parameters:
        webhook_data (dict): Webhook data from GHL
        
        Returns:
        dict: Response from Ongoing WMS
        """
        # Extract order data from webhook
        order_data = self._extract_order_from_webhook(webhook_data)
        
        # Create or update order in Ongoing WMS
        return self.ongoing.create_or_update_order(order_data)
    
    def _extract_order_from_webhook(self, webhook_data: Dict[str, Any]) -> Dict:
        """
        Extract order data from GHL webhook
        
        Parameters:
        webhook_data (dict): Webhook data from GHL
        
        Returns:
        dict: Extracted order data
        """
        # This needs to be customized based on GHL webhook structure
        # Below is a placeholder assuming webhook_data contains the order
        
        # Here you'll need to adapt to the actual structure of GHL webhooks
        return webhook_data.get('payload', {}).get('order', {})


# Example usage
if __name__ == "__main__":
    # Initialize the integration (add your API key and secret when available)
    ongoing = OngoingWMSIntegration(api_key=None, api_secret=None)
    
    # Example GHL order (adapt to match your actual GHL order structure)
    ghl_order = {
        "internal_order_id": "GHL-12345",
        "customer": {
            "email": "customer@example.com",
            "phone": "123-456-7890"
        },
        "shipping_address": {
            "name": "John Doe",
            "address": "123 Main St",
            "address2": "Apt 4B",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "country": "US"
        },
        "items": [
            {
                "sku": "BOOK-001",
                "name": "Starter Kit Book",
                "quantity": 1
            }
        ],
        "notes": "Please ship as soon as possible"
    }
    
    # Create webhook handler
    webhook_handler = GHLWebhookHandler(ongoing)
    
    # Example usage (commented out for now)
    # Create or update an article
    # article_data = {"sku": "BOOK-001", "name": "Starter Kit Book", "description": "Comprehensive starter guide"}
    # result = ongoing.create_or_update_article(article_data)
    # print(result)
    
    # Create or update an order
    # result = ongoing.create_or_update_order(ghl_order)
    # print(result)
    
    # Get stock levels
    # stock = ongoing.get_stock_levels(["BOOK-001"])
    # print(stock)