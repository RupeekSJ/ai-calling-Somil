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
import time
from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File
)
from fastapi.responses import HTMLResponse
import uvicorn

# ==================================================
# ENV
# ==================================================
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME")

# Exotel
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_FROM_NUMBER = os.getenv("EXOTEL_FROM_NUMBER")  # EXOTEL NUMBER (FIXED)

# Sarvam
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG
# ==================================================
SAMPLE_RATE = 16000
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6

MIN_SPEECH_MS = 800
MIN_SPEECH_BYTES = int(SAMPLE_RATE * 2 * (MIN_SPEECH_MS / 1000))
BOT_COOLDOWN = 2.5

# ==================================================
# LOGGING
# ==================================================
logging.basicConfig(
    level=LOG_LEVEL,
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
# phone_number -> pitch
CUSTOMER_PITCH = {}

# ==================================================
# WHERE THE ACTUAL CALL IS MADE (curl equivalent)
# ==================================================
def trigger_exotel_call(customer_number: str):
    """
    This function is equivalent to:
    curl -X POST https://api.exotel.com/v1/Accounts/.../Calls/connect.json
    """
    url = (
        f"https://api.exotel.com/v1/Accounts/"
        f"{EXOTEL_ACCOUNT_SID}/Calls/connect.json"
    )

    payload = {
        "From": customer_number,          # ✅ CUSTOMER NUMBER (VARIES)
        "CallerId": EXOTEL_FROM_NUMBER,   # ✅ EXOTEL NUMBER (FIXED)
        "Url": f"{PUBLIC_HOSTNAME}/ws?number={customer_number}"
    }

    response = requests.post(
        url,
        auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )

    logger.info(
        f"📞 Calling {customer_number} | "
        f"Exotel={EXOTEL_FROM_NUMBER} | "
        f"Status={response.status_code}"
    )

# ==================================================
# UPLOAD HTML
# ==================================================
@app.get("/", response_class=HTMLResponse)
def upload_page():
    with open("upload.html", "r", encoding="utf-8") as f:
        return f.read()

# ==================================================
# CSV UPLOAD ENDPOINT
# ==================================================
@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "Only CSV files are allowed"}

    content = await file.read()
    reader = csv.DictReader(content.decode("utf-8").splitlines())

    CUSTOMER_PITCH.clear()

    for row in reader:
        phone = row.get("phone_number")
        pitch = row.get("pitch")

        if phone and pitch:
            CUSTOMER_PITCH[phone.strip()] = pitch.strip()

    if not CUSTOMER_PITCH:
        return {"error": "CSV empty or invalid"}

    logger.info(f"📂 Uploaded CSV with {len(CUSTOMER_PITCH)} customers")

    # 🔥 Trigger outbound calls
    for phone in CUSTOMER_PITCH:
        trigger_exotel_call(phone)
        await asyncio.sleep(1)  # Exotel rate safety

    return {
        "status": "success",
        "customers": len(CUSTOMER_PITCH),
        "message": "Calls triggered"
    }

# ==================================================
# FAQ / INTENT LOGIC
# ==================================================
FAQS = [
    (["interest", "rate"],
     "The interest rate starts from ten percent per annum."),
    (["limit", "pre approved"],
     "Your loan limit is already sanctioned."),
    (["emi", "repay"],
     "Your EMI will be auto deducted on the fifth of every month."),
    (["yes", "interested"],
     "Great. I will arrange a callback from our executive."),
    (["no", "not interested"],
     "Thank you for your time. Have a great day.")
]

def get_reply(text: str) -> str:
    text = text.lower()
    for keys, reply in FAQS:
        if any(k in text for k in keys):
            return reply
    return "I can help you with interest rate, loan limit, or repayment."

# ==================================================
# AUDIO UTILS
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
def sarvam_stt(pcm: bytes) -> str:
    wav = pcm_to_wav(pcm)
    r = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": SARVAM_API_KEY},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"language_code": "en-IN"},
        timeout=20
    )
    r.raise_for_status()
    return r.json().get("transcript", "").strip()

def sarvam_tts(text: str) -> bytes:
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

async def send_pcm(ws, pcm, interrupt_fn):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        if interrupt_fn():
            return
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {
                "payload": base64.b64encode(
                    pcm[i:i + MIN_CHUNK_SIZE]
                ).decode()
            }
        }))
        await asyncio.sleep(0)

# ==================================================
# WEBSOCKET (VOICE BOT)
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()

    phone = ws.query_params.get("number")
    pitch = CUSTOMER_PITCH.get(
        phone,
        "Hello, this is Rupeek personal loan assistant."
    )

    buffer = b""
    speech_buffer = b""
    silence_count = 0

    bot_speaking = False
    interrupted = False
    last_bot_spoke = 0

    try:
        while True:
            msg = await ws.receive()
            if "text" not in msg:
                continue

            data = json.loads(msg["text"])
            event = data.get("event")

            # Initial pitch
            if event == "start" and time.time() - last_bot_spoke > BOT_COOLDOWN:
                bot_speaking = True
                interrupted = False
                pcm = await asyncio.to_thread(sarvam_tts, pitch)
                await send_pcm(ws, pcm, lambda: interrupted)
                bot_speaking = False
                last_bot_spoke = time.time()
                continue

            if event != "media":
                continue

            chunk = base64.b64decode(data["media"]["payload"])
            buffer += chunk

            if len(buffer) < MIN_CHUNK_SIZE:
                continue

            frame = buffer[:MIN_CHUNK_SIZE]
            buffer = buffer[MIN_CHUNK_SIZE:]

            if is_speech(frame):
                if bot_speaking:
                    interrupted = True
                    bot_speaking = False
                    speech_buffer = b""
                    continue
                speech_buffer += frame
                silence_count = 0
            else:
                silence_count += 1

            if (
                silence_count >= SILENCE_CHUNKS and
                len(speech_buffer) >= MIN_SPEECH_BYTES
            ):
                text = await asyncio.to_thread(
                    sarvam_stt,
                    speech_buffer
                )
                speech_buffer = b""
                silence_count = 0

                if not text:
                    continue

                reply = get_reply(text)
                pcm = await asyncio.to_thread(sarvam_tts, reply)

                bot_speaking = True
                interrupted = False
                await send_pcm(ws, pcm, lambda: interrupted)
                bot_speaking = False
                last_bot_spoke = time.time()

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
