"""LLM helper — Gemini primary, Groq failover (rule 11: fallbacks mandatory).

Contract:
    what it does : one entry point for free-tier text generation; transparent failover.
    how to use   : `from src.llm import generate; text = generate(prompt, json=True)`
    depends on   : google-genai, groq, requests, src.config (GEMINI_API_KEY, GROQ_API_KEY).

Used by the scriptwriter (Module 3) and the ideation fallback. NOT used for Claude —
Claude ideation runs only in the Routine (rule 4). Respect free-tier quotas (rule 13).

Optional third provider: **GitHub Models** (free with a GitHub plan, OpenAI-family catalog).
It is OPT-IN via ENABLE_GH_MODELS / PREFER_GH_MODELS so an incidentally-present GITHUB_TOKEN
can't wedge an unconfigured provider into the failover chain.

SDK note: uses the current **google-genai** SDK (`from google import genai`), not the
deprecated `google-generativeai`. Models are overridable via env (GEMINI_MODEL/GROQ_MODEL)
so we can swap free-tier models without a code change.
"""
from __future__ import annotations

import logging

from functools import lru_cache

import requests

from src import config

log = logging.getLogger(__name__)

# Free-tier defaults (override via env). gemini-2.5-flash + llama-3.3-70b are both on the
# free tiers as of 2026-06; bump here or via env when limits/models change (rule 13).
_GEMINI_MODEL = config.get("GEMINI_MODEL", "gemini-2.5-flash")
_GROQ_MODEL = config.get("GROQ_MODEL", "llama-3.3-70b-versatile")


@lru_cache(maxsize=1)
def _gemini_client():
    """Cached google-genai client. Imported lazily so the module loads without the SDK."""
    from google import genai

    return genai.Client(api_key=config.require("GEMINI_API_KEY"))


@lru_cache(maxsize=1)
def _groq_client():
    """Cached Groq client. Imported lazily so the module loads without the SDK."""
    from groq import Groq

    return Groq(api_key=config.require("GROQ_API_KEY"))


def _gen_gemini(prompt: str, *, json: bool, max_tokens: int) -> str:
    from google.genai import types

    # Disable "thinking" — on gemini-2.5-flash it's on by default and eats max_output_tokens,
    # which truncated JSON replies. We want the whole budget for the actual output.
    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if json:
        cfg.response_mime_type = "application/json"
    resp = _gemini_client().models.generate_content(
        model=_GEMINI_MODEL, contents=prompt, config=cfg
    )
    return resp.text or ""


def _gen_gemini_grounded(prompt: str, *, max_tokens: int, model: str | None = None) -> str:
    """Gemini with Google Search grounding — live web research with real sources.

    Note: the google_search tool can't combine with forced-JSON mime, so the caller must
    ask for JSON in the prompt text and parse it (grounding still makes the model use real,
    current facts + cite genuine sources).

    `model` overrides GEMINI_MODEL for this call. Free-tier quota is metered
    **per model** (quotaId GenerateRequestsPerDayPerProjectPerModel), so pointing a second
    grounded consumer at a different model gives it its OWN daily budget instead of competing
    with ideation and the scriptwriter for one shared 20/day bucket (rule 13).
    """
    from google.genai import types

    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        # Disable "thinking" (on by default for 2.5-flash) — it eats max_output_tokens and was
        # truncating the grounded JSON reply mid-script, forcing the ungrounded fallback. Keep
        # the whole budget for the actual output (mirrors _gen_gemini).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    resp = _gemini_client().models.generate_content(
        model=model or _GEMINI_MODEL, contents=prompt, config=cfg
    )
    return resp.text or ""


def generate_grounded(prompt: str, *, max_tokens: int = 4096, model: str | None = None) -> str:
    """Generate with live web research (Gemini Google Search grounding). Raises on failure so
    callers can fall back to plain generate(). Gemini-only — Groq has no grounding.

    Pass `model` to spend a DIFFERENT model's free-tier quota (see _gen_gemini_grounded)."""
    text = _gen_gemini_grounded(prompt, max_tokens=max_tokens, model=model)
    if not text or not text.strip():
        raise RuntimeError("llm.generate_grounded: empty response")
    return text


def _gen_groq(prompt: str, *, json: bool, max_tokens: int) -> str:
    # Groq's json_object mode requires the word "json" to appear in the prompt; callers
    # that pass json=True already phrase the prompt as "return a JSON object …".
    kwargs: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "model": _GROQ_MODEL,
        "max_tokens": max_tokens,
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
            text = fn(prompt, json=json, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 — failover must catch anything upstream throws
            log.warning("llm: %s failed (%s); failing over", name, e)
            errors.append(f"{name}: {e}")
            continue
        if text and text.strip():
            return text
        log.warning("llm: %s returned an empty response; failing over", name)
        errors.append(f"{name}: empty response")
    raise RuntimeError("llm.generate: all providers failed — " + " | ".join(errors))
