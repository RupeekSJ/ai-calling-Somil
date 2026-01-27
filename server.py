import os
import json
import asyncio
import logging
import sys
import base64
import requests
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

EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG
# ==================================================
SAMPLE_RATE = 16000
MIN_CHUNK_SIZE = 3200

# ==================================================
# LOGGING
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger("voicebot")

# ==================================================
# APP
# ==================================================
app = FastAPI()

# ==================================================
# IN-MEMORY STORE
# ==================================================
CALLSID_TO_PITCH = {}

# ==================================================
# EXOTEL CALL TRIGGER (VOICEBOT)
# ==================================================
def trigger_exotel_call(customer_number: str, pitch: str):
    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Calls/connect.json"

    payload = {
        "From": customer_number,
        "CallerId": EXOTEL_TO_NUMBER,
        # ⚠️ MUST BE YOUR VOICEBOT APP URL
        "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
    }

    r = requests.post(
        url,
        auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data=payload,
        timeout=10
    )
    r.raise_for_status()

    call_sid = r.json()["Call"]["Sid"]
    CALLSID_TO_PITCH[call_sid] = pitch

    logger.info(f"📞 Call placed → {customer_number} | CallSid={call_sid}")

# ==================================================
# HOME
# ==================================================
@app.get("/")
def home():
    return HTMLResponse(open("upload.html").read())

# ==================================================
# CSV UPLOAD
# ==================================================
@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    reader = csv.DictReader(content.decode().splitlines())

    for row in reader:
        phone = row.get("phone_number")
        pitch = row.get("pitch")

        if phone and pitch:
            logger.info(f"📄 Loaded pitch for {phone}: {pitch}")
            trigger_exotel_call(phone.strip(), pitch.strip())
            await asyncio.sleep(1)

    return {"status": "success"}

# ==================================================
# SARVAM TTS
# ==================================================
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
            "speech_sample_rate": "16000",
            "pace":2.0
        },
        timeout=15
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])

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

# ==================================================
# VOICEBOT WEBSOCKET (CORRECT)
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Voicebot WS connected")

    call_sid = None
    pitch_sent = False

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)

            event = data.get("event")

            # ✅ START EVENT → CALL SID
            if event == "start":
                call_sid = data["start"].get("call_sid")
                logger.info(f"☎️ CallSid={call_sid}")
                continue

            # ✅ PLAY PITCH ON FIRST MEDIA
            if event == "media" and not pitch_sent:
                pitch = CALLSID_TO_PITCH.get(
                    call_sid,
                    "Hello, this is Rupeek personal loan assistant."
                )

                logger.info(f"🗣 Pitch={pitch}")

                pcm = await asyncio.to_thread(sarvam_tts, pitch)
                await send_pcm(ws, pcm)

                pitch_sent = True
                continue

            # ✅ DRAIN MEDIA
            if event == "media":
                continue

            # ✅ STOP EVENT
            if event == "stop":
                logger.info("📴 Call ended")
                break

    except WebSocketDisconnect:
        logger.info("🔌 Voicebot disconnected")

    except Exception as e:
        logger.error(f"❌ WS error: {e}")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
