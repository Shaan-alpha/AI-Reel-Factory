"""Unit tests for the LLM failover logic (rule 11: the fallback chain must be tested).

These mock the two provider calls, so they need no API keys, no network, and no SDK
installed — they verify the orchestration in src.llm.generate in isolation (rule 7).
"""
from __future__ import annotations

import os

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
    monkeypatch.setattr(llm, "_gen_gemini_grounded",
                        lambda prompt, *, max_tokens, model=None: "grounded")
    assert llm.generate_grounded("x") == "grounded"


def test_generate_grounded_raises_on_empty(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini_grounded",
                        lambda prompt, *, max_tokens, model=None: "   ")
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



def test_generate_grounded_passes_a_model_override(monkeypatch):
    """Free-tier grounding quota is metered per model, so callers must be able to aim a grounded
    call at a specific one."""
    seen = {}
    monkeypatch.setattr(llm, "_gen_gemini_grounded",
                        lambda prompt, *, max_tokens, model=None: seen.update(model=model) or "ok")
    llm.generate_grounded("x", model="gemini-2.5-pro")
    assert seen["model"] == "gemini-2.5-pro"
    llm.generate_grounded("x")
    assert seen["model"] is None   # None = fall through to GEMINI_GROUNDED_MODEL


# --- model routing (2026-08-07): ungrounded and grounded are NOT the same model -------------

def test_grounded_defaults_to_the_grounded_model_not_the_text_model(monkeypatch):
    """Measured 2026-08-07: gemini-2.5-flash is the ONLY model with free grounded search — every
    3.x model 429s the google_search tool. If grounding followed GEMINI_MODEL, moving the text
    model forward would silently kill grounded ideation, the scriptwriter AND the fact-check gate.
    """
    seen = {}

    class _Resp:
        text = "ok"

    class _Models:
        @staticmethod
        def generate_content(*, model, contents, config):
            seen["model"] = model
            return _Resp()

    monkeypatch.setattr(llm, "_gemini_client", lambda: type("C", (), {"models": _Models})())
    monkeypatch.setattr(llm, "_GEMINI_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", "gemini-2.5-flash")

    llm._gen_gemini_grounded("x", max_tokens=64)
    assert seen["model"] == "gemini-2.5-flash", "grounding must not follow the text model"


def test_thinking_config_is_picked_per_model_generation():
    """`thinking_budget` is REJECTED by Gemini 3.x (400 INVALID_ARGUMENT, verified live) — it was
    replaced by `thinking_level`. Sending the wrong field 400s every Gemini call, which the Groq
    failover then HIDES, so this needs a test rather than a code comment.

    The only test here that needs the SDK — it asserts on real SDK enum values, and faking those
    would assert nothing. Skipped rather than dropped so the rest of the file keeps its
    no-SDK-required property."""
    types = pytest.importorskip("google.genai.types")

    for name in ("gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"):
        cfg = llm._thinking_cfg(name)
        assert cfg.thinking_level == types.ThinkingLevel.MINIMAL, name
        assert cfg.thinking_budget is None, f"{name}: 3.x rejects thinking_budget"

    for name in ("gemini-2.5-flash", "gemini-2.0-flash"):
        cfg = llm._thinking_cfg(name)
        assert cfg.thinking_budget == 0, name
        assert cfg.thinking_level is None, f"{name}: 2.x uses thinking_budget"


# --- the fallback itself must be alive (rule 11) ------------------------------------------

@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"),
                    reason="needs a live Groq key (.env / Actions secrets)")
@pytest.mark.parametrize("as_json", [False, True])
def test_configured_groq_model_actually_exists(as_json):
    """The Groq fallback must be a model Groq still serves.

    Every other Groq test here mocks `_gen_groq`, so they verify the failover LOGIC while saying
    nothing about whether the configured model is real. That gap let the default rot: Groq
    decommissioned `llama-3.3-70b-versatile` and the whole suite stayed green while the ONLY
    fallback under Gemini returned 404 model_not_found on every call. Rule 11 says a single
    upstream failure must never kill the run — but with a dead second link, Gemini's 20/day free
    cap became a hard stop for the entire pipeline.

    Both modes are pinned because the pipeline needs both: scriptwriter and keyword extraction
    ask for JSON, and `json_object` support is NOT implied by a model answering plain prompts
    (`qwen/qwen3.6-27b` answers plain text fine and 400s on JSON).
    """
    prompt = ("Return a JSON object like {\"ok\": true} and nothing else."
              if as_json else "Reply with the single word OK.")
    out = llm._gen_groq(prompt, json=as_json, max_tokens=256)
    assert out and out.strip(), f"{llm._GROQ_MODEL} returned nothing (json={as_json})"
    if as_json:
        import json as _json
        _json.loads(out)  # must be parseable — callers json.loads() this directly


# --- the fallback must survive the BUDGET the pipeline actually passes ---------------------

def test_gen_groq_sends_a_reasoning_effort_so_the_trace_cannot_eat_the_budget(monkeypatch):
    """`_gen_groq` must cap reasoning effort.

    `openai/gpt-oss-120b` is a reasoning model and Groq bills its reasoning trace against the
    completion budget. At the default (medium) effort the trace alone can exhaust a small
    `max_tokens`, so generation stops before one content token is emitted; in json_object mode
    Groq then rejects the empty completion with `400 json_validate_failed` and an empty
    `failed_generation`. That is the 2026-09-01 production failure, reproduced against the real
    `visuals.extract_keywords` call (max_tokens=200) — which is why the model-identity test above
    stayed green: its toy prompt at 256 fits inside the trace.
    """
    seen = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            seen.update(kwargs)
            msg = type("M", (), {"content": '{"ok": true}'})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    monkeypatch.setattr(llm, "_groq_client",
                        lambda: type("Cl", (), {"chat": type("Ch", (), {"completions": _FakeCompletions()})()})())
    llm._gen_groq("return a json object", json=True, max_tokens=200)

    assert seen.get("reasoning_effort") == "low", (
        "reasoning_effort must be sent, else the trace eats max_tokens and JSON mode 400s")


def test_gen_groq_reasoning_effort_is_overridable(monkeypatch):
    seen = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            seen.update(kwargs)
            msg = type("M", (), {"content": "ok"})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    monkeypatch.setattr(llm, "_groq_client",
                        lambda: type("Cl", (), {"chat": type("Ch", (), {"completions": _FakeCompletions()})()})())
    monkeypatch.setenv("GROQ_REASONING_EFFORT", "medium")
    llm._gen_groq("hello", json=False, max_tokens=256)
    assert seen.get("reasoning_effort") == "medium"


@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"),
                    reason="needs a live Groq key (.env / Actions secrets)")
def test_groq_survives_the_real_keyword_prompt_at_its_real_budget():
    """The exact call that 400s in production: the visuals keyword prompt at max_tokens=200.

    Pinned as a LIVE test with the REAL prompt shape and the REAL budget, because the previous
    live test proved only that the model id resolves. The property that broke was whether the
    model reaches its answer inside the budget the pipeline actually passes — which is a
    function of prompt shape, not model identity, and is invisible to a toy prompt.
    """
    import json as _json

    from src import visuals

    captured = {}
    real = llm.generate

    def _spy(prompt, **kw):
        captured["prompt"], captured["kw"] = prompt, kw
        raise RuntimeError("captured")

    llm.generate = _spy
    try:
        visuals.extract_keywords("Trump is threatening a 50% tariff on Canada. It hits cars and steel.")
    except Exception:
        pass
    finally:
        llm.generate = real

    out = llm._gen_groq(captured["prompt"], json=True, max_tokens=captured["kw"]["max_tokens"])
    assert out and out.strip(), f"{llm._GROQ_MODEL} returned nothing for the real keyword prompt"
    _json.loads(out)


# --- transient upstream errors deserve a retry, not an instant failover --------------------

def test_transient_gemini_error_retries_the_same_provider(monkeypatch):
    """A 503 is capacity, not a verdict — retry before burning the fallback.

    Run 32920283763 shows Gemini 503ing and the loop failing straight over to a provider that
    400s on every JSON call, inside a job with ~40 minutes of budget left.
    """
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def _flaky(prompt, *, json, max_tokens):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("503 UNAVAILABLE. The model is overloaded.")
        return "gemini-text"

    monkeypatch.setattr(llm, "_gen_gemini", _flaky)
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: pytest.fail("must not fail over yet"))
    assert llm.generate("p") == "gemini-text"
    assert len(calls) == 2, "the transient error should have been retried once"


def test_a_429_waits_the_delay_the_api_asked_for(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    calls = []

    def _quota(prompt, *, json, max_tokens):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED ... 'retryDelay': '46s' ...")
        return "ok"

    monkeypatch.setattr(llm, "_gen_gemini", _quota)
    assert llm.generate("p") == "ok"
    assert slept and 45 <= slept[0] <= 47, f"should honour the API's own retryDelay, slept {slept}"


def test_a_long_retry_delay_is_not_waited_for(monkeypatch):
    """A daily-cap 429 can name a delay longer than the reel is worth — fail over instead."""
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(llm, "_gen_gemini", _raise("429 RESOURCE_EXHAUSTED 'retryDelay': '3600s'"))
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("p") == "groq-text"
    assert not slept, "must not stall the run on an hour-long backoff"


def test_a_permanent_error_fails_over_immediately(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    calls = []
    monkeypatch.setattr(llm, "_gen_gemini",
                        lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(
                            RuntimeError("400 INVALID_ARGUMENT: your request is malformed")))
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("p") == "groq-text"
    assert len(calls) == 1 and not slept, "a 400 is a verdict, not a blip — no retry"


def test_retry_happens_at_most_once_per_provider(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []
    monkeypatch.setattr(llm, "_gen_gemini",
                        lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(
                            RuntimeError("503 UNAVAILABLE")))
    monkeypatch.setattr(llm, "_gen_groq", lambda *a, **k: "groq-text")
    assert llm.generate("p") == "groq-text"
    assert len(calls) == 2, "one original attempt + one retry, then fail over"


def test_generate_grounded_retries_a_transient_error(monkeypatch):
    """Grounding has no second provider, so a blip there is a total loss.

    It is the single point of failure behind the fact-check gate: when it raises, factcheck
    fails OPEN (FACTCHECK_STRICT=false), so a 503 silently removes the accuracy gate rather
    than blocking a reel. One retry is the cheapest thing standing between a blip and an
    unverified publish.
    """
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def _flaky(prompt, *, max_tokens, model=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("503 UNAVAILABLE. high demand")
        return "grounded-text"

    monkeypatch.setattr(llm, "_gen_gemini_grounded", _flaky)
    assert llm.generate_grounded("p") == "grounded-text"
    assert len(calls) == 2


def test_generate_grounded_does_not_retry_a_permanent_error(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("must not sleep on a 400"))
    calls = []

    def _bad(prompt, *, max_tokens, model=None):
        calls.append(1)
        raise RuntimeError("400 INVALID_ARGUMENT")

    monkeypatch.setattr(llm, "_gen_gemini_grounded", _bad)
    with pytest.raises(RuntimeError, match="400"):
        llm.generate_grounded("p")
    assert len(calls) == 1
