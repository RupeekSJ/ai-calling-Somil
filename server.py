print("🚀 STARTING SERVER V9.0 - EXOTEL VOICEBOT (μ-LAW RENDER SAFE)")

import os
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

# --------------------------------------------------
# AUDIO CONFIG
# --------------------------------------------------
INPUT_SAMPLE_RATE = 16000  # Sarvam TTS output
OUTPUT_SAMPLE_RATE = 8000  # Exotel μ-law requirement
FRAME_SIZE = 160           # 20ms @ 8kHz μ-law

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
        "answer": "Interest rates start from 10% p.a. Check the Rupeek app for your exact rate."
    },
    {
        "keywords": ["pre approved", "limit"],
        "answer": "Pre approved limit means you already have a sanctioned loan offer. Check the Rupeek app for exact limit."
    },
    {
        "keywords": ["gold", "collateral"],
        "answer": "This is a personal loan without gold or collateral. Fully unsecured."
    },
    {
        "keywords": ["repay", "emi"],
        "answer": "EMI auto deducted on 5th of each month. You can also use 'Pay Now' in the app."
    },
]

DEFAULT_REPLY = "I can help you with interest rate, pre approved limit, repayment, or tenure. Please ask your question."

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
# PURE PYTHON μ-LAW ENCODER
# --------------------------------------------------
def linear_to_mulaw(sample: int) -> int:
    """Convert a single 16-bit PCM sample to 8-bit μ-law"""
    MU = 255
    MAX = 32767
    sample = max(-MAX, min(MAX, sample))
    sign = 0x80 if sample < 0 else 0x00
    magnitude = abs(sample)
    magnitude = min(magnitude, MAX)
    mulaw_sample = int((1 + MU) * (magnitude / (MAX + 1)))
    mulaw_sample = 255 - mulaw_sample
    return mulaw_sample | sign

def pcm16_bytes_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert PCM16 bytes to μ-law bytes"""
    mulaw = bytearray()
    for i in range(0, len(pcm_bytes), 2):
        sample = int.from_bytes(pcm_bytes[i:i+2], "little", signed=True)
        mulaw.append(linear_to_mulaw(sample))
    return bytes(mulaw)

# --------------------------------------------------
# SARVAM TTS → PCM16
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
    wav_bytes = base64.b64decode(resp.json()["audios"][0])
    # Strip WAV header (44 bytes)
    return wav_bytes[44:]

# --------------------------------------------------
# WEBSOCKET ENDPOINT
# --------------------------------------------------
@app.websocket("/ws")
async def voicebot_ws(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel Voicebot connected")

    responded = False  # reply only once per call

    try:
        async for chunk in ws.iter_bytes():
            if not responded:
                # ------------------------
                # 🔴 Placeholder STT
                # ------------------------
                simulated_text = "interest rate"
                logger.info(f"🗣 Detected text: {simulated_text}")

                reply_text = get_faq_reply(simulated_text)
                logger.info(f"🤖 Bot reply: {reply_text}")

                pcm16 = await asyncio.to_thread(sarvam_tts_to_pcm16, reply_text)
                mulaw_bytes = pcm16_bytes_to_mulaw(pcm16)

                # Stream in 20ms frames
                for i in range(0, len(mulaw_bytes), FRAME_SIZE):
                    await ws.send_bytes(mulaw_bytes[i:i + FRAME_SIZE])
                    await asyncio.sleep(0.02)  # simulate real-time streaming

                responded = True  # don't repeat

    except WebSocketDisconnect:
        logger.info("🔌 Voicebot disconnected")
    except Exception as e:
        logger.error(f"❌ WS error: {e}")

# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, log_level="info")
