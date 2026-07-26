"""Render one script through each voice engine so the operator can pick by ear.

Run: python tools/compare_voices.py [out_dir]
Needs GOOGLE_TTS_API_KEY + GOOGLE_TTS_VOICE for Chirp, GEMINI_API_KEY for Gemini.

Why this exists: gemini-2.5-pro-preview-tts has NO free tier (~$1.27/month at 3 Shorts/day),
while gemini-2.5-flash-preview-tts is free on both input and output. Whether Pro's delivery is
actually worth it is a judgement about how the sarcasm LANDS -- so listen, don't take anyone's
word for it. The Chirp render is the current production sound, for reference.

Note the script below deliberately carries both tag families: [sarcastic] only does something on
the Gemini engines, [pause long] only on Chirp. Each engine strips what it cannot use.
(ASCII-safe output for the Windows console.)"""
import os
import sys

# Running "python tools/compare_voices.py" puts tools/ on sys.path, not the project root, so
# `src` would not import. Add the repo root explicitly so the documented invocation works.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # load local .env on the dev machine (CI sets env directly)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import voice  # noqa: E402 — must follow the sys.path fix above

SCRIPT = ("Another committee has been formed. [sarcastic] Groundbreaking. "
          "[pause long] Here's why it actually matters: the rules change in April, "
          "and your electricity bill is the one that moves.")

OUT = sys.argv[1] if len(sys.argv) > 1 else "voice_ab"
os.makedirs(OUT, exist_ok=True)

# (label, gemini model or None for the Chirp REST path)
CANDIDATES = [
    ("chirp", None),
    ("gemini-flash", "gemini-2.5-flash-preview-tts"),
    ("gemini-pro", "gemini-2.5-pro-preview-tts"),
]

print("script: %s\n" % SCRIPT)
results = []
for label, model in CANDIDATES:
    target = os.path.join(OUT, label)
    os.makedirs(target, exist_ok=True)
    try:
        if model is None:
            path, dur = voice._synthesize_google(SCRIPT, target)
        else:
            os.environ["GEMINI_TTS_MODEL"] = model
            path, dur = voice._synthesize_gemini(SCRIPT, target)
        print("OK   %-13s %5.1fs  %s" % (label, dur, path))
        results.append(label)
    except Exception as e:  # noqa: BLE001 — report and continue to the next candidate
        print("FAIL %-13s %s" % (label, str(e)[:160]))

if not results:
    print("\nNothing rendered. Check GOOGLE_TTS_API_KEY / GOOGLE_TTS_VOICE / GEMINI_API_KEY.")
    sys.exit(1)

print("\nListen to each, then set:")
print("  VOICE_ENGINE=gemini            (or leave 'google' to keep Chirp)")
print("  GEMINI_TTS_MODEL=<model>       (flash is free; pro is ~$1.27/mo at 3 Shorts/day)")
