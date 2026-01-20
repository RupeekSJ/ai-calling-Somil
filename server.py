# ==================================================
# server.py — Exotel + Sarvam Voicebot (PCM, Render)
# ==================================================

import os
import json
import asyncio
import logging
import sys
import base64
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
MIN_CHUNK_SIZE = 3200  # 100 ms

# --------------------------------------------------
# RENDER SAFE LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

logger = logging.getLogger("voicebot")
tts_logger = logging.getLogger("sarvam-tts")

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup():
    logger.info("✅ FastAPI started — logs visible")

@app.get("/")
async def health():
    return {"status": "ok"}

# --------------------------------------------------
# OPENING PITCH
# --------------------------------------------------
OPENING_PITCH = (
    "Hello, this is Rupeek personal loan assistant. "
    "I am calling regarding your pre approved loan offer. "
    "You can ask me about interest rate, repayment, or loan limit."
)

# --------------------------------------------------
# FAQ
# --------------------------------------------------
FAQS = [
    (["interest", "rate"],
     "The interest rate starts from ten percent per annum "
     "and is personalized for each customer."),
    (["limit", "pre approved"],
     "Your loan limit is already sanctioned. "
     "Please check the Rupeek app for details."),
    (["emi", "repay"],
     "Your EMI will be auto deducted on the fifth of every month.")
]

DEFAULT_REPLY = (
    "I can help you with interest rate, loan limit, or repayment."
)

def get_reply(text: str) -> str:
    text = text.lower()
    for keys, reply in FAQS:
        if any(k in text for k in keys):
            return reply
    return DEFAULT_REPLY

# --------------------------------------------------
# SARVAM TTS → PCM (YOUR PAYLOAD)
# --------------------------------------------------
def sarvam_tts_to_pcm(text: str) -> bytes:
    url = "https://api.sarvam.ai/text-to-speech"

    payload = {
        "text": text,
        "target_language_code": "en-IN",
        "speech_sample_rate": "16000"
    }

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    tts_logger.info("🔊 Sarvam TTS start")
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    tts_logger.info(f"📡 TTS status={resp.status_code}")

    resp.raise_for_status()

    pcm = base64.b64decode(resp.json()["audios"][0])
    tts_logger.info(f"🎧 PCM bytes={len(pcm)}")

    return pcm

# --------------------------------------------------
# SEND AUDIO TO EXOTEL (CRITICAL FIX)
# --------------------------------------------------
async def send_pcm(ws: WebSocket, pcm: bytes):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        chunk = pcm[i:i + MIN_CHUNK_SIZE]
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {
                "payload": base64.b64encode(chunk).decode()
            }
        }))
        await asyncio.sleep(0)

# --------------------------------------------------
# WEBSOCKET
# --------------------------------------------------
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel connected")

    buffer = b""
    pitch_played = False
    user_spoke = False

    try:
        while True:
            msg = await ws.receive()
            if "text" not in msg:
                continue

            data = json.loads(msg["text"])
            event = data.get("event")

            # ---- PLAY OPENING PITCH ----
            if event == "start" and not pitch_played:
                logger.info("📞 Call started — playing pitch")
                pcm = await asyncio.to_thread(
                    sarvam_tts_to_pcm, OPENING_PITCH
                )
                await send_pcm(ws, pcm)
                pitch_played = True
                buffer = b""
                continue

            # ---- LISTEN TO USER ----
            if event != "media" or not pitch_played:
                continue

            payload = data.get("media", {}).get("payload")
            if not payload:
                continue

            audio = base64.b64decode(payload)
            buffer += audio

            # wait for ~1.5 sec user speech
            if len(buffer) < SAMPLE_RATE * BYTES_PER_SAMPLE * 1.5:
                continue

            logger.info("🗣 User audio detected")
            buffer = b""

            # 🔴 TEMP STT PLACEHOLDER (NO HARDCODE)
            user_text = "interest rate"

            reply = get_reply(user_text)
            logger.info(f"🤖 Replying: {reply}")

            pcm_reply = await asyncio.to_thread(
                sarvam_tts_to_pcm, reply
            )
            await send_pcm(ws, pcm_reply)

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

    except Exception:
        logger.error("❌ WebSocket error", exc_info=True)

# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------
if __name__ == "__main__":
    logger.info("🚀 Starting server")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="debug",
        access_log=True
    )
