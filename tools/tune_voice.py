"""Render the same script through several Gemini TTS voices so the operator can pick by ear.

Run: python tools/tune_voice.py [out_dir]
Needs GEMINI_API_KEY. Uses the FREE gemini-2.5-flash-preview-tts model only.

Why a separate tool from compare_voices.py: that one answers "which ENGINE" (Chirp vs Gemini),
this one answers "which VOICE and which style prompt" once you have settled on Gemini.

FREE-TIER BUDGET (rule 13). Measured 2026-07-27 for gemini-2.5-flash-preview-tts:
3 RPM / 10 RPD. So this paces calls ~21s apart and refuses to make more than MAX_CALLS in one
run, leaving room for the day's actual Shorts. Each Short costs 1 request.

Voice characteristics come from Google's speech-generation docs. Picked for DRY delivery --
"Even" and "Gravelly" and "Casual" suit deadpan far better than the current "Firm" default,
and Upbeat/Excitable/Lively voices are deliberately excluded as wrong for this channel.
(ASCII-safe output for the Windows console.)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import voice  # noqa: E402 — must follow the sys.path fix above

MAX_CALLS = 5          # stay well inside the 10 RPD free-tier ceiling
SECONDS_BETWEEN = 21   # 3 RPM ceiling -> at most one call per 20s

SCRIPT = ("Another committee has been formed. [sarcastic] Groundbreaking. "
          "[pause long] Here's why it actually matters: the rules change in April, "
          "and your electricity bill is the one that moves.")

# (label, voice_name, documented characteristic)
VOICES = [
    ("schedar", "Schedar", "Even - flattest affect, best theoretical fit for deadpan"),
    ("algenib", "Algenib", "Gravelly - dry, wry texture"),
    ("zubenelgenubi", "Zubenelgenubi", "Casual - the 'clever friend' register"),
    ("charon", "Charon", "Informative - news credibility with room to underplay"),
]

OUT = sys.argv[1] if len(sys.argv) > 1 else "voice_tune"
os.makedirs(OUT, exist_ok=True)

if len(VOICES) > MAX_CALLS:
    print("refusing to make %d calls (MAX_CALLS=%d, free tier is 10/day)" % (len(VOICES), MAX_CALLS))
    sys.exit(1)

print("style prompt in use:\n  %s\n" % voice._DEFAULT_STYLE_PROMPT)
print("script:\n  %s\n" % SCRIPT)

os.environ["GEMINI_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"  # free tier only
ok = 0
for i, (label, voice_name, why) in enumerate(VOICES):
    if i:
        time.sleep(SECONDS_BETWEEN)  # respect the 3 RPM ceiling
    target = os.path.join(OUT, label)
    os.makedirs(target, exist_ok=True)
    os.environ["GEMINI_TTS_VOICE"] = voice_name
    for attempt in (1, 2):  # a transient 500 should not cost a voice slot; retry ONCE only
        try:
            path, dur = voice._synthesize_gemini(SCRIPT, target)
            print("OK   %-15s %5.1fs  %-14s  %s" % (label, dur, voice_name, why))
            print("     %s" % path)
            ok += 1
            break
        except Exception as e:  # noqa: BLE001 — report and continue to the next voice
            msg = str(e)
            transient = " 500 " in msg or "INTERNAL" in msg or " 503 " in msg
            if attempt == 1 and transient:
                print("..   %-15s transient error; retrying once" % label)
                time.sleep(SECONDS_BETWEEN)
                continue
            print("FAIL %-15s %s" % (label, msg[:140]))
            break

print("\n%d/%d rendered. Listen, then set GEMINI_TTS_VOICE to the winner." % (ok, len(VOICES)))
if ok:
    print("Requests used: %d of the 10/day free-tier budget." % ok)
