print("🚀 STARTING SERVER V6.0 - EXOTEL VOICEBOT (BIDIRECTIONAL)")

import os
import json
import asyncio
import logging
import websockets
import requests
import base64
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

SAMPLE_RATE = 16000          # MUST match Voicebot Applet
BYTES_PER_SAMPLE = 2         # PCM16
MIN_CHUNK_SIZE = 3200        # 100ms @ 16kHz

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("voicebot")

# --------------------------------------------------
# FASTAPI (for health + dynamic WS if needed)
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
        "answer": "The interest rate starts from ten percent per annum and is personalized for each customer. You can check your exact rate in the Rupeek app."
    },
    {
        "keywords": ["pre approved", "limit"],
        "answer": "A pre approved limit means you already have a sanctioned loan offer with no documents required. Please open the Rupeek app to see your exact limit."
    },
    {
        "keywords": ["gold", "collateral"],
        "answer": "This is a personal loan without gold or any collateral. The loan is completely unsecured."
    },
    {
        "keywords": ["repay", "emi"],
        "answer": "Your EMI will be auto deducted from your linked bank account on the fifth of every month. You can also repay using the Pay Now option in the Rupeek app."
    },
]

DEFAULT_REPLY = (
    "I can help you with loan details like interest rate, pre approved limit, "
    "repayment process, or tenure. Please ask your question."
)

# --------------------------------------------------
# SIMPLE INTENT MATCHER
# --------------------------------------------------
def get_faq_reply(text: str) -> str:
    text = text.lower()
    for faq in FAQS:
        if any(k in text for k in faq["keywords"]):
            return faq["answer"]
    return DEFAULT_REPLY

# --------------------------------------------------
# SARVAM TTS (NON-STREAMING → PCM)
# --------------------------------------------------
def sarvam_tts_to_pcm(text: str) -> bytes:
    """
    Calls Sarvam TTS, returns RAW PCM16 bytes (NO WAV HEADER)
    """
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

    # ⚠️ IMPORTANT:
    # Strip WAV header (44 bytes) → Exotel wants RAW PCM
    return wav_bytes[44:]

# --------------------------------------------------
# WEBSOCKET VOICEBOT
# --------------------------------------------------
async def voicebot_handler(websocket):
    logger.info("🎧 Exotel Voicebot connected")

    buffer = b""

    try:
        async for message in websocket:

            # Exotel sends raw PCM bytes
            if isinstance(message, bytes):
                buffer += message

                # Process in 100ms windows
                if len(buffer) >= MIN_CHUNK_SIZE:
                    audio_chunk = buffer[:MIN_CHUNK_SIZE]
                    buffer = buffer[MIN_CHUNK_SIZE:]

                    # ----------------------------
                    # TODO: STT SHOULD GO HERE
                    # ----------------------------
                    # For now, simulate detected text
                    simulated_text = "interest rate"

                    logger.info(f"🗣 Detected text: {simulated_text}")

                    reply_text = get_faq_reply(simulated_text)
                    logger.info(f"🤖 Bot reply: {reply_text}")

                    # Convert reply to PCM
                    pcm_audio = await asyncio.to_thread(
                        sarvam_tts_to_pcm, reply_text
                    )

                    # Chunk & stream back
                    for i in range(0, len(pcm_audio), MIN_CHUNK_SIZE):
                        await websocket.send(
                            pcm_audio[i:i + MIN_CHUNK_SIZE]
                        )

            else:
                logger.warning("⚠️ Non-binary WS message ignored")

    except Exception as e:
        logger.error(f"❌ WS error: {e}")

    finally:
        logger.info("🔌 Voicebot disconnected")

# --------------------------------------------------
# START SERVER
# --------------------------------------------------
async def main():
    ws_server = await websockets.serve(
        voicebot_handler,
        host="0.0.0.0",
        port=PORT,
        max_size=100_000
    )

    logger.info(f"🚀 Voicebot WS listening on port {PORT}")
    await ws_server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
