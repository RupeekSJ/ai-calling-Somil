import base64
import json
import logging
import asyncio
import requests
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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

# --- Sarvam TTS Helper ---
def generate_sarvam_tts(text: str) -> str:
    """Generates TTS audio from Sarvam and returns Base64 string."""
    if not settings.sarvam_api_key:
        log.warning("SARVAM_API_KEY missing, skipping TTS.")
        return None

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json"
    }
    # Sarvam Payload: Adjust 'speech_sample_rate' to 8000 for Exotel if needed
    payload = {
        "inputs": [text],
        "target_language_code": "hi-IN", # Hindi (or en-IN)
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

# --- Routes ---

@app.get("/")
async def health():
    return {"status": "ok", "service": "rupeek-voicebot"}

@app.api_route("/exotel/voicebot", methods=["GET", "POST"])
async def exotel_voicebot(request: Request):
    """Handshake endpoint for Exotel Voicebot."""
    if request.method == "GET":
        return JSONResponse({"status": "ok"})

    # Exotel requires us to return the WebSocket URL
    # Clean the hostname (remove http/https)
    host = settings.public_hostname.replace("https://", "").replace("http://", "").strip("/")
    wss_url = f"wss://{host}/ws"
    
    log.info(f"Handshake received. Returning WSS URL: {wss_url}")
    return JSONResponse({"url": wss_url})

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

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    """WebSocket handler for real-time audio stream."""
    await ws.accept()
    log.info("🔌 WS Connected to Exotel")

    # 1. Greet the user immediately
    greeting_text = "Namaste. Welcome to Rupeek. How can I assist you?"
    audio_b64 = generate_sarvam_tts(greeting_text)
    
    if audio_b64:
        # Exotel format: {"event": "media", "media": {"payload": "base64", "content_type": "audio/wav"}}
        # Note: Check if Sarvam sends WAV or PCM. Exotel often handles WAV header automatically.
        await ws.send_json({
            "event": "media",
            "media": {
                "payload": audio_b64,
                "content_type": "audio/wav"
            }
        })
        log.info("Sent greeting audio")

    # 2. Listen loop
    try:
        while True:
            msg_text = await ws.receive_text()
            data = json.loads(msg_text)
            event_type = data.get("event")

            if event_type == "media":
                # User audio (base64)
                # payload = data['media']['payload']
                # TODO: Accumulate this payload and send to STT when silence is detected
                pass
            
            elif event_type == "stop":
                log.info("Call stopped by user/Exotel")
                break
                
    except WebSocketDisconnect:
        log.info("WS Disconnected")
    except Exception as e:
        log.error(f"WS Error: {e}")
