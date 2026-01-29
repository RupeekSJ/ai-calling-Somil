# import os
# import json
# import asyncio
# import logging
# import sys
# import base64
# import requests
# import csv
# from dotenv import load_dotenv

# from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
# from fastapi.responses import HTMLResponse
# import uvicorn

# # ==================================================
# # ENV
# # ==================================================
# load_dotenv()

# PORT = int(os.getenv("PORT", 10000))

# EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
# EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
# EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
# EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

# SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# # ==================================================
# # AUDIO CONFIG
# # ==================================================
# SAMPLE_RATE = 16000
# MIN_CHUNK_SIZE = 3200

# # ==================================================
# # LOGGING
# # ==================================================
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[logging.StreamHandler(sys.stdout)],
#     force=True
# )
# logger = logging.getLogger("voicebot")

# # ==================================================
# # APP
# # ==================================================
# app = FastAPI()

# # ==================================================
# # IN-MEMORY STORE
# # ==================================================
# CALLSID_TO_PITCH = {}

# # ==================================================
# # EXOTEL CALL TRIGGER (VOICEBOT)
# # ==================================================
# def trigger_exotel_call(customer_number: str, pitch: str):
#     url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Calls/connect.json"

#     payload = {
#         "From": customer_number,
#         "CallerId": EXOTEL_TO_NUMBER,
#         # ⚠️ MUST BE YOUR VOICEBOT APP URL
#         "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
#     }

#     r = requests.post(
#         url,
#         auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
#         data=payload,
#         timeout=10
#     )
#     r.raise_for_status()

#     call_sid = r.json()["Call"]["Sid"]
#     CALLSID_TO_PITCH[call_sid] = pitch

#     logger.info(f"📞 Call placed → {customer_number} | CallSid={call_sid}")

# # ==================================================
# # HOME
# # ==================================================
# @app.get("/")
# def home():
#     return HTMLResponse(open("upload.html").read())

# # ==================================================
# # CSV UPLOAD
# # ==================================================
# @app.post("/upload-csv")
# async def upload_csv(file: UploadFile = File(...)):
#     content = await file.read()
#     reader = csv.DictReader(content.decode().splitlines())

#     for row in reader:
#         phone = row.get("phone_number")
#         pitch = row.get("pitch")

#         if phone and pitch:
#             logger.info(f"📄 Loaded pitch for {phone}: {pitch}")
#             trigger_exotel_call(phone.strip(), pitch.strip())
#             await asyncio.sleep(1)

#     return {"status": "success"}

# # ==================================================
# # SARVAM TTS
# # ==================================================
# def sarvam_tts(text: str) -> bytes:
#     r = requests.post(
#         "https://api.sarvam.ai/text-to-speech",
#         headers={
#             "api-subscription-key": SARVAM_API_KEY,
#             "Content-Type": "application/json"
#         },
#         json={
#             "text": text,
#             "target_language_code": "en-IN",
#             "speech_sample_rate": "16000",
#             # "pace":2.0
#         },
#         timeout=15
#     )
#     r.raise_for_status()
#     return base64.b64decode(r.json()["audios"][0])

# async def send_pcm(ws: WebSocket, pcm: bytes):
#     for i in range(0, len(pcm), MIN_CHUNK_SIZE):
#         await ws.send_text(json.dumps({
#             "event": "media",
#             "media": {
#                 "payload": base64.b64encode(
#                     pcm[i:i + MIN_CHUNK_SIZE]
#                 ).decode()
#             }
#         }))
#         await asyncio.sleep(0)

# # ==================================================
# # VOICEBOT WEBSOCKET (CORRECT)
# # ==================================================
# @app.websocket("/ws")
# async def ws_handler(ws: WebSocket):
#     await ws.accept()
#     logger.info("🎧 Voicebot WS connected")

#     call_sid = None
#     pitch_sent = False

#     try:
#         while True:
#             msg = await ws.receive_text()
#             data = json.loads(msg)

#             event = data.get("event")

#             # ✅ START EVENT → CALL SID
#             if event == "start":
#                 call_sid = data["start"].get("call_sid")
#                 logger.info(f"☎️ CallSid={call_sid}")
#                 continue

#             # ✅ PLAY PITCH ON FIRST MEDIA
#             if event == "media" and not pitch_sent:
#                 pitch = CALLSID_TO_PITCH.get(
#                     call_sid,
#                     "Hello, this is Rupeek personal loan assistant."
#                 )

#                 logger.info(f"🗣 Pitch={pitch}")

#                 pcm = await asyncio.to_thread(sarvam_tts, pitch)
#                 await send_pcm(ws, pcm)

#                 pitch_sent = True
#                 continue

#             # ✅ DRAIN MEDIA
#             if event == "media":
#                 continue

#             # ✅ STOP EVENT
#             if event == "stop":
#                 logger.info("📴 Call ended")
#                 break

#     except WebSocketDisconnect:
#         logger.info("🔌 Voicebot disconnected")

#     except Exception as e:
#         logger.error(f"❌ WS error: {e}")

# # ==================================================
# # START
# # ==================================================
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=PORT)


# import os
# import json
# import asyncio
# import logging
# import sys
# import base64
# import requests
# import io
# import struct
# import csv
# from dotenv import load_dotenv

# from fastapi import (
#     FastAPI,
#     WebSocket,
#     WebSocketDisconnect,
#     UploadFile,
#     File
# )
# from fastapi.responses import HTMLResponse, PlainTextResponse
# import uvicorn

# # ==================================================
# # ENV
# # ==================================================
# load_dotenv()

# PORT = int(os.getenv("PORT", 10000))
# PUBLIC_HOSTNAME = os.getenv("PUBLIC_HOSTNAME").rstrip("/")

# # Exotel
# EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
# EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
# EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
# EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

# # Sarvam
# SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# # ==================================================
# # AUDIO CONFIG (SAME AS WORKING CODE)
# # ==================================================
# SAMPLE_RATE = 16000
# MIN_CHUNK_SIZE = 3200
# SPEECH_THRESHOLD = 500
# SILENCE_CHUNKS = 6

# # ==================================================
# # LOGGING
# # ==================================================
# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[logging.StreamHandler(sys.stdout)],
#     force=True
# )
# logger = logging.getLogger("voicebot")

# # ==================================================
# # FASTAPI
# # ==================================================
# app = FastAPI()

# # ==================================================
# # IN-MEMORY STORE
# # ==================================================
# CUSTOMER_PITCH = {}
# pitch=""

# # ==================================================
# # EXOTEL CALL TRIGGER
# # ==================================================
# def trigger_exotel_call(customer_number: str):
#     url = (
#         f"https://api.exotel.com/v1/Accounts/"
#         f"{EXOTEL_ACCOUNT_SID}/Calls/connect.json"
#     )

#     payload = {
#         "From": customer_number,
#         "CallerId": EXOTEL_TO_NUMBER,
#         "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
#     }

#     r = requests.post(
#         url,
#         auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
#         data=payload,
#         headers={"Content-Type": "application/x-www-form-urlencoded"},
#         timeout=10
#     )

#     logger.info(f"📞 Call {customer_number} → {r.status_code}")

# # ==================================================
# # EXOTEL VOICE URL (CRITICAL FIX)
# # ==================================================
# @app.get("/exotel-voice")
# def exotel_voice(number: str):
#     ws_url = PUBLIC_HOSTNAME.replace("https://", "wss://")

#     xml = f"""<?xml version="1.0" encoding="UTF-8"?>
# <Response>
#   <Stream url="{ws_url}/ws" />
# </Response>
# """

#     logger.info(f"📡 Exotel voice hit for {number}")

#     return PlainTextResponse(
#         xml.strip(),
#         media_type="text/xml"  # 🔥 REQUIRED
#     )

# # ==================================================
# # UPLOAD PAGE
# # ==================================================
# @app.get("/", response_class=HTMLResponse)
# def upload_page():
#     with open("upload.html", "r", encoding="utf-8") as f:
#         return f.read()

# # ==================================================
# # CSV UPLOAD
# # ==================================================
# @app.post("/upload-csv")
# async def upload_csv(file: UploadFile = File(...)):
#     content = await file.read()
#     reader = csv.DictReader(content.decode().splitlines())

#     CUSTOMER_PITCH.clear()

#     for row in reader:
#         phone = row.get("phone_number")
#         pitch = row.get("pitch")
#         logger.info(f"-------1121212--------,{pitch}")
#         if phone and pitch:
#             CUSTOMER_PITCH[phone.strip()] = pitch.strip()
#             print(CUSTOMER_PITCH)

#     for phone in CUSTOMER_PITCH:
#         logger.info(f"CSV ++U+O++++++++++++++++++++++,{phone}")
#         trigger_exotel_call(phone)
#         await asyncio.sleep(1)

#     return {
#         "status": "success",
#         "customers": len(CUSTOMER_PITCH)
#     }

# # ==================================================
# # FAQ
# # ==================================================
# FAQS = [
#     (["interest", "rate"], "The interest rate starts from ten percent per annum."),
#     (["limit", "pre approved"], "Your loan limit is already sanctioned."),
#     (["emi", "repay"], "Your EMI will be auto deducted on the fifth of every month.")
# ]
# def get_pitch():
#         logger.info(f"-------1121212-function--------,{pitch}")
#         return pitch

# def get_reply(text: str) -> str:
#     text = text.lower()
#     for keys, reply in FAQS:
#         if any(k in text for k in keys):
#             return reply
#     return "I can help you with interest rate, loan limit, or repayment."

# # ==================================================
# # AUDIO UTILS (WORKING LOGIC)
# # ==================================================
# def is_speech(pcm: bytes) -> bool:
#     total, count = 0, 0
#     for i in range(0, len(pcm) - 1, 2):
#         s = int.from_bytes(pcm[i:i+2], "little", signed=True)
#         total += abs(s)
#         count += 1
#     return count > 0 and (total / count) > SPEECH_THRESHOLD

# def pcm_to_wav(pcm: bytes) -> bytes:
#     buf = io.BytesIO()
#     buf.write(b"RIFF")
#     buf.write(struct.pack("<I", 36 + len(pcm)))
#     buf.write(b"WAVEfmt ")
#     buf.write(struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
#                            SAMPLE_RATE * 2, 2, 16))
#     buf.write(b"data")
#     buf.write(struct.pack("<I", len(pcm)))
#     buf.write(pcm)
#     return buf.getvalue()

# # ==================================================
# # SARVAM
# # ==================================================
# def sarvam_stt(pcm: bytes) -> str:
#     wav = pcm_to_wav(pcm)
#     r = requests.post(
#         "https://api.sarvam.ai/speech-to-text",
#         headers={"api-subscription-key": SARVAM_API_KEY},
#         files={"file": ("audio.wav", wav, "audio/wav")},
#         data={"language_code": "en-IN"},
#         timeout=20
#     )
#     r.raise_for_status()
#     return r.json().get("transcript", "").strip()

# def sarvam_tts(text: str) -> bytes:
#     r = requests.post(
#         "https://api.sarvam.ai/text-to-speech",
#         headers={
#             "api-subscription-key": SARVAM_API_KEY,
#             "Content-Type": "application/json"
#         },
#         json={
#             "text": text,
#             "target_language_code": "en-IN",
#             "speech_sample_rate": "16000"
#         },
#         timeout=15
#     )
#     r.raise_for_status()
#     return base64.b64decode(r.json()["audios"][0])

# async def send_pcm(ws, pcm):
#     for i in range(0, len(pcm), MIN_CHUNK_SIZE):
#         await ws.send_text(json.dumps({
#             "event": "media",
#             "media": {
#                 "payload": base64.b64encode(
#                     pcm[i:i + MIN_CHUNK_SIZE]
#                 ).decode()
#             }
#         }))
#         await asyncio.sleep(0)

# # ==================================================
# # WEBSOCKET
# # ==================================================
# @app.websocket("/ws")
# async def ws_handler(ws: WebSocket):
#     await ws.accept()
#     logger.info("🎧 Exotel connected")

#     phone = ws.query_params.get("number")
#     print("12345543212345",CUSTOMER_PITCH)
#     print("12345678765432q",phone)

#     first_number = '7985361213'
#     pitch = CUSTOMER_PITCH.get(first_number)
#     print("12345543212345",pitch)

#     buffer = b""
#     speech_buffer = b""
#     silence_count = 0
#     pitch_done = False

#     try:
#         while True:
#             msg = await ws.receive()
#             if "text" not in msg:
#                 continue

#             data = json.loads(msg["text"])
#             event = data.get("event")

#             # 🔥 OUTBOUND: play pitch on first media packet
#             if event == "media" and not pitch_done:
#                 pcm = await asyncio.to_thread(sarvam_tts, pitch)
#                 await send_pcm(ws, pcm)
#                 pitch_done = True

#             if event != "media":
#                 continue

#             chunk = base64.b64decode(data["media"]["payload"])
#             buffer += chunk

#             if len(buffer) < MIN_CHUNK_SIZE:
#                 continue

#             frame = buffer[:MIN_CHUNK_SIZE]
#             buffer = buffer[MIN_CHUNK_SIZE:]

#             if is_speech(frame):
#                 speech_buffer += frame
#                 silence_count = 0
#             else:
#                 silence_count += 1

#             if silence_count >= SILENCE_CHUNKS and speech_buffer:
#                 text = await asyncio.to_thread(sarvam_stt, speech_buffer)
#                 speech_buffer = b""
#                 silence_count = 0

#                 if not text:
#                     continue

#                 reply = get_reply(text)
#                 pcm = await asyncio.to_thread(sarvam_tts, reply)
#                 await send_pcm(ws, pcm)

#     except WebSocketDisconnect:
#         logger.info("🔌 Call disconnected")

# # ==================================================
# # START
# # ==================================================
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=PORT)



# import os
# import json
# import asyncio
# import logging
# import sys
# import base64
# import requests
# import csv
# from dotenv import load_dotenv

# from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
# from fastapi.responses import HTMLResponse
# import uvicorn

# # ==================================================
# # ENV
# # ==================================================
# load_dotenv()

# PORT = int(os.getenv("PORT", 10000))

# EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
# EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
# EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
# EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

# SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# # ==================================================
# # CONFIG
# # ==================================================
# SAMPLE_RATE = 16000
# MIN_CHUNK_SIZE = 3200

# # ==================================================
# # LOGGING
# # ==================================================
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[logging.StreamHandler(sys.stdout)],
#     force=True
# )
# logger = logging.getLogger("voicebot")

# # ==================================================
# # APP
# # ==================================================
# app = FastAPI()

# # ==================================================
# # MEMORY STORES
# # ==================================================
# CALLSID_TO_PITCH = {}

# # ==================================================
# # EXOTEL CALL TRIGGER (VOICEBOT)
# # ==================================================
# def trigger_exotel_call(phone: str, pitch: str):
#     url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Calls/connect.json"

#     payload = {
#         "From": phone,
#         "CallerId": EXOTEL_TO_NUMBER,
#         "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
#     }

#     r = requests.post(
#         url,
#         auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
#         data=payload,
#         timeout=10
#     )
#     r.raise_for_status()

#     call_sid = r.json()["Call"]["Sid"]

#     # ✅ store clean pitch
#     CALLSID_TO_PITCH[call_sid] = pitch.strip().strip('"')

#     logger.info(f"📞 Call placed → {phone} | CallSid={call_sid}")

# # ==================================================
# # HOME
# # ==================================================
# @app.get("/")
# def home():
#     return HTMLResponse(open("upload.html").read())

# # ==================================================
# # CSV UPLOAD
# # ==================================================
# @app.post("/upload-csv")
# async def upload_csv(file: UploadFile = File(...)):
#     content = await file.read()
#     reader = csv.DictReader(content.decode().splitlines())

#     for row in reader:
#         phone = row.get("phone_number")
#         pitch = row.get("pitch")

#         if not phone or not pitch:
#             continue

#         clean_pitch = pitch.strip().strip('"')

#         logger.info(f"📄 Loaded pitch for {phone}: {clean_pitch[:60]}...")

#         trigger_exotel_call(phone.strip(), clean_pitch)
#         await asyncio.sleep(1)

#     return {"status": "success"}

# # ==================================================
# # SARVAM TTS
# # ==================================================
# def sarvam_tts(text: str) -> bytes:
#     if not text or not text.strip():
#         raise ValueError("Empty TTS text")

#     r = requests.post(
#         "https://api.sarvam.ai/text-to-speech",
#         headers={
#             "api-subscription-key": SARVAM_API_KEY,
#             "Content-Type": "application/json"
#         },
#         json={
#             "text": text,
#             "target_language_code": "en-IN",
#             "speech_sample_rate": "16000"
#         },
#         timeout=15
#     )
#     r.raise_for_status()
#     return base64.b64decode(r.json()["audios"][0])

# async def send_pcm(ws: WebSocket, pcm: bytes):
#     for i in range(0, len(pcm), MIN_CHUNK_SIZE):
#         await ws.send_text(json.dumps({
#             "event": "media",
#             "media": {
#                 "payload": base64.b64encode(pcm[i:i+MIN_CHUNK_SIZE]).decode()
#             }
#         }))
#         await asyncio.sleep(0)

# # ==================================================
# # VOICEBOT WEBSOCKET (CORRECT)
# # ==================================================
# @app.websocket("/ws")
# async def ws_handler(ws: WebSocket):
#     await ws.accept()
#     logger.info("🎧 Voicebot connected")

#     call_sid = None
#     pitch_sent = False

#     try:
#         while True:
#             msg = await ws.receive_text()
#             data = json.loads(msg)
#             event = data.get("event")

#             # ✅ START EVENT
#             if event == "start":
#                 call_sid = data["start"]["call_sid"]
#                 logger.info(f"☎️ CallSid={call_sid}")
#                 continue

#             # ✅ PLAY PITCH ON FIRST MEDIA
#             if event == "media" and not pitch_sent:
#                 pitch = CALLSID_TO_PITCH.get(
#                     call_sid,
#                     "Hello, this is Rupeek personal loan assistant."
#                 )

#                 logger.info(f"🗣 Playing pitch")

#                 pcm = await asyncio.to_thread(sarvam_tts, pitch)
#                 await send_pcm(ws, pcm)

#                 pitch_sent = True
#                 continue

#             # ✅ STOP EVENT
#             if event == "stop":
#                 logger.info("📴 Call ended")
#                 break

#     except WebSocketDisconnect:
#         logger.info("🔌 Voicebot disconnected")

#     except Exception as e:
#         logger.error(f"❌ Voicebot error: {e}")

# # ==================================================
# # START
# # ==================================================
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=PORT)


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
from fastapi.responses import JSONResponse
import uvicorn
from openai import OpenAI

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_TO_NUMBER = os.getenv("EXOTEL_TO_NUMBER")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# --------------------------------------------------
# AUDIO
# --------------------------------------------------
SAMPLE_RATE = 16000
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebot")

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI()

# --------------------------------------------------
# IN-MEMORY STATE
# --------------------------------------------------
CALL_STATE = {}  # call_id → state

STEPS = [
    "Step 1: Download the Rupeek app from Play Store.",
    "Step 2: Complete basic KYC.",
    "Step 3: Select loan amount and get instant disbursal."
]

FAQS = {
    "interest": "The interest rate starts from ten percent per annum.",
    "repayment": "Repayment happens automatically every month.",
    "limit": "Your loan limit is pre-approved and visible in the app."
}

# --------------------------------------------------
# EXOTEL DIAL (POSTMAN CALLS THIS)
# --------------------------------------------------
@app.post("/dial")
def dial(payload: dict):
    phone = payload["phone"]

    r = requests.post(
        f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Calls/connect.json",
        auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data={
            "From": phone,
            "CallerId": EXOTEL_TO_NUMBER,
            "Url": "http://my.exotel.com/rupeekfintech13/exoml/start_voice/1105077"
        }
    )

    r.raise_for_status()
    call_sid = r.json()["Call"]["Sid"]
    CALL_STATE[call_sid] = {"step": -1}

    logger.info(f"📞 Dialed {phone} | CallSid={call_sid}")
    return JSONResponse({"status": "calling", "callSid": call_sid})

# --------------------------------------------------
# UTILS
# --------------------------------------------------
def pcm_to_wav(pcm):
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

def sarvam_stt(pcm):
    wav = pcm_to_wav(pcm)
    r = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": SARVAM_API_KEY},
        files={"file": ("audio.wav", wav)},
        data={"language_code": "en-IN"}
    )
    return r.json().get("transcript", "")

def sarvam_tts(text):
    r = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": SARVAM_API_KEY},
        json={
            "text": text,
            "target_language_code": "en-IN",
            "speech_sample_rate": "16000"
        }
    )
    return base64.b64decode(r.json()["audios"][0])

async def send_pcm(ws, pcm):
    for i in range(0, len(pcm), MIN_CHUNK_SIZE):
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {"payload": base64.b64encode(pcm[i:i+MIN_CHUNK_SIZE]).decode()}
        }))

# --------------------------------------------------
# OPENAI INTENT
# --------------------------------------------------
def classify_intent(text):
    prompt = f"""
User said: "{text}"

Classify intent strictly as one of:
yes, no, next, repeat, done, help, faq
Return only intent.
"""
    r = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return r.output_text.strip().lower()

# --------------------------------------------------
# WEBSOCKET (VOICEBOT)
# --------------------------------------------------
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    logger.info("🎧 Call connected")

    buffer, speech, silence = b"", b"", 0
    call_sid = None

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            event = data.get("event")

            if event == "start":
                call_sid = data.get("callSid")
                greeting = "Hello! Are you interested in a Rupeek personal loan?"
                pcm = sarvam_tts(greeting)
                await send_pcm(ws, pcm)

            if event != "media":
                continue

            chunk = base64.b64decode(data["media"]["payload"])
            buffer += chunk

            if len(buffer) < MIN_CHUNK_SIZE:
                continue

            frame, buffer = buffer[:MIN_CHUNK_SIZE], buffer[MIN_CHUNK_SIZE:]

            avg = sum(abs(int.from_bytes(frame[i:i+2], "little", signed=True))
                      for i in range(0, len(frame), 2)) / (len(frame)//2)

            if avg > SPEECH_THRESHOLD:
                speech += frame
                silence = 0
            else:
                silence += 1

            if silence >= SILENCE_CHUNKS and speech:
                text = sarvam_stt(speech)
                speech = b""

                intent = classify_intent(text)
                state = CALL_STATE.get(call_sid, {"step": -1})

                if intent == "no":
                    reply = "Thank you for your time. Goodbye!"
                    await send_pcm(ws, sarvam_tts(reply))
                    await ws.close()
                    return

                if intent == "yes" or intent == "next":
                    state["step"] += 1
                    if state["step"] < len(STEPS):
                        reply = STEPS[state["step"]]
                    else:
                        reply = "Process completed. Thank you!"
                        await send_pcm(ws, sarvam_tts(reply))
                        await ws.close()
                        return

                elif intent == "repeat":
                    reply = STEPS[state["step"]]

                elif intent == "help":
                    logger.warning(f"🚨 Human help needed: {call_sid}")
                    reply = "I will connect you to our team shortly."
                    await send_pcm(ws, sarvam_tts(reply))
                    await ws.close()
                    return

                else:
                    reply = "Please say yes, next, repeat, or no."

                CALL_STATE[call_sid] = state
                await send_pcm(ws, sarvam_tts(reply))

    except WebSocketDisconnect:
        logger.info("🔌 Call disconnected")

# --------------------------------------------------
# START
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
