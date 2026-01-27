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

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File
)
from fastapi.responses import HTMLResponse, PlainTextResponse
import uvicorn

# ==================================================
# ENV
# ==================================================
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME").rstrip("/")

# Exotel
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

# Sarvam
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG (SAME AS WORKING CODE)
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
CUSTOMER_PITCH = {}

# ==================================================
# EXOTEL CALL TRIGGER
# ==================================================
def trigger_exotel_call(customer_number: str):
    url = (
        f"https://api.exotel.com/v1/Accounts/"
        f"{EXOTEL_ACCOUNT_SID}/Calls/connect.json"
    )

    payload = {
        "From": customer_number,
        "CallerId": EXOTEL_TO_NUMBER,
        "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
    }

    r = requests.post(
        url,
        auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )

    logger.info(f"📞 Call {customer_number} → {r.status_code}")

# ==================================================
# EXOTEL VOICE URL (CRITICAL FIX)
# ==================================================
@app.get("/exotel-voice")
def exotel_voice(number: str):
    ws_url = PUBLIC_HOSTNAME.replace("https://", "wss://")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream url="{ws_url}/ws" />
</Response>
"""

    logger.info(f"📡 Exotel voice hit for {number}")

    return PlainTextResponse(
        xml.strip(),
        media_type="text/xml"  # 🔥 REQUIRED
    )

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
    global pitch
    content = await file.read()
    reader = csv.DictReader(content.decode().splitlines())

    CUSTOMER_PITCH.clear()

    for row in reader:
        phone = row.get("phone_number")
        pitch = row.get("pitch")
        logger.info(f"-------1121212--------,{pitch}")
        if phone and pitch:
            CUSTOMER_PITCH[phone.strip()] = pitch.strip()


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

async def send_pcm(ws, pcm):
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

# ==================================================
# WEBSOCKET
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Exotel connected")

    phone = ws.query_params.get("number")
    logger.info(f"-------11212121313--------,{pitch}")
    pitch = CUSTOMER_PITCH.get(
        phone,
        pitch
    )

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

            # 🔥 OUTBOUND: play pitch on first media packet
            if event == "media" and not pitch_done:
                pcm = await asyncio.to_thread(sarvam_tts, pitch)
                await send_pcm(ws, pcm)
                pitch_done = True

            if event != "media":
                continue

            chunk = base64.b64decode(data["media"]["payload"])
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

            if silence_count >= SILENCE_CHUNKS and speech_buffer:
                text = await asyncio.to_thread(sarvam_stt, speech_buffer)
                speech_buffer = b""
                silence_count = 0

                if not text:
                    continue

                reply = get_reply(text)
                pcm = await asyncio.to_thread(sarvam_tts, reply)
                await send_pcm(ws, pcm)

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
