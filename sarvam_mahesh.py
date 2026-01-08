import os
import base64
import requests
import tempfile
import time
from dotenv import load_dotenv
import sounddevice as sd
from scipy.io.wavfile import write
import simpleaudio as sa

load_dotenv()

# === Environment Variables ===
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en-IN")

# TTS Settings (Use only valid speakers)
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
TTS_CODEC = os.getenv("SARVAM_TTS_CODEC", "wav")

# STT Settings
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
STT_LANG = os.getenv("SARVAM_STT_LANG", "en-IN")
STT_CODEC = os.getenv("SARVAM_STT_CODEC", "wav")

# === Helper Functions ===
def text_to_speech(text):
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
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        audio_base64 = resp.json().get("audios")[0]
        audio_bytes = base64.b64decode(audio_base64)
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(audio_bytes)
        tmp_file.close()
        return tmp_file.name
    except requests.RequestException as e:
        print(f"TTS request failed: {e} - {getattr(e.response, 'text', '')}")
        return None

def play_audio(file_path):
    try:
        wave_obj = sa.WaveObject.from_wave_file(file_path)
        play_obj = wave_obj.play()
        play_obj.wait_done()
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def record_audio(duration=5, fs=16000):
    print("🎙 Listening...")
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16', blocking=True)
    sd.wait()
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    write(tmp_file.name, fs, audio)  # Proper PCM16 WAV
    return tmp_file.name

def speech_to_text(audio_file):
    url = "https://api.sarvam.ai/speech-to-text"
    files = {'file': ('audio.wav', open(audio_file, 'rb'), 'audio/wav')}
    data = {
        "model": STT_MODEL,
        "language_code": STT_LANG,
        "input_audio_codec": STT_CODEC
    }
    headers = {"api-subscription-key": SARVAM_API_KEY}

    try:
        resp = requests.post(url, files=files, data=data, headers=headers)
        resp.raise_for_status()
        return resp.json().get("transcript", "")
    except requests.RequestException as e:
        print(f"STT request failed: {e} - {getattr(e.response, 'text', '')}")
        return ""
    finally:
        files['file'][1].close()
        if os.path.exists(audio_file):
            os.remove(audio_file)

def tts_and_play(text):
    audio_file = text_to_speech(text)
    if audio_file:
        play_audio(audio_file)

def get_user_response(duration=5):
    try:
        audio_file = record_audio(duration)
        transcript = speech_to_text(audio_file)
        if transcript.strip():
            print("User:", transcript)
            return transcript.lower()
        else:
            return input("Type user response (fallback): ").lower()
    except Exception as e:
        print("Error recording/recognizing:", e)
        return input("Type user response (fallback): ").lower()

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
    if any(x in user_response for x in ["yes", "interested", "sure", "ok"]):
        tts_and_play("Great! Kindly open the Rupeek app. I will guide you through the loan disbursal process.")
        for step in loan_steps:
            tts_and_play(step)
            resp = get_user_response()
            if any(x in resp for x in ["exit", "stop"]):
                tts_and_play("Okay, stopping the guidance. You can try again later.")
                break
        tts_and_play("Congratulations! You have completed the loan disbursal process.")
    else:
        tts_and_play("No worries! Have a nice day.")

if __name__ == "__main__":
    run_demo_call()
def get_user_response(duration=5):
    print("🎙 (Microphone disabled to prevent crash)")
    return input(">> Type your response here: ").lower()
