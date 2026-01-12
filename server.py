import os
import json
import asyncio
import logging
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv()

# --------------------
# CONFIG
# --------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

SARVAM_TTS_URL = "https://api.sarvam.ai/v1/text-to-speech"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("voicebot")

app = FastAPI()

# --------------------
# UTIL: Sarvam TTS → PCM
# --------------------
def sarvam_tts(text: str) -> bytes:
    """
    Generate 16-bit PCM, 8kHz mono audio for Exotel
    """
    payload = {
        "text": text,
        "voice": "meera",
        "sample_rate": 8000,
        "audio_format": "pcm"
    }

    headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        SARVAM_TTS_URL,
        json=payload,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()
    return response.content  # RAW PCM bytes

# --------------------
# HEALTH
# --------------------
@app.get("/")
def health():
    return {"status": "ok"}

# --------------------
# WEBSOCKET FOR EXOTEL
# --------------------
@app.websocket("/ws")
async def exotel_ws(ws: WebSocket):
    await ws.accept()
    logger.info("📞 Exotel WebSocket connected")

    greeted = False

    try:
        while True:
            message = await ws.receive()

            # ---- TEXT CONTROL FRAMES ----
            if "text" in message:
                data = message["text"]
                logger.debug(f"📩 Control frame: {data}")

                # First time Exotel connects → speak greeting
                if not greeted:
                    greeted = True
                    greeting = (
                        "Hello. This is Rup eek Finance virtual assistant. "
                        "How can I help you today?"
                    )

                    audio = sarvam_tts(greeting)

                    # Send audio in chunks (VERY IMPORTANT)
                    chunk_size = 320  # 20ms @ 8kHz PCM
                    for i in range(0, len(audio), chunk_size):
                        await ws.send_bytes(audio[i:i+chunk_size])
                        await asyncio.sleep(0.02)

            # ---- AUDIO FROM USER (IGNORE FOR NOW) ----
            elif "bytes" in message:
                # User audio received (we're not processing it yet)
                pass

    except WebSocketDisconnect:
        logger.info("📴 Call disconnected")

    except Exception as e:
        logger.error(f"❌ WS error: {e}")
        await ws.close()
