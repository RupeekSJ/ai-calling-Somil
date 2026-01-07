import base64
import json
import logging
import asyncio
import requests
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
# 👇 FIXED: Added JSONResponse import
from fastapi.responses import JSONResponse, Response 
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from dialer import make_outbound_call

# Setup Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("voicebot")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Sarvam Helper Functions (Inline) ---
def generate_sarvam_tts(text: str) -> str:
    """Generates TTS audio from Sarvam and returns Base64 string."""
    if not settings.sarvam_api_key:
        log.warning("Sarvam API Key missing")
        return None

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [text],
        "target_language_code": "hi-IN",
        "speaker": "meera",
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 8000,
        "enable_preprocessing": True,
        "model": "bulbul:v1"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if "audios" in data and len(data["audios"]) > 0:
            return data["audios"][0]
    except Exception as e:
        log.error(f"Sarvam TTS Error: {e}")
    return None

def transcribe_sarvam_stt_mock(audio_buffer: bytes) -> str:
    """
    Mock STT: Real Sarvam STT requires file upload logic.
    For this test, we assume user said 'I want a gold loan'.
    """
    if not settings.sarvam_api_key:
        return ""
    return "I want a gold loan"

# --- Routes ---

# 👇 FIXED: Health check works for Render
@app.api_route("/", methods=["GET", "HEAD"])
async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "rupeek-voicebot"})

@app.api_route("/exotel/voicebot", methods=["GET", "POST"])
async def exotel_voicebot(request: Request):
    """Handshake endpoint for Exotel Voicebot Applet."""
    if request.method == "GET":
        return JSONResponse({"status": "ok"})
    
    # Return WSS URL for the Voicebot Applet
    host = settings.public_hostname.replace("https://", "").replace("http://", "").strip("/")
    wss_url = f"wss://{host}/ws"
    
    return JSONResponse({"url": wss_url})

# 👇 FIXED: Restored the /dial endpoint so your Curl command works
@app.post("/dial")
async def dial(body: Dict[str, Any]):
    """Trigger an outbound call."""
    to_number = body.get("to") or settings.exotel_to_number
    from_number = body.get("from") or settings.exotel_from_number
    exoml_url = body.get("exoml_url") or settings.exotel_exoml_url

    try:
        result = make_outbound_call(
            to_number=to_number,
            from_number=from_number,
            exoml_url=exoml_url,
        )
        return {"ok": True, "exotel": result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# --- WebSocket ---

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    log.info("🔌 WS Connected")
    
    # 1. Greet the user immediately
    greeting_text = "Namaste. This is your Rupeek assistant. How can I help you?"
    audio_b64 = generate_sarvam_tts(greeting_text)
    
    if audio_b64:
        await ws.send_json({
            "event": "media",
            "media": {
                "payload": audio_b64,
                "content_type": "audio/wav"
            }
        })
        log.info("Sent greeting audio")

    # Audio Buffer vars
    audio_buffer = bytearray()
    chunk_count = 0
    MAX_CHUNKS = 50 # Simulate VAD

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event_type = data.get("event")

            if event_type == "media":
                # Collect audio
                chunk = base64.b64decode(data['media']['payload'])
                audio_buffer.extend(chunk)
                chunk_count += 1
                
                # Simulate "Silence Detection" after N chunks
                if chunk_count >= MAX_CHUNKS:
                    log.info("Simulating End-of-Speech...")
                    
                    # 1. STT
                    user_text = transcribe_sarvam_stt_mock(bytes(audio_buffer))
                    log.info(f"User said: {user_text}")
                    
                    if user_text:
                        # 2. Simple Reply (Logic)
                        bot_reply = f"I heard you say: {user_text}. Let me check the rates."
                        
                        # 3. TTS
                        resp_audio = generate_sarvam_tts(bot_reply)
                        if resp_audio:
                            await ws.send_json({
                                "event": "media",
                                "media": {"payload": resp_audio, "content_type": "audio/wav"}
                            })
                    
                    # Reset buffer
                    audio_buffer = bytearray()
                    chunk_count = 0 

            elif event_type == "stop":
                log.info("Call Ended")
                break

    except WebSocketDisconnect:
        log.info("WS Disconnected")
    except Exception as e:
        log.error(f"WS Error: {e}")
