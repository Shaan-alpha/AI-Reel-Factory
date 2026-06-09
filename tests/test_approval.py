"""Tests for the approval module (Module 2).

The Telegram HTTP API and db are mocked, so these run with no network and no bot — they verify
message formatting, the keyboard, digest sending, cap enforcement, callback handling, and the
chat-id security check. A real digest send is gated behind TELEGRAM_LIVE_TEST=1.
"""
from __future__ import annotations

import os

import pytest

from src import approval


IDEA = {"id": 7, "title": "ISRO <reusable> rocket", "hook": "It lands itself.",
        "angle": "Cheaper launches", "est_score": 0.82,
        "sources": ["https://a.example", "https://b.example"]}


def _mock_api(monkeypatch):
    calls = []
    monkeypatch.setattr(approval, "_api", lambda method, **p: calls.append((method, p)) or [])
    return calls


# --- formatting ------------------------------------------------------------------------

def test_format_idea_escapes_and_lists_sources():
    body = approval._format_idea(IDEA)
    assert "&lt;reusable&gt;" in body          # HTML-escaped
    assert "https://a.example" in body and "https://b.example" in body
    assert "0.82" in body


def test_keyboard_encodes_action_and_id():
    kb = approval._keyboard(7)
    btns = kb["inline_keyboard"][0]
    assert [b["callback_data"] for b in btns] == ["a:7", "r:7", "p:7"]


# --- send_digest -----------------------------------------------------------------------

def test_send_digest_one_message_per_idea(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(approval.db, "get_pending_ideas", lambda: [IDEA, {**IDEA, "id": 8}])
    calls = _mock_api(monkeypatch)
    assert approval.send_digest() == 2
    assert all(m == "sendMessage" and "reply_markup" in p for m, p in calls)


def test_send_digest_empty_noop(monkeypatch):
    monkeypatch.setattr(approval.db, "get_pending_ideas", lambda: [])
    calls = _mock_api(monkeypatch)
    assert approval.send_digest() == 0 and calls == []


# --- cap enforcement -------------------------------------------------------------------

def test_apply_callback_approve_under_cap(monkeypatch):
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [])
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s: statuses.append((i, s)))
    assert approval._apply_callback("a", 7, cap=5) == "approved"
    assert statuses == [(7, "approved")]


def test_apply_callback_approve_at_cap_blocks(monkeypatch):
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [{}] * 5)  # already 5
    monkeypatch.setattr(approval.db, "set_idea_status",
                        lambda i, s: pytest.fail("should not write at cap"))
    assert approval._apply_callback("a", 7, cap=5) == "capped"


def test_apply_callback_reject(monkeypatch):
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s: statuses.append((i, s)))
    assert approval._apply_callback("r", 7, cap=5) == "rejected"
    assert statuses == [(7, "rejected")]


def test_apply_callback_pass(monkeypatch):
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s: statuses.append((i, s)))
    assert approval._apply_callback("p", 7, cap=5) == "passed"
    assert statuses == [(7, "passed")]  # soft skip, distinct from reject


# --- callback handling -----------------------------------------------------------------

def _update(chat_id="111", data="a:7"):
    return {"update_id": 1, "callback_query": {
        "id": "cb1", "data": data,
        "message": {"message_id": 50, "text": "ISRO rocket", "chat": {"id": int(chat_id)}}}}


def test_handle_update_approves_and_acks(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [])
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s: None)
    calls = _mock_api(monkeypatch)
    assert approval._handle_update(_update(), cap=5) == "approved"
    methods = [m for m, _ in calls]
    assert "answerCallbackQuery" in methods and "editMessageText" in methods


def test_handle_update_ignores_foreign_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(approval.db, "set_idea_status",
                        lambda i, s: pytest.fail("must not act on foreign chat"))
    calls = _mock_api(monkeypatch)
    assert approval._handle_update(_update(chat_id="999"), cap=5) is None
    assert calls == []


def test_handle_update_non_callback_returns_none():
    assert approval._handle_update({"update_id": 2, "message": {"text": "hi"}}, cap=5) is None


# --- gated live digest -----------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("TELEGRAM_LIVE_TEST") != "1",
                    reason="set TELEGRAM_LIVE_TEST=1 to send a real digest to your chat")
def test_live_send_digest():
    sent = approval.send_digest()
    assert sent >= 0
