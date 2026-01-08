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
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")

logger.info("🚀 Config loaded:")
logger.info(f"   SARVAM_API_KEY: {'✅' if SARVAM_API_KEY else '❌'}")
logger.info(f"   PUBLIC_HOSTNAME: {PUBLIC_HOSTNAME}")
logger.info(f"   EXOTEL_SID: {'✅' if EXOTEL_SID else '❌'}")
logger.info(f"   EXOTEL_FROM_NUMBER: {EXOTEL_FROM_NUMBER}")

app = FastAPI(title="Rupeek VoiceBot", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class DialRequest(BaseModel):
    to: str
    from_: Optional[str] = Field(default=None, alias="from")
    exoml_url: Optional[str] = None

# 🚀 NEW DEBUG ENDPOINTS
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

@app.get("/ws-health")
async def ws_health():
    """Test WebSocket readiness"""
    return {
        "status": "ready", 
        "websocket": f"wss://{PUBLIC_HOSTNAME or 'ai-calling-somil.onrender.com'}/ws",
        "timestamp": "ready"
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
    return {"status": "ok", "service": "rupeek-voicebot-v4-audiofix"}

# --- Helper Functions (IMPROVED) ---
def generate_sarvam_tts(text: str) -> Optional[str]:
    if not SARVAM_API_KEY:
        logger.error("❌ Sarvam API Key missing")
        return None
    
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": SARVAM_API_KEY, 
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [text],
        "target_language_code": "en-IN",
        "speaker": "meera",
        "speech_sample_rate": 8000,  # CRITICAL for Exotel
        "model": "bulbul:v1"
    }
    
    try:
        logger.info(f"🗣️ TTS Request: '{text[:30]}...'")
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        logger.info(f"🗣️ TTS Response: {resp.status_code}")
        
        if resp.status_code != 200:
            logger.error(f"❌ TTS HTTP {resp.status_code}: {resp.text[:200]}")
            return None
            
        data = resp.json()
        if "audios" in data and data["audios"]:
            audio_b64 = data["audios"][0]
            logger.info(f"✅ TTS Success: {len(audio_b64)} bytes")
            return audio_b64
        else:
            logger.error(f"❌ TTS No audio in response: {data}")
            return None
            
    except Exception as e:
        logger.error(f"❌ TTS Exception: {e}")
        return None

def transcribe_sarvam_stt(audio_bytes: bytes) -> str:
    if not SARVAM_API_KEY or not audio_bytes:
        return ""
    
    tmp_filename = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_filename = tmp_wav.name
            with wave.open(tmp_filename, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit PCM
                wf.setframerate(8000)
                wf.writeframes(audio_bytes)

        url = "https://api.sarvam.ai/speech-to-text"
        headers = {"api-subscription-key": SARVAM_API_KEY}
        with open(tmp_filename, "rb") as f:
            files = {'file': ('audio.wav', f, 'audio/wav')}
            data = {"model": "saarika:v1", "language_code": "en-IN"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=15)
            
        if resp.status_code == 200:
            return resp.json().get("transcript", "").strip()
        else:
            logger.error(f"❌ STT HTTP {resp.status_code}: {resp.text[:100]}")
            return ""
    except Exception as e:
        logger.error(f"❌ STT Exception: {e}")
        return ""
    finally:
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)

# --- Exotel Routes ---
@app.get("/exoml")
@app.post("/exoml")
async def get_exoml(request: Request):
    host = request.headers.get("host") or PUBLIC_HOSTNAME
    host = host.replace("http://", "").replace("https://", "").strip("/")
    wss_url = f"wss://{host}/ws"
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}">
            <Parameter name="packetS" value="true" />
        </Stream>
    </Connect>
</Response>"""
    logger.info(f"📡 EXOML Returning: {wss_url}")
    return Response(content=xml, media_type="application/xml")

@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(f"📞 Dial: {request.to} from {request.from_ or EXOTEL_FROM_NUMBER}")
    
    missing = []
    if not EXOTEL_SID: missing.append("EXOTEL_ACCOUNT_SID")
    if not EXOTEL_API_KEY: missing.append("EXOTEL_API_KEY")
    if not EXOTEL_API_TOKEN: missing.append("EXOTEL_API_TOKEN")
    
    if missing:
        logger.error(f"❌ Missing: {missing}")
        return JSONResponse({"error": f"Missing: {', '.join(missing)}"}, status_code=500)

    url = f"https://{EXOTEL_API_KEY}:{EXOTEL_API_TOKEN}@{EXOTEL_SUBDOMAIN}/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    callback_url = request.exoml_url or f"https://{PUBLIC_HOSTNAME or 'ai-calling-somil.onrender.com'}/exoml"
    
    payload = {
        "From": request.from_ or EXOTEL_FROM_NUMBER,
        "To": request.to,
        "Url": callback_url,
        "CallType": "trans"
    }
    
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"✅ Dial SUCCESS: CallSid={result.get('CallSid')}")
        return {"status": "success", "call_sid": result.get("CallSid")}
    except Exception as e:
        logger.error(f"❌ Dial failed: {e}")
        return JSONResponse({"status": "error", "details": str(e)}, status_code=500)

# --- WebSocket (ENHANCED with better error handling) ---
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("✅ WebSocket CONNECTED - Exotel stream active!")
    
    # 🎤 IMMEDIATE GREETING (Critical for audio test)
    logger.info("🎤 Sending greeting...")
    greeting_audio = generate_sarvam_tts("Namaste. Welcome to Rupeek. How can I help you?")
    
    if greeting_audio:
        await ws.send_json({
            "event": "media",
            "media": {
                "payload": greeting_audio,
                "content_type": "audio/wav",
                "sample_rate": 8000  # Explicit for Exotel
            }
        })
        logger.info("✅ Greeting SENT - Check if you hear it!")
    else:
        logger.error("❌ Greeting FAILED - Sarvam TTS issue!")
        # Send fallback silence message
        await ws.send_json({"event": "clear"})

    # Conversation loop
    audio_buffer = bytearray()
    chunk_count = 0
    BUFFER_LIMIT = 100  # Increased for better speech detection

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event = data.get("event")
            
            logger.info(f"📨 WS Event: {event}")

            if event == "media":
                # User speaking - buffer audio
                payload_b64 = data["media"]["payload"]
                mulaw_chunk = base64.b64decode(payload_b64)
                pcm_chunk = g711.decode_ulaw(mulaw_chunk)
                
                audio_buffer.extend(pcm_chunk)
                chunk_count += 1
                
                if chunk_count >= BUFFER_LIMIT:
                    logger.info("⏳ Processing user speech...")
                    await ws.send_json({"event": "clear"})
                    
                    user_text = transcribe_sarvam_stt(bytes(audio_buffer))
                    logger.info(f"🎤 User said: '{user_text}'")
                    
                    # Bot response
                    if user_text and "loan" in user_text.lower():
                        reply = generate_sarvam_tts("Great. Rupeek offers instant gold loans.")
                    elif user_text:
                        reply = generate_sarvam_tts("I understand. Tell me more.")
                    else:
                        reply = generate_sarvam_tts("Sorry, I did not hear clearly.")
                    
                    if reply:
                        await ws.send_json({
                            "event": "media",
                            "media": {
                                "payload": reply,
                                "content_type": "audio/wav",
                                "sample_rate": 8000
                            }
                        })
                        logger.info("✅ Bot replied!")
                    
                    audio_buffer.clear()
                    chunk_count = 0
                    
            elif event == "stop":
                logger.info("🛑 Call ended by Exotel")
                break
            elif event == "connected":
                logger.info("🔗 Exotel stream connected")
                
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"💥 WebSocket ERROR: {e}")
        traceback.print_exc()
