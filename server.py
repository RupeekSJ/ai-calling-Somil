print("🚀 STARTING SERVER V4 - AUDIO DEBUG + TESTS")

import os
import json
import base64
import logging
import tempfile
import wave
import requests
import traceback
import g711
from typing import Optional
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --- Configuration FIRST ---
load_dotenv()

# Setup Logging FIRST
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("voicebot")

# Load config
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")
EXOTEL_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER", "08069489493")  # ← YOUR EXOTEL NUMBER

logger.info("🚀 Config loaded:")
logger.info(f"   SARVAM_API_KEY: {'✅' if SARVAM_API_KEY else '❌'}")
logger.info(f"   PUBLIC_HOSTNAME: {PUBLIC_HOSTNAME}")
logger.info(f"   EXOTEL_SID: {'✅' if EXOTEL_SID else '❌'}")
logger.info(f"   EXOTEL_FROM_NUMBER: {EXOTEL_FROM_NUMBER}")

app = FastAPI(title="Rupeek VoiceBot", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class DialRequest(BaseModel):
    to: str          # ← EXOTEL NUMBER (08069489493)
    from_: Optional[str] = Field(default=None, alias="from")  # ← USER (+917999796548)
    exoml_url: Optional[str] = None

# 🚀 DEBUG ENDPOINTS
@app.get("/debug")
async def debug():
    return {
        "EXOTEL_ACCOUNT_SID": bool(EXOTEL_SID),
        "EXOTEL_API_KEY": bool(EXOTEL_API_KEY),
        "EXOTEL_API_TOKEN": bool(EXOTEL_API_TOKEN),
        "EXOTEL_FROM_NUMBER": EXOTEL_FROM_NUMBER,
        "PUBLIC_HOSTNAME": PUBLIC_HOSTNAME,
        "SARVAM_API_KEY": bool(SARVAM_API_KEY)
    }

@app.get("/test-tts")
async def test_tts():
    """Test Sarvam TTS directly"""
    audio = generate_sarvam_tts("Hello this is a test")
    return {
        "success": bool(audio),
        "length": len(audio) if audio else 0,
        "sarvam_key_loaded": bool(SARVAM_API_KEY)
    }

@app.get("/")
async def health():
    return {"status": "ok", "service": "rupeek-voicebot-v4-fixed"}

# --- FIXED TTS ---
def generate_sarvam_tts(text: str) -> Optional[str]:
    if not SARVAM_API_KEY:
        logger.error("❌ Sarvam API Key missing")
        return None
    
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
    payload = {
        "inputs": [text],
        "text_language_code": "en",      # ← FIXED
        "voice_id": "meera",             # ← FIXED (not "speaker")
        "output_format": "base64",       # ← CRITICAL
        "sample_rate": 8000              # Exotel compatible
    }
    
    try:
        logger.info(f"🗣️ TTS: '{text[:30]}...'")
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if resp.status_code != 200:
            logger.error(f"❌ TTS HTTP {resp.status_code}: {resp.text[:200]}")
            return None
            
        data = resp.json()
        if "audios" in data and data["audios"]:
            return data["audios"][0]
        return None
    except Exception as e:
        logger.error(f"❌ TTS Exception: {e}")
        return None

# --- FIXED EXOTEL ROUTES ---
@app.get("/exoml")
@app.post("/exoml")
async def exoml_fallback(request: Request):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak language="en-IN">Namaste. Welcome to Rupeek gold loans.</Speak>
    <Pause length="1"/>
    <Speak language="en-IN">We offer instant gold loans up to 75 percent of your gold value.</Speak>
    <Pause length="1"/>
    <Speak language="en-IN">Press 1 for details or hang up to end.</Speak>
    <Gather action="https://ai-calling-somil.onrender.com/collect" inputTimeout="5" finishOnKey="#"/>
</Response>"""
    logger.info("🎤 FALLBACK SPEAK ACTIVE ✅")
    return Response(content=xml, media_type="application/xml")

@app.post("/collect")  # ← NEW & CRITICAL
async def collect_input(request: Request):
    body = await request.body()
    logger.info(f"🔢 DTMF INPUT: {body}")
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak language="en-IN">Thank you. Our team will call you shortly. Goodbye.</Speak>
</Response>"""
    return Response(content=xml, media_type="application/xml")
@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(f"📞 Dial: FROM={request.from_ or EXOTEL_FROM_NUMBER} TO={request.to}")
    
    # ✅ LOG ALL CREDS FOR DEBUG
    logger.info(f"🔑 SID={EXOTEL_SID}, API_KEY={bool(EXOTEL_API_KEY)}, API_TOKEN={bool(EXOTEL_API_TOKEN)}")
    
    url = "https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls.json".format(EXOTEL_SID=EXOTEL_SID)
    payload = {
        "From": request.from_ or EXOTEL_FROM_NUMBER,  # +917999796548 (USER)
        "To": request.to,                             # 08069489493 (EXOTEL)
        "Url": "https://ai-calling-somil.onrender.com/exoml",
        "StatusCallback": "https://ai-calling-somil.onrender.com/status"
    }
    
    # 🔥 EXOTEL AUTH = (SID, API_KEY) - NOT API_TOKEN!
    auth = (EXOTEL_SID, EXOTEL_API_KEY)  
    
    try:
        resp = requests.post(url, auth=auth, data=payload, timeout=10)
        logger.info(f"🔍 DEBUG: Status={resp.status_code}, Response={resp.text[:400]}")
        
        if resp.status_code != 200:
            logger.error(f"❌ EXOTEL ERROR {resp.status_code}: {resp.text}")
            return JSONResponse({"error": f"Exotel {resp.status_code}", "response": resp.text}, status_code=500)
            
        result = resp.json()
        call_sid = result.get("CallSid") or result.get("call", {}).get("CallSid", "UNKNOWN")
        logger.info(f"✅ Dial SUCCESS: CallSid={call_sid}")
        return {"status": "success", "call_sid": call_sid}
        
    except Exception as e:
        logger.error(f"❌ Dial failed: {e}")
        return JSONResponse({"status": "error", "details": str(e)}, status_code=500)
@app.get("/creds")
async def debug_creds():
    return {
        "sid": EXOTEL_SID,
        "api_key_exists": bool(EXOTEL_API_KEY),
        "api_token_exists": bool(EXOTEL_API_TOKEN),
        "from_number": EXOTEL_FROM_NUMBER,
        "correct_auth": "(SID, API_KEY)"
    }


# --- WebSocket (DISABLED for fallback testing) ---
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🔗 WebSocket connected (fallback testing active)")
    await ws.send_json({"event": "clear", "message": "Use /exoml fallback for testing"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
