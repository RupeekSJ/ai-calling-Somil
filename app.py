import base64
import json
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from config import settings
from dialer import make_outbound_call

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("voicebot")

app = FastAPI()

@app.get("/")
async def health():
    return {"status": "ok"}

# -------- Exotel Voicebot Handshake (Dynamic URL) --------
# Exotel expects: { "url": "wss://...." } when you configure an https endpoint. [web:67]
@app.api_route("/exotel/voicebot", methods=["GET", "POST"])
async def exotel_voicebot(request: Request):
    if request.method == "GET":
        return JSONResponse({"status": "ok", "message": "voicebot endpoint reachable"})

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if payload is not None:
        log.info("Exotel handshake payload: %s", json.dumps(payload, ensure_ascii=False)[:2000])
    else:
        log.warning("Exotel handshake: non-JSON payload")

    # Keep params short (Exotel has limits), so only pass what you need.
    # Also: hostname should be your PUBLIC domain (TLS), not request.url.hostname (can be internal). [web:67]
    wss_url = f"wss://{settings.public_hostname}/ws"
    return JSONResponse({"url": wss_url})

# -------- Optional: ExoML file (example placeholder) --------
# You can serve ExoML from here OR from Exotel dashboard.
# This is a placeholder; you must configure Voicebot applet in your ExoML/Flow.
@app.get("/exoml/outbound.xml")
async def outbound_exoml():
    # Keep it simple: return something valid so Exotel can fetch.
    # Replace with a real flow that includes Voicebot applet in Exotel.
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Connecting you to Rupeek voice assistant.</Say>
  <!-- Configure Voicebot applet in Exotel Flow/ExoML as per Exotel docs -->
  <Hangup/>
</Response>
"""
    return Response(content=xml, media_type="application/xml")

# -------- Outbound dial endpoint (recommended) --------
@app.post("/dial")
async def dial(body: Dict[str, Any]):
    """
    POST /dial
    {
      "to": "+91....",
      "from": "0....",
      "exoml_url": "https://....../exoml/outbound.xml"
    }
    """
    to_number = body.get("to") or settings.exotel_to_number
    from_number = body.get("from") or settings.exotel_from_number
    exoml_url = body.get("exoml_url") or settings.exotel_exoml_url

    result = make_outbound_call(
        to_number=to_number,
        from_number=from_number,
        exoml_url=exoml_url,
    )
    return {"ok": True, "exotel": result}

# -------- WebSocket: receive Exotel events --------
# Exotel sends JSON strings with events like Connected/Start/Media/DTMF/Stop. [web:67]
@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    log.info("WS connected")

    # For debugging: store raw audio bytes
    audio_bytes = bytearray()

    try:
        while True:
            msg_text = await ws.receive_text()
            try:
                evt = json.loads(msg_text)
            except Exception:
                log.warning("WS received non-JSON text: %s", msg_text[:200])
                continue

            event_type = (evt.get("event") or evt.get("type") or "").lower()

            if event_type in ("connected",):
                log.info("WS event: connected")

            elif event_type in ("start",):
                log.info("WS event: start | %s", json.dumps(evt, ensure_ascii=False)[:1000])

            elif event_type in ("dtmf",):
                log.info("WS event: dtmf | %s", json.dumps(evt, ensure_ascii=False)[:500])

            elif event_type in ("media",):
                media = evt.get("media") or {}
                b64 = media.get("payload")
                if b64:
                    chunk = base64.b64decode(b64)
                    audio_bytes.extend(chunk)
                if len(audio_bytes) and (len(audio_bytes) % (32000 * 5) == 0):
                    # periodic progress log (roughly depends on codec/chunking)
                    log.info("Collected audio bytes: %d", len(audio_bytes))

            elif event_type in ("stop",):
                log.info("WS event: stop | audio_bytes=%d", len(audio_bytes))
                break

            else:
                log.info("WS event: %s", json.dumps(evt, ensure_ascii=False)[:800])

    except WebSocketDisconnect:
        log.warning("WS disconnected")
    except Exception as e:
        log.exception("WS error: %s", e)
    finally:
        # write debug audio to disk (raw PCM most likely); later we’ll decode properly.
        try:
            with open("debug_audio.raw", "wb") as f:
                f.write(audio_bytes)
            log.info("Saved debug_audio.raw (%d bytes)", len(audio_bytes))
        except Exception as e:
            log.warning("Could not save debug audio: %s", e)

        await ws.close()
        log.info("WS closed")
