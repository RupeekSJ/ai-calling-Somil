print("🚀 STARTING SERVER - HAS DIAL ENDPOINT V2 (FINAL)")

import os
import json
import base64
import logging
import tempfile
import wave
import requests
import g711  # pip install g711
from typing import Optional
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")

# Exotel Credentials
EXOTEL_SID = os.getenv("EXOTEL_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("voicebot")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
class DialRequest(BaseModel):
    to: str
    from_: Optional[str] = None
    exoml_url: Optional[str] = None
    class Config:
        fields = {'from_': 'from'}

# --- Helper Functions ---
def generate_sarvam_tts(text: str) -> str:
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
        logger.info(f"🗣️ TTS: '{text}'")
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if "audios" in data and len(data["audios"]) > 0:
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
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=8)
        if resp.status_code == 200:
            return resp.json().get("transcript", "").strip()
        else:
            logger.error(f"❌ STT Error: {resp.text}")
            return ""
    except Exception as e:
        logger.error(f"❌ STT Exception: {e}")
        return ""
    finally:
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)

# --- Routes ---

@app.get("/")
async def health():
    return {"status": "ok", "service": "sarvam-exotel-voicebot-v3-dial"}

@app.get("/exoml")
@app.post("/exoml")
async def get_exoml(request: Request):
    """Instructions for Exotel to connect to WebSocket"""
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
    return Response(content=xml_content, media_type="application/xml")

@app.post("/dial")
async def dial(request: DialRequest):
    """Triggers outbound call"""
    if not (EXOTEL_SID and EXOTEL_API_KEY and EXOTEL_API_TOKEN):
        return JSONResponse({"error": "Exotel credentials missing"}, status_code=500)

    url = f"https://{EXOTEL_API_KEY}:{EXOTEL_API_TOKEN}@{EXOTEL_SUBDOMAIN}/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    
    # Construct callback URL (Where Exotel asks 'what do I do?')
    host = PUBLIC_HOSTNAME or "ai-calling-somil.onrender.com"
    if not host.startswith("http"):
        host = f"https://{host}"
    
    # We point Exotel to our /exoml endpoint, which tells it to open the WebSocket
    callback_url = request.exoml_url or f"{host}/exoml"

    payload = {
        "From": request.from_ or EXOTEL_FROM_NUMBER,
        "To": request.to,
        "Url": callback_url,
        "CallType": "trans"
    }
    
    logger.info(f"📞 Dialing {request.to} -> Callback: {callback_url}")
    try:
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
        return {"status": "success", "exotel": resp.json()}
    except Exception as e:
        logger.error(f"Dial Failed: {e}")
        return JSONResponse({"status": "error", "details": str(e)}, status_code=500)

# --- WebSocket ---

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("✅ WS Connected")
    
    greeting = "Namaste. I am your Rupeek assistant. How can I help you today?"
    audio_b64 = generate_sarvam_tts(greeting)
    if audio_b64:
        await ws.send_json({"event": "media", "media": {"payload": audio_b64, "content_type": "audio/wav"}})

    audio_buffer = bytearray()
    chunk_count = 0
    BUFFER_LIMIT = 80 

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event_type = data.get("event")

            if event_type == "media":
                payload = base64.b64decode(data['media']['payload'])
                pcm_chunk = g711.decode_ulaw(payload)
                audio_buffer.extend(pcm_chunk)
                chunk_count += 1
                
                if chunk_count >= BUFFER_LIMIT:
                    logger.info("⏳ Processing Speech...")
                    await ws.send_json({"event": "clear"}) 
                    user_text = transcribe_sarvam_stt(bytes(audio_buffer))
                    logger.info(f"🎤 User: {user_text}")
                    if user_text:
                        # Simple Logic
                        reply = "I heard you."
                        if "loan" in user_text.lower(): reply = "We offer gold loans."
                        
                        tts_audio = generate_sarvam_tts(reply)
                        if tts_audio:
                            await ws.send_json({"event": "media", "media": {"payload": tts_audio, "content_type": "audio/wav"}})
                    
                    audio_buffer = bytearray()
                    chunk_count = 0
            elif event_type == "stop":
                break
    except WebSocketDisconnect:
        logger.info("🔌 WS Disconnected")
