"""Diagnostic: can this environment reach Vertex AI grounded search, with no API key?

    python tools/verify_vertex.py

Proves the whole chain the pipeline depends on: credentials (ADC locally, Workload Identity
Federation in CI) -> Vertex AI -> Gemini with Google Search grounding -> real citation URLs.

Why it exists: this Google Cloud organization's policy blocks BOTH API keys and service-account
keys, so there is no credential to eyeball. A failure here is either "the runner never got a
token" or "the token cannot reach Vertex", and those need different fixes — so the two are
reported separately rather than as one opaque error.

Prints nothing secret: credentials are never rendered, only their source and the account.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import config, llm  # noqa: E402

_PROBE = "In one sentence, name a significant news story from India this week."


def main() -> int:
    os.environ.setdefault("GEMINI_USE_VERTEX", "true")
    project = config.get("GCP_PROJECT") or "(unset)"
    location = config.get("GCP_LOCATION", "global")
    print(f"GEMINI_USE_VERTEX : {llm._use_vertex()}")
    print(f"GCP_PROJECT       : {project}")
    print(f"GCP_LOCATION      : {location}")

    if not llm._use_vertex():
        print("\nVertex is off — set GEMINI_USE_VERTEX=true to exercise this path.")
        return 1
    if project == "(unset)":
        print("\n[FAIL] GCP_PROJECT is not set; Vertex cannot be addressed.")
        return 1

    # Step 1 — credentials. Separated from the API call so a token problem is never reported
    # as a Vertex problem.
    try:
        import google.auth

        creds, detected = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        who = getattr(creds, "service_account_email", None) or type(creds).__name__
        print(f"\ncredentials       : OK ({who}, project={detected})")
    except Exception as e:  # noqa: BLE001
        print(f"\n[FAIL] no usable credentials: {e}")
        print("       locally:  gcloud auth application-default login")
        print("       in CI:    the google-github-actions/auth step must run, and the job needs")
        print("                 `permissions: id-token: write`")
        return 1

    # Step 2 — the actual grounded call the pipeline makes.
    try:
        text, sources = llm.generate_grounded_with_sources(_PROBE, max_tokens=200)
    except Exception as e:  # noqa: BLE001
        print(f"\n[FAIL] Vertex grounded call failed: {str(e)[:300]}")
        print("       Check the service account holds roles/aiplatform.user on the project.")
        return 1

    domains = [s.get("domain") for s in sources if s.get("domain")]
    print(f"grounded call     : OK ({len(text)} chars)")
    print(f"real citations    : {domains[:5] or 'NONE'}")
    print(f"\n  {text.strip()[:160]}")

    if not domains:
        print("\n[WARN] The call succeeded but returned no citations. Grounding may not have")
        print("       engaged for this prompt; the credential path is fine.")
        return 0
    print("\n[PASS] Keyless Vertex grounding works end to end. The 20/day Developer-API ceiling")
    print("       no longer applies: Vertex allows 1,500 grounded requests/day free on 2.5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
