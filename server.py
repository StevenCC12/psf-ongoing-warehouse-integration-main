from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from pydantic import BaseModel # Import BaseModel from Pydantic

# Import our service functions
from wms_service import get_ghl_order_details, map_ghl_order_to_wms_payload, create_ongoing_order

# --- Pydantic Models for API Request/Response ---
class HighLevelWebhook(BaseModel):
    contactId: str # We expect a contactId from the GHL webhook

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    wmsOrderNumber: str | None = None

class ErrorResponse(BaseModel): # Though FastAPI handles 422 validation errors automatically
    detail: str

app = FastAPI(
    title="PSF to Ongoing WMS Integrator",
    description="Receives webhooks from HighLevel and creates orders in Ongoing WMS.",
    version="1.0.2" # Updated version
)

@app.get("/")
async def root():
    return {"message": "PSF-WMS Integration Service v1.0.2 is running."}

@app.post("/webhook-receiver", response_model=SuccessResponse) # Define a success response model
async def handle_highlevel_order(payload: HighLevelWebhook): # Use the Pydantic model for input validation
    process_id = os.urandom(4).hex()
    print(f"\n--- [{process_id}] New Webhook Received ---")
    print(f"[{process_id}] INFO: Validated Webhook payload received. Contact ID: {payload.contactId}")

    # 1. Get the full, reliable order details from GHL using our 2-step process
    ghl_order_data = get_ghl_order_details(payload.contactId) # Pass the validated contactId
    if not ghl_order_data:
        print(f"[{process_id}] ERROR: Failed to fetch complete order details from GHL for contact {payload.contactId}.")
        # FastAPI will return a 500 if an HTTPException is raised.
        # For specific error responses, you can catch exceptions and return JSONResponse with an ErrorResponse model.
        raise HTTPException(status_code=502, detail=f"Failed to fetch order details from GHL for contact {payload.contactId}.")
    print(f"[{process_id}] INFO: Successfully fetched complete order details from GHL.")

    # 2. Map the GHL data to the format the WMS needs
    wms_payload_model = map_ghl_order_to_wms_payload(ghl_order_data) # This will now return a Pydantic model or None
    if not wms_payload_model:
        print(f"[{process_id}] ERROR: Failed to map GHL order data to WMS payload.")
        raise HTTPException(status_code=500, detail="Failed to map order data for WMS processing.")
    print(f"[{process_id}] INFO: Successfully mapped data for WMS. OrderNumber: {wms_payload_model.orderNumber}")
    
    # 3. Send the complete order to the WMS
    success = create_ongoing_order(wms_payload_model) # Pass the Pydantic model
    
    if success:
        print(f"--- [{process_id}] Workflow Complete: Success ---")
        return SuccessResponse(
            message="Order processed and sent to WMS.",
            wmsOrderNumber=wms_payload_model.orderNumber
        )
    else:
        print(f"--- [{process_id}] Workflow Complete: Failure ---")
        # Consider how to differentiate between a mapping failure (500) vs WMS failure (502)
        raise HTTPException(status_code=502, detail="Order data was fetched, but failed to create order in WMS.")

if __name__ == "__main__":
    print("Starting local server for PSF-OngoingWMS Integration...")
    print("Listening on http://0.0.0.0:8000")
    print("Webhook endpoint: /webhook-receiver")
    uvicorn.run(app, host="0.0.0.0", port=8000)