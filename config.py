import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file immediately
load_dotenv()

def _must(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

class Settings:
    # App Config
    public_hostname: str = _must("PUBLIC_HOSTNAME")
    
    # Exotel Config
    exotel_account_sid: str = _must("EXOTEL_ACCOUNT_SID")
    exotel_subdomain: str = _must("EXOTEL_SUBDOMAIN")
    exotel_api_key: str = _must("EXOTEL_API_KEY")
    exotel_api_token: str = _must("EXOTEL_API_TOKEN")

settings = Settings()
