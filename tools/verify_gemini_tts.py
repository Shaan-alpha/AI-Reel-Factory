"""Diagnostic: can this environment voice the channel narrator on each Gemini TTS backend?

    python tools/verify_gemini_tts.py

The channel voice (Zubenelgenubi) lives only on Gemini TTS, and voice.py tries it on two
backends before falling back to Chirp: the Developer API (GEMINI_API_KEY, free) and Vertex AI
(Application Default Credentials locally, Workload Identity Federation in CI). This renders one
short line on each and reports OK or the exact failure, so a broken credential shows up here
rather than as a reel voiced by Chirp. Two short requests; nothing is published or stored.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import config, voice  # noqa: E402

# Production length on purpose: a 9-word line under the long style prompt made 3.1 return no
# audio and 2.5 read the style prompt aloud (measured 2026-09-28), which real 60-80 word scripts
# do not do. The check should test what production sends.
_LINE = ("The committee met again this week and, predictably, formed another committee. "
         "[pause] [serious] Here is why it actually matters: the rules it is supposed to write "
         "decide what your electricity bill looks like next spring, and nobody has started "
         "writing them yet. That delay has a cost, and you are the one who pays it.")


def _one(label: str, env: dict[str, str]) -> bool:
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        meta: dict = {}
        with tempfile.TemporaryDirectory() as tmp:
            _path, dur = voice._synthesize_gemini(_LINE, tmp, meta)
        print(f"[OK]   {label:<9} {meta.get('model')} ({dur:.1f}s)")
        return True
    except Exception as e:  # noqa: BLE001 — report, do not raise
        print(f"[FAIL] {label:<9} {str(e)[:300]}")
        return False
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    print(f"model: {config.get('GEMINI_TTS_MODEL', voice._GEMINI_TTS_PRIMARY)}   "
          f"voice: {config.get('GEMINI_TTS_VOICE', 'Zubenelgenubi')}")
    results = []
    if config.get("GEMINI_TTS_API_KEY") or config.get("GEMINI_API_KEY"):
        results.append(_one("developer", {"GEMINI_TTS_VERTEX_FALLBACK": "false"}))
    else:
        print("[SKIP] developer  no GEMINI_API_KEY")
    if config.get("GCP_PROJECT"):
        # Blank the key so only the Vertex attempts run.
        results.append(_one("vertex", {"GEMINI_API_KEY": "", "GEMINI_TTS_API_KEY": "",
                                       "GEMINI_USE_VERTEX": "true"}))
    else:
        print("[SKIP] vertex     no GCP_PROJECT")
    if results and all(results):
        print("\n[PASS] The channel voice renders on every configured backend.")
        return 0
    print("\n[FAIL] At least one backend cannot voice the channel narrator; see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
