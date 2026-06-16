"""List en-IN Chirp 3 HD voices so the operator can choose GOOGLE_TTS_VOICE.

Run: GOOGLE_TTS_API_KEY=... python tools/list_google_voices.py
(ASCII-safe output for the Windows console.)"""
import os
import sys

try:  # load local .env so the key is available when run on the dev machine (CI sets env directly)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import requests

KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
if not KEY:
    print("set GOOGLE_TTS_API_KEY first")
    sys.exit(1)

r = requests.get(
    "https://texttospeech.googleapis.com/v1/voices",
    params={"key": KEY, "languageCode": "en-IN"}, timeout=30,
)
if r.status_code != 200:
    print(f"FAIL: HTTP {r.status_code} - {r.text[:400]}")
    sys.exit(1)
voices = [v["name"] for v in r.json().get("voices", []) if "Chirp3" in v.get("name", "")]
print(f"OK: key works ({len(voices)} en-IN Chirp 3 HD voices)")
for name in sorted(voices):
    print(" -", name)
if not voices:
    print(" (none returned - check the API is enabled)")
