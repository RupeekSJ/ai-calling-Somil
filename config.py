import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file immediately
load_dotenv()

def _must(name: str) -> str:
    """Helper to ensure env var exists"""
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

class Settings(BaseSettings):
    # App Config
    public_hostname: str = os.getenv("PUBLIC_HOSTNAME", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Exotel Config
    exotel_account_sid: str = os.getenv("EXOTEL_ACCOUNT_SID", "")
    exotel_subdomain: str = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
    exotel_api_key: str = os.getenv("EXOTEL_API_KEY", "")
    exotel_api_token: str = os.getenv("EXOTEL_API_TOKEN", "")

    # --- NEW: Sarvam Config ---
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")
    
    # Validation
    def validate(self):
        if not self.exotel_api_key:
            raise ValueError("EXOTEL_API_KEY is missing")
        if not self.exotel_api_token:
            raise ValueError("EXOTEL_API_TOKEN is missing")
        if not self.sarvam_api_key:
            # We warn but don't crash yet, in case you are still setting it up
            print("WARNING: SARVAM_API_KEY is missing")

settings = Settings()
