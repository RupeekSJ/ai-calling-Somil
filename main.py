import json
import base64
import logging
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from config import settings
from sarvam_service import sarvam_client
from llm_service import llm_client  # <--- NEW IMPORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebot")

app = FastAPI()

@app.get("/exotel/voicebot")
@app.post("/exotel/voicebot")
async def voicebot_init(request: Request):
    host = request.headers.get("host", settings.public_hostname.replace("https://", "").replace("http://", ""))
    stream_url = f"wss://{host}/ws"
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream url="{stream_url}">
        <Parameter name="packetS" value="true" />
    </Stream>
</Response>"""
    return Response(content=xml_response, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("✅ WS Connected")
    
    audio_buffer = bytearray()
    IS_LISTENING = False 
    
    try:
        # 1. Greeting
        greeting = "Namaste. I am your Rupeek assistant. How can I help?"
        audio_b64 = sarvam_client.text_to_speech(greeting)
        if audio_b64:
            await websocket.send_text(json.dumps({
                "event": "media", 
                "media": {"payload": audio_b64, "content_type": "audio/wav", "sample_rate": 8000}
            }))
            IS_LISTENING = True

        # 2. Loop
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            event = message.get("event")

            if event == "media":
                if IS_LISTENING:
                    chunk = base64.b64decode(message["media"]["payload"])
                    audio_buffer.extend(chunk)
            
            elif event == "stop":
                break

            # Placeholder Silence Logic (~3-4 seconds)
            if IS_LISTENING and len(audio_buffer) > 40000:
                IS_LISTENING = False # Stop listening while processing
                logger.info("⏳ Processing...")
                
                # A. Transcribe (Sarvam)
                user_text = sarvam_client.speech_to_text(bytes(audio_buffer))
                audio_buffer = bytearray() # Clear buffer
                
                if user_text:
                    logger.info(f"🗣️ User: {user_text}")
                    
                    # B. Get AI Response (Gemini)
                    ai_text = llm_client.get_response(user_text)
                    logger.info(f"🤖 AI: {ai_text}")
                    
                    # C. Speak Response (Sarvam)
                    resp_audio = sarvam_client.text_to_speech(ai_text)
                    if resp_audio:
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "media": {"payload": resp_audio, "content_type": "audio/wav", "sample_rate": 8000}
                        }))
                
                IS_LISTENING = True # Resume listening

    except WebSocketDisconnect:
        logger.info("WS Disconnected")
