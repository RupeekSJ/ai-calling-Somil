from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dialer import make_outbound_call
from config import settings

router = APIRouter()

class CallRequest(BaseModel):
    phone_number: str

@router.post("/trigger-call")
async def trigger_outbound_call(request: CallRequest):
    """
    Endpoint to trigger a call to a specific number.
    """
    # The Exophone (Your Virtual Number)
    FROM_NUMBER = "08069489493" 
    
    # The URL that serves the ExoML (XML) logic for the call
    # Ensure this endpoint exists in your app and returns valid XML
    FLOW_URL = f"{settings.public_hostname}/exotel/voicebot"

    try:
        result = make_outbound_call(
            to_number=request.phone_number,
            from_number=FROM_NUMBER,
            exoml_url=FLOW_URL
        )
        return {"status": "success", "call_sid": result.get("Call", {}).get("Sid")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
