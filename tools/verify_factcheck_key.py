"""Diagnostic: does FACTCHECK_API_KEY actually give the fact-check gate its OWN quota?

    python tools/verify_factcheck_key.py

Free grounded search is 20 requests/day and is metered per **project**, not per key. So a second
key minted inside the SAME Google Cloud project shares the same 20 and buys nothing — and the
failure is silent: the gate keeps working right up until the shared budget is gone, then fails
open exactly as before. This spends ONE grounded request on each key and reports what each has
left, which is the only way to tell the two situations apart.

Prints nothing secret: keys are shown as a length and a 4-character tail only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import config, llm  # noqa: E402

_PROBE = "Reply with the single word: ok"


def _mask(key: str) -> str:
    return f"<{len(key)} chars, ...{key[-4:]}>" if key else "<unset>"


def _probe(label: str, api_key: str | None) -> str:
    """Spend one grounded request. Returns 'ok', 'exhausted', or an error summary."""
    try:
        llm.generate_grounded(_PROBE, max_tokens=64, api_key=api_key)
        return "ok"
    except Exception as e:  # noqa: BLE001 — this is a diagnostic; report, never raise
        text = str(e)
        if "429" in text or "RESOURCE_EXHAUSTED" in text:
            return "exhausted (429 — this project's 20/day grounded budget is spent)"
        return f"error: {text[:160]}"


def main() -> int:
    shared = (config.get("GEMINI_API_KEY") or "").strip()
    checker = (config.get("FACTCHECK_API_KEY") or "").strip()

    print(f"GEMINI_API_KEY     {_mask(shared)}")
    print(f"FACTCHECK_API_KEY  {_mask(checker)}")
    if not shared:
        print("\nGEMINI_API_KEY is not set — nothing to compare against.")
        return 1
    if not checker:
        print("\nFACTCHECK_API_KEY is not set, so the gate still shares one 20/day budget with")
        print("ideation and the scriptwriter. Set it in .env and as a repo secret.")
        return 1
    if checker == shared:
        print("\n[FAIL] The two keys are IDENTICAL — that isolates nothing.")
        return 1

    print("\nSpending one grounded request on each key ...\n")
    a = _probe("shared", None)
    b = _probe("checker", checker)
    print(f"  GEMINI_API_KEY     -> {a}")
    print(f"  FACTCHECK_API_KEY  -> {b}")

    if a == "ok" and b == "ok":
        print("\n[PASS] Both keys answered. Re-run this on a day the shared key is exhausted:")
        print("       if FACTCHECK_API_KEY still answers while GEMINI_API_KEY 429s, the gate")
        print("       genuinely has its own budget and the isolation is real.")
        return 0
    if a.startswith("exhausted") and b == "ok":
        print("\n[PASS] The shared budget is spent and the checker key still answers — that is")
        print("       exactly the isolation this is for. The gate can run when nothing else can.")
        return 0
    if a == "ok" and b.startswith("exhausted"):
        print("\n[WARN] The checker key is exhausted while the shared one is not. Either it was")
        print("       already used today, or it lives in a project whose budget is spent.")
        return 1
    if a.startswith("exhausted") and b.startswith("exhausted"):
        print("\n[WARN] BOTH are exhausted. If you have not used the new key today, it is almost")
        print("       certainly in the SAME Google Cloud project as the first — quota is metered")
        print("       per project. Create the key in a NEW project.")
        return 1
    print("\n[WARN] Inconclusive — see the errors above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
