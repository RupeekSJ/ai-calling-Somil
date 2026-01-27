import os
import json
import asyncio
import logging
import sys
import base64
import requests
import io
import struct
import csv
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse
import uvicorn

# ==================================================
# ENV
# ==================================================
load_dotenv()

PORT = int(os.getenv("PORT", 10000))

# Exotel
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

# Sarvam
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG (WORKING)
# ==================================================
SAMPLE_RATE = 16000
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6

# ==================================================
# LOGGING
# ==================================================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger("voicebot")

# ==================================================
# FASTAPI
# ==================================================
app = FastAPI()

# ==================================================
# IN-MEMORY STORE
# ==================================================
CUSTOMER_PITCH: dict[str, str] = {}

# ==================================================
# EXOTEL CALL TRIGGER (USING WORKING EXOTEL APP)
# ==================================================
def trigger_exotel_call(customer_number: str):
    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Calls/connect.json"

    payload = {
        "From": customer_number,
        "CallerId": EXOTEL_TO_NUMBER,
        # ✅ Your already working Exotel App
        "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
    }

    r = requests.post(
        url,
        auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data=payload,
        timeout=10
    )

    logger.info(f"📞 Call {customer_number} → {r.status_code}")

# ==================================================
# UPLOAD PAGE
# ==================================================
@app.get("/", response_class=HTMLResponse)
def upload_page():
    with open("upload.html", "r", encoding="utf-8") as f:
        return f.read()

# ==================================================
# CSV UPLOAD
# ==================================================
@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    reader = csv.DictReader(content.decode().splitlines())

    CUSTOMER_PITCH.clear()

    for row in reader:
        phone = row.get("phone_number")
        pitch = row.get("pitch")

        if not phone or not pitch:
            continue

        # ✅ strip quotes + whitespace
        clean_pitch = pitch.strip().strip('"').strip("'")

        CUSTOMER_PITCH[phone.strip()] = clean_pitch
        logger.info(f"📄 Loaded pitch for {phone}: {clean_pitch}")

    for phone in CUSTOMER_PITCH:
        trigger_exotel_call(phone)
        await asyncio.sleep(1)

    return {
        "status": "success",
        "customers": len(CUSTOMER_PITCH)
    }

# ==================================================
# FAQ
# ==================================================
FAQS = [
    (["interest", "rate"], "The interest rate starts from ten percent per annum."),
    (["limit", "pre approved"], "Your loan limit is already sanctioned."),
    (["emi", "repay"], "Your EMI will be auto deducted on the fifth of every month.")
]

def get_reply(text: str) -> str:
    text = text.lower()
    for keys, reply in FAQS:
        if any(k in text for k in keys):
            return reply
    return "I can help you with interest rate, loan limit, or repayment."

# ==================================================
# AUDIO UTILS (WORKING LOGIC)
# ==================================================
def is_speech(pcm: bytes) -> bool:
    total, count = 0, 0
    for i in range(0, len(pcm) - 1, 2):
        s = int.from_bytes(pcm[i:i+2], "little", signed=True)
        total += abs(s)
        count += 1
    return count > 0 and (total / count) > SPEECH_THRESHOLD

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

# ==================================================
# SARVAM
# ==================================================
def sarvam_tts(text: str) -> bytes:
    if not text:
        raise ValueError("TTS text is empty")

    r = requests.post(
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
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])

async def send_pcm(ws, pcm):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {
                "payload": base64.b64encode(pcm[i:i + MIN_CHUNK_SIZE]).decode()
            }
        }))
        await asyncio.sleep(0)

# ==================================================
# WEBSOCKET (FINAL, CLEAN)
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel connected")

    # 🔥 Exotel App MUST pass ?number=XXXX
    phone = ws.query_params.get("number")
    pitch = CUSTOMER_PITCH.get(phone)

    logger.info(f"☎️ WS number={phone}")
    logger.info(f"🗣 Pitch={pitch}")

    if not pitch:
        pitch = "Hello, this is Rupeek personal loan assistant."

    try:
        # ✅ play pitch immediately
        pcm = await asyncio.to_thread(sarvam_tts, pitch)
        await send_pcm(ws, pcm)

        # keep socket alive
        while True:
            await ws.receive()

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
