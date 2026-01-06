import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _must(name: str) -> str:
    val = os.getenv(name)
    if not val:
        # Fallback to os.environ for Render
        if name in os.environ:
            return os.environ[name]
        raise RuntimeError(f"Missing required env var: {name}")
    return val

@dataclass(frozen=True)
class Settings:
    # Server
    public_hostname: str = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("PUBLIC_HOSTNAME") or "localhost:8000"
    port: int = int(os.getenv("PORT", "8000"))
    
    # --- THIS WAS MISSING OR MISNAMED ---
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # ------------------------------------

    # Exotel
    exotel_account_sid: str = _must("EXOTEL_ACCOUNT_SID")
    exotel_api_key: str = _must("EXOTEL_API_KEY")
    exotel_api_token: str = _must("EXOTEL_API_TOKEN")
    exotel_subdomain: str = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")

    # Outbound defaults
    exotel_from_number: str = os.getenv("EXOTEL_FROM_NUMBER", "")
    exotel_to_number: str = os.getenv("EXOTEL_TO_NUMBER", "")
    exotel_exoml_url: str = os.getenv("EXOTEL_EXOML_URL", "")

    # AI / Sarvam
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")

settings = Settings()
