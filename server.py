import os
import json
import asyncio
import logging
import sys
import base64
import requests
import io
import struct
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
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6  # ~600ms silence ends utterance

# --------------------------------------------------
# LOGGING
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

# --------------------------------------------------
# FAQ
# --------------------------------------------------
FAQS = [
    {
        "keywords": ["rate", "interest"],
        "answer": "The interest rate starts from 10% per annum. It’s personalized for every customer based on their profile. You can check your exact rate in the Rupeek app."
    },
    {
        "keywords": ["pre approved", "pre-approved", "limit meaning"],
        "answer": "A pre-approved limit means you’ve been sanctioned a personal loan offer without any need for documents or additional verification."
    },
    {
        "keywords": ["my limit", "pre approved limit", "how much"],
        "answer": "Pre-approved limits typically start from ₹30,000 and are customized for every customer. You can view your exact limit by opening the Rupeek app."
    },
    {
        "keywords": ["gold", "collateral"],
        "answer": "This is a personal loan, completely without gold or any collateral. You can get it instantly with no documentation."
    },
    {
        "keywords": ["repay", "repayment", "emi pay"],
        "answer": "You can repay through the Pay Now button in the Rupeek app. The EMI will be auto-deducted from your linked bank account on the 5th of every month."
    },
    {
        "keywords": ["tenure", "duration", "months"],
        "answer": "The minimum tenure is 3 months and the maximum is up to 12 months. Since offers are customized, please open the app to see the tenure and limit applicable to you."
    },
    {
        "keywords": ["process", "how to get", "apply"],
        "answer": "Simply open the Rupeek app and complete 2-3 simple steps. The loan will be disbursed instantly to your bank account within 30–40 seconds."
    },
    {
        "keywords": ["emi", "monthly"],
        "answer": "EMI depends on the principal amount and tenure you select. You can calculate your EMI in the Rupeek app before confirming your loan."
    },
    {
        "keywords": ["higher loan", "increase amount"],
        "answer": "Once you repay your existing loan, you’ll automatically become eligible for a higher loan amount and lower interest rate in the future."
    },
    {
        "keywords": ["processing fee", "charges"],
        "answer": "The processing fee details are visible in the Rupeek app once you choose your loan amount and tenure."
    },
    {
        "keywords": ["pre close", "foreclose", "close loan"],
        "answer": "Yes, you can close or pre-close your loan anytime through the Rupeek app as per your convenience."
    }
]


def get_reply(text: str) -> str:
    text = text.lower()
    for keys, reply in FAQS:
        if any(k in text for k in keys):
            return reply
    return "I can help you with interest rate, loan limit, or repayment."

# --------------------------------------------------
# UTILS
# --------------------------------------------------
def is_speech(pcm: bytes) -> bool:
    total, count = 0, 0
    for i in range(0, len(pcm) - 1, 2):
        s = int.from_bytes(pcm[i:i+2], "little", signed=True)
        total += abs(s)
        count += 1
    if count == 0:
        return False
    avg = total / count
    logger.debug(f"🔈 Avg amplitude={avg}")
    return avg > SPEECH_THRESHOLD

def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                           SAMPLE_RATE * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()

# --------------------------------------------------
# SARVAM
# --------------------------------------------------
def sarvam_stt(pcm: bytes) -> str:
    wav = pcm_to_wav(pcm)
    resp = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": SARVAM_API_KEY},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"language_code": "en-IN"},
        timeout=20
    )
    stt_logger.info(f"📡 STT status={resp.status_code}")
    stt_logger.debug(f"📦 STT raw={resp.text}")
    resp.raise_for_status()

    # ✅ FIXED: transcript field
    return resp.json().get("transcript", "").strip()

def sarvam_tts(text: str) -> bytes:
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
    resp.raise_for_status()
    return base64.b64decode(resp.json()["audios"][0])

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
# WS
# --------------------------------------------------
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel connected")

    buffer = b""
    speech_buffer = b""
    silence_count = 0
    pitch_done = False

    try:
        while True:
            msg = await ws.receive()
            if "text" not in msg:
                continue

            data = json.loads(msg["text"])
            event = data.get("event")

            if event == "start" and not pitch_done:
                pcm = await asyncio.to_thread(
                    sarvam_tts,
                    "Hello, this is Rupeek personal loan assistant. "
                    "You may ask about interest rate, repayment, or loan limit."
                )
                await send_pcm(ws, pcm)
                pitch_done = True
                continue

            if event != "media":
                continue

            payload = data["media"].get("payload")
            if not payload:
                continue

            chunk = base64.b64decode(payload)
            buffer += chunk

            if len(buffer) < MIN_CHUNK_SIZE:
                continue

            frame = buffer[:MIN_CHUNK_SIZE]
            buffer = buffer[MIN_CHUNK_SIZE:]

            if is_speech(frame):
                speech_buffer += frame
                silence_count = 0
            else:
                silence_count += 1

            # ---- END OF UTTERANCE ----
            if silence_count >= SILENCE_CHUNKS and speech_buffer:
                logger.info("🗣 Utterance ended — sending to STT")
                text = await asyncio.to_thread(sarvam_stt, speech_buffer)
                speech_buffer = b""
                silence_count = 0

                if not text:
                    continue

                logger.info(f"📝 User said: {text}")
                reply = get_reply(text)
                pcm = await asyncio.to_thread(sarvam_tts, reply)
                await send_pcm(ws, pcm)

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")
