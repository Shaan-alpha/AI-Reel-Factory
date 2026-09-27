"""Module 2 — Approval (Telegram Morning Digest).

Contract:
    what it does : sends the day's pending ideas to Telegram with Approve/Reject buttons;
                   writes the operator's decision back to the ideas table.
    how to use   : `send_digest()` to push; `process_responses()` to apply taps (polling).
    depends on   : requests (Telegram Bot HTTP API), src.db, src.config.

This is the ONLY human step (rule 16: keep the human approval layer). Each idea shows its
source links so the operator can sanity-check (docs/08 §6). Three buttons: Approve (queue it),
Reject (bad idea), Pass (soft skip — not posted, but not a hard reject). Soft-cap at
APPROVAL_CAP (4-5) approvals to protect daily volume. We talk to the Bot HTTP API directly via
requests — no async framework — which suits a short polling script run by the production workflow.

Idempotency (rule 12): decisions write idea status; re-tapping just re-sets the same status.
Security: callbacks from any chat other than TELEGRAM_CHAT_ID are ignored.
"""
from __future__ import annotations

import html
import logging
import time
from urllib.parse import urlparse

import requests

from src import config, db

log = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 40  # HTTP timeout; must exceed the long-poll timeout below

_DECISION_TEXT = {
    "approved": "✅ Approved",
    "rejected": "❌ Rejected",
    "passed": "⏭️ Passed",
    "capped": "⚠️ Daily approval cap reached — not approved",
    "unknown": "Could not process that.",
    "stale": "Already decided — this idea is no longer waiting for a tap.",
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
        {"text": "⏭️ Pass", "callback_data": f"p:{idea_id}"},
    ]]}


# How many publishers the digest names before collapsing the rest into "+N more". The operator
# needs enough to see the idea is sourced from real outlets, not a wall of URLs to read.
_SOURCES_SHOWN = 3
# Every digest message is sent and edited with previews off: the preview card is the biggest
# thing in the chat, and it previews only the first link, which says nothing about the idea.
_NO_PREVIEW = {"is_disabled": True}


def _source_label(url: str) -> str:
    """'https://www.theguardian.com/world/…' -> 'theguardian.com'. Readable, never a raw URL."""
    host = urlparse(url if "://" in url else "http://" + url).netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    for prefix in ("www.", "m.", "amp."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return "Google News" if host == "news.google.com" else (host or "link")


def _format_sources(sources: list[str]) -> str:
    """One line: up to _SOURCES_SHOWN publishers as tappable names, then '+N more'.

    Each source used to get its own '🔗 <full URL>' line. Google News reader links run 249-884
    characters, and a digest idea carried up to 17 of them (2026-09-12), so one idea filled the
    screen. The full list still ships in the YouTube description; the digest only needs the
    publishers at a glance and a tap-through to check one.
    """
    firsts: dict[str, str] = {}  # label -> first URL from that publisher
    for s in sources:
        firsts.setdefault(_source_label(str(s)), str(s))
    if not firsts:
        return "📰 <b>no sources!</b>"
    shown = list(firsts.items())[:_SOURCES_SHOWN]
    links = " · ".join(f'<a href="{html.escape(u, quote=True)}">{html.escape(label)}</a>'
                       for label, u in shown)
    rest = len(sources) - len(shown)
    return f"📰 {links}" + (f" <i>+{rest} more</i>" if rest > 0 else "")


def _format_idea(idea: dict) -> str:
    """Compact HTML message body for one idea: title, hook, angle, then score + sources on ONE
    line. Sources stay tappable so the operator can still sanity-check one (docs/08 §6)."""
    def esc(x):
        return html.escape(str(x or ""))

    from src import scriptwriter  # local: the tone rule lives in ONE place (rule 7)

    score = idea.get("est_score")
    score_str = f"{float(score):.2f}" if score is not None else "—"
    # The sensitivity filter was prompt-only; a story about deaths or serious harm is now
    # flagged for the approver, who also learns it will be read in a serious tone.
    flag = ("⚠️ <i>Sensitive: deaths or serious harm. It will be written and read in a "
            "serious tone.</i>\n") if scriptwriter.tone_for(idea) == "somber" else ""
    return (
        f"{flag}<b>{esc(idea.get('title'))}</b>\n"
        f"<i>Hook:</i> {esc(idea.get('hook'))}\n"
        f"<i>Why it matters:</i> {esc(idea.get('angle'))}\n"
        f"⭐ {score_str}  {_format_sources(idea.get('sources') or [])}"
    )


def _utf16_len(text: str) -> int:
    """Telegram measures entity offsets in UTF-16 code units, not Python characters."""
    return len(text.encode("utf-16-le")) // 2


def _decided_message(label: str, msg: dict) -> dict:
    """editMessageText params that put the decision on top and KEEP the idea's formatting.

    Telegram hands the message back as plain `text` plus `entities` (bold, italic, links). This
    used to re-send that plain text with parse_mode=HTML, which (a) dropped every link and all
    formatting on the first tap and (b) failed outright — so the tap looked ignored — whenever
    the text held '&' or '<', e.g. a title like "AT&T" or "S&P 500". Re-sending the entities,
    shifted past the new label, keeps the message exactly as it was.
    """
    original = msg.get("text") or msg.get("caption") or ""
    prefix = f"{label}\n\n" if original else label
    shift = _utf16_len(prefix)
    entities = [{"type": "bold", "offset": 0, "length": _utf16_len(label)}]
    for ent in msg.get("entities") or msg.get("caption_entities") or []:
        if isinstance(ent, dict) and "offset" in ent:
            entities.append({**ent, "offset": int(ent["offset"]) + shift})
    return {"text": prefix + original, "entities": entities,
            "link_preview_options": _NO_PREVIEW}


def send_digest() -> int:
    """Send pending ideas as a Morning Digest with inline Approve/Reject buttons. Return #sent."""
    ideas = db.get_pending_ideas()
    if not ideas:
        log.info("approval: no pending ideas to send.")
        return 0
    chat = config.require("TELEGRAM_CHAT_ID")
    for idea in ideas:
        _api("sendMessage", chat_id=chat, text=_format_idea(idea), parse_mode="HTML",
             link_preview_options=_NO_PREVIEW, reply_markup=_keyboard(idea["id"]))
    log.info("approval: sent %d ideas to the digest.", len(ideas))
    return len(ideas)


def _apply_callback(action: str, idea_id: int, cap: int) -> str:
    """Apply one tap to the DB, enforcing the approval cap. Returns the decision label.

    Only a PENDING idea can be decided. An untapped digest message keeps live buttons after its
    run moves on (a timed-out idea is re-sent as a new message; aged-out ideas keep theirs), and
    a tap on one used to move a rejected or produced idea back to 'approved' — the stuck-approved
    state STATUS 2026-09-01 records for idea 223."""
    status = {"a": "approved", "r": "rejected", "p": "passed"}.get(action)
    if status is None:
        return "unknown"
    if status == "approved" and len(db.get_approved_ideas()) >= cap:
        return "capped"
    return status if db.set_idea_status(idea_id, status, from_status="pending") else "stale"


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
             **_decided_message(_DECISION_TEXT[decision], msg))
    return decision


def process_responses(max_seconds: int = 600, poll_timeout: int = 25, cap: int | None = None) -> int:
    """Poll for button taps, write approved/rejected to db. Return #approved this run.

    Stops early once no pending ideas remain (everything decided), else after max_seconds.
    """
    cap = cap if cap is not None else int(config.get("APPROVAL_CAP", "3"))
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
