import json
import base64
import logging
import requests
import g711  # pip install g711
from typing import Optional
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from config import settings
from sarvam_service import sarvam_client
from llm_service import llm_client

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("voicebot")

app = FastAPI()

# --- Data Models ---
class DialRequest(BaseModel):
    to: str
    from_: Optional[str] = None  # Maps to 'from' in JSON
    exoml_url: Optional[str] = None

    class Config:
        fields = {'from_': 'from'} # Allows "from": "..." in JSON

# --- 1. Health Check ---
@app.get("/")
async def health():
    return {"status": "ok", "service": "rupeek-voicebot"}

# --- 2. ExoML Instructions (Exotel reads this) ---
@app.get("/exoml")
@app.post("/exoml")
async def get_exoml(request: Request):
    """Returns XML instructing Exotel to connect to WebSocket."""
    host = request.headers.get("host") or settings.public_hostname
    host = host.replace("http://", "").replace("https://", "").strip("/")
    
    wss_url = f"wss://{host}/ws"
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}">
            <Parameter name="packetS" value="true" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=xml_content, media_type="application/xml")

# --- 3. Dial Endpoint (Trigger Call) ---
@app.post("/dial")
async def dial(request: DialRequest):
    """Initiates an outbound call via Exotel API."""
    sid = settings.exotel_sid
    api_key = settings.exotel_api_key
    api_token = settings.exotel_api_token
    subdomain = settings.exotel_subdomain  # e.g. "api.exotel.com"
    
    # Construct the Exotel API URL
    url = f"https://{api_key}:{api_token}@{subdomain}/v1/Accounts/{sid}/Calls/connect.json"
    
    # Determine which URL Exotel should fetch for instructions
    # If user provided one, use it. Otherwise, point to our own /exoml endpoint.
    host = settings.public_hostname.replace("http://", "https://") # Ensure HTTPS
    callback_url = request.exoml_url or f"{host}/exoml"

    payload = {
        "From": request.from_ or settings.exotel_from_number,
        "To": request.to,
        "Url": callback_url,
        "CallType": "trans" # Transactional call
    }
    
    logger.info(f"📞 Dialing {request.to} using callback: {callback_url}")
    
    try:
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
        return {"status": "success", "exotel_response": resp.json()}
    except Exception as e:
        logger.error(f"Dial Error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# --- 4. WebSocket (The Voice Conversation) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("✅ WS Connected")
    
    audio_buffer = bytearray()
    chunk_counter = 0
    IS_LISTENING = False 
    
    try:
        # A. Initial Greeting
        greeting = "Namaste. I am your Rupeek assistant. How can I help you today?"
        audio_b64 = sarvam_client.text_to_speech(greeting)
        
        if audio_b64:
            await websocket.send_text(json.dumps({
                "event": "media", 
                "media": {"payload": audio_b64, "content_type": "audio/wav"}
            }))
            IS_LISTENING = True

        # B. Main Loop
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            event = message.get("event")

            if event == "media":
                if IS_LISTENING:
                    # 1. Decode & Convert
                    payload_b64 = message["media"]["payload"]
                    mulaw_chunk = base64.b64decode(payload_b64)
                    pcm_chunk = g711.decode_ulaw(mulaw_chunk) # Mu-Law -> PCM
                    
                    # 2. Buffer
                    audio_buffer.extend(pcm_chunk)
                    chunk_counter += 1
                    
                    # 3. Detect Silence (Naive VAD: ~1.5 seconds)
                    if chunk_counter > 75: 
                        IS_LISTENING = False
                        logger.info("⏳ Processing Speech...")
                        
                        # 4. STT (Hearing)
                        user_text = sarvam_client.speech_to_text(bytes(audio_buffer))
                        audio_buffer = bytearray()
                        chunk_counter = 0
                        
                        if user_text:
                            logger.info(f"🗣️ User: {user_text}")
                            
                            # 5. LLM (Thinking)
                            ai_text = llm_client.get_response(user_text)
                            logger.info(f"🤖 AI: {ai_text}")
                            
                            # 6. TTS (Speaking)
                            resp_audio = sarvam_client.text_to_speech(ai_text)
                            if resp_audio:
                                # Stop user interruption
                                await websocket.send_text(json.dumps({"event": "clear"}))
                                await websocket.send_text(json.dumps({
                                    "event": "media",
                                    "media": {"payload": resp_audio, "content_type": "audio/wav"}
                                }))
                        else:
                            logger.info("🤷 No speech detected.")
                        
                        IS_LISTENING = True # Resume listening

            elif event == "stop":
                logger.info("🛑 Call Ended")
                break
            elif event == "connected":
                logger.info("🤝 Exotel Stream Connected")

    except WebSocketDisconnect:
        logger.info("🔌 WS Disconnected")
    except Exception as e:
        logger.error(f"🔥 WS Error: {e}")
