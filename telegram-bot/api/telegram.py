"""Telegram command bot — Vercel serverless webhook (stdlib only, zero deps).

A free, instant control surface for the AI Reel Factory. Telegram calls this function on every
message (webhook); it authenticates the operator's chat + a secret token, parses a command, and
acts. No always-on server, no polling — Vercel spins this up per request.

Commands (operator-only):
  /makeshort [n]  → start the GitHub make-short Action (n ideas, default 5) → you get the digest
  /today          → how many Shorts published today (IST) + their links
  /stats          → totals + today + the current top performer by views
  /pending        → ideas waiting for your approval in the digest
  /latest         → the last few published Short links
  /help           → this list

Env (set in Vercel project settings; never commit real values):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET, GH_PAT, GH_REPO,
  SUPABASE_URL, SUPABASE_KEY  (the sb_secret_… key)

Security: ignores any chat != TELEGRAM_CHAT_ID, and rejects requests whose
`X-Telegram-Bot-Api-Secret-Token` header != WEBHOOK_SECRET (set when registering the webhook).
Replies are best-effort; the function always 200s so Telegram doesn't retry-storm.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

IST = timezone(timedelta(hours=5, minutes=30))  # the channel + operator run on India time

HELP = (
    "<b>But It Matters — control bot</b>\n"
    "/makeshort [n] — start a batch (n ideas, default 5) → approve in the digest\n"
    "/today — Shorts published today (IST)\n"
    "/stats — totals + today + top performer\n"
    "/pending — ideas waiting for your approval\n"
    "/latest — last published links\n"
    "/help — this message"
)


# --- env -------------------------------------------------------------------------------

def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


# --- tiny stdlib HTTP ------------------------------------------------------------------

def _http(method: str, url: str, headers: dict | None = None, payload: dict | None = None,
          timeout: int = 15) -> tuple[int, str]:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# --- Telegram --------------------------------------------------------------------------

def tg_send(chat_id, text: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    try:
        _http("POST", f"https://api.telegram.org/bot{token}/sendMessage",
              {"Content-Type": "application/json"},
              {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True})
    except Exception:  # noqa: BLE001 — replying is best-effort
        pass


# --- GitHub (start the Action) ---------------------------------------------------------

def gh_dispatch_make_short(ideas: int, wait_min: int = 30) -> bool:
    """workflow_dispatch make-short.yml on main. True on success (HTTP 204)."""
    repo, pat = _env("GH_REPO"), _env("GH_PAT")
    if not (repo and pat):
        return False
    url = f"https://api.github.com/repos/{repo}/actions/workflows/make-short.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reel-factory-bot",
        "Content-Type": "application/json",
    }
    try:
        status, _ = _http("POST", url, headers,
                          {"ref": "main", "inputs": {"ideas": str(ideas), "wait_min": str(wait_min)}})
        return status == 204
    except Exception:  # noqa: BLE001
        return False


# --- Supabase (read state) -------------------------------------------------------------

def sb_get(path: str) -> list:
    base, key = _env("SUPABASE_URL"), _env("SUPABASE_KEY")
    if not (base and key):
        return []
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    status, body = _http("GET", f"{base}/rest/v1/{path}", headers)
    if status >= 300 or not body:
        return []
    try:
        data = json.loads(body)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _ist_today_start_utc_iso() -> str:
    """UTC ISO timestamp of the most recent IST midnight (start of 'today' for the operator)."""
    start_ist = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_ist.astimezone(timezone.utc).isoformat()


def _published_filter() -> str:
    return "platform=eq.youtube&external_id=not.is.null"


def posts_today() -> list:
    since = urllib.parse.quote(_ist_today_start_utc_iso(), safe="")
    return sb_get(f"posts?select=url,published_at&{_published_filter()}"
                  f"&published_at=gte.{since}&order=published_at.desc")


def posts_total() -> int:
    return len(sb_get(f"posts?select=id&{_published_filter()}"))


def latest_posts(n: int = 5) -> list:
    return sb_get(f"posts?select=url,published_at&{_published_filter()}"
                  f"&order=published_at.desc&limit={n}")


def top_performer() -> str | None:
    rows = sb_get("analytics?select=views,posts(scripts(title,ideas(title)))&order=views.desc&limit=1")
    for r in rows:
        try:
            script = r["posts"]["scripts"]
            title = (script.get("title") or "").strip() or script["ideas"]["title"]
            return f'"{title}" — {int(r.get("views") or 0):,} views'
        except (TypeError, KeyError):
            return None
    return None


def pending_ideas() -> list:
    rows = sb_get("ideas?select=title&status=eq.pending&order=est_score.desc&limit=10")
    return [r.get("title", "") for r in rows if r.get("title")]


# --- command parsing + dispatch (pure-ish; network fns above are monkeypatchable) ------

def parse_command(text: str | None) -> tuple[str | None, str]:
    """('/makeShort 5@Bot') → ('makeshort', '5'). Returns (None, '') for non-commands."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None, ""
    parts = text.split()
    cmd = parts[0].lstrip("/").split("@")[0].lower()  # drop a trailing @botname
    return cmd, " ".join(parts[1:]).strip()


def dispatch(cmd: str, arg: str) -> str:
    if cmd in ("start", "help"):
        return HELP

    if cmd == "makeshort":
        n = max(1, min(8, int(arg))) if arg.isdigit() else 5
        ok = gh_dispatch_make_short(n)
        return (f"🎬 Starting a batch of <b>{n}</b> ideas — the approval digest lands in ~1–2 min. "
                "Tap ✅ Make it on the ones you want."
                if ok else "⚠️ Couldn't start the Action — check <code>GH_PAT</code>/<code>GH_REPO</code>.")

    if cmd == "today":
        rows = posts_today()
        if not rows:
            return "📅 <b>Today (IST):</b> 0 Shorts so far. Send /makeshort to make some."
        links = "\n".join(f"• {r['url']}" for r in rows if r.get("url"))
        return f"📅 <b>Today (IST): {len(rows)} Short(s)</b>\n{links}"

    if cmd == "stats":
        total, today, top = posts_total(), len(posts_today()), top_performer()
        lines = [f"📊 <b>Channel stats</b>",
                 f"• Total published: <b>{total}</b>",
                 f"• Today (IST): <b>{today}</b>"]
        if top:
            lines.append(f"• Top performer: {top}")
        return "\n".join(lines)

    if cmd == "pending":
        titles = pending_ideas()
        if not titles:
            return "✅ No ideas waiting. Send /makeshort to generate a fresh batch."
        body = "\n".join(f"• {t}" for t in titles)
        return f"⏳ <b>{len(titles)} idea(s) awaiting approval:</b>\n{body}"

    if cmd == "latest":
        rows = latest_posts(5)
        if not rows:
            return "No Shorts published yet."
        links = "\n".join(f"• {r['url']}" for r in rows if r.get("url"))
        return f"🎬 <b>Latest Shorts</b>\n{links}"

    return "Unknown command. Send /help for the list."


def handle_update(update: dict) -> None:
    """Authorize the chat, parse a command, reply. Foreign chats are silently ignored."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    auth = _env("TELEGRAM_CHAT_ID")
    if auth and str(chat_id) != str(auth):
        return  # only the operator's chat is served
    cmd, arg = parse_command(msg.get("text"))
    if not cmd:
        return
    reply = dispatch(cmd, arg)
    if reply:
        tg_send(chat_id, reply)


# --- Vercel handler --------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, text: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):  # health check / webhook-set sanity
        self._reply(200, "reel-factory bot ok")

    def do_POST(self):
        secret = _env("WEBHOOK_SECRET")
        if secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            self._reply(401, "unauthorized")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            handle_update(json.loads(raw or b"{}"))
        except Exception:  # noqa: BLE001 — never 5xx at Telegram (it would retry-storm)
            pass
        self._reply(200, "ok")
