print("🚀 STARTING SERVER V4.5 - EXOTEL CONNECT.JSON (MAX DEBUG)")

import os
import logging
import requests
import traceback
import uuid
from datetime import datetime

from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

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

logger.info("🚀 Config loaded")
logger.info(f"PUBLIC_HOSTNAME = {PUBLIC_HOSTNAME}")
logger.info(f"EXOTEL_FROM_NUMBER = {EXOTEL_FROM_NUMBER}")

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(title="Rupeek VoiceBot", version="4.5-DEBUG")

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
    from_: str = Field(..., alias="from")

# --------------------------------------------------
# GLOBAL REQUEST LOGGER
# --------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = datetime.utcnow()

    logger.info(
        f"➡️  [{request_id}] {request.method} {request.url} "
        f"HEADERS={dict(request.headers)}"
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.error(f"💥 [{request_id}] UNHANDLED EXCEPTION")
        logger.error(traceback.format_exc())
        raise

    duration = (datetime.utcnow() - start_time).total_seconds()
    logger.info(
        f"⬅️  [{request_id}] {request.method} {request.url} "
        f"STATUS={response.status_code} TIME={duration}s"
    )
    return response

# --------------------------------------------------
# HEALTH
# --------------------------------------------------
@app.get("/")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# --------------------------------------------------
# EXOML
# --------------------------------------------------
@app.get("/exoml")
@app.post("/exoml")
async def exoml(request: Request):
    logger.info("🎤 EXOML HIT — CALL CONNECTED")
    logger.info(f"📞 Exotel headers: {dict(request.headers)}")

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>

    <Pause length="1"/>

    <Say language="en-IN">
        Namaste. Welcome to Rupeek gold loans.
    </Say>

    <Pause length="1"/>

    <Say language="en-IN">
        We offer instant gold loans up to seventy five percent of your gold value.
    </Say>

    <Pause length="1"/>

    <Gather input="dtmf"
            action="https://ai-calling-somil.onrender.com/collect"
            timeout="10"
            finishOnKey="#">
        <Say language="en-IN">
            Press 1 for more details.
        </Say>
    </Gather>

    <Pause length="3"/>

    <Say language="en-IN">
        No input received. Goodbye.
    </Say>

</Response>
"""
    return Response(content=xml, media_type="application/xml")

# --------------------------------------------------
# COLLECT
# --------------------------------------------------
@app.post("/collect")
async def collect(request: Request):
    body = await request.body()
    logger.info("🔢 COLLECT HIT")
    logger.info(f"🔢 RAW BODY = {body}")
    logger.info(f"🔢 HEADERS = {dict(request.headers)}")

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="en-IN">
        Thank you. Our team will contact you shortly. Goodbye.
    </Say>
</Response>
"""
    return Response(content=xml, media_type="application/xml")

# --------------------------------------------------
# CALL STATUS WEBHOOK (🔥 VERY IMPORTANT)
# --------------------------------------------------
@app.post("/call-status")
async def call_status(request: Request):
    body = await request.body()
    logger.info("📡 CALL STATUS WEBHOOK HIT")
    logger.info(f"📡 BODY = {body}")
    logger.info(f"📡 HEADERS = {dict(request.headers)}")
    return {"ok": True}

# --------------------------------------------------
# DIAL
# --------------------------------------------------
@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(f"📞 DIAL REQUEST RECEIVED | USER={request.from_}")

    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"

    payload = {
        "From": request.from_,                 # USER
        "CallerId": EXOTEL_FROM_NUMBER,        # EXOTEL
        "Url": f"{PUBLIC_HOSTNAME}/exoml",
        "StatusCallback": f"{PUBLIC_HOSTNAME}/call-status",
        "StatusCallbackEvents": "initiated,answered,completed",
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
        logger.info(resp.headers)

        logger.info("📥 EXOTEL RESPONSE BODY")
        logger.info(resp.text)

        return {
            "status_code": resp.status_code,
            "response": resp.text
        }

    except Exception:
        logger.error("💥 DIAL FAILED")
        logger.error(traceback.format_exc())
        return JSONResponse(
            {"error": "Dial exception"},
            status_code=500
        )

# --------------------------------------------------
# WEBSOCKET
# --------------------------------------------------
@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"debug": "WebSocket connected"})

# --------------------------------------------------
# LOCAL RUN
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
