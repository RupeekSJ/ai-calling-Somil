import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file immediately
load_dotenv()

class Settings(BaseSettings):
    # App Config
    public_hostname: str = os.getenv("PUBLIC_HOSTNAME", "")
    # CRITICAL: This was missing and causing your crash in app.py
    log_level: str = os.getenv("LOG_LEVEL", "INFO") 

    # LLM Config (Gemini Only)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Exotel Config
    exotel_account_sid: str = os.getenv("EXOTEL_ACCOUNT_SID", "")
    exotel_subdomain: str = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
    exotel_api_key: str = os.getenv("EXOTEL_API_KEY", "")
    exotel_api_token: str = os.getenv("EXOTEL_API_TOKEN", "")

    # Outbound Call Defaults (Required for dialer.py)
    exotel_from_number: str = os.getenv("EXOTEL_FROM_NUMBER", "")
    exotel_to_number: str = os.getenv("EXOTEL_TO_NUMBER", "")
    exotel_exoml_url: str = os.getenv("EXOTEL_EXOML_URL", "")

    # Sarvam Config (TTS/STT)
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")

    # Validation
    def validate(self):
        if not self.exotel_api_key:
            raise ValueError("EXOTEL_API_KEY is missing")
        if not self.exotel_api_token:
            raise ValueError("EXOTEL_API_TOKEN is missing")
        if not self.gemini_api_key:
            print("WARNING: GEMINI_API_KEY is missing")
        if not self.sarvam_api_key:
            print("WARNING: SARVAM_API_KEY is missing")

settings = Settings()
settings.validate()
