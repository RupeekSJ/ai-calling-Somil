print("🚀 STARTING SERVER V6.1 - EXOTEL VOICEBOT (RENDER SAFE)")

import os
import json
import asyncio
import logging
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
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("voicebot")

# --------------------------------------------------
# FASTAPI APP
# --------------------------------------------------
app = FastAPI()

@app.get("/")
@app.head("/")
async def health():
    return {"status": "ok", "service": "exotel-voicebot"}

# --------------------------------------------------
# FAQ KNOWLEDGE BASE
# --------------------------------------------------
FAQS = [
    {
        "keywords": ["interest", "rate"],
        "answer": (
            "The interest rate starts from ten percent per annum "
            "and is personalized for each customer. "
            "You can check your exact rate in the Rupeek app."
        )
    },
    {
        "keywords": ["pre approved", "limit"],
        "answer": (
            "A pre approved limit means you already have a sanctioned "
            "loan offer with no documents required. "
            "Please open the Rupeek app to see your exact limit."
        )
    },
    {
        "keywords": ["gold", "collateral"],
        "answer": (
            "This is a personal loan without gold or any collateral. "
            "The loan is completely unsecured."
        )
    },
    {
        "keywords": ["repay", "emi"],
        "answer": (
            "Your EMI will be auto deducted from your linked bank account "
            "on the fifth of every month. "
            "You can also repay using the Pay Now option in the Rupeek app."
        )
    },
]

DEFAULT_REPLY = (
    "I can help you with loan details like interest rate, "
    "pre approved limit, repayment process, or tenure. "
    "Please ask your question."
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
# SARVAM TTS → RAW PCM16
# --------------------------------------------------
def sarvam_tts_to_pcm(text: str) -> bytes:
    url = "https://api.sarvam.ai/text-to-speech"

    payload = {
        "text": text,
        "target_language_code": "en-IN",
        "speaker": "anushka",
        "model": "bulbul:v2",
        "output_audio_codec": "wav"
    }

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()

    audio_b64 = resp.json()["audios"][0]
    wav_bytes = base64.b64decode(audio_b64)

    # Strip WAV header (44 bytes) → RAW PCM16
    return wav_bytes[44:]

# --------------------------------------------------
# WEBSOCKET ENDPOINT (EXOTEL)
# --------------------------------------------------
@app.websocket("/ws")
async def voicebot_ws(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel Voicebot connected")

    buffer = b""

    try:
        while True:
            message = await ws.receive()

            # Exotel sends JSON TEXT frames
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("⚠️ Invalid JSON received")
                    continue

                event = data.get("event")

                # Ignore non-media events (start, stop, mark)
                if event != "media":
                    logger.info(f"ℹ️ Exotel event: {event}")
                    continue

                payload_b64 = data["media"].get("payload")
                if not payload_b64:
                    continue

                audio_bytes = base64.b64decode(payload_b64)
                buffer += audio_bytes

                if len(buffer) >= MIN_CHUNK_SIZE:
                    buffer = buffer[MIN_CHUNK_SIZE:]

                    # 🔴 TEMP STT (replace with real STT later)
                    simulated_text = "interest rate"
                    logger.info(f"🗣 Detected text: {simulated_text}")

                    reply_text = get_faq_reply(simulated_text)
                    logger.info(f"🤖 Bot reply: {reply_text}")

                    pcm_audio = await asyncio.to_thread(
                        sarvam_tts_to_pcm, reply_text
                    )

                    # Stream PCM back to Exotel
                    for i in range(0, len(pcm_audio), MIN_CHUNK_SIZE):
                        await ws.send_bytes(
                            pcm_audio[i:i + MIN_CHUNK_SIZE]
                        )

            else:
                logger.warning("⚠️ Unknown WebSocket frame ignored")

    except WebSocketDisconnect:
        logger.info("🔌 Voicebot disconnected")

    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")

# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )