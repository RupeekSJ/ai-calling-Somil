import json
import base64
import asyncio
import logging
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from config import settings
from sarvam_service import sarvam_client

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebot")

app = FastAPI()

# Change this part in app.py

@app.api_route("/", methods=["GET", "HEAD"])
async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "rupeek-voicebot"})


@app.get("/exotel/voicebot")
@app.post("/exotel/voicebot")
async def voicebot_init(request: Request):
    """
    1. Exotel calls this when call connects.
    2. We return XML to start the WebSocket stream.
    """
    host = request.headers.get("host", settings.public_hostname.replace("https://", "").replace("http://", ""))
    stream_url = f"wss://{host}/ws"
    
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting to AI.</Say>
    <Stream url="{stream_url}">
        <Parameter name="packetS" value="true" />
    </Stream>
</Response>
"""
    return Response(content=xml_response, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("✅ WS Connected")
    
    # BUFFER for user audio
    audio_buffer = bytearray()
    silence_frames = 0
    IS_LISTENING = False # toggle to know if we are waiting for user
    
    try:
        # --- STEP 1: PLAY GREETING ---
        greeting_text = "Namaste. This is your Rupeek assistant. How can I help you with your loan today?"
        
        # 1a. Get Audio from Sarvam
        audio_b64 = sarvam_client.text_to_speech(greeting_text)
        
        if audio_b64:
            # 1b. Send to Exotel
            media_msg = {
                "event": "media",
                "media": {
                    "payload": audio_b64,
                    "content_type": "audio/wav", 
                    "sample_rate": 8000
                }
            }
            await websocket.send_text(json.dumps(media_msg))
            logger.info("🔊 Greeting sent")
            IS_LISTENING = True # Now we expect user to reply
        
        # --- STEP 2: LISTEN LOOP ---
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            event = message.get("event")

            if event == "media":
                # This is a chunk of User Audio
                if IS_LISTENING:
                    chunk = base64.b64decode(message["media"]["payload"])
                    audio_buffer.extend(chunk)
            
            elif event == "stop":
                logger.info("Call ended")
                break
                
            # --- SIMPLE SILENCE LOGIC (Placeholder) ---
            # In a real app, you need VAD (Voice Activity Detection). 
            # For this demo, we can assume if the buffer gets big enough (~3 seconds), we process it.
            # 8000 Hz * 1 byte * 3 seconds = ~24000 bytes (mu-law is 1 byte/sample)
            
            if IS_LISTENING and len(audio_buffer) > 40000: # ~5 seconds of audio
                logger.info("⏳ Processing User Audio...")
                
                # 1. Transcribe
                user_text = sarvam_client.speech_to_text(bytes(audio_buffer))
                
                # 2. Clear buffer
                audio_buffer = bytearray()
                
                if user_text:
                    # 3. Simple AI Logic (Replace with LLM later)
                    response_text = f"I heard you say {user_text}. Let me check that for you."
                    
                    # 4. Speak Response
                    resp_audio = sarvam_client.text_to_speech(response_text)
                    if resp_audio:
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "media": {"payload": resp_audio, "content_type": "audio/wav", "sample_rate": 8000}
                        }))
                else:
                     logger.info("No speech detected or transcription failed.")

    except WebSocketDisconnect:
        logger.info("WS Disconnected")
    except Exception as e:
        logger.error(f"WS Error: {e}")
