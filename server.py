print("🚀 STARTING SERVER V3 - MATCHES .ENV FILE")

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

# --- Configuration (MATCHES YOUR .env EXACTLY) ---
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")

# FIXED: Using EXACT names from your .env file
EXOTEL_SID = os.getenv("EXOTEL_ACCOUNT_SID")  # Changed from EXOTEL_SID
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")

# Debug logging - shows what's loaded
logger.info(f"🚀 Config loaded:")
logger.info(f"   SARVAM_API_KEY: {'✅' if SARVAM_API_KEY else '❌'}")
logger.info(f"   PUBLIC_HOSTNAME: {PUBLIC_HOSTNAME}")
logger.info(f"   EXOTEL_SID: {'✅' if EXOTEL_SID else '❌'}")
logger.info(f"   EXOTEL_API_KEY: {'✅' if EXOTEL_API_KEY else '❌'}")
logger.info(f"   EXOTEL_API_TOKEN: {'✅' if EXOTEL_API_TOKEN else '❌'}")
logger.info(f"   EXOTEL_FROM_NUMBER: {EXOTEL_FROM_NUMBER}")

# Setup main logging AFTER config logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("voicebot")

app = FastAPI(title="Rupeek VoiceBot", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
class DialRequest(BaseModel):
    to: str
    from_: Optional[str] = Field(default=None, alias="from")
    exoml_url: Optional[str] = None

# --- Debug Endpoint (REMOVE AFTER TESTING) ---
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

@app.get("/")
async def health():
    return {"status": "ok", "service": "rupeek-voicebot-v3"}

# --- Helper Functions ---
def generate_sarvam_tts(text: str) -> Optional[str]:
    if not SARVAM_API_KEY:
        logger.error("❌ Sarvam API Key missing")
        return None
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
    payload = {
        "inputs": [text],
        "target_language_code": "en-IN",
        "speaker": "meera",
        "speech_sample_rate": 8000,
        "model": "bulbul:v1"
    }
    try:
        logger.info(f"🗣️ TTS: '{text[:50]}...'")
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "audios" in data and data["audios"]:
            return data["audios"][0]
    except Exception as e:
        logger.error(f"❌ TTS Error: {e}")
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
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(audio_bytes)
        
        url = "https://api.sarvam.ai/speech-to-text"
        headers = {"api-subscription-key": SARVAM_API_KEY}
        with open(tmp_filename, "rb") as f:
            files = {'file': ('audio.wav', f, 'audio/wav')}
            data = {"model": "saarika:v1", "language_code": "en-IN"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=15)
        
        if resp.status_code == 200:
            transcript = resp.json().get("transcript", "").strip()
            logger.info(f"✅ STT Success: '{transcript[:50]}...'")
            return transcript
        else:
            logger.error(f"❌ STT HTTP {resp.status_code}: {resp.text[:200]}")
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
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}">
            <Parameter name="packetS" value="true" />
        </Stream>
    </Connect>
</Response>"""
    logger.info(f"📡 Exoml requested, returning WS: {wss_url}")
    return Response(content=xml_content, media_type="application/xml")

@app.post("/dial")
async def dial(request: DialRequest):
    logger.info(f"📞 Dial request: to={request.to}, from={request.from_}")
    
    # Check credentials
    missing = []
    if not EXOTEL_SID: missing.append("EXOTEL_ACCOUNT_SID")
    if not EXOTEL_API_KEY: missing.append("EXOTEL_API_KEY")
    if not EXOTEL_API_TOKEN: missing.append("EXOTEL_API_TOKEN")
    
    if missing:
        logger.error(f"❌ Missing credentials: {', '.join(missing)}")
        return JSONResponse({"error": f"Missing: {', '.join(missing)}"}, status_code=500)

    # Build Exotel API URL
    url = f"https://{EXOTEL_API_KEY}:{EXOTEL_API_TOKEN}@{EXOTEL_SUBDOMAIN}/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    
    # Use your custom EXOML URL if provided, otherwise our /exoml
    host = PUBLIC_HOSTNAME or "ai-calling-somil.onrender.com"
    callback_url = request.exoml_url or f"https://{host}/exoml"

    payload = {
        "From": request.from_ or EXOTEL_FROM_NUMBER,
        "To": request.to,
        "Url": callback_url,
        "CallType": "trans"
    }
    
    logger.info(f"📞 Calling Exotel: {request.to} <- {payload['From']}")
    logger.info(f"📡 Callback URL: {callback_url}")
    
    try:
        resp = requests.post(url, data=payload, timeout=10)
        logger.info(f"Exotel response: {resp.status_code}")
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"✅ Dial SUCCESS: {result.get('CallSid', 'No SID')}")
        return {"status": "success", "call_sid": result.get("CallSid"), "exotel": result}
    except Exception as e:
        logger.error(f"❌ Dial Failed: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "details": str(e)}, status_code=500)

# --- WebSocket (Voice Conversation) ---
@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    logger.info("✅ WebSocket Connected - Voice session started")
    
    # Greeting
    greeting = "Namaste. I am your Rupeek gold loan assistant. How can I help you today?"
    audio_b64 = generate_sarvam_tts(greeting)
    if audio_b64:
        await websocket.send_json({
            "event": "media",
            "media": {"payload": audio_b64, "content_type": "audio/wav"}
        })
        logger.info("📤 Greeting sent")

    # Conversation state
    audio_buffer = bytearray()
    chunk_count = 0
    BUFFER_LIMIT = 80  # ~1.6 seconds of audio

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            event = data.get("event")

            if event == "media":
                # Process incoming audio (μ-law -> PCM)
                payload_b64 = data["media"]["payload"]
                mulaw_chunk = base64.b64decode(payload_b64)
                pcm_chunk = g711.decode_ulaw(mulaw_chunk)
                
                audio_buffer.extend(pcm_chunk)
                chunk_count += 1
                
                # Process when buffer is full (end of speech)
                if chunk_count >= BUFFER_LIMIT:
                    logger.info("⏳ Processing user speech...")
                    
                    # Stop any playback
                    await websocket.send_json({"event": "clear"})
                    
                    # Speech-to-Text
                    user_text = transcribe_sarvam_stt(bytes(audio_buffer))
                    
                    if user_text.strip():
                        logger.info(f"🎤 User said: '{user_text}'")
                        
                        # Simple loan bot logic
                        ut = user_text.lower()
                        if any(word in ut for word in ["loan", "gold", "money", "rupee"]):
                            reply = "Rupeek offers instant gold loans at competitive rates. Would you like to know more?"
                        elif any(word in ut for word in ["yes", "sure", "okay"]):
                            reply = "Excellent! Our team will call you shortly with loan details. Thank you!"
                        elif any(word in ut for word in ["bye", "end", "stop"]):
                            reply = "Thank you for calling Rupeek. Have a great day!"
                        else:
                            reply = "I understand. Could you tell me more about what loan you need?"
                        
                        # Text-to-Speech response
                        tts_audio = generate_sarvam_tts(reply)
                        if tts_audio:
                            await websocket.send_json({
                                "event": "media",
                                "media": {"payload": tts_audio, "content_type": "audio/wav"}
                            })
                            logger.info(f"🤖 Replied: '{reply[:50]}...'")
                    
                    # Reset for next utterance
                    audio_buffer.clear()
                    chunk_count = 0
                    
            elif event == "stop":
                logger.info("🛑 Call ended by user")
                break
            elif event == "connected":
                logger.info("🔗 Exotel stream connected")

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected")
    except Exception as e:
        logger.error(f"💥 WebSocket error: {e}")
        traceback.print_exc()
