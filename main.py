import json
import base64
import logging
import g711  # <--- CRITICAL: Needed to convert phone audio
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.websockets import WebSocketDisconnect
from config import settings
from sarvam_service import sarvam_client
from llm_service import llm_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebot")

app = FastAPI()

@app.get("/exotel/voicebot")
@app.post("/exotel/voicebot")
async def voicebot_init(request: Request):
    # Ensure we get the raw hostname without protocol
    host = request.headers.get("host") or settings.public_hostname
    host = host.replace("http://", "").replace("https://", "").strip("/")
    
    stream_url = f"wss://{host}/ws"
    
    # Simple TwiML/ExoML response to start the stream
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}">
            <Parameter name="packetS" value="true" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=xml_response, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("✅ WS Connected")
    
    audio_buffer = bytearray()
    chunk_counter = 0
    IS_LISTENING = False 
    
    try:
        # 1. Greeting
        greeting = "Namaste. I am your Rupeek assistant. How can I help you today?"
        audio_b64 = sarvam_client.text_to_speech(greeting)
        if audio_b64:
            # Send initial audio
            await websocket.send_text(json.dumps({
                "event": "media", 
                "media": {"payload": audio_b64, "content_type": "audio/wav"}
            }))
            IS_LISTENING = True

        # 2. Main Loop
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            event = message.get("event")

            if event == "media":
                if IS_LISTENING:
                    # A. Decode Base64
                    payload_b64 = message["media"]["payload"]
                    mulaw_chunk = base64.b64decode(payload_b64)
                    
                    # B. Convert Mu-Law -> PCM (Crucial for Sarvam STT)
                    pcm_chunk = g711.decode_ulaw(mulaw_chunk)
                    
                    # C. Append to Buffer
                    audio_buffer.extend(pcm_chunk)
                    chunk_counter += 1
                    
                    # D. Silence/End-of-Speech Detection (Naive)
                    # 1 chunk ~ 20ms. 100 chunks ~ 2 seconds.
                    # Adjust '100' based on how fast you want it to respond.
                    if chunk_counter > 100: 
                        IS_LISTENING = False # Stop listening logic
                        logger.info("⏳ Processing Speech...")
                        
                        # E. Transcribe (Sarvam)
                        # We send the PCM bytes; sarvam_client should wrap this in a WAV container
                        user_text = sarvam_client.speech_to_text(bytes(audio_buffer))
                        
                        # Reset Buffer Immediately
                        audio_buffer = bytearray() 
                        chunk_counter = 0
                        
                        if user_text:
                            logger.info(f"🗣️ User: {user_text}")
                            
                            # F. Get AI Response (Gemini/LLM)
                            ai_text = llm_client.get_response(user_text)
                            logger.info(f"🤖 AI: {ai_text}")
                            
                            # G. Speak Response (Sarvam)
                            resp_audio = sarvam_client.text_to_speech(ai_text)
                            if resp_audio:
                                # Send 'clear' to stop any previous audio if user interrupted
                                await websocket.send_text(json.dumps({"event": "clear"}))
                                
                                await websocket.send_text(json.dumps({
                                    "event": "media",
                                    "media": {"payload": resp_audio, "content_type": "audio/wav"}
                                }))
                        else:
                            logger.info("🤷 No speech detected, listening again...")
                        
                        IS_LISTENING = True # Resume listening

            elif event == "stop":
                logger.info("🛑 Call Ended")
                break
            elif event == "connected":
                logger.info("🤝 Exotel Connected")

    except WebSocketDisconnect:
        logger.info("🔌 WS Disconnected")
    except Exception as e:
        logger.error(f"🔥 Error: {e}")
