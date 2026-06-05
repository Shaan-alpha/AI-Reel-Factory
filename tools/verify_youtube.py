"""Verify the YouTube OAuth creds in .env actually authenticate.

Run: python tools/verify_youtube.py

Confirms YOUTUBE_CLIENT_ID / SECRET / REFRESH_TOKEN can mint a fresh access token
(i.e. the refresh token is valid and not expired/revoked) AND prints the channel the
token is bound to, so you can confirm it's "But It Matters" and not your main channel.
Requires the token to have been generated with the youtube.readonly scope.
"""
from __future__ import annotations

import os
import sys

# Allow running directly (`python tools/verify_youtube.py`) by putting the repo root on path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


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

    # Confirm WHICH channel this token uploads to (needs youtube.readonly).
    try:
        from googleapiclient.discovery import build

        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if not items:
            print("channel: (none returned)")
            return
        title = items[0]["snippet"]["title"]
        expected = config.get("CHANNEL_NAME") or ""
        print(f"bound channel: {title!r}")
        if expected and expected.lower() in title.lower():
            print(f"  ✓ matches CHANNEL_NAME ({expected!r}) — correct channel")
        else:
            print(f"  ⚠ does NOT match CHANNEL_NAME ({expected!r}). If this is your main "
                  "channel, revoke + regenerate the token against But It Matters.")
    except Exception as e:  # noqa: BLE001 — diagnostic only
        print(f"(channel read failed — did you add the youtube.readonly scope? {type(e).__name__})")


if __name__ == "__main__":
    main()
