print("🚀 STARTING SERVER V5.0 - EXOTEL + SARVAM TTS (PROD READY)")

import os
import uuid
import logging
import requests
import traceback
import time
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import base64

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")

EXOTEL_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("voicebot")

logger.info("🚀 Config loaded")
logger.info(f"PUBLIC_HOSTNAME = {PUBLIC_HOSTNAME}")
logger.info(f"EXOTEL_SID loaded = {'✅' if EXOTEL_SID else '❌'}")
logger.info(f"EXOTEL_FROM_NUMBER = {EXOTEL_FROM_NUMBER}")

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(title="Rupeek VoiceBot + Sarvam TTS", version="5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# REQUEST LOGGER
# --------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    start = time.time()

    logger.info(f"➡️  [{req_id}] {request.method} {request.url}")
    logger.info(f"➡️  [{req_id}] HEADERS={dict(request.headers)}")

    response = await call_next(request)

    duration = time.time() - start
    logger.info(
        f"⬅️  [{req_id}] STATUS={response.status_code} TIME={duration:.3f}s"
    )

    return response

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class DialRequest(BaseModel):
    from_: str = Field(..., alias="from")  # USER PHONE NUMBER (+91...)

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
# SARVAM TTS HELPER
# --------------------------------------------------
def generate_sarvam_audio(text: str) -> str:
    """
    Call Sarvam API to generate TTS audio.
    Returns a base64 audio string.
    """
    try:
        payload = {"text": text, "voice": "en-IN"}
        headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}

        resp = requests.post(
            "https://api.sarvam.ai/v1/tts",
            json=payload,
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        audio_base64 = data.get("audio_base64", "")
        logger.info("✅ Sarvam TTS generated successfully")
        return audio_base64
    except Exception as e:
        logger.error(f"❌ Sarvam TTS failed: {e}")
        return ""

# --------------------------------------------------
# EXOML
# --------------------------------------------------
@app.get("/exoml")
@app.post("/exoml")
async def exoml():
    logger.info("🎤 EXOML HIT — CALL CONNECTED")

    welcome_text = (
        "Namaste. Welcome to Rupeek gold loans. "
        "We offer instant gold loans up to seventy five percent of your gold value. "
        "Press 1 for more details."
    )

    # Generate dynamic audio
    audio_base64 = await asyncio.to_thread(generate_sarvam_audio, welcome_text)

    if audio_base64:
        # Use <Play> with base64 audio
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>data:audio/wav;base64,{audio_base64}</Play>
    <Gather input="dtmf"
            timeout="10"
            finishOnKey="#"
            action="{PUBLIC_HOSTNAME}/collect">
        <Say language="en-IN">
            Press 1 for more details.
        </Say>
    </Gather>
</Response>
"""
    else:
        # Fallback using <Say>
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="en-IN">{welcome_text}</Say>
    <Gather input="dtmf"
            timeout="10"
            finishOnKey="#"
            action="{PUBLIC_HOSTNAME}/collect">
        <Say language="en-IN">
            Press 1 for more details.
        </Say>
    </Gather>
</Response>
"""

    return Response(content=xml, media_type="application/xml")

# --------------------------------------------------
# DTMF COLLECT
# --------------------------------------------------
@app.post("/collect")
async def collect(request: Request):
    body = await request.body()
    logger.info(f"🔢 DTMF RECEIVED: {body}")

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="en-IN">
        Thank you. Our team will contact you shortly. Goodbye.
    </Say>
</Response>
"""
    return Response(content=xml, media_type="application/xml")

# --------------------------------------------------
# CALL STATUS WEBHOOK
# --------------------------------------------------
@app.post("/call-status")
async def call_status(request: Request):
    body = await request.body()
    logger.info(f"📡 CALL STATUS CALLBACK RECEIVED: {body}")
    return Response(content="OK", media_type="text/plain")

# --------------------------------------------------
# DIAL
# --------------------------------------------------
@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(f"📞 DIAL REQUEST RECEIVED | USER={request.from_}")

    missing = []
    if not EXOTEL_SID: missing.append("EXOTEL_ACCOUNT_SID")
    if not EXOTEL_API_KEY: missing.append("EXOTEL_API_KEY")
    if not EXOTEL_API_TOKEN: missing.append("EXOTEL_API_TOKEN")
    if not EXOTEL_FROM_NUMBER: missing.append("EXOTEL_FROM_NUMBER")

    if missing:
        logger.error(f"❌ Missing ENV VARS: {missing}")
        return JSONResponse(
            {"error": f"Missing env vars: {', '.join(missing)}"},
            status_code=500,
        )

    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"

    payload = {
        "From": request.from_,
        "CallerId": EXOTEL_FROM_NUMBER,
        "Url": f"{PUBLIC_HOSTNAME}/exoml",
        "StatusCallback": f"{PUBLIC_HOSTNAME}/call-status",
    }

    logger.info(f"📤 EXOTEL REQUEST PAYLOAD = {payload}")

    try:
        resp = requests.post(
            url,
            data=payload,
            auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
            timeout=15,
        )

        logger.info("📥 EXOTEL RESPONSE HEADERS")
        logger.info(dict(resp.headers))

        logger.info("📥 EXOTEL RESPONSE BODY")
        logger.info(resp.text)

        if resp.status_code != 200:
            return JSONResponse(
                {"status_code": resp.status_code, "response": resp.text},
                status_code=500,
            )

        data = resp.json()
        call_sid = data.get("Call", {}).get("Sid", "UNKNOWN")

        logger.info(f"✅ CALL INITIATED | CallSid={call_sid}")

        return {"status": "success", "call_sid": call_sid}

    except Exception:
        logger.error("❌ DIAL EXCEPTION")
        logger.error(traceback.format_exc())
        return JSONResponse(
            {"status": "error", "message": "Dial failed"},
            status_code=500,
        )

# --------------------------------------------------
# LOCAL RUN
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
