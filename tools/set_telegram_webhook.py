"""Register (or clear) the Telegram webhook for the control bot.

Points Telegram at the deployed Vercel function and sets the secret token that the function
checks on every request (so only Telegram, with the right secret, can reach it).

Usage (PowerShell):
    # set the webhook to your Vercel URL (reads TELEGRAM_BOT_TOKEN + WEBHOOK_SECRET from .env)
    python tools/set_telegram_webhook.py https://<your-project>.vercel.app/api/telegram
    python tools/set_telegram_webhook.py --info     # show current webhook status
    python tools/set_telegram_webhook.py --delete    # remove the webhook

WEBHOOK_SECRET: set the same value here and in the Vercel env. If absent, a note is printed —
set one (any random string) for security. Token/secret are read from the local .env (gitignored).
"""
from __future__ import annotations

import os
import sys
import urllib.request

# Load .env without a hard dependency (python-dotenv if present, else a tiny parser).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 — fall back to a minimal .env reader
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import json
import urllib.parse

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SECRET = os.environ.get("WEBHOOK_SECRET", "")


def _api(method: str, **params) -> dict:
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN not set (add it to .env).")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    if argv[0] == "--info":
        print(json.dumps(_api("getWebhookInfo"), indent=2))
        return
    if argv[0] == "--delete":
        print(_api("deleteWebhook"))
        return

    url = argv[0]
    params = {"url": url, "allowed_updates": json.dumps(["message"])}
    if SECRET:
        params["secret_token"] = SECRET
    else:
        print("WARNING: WEBHOOK_SECRET is empty - set one in .env AND Vercel for security.")
    resp = _api("setWebhook", **params)
    print(json.dumps(resp, indent=2))
    print("-> verify with: python tools/set_telegram_webhook.py --info")


if __name__ == "__main__":
    main(sys.argv[1:])
