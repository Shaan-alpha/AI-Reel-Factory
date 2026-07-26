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


def test_prefer_groq_tries_groq_first(monkeypatch):
    # prefer_groq=True must use Groq even when Gemini would also succeed (reserve Gemini RPD)
    monkeypatch.setattr(llm, "_gen_gemini", lambda *a, **k: "gemini-text")
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi", prefer_groq=True) == "groq-text"


def test_prefer_groq_still_falls_back_to_gemini(monkeypatch):
    # if Groq fails, prefer_groq must still fail over to Gemini (chain stays intact, rule 11)
    monkeypatch.setattr(llm, "_gen_groq", _raise("groq down"))
    monkeypatch.setattr(llm, "_gen_gemini", lambda *a, **k: "gemini-text")
    assert llm.generate("hi", prefer_groq=True) == "gemini-text"


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


def test_github_models_first_when_preferred(monkeypatch):
    monkeypatch.setenv("GH_MODELS_KEY", "fake_models_token")
    monkeypatch.setenv("PREFER_GH_MODELS", "true")
    monkeypatch.setattr(llm, "_gen_github_models", lambda *a, **k: "github-text")
    monkeypatch.setattr(llm, "_gen_gemini", lambda *a, **k: "gemini-text")
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi") == "github-text"


def test_github_models_is_opt_in_not_key_presence(monkeypatch):
    """A token alone must NOT enlist the provider: GITHUB_TOKEN shows up in Actions
    environments incidentally, and a doomed provider in the chain delays the real failover."""
    monkeypatch.setenv("GITHUB_TOKEN", "incidental_actions_token")
    monkeypatch.delenv("ENABLE_GH_MODELS", raising=False)
    monkeypatch.delenv("PREFER_GH_MODELS", raising=False)
    called = []
    monkeypatch.setattr(llm, "_gen_github_models",
                        lambda *a, **k: called.append(1) or "github-text")
    monkeypatch.setattr(llm, "_gen_gemini", _raise("gemini down"))
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")

    assert llm.generate("hi") == "groq-text"  # straight to Groq
    assert called == [], "GitHub Models was called without being opted in"


def test_github_models_enabled_sits_between_gemini_and_groq(monkeypatch):
    monkeypatch.setenv("GH_MODELS_KEY", "fake_models_token")
    monkeypatch.setenv("ENABLE_GH_MODELS", "true")
    monkeypatch.setattr(llm, "_gen_gemini", _raise("gemini down"))
    monkeypatch.setattr(llm, "_gen_github_models", lambda *a, **k: "github-text")
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("hi") == "github-text"


def test_github_models_posts_to_github_host_with_publisher_prefixed_model(monkeypatch):
    """The retired Azure preview host and a bare model name both fail on this API, so pin both."""
    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, payload=json)
        return _Resp()

    monkeypatch.setenv("GH_MODELS_KEY", "fake_models_token")
    monkeypatch.delenv("GH_MODEL", raising=False)
    monkeypatch.setattr(llm.requests, "post", _fake_post)

    assert llm._gen_github_models("hi", json=False, max_tokens=64) == "ok"
    assert seen["url"] == "https://models.github.ai/inference/chat/completions"
    assert seen["payload"]["model"] == "openai/gpt-4o-mini"
    assert seen["headers"]["Authorization"] == "Bearer fake_models_token"


def test_github_models_adds_publisher_prefix_to_bare_model(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("GH_MODELS_KEY", "k")
    monkeypatch.setenv("GH_MODEL", "gpt-4o")  # operator forgot the publisher
    monkeypatch.setattr(llm.requests, "post",
                        lambda url, **kw: (seen.update(kw["json"]), _Resp())[1])
    llm._gen_github_models("hi", json=False, max_tokens=8)
    assert seen["model"] == "openai/gpt-4o"


def test_github_models_never_uses_gh_pat(monkeypatch):
    """GH_PAT is the Telegram bot's Actions read+write token; this repo's Actions hold the
    YouTube/Supabase/Telegram secrets, so it must never leave for an inference endpoint."""
    monkeypatch.delenv("GH_MODELS_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_PAT", "ghp_actions_read_write")
    assert llm._github_key() is None
    assert llm._github_enabled() is False

