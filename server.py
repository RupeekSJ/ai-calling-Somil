# ==================================================
# SERVER.PY — EXOTEL VOICEBOT
# FLOW: BOT PITCH → USER SPEAKS → BOT RESPONDS
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
# LOAD ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
MIN_CHUNK_SIZE = 3200  # 100ms @ 16kHz PCM16

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
# FASTAPI APP
# --------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    logger.info("✅ FastAPI startup completed — Render logs OK")

@app.get("/")
async def health():
    return {"status": "ok"}

# --------------------------------------------------
# OPENING PITCH (FIRST AUDIO)
# --------------------------------------------------
OPENING_PITCH = (
    "Hello, this is Rupeek personal loan assistant. "
    "I am calling to help you with your pre approved loan offer. "
    "You may ask about interest rate, repayment, or your loan limit."
)

# --------------------------------------------------
# FAQ KNOWLEDGE BASE
# --------------------------------------------------
FAQS = [
    {
        "keywords": ["interest", "rate"],
        "answer": (
            "The interest rate starts from ten percent per annum "
            "and is personalized for each customer."
        )
    },
    {
        "keywords": ["limit", "pre approved"],
        "answer": (
            "Your pre approved limit is already sanctioned. "
            "Please check the Rupeek app for the exact amount."
        )
    },
    {
        "keywords": ["emi", "repay"],
        "answer": (
            "Your EMI will be auto deducted from your linked bank account "
            "on the fifth of every month."
        )
    }
]

DEFAULT_REPLY = (
    "I can help you with interest rate, loan limit, or repayment. "
    "Please tell me your question."
)

# --------------------------------------------------
# INTENT MATCHER
# --------------------------------------------------
def get_faq_reply(text: str) -> str:
    text = text.lower()
    for faq in FAQS:
        if any(k in text for k in faq["keywords"]):
            return faq["answer"]
    return DEFAULT_REPLY

# --------------------------------------------------
# SARVAM TTS → PCM16 (YOUR PAYLOAD)
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
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    tts_logger.info(f"📡 TTS status={resp.status_code}")

    resp.raise_for_status()

    audio_b64 = resp.json()["audios"][0]
    pcm = base64.b64decode(audio_b64)

    tts_logger.info(f"🎧 PCM bytes={len(pcm)}")
    return pcm

# --------------------------------------------------
# STREAM PCM TO EXOTEL
# --------------------------------------------------
async def stream_pcm(ws: WebSocket, pcm: bytes):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        await ws.send_bytes(pcm[i:i + MIN_CHUNK_SIZE])
        await asyncio.sleep(0)  # yield control

# --------------------------------------------------
# WEBSOCKET ENDPOINT (EXOTEL)
# --------------------------------------------------
@app.websocket("/ws")
async def voicebot_ws(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel connected")

    buffer = b""
    pitch_played = False

    try:
        while True:
            message = await ws.receive()

            # Exotel sends JSON frames
            if "text" not in message:
                continue

            data = json.loads(message["text"])
            event = data.get("event")

            # -------------------------------
            # CALL START → PLAY OPENING PITCH
            # -------------------------------
            if event == "start" and not pitch_played:
                logger.info("📞 Call started — playing opening pitch")

                pcm = await asyncio.to_thread(
                    sarvam_tts_to_pcm, OPENING_PITCH
                )
                await stream_pcm(ws, pcm)

                pitch_played = True
                buffer = b""  # clear buffer before listening
                continue

            # -------------------------------
            # AFTER PITCH → LISTEN TO USER
            # -------------------------------
            if event != "media" or not pitch_played:
                continue

            payload_b64 = data["media"].get("payload")
            if not payload_b64:
                continue

            audio_bytes = base64.b64decode(payload_b64)
            buffer += audio_bytes

            if len(buffer) < MIN_CHUNK_SIZE:
                continue

            buffer = buffer[MIN_CHUNK_SIZE:]

            # 🔴 TEMP STT PLACEHOLDER
            user_text = "interest rate"
            logger.info(f"🗣 User said: {user_text}")

            reply = get_faq_reply(user_text)
            logger.info(f"🤖 Replying: {reply}")

            pcm_reply = await asyncio.to_thread(
                sarvam_tts_to_pcm, reply
            )
            await stream_pcm(ws, pcm_reply)

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

    except Exception:
        logger.error("❌ Fatal WS error", exc_info=True)

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
