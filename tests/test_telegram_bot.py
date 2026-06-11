"""Tests for the Telegram control bot (Vercel webhook function).

The function lives outside src/ (telegram-bot/api/telegram.py, deployed to Vercel), so we load
it by path. Network calls (Telegram/GitHub/Supabase) are monkeypatched — these verify command
parsing, dispatch, clamping, IST-date math, and the chat-authorization gate (rule 7: isolation).
"""
from __future__ import annotations

import importlib.util
import pathlib
from datetime import datetime, timezone

import pytest

_BOT_PATH = pathlib.Path(__file__).resolve().parents[1] / "telegram-bot" / "api" / "telegram.py"


@pytest.fixture()
def bot():
    spec = importlib.util.spec_from_file_location("reel_telegram_bot", _BOT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_command(bot):
    assert bot.parse_command("/makeshort 5") == ("makeshort", "5")
    assert bot.parse_command("/help@Ai_Reel_Factory_Bot") == ("help", "")
    assert bot.parse_command("/MakeShort") == ("makeshort", "")
    assert bot.parse_command("hello there") == (None, "")
    assert bot.parse_command("") == (None, "")


def test_ist_today_start_is_utc_midnight_ist(bot):
    iso = bot._ist_today_start_utc_iso()
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo == timezone.utc
    assert dt.astimezone(bot.IST).hour == 0  # it is IST midnight expressed in UTC


def test_dispatch_help_and_unknown(bot):
    assert "control bot" in bot.dispatch("help", "").lower()
    assert "unknown command" in bot.dispatch("frobnicate", "").lower()


def test_dispatch_makeshort_starts_action(bot, monkeypatch):
    captured = {}
    monkeypatch.setattr(bot, "gh_dispatch_make_short", lambda n: captured.setdefault("n", n) or True)
    msg = bot.dispatch("makeshort", "5")
    assert captured["n"] == 5 and "starting" in msg.lower()


def test_dispatch_makeshort_clamps_and_defaults(bot, monkeypatch):
    seen = []
    monkeypatch.setattr(bot, "gh_dispatch_make_short", lambda n: seen.append(n) or True)
    bot.dispatch("makeshort", "99")   # clamps to 8
    bot.dispatch("makeshort", "")     # defaults to 5
    bot.dispatch("makeshort", "x")    # non-numeric → default 5
    assert seen == [8, 5, 5]


def test_dispatch_makeshort_reports_failure(bot, monkeypatch):
    monkeypatch.setattr(bot, "gh_dispatch_make_short", lambda n: False)
    assert "couldn't start" in bot.dispatch("makeshort", "3").lower()


def test_handle_update_ignores_foreign_chat(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    sent = []
    monkeypatch.setattr(bot, "tg_send", lambda cid, text: sent.append((cid, text)))
    monkeypatch.setattr(bot, "dispatch", lambda *a: pytest.fail("should not dispatch foreign chat"))
    bot.handle_update({"message": {"chat": {"id": 999}, "text": "/help"}})
    assert sent == []


def test_handle_update_serves_authorized_chat(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    sent = []
    monkeypatch.setattr(bot, "tg_send", lambda cid, text: sent.append((cid, text)))
    bot.handle_update({"message": {"chat": {"id": 111}, "text": "/help"}})
    assert len(sent) == 1 and sent[0][0] == 111 and "control bot" in sent[0][1].lower()


def test_handle_callback_approves_authorized_chat(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(bot, "approved_count", lambda: 0)
    writes = []
    monkeypatch.setattr(bot, "set_idea_status", lambda i, s: writes.append((i, s)) or True)
    calls = []
    monkeypatch.setattr(bot, "tg_api", lambda method, payload: calls.append((method, payload)))

    bot.handle_update({"callback_query": {
        "id": "cb1", "data": "a:7",
        "message": {"message_id": 50, "text": "Idea text", "chat": {"id": 111}},
    }})

    assert writes == [(7, "approved")]
    assert [method for method, _ in calls] == ["answerCallbackQuery", "editMessageText"]
    assert calls[-1][1]["text"].startswith("Approved")
    assert calls[-1][1]["parse_mode"] == "HTML"


def test_handle_callback_ignores_foreign_chat(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(bot, "set_idea_status",
                        lambda *a, **k: pytest.fail("must not act on foreign callback"))
    monkeypatch.setattr(bot, "tg_api",
                        lambda *a, **k: pytest.fail("must not answer foreign callback"))

    bot.handle_update({"callback_query": {
        "id": "cb1", "data": "a:7",
        "message": {"message_id": 50, "text": "Idea text", "chat": {"id": 999}},
    }})
