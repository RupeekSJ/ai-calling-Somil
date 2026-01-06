import requests
from requests.auth import HTTPBasicAuth
from config import settings
import logging

# Initialize logger
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("voicebot")

def make_outbound_call(
    to_number: str,
    from_number: str,
    exoml_url: str
) -> dict:
    """
    Initiates an outbound call via Exotel Voice API.
    """
    if not (to_number and from_number and exoml_url):
        raise ValueError("to_number, from_number, and exoml_url are required")

    url = f"https://{settings.exotel_subdomain}/v1/Accounts/{settings.exotel_account_sid}/Calls/connect.json"
    
    payload = {
        "From": to_number,        # The customer number
        "CallerId": from_number,  # Your Exophone
        "Url": exoml_url,         # The logic URL
    }

    log.info(f"Initiating Exotel call: URL={url}, Payload={payload}")

    try:
        resp = requests.post(
            url,
            data=payload,
            auth=HTTPBasicAuth(settings.exotel_api_key, settings.exotel_api_token),
            timeout=20,
        )
        
        if not resp.ok:
            error_msg = f"❌ EXOTEL ERROR: {resp.status_code} - {resp.text}"
            log.error(error_msg)
            print(error_msg)
            resp.raise_for_status()

        return resp.json()

    except Exception as e:
        log.error(f"Failed to make outbound call: {e}")
        raise

# --- TEST BLOCK ---
if __name__ == "__main__":
    # 1. Update Customer Number
    CUSTOMER_NUMBER = "07908120920"
    EXOPHONE_NUMBER = "08069489493"
    
    # 2. Construct Full URL
    hostname = settings.public_hostname
    # Ensure https:// prefix
    if hostname and not hostname.startswith("http"):
        hostname = f"https://{hostname}"
        
    FLOW_URL = f"{hostname}/exotel/voicebot"

    print(f"\n📞 TEST: Dialing {CUSTOMER_NUMBER} via {EXOPHONE_NUMBER}...")
    print(f"🔗 Flow URL: {FLOW_URL}")
    
    try:
        response = make_outbound_call(CUSTOMER_NUMBER, EXOPHONE_NUMBER, FLOW_URL)
        print(f"\n✅ SUCCESS! Call SID: {response.get('Call', {}).get('Sid')}")
        print("Call initiated. Exotel will now hit your Render app at /exotel/voicebot")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
