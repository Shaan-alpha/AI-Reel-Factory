"""One-time helper: generate a YouTube refresh token for headless uploads.

WHY: The cron pipeline uploads to YouTube without a browser. To do that it needs a
*refresh token* — a long-lived credential proving you authorized this app to upload to
your channel. You generate it ONCE here (in a browser), then store it as a secret.

PREREQS
  1. In Google Cloud Console you created an OAuth *Desktop app* client and downloaded
     its JSON (see docs/03-setup-guide.md §8). Save that file next to this script as
     `client_secret.json` (this name is gitignored).
  2. Install deps:  pip install google-auth-oauthlib google-api-python-client

RUN
    python tools/get_youtube_token.py
  A browser opens -> log in with the Google account that OWNS the @butitmatters channel
  -> approve. The script prints CLIENT_ID, CLIENT_SECRET, and REFRESH_TOKEN.

THEN
  Paste those three values into .env (and later into the cron repo's GitHub secrets):
    YOUTUBE_CLIENT_ID=...
    YOUTUBE_CLIENT_SECRET=...
    YOUTUBE_REFRESH_TOKEN=...

NOTE: If the consent screen is in "Testing" mode, refresh tokens can expire in ~7 days.
Set the OAuth consent screen to "In production" (publish app) for a long-lived token.
"""
from __future__ import annotations

import os
import sys

# Only the upload scope — least privilege.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main(client_secret_path: str = "client_secret.json") -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("Missing dep. Run: pip install google-auth-oauthlib google-api-python-client")

    if not os.path.exists(client_secret_path):
        sys.exit(
            f"Can't find {client_secret_path}. Download your OAuth *Desktop app* client JSON "
            "from Google Cloud Console and save it there. See docs/03-setup-guide.md §8."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    # access_type=offline + prompt=consent forces Google to return a refresh token.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        sys.exit(
            "No refresh token returned. Revoke prior access at "
            "https://myaccount.google.com/permissions and re-run, or ensure the consent "
            "screen is published."
        )

    print("\n=== Copy these into .env (and the cron repo's GitHub secrets) ===")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("================================================================\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
