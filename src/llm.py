"""LLM helper — Gemini primary, Groq failover (rule 11: fallbacks mandatory).

Contract:
    what it does : one entry point for free-tier text generation; transparent failover.
    how to use   : `from src.llm import generate; text = generate(prompt, json=True)`
    depends on   : google-genai, groq, src.config (GEMINI_API_KEY, GROQ_API_KEY).

Used by the scriptwriter (Module 3) and the ideation fallback. NOT used for Claude —
Claude ideation runs only in the Routine (rule 4). Respect free-tier quotas (rule 13).

SDK note: uses the current **google-genai** SDK (`from google import genai`), not the
deprecated `google-generativeai`. Models are overridable via env (GEMINI_MODEL/GROQ_MODEL)
so we can swap free-tier models without a code change.
"""
from __future__ import annotations

import logging

from functools import lru_cache

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
    cfg: dict = {"max_output_tokens": max_tokens}
    if json:
        cfg["response_mime_type"] = "application/json"
    resp = _gemini_client().models.generate_content(
        model=_GEMINI_MODEL, contents=prompt, config=cfg
    )
    return resp.text or ""


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


def generate(prompt: str, *, json: bool = False, max_tokens: int = 1024) -> str:
    """Generate text via Gemini; on error/quota/empty, fail over to Groq. Return raw text.

    Set json=True when the prompt asks for a JSON object (callers parse the result); both
    providers are put into JSON mode. Raises RuntimeError only if *every* provider fails —
    a single upstream failure never propagates (rule 11). This is the runtime-soft path
    (rule 14): providers are tried in order and failures are logged, not fatal.
    """
    errors: list[str] = []
    for name, fn in (("gemini", _gen_gemini), ("groq", _gen_groq)):
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
