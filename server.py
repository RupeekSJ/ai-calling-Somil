print("🚀 STARTING SERVER V6.3 - EXOTEL VOICEBOT (SARVAM PCM MODE)")

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
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("voicebot")
tts_logger = logging.getLogger("sarvam-tts")

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
# SARVAM TTS → RAW PCM16 (NO WAV)
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

    try:
        tts_logger.info("🔊 Sarvam TTS request started")
        tts_logger.debug(f"➡️ URL: {url}")
        tts_logger.debug(
            f"➡️ Headers: "
            f"{ {k: ('***' if 'key' in k.lower() else v) for k, v in headers.items()} }"
        )
        tts_logger.debug(f"➡️ Payload:\n{json.dumps(payload, indent=2)}")

        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        tts_logger.info(f"📡 HTTP Status: {resp.status_code}")
        tts_logger.debug(f"📦 Raw Response:\n{resp.text}")

        resp.raise_for_status()

        resp_json = resp.json()
        tts_logger.debug(
            f"📦 Parsed JSON:\n{json.dumps(resp_json, indent=2)}"
        )

        # Sarvam returns base64 PCM16 directly
        audio_b64 = resp_json["audios"][0]
        pcm_bytes = base64.b64decode(audio_b64)

        tts_logger.info(
            f"🎧 PCM received | bytes={len(pcm_bytes)} | "
            f"duration≈{len(pcm_bytes)/(SAMPLE_RATE*BYTES_PER_SAMPLE):.2f}s"
        )

        return pcm_bytes

    except Exception:
        tts_logger.error("❌ Sarvam TTS failed", exc_info=True)
        raise

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
            logger.debug(f"📨 WebSocket frame: {message}")

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("⚠️ Invalid JSON frame")
                    continue

                event = data.get("event")

                if event != "media":
                    logger.info(f"ℹ️ Exotel event: {event}")
                    continue

                payload_b64 = data["media"].get("payload")
                if not payload_b64:
                    continue

                audio_bytes = base64.b64decode(payload_b64)
                buffer += audio_bytes

                logger.debug(
                    f"🎙 RX audio | chunk={len(audio_bytes)} | buffer={len(buffer)}"
                )

                if len(buffer) >= MIN_CHUNK_SIZE:
                    buffer = buffer[MIN_CHUNK_SIZE:]

                    # 🔴 TEMP STT PLACEHOLDER
                    simulated_text = "interest rate"
                    logger.info(f"🗣 STT text: {simulated_text}")

                    reply_text = get_faq_reply(simulated_text)
                    logger.info(f"🤖 Reply text: {reply_text}")

                    pcm_audio = await asyncio.to_thread(
                        sarvam_tts_to_pcm, reply_text
                    )

                    for i in range(0, len(pcm_audio), MIN_CHUNK_SIZE):
                        chunk = pcm_audio[i:i + MIN_CHUNK_SIZE]
                        await ws.send_bytes(chunk)
                        logger.debug(
                            f"📤 TX audio | size={len(chunk)}"
                        )

            else:
                logger.warning("⚠️ Unknown WS frame ignored")

    except WebSocketDisconnect:
        logger.info("🔌 Exotel Voicebot disconnected")

    except Exception:
        logger.error("❌ WebSocket fatal error", exc_info=True)

# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="debug"
    )
