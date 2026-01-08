print("🚀 STARTING SERVER - HAS DIAL ENDPOINT V1")

import os
import json
import base64
import logging
import asyncio
import tempfile
import wave
import requests
import g711  # Library to convert phone audio (ulaw) to PCM
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME") # e.g. "ai-calling-somil.onrender.com"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
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

# --- 1. Sarvam TTS (Text -> Audio) ---
def generate_sarvam_tts(text: str) -> str:
    """Generates TTS audio from Sarvam and returns Base64 string."""
    if not SARVAM_API_KEY:
        log.error("❌ Sarvam API Key missing")
        return None

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    # Exotel requires 8000Hz. Sarvam handles this via 'speech_sample_rate'.
    payload = {
        "inputs": [text],
        "target_language_code": "en-IN", # or hi-IN
        "speaker": "meera",
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 8000, 
        "enable_preprocessing": True,
        "model": "bulbul:v1"
    }
    try:
        log.info(f"🗣️ Generating TTS: '{text}'")
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if "audios" in data and len(data["audios"]) > 0:
            return data["audios"][0]
    except Exception as e:
        log.error(f"❌ Sarvam TTS Error: {e}")
    return None

# --- 2. Sarvam STT (Audio -> Text) ---
def transcribe_sarvam_stt(audio_bytes: bytes) -> str:
    """
    Saves raw PCM bytes to a WAV file and uploads to Sarvam STT.
    """
    if not SARVAM_API_KEY or not audio_bytes:
        return ""

    tmp_filename = None
    try:
        # Save buffer to a temporary WAV file with correct headers
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_filename = tmp_wav.name
            with wave.open(tmp_filename, "wb") as wf:
                wf.setnchannels(1)       # Mono
                wf.setsampwidth(2)       # 16-bit PCM
                wf.setframerate(8000)    # 8kHz (standard telephony)
                wf.writeframes(audio_bytes)

        # Upload to Sarvam
        url = "https://api.sarvam.ai/speech-to-text"
        headers = {"api-subscription-key": SARVAM_API_KEY}
        
        with open(tmp_filename, "rb") as f:
            files = {'file': ('audio.wav', f, 'audio/wav')}
            data = {"model": "saarika:v1", "language_code": "en-IN"} # use saarika:v2.5 if available
            
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=8)
            
        if resp.status_code == 200:
            transcript = resp.json().get("transcript", "").strip()
            return transcript
        else:
            log.error(f"❌ STT API Failed: {resp.text}")
            return ""

    except Exception as e:
        log.error(f"❌ Sarvam STT Exception: {e}")
        return ""
    finally:
        # Cleanup temp file
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)

# --- Routes ---

@app.get("/")
async def health():
    return {"status": "ok", "service": "sarvam-exotel-voicebot"}

@app.api_route("/exotel/voicebot", methods=["GET", "POST"])
async def exotel_handshake(request: Request):
    """Exotel calls this to get the WebSocket URL."""
    # Dynamically get the host to avoid config errors
    host = request.headers.get("host") or PUBLIC_HOSTNAME
    host = host.replace("http://", "").replace("https://", "").strip("/")
    
    wss_url = f"wss://{host}/ws"
    log.info(f"🤝 Handshake. Returning: {wss_url}")
    return JSONResponse({"url": wss_url})

# --- WebSocket Logic ---

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    log.info("🔌 WS Connected")
    
    # 1. Initial Greeting
    greeting = "Namaste. I am your AI assistant. How can I help you today?"
    audio_b64 = generate_sarvam_tts(greeting)
    
    if audio_b64:
        await ws.send_json({
            "event": "media",
            "media": {
                "payload": audio_b64,
                "content_type": "audio/wav" # Sarvam sends WAV
            }
        })
        log.info("📤 Sent greeting")

    # Audio State
    audio_buffer = bytearray()
    chunk_count = 0
    # Tune this: 50 chunks * 20ms = ~1 second of audio. 
    # Increase to 100-150 for longer listening window (2-3s).
    BUFFER_LIMIT = 80 

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event_type = data.get("event")

            if event_type == "media":
                # 2. Receive Audio from Exotel
                payload_b64 = data['media']['payload']
                mulaw_chunk = base64.b64decode(payload_b64)
                
                # 3. Convert Mu-Law (Phone) -> PCM (AI)
                # Exotel sends Mu-Law. Sarvam STT needs PCM 16-bit.
                pcm_chunk = g711.decode_ulaw(mulaw_chunk)
                
                audio_buffer.extend(pcm_chunk)
                chunk_count += 1
                
                # 4. Naive "Silence/End of Speech" Detection
                # Real systems use WebRTC VAD. Here we just process every X seconds.
                if chunk_count >= BUFFER_LIMIT:
                    log.info("⏳ Processing audio buffer...")
                    
                    # A. Clear Exotel's buffer so user doesn't hear echo/delay
                    await ws.send_json({"event": "clear"})
                    
                    # B. Get Transcript
                    user_text = transcribe_sarvam_stt(bytes(audio_buffer))
                    log.info(f"🎤 User Said: '{user_text}'")
                    
                    if user_text:
                        # C. Simple Brain/Logic
                        response_text = ""
                        ut = user_text.lower()
                        
                        if "loan" in ut or "money" in ut:
                            response_text = "We offer gold loans at great rates. Are you interested?"
                        elif "yes" in ut or "sure" in ut:
                            response_text = "Great! Someone from our team will call you shortly."
                        elif "bye" in ut:
                            response_text = "Goodbye! Have a nice day."
                            
                        # D. Speak Reply
                        if response_text:
                            tts_audio = generate_sarvam_tts(response_text)
                            if tts_audio:
                                await ws.send_json({
                                    "event": "media",
                                    "media": {"payload": tts_audio, "content_type": "audio/wav"}
                                })
                        
                    # Reset buffer for next turn
                    audio_buffer = bytearray()
                    chunk_count = 0

            elif event_type == "stop":
                log.info("🛑 Call Ended by User")
                break

    except WebSocketDisconnect:
        log.info("🔌 WS Disconnected")
    except Exception as e:
        log.error(f"🔥 Critical WS Error: {e}")
