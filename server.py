# ==================================================
# server.py — Exotel + Sarvam Voicebot
# Python 3.13 compatible (NO audioop)
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
SPEECH_THRESHOLD = 500  # tune if needed

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
stt_logger = logging.getLogger("sarvam-stt")

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup():
    logger.info("✅ FastAPI started")

@app.get("/")
async def health():
    return {"status": "ok"}

# --------------------------------------------------
# OPENING PITCH
# --------------------------------------------------
OPENING_PITCH = (
    "Hello, this is Rupeek personal loan assistant. "
    "I am calling regarding your pre approved loan offer. "
    "You may ask about interest rate, repayment, or loan limit."
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
     "Please check the Rupeek app."),
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
# PURE PYTHON SILENCE DETECTION (NO audioop)
# --------------------------------------------------
def is_speech(pcm: bytes) -> bool:
    if not pcm:
        return False

    # PCM16 LE → int samples
    total = 0
    count = 0

    for i in range(0, len(pcm) - 1, 2):
        sample = int.from_bytes(
            pcm[i:i+2], byteorder="little", signed=True
        )
        total += abs(sample)
        count += 1

    if count == 0:
        return False

    avg_amplitude = total / count
    logger.debug(f"🔈 Avg amplitude={avg_amplitude}")

    return avg_amplitude > SPEECH_THRESHOLD

# --------------------------------------------------
# SARVAM STT (PCM → TEXT)
# --------------------------------------------------
def sarvam_stt_from_pcm(pcm: bytes) -> str:
    stt_logger.info("🎙 Sending audio to Sarvam STT")

    resp = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "audio": base64.b64encode(pcm).decode(),
            "language_code": "en-IN",
            "sample_rate": SAMPLE_RATE
        },
        timeout=20
    )

    stt_logger.info(f"📡 STT status={resp.status_code}")
    resp.raise_for_status()

    text = resp.json().get("text", "").strip()
    stt_logger.info(f"📝 Transcription: {text}")

    return text

# --------------------------------------------------
# SARVAM TTS (TEXT → PCM)
# --------------------------------------------------
def sarvam_tts_to_pcm(text: str) -> bytes:
    resp = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "text": text,
            "target_language_code": "en-IN",
            "speech_sample_rate": "16000"
        },
        timeout=15
    )

    tts_logger.info(f"🔊 TTS status={resp.status_code}")
    resp.raise_for_status()

    return base64.b64decode(resp.json()["audios"][0])

# --------------------------------------------------
# SEND AUDIO TO EXOTEL (JSON MEDIA)
# --------------------------------------------------
async def send_pcm(ws: WebSocket, pcm: bytes):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {
                "payload": base64.b64encode(
                    pcm[i:i + MIN_CHUNK_SIZE]
                ).decode()
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
    awaiting_user = False

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
                awaiting_user = True
                buffer = b""
                continue

            # ---- LISTEN TO USER ----
            if event != "media" or not awaiting_user:
                continue

            payload = data.get("media", {}).get("payload")
            if not payload:
                continue

            buffer += base64.b64decode(payload)

            # wait ~1s of audio
            if len(buffer) < SAMPLE_RATE * BYTES_PER_SAMPLE:
                continue

            # silence check
            if not is_speech(buffer):
                buffer = b""
                continue

            logger.info("🗣 User speech detected")
            awaiting_user = False

            # ---- REAL STT ----
            user_text = await asyncio.to_thread(
                sarvam_stt_from_pcm, buffer
            )
            buffer = b""

            if not user_text:
                awaiting_user = True
                continue

            reply = get_reply(user_text)
            logger.info(f"🤖 Reply: {reply}")

            pcm_reply = await asyncio.to_thread(
                sarvam_tts_to_pcm, reply
            )
            await send_pcm(ws, pcm_reply)

            awaiting_user = True

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

    except Exception:
        logger.error("❌ WebSocket error", exc_info=True)

# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="debug",
        access_log=True
    )
