"""Unit tests for the LLM failover logic (rule 11: the fallback chain must be tested).

These mock the two provider calls, so they need no API keys, no network, and no SDK
installed — they verify the orchestration in src.llm.generate in isolation (rule 7).
"""
from __future__ import annotations

import pytest

from src import llm


def _raise(msg):
    def _fn(*_args, **_kwargs):
        raise RuntimeError(msg)

    return _fn


def test_primary_used_when_gemini_ok(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini", lambda *a, **k: "gemini-text")
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi") == "gemini-text"


def test_failover_to_groq_on_gemini_error(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini", _raise("quota exceeded"))
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi") == "groq-text"


def test_failover_to_groq_on_empty_gemini(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini", lambda *a, **k: "   ")
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi") == "groq-text"


def test_raises_when_all_providers_fail(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini", _raise("gemini down"))
    monkeypatch.setattr(llm, "_gen_groq", _raise("groq down"))
    with pytest.raises(RuntimeError, match="all providers failed"):
        llm.generate("hi")


def test_generate_grounded_returns_text(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini_grounded", lambda prompt, *, max_tokens: "grounded")
    assert llm.generate_grounded("x") == "grounded"


def test_generate_grounded_raises_on_empty(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini_grounded", lambda prompt, *, max_tokens: "   ")
    with pytest.raises(RuntimeError, match="empty"):
        llm.generate_grounded("x")


def test_json_flag_threads_through(monkeypatch):
    captured = {}

    def fake_gemini(prompt, *, json, max_tokens):
        captured["json"] = json
        captured["max_tokens"] = max_tokens
        return '{"ok": true}'

    monkeypatch.setattr(llm, "_gen_gemini", fake_gemini)
    out = llm.generate("return JSON", json=True, max_tokens=256)
    assert out == '{"ok": true}'
    assert captured == {"json": True, "max_tokens": 256}
