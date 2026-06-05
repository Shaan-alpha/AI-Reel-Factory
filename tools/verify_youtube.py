"""Verify the YouTube OAuth creds in .env actually authenticate.

Run: python tools/verify_youtube.py

Confirms YOUTUBE_CLIENT_ID / SECRET / REFRESH_TOKEN can mint a fresh access token
(i.e. the refresh token is valid and not expired/revoked). Uses the upload-only scope
(least privilege), so it proves auth works — the channel read is best-effort.
"""
from __future__ import annotations

import os
import sys

# Allow running directly (`python tools/verify_youtube.py`) by putting the repo root on path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    missing = [k for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                           "YOUTUBE_REFRESH_TOKEN") if not config.get(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")

    creds = Credentials(
        token=None,
        refresh_token=config.require("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.require("YOUTUBE_CLIENT_ID"),
        client_secret=config.require("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    creds.refresh(Request())  # raises if the refresh token is bad
    print(f"OK: refresh token valid -> access token minted (expires {creds.expiry} UTC)")

    # Best-effort channel read (upload-only scope may not permit this — that's fine).
    try:
        from googleapiclient.discovery import build

        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if items:
            print(f"channel: {items[0]['snippet']['title']}")
    except Exception as e:  # noqa: BLE001 — diagnostic only
        print(f"(channel read unavailable with upload-only scope — expected: {type(e).__name__})")


if __name__ == "__main__":
    main()
