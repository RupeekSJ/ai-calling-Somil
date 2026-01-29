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

# ==================================================
# ENV
# ==================================================
load_dotenv()
PORT = int(os.getenv("PORT", 10000))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ==================================================
# AUDIO CONFIG
# ==================================================
SAMPLE_RATE = 22050
MIN_CHUNK_SIZE = 3200
SPEECH_THRESHOLD = 500
SILENCE_CHUNKS = 6

# ==================================================
# LOGGING (EXTENSIVE)
# ==================================================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

log = logging.getLogger("VOICEBOT")
flow_log = logging.getLogger("FLOW")
stt_log = logging.getLogger("STT")
tts_log = logging.getLogger("TTS")
flag_log = logging.getLogger("FLAG")

# ==================================================
# FASTAPI
# ==================================================
app = FastAPI()

# ==================================================
# LANGUAGE CONFIG
# ==================================================
LANGUAGE = "en-IN"
VOICE = "shubh"

# ==================================================
# EXACT PITCH (UNCHANGED)
# ==================================================
PITCH = (
    "Hi, my name is Mahesh, calling from Rupeek. "
    "You have a pre approved personal loan at zero interest — "
    "means you do not have to pay any interest if you repay the amount within the same month. "
    "It works like a credit line. "
    "You can withdraw money whenever you need, and repay only what you use. "
    "You can even withdraw again every month with zero interest, as long as it is repaid within the month. "
    "The process is one hundred percent digital, with no income proof and no paperwork required. "
    "You can receive instant disbursal to your bank account in just sixty seconds. "
    "With timely repayments, you can boost your CIBIL score and unlock higher limits in future without any interest. "
    "This is a limited time offer. "
    "Are you interested?"
)

# ==================================================
# FAQ INTENTS (YOUR CONTENT)
# ==================================================
FAQS = [
    (
        ["loan amount", "eligible", "how much", "limit"],
        "The loan amount is personalized for each customer. "
        "You can check your approved limit in the Rupeek app under Click Cash."
    ),
    (
        ["miss payment", "miss repayment", "roi", "interest if miss"],
        "If the loan repayment is missed, the loan converts to EMI with interest as shown in the app."
    ),
    (
        ["zero interest", "0%", "really zero"],
        "Yes, there will be no interest if you repay before month end."
    ),
    (
        ["monthly emi", "emi amount"],
        "EMI depends on the tenure you select. The app shows the exact EMI amount."
    ),
    (
        ["processing fee", "pf", "gst"],
        "Zero interest applies to the amount you use if you repay within the same month. "
        "The processing fee is a one time standard charge for instant digital disbursal. "
        "In credit cards, similar costs are recovered through annual fees and high cash withdrawal charges."
    ),
    (
        ["app shows interest", "32%", "1.45"],
        "The app shows the standard ROI for EMI. "
        "If you repay by month end, you do not have to pay any interest."
    ),
    (
        ["repay date", "any date", "month end"],
        "You will be required to pay the amount by month end for zero interest."
    ),
    (
        ["two lakh", "thirty thousand", "limit reduced"],
        "Currently based on system checks, your eligible amount is thirty thousand. "
        "With timely repayments, your eligibility increases automatically in future."
    ),
]

# ==================================================
# STEP-BY-STEP PROCESS FLOW
# ==================================================
PROCESS_STEPS = [
    "Step one. Download the Rupeek app and log in using your registered mobile number.",
    "Step two. Go to Click Cash and check your pre approved loan limit.",
    "Step three. Enter the amount you want to withdraw and select repayment option.",
    "Step four. Complete digital verification and receive money instantly in your bank account."
]

# ==================================================
# AUDIO UTILS
# ==================================================
def is_speech(pcm: bytes) -> bool:
    total, count = 0, 0
    for i in range(0, len(pcm) - 1, 2):
        s = int.from_bytes(pcm[i:i+2], "little", signed=True)
        total += abs(s)
        count += 1
    avg = total / count if count else 0
    log.debug(f"Amplitude={avg}")
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

# ==================================================
# SARVAM STT
# ==================================================
def sarvam_stt(pcm: bytes) -> str:
    wav = pcm_to_wav(pcm)
    resp = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": SARVAM_API_KEY},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"language_code": LANGUAGE},
        timeout=20
    )
    stt_log.info(f"STT status={resp.status_code}")
    resp.raise_for_status()
    text = resp.json().get("transcript", "").strip()
    stt_log.info(f"STT transcript='{text}'")
    return text

# ==================================================
# SARVAM STREAMING TTS
# ==================================================
def tts_stream(text: str):
    tts_log.info(f"TTS → {text[:80]}")
    return requests.post(
        "https://api.sarvam.ai/text-to-speech/stream",
        headers={
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "text": text,
            "target_language_code": LANGUAGE,
            "speaker": VOICE,
            "model": "bulbul:v3-beta",
            "speech_sample_rate": 22050,
            "pace": 1.05,
            "temperature": 0.6,
            "output_audio_codec": "mp3",
            "enable_preprocessing": True
        },
        stream=True,
        timeout=20
    )

async def send_audio(ws, stream):
    for chunk in stream.iter_content(chunk_size=8192):
        if chunk:
            await ws.send_text(json.dumps({
                "event": "media",
                "media": {"payload": base64.b64encode(chunk).decode()}
            }))
            await asyncio.sleep(0)

# ==================================================
# INTENT MATCHER
# ==================================================
def match_faq(text: str):
    text = text.lower()
    for keys, answer in FAQS:
        if any(k in text for k in keys):
            return answer
    return None

# ==================================================
# WEBSOCKET VOICEBOT
# ==================================================
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    log.info("📞 CALL CONNECTED")

    buffer = b""
    speech_buffer = b""
    silence_count = 0
    retries = 0
    step_index = 0
    stage = "PITCH"

    try:
        while True:
            msg = await ws.receive()
            if "text" not in msg:
                continue

            data = json.loads(msg["text"])
            event = data.get("event")

            # ---- PLAY PITCH ----
            if event == "start" and stage == "PITCH":
                flow_log.info("Playing pitch")
                await send_audio(ws, tts_stream(PITCH))
                stage = "INTEREST"
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
                speech_buffer += frame
                silence_count = 0
            else:
                silence_count += 1

            if silence_count >= SILENCE_CHUNKS and speech_buffer:
                user_text = await asyncio.to_thread(sarvam_stt, speech_buffer)
                speech_buffer = b""
                silence_count = 0

                log.info(f"USER SAID → {user_text}")

                if not user_text:
                    retries += 1
                elif "no" in user_text.lower():
                    await send_audio(ws, tts_stream("Thank you for your time. Have a great day."))
                    break
                elif "yes" in user_text.lower():
                    stage = "PROCESS"
                    step_index = 0
                    await send_audio(ws, tts_stream(PROCESS_STEPS[step_index]))
                elif stage == "PROCESS":
                    if "next" in user_text.lower():
                        step_index += 1
                        if step_index < len(PROCESS_STEPS):
                            await send_audio(ws, tts_stream(PROCESS_STEPS[step_index]))
                        else:
                            await send_audio(ws, tts_stream("You are all set. Thank you for choosing Rupeek."))
                            break
                    elif "repeat" in user_text.lower():
                        await send_audio(ws, tts_stream(PROCESS_STEPS[step_index]))
                else:
                    faq = match_faq(user_text)
                    if faq:
                        await send_audio(ws, tts_stream(faq))
                        retries = 0
                    else:
                        retries += 1

                if retries >= 3:
                    flag_log.warning("Human intervention required")
                    await send_audio(
                        ws,
                        tts_stream(
                            "Sorry, I am unable to understand. "
                            "Our representative will connect with you shortly."
                        )
                    )
                    break

                await asyncio.sleep(0.8)

    except WebSocketDisconnect:
        log.info("🔌 CALL DISCONNECTED")

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
