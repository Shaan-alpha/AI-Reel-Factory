"""Module 2 — Approval (Telegram Morning Digest).

Contract:
    what it does : sends the day's pending ideas to Telegram with Approve/Reject buttons;
                   writes the operator's decision back to the ideas table.
    how to use   : `send_digest()` to push; `process_responses()` to apply taps (polling).
    depends on   : python-telegram-bot, src.db, src.config (TELEGRAM_BOT_TOKEN, _CHAT_ID).

This is the ONLY human step (rule 16: keep the human approval layer). Show each idea's
source link so the operator can sanity-check (docs/08 §6). Soft-cap at 4–5 approvals.

STATUS: stub.
"""
from __future__ import annotations


def send_digest() -> None:
    """Send pending ideas as a Morning Digest with inline Approve/Reject buttons."""
    raise NotImplementedError("approval.send_digest — see docs/02-implementation-plan.md §3")


def process_responses() -> int:
    """Poll for button taps, write approved/rejected to db. Return #approved today."""
    raise NotImplementedError("approval.process_responses — see docs/02-implementation-plan.md §3")
