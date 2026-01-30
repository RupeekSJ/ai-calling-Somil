import os
import json
import asyncio
import logging
import sys
import base64
import requests
import io
import struct
import time
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

# ==================================================
# ENV
# ==================================================
load_dotenv()
PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG
# ==================================================
SAMPLE_RATE = 16000
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6
MAX_SILENCE_RETRIES = 2
MAX_CONFUSION_RETRIES = 2
PAUSE_SECONDS = 0.7

# ==================================================
# LOGGING (DETAILED)
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
SESSIONS = {}

# ==================================================
# UPDATED PITCH (SINGLE STRING – SAFE)
# ==================================================
PITCH = (
    "Hi, my name is Neeraja, calling from Rupeek. "
    "You have a pre approved personal loan at zero interest, "
    "which means you do not pay any interest if you repay within the same month. "
    "The process is completely digital with no paperwork required, "
    "and you can receive instant disbursal to your bank account in just sixty seconds. "
    "With timely repayments, you can improve your CIBIL score and unlock higher limits in the future. "
    "This is a limited time offer. Are you interested?"
)

# ==================================================
# STEP FLOW
# ==================================================
STEPS = [
    PITCH,
    "Step one. Download the Rupeek app from the Play Store. Say next once done.",
    "Step two. Complete your KYC using Aadhaar. Say next once completed.",
    "Step three. Select your loan amount and confirm disbursal. Say done to finish."
]

# ==================================================
# UPDATED FAQS (MORE REALISTIC)
# ==================================================
FAQS = {
    "loan amount": (
        "The loan amount is personalized for each customer. "
        "You can check your approved limit in the Rupeek app under Click Cash."
    ),
    "interest": (
        "If you repay the amount within the same month, there is zero interest. "
        "If repayment is missed, the loan converts into EMI with interest as shown in the app."
    ),
    "emi": (
        "There is no EMI if you repay within the month. "
        "If converted to EMI, the amount depends on the tenure you choose."
    ),
    "processing": (
        "Zero interest applies if repaid within the month. "
        "The processing fee is a one time standard charge for instant digital disbursal."
    ),
    "repay": (
        "You need to repay the amount by month end to avoid interest. "
        "Repayment can be done easily through the Rupeek app."
    )
}

# ==================================================
# INTENT CLASSIFIER (WITH PREVIOUS)
# ==================================================
def classify(text: str):
    t = text.lower()
    logger.info(f"🔍 Classifying text: {t}")

    for key in FAQS:
        if key in t:
            return ("FAQ", key)

    if any(x in t for x in ["previous", "back", "go back"]):
        return ("PREVIOUS", None)

    if any(x in t for x in ["no", "not interested", "stop"]):
        return ("NO", None)

    if any(x in t for x in ["yes", "yeah", "ok", "okay", "interested"]):
        return ("YES", None)

    if any(x in t for x in ["next", "continue"]):
        return ("NEXT", None)

    if any(x in t for x in ["repeat", "again"]):
        return ("REPEAT", None)

    if any(x in t for x in ["done", "completed"]):
        return ("DONE", None)

    return ("UNKNOWN", None)

# ==================================================
# AUDIO UTILS
# ==================================================
def is_speech(pcm: bytes) -> bool:
    total, count = 0, 0
    for i in range(0, len(pcm) - 1, 2):
        s = int.from_bytes(pcm[i:i+2], "little", signed=True)
        total += abs(s)
        count += 1
    avg_energy = total / max(count, 1)
    logger.debug(f"🔊 Avg energy: {avg_energy}")
    return avg_energy > SPEECH_THRESHOLD

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
    if r.status_code != 200:
        logger.error(f"❌ STT failed: {r.status_code}")
        return ""
    return r.json().get("transcript", "").strip()

def sarvam_tts(text: str) -> bytes:
    logger.info(f"🗣 BOT → {text[:80]}...")
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
            "media": {"payload": base64.b64encode(pcm[i:i+MIN_CHUNK_SIZE]).decode()}
        }))
        await asyncio.sleep(0)

# ==================================================
# WEBSOCKET
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    session_id = str(time.time())

    logger.info(f"🎧 Call connected | {session_id}")

    SESSIONS[session_id] = {
        "step": 0,
        "silence": 0,
        "confusion": 0,
        "started": False
    }

    buffer = b""
    speech_buffer = b""
    silence_count = 0

    try:
        while True:
            msg = await ws.receive()
            if "text" not in msg:
                continue

            data = json.loads(msg["text"])
            event = data.get("event")

            if event == "start" and not SESSIONS[session_id]["started"]:
                logger.info("▶️ Starting pitch")
                pcm = await asyncio.to_thread(sarvam_tts, STEPS[0])
                await send_pcm(ws, pcm)
                SESSIONS[session_id]["started"] = True
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

            if silence_count >= SILENCE_CHUNKS and speech_buffer:
                text = await asyncio.to_thread(sarvam_stt, speech_buffer)
                speech_buffer = b""
                silence_count = 0

                logger.info(f"🗣 USER → {text}")

                if not text:
                    SESSIONS[session_id]["silence"] += 1
                    logger.warning(f"🔇 Silence count: {SESSIONS[session_id]['silence']}")
                    continue

                intent, meta = classify(text)
                logger.info(f"🎯 Intent={intent}, Meta={meta}")

                # FAQ
                if intent == "FAQ":
                    pcm = await asyncio.to_thread(sarvam_tts, FAQS[meta])
                    await send_pcm(ws, pcm)
                    await asyncio.sleep(PAUSE_SECONDS)
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        STEPS[SESSIONS[session_id]["step"]]
                    )
                    await send_pcm(ws, pcm)
                    continue

                # PREVIOUS
                if intent == "PREVIOUS":
                    SESSIONS[session_id]["step"] = max(0, SESSIONS[session_id]["step"] - 1)
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        STEPS[SESSIONS[session_id]["step"]]
                    )
                    await send_pcm(ws, pcm)
                    continue

                # FLOW
                if intent in ("YES", "NEXT"):
                    SESSIONS[session_id]["step"] += 1
                    if SESSIONS[session_id]["step"] >= len(STEPS):
                        pcm = await asyncio.to_thread(
                            sarvam_tts,
                            "Your process is complete. Thank you."
                        )
                        await send_pcm(ws, pcm)
                        break
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        STEPS[SESSIONS[session_id]["step"]]
                    )
                    await send_pcm(ws, pcm)
                    continue

                if intent == "REPEAT":
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        STEPS[SESSIONS[session_id]["step"]]
                    )
                    await send_pcm(ws, pcm)
                    continue

                if intent == "NO":
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        "Thank you for your time. Have a great day."
                    )
                    await send_pcm(ws, pcm)
                    break

                if intent == "DONE":
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        "Thank you. Your request is complete."
                    )
                    await send_pcm(ws, pcm)
                    break

                # UNKNOWN
                SESSIONS[session_id]["confusion"] += 1
                logger.warning(f"⚠️ Confusion count: {SESSIONS[session_id]['confusion']}")

                if SESSIONS[session_id]["confusion"] > MAX_CONFUSION_RETRIES:
                    pcm = await asyncio.to_thread(
                        sarvam_tts,
                        "I will connect you to a representative for further assistance."
                    )
                    await send_pcm(ws, pcm)
                    break

                pcm = await asyncio.to_thread(
                    sarvam_tts,
                    "Please say yes, next, repeat, previous, or no."
                )
                await send_pcm(ws, pcm)

    except WebSocketDisconnect:
        logger.info(f"🔌 Call disconnected | {session_id}")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
