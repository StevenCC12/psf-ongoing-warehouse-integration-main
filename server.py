from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from pydantic import BaseModel
import json

# Import our service functions
from wms_service import (
    get_ghl_order_details,
    map_ghl_order_to_wms_payload,
    create_ongoing_order
)

# --- Pydantic Models for API Request/Response ---
class HighLevelWebhook(BaseModel):
    contactId: str

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    wmsOrderNumber: str | None = None

app = FastAPI(
    title="PSF to Ongoing WMS Integrator",
    description="Receives webhooks from HighLevel and creates orders in Ongoing WMS.",
    version="1.0.5" # Final version
)

@app.get("/")
async def root():
    return {"message": "PSF-WMS Integration Service v1.0.5 is running."}

@app.post("/webhook-receiver", response_model=SuccessResponse)
async def handle_highlevel_order(payload: HighLevelWebhook):
    process_id = os.urandom(4).hex()
    print(f"\n--- [{process_id}] New Webhook Received ---")
    print(f"[{process_id}] INFO: Validated Webhook payload received. Contact ID: {payload.contactId}")

    # Step 1: Get the full order details from GHL
    ghl_order_data = get_ghl_order_details(payload.contactId)
    if not ghl_order_data:
        raise HTTPException(status_code=502, detail=f"Failed to fetch order details from GHL for contact {payload.contactId}.")
    
    print(f"[{process_id}] DEBUG: Full GHL order data received:\n{json.dumps(ghl_order_data, indent=2)}")

    # Step 2: Map the GHL data to the WMS payload format
    wms_payload_model = map_ghl_order_to_wms_payload(ghl_order_data)
    if not wms_payload_model:
        raise HTTPException(status_code=500, detail="Failed to map order data for WMS processing.")
    
    # Step 3: Send the complete order to the WMS
    success = create_ongoing_order(wms_payload_model)
    
    if success:
        print(f"--- [{process_id}] Workflow Complete: Success ---")
        return SuccessResponse(
            message="Order processed and sent to WMS.",
            wmsOrderNumber=wms_payload_model.orderNumber
        )
    else:
        raise HTTPException(status_code=502, detail="Order data was fetched, but failed to create order in WMS.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)