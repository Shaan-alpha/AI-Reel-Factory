"""Module 2 — Approval (Telegram Morning Digest).

Contract:
    what it does : sends the day's pending ideas to Telegram with Approve/Reject buttons;
                   writes the operator's decision back to the ideas table.
    how to use   : `send_digest()` to push; `process_responses()` to apply taps (polling).
    depends on   : requests (Telegram Bot HTTP API), src.db, src.config.

This is the ONLY human step (rule 16: keep the human approval layer). Each idea shows its
source links so the operator can sanity-check (docs/08 §6). Soft-cap at APPROVAL_CAP (4-5)
approvals to protect daily volume. We talk to the Bot HTTP API directly via requests — no
async framework — which suits a short polling script run by the production workflow.

Idempotency (rule 12): decisions write idea status; re-tapping just re-sets the same status.
Security: callbacks from any chat other than TELEGRAM_CHAT_ID are ignored.
"""
from __future__ import annotations

import html
import logging
import time

import requests

from src import config, db

log = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 40  # HTTP timeout; must exceed the long-poll timeout below

_DECISION_TEXT = {
    "approved": "✅ Approved",
    "rejected": "❌ Rejected",
    "capped": "⚠️ Daily approval cap reached — not approved",
    "unknown": "Could not process that.",
}


def _api(method: str, **params):
    """Call a Telegram Bot API method; return its `result`. Raises on transport/API error."""
    url = _BASE.format(token=config.require("TELEGRAM_BOT_TOKEN"), method=method)
    resp = requests.post(url, json=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {data.get('description', data)}")
    return data["result"]


def _keyboard(idea_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"a:{idea_id}"},
        {"text": "❌ Reject", "callback_data": f"r:{idea_id}"},
    ]]}


def _format_idea(idea: dict) -> str:
    """HTML message body for one idea, with clickable source links (operator sanity-check)."""
    def esc(x):
        return html.escape(str(x or ""))

    sources = idea.get("sources") or []
    src_lines = "\n".join(f"🔗 {esc(s)}" for s in sources) or "🔗 (no sources!)"
    score = idea.get("est_score")
    score_str = f"{float(score):.2f}" if score is not None else "—"
    return (
        f"<b>{esc(idea.get('title'))}</b>\n"
        f"<i>Hook:</i> {esc(idea.get('hook'))}\n"
        f"<i>Why it matters:</i> {esc(idea.get('angle'))}\n"
        f"<i>Score:</i> {score_str}\n\n"
        f"{src_lines}"
    )


def send_digest() -> int:
    """Send pending ideas as a Morning Digest with inline Approve/Reject buttons. Return #sent."""
    ideas = db.get_pending_ideas()
    if not ideas:
        log.info("approval: no pending ideas to send.")
        return 0
    chat = config.require("TELEGRAM_CHAT_ID")
    for idea in ideas:
        _api("sendMessage", chat_id=chat, text=_format_idea(idea), parse_mode="HTML",
             reply_markup=_keyboard(idea["id"]))
    log.info("approval: sent %d ideas to the digest.", len(ideas))
    return len(ideas)


def _apply_callback(action: str, idea_id: int, cap: int) -> str:
    """Apply one tap to the DB, enforcing the approval cap. Returns the decision label."""
    if action == "a":
        if len(db.get_approved_ideas()) >= cap:
            return "capped"
        db.set_idea_status(idea_id, "approved")
        return "approved"
    if action == "r":
        db.set_idea_status(idea_id, "rejected")
        return "rejected"
    return "unknown"


def _handle_update(update: dict, cap: int) -> str | None:
    """Process one getUpdates entry. Returns the decision label, or None if not for us."""
    cq = update.get("callback_query")
    if not cq:
        return None
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if str(chat_id) != str(config.require("TELEGRAM_CHAT_ID")):
        log.warning("approval: ignoring callback from unexpected chat %s", chat_id)
        return None

    action, _, sid = (cq.get("data") or "").partition(":")
    try:
        idea_id = int(sid)
    except ValueError:
        idea_id = None
    decision = _apply_callback(action, idea_id, cap) if idea_id is not None else "unknown"

    _api("answerCallbackQuery", callback_query_id=cq["id"], text=_DECISION_TEXT[decision])
    if msg.get("message_id"):
        _api("editMessageText", chat_id=chat_id, message_id=msg["message_id"],
             text=f"{_DECISION_TEXT[decision]}\n\n{msg.get('text', '')}", parse_mode="HTML")
    return decision


def process_responses(max_seconds: int = 600, poll_timeout: int = 25, cap: int | None = None) -> int:
    """Poll for button taps, write approved/rejected to db. Return #approved this run.

    Stops early once no pending ideas remain (everything decided), else after max_seconds.
    """
    cap = cap if cap is not None else int(config.get("APPROVAL_CAP", "5"))
    deadline = time.monotonic() + max_seconds
    offset = None
    approved = 0
    while time.monotonic() < deadline:
        if not db.get_pending_ideas():
            log.info("approval: all ideas decided.")
            break
        updates = _api("getUpdates", offset=offset, timeout=poll_timeout,
                       allowed_updates=["callback_query"])
        for up in updates:
            offset = up["update_id"] + 1
            if _handle_update(up, cap) == "approved":
                approved += 1
    log.info("approval: %d approved this run.", approved)
    return approved
