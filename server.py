from fastapi import FastAPI, HTTPException
import uvicorn
import os
from pydantic import BaseModel
from typing import Optional
import json

# Import our service functions
from wms_service import (
    get_ghl_order_details,
    map_ghl_order_to_wms_payload,
    create_ongoing_order,
    create_winner_order
)

# --- Pydantic Models ---
class HighLevelWebhook(BaseModel):
    contactId: str

class WinnerWebhook(BaseModel):
    contact_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address1: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    tags: Optional[str] = None

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    wmsOrderNumber: str | None = None

app = FastAPI(
    title="PSF to Ongoing WMS Integrator",
    description="Receives webhooks from HighLevel and creates orders in Ongoing WMS.",
    version="1.1.0"
)

@app.get("/")
async def root():
    return {"message": "PSF-WMS Integration Service v1.1.0 is running."}

@app.post("/webhook-receiver", response_model=SuccessResponse)
async def handle_highlevel_order(payload: HighLevelWebhook):
    process_id = os.urandom(4).hex()
    print(f"\n--- [{process_id}] New Webhook Received ---")
    print(f"[{process_id}] INFO: Validated Webhook payload received. Contact ID: {payload.contactId}")

    ghl_order_data = get_ghl_order_details(payload.contactId)
    if not ghl_order_data:
        raise HTTPException(status_code=502, detail=f"Failed to fetch order details from GHL for contact {payload.contactId}.")
    
    print(f"[{process_id}] DEBUG: Full GHL order data received:\n{json.dumps(ghl_order_data, indent=2)}")

    wms_payload_model = map_ghl_order_to_wms_payload(ghl_order_data)
    if not wms_payload_model:
        raise HTTPException(status_code=500, detail="Failed to map order data for WMS processing.")
    
    success = create_ongoing_order(wms_payload_model)
    
    if success:
        print(f"--- [{process_id}] Workflow Complete: Success ---")
        return SuccessResponse(
            message="Order processed and sent to WMS.",
            wmsOrderNumber=wms_payload_model.orderNumber
        )
    else:
        raise HTTPException(status_code=502, detail="Failed to create order in WMS.")

@app.post("/winner-webhook", response_model=SuccessResponse)
async def handle_winner_webhook(payload: WinnerWebhook):
    process_id = os.urandom(4).hex()
    print(f"\n--- [{process_id}] Winner Webhook Received ---")
    print(f"[{process_id}] INFO: Contact ID: {payload.contact_id}, Name: {payload.first_name} {payload.last_name}")

    wms_payload = create_winner_order(payload.model_dump())
    if not wms_payload:
        raise HTTPException(status_code=500, detail="Failed to build WMS payload from winner webhook data.")

    success = create_ongoing_order(wms_payload)

    if success:
        print(f"--- [{process_id}] Winner Order Complete: Success ---")
        return SuccessResponse(
            message="Winner order sent to WMS.",
            wmsOrderNumber=wms_payload.orderNumber
        )
    else:
        raise HTTPException(status_code=502, detail="Failed to create winner order in WMS.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)