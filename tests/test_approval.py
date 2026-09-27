"""Tests for the approval module (Module 2).

The Telegram HTTP API and db are mocked, so these run with no network and no bot — they verify
message formatting, the keyboard, digest sending, cap enforcement, callback handling, and the
chat-id security check. A real digest send is gated behind TELEGRAM_LIVE_TEST=1.
"""
from __future__ import annotations

import os
import re

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


def test_digest_sources_fit_on_one_line_however_many_there_are():
    """2026-09-12: one idea carried 17 sources, each on its own '🔗 <full URL>' line — Google News
    reader links run up to 884 characters — so a single idea filled the screen."""
    many = ([f"https://news.google.com/rss/articles/{'X' * 600}{i}?oc=5" for i in range(2)]
            + ["https://www.theguardian.com/world/2026/sep/11/houthis",
               "https://m.timesofindia.indiatimes.com/city/a.cms",
               "https://www.theguardian.com/world/2026/sep/12/houthis-2"]
            + [f"https://outlet{i}.example/story" for i in range(12)])
    body = approval._format_idea({**IDEA, "sources": many})

    assert body.count("<a href=") == 3, "at most three publishers are named"
    assert "+14 more" in body
    assert "📰" in body and body.count("\n") == 3, "title, hook, angle, then ONE score+sources line"
    assert ">Google News<" in body and ">theguardian.com<" in body
    visible = re.sub(r"<[^>]+>", "", body)
    assert len(visible) < 400 and "news.google.com/rss" not in visible


def test_digest_sources_escape_the_link_target():
    body = approval._format_idea({**IDEA, "sources": ['https://x.example/a?b=1&c="2"']})
    assert 'href="https://x.example/a?b=1&amp;c=&quot;2&quot;"' in body


def test_an_unsourced_idea_is_still_flagged_loudly():
    assert "no sources!" in approval._format_idea({**IDEA, "sources": []})


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
    assert all(p["link_preview_options"] == {"is_disabled": True} for _, p in calls), \
        "a preview card of the first link is the biggest thing in the chat and says nothing"


def test_send_digest_empty_noop(monkeypatch):
    monkeypatch.setattr(approval.db, "get_pending_ideas", lambda: [])
    calls = _mock_api(monkeypatch)
    assert approval.send_digest() == 0 and calls == []


# --- cap enforcement -------------------------------------------------------------------

def test_apply_callback_approve_under_cap(monkeypatch):
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [])
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s, **k: statuses.append((i, s)) or True)
    assert approval._apply_callback("a", 7, cap=5) == "approved"
    assert statuses == [(7, "approved")]


def test_apply_callback_approve_at_cap_blocks(monkeypatch):
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [{}] * 5)  # already 5
    monkeypatch.setattr(approval.db, "set_idea_status",
                        lambda i, s: pytest.fail("should not write at cap"))
    assert approval._apply_callback("a", 7, cap=5) == "capped"


def test_apply_callback_reject(monkeypatch):
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s, **k: statuses.append((i, s)) or True)
    assert approval._apply_callback("r", 7, cap=5) == "rejected"
    assert statuses == [(7, "rejected")]


def test_apply_callback_pass(monkeypatch):
    statuses = []
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s, **k: statuses.append((i, s)) or True)
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
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s, **k: True)
    calls = _mock_api(monkeypatch)
    assert approval._handle_update(_update(), cap=5) == "approved"
    methods = [m for m, _ in calls]
    assert "answerCallbackQuery" in methods and "editMessageText" in methods


def test_a_decision_keeps_the_idea_formatting(monkeypatch):
    """The edit re-sent Telegram's PLAIN text with parse_mode=HTML: links gone after one tap, and
    a 400 on any '&' or '<' (this very fixture's title) so the tap looked ignored."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [])
    monkeypatch.setattr(approval.db, "set_idea_status", lambda i, s, **k: True)
    calls = _mock_api(monkeypatch)
    up = _update()
    text = "ISRO <reusable> & rocket\n📰 isro.gov.in"
    at = len(text[: text.index("isro.gov")].encode("utf-16-le")) // 2  # 📰 is TWO units
    up["callback_query"]["message"].update(
        text=text,
        entities=[{"type": "text_link", "offset": at, "length": 11, "url": "https://isro.gov.in/x"}])

    approval._handle_update(up, cap=5)

    edit = next(p for m, p in calls if m == "editMessageText")
    assert "parse_mode" not in edit
    assert edit["text"] == "✅ Approved\n\nISRO <reusable> & rocket\n📰 isro.gov.in"
    link = next(e for e in edit["entities"] if e["type"] == "text_link")
    units = edit["text"].encode("utf-16-le")
    assert units[link["offset"] * 2:(link["offset"] + 11) * 2].decode("utf-16-le") == "isro.gov.in"


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


def test_a_tap_on_an_old_digest_cannot_revive_a_decided_idea(monkeypatch):
    """An untapped digest message keeps live buttons after its run moves on; a tap used to move
    a rejected or produced idea back to 'approved' (the stuck-approved state of idea 223)."""
    monkeypatch.setattr(approval.db, "get_approved_ideas", lambda: [])
    calls = []
    monkeypatch.setattr(approval.db, "set_idea_status",
                        lambda i, s, **k: calls.append(k) or False)  # not pending any more
    assert approval._apply_callback("a", 7, cap=5) == "stale"
    assert calls == [{"from_status": "pending"}]
