"""LLM helper — Gemini primary, Groq failover (rule 11: fallbacks mandatory).

Contract:
    what it does : one entry point for free-tier text generation; transparent failover.
    how to use   : `from src.llm import generate; text = generate(prompt, json=True)`
    depends on   : google-genai, groq, requests, src.config (GEMINI_API_KEY, GROQ_API_KEY).

Used by the scriptwriter (Module 3) and the ideation fallback. NOT used for Claude —
Claude ideation runs only in the Routine (rule 4). Respect free-tier quotas (rule 13).

Optional third provider: **GitHub Models** — ⚠️ **RETIRED BY GITHUB** (HTTP 410
`github_models_retirement_brownout`, verified 2026-09-01). Still opt-in via ENABLE_GH_MODELS /
PREFER_GH_MODELS and still fails over cleanly, but it can no longer answer, so rule 11's THIRD
link does not currently exist: the live chain is Gemini ↔ Groq only.

SDK note: uses the current **google-genai** SDK (`from google import genai`), not the
deprecated `google-generativeai`. Models are overridable via env (GEMINI_MODEL/GROQ_MODEL)
so we can swap free-tier models without a code change.
"""
from __future__ import annotations

import logging
import re
import time

from functools import lru_cache

import requests

from src import config

log = logging.getLogger(__name__)

# Free-tier defaults (override via env). Two SEPARATE Gemini models on purpose — measured on this
# account 2026-08-07 (rule 13):
#
#   · plain text  — gemini-3.5/3.6-flash, 3.5/3.1-flash-lite and 3-flash-preview all answered fine
#     while gemini-2.5-flash was returning `limit: 20 ... model: gemini-2.5-flash`. Free quota is
#     metered PER MODEL, so each newer model carries its own untouched daily budget, and 3.6 Flash
#     is a straight quality upgrade over 2.5 Flash for scripts and hooks.
#   · grounded    — Google Search grounding 429s on EVERY 3.x model with an empty quota-violation
#     list (the signature of no free allowance), while gemini-2.5-flash 429s with an explicit
#     `limit: 20`, i.e. a real budget that was merely spent. **gemini-2.5-flash is still the only
#     model with free grounded search**, so grounding stays pinned to it.
#
# Keeping these on one knob was a live footgun: `_gen_gemini_grounded` defaulted to GEMINI_MODEL,
# so "bump GEMINI_MODEL if RPD gets tight" — which .env.example actively advised — would have
# silently killed grounded ideation, the grounded scriptwriter AND the fact-check gate at once.
#
# 2026-09-04, measured on a second key: free grounded search is now CLOSED TO NEW PROJECTS.
# `gemini-2.5-flash` 404s with "no longer available to new users" on a fresh key while still
# serving the original project, and every other model 429s with no allowance on BOTH keys. So
# the 20/day on this one project is the entire grounded budget the pipeline will ever have for
# free — it cannot be widened by minting more keys, only by paying.
_GEMINI_MODEL = config.get("GEMINI_MODEL", "gemini-3.6-flash")
_GEMINI_GROUNDED_MODEL = config.get("GEMINI_GROUNDED_MODEL", "gemini-2.5-flash")
# Groq retired `llama-3.3-70b-versatile` — it 404s `model_not_found` (found 2026-08-25, live).
# That left rule 11's mandatory chain with a DEAD second link: every Groq test mocks `_gen_groq`,
# so the suite stayed green while the only fallback under Gemini failed on every call, turning
# Gemini's 20/day free cap into a hard stop for the whole pipeline. `openai/gpt-oss-120b` is the
# most capable model Groq still serves that handles BOTH plain and `json_object` mode, which the
# scriptwriter and keyword extraction both need. (`qwen/qwen3.6-27b` answers plain prompts but
# 400s on JSON and leaks `<think>` reasoning into its output, so it is not a drop-in.)
# `test_configured_groq_model_actually_exists` now pins this against the live API.
_GROQ_MODEL = config.get("GROQ_MODEL", "openai/gpt-oss-120b")


@lru_cache(maxsize=4)
def _gemini_client(api_key: str | None = None):
    """Cached google-genai client, one per API key. Imported lazily (no SDK at import time).

    Keyed by credential because the free tier is metered per PROJECT as well as per model:
    a second free key carries its own 20/day grounded allowance. That matters because
    ideation, the scriptwriter and the fact-check gate all draw on one budget today — see
    `generate_grounded`.
    """
    from google import genai

    return genai.Client(api_key=api_key or config.require("GEMINI_API_KEY"))


@lru_cache(maxsize=1)
def _groq_client():
    """Cached Groq client. Imported lazily so the module loads without the SDK."""
    from groq import Groq

    return Groq(api_key=config.require("GROQ_API_KEY"))


def _thinking_cfg(model: str):
    """Least-thinking config for `model` — the knob is NOT the same across generations.

    Thinking is on by default and eats `max_output_tokens`, which is what truncated grounded
    JSON mid-script back in 2026-06. Suppressing it needs a different field per generation:

      · Gemini 2.x — `thinking_budget=0` (0 = DISABLED).
      · Gemini 3.x — `thinking_budget` is REJECTED (400 INVALID_ARGUMENT, verified 2026-08-07 on
        gemini-3.6-flash); it was replaced by `thinking_level`, whose floor is MINIMAL. Thinking
        cannot be switched off entirely on these models, only minimised.

    Sending the 2.x field to a 3.x model 400s every call, which silently drains the whole Gemini
    leg of the fallback chain into Groq (rule 11) — the failover hides it, so it looks like it
    still works. Hence: pick by model, don't assume.
    """
    from google.genai import types

    head = model.split("-")[1] if "-" in model else ""
    if head.startswith("3"):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    return types.ThinkingConfig(thinking_budget=0)


def _gen_gemini(prompt: str, *, json: bool, max_tokens: int) -> str:
    from google.genai import types

    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=_thinking_cfg(_GEMINI_MODEL),
    )
    if json:
        cfg.response_mime_type = "application/json"
    resp = _gemini_client().models.generate_content(
        model=_GEMINI_MODEL, contents=prompt, config=cfg
    )
    return resp.text or ""


def _gen_gemini_grounded(prompt: str, *, max_tokens: int, model: str | None = None,
                         api_key: str | None = None) -> str:
    """Gemini with Google Search grounding — live web research with real sources.

    Note: the google_search tool can't combine with forced-JSON mime, so the caller must
    ask for JSON in the prompt text and parse it (grounding still makes the model use real,
    current facts + cite genuine sources).

    Defaults to GEMINI_GROUNDED_MODEL, NOT GEMINI_MODEL: free grounded search exists only on
    gemini-2.5-flash on this account (measured 2026-08-07 — every 3.x model 429s the google_search
    tool with no allowance), so the ungrounded model must be free to move ahead without dragging
    grounding onto a model that cannot do it.

    Free-tier quota is metered **per model** (quotaId GenerateRequestsPerDayPerProjectPerModel),
    so pointing a second grounded consumer at a different model would give it its OWN daily budget
    instead of competing for the shared 20/day bucket (rule 13) — but only among models that HAVE
    a grounded allowance, which today is just the default. See factcheck._model().
    """
    return _gen_gemini_grounded_full(prompt, max_tokens=max_tokens, model=model,
                                     api_key=api_key)[0]


def _grounded_sources(resp) -> list[dict]:
    """The REAL Google Search citations behind a grounded reply: [{uri, domain, spans}].

    This is the metadata the module used to discard. Without it, callers had no way to learn
    which pages the search actually returned, so `ideation_fallback` asked the MODEL for source
    URLs — and a model cannot recall URLs, so it produced plausible-looking ones with placeholder
    ids (`articleshow/115000000.cms`, `world-asia-68700000`). Measured 2026-09-03: every such URL
    404'd, the liveness probe dropped the ideas, and the on-demand run either shipped a digest of
    one or died with "no fresh ideas to seed".

    `spans` are (start, end) character offsets into the reply text, from `grounding_supports`, so
    a caller emitting several objects in one reply can attribute each citation to the right one.
    A chunk with no support keeps an empty span list: it is still a real article, merely
    unattributable. Fail-soft (rule 11) — a reply with no grounding metadata yields [].
    """
    try:
        gm = resp.candidates[0].grounding_metadata
        chunks = list(gm.grounding_chunks or [])
    except (AttributeError, IndexError, TypeError):
        return []

    spans: dict[int, list[tuple[int, int]]] = {}
    try:
        for sup in gm.grounding_supports or []:
            seg = sup.segment
            for idx in sup.grounding_chunk_indices or []:
                spans.setdefault(int(idx), []).append((int(seg.start_index), int(seg.end_index)))
    except (AttributeError, TypeError):  # noqa: BLE001 — spans are a bonus, citations are not
        spans = {}

    out: list[dict] = []
    for i, chunk in enumerate(chunks):
        web = getattr(chunk, "web", None)
        uri = (getattr(web, "uri", "") or "").strip()
        if uri:
            out.append({"uri": uri, "domain": (getattr(web, "title", "") or "").strip(),
                        "spans": spans.get(i, [])})
    return out


def _gen_gemini_grounded_full(prompt: str, *, max_tokens: int, model: str | None = None,
                              api_key: str | None = None) -> tuple[str, list[dict]]:
    """One grounded call — returns (text, real citations). See `_grounded_sources`."""
    from google.genai import types

    chosen = model or _GEMINI_GROUNDED_MODEL
    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        # Minimise "thinking" — it eats max_output_tokens and was truncating the grounded JSON
        # reply mid-script, forcing the ungrounded fallback. Per-generation field (_thinking_cfg).
        thinking_config=_thinking_cfg(chosen),
    )
    resp = _gemini_client(api_key).models.generate_content(
        model=chosen, contents=prompt, config=cfg
    )
    return resp.text or "", _grounded_sources(resp)


def generate_grounded(prompt: str, *, max_tokens: int = 4096, model: str | None = None,
                      api_key: str | None = None) -> str:
    """Generate with live web research (Gemini Google Search grounding). Raises on failure so
    callers can fall back to plain generate(). Gemini-only — Groq has no grounding.

    Pass `model` to spend a DIFFERENT model's free-tier quota (see _gen_gemini_grounded), or
    `api_key` to spend a different PROJECT's. Both matter: measured 2026-09-03, ideation +
    the scriptwriter + the fact-check gate share ONE 20/day grounded budget, a 3-reel run
    costs 7 calls, and once it is gone the gate fails open (factcheck.verify).

    Retried once on a transient error, because this path has NO second provider (Groq has no
    grounding) and its failure is silent: `factcheck.verify` treats a checker outage as
    fail-open under the default FACTCHECK_STRICT=false, so a 503 here does not block a reel —
    it publishes one with the accuracy gate quietly absent.
    """
    def _attempt(p, *, json=False, max_tokens=max_tokens):  # noqa: ARG001 — _call_with_retry's shape
        return _gen_gemini_grounded(p, max_tokens=max_tokens, model=model, api_key=api_key)

    text = _call_with_retry("gemini-grounded", _attempt, prompt, json=False, max_tokens=max_tokens)
    if not text or not text.strip():
        raise RuntimeError("llm.generate_grounded: empty response")
    return text


def generate_grounded_with_sources(prompt: str, *, max_tokens: int = 4096,
                                   model: str | None = None,
                                   api_key: str | None = None) -> tuple[str, list[dict]]:
    """Like `generate_grounded`, but also returns the search's REAL citation URLs.

    Use this wherever the reply is supposed to be SOURCED. Asking the model to write the URLs
    into its own answer does not work — it invents them — so the citations must come from the
    grounding metadata, which is what this exposes (see `_grounded_sources`).
    """
    def _attempt(p, *, json=False, max_tokens=max_tokens):  # noqa: ARG001 — _call_with_retry's shape
        return _gen_gemini_grounded_full(p, max_tokens=max_tokens, model=model,
                                         api_key=api_key)

    text, sources = _call_with_retry("gemini-grounded", _attempt, prompt,
                                     json=False, max_tokens=max_tokens)
    if not text or not text.strip():
        raise RuntimeError("llm.generate_grounded: empty response")
    return text, sources


# Upstream states worth ONE retry: capacity and quota-window, not "your request is wrong".
# A 400 is a verdict — retrying it just spends the clock twice for the same answer.
_RETRYABLE_MARKERS = ("429", "resource_exhausted", "503", "unavailable", "500", "internal",
                      "504", "deadline", "overloaded")
# Google returns its own advice as `'retryDelay': '46s'`. Honour it rather than guessing.
_RETRY_DELAY_RE = re.compile(r"retrydelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.I)
_DEFAULT_RETRY_WAIT = 2.0


def _retry_wait(exc: Exception) -> float | None:
    """Seconds to wait before retrying `exc`, or None if it is not worth retrying.

    None also covers "retryable, but the API wants longer than a reel is worth": a daily-cap 429
    can name an hour, and stalling a 60-minute job on it is worse than failing over.
    """
    text = str(exc).lower()
    if not any(m in text for m in _RETRYABLE_MARKERS):
        return None
    m = _RETRY_DELAY_RE.search(text)
    wait = float(m.group(1)) if m else _DEFAULT_RETRY_WAIT
    try:
        ceiling = float(config.get("LLM_RETRY_MAX_WAIT", "90"))
    except (TypeError, ValueError):
        ceiling = 90.0
    return wait if wait <= ceiling else None


def _call_with_retry(name: str, fn, prompt: str, *, json: bool, max_tokens: int) -> str:
    """One provider call, retried ONCE on a transient upstream error.

    Rule 11 gives every dependency a fallback, but failing over on a 503 spends the fallback on
    a blip — and when the fallback is itself degraded, that turns a recoverable hiccup into a
    dead reel. Run 32920283763: Gemini 503s, the loop immediately hands the work to a Groq leg
    that 400s on every JSON call, and the reel dies with ~40 minutes of job budget unused, while
    the 429 in the same run carried an explicit `retryDelay: 46s` nobody read.
    """
    try:
        return fn(prompt, json=json, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001 — decide retry-vs-failover from the error itself
        wait = _retry_wait(e)
        if wait is None:
            raise
        log.warning("llm: %s hit a transient error (%s); retrying once in %.1fs", name, e, wait)
        time.sleep(wait)
        return fn(prompt, json=json, max_tokens=max_tokens)


def _gen_groq(prompt: str, *, json: bool, max_tokens: int) -> str:
    # Groq's json_object mode requires the word "json" to appear in the prompt; callers
    # that pass json=True already phrase the prompt as "return a JSON object …".
    #
    # reasoning_effort is LOAD-BEARING, not a tuning knob. The default model is a reasoning
    # model (openai/gpt-oss-*) and Groq bills the reasoning trace against the completion budget.
    # At Groq's default effort the trace alone can consume a small max_tokens, so generation is
    # cut off before a single content token is emitted — and in json_object mode Groq then
    # rejects that empty completion with `400 json_validate_failed` / `failed_generation: ''`.
    # Measured 2026-09-01 on the real visuals keyword prompt at max_tokens=200: default effort
    # 400s, "low" answers in 52 reasoning tokens. That 400 is what left rule 11's chain one-deep
    # for six days, because the model-identity test passes a toy prompt that fits in the trace.
    # Documented values for gpt-oss are low|medium|high (console.groq.com/docs/reasoning).
    kwargs: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "model": _GROQ_MODEL,
        "max_tokens": max_tokens,
        "reasoning_effort": config.get("GROQ_REASONING_EFFORT", "low"),
    }
    if json:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _groq_client().chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _github_key() -> str | None:
    """The GitHub Models credential.

    Named GH_MODELS_KEY, not GITHUB_MODELS_KEY: GitHub rejects secret/variable names starting
    with the `GITHUB_` prefix, so the latter could never be created as an Actions secret.
    `GITHUB_TOKEN` is still read because it is the built-in Actions token (usable with
    `permissions: models: read`).

    Deliberately does NOT fall back to GH_PAT: that is the Telegram bot's Actions read+write
    PAT, and this repo's Actions hold the YouTube/Supabase/Telegram secrets — sending it to a
    third-party inference endpoint would widen its blast radius for nothing (rule 5). Use a
    token whose ONLY scope is `models: read`."""
    return config.get("GH_MODELS_KEY") or config.get("GITHUB_TOKEN")


def _github_enabled() -> bool:
    """GitHub Models is OPT-IN, not "on whenever a token exists".

    `GITHUB_TOKEN` shows up in environments incidentally (any Actions job that forwards it), and
    an unconfigured provider silently inserted into the chain costs a doomed HTTP round-trip on
    every call — which delays the Groq failover on exactly the Gemini-quota outages it's there
    to survive (rules 11, 13)."""
    if not _github_key():
        return False
    return (config.get_bool("PREFER_GH_MODELS", False)
            or config.get_bool("ENABLE_GH_MODELS", False))


def _gen_github_models(prompt: str, *, json: bool, max_tokens: int) -> str:
    """GitHub Models inference (OpenAI-compatible chat completions).

    ⚠️ **RETIRED BY GITHUB — this leg cannot contribute a completion.** Verified 2026-09-01:
    both `models.github.ai/catalog/models` and the inference endpoint below return HTTP 410
    `github_models_retirement_brownout`. It stays in the tree because it is opt-in, defaults to
    off, and fails over cleanly — but do NOT count it as rule 11's third link. If a genuine
    third provider is wanted, a second model on the existing Groq key is the cheapest real one.

    Endpoint + model naming per GitHub's REST docs: the host is `models.github.ai/inference`
    (the old `models.inference.ai.azure.com` preview host is retired) and `model` MUST carry its
    publisher prefix, e.g. `openai/gpt-4o-mini`. The token needs the **`models: read`** scope; in
    Actions the job also needs `permissions: models: read`.

    Catalog is OpenAI/DeepSeek/Microsoft/Llama/Mistral/xAI — there is no Anthropic model here,
    so this never becomes a back door around rule 4."""
    key = _github_key()
    if not key:
        raise RuntimeError("github models: GH_MODELS_KEY / GITHUB_TOKEN not set")
    model = config.get("GH_MODEL", "openai/gpt-4o-mini")
    if "/" not in model:  # a bare name 400s on this endpoint; assume the OpenAI publisher
        model = f"openai/{model}"
    payload: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "model": model,
        "max_tokens": max_tokens,
    }
    if json:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://models.github.ai/inference/chat/completions",
        headers={"Authorization": f"Bearer {key}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"github models HTTP {r.status_code}: {r.text[:300]}")
    choices = (r.json() or {}).get("choices") or []
    if not choices:
        raise RuntimeError("github models returned no choices")
    return choices[0].get("message", {}).get("content") or ""


def generate(prompt: str, *, json: bool = False, max_tokens: int = 1024,
             prefer_groq: bool = False) -> str:
    """Generate text via Gemini; on error/quota/empty, fail over to Groq. Return raw text.

    Set json=True when the prompt asks for a JSON object (callers parse the result); every
    provider is put into JSON mode. Raises RuntimeError only if *every* provider fails —
    a single upstream failure never propagates (rule 11). This is the runtime-soft path
    (rule 14): providers are tried in order and failures are logged, not fatal.

    prefer_groq=True tries Groq FIRST (Gemini second). Use it for no-web text tasks (hook
    punch-up, keyword extraction) so Gemini's scarce free RPD (rule 13) is reserved for the
    grounded web research that only Gemini can do — quality on the accuracy-critical path stays.

    GitHub Models joins the chain only when explicitly opted in (see `_github_enabled`):
    ENABLE_GH_MODELS inserts it as a middle fallback, PREFER_GH_MODELS puts it first.
    """
    gemini = ("gemini", _gen_gemini)
    groq = ("groq", _gen_groq)
    github = ("github", _gen_github_models)

    use_github = _github_enabled()
    if prefer_groq:
        order = (groq, github, gemini) if use_github else (groq, gemini)
    elif use_github and config.get_bool("PREFER_GH_MODELS", False):
        order = (github, gemini, groq)
    else:
        order = (gemini, github, groq) if use_github else (gemini, groq)

    errors: list[str] = []
    for name, fn in order:
        try:
            text = _call_with_retry(name, fn, prompt, json=json, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 — failover must catch anything upstream throws
            log.warning("llm: %s failed (%s); failing over", name, e)
            errors.append(f"{name}: {e}")
            continue
        if text and text.strip():
            return text
        log.warning("llm: %s returned an empty response; failing over", name)
        errors.append(f"{name}: empty response")
    raise RuntimeError("llm.generate: all providers failed — " + " | ".join(errors))
