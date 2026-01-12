print("🚀 STARTING SERVER V7.2 - EXOTEL VOICEBOT (PCM SAFE)")

import os
import asyncio
import logging
import base64
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# 20ms @ 8kHz, 16-bit mono
FRAME_SIZE = 320  

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
def health():
    return {"status": "ok"}

# --------------------------------------------------
# FAQ KNOWLEDGE BASE
# --------------------------------------------------
FAQS = [
    {
        "keywords": ["interest", "rate"],
        "answer": "The interest rate starts from ten percent per annum and is personalized for every customer. Please check your exact rate in the Rupeek app."
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
    "I can help you with interest rate, pre approved limit, or repayment details. "
    "Please ask your question."
)

def get_faq_reply(text: str) -> str:
    text = text.lower()
    for faq in FAQS:
        if any(k in text for k in faq["keywords"]):
            return faq["answer"]
    return DEFAULT_REPLY

# --------------------------------------------------
# SARVAM TTS → PCM 16-bit 8kHz
# --------------------------------------------------
def sarvam_tts(text: str) -> bytes:
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

    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()

    wav = base64.b64decode(r.json()["audios"][0])
    return wav[44:]  # strip WAV header → raw PCM

# --------------------------------------------------
# EXOTEL VOICEBOT WS
# --------------------------------------------------
@app.websocket("/ws")
async def voicebot(ws: WebSocket):
    await ws.accept()
    logger.info("📞 Exotel connected")

    greeted = False

    try:
        while True:
            msg = await ws.receive()

            # Control frames
            if "text" in msg and not greeted:
                greeted = True

                simulated_text = "interest rate"
                reply = get_faq_reply(simulated_text)

                logger.info(f"🤖 Replying: {reply}")

                audio = await asyncio.to_thread(sarvam_tts, reply)

                for i in range(0, len(audio), FRAME_SIZE):
                    await ws.send_bytes(audio[i:i + FRAME_SIZE])
                    await asyncio.sleep(0.02)

            # Incoming audio ignored for now
            elif "bytes" in msg:
                pass

    except WebSocketDisconnect:
        logger.info("📴 Call ended")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
