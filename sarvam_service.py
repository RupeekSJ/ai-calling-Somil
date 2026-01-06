import requests
import base64
import json
from config import settings

class SarvamService:
    def __init__(self):
        self.api_key = settings.sarvam_api_key
        self.base_url = "https://api.sarvam.ai"

    def text_to_speech(self, text: str, language_code: str = "hi-IN") -> str:
        """
        Converts text to speech using Sarvam AI (Bulbul model).
        Returns: base64 encoded audio string (WAV/PCM 8kHz).
        """
        url = f"{self.base_url}/text-to-speech"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Exotel requires 8000Hz. 
        # 'wav' format usually works best as Exotel can decode the header.
        payload = {
            "inputs": [text],
            "target_language_code": language_code,
            "speaker": "meera",  # Options: meera, pavithra, maithili, etc.
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000, 
            "enable_preprocessing": True,
            "model": "bulbul:v1"
        }
        
        try:
            print(f"Generating TTS for: {text[:20]}...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if "audios" in data and len(data["audios"]) > 0:
                # Sarvam returns base64 string directly
                return data["audios"][0]
            return None
        except Exception as e:
            print(f"❌ Sarvam TTS Error: {e}")
            return None

    def speech_to_text(self, audio_bytes: bytes) -> str:
        """
        Transcribes audio bytes using Sarvam AI (Saarika model).
        Accepts a WAV file content as bytes.
        """
        url = f"{self.base_url}/speech-to-text"
        headers = {
            "api-subscription-key": self.api_key,
            # Content-Type is multipart/form-data, handled auto by requests if 'files' is used
        }
        
        # We must send a file-like object. 
        files = {
            'file': ('audio.wav', audio_bytes, 'audio/wav')
        }
        data = {
            'model': 'saarika:v2.5', # or saarika:v2
            'language_code': 'hi-IN', # or 'en-IN' if you want English
            'with_diarization': 'false'
        }

        try:
            print(f"Transcribing {len(audio_bytes)} bytes of audio...")
            response = requests.post(url, headers=headers, files=files, data=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            transcript = result.get("transcript", "")
            print(f"✅ Transcript: {transcript}")
            return transcript
        except Exception as e:
            print(f"❌ Sarvam STT Error: {e}")
            return ""

sarvam_client = SarvamService()
