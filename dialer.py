import requests
from requests.auth import HTTPBasicAuth
from config import settings

def make_outbound_call(
    to_number: str,
    from_number: str,
    exoml_url: str,
    call_type: str = "trans",
) -> dict:
    """
    Initiates an outbound call via Exotel Voice API.
    The ExoML URL must point to a call-flow that includes the Voicebot applet,
    otherwise your /exotel/voicebot and /ws will never get invoked.
    """
    if not (to_number and from_number and exoml_url):
        raise ValueError("to_number, from_number, and exoml_url are required")

    url = f"https://{settings.exotel_subdomain}/v1/Accounts/{settings.exotel_account_sid}/Calls/connect.json"

    payload = {
        "Caller": from_number,
        "CallType": call_type,
        "Destination": to_number,
        "Url": exoml_url,
    }

    resp = requests.post(
        url,
        data=payload,
        auth=HTTPBasicAuth(settings.exotel_api_key, settings.exotel_api_token),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()
