# Exotel Outbound Voicebot (Starter)

## What this is
- FastAPI server that supports Exotel Voicebot (dynamic handshake + WebSocket receiver).
- Outbound dial endpoint `POST /dial` to start a call.

## Setup
1. Copy `.env.example` to `.env` and fill values.
2. Install deps:
   - `pip install -r requirements.txt`
3. Run:
   - `uvicorn app:app --host 0.0.0.0 --port 8000`

## Important
- Your ExoML/Flow must include Exotel's Voicebot applet pointing to:
  `https://<your-domain>/exotel/voicebot`
  so Exotel can fetch `{ "url": "wss://<your-domain>/ws" }` and then open the WebSocket.
