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
    create_ongoing_order,
    create_or_update_consignee # <-- IMPORT THE NEW FUNCTION
)

# ... (Pydantic models are the same) ...
class HighLevelWebhook(BaseModel):
    contactId: str

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    wmsOrderNumber: str | None = None

app = FastAPI(
    title="PSF to Ongoing WMS Integrator",
    description="Receives webhooks from HighLevel and creates orders in Ongoing WMS.",
    version="1.0.4" # Updated version
)

@app.get("/")
async def root():
    return {"message": "PSF-WMS Integration Service v1.0.4 is running."}

@app.post("/webhook-receiver", response_model=SuccessResponse)
async def handle_highlevel_order(payload: HighLevelWebhook):
    process_id = os.urandom(4).hex()
    contact_id = payload.contactId
    print(f"\n--- [{process_id}] New Webhook Received ---")
    print(f"[{process_id}] INFO: Validated Webhook payload received. Contact ID: {contact_id}")

    # 1. Get GHL order details
    ghl_order_data = get_ghl_order_details(contact_id)
    if not ghl_order_data:
        raise HTTPException(status_code=502, detail=f"Failed to fetch order details from GHL for contact {contact_id}.")
    print(f"[{process_id}] DEBUG: Full GHL order data received:\n{json.dumps(ghl_order_data, indent=2)}")

    # 2. Map GHL data to WMS payload model
    wms_payload_model = map_ghl_order_to_wms_payload(ghl_order_data)
    if not wms_payload_model:
        raise HTTPException(status_code=500, detail="Failed to map order data for WMS processing.")

    # --- NEW STEP: Create or Update the Consignee in Ongoing ---
    consignee_updated = create_or_update_consignee(
        ghl_contact_id=contact_id,
        consignee_data=wms_payload_model.consignee.model_dump()
    )
    if not consignee_updated:
        # We can decide if this is a critical failure or not.
        # For now, we will log a warning but still attempt to create the order.
        print(f"[{process_id}] WARNING: Failed to create/update the consignee master record. The order may be missing some details in the Ongoing UI.")

    # 3. Send the complete order to the WMS
    order_created = create_ongoing_order(wms_payload_model)
    
    if order_created:
        print(f"--- [{process_id}] Workflow Complete: Success ---")
        return SuccessResponse(
            message="Order processed and sent to WMS.",
            wmsOrderNumber=wms_payload_model.orderNumber
        )
    else:
        raise HTTPException(status_code=502, detail="Failed to create order in WMS.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)