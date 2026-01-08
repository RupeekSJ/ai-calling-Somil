print("🚀 STARTING SERVER V4 - EXOTEL CONNECT.JSON (FINAL)")

import os
import logging
import requests
import traceback
from typing import Optional

from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("voicebot")

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")

EXOTEL_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")  # not used yet

logger.info("🚀 Config loaded")
logger.info(f"PUBLIC_HOSTNAME = {PUBLIC_HOSTNAME}")
logger.info(f"EXOTEL_SID loaded = {'✅' if EXOTEL_SID else '❌'}")
logger.info(f"EXOTEL_FROM_NUMBER = {EXOTEL_FROM_NUMBER}")

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(title="Rupeek VoiceBot", version="4.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class DialRequest(BaseModel):
    from_: str = Field(..., alias="from")  # USER PHONE NUMBER


# --------------------------------------------------
# HEALTH & DEBUG
# --------------------------------------------------
@app.get("/")
async def health():
    return {"status": "ok", "service": "rupeek-voicebot"}

@app.get("/debug")
async def debug():
    return {
        "PUBLIC_HOSTNAME": PUBLIC_HOSTNAME,
        "EXOTEL_ACCOUNT_SID": bool(EXOTEL_SID),
        "EXOTEL_API_KEY": bool(EXOTEL_API_KEY),
        "EXOTEL_API_TOKEN": bool(EXOTEL_API_TOKEN),
        "EXOTEL_FROM_NUMBER": EXOTEL_FROM_NUMBER,
        "SARVAM_API_KEY": bool(SARVAM_API_KEY),
    }


# --------------------------------------------------
# EXOML
# --------------------------------------------------
@app.get("/exoml")
@app.post("/exoml")
async def exoml():
    logger.info("🎤 ExoML HIT")

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak language="en-IN">
        Namaste. Welcome to Rupeek gold loans.
    </Speak>
    <Pause length="1"/>
    <Speak language="en-IN">
        We offer instant gold loans up to seventy five percent of your gold value.
    </Speak>
    <Pause length="1"/>
    <Speak language="en-IN">
        Press 1 for more details or hang up to end this call.
    </Speak>
    <Gather
        action="https://ai-calling-somil.onrender.com/collect"
        inputTimeout="5"
        finishOnKey="#"
    />
</Response>
"""
    return Response(content=xml, media_type="application/xml")


@app.post("/collect")
async def collect(request: Request):
    body = await request.body()
    logger.info(f"🔢 DTMF RECEIVED: {body}")

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak language="en-IN">
        Thank you. Our team will contact you shortly. Goodbye.
    </Speak>
</Response>
"""
    return Response(content=xml, media_type="application/xml")


# --------------------------------------------------
# DIAL (Exotel connect.json)
# --------------------------------------------------
@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(
        f"📞 Dial request | USER={request.from_} | EXOTEL={EXOTEL_FROM_NUMBER}"
    )

    missing = []
    if not EXOTEL_SID:
        missing.append("EXOTEL_ACCOUNT_SID")
    if not EXOTEL_API_KEY:
        missing.append("EXOTEL_API_KEY")
    if not EXOTEL_API_TOKEN:
        missing.append("EXOTEL_API_TOKEN")
    if not EXOTEL_FROM_NUMBER:
        missing.append("EXOTEL_FROM_NUMBER")

    if missing:
        logger.error(f"❌ Missing env vars: {missing}")
        return JSONResponse(
            {"error": f"Missing env vars: {', '.join(missing)}"},
            status_code=500,
        )

    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"

    payload = {
        "From": request.from_,          # USER number
        "CallerId": EXOTEL_FROM_NUMBER, # EXOTEL number
        "Url": f"{PUBLIC_HOSTNAME}/exoml",
    }

    try:
        resp = requests.post(
            url,
            data=payload,
            auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
            timeout=10,
        )

        logger.info(
            f"🔍 Exotel response {resp.status_code}: {resp.text[:300]}"
        )

        if resp.status_code != 200:
            return JSONResponse(
                {
                    "error": "Exotel call failed",
                    "status_code": resp.status_code,
                    "response": resp.text,
                },
                status_code=500,
            )

        data = resp.json()
        call_sid = (
            data.get("CallSid")
            or data.get("call", {}).get("sid")
            or "UNKNOWN"
        )

        logger.info(f"✅ Call placed | CallSid={call_sid}")

        return {"status": "success", "call_sid": call_sid}

    except Exception:
        logger.error(traceback.format_exc())
        return JSONResponse(
            {"status": "error", "message": "Dial failed"},
            status_code=500,
        )


# --------------------------------------------------
# WEBSOCKET (NOT USED BY EXOTEL)
# --------------------------------------------------
@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    await ws.send_json(
        {"message": "WebSocket active (Exotel does not use this)"}
    )


# --------------------------------------------------
# LOCAL RUN
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
