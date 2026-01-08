import os
import base64
import requests
import tempfile
import subprocess  # <--- Added this to run macOS commands
from dotenv import load_dotenv

load_dotenv()

# === Environment Variables ===
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en-IN")

# TTS Settings
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
TTS_CODEC = os.getenv("SARVAM_TTS_CODEC", "wav")

# === Helper Functions ===

def text_to_speech(text):
    """Generates audio from text using Sarvam API."""
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "text": text,
        "target_language_code": DEFAULT_LANG,
        "speaker": TTS_SPEAKER,
        "model": TTS_MODEL,
        "output_audio_codec": TTS_CODEC
    }
    headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}

    try:
        print(f"🤖 Bot says: {text}") 
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        
        audio_base64 = resp.json().get("audios")[0]
        audio_bytes = base64.b64decode(audio_base64)
        
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(audio_bytes)
        tmp_file.close()
        return tmp_file.name
    except requests.RequestException as e:
        print(f"❌ TTS request failed: {e}")
        return None

def play_audio(file_path):
    """Plays audio using macOS native 'afplay' command."""
    try:
        # This calls the built-in macOS audio player
        # It is much more stable than simpleaudio/pyaudio
        subprocess.run(["afplay", file_path], check=True)
    except Exception as e:
        print(f"⚠️ Audio playback error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def tts_and_play(text):
    audio_file = text_to_speech(text)
    if audio_file:
        play_audio(audio_file)

def get_user_response(duration=5):
    """Gets user input via Text (Keyboard)."""
    print("👉 Type your response below:")
    return input(">> ").lower().strip()

# === Main Loan Process Flow ===
loan_steps = [
    "Open the Rupeek app.",
    "On the home screen, click the Cash banner.",
    "Check your pre-approved limit.",
    "Slide the slider to select the amount and tenure required.",
    "Tick the consent box to proceed.",
    "Add your bank account if not visible.",
    "Update your email id and address, then select proceed to mandate setup.",
    "Setup autopay for EMI deduction on 5th of each month.",
    "Once mandate setup is done, you will see the loan summary page.",
    "Review loan details and click 'Get Money Now'.",
    "Enter OTP sent to your mobile. Loan disbursal will be initiated within 30-40 seconds."
]

def run_demo_call():
    tts_and_play("Hi Mahesh, we have a pre-approved personal loan offer from Rupeek. Are you interested?")
    
    user_response = get_user_response()
    
    if any(x in user_response for x in ["yes", "interested", "sure", "ok", "yep", "yeah"]):
        tts_and_play("Great! Kindly open the Rupeek app. I will guide you through the loan disbursal process.")
        
        for step in loan_steps:
            tts_and_play(step)
            print("(Type 'next' to continue, or 'stop' to exit)")
            resp = get_user_response()
            
            if any(x in resp for x in ["exit", "stop", "no", "cancel"]):
                tts_and_play("Okay, stopping the guidance. You can try again later.")
                break
        else:
            tts_and_play("Congratulations! You have completed the loan disbursal process.")
    else:
        tts_and_play("No worries! Have a nice day.")

if __name__ == "__main__":
    run_demo_call()
