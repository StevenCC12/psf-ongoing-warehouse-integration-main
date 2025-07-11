from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from wms_service import get_ghl_order_details, map_ghl_order_to_wms_payload, create_ongoing_order

# --- Pydantic Models ---
class HighLevelWebhook(BaseModel):
    contactId: str

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    wmsOrderNumber: str | None = None

app = FastAPI(title="PSF to Ongoing WMS Integrator")

@app.get("/")
async def root():
    return {"message": "PSF-WMS Integration Service is running."}

@app.post("/webhook-receiver", response_model=SuccessResponse)
async def handle_highlevel_order(payload: HighLevelWebhook):
    process_id = os.urandom(4).hex()
    print(f"\n--- [{process_id}] New Webhook Received: {payload.contactId} ---")

    ghl_order_data = get_ghl_order_details(payload.contactId)
    if not ghl_order_data:
        raise HTTPException(status_code=502, detail="Failed to fetch order details from GHL.")

    wms_payload_model = map_ghl_order_to_wms_payload(ghl_order_data)
    if not wms_payload_model:
        raise HTTPException(status_code=500, detail="Failed to map order data for WMS processing.")

    success = create_ongoing_order(wms_payload_model)
    if success:
        return SuccessResponse(message="Order processed and sent to WMS.", wmsOrderNumber=wms_payload_model.orderNumber)
    else:
        raise HTTPException(status_code=502, detail="Failed to create order in WMS.")