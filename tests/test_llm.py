"""Unit tests for the LLM failover logic (rule 11: the fallback chain must be tested).

These mock the two provider calls, so they need no API keys, no network, and no SDK
installed — they verify the orchestration in src.llm.generate in isolation (rule 7).
"""
from __future__ import annotations

import os

import pytest

from src import config, llm


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
                        lambda prompt, *, max_tokens, model=None, api_key=None: "grounded")
    assert llm.generate_grounded("x") == "grounded"


def test_generate_grounded_raises_on_empty(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini_grounded",
                        lambda prompt, *, max_tokens, model=None, api_key=None: "   ")
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
                        lambda prompt, *, max_tokens, model=None, api_key=None: seen.update(model=model) or "ok")
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

    monkeypatch.setattr(llm, "_gemini_client",
                        lambda api_key=None: type("C", (), {"models": _Models})())
    monkeypatch.setattr(llm, "_GEMINI_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", "gemini-2.5-flash")

    llm._gen_gemini_grounded("x", max_tokens=64)
    assert seen["model"] == "gemini-2.5-flash", "grounding must not follow the text model"


def _grounded_fake(monkeypatch, fail: dict[str, Exception]):
    """A client whose generate_content fails for the named models; records every attempt."""
    seen: list[str] = []

    class _Resp:
        text = "ok"
        candidates: list = []

    class _Models:
        @staticmethod
        def generate_content(*, model, contents, config):
            seen.append(model)
            if model in fail:
                raise fail[model]
            return _Resp()

    monkeypatch.setattr(llm, "_gemini_client",
                        lambda api_key=None: type("C", (), {"models": _Models})())
    return seen


def test_a_retired_grounded_model_falls_through_to_the_next_in_the_chain(monkeypatch):
    """Vertex retires gemini-2.5-flash on 2026-10-20 (Google's model-versions page, fetched
    2026-09-27). It grounds ideation, the scriptwriter AND the fact-check gate, and with
    FACTCHECK_STRICT=true a gate that cannot run holds every reel back — so a single pinned model
    would stop the channel publishing on that date. A 404 must advance the chain instead."""
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", "gemini-2.5-flash,gemini-3.5-flash-lite")
    seen = _grounded_fake(monkeypatch, {"gemini-2.5-flash": RuntimeError(
        "404 NOT_FOUND. Publisher model `.../gemini-2.5-flash` was not found or your project "
        "does not have access to it.")})
    assert llm._gen_gemini_grounded("x", max_tokens=64) == "ok"
    assert seen == ["gemini-2.5-flash", "gemini-3.5-flash-lite"]


def test_the_grounded_chain_does_not_skip_a_model_on_other_errors(monkeypatch):
    """Only "this model is gone" advances the chain. A 503 is retried by _call_with_retry on the
    SAME model; moving on would quietly swap the fact-check model on a blip."""
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", "gemini-2.5-flash,gemini-3.5-flash-lite")
    seen = _grounded_fake(monkeypatch, {"gemini-2.5-flash": RuntimeError("503 UNAVAILABLE")})
    with pytest.raises(RuntimeError, match="503"):
        llm._gen_gemini_grounded("x", max_tokens=64)
    assert seen == ["gemini-2.5-flash"]


def test_an_explicit_grounded_model_is_not_expanded_into_the_chain(monkeypatch):
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", "gemini-2.5-flash,gemini-3.5-flash-lite")
    seen = _grounded_fake(monkeypatch, {})
    llm._gen_gemini_grounded("x", max_tokens=64, model="gemini-3.5-flash")
    assert seen == ["gemini-3.5-flash"]


def test_vertex_has_moved_off_the_retiring_model(monkeypatch):
    """gemini-2.5-flash retires on Vertex on 2026-10-20; the pipeline moved ahead of it."""
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", None)
    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    chain = llm._grounded_chain(None)
    assert chain[0] == "gemini-3.5-flash-lite" and "gemini-2.5-flash" not in chain


def test_the_developer_api_keeps_its_only_free_grounded_model(monkeypatch):
    monkeypatch.setattr(llm, "_GEMINI_GROUNDED_MODEL", None)
    monkeypatch.delenv("GEMINI_USE_VERTEX", raising=False)
    assert llm._grounded_chain(None) == ["gemini-2.5-flash"]


def test_an_explicit_model_may_be_a_chain_of_its_own():
    assert llm._grounded_chain("gemini-3.5-flash, gemini-3.5-flash-lite") == [
        "gemini-3.5-flash", "gemini-3.5-flash-lite"]


def test_an_unsupported_thinking_level_is_retried_at_low(monkeypatch):
    """gemini-3.8-flash rejects THINKING_LEVEL_MINIMAL with a 400 (measured 2026-09-27 on
    Vertex); LOW is its floor. Without this, moving GEMINI_MODEL to 3.8 would 400 every Gemini
    call and the Groq failover would hide it."""
    types = pytest.importorskip("google.genai.types")
    levels = []

    class _Resp:
        text = "ok"

    class _Models:
        @staticmethod
        def generate_content(*, model, contents, config):
            levels.append(config.thinking_config.thinking_level)
            if config.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL:
                raise RuntimeError("400 INVALID_ARGUMENT. Thinking level is unsupported: "
                                   "THINKING_LEVEL_MINIMAL")
            return _Resp()

    monkeypatch.setattr(llm, "_gemini_client",
                        lambda api_key=None: type("C", (), {"models": _Models})())
    monkeypatch.setattr(llm, "_GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(llm, "_MINIMAL_REFUSED", set())
    assert llm._gen_gemini("x", json=False, max_tokens=64) == "ok"
    assert levels == [types.ThinkingLevel.MINIMAL, types.ThinkingLevel.LOW]
    # Remembered: the next call does not spend a failed request first.
    assert llm._gen_gemini("y", json=False, max_tokens=64) == "ok"
    assert levels[2:] == [types.ThinkingLevel.LOW]


@pytest.mark.parametrize("message", [
    "400 INVALID_ARGUMENT. Thinking level is unsupported: THINKING_LEVEL_MINIMAL",  # Vertex
    "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Thinking level MINIMAL is not "
    "supported for this model. Please retry with other thinking level'}}",  # Developer API
])
def test_both_wordings_of_the_minimal_refusal_are_recognised(message):
    """The Developer API's wording was missed, so there every 3.8 call went to Groq."""
    assert llm._MINIMAL_REFUSAL_RE.search(message)
    assert not llm._MINIMAL_REFUSAL_RE.search("400 INVALID_ARGUMENT. Request contains an "
                                              "invalid argument.")


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

@pytest.mark.live
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


@pytest.mark.live
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

    def _flaky(prompt, *, max_tokens, model=None, api_key=None):
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

    def _bad(prompt, *, max_tokens, model=None, api_key=None):
        calls.append(1)
        raise RuntimeError("400 INVALID_ARGUMENT")

    monkeypatch.setattr(llm, "_gen_gemini_grounded", _bad)
    with pytest.raises(RuntimeError, match="400"):
        llm.generate_grounded("p")
    assert len(calls) == 1


# --- grounded CITATIONS (2026-09-03) ------------------------------------------------------
# `_gen_gemini_grounded` returned only resp.text and dropped grounding_metadata on the floor, so
# the real Google Search citations were discarded and callers had to ask the model to write
# source URLs from memory. It cannot, so it invented them. These expose the real ones.

class _FakeWeb:
    def __init__(self, uri, title):
        self.uri, self.title = uri, title


class _FakeChunk:
    def __init__(self, uri, title):
        self.web = _FakeWeb(uri, title)


class _FakeSegment:
    def __init__(self, start, end):
        self.start_index, self.end_index, self.text = start, end, ""


class _FakeSupport:
    def __init__(self, start, end, idxs):
        self.segment = _FakeSegment(start, end)
        self.grounding_chunk_indices = idxs


class _FakeMeta:
    def __init__(self, chunks, supports):
        self.grounding_chunks, self.grounding_supports = list(chunks), list(supports)


class _FakeCandidate:
    def __init__(self, meta):
        self.grounding_metadata = meta


class _FakeResponse:
    def __init__(self, text, candidates):
        self.text, self.candidates = text, candidates


def _fake_grounded_response(text, chunks=(), supports=()):
    return _FakeResponse(text, [_FakeCandidate(_FakeMeta(chunks, supports))])


def test_grounded_sources_extracts_real_citation_uris():
    resp = _fake_grounded_response(
        "some text",
        chunks=[_FakeChunk("https://redirect/aaa", "aljazeera.com"),
                _FakeChunk("https://redirect/bbb", "bbc.com")],
        supports=[_FakeSupport(0, 4, [0]), _FakeSupport(5, 9, [1])],
    )
    assert llm._grounded_sources(resp) == [
        {"uri": "https://redirect/aaa", "domain": "aljazeera.com", "spans": [(0, 4)]},
        {"uri": "https://redirect/bbb", "domain": "bbc.com", "spans": [(5, 9)]},
    ]


def test_grounded_sources_keeps_chunks_that_have_no_support_span():
    """A citation with no span still names a real, live article — it just can't be attributed
    to one idea. Dropping it would throw away the only usable URL on a thin response."""
    resp = _fake_grounded_response("t", chunks=[_FakeChunk("https://r/a", "ndtv.com")])
    assert llm._grounded_sources(resp) == [
        {"uri": "https://r/a", "domain": "ndtv.com", "spans": []}]


def test_grounded_sources_is_empty_when_metadata_is_absent():
    """Grounding metadata is absent on plenty of real replies; that must not raise (rule 11)."""
    assert llm._grounded_sources(_FakeResponse("t", [])) == []


# --- what the API's offsets actually MEAN (2026-09-13, measured live on Vertex) ------------
# Ideas 291 and 292 each shipped citing the same 15 articles — Modi-Xi, the Houthis, a Nagpur
# robbery and a California murder — because every one of these was misread.

class _FakePart:
    def __init__(self, text, thought=None):
        self.text, self.thought = text, thought


class _FakeContent:
    def __init__(self, parts):
        self.parts = list(parts)


class _FakePartsCandidate(_FakeCandidate):
    def __init__(self, meta, parts):
        super().__init__(meta)
        self.content = _FakeContent(parts)


def _seg_support(start, end, idxs, part_index=None):
    sup = _FakeSupport(start, end, idxs)
    sup.segment.part_index = part_index
    return sup


def test_a_support_at_offset_zero_keeps_every_span():
    """proto3 omits a 0, so the reply's FIRST support arrives with start_index=None. `int(None)`
    used to throw away the spans of ALL supports, making every citation unattributable."""
    text = '{"ideas": [{"title": "A"}, {"title": "B"}]}'
    resp = _fake_grounded_response(
        text,
        chunks=[_FakeChunk("https://r/a", "a.com"), _FakeChunk("https://r/b", "b.com")],
        supports=[_FakeSupport(None, 24, [0]), _FakeSupport(26, 42, [1])])
    out = llm._grounded_sources(resp)
    assert out[0]["spans"] == [(0, 24)]
    assert out[1]["spans"] == [(26, 42)], "one None must not wipe the other supports"


def test_support_offsets_are_bytes_and_become_character_offsets():
    """Vertex counts UTF-8 bytes. '₹' is 3 bytes and '—' is 3, so reading bytes as characters
    lands a later citation 4 characters to the right — on the neighbouring idea, in a digest."""
    text = "₹5 cr — first. Second claim."
    start_b = len("₹5 cr — first. ".encode("utf-8"))
    resp = _fake_grounded_response(
        text, chunks=[_FakeChunk("https://r/a", "a.com")],
        supports=[_FakeSupport(start_b, len(text.encode("utf-8")), [0])])
    (s, e), = llm._grounded_sources(resp)[0]["spans"]
    assert text[s:e] == "Second claim."


def test_support_offsets_are_relative_to_their_part():
    parts = [_FakePart("thinking…", thought=True), _FakePart("First part. "), _FakePart("Second.")]
    text = "First part. Second."
    meta = _FakeMeta([_FakeChunk("https://r/a", "a.com")], [_seg_support(0, 7, [0], part_index=2)])
    resp = _FakeResponse(text, [_FakePartsCandidate(meta, parts)])
    (s, e), = llm._grounded_sources(resp)[0]["spans"]
    assert text[s:e] == "Second."


def test_a_malformed_support_costs_only_itself():
    text = "alpha beta"
    resp = _fake_grounded_response(
        text, chunks=[_FakeChunk("https://r/a", "a.com"), _FakeChunk("https://r/b", "b.com")],
        supports=[_FakeSupport(0, None, [0]), _FakeSupport(6, 10, [1])])
    out = llm._grounded_sources(resp)
    assert out[0]["spans"] == []
    assert out[1]["spans"] == [(6, 10)]


def test_generate_grounded_with_sources_returns_text_and_citations(monkeypatch):
    monkeypatch.setattr(
        llm, "_gen_gemini_grounded_full",
        lambda prompt, *, max_tokens, model=None, api_key=None: ("body", [{"uri": "https://r/a",
                                                             "domain": "bbc.com", "spans": []}]))
    text, sources = llm.generate_grounded_with_sources("x")
    assert text == "body"
    assert sources == [{"uri": "https://r/a", "domain": "bbc.com", "spans": []}]


def test_generate_grounded_with_sources_raises_on_empty(monkeypatch):
    monkeypatch.setattr(llm, "_gen_gemini_grounded_full",
                        lambda prompt, *, max_tokens, model=None, api_key=None: ("  ", []))
    with pytest.raises(RuntimeError):
        llm.generate_grounded_with_sources("x")


# --- a SEPARATE grounded key (2026-09-03 audit) --------------------------------------------
# Ideation, the scriptwriter and the fact-check gate all spend ONE 20/day free budget on
# gemini-2.5-flash. A 3-reel run costs 7 grounded calls, so a busy day exhausts it — and the
# fact-check gate then fails OPEN. Threading an api_key lets the gate spend a different free
# key's own budget (the same trick GEMINI_TTS_API_KEY already uses for TTS).

def test_gemini_client_is_cached_per_api_key(monkeypatch):
    built = []

    class _FakeGenai:
        @staticmethod
        def Client(api_key=None):
            built.append(api_key)
            return f"client:{api_key}"

    monkeypatch.setattr(llm, "_gemini_client", llm._gemini_client.__wrapped__)  # drop the cache
    monkeypatch.setitem(__import__("sys").modules, "google", type("m", (), {"genai": _FakeGenai}))
    monkeypatch.setenv("GEMINI_API_KEY", "default-key")

    assert llm._gemini_client("other-key") == "client:other-key"
    assert llm._gemini_client(None) == "client:default-key"
    assert built == ["other-key", "default-key"]


def test_generate_grounded_threads_an_api_key_through(monkeypatch):
    seen = {}

    def _fake(prompt, *, max_tokens, model=None, api_key=None):
        seen["api_key"] = api_key
        return ("body", [])

    monkeypatch.setattr(llm, "_gen_gemini_grounded_full", _fake)
    llm.generate_grounded("x", api_key="checker-key")
    assert seen["api_key"] == "checker-key"


# --- Vertex AI path (2026-09-04) -----------------------------------------------------------
# The Developer API free tier gives 20 grounded requests/DAY on gemini-2.5-flash, shared by
# ideation, the scriptwriter and the fact-check gate — ~21/day of demand, so it runs dry. Vertex
# AI serves the same models with 1,500 grounded requests/DAY free on 2.5, and authenticates with
# ADC instead of an API key, which is what this Google Cloud org's policy permits (it blocks both
# API keys and service-account keys). Measured working 2026-09-04 on but-it-matters-tts.

def test_vertex_is_off_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_USE_VERTEX", raising=False)
    assert llm._use_vertex() is False


def test_vertex_client_needs_no_api_key(monkeypatch):
    built = {}

    class _FakeGenai:
        @staticmethod
        def Client(**kw):
            built.update(kw)
            return "vertex-client"

    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    monkeypatch.setenv("GCP_PROJECT", "but-it-matters-tts")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # must not be required in Vertex mode
    monkeypatch.setattr(llm, "_gemini_client", llm._gemini_client.__wrapped__)
    monkeypatch.setitem(__import__("sys").modules, "google", type("m", (), {"genai": _FakeGenai}))

    assert llm._gemini_client(None) == "vertex-client"
    assert built == {"vertexai": True, "project": "but-it-matters-tts", "location": "global"}


def test_vertex_ignores_a_per_caller_api_key(monkeypatch):
    """FACTCHECK_API_KEY is meaningless on Vertex — quota there is per PROJECT, not per key."""
    built = {}

    class _FakeGenai:
        @staticmethod
        def Client(**kw):
            built.update(kw)
            return "vertex-client"

    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    monkeypatch.setenv("GCP_PROJECT", "p")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.setattr(llm, "_gemini_client", llm._gemini_client.__wrapped__)
    monkeypatch.setitem(__import__("sys").modules, "google", type("m", (), {"genai": _FakeGenai}))

    llm._gemini_client("some-key")
    assert "api_key" not in built
    assert built["location"] == "us-central1"


def test_vertex_without_a_project_fails_loudly(monkeypatch):
    """Rule 14: a half-configured Vertex switch must not silently fall back to a spent key."""
    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.setattr(llm, "_gemini_client", llm._gemini_client.__wrapped__)
    with pytest.raises(config.ConfigError):
        llm._gemini_client(None)


# --- shared JSON repair (2026-09-27): one parser for every hand-written LLM JSON ----------

def test_parse_json_survives_the_channels_scare_quotes():
    """Both 2026-09-22 scripts were written UNGROUNDED because the grounded reply carried a raw
    scare quote ('the US just "destroyed" five...') and the scriptwriter's parser died on it."""
    raw = '{"script_body": "The US just "destroyed" five boats. Sure.", "title": "t"}'
    assert llm.parse_json_object(raw)["script_body"] == 'The US just "destroyed" five boats. Sure.'


def test_parse_json_ignores_text_after_the_object():
    """'Extra data: line 11 column 4' killed ideation's top-up on run 34954327606."""
    raw = 'Sure! {"stories": [{"story": "a"}]}\nHope that helps. {"not": "this"}'
    assert llm.parse_json(raw) == {"stories": [{"story": "a"}]}


def test_parse_json_reads_a_bare_array():
    """The old first-{-to-last-} slice turned `[{..}, {..}]` into `{..}, {..}`: Extra data."""
    assert llm.parse_json('```json\n[{"a": 1}, {"b": 2}]\n```') == [{"a": 1}, {"b": 2}]


def test_parse_json_tolerates_raw_newlines_in_strings():
    assert llm.parse_json_object('{"caption": "line one\nline two"}')["caption"] == \
        "line one\nline two"


def test_parse_json_raises_valueerror_when_there_is_nothing_to_parse():
    with pytest.raises(ValueError):
        llm.parse_json("no json here at all")
    with pytest.raises(ValueError):
        llm.parse_json_object("[1, 2]")


def test_groq_retries_an_empty_json_completion_with_more_room(monkeypatch):
    """gpt-oss bills its reasoning against max_tokens; an EMPTY failed_generation means the
    budget ran out before any content (seen at 200 and at 1024 tokens)."""
    budgets = []

    class _Completions:
        @staticmethod
        def create(**kw):
            budgets.append(kw["max_tokens"])
            if len(budgets) == 1:
                raise RuntimeError("Error code: 400 - {'error': {'code': 'json_validate_failed', "
                                   "'failed_generation': ''}}")
            msg = type("M", (), {"content": '{"ok": 1}'})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    client = type("G", (), {"chat": type("Ch", (), {"completions": _Completions})()})()
    monkeypatch.setattr(llm, "_groq_client", lambda: client)
    assert llm._gen_groq("json please", json=True, max_tokens=512) == '{"ok": 1}'
    assert budgets == [512, 1024]


def test_a_dropped_connection_on_a_grounded_call_is_retried():
    """Under FACTCHECK_STRICT one network blip on the gate's call held a reel back."""
    assert llm._retry_wait(RuntimeError("Server disconnected without sending a response.")) == 2.0
    assert llm._retry_wait(RuntimeError("400 INVALID_ARGUMENT")) is None


@pytest.mark.parametrize("reply", [
    'Per the search [1][2], here it is: {"ok": true}',
    '[pause] {"ok": true}',
    'Sure.\n```json\n{"ok": true}\n```',
])
def test_a_bracket_before_the_json_is_not_the_json(reply):
    """A preamble bracket used to be decoded as the reply ('[1]') or fail the parse outright."""
    assert llm.parse_json(reply) == {"ok": True}


def test_a_list_of_objects_and_an_empty_list_still_parse():
    assert llm.parse_json('[{"a": 1}, {"a": 2}] trailing') == [{"a": 1}, {"a": 2}]
    assert llm.parse_json("[]") == []
    with pytest.raises(ValueError):
        llm.parse_json("[1, 2] and nothing else")


@pytest.mark.parametrize("message, gone", [
    ("404 NOT_FOUND. Publisher model gemini-2.5-flash was not found", True),
    ("400 FAILED_PRECONDITION. Model gemini-2.5-flash has been retired.", True),
    ("410 Gone: gemini-2.5-flash is no longer supported", True),
    ("400 INVALID_ARGUMENT. The model gemini-2.5-flash is deprecated.", True),
    ("503 UNAVAILABLE. The model is overloaded.", False),
    ("429 RESOURCE_EXHAUSTED. Quota exceeded.", False),
    ("400 INVALID_ARGUMENT. Request contains an invalid argument.", False),
])
def test_a_retired_model_is_recognised_however_it_is_worded(message, gone):
    """gemini-2.5-flash retires on Vertex on 2026-10-20; the chain must move on unattended."""
    assert llm._is_model_gone(RuntimeError(message)) is gone
