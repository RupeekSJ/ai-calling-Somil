print("🚀 STARTING SERVER V7.0 - EXOTEL VOICEBOT (G711 μ-LAW)")

import os
import json
import asyncio
import logging
import base64
import requests
import audioop
import g711
import websockets

from dotenv import load_dotenv
from fastapi import FastAPI

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# --------------------------------------------------
# EXOTEL AUDIO REQUIREMENTS
# --------------------------------------------------
INPUT_SAMPLE_RATE = 16000      # Sarvam output
OUTPUT_SAMPLE_RATE = 8000      # Exotel requirement
FRAME_SIZE = 160               # 20ms @ 8kHz μ-law

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("voicebot")

# --------------------------------------------------
# FASTAPI (Render health check)
# --------------------------------------------------
app = FastAPI()

@app.get("/")
async def health():
    return {"status": "ok", "service": "exotel-voicebot"}

# --------------------------------------------------
# FAQ KNOWLEDGE BASE
# --------------------------------------------------
FAQS = [
    {
        "keywords": ["interest", "rate"],
        "answer": "The interest rate starts from ten percent per annum and is personalized for each customer. Please check your exact rate in the Rupeek app."
    },
    {
        "keywords": ["pre approved", "limit"],
        "answer": "A pre approved limit means you already have a sanctioned loan offer. Please open the Rupeek app to view your exact limit."
    },
    {
        "keywords": ["gold", "collateral"],
        "answer": "This is a personal loan without gold or any collateral. It is completely unsecured."
    },
    {
        "keywords": ["repay", "emi"],
        "answer": "Your EMI will be auto deducted from your linked bank account on the fifth of every month."
    },
]

DEFAULT_REPLY = (
    "I can help you with interest rate, pre approved limit, repayment, or tenure. "
    "Please ask your question."
)

# --------------------------------------------------
# SIMPLE INTENT MATCHING
# --------------------------------------------------
def get_faq_reply(text: str) -> str:
    text = text.lower()
    for faq in FAQS:
        if any(k in text for k in faq["keywords"]):
            return faq["answer"]
    return DEFAULT_REPLY

# --------------------------------------------------
# SARVAM TTS → PCM16 (16kHz)
# --------------------------------------------------
def sarvam_tts_to_pcm16(text: str) -> bytes:
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

    # Strip WAV header (44 bytes)
    return wav_bytes[44:]

# --------------------------------------------------
# PCM16 (16kHz) → G711 μ-law (8kHz)
# --------------------------------------------------
def pcm16_to_mulaw(pcm16: bytes) -> bytes:
    pcm8k, _ = audioop.ratecv(
        pcm16,
        2,      # bytes per sample
        1,      # mono
        INPUT_SAMPLE_RATE,
        OUTPUT_SAMPLE_RATE,
        None
    )
    return g711.encode_pcm(pcm8k)

# --------------------------------------------------
# EXOTEL VOICEBOT HANDLER
# --------------------------------------------------
async def voicebot_handler(websocket):
    logger.info("🎧 Exotel Voicebot connected")

    try:
        async for message in websocket:

            # Exotel sends raw μ-law audio (we ignore for now)
            if not isinstance(message, bytes):
                continue

            # -----------------------------
            # ⚠️ STT WOULD GO HERE
            # -----------------------------
            # For now, simulate intent
            simulated_text = "interest rate"
            logger.info(f"🗣 Simulated user text: {simulated_text}")

            reply_text = get_faq_reply(simulated_text)
            logger.info(f"🤖 Bot reply: {reply_text}")

            pcm16 = await asyncio.to_thread(
                sarvam_tts_to_pcm16, reply_text
            )

            mulaw_audio = pcm16_to_mulaw(pcm16)

            # Stream 20ms μ-law frames
            for i in range(0, len(mulaw_audio), FRAME_SIZE):
                await websocket.send(
                    mulaw_audio[i:i + FRAME_SIZE]
                )

    except Exception as e:
        logger.error(f"❌ Voicebot error: {e}")

    finally:
        logger.info("🔌 Voicebot disconnected")

# --------------------------------------------------
# START SERVER (HTTP + WS)
# --------------------------------------------------
async def main():
    ws_server = await websockets.serve(
        voicebot_handler,
        host="0.0.0.0",
        port=PORT,
        max_size=100_000
    )

    logger.info(f"🚀 Voicebot WebSocket running on port {PORT}")
    await ws_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
