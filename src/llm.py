"""LLM helper — Gemini primary, Groq failover (rule 11: fallbacks mandatory).

Contract:
    what it does : one entry point for free-tier text generation; transparent failover.
    how to use   : `from src.llm import generate; text = generate(prompt, json=True)`
    depends on   : google-generativeai, groq, src.config (GEMINI_API_KEY, GROQ_API_KEY).

Used by the scriptwriter (Module 3) and the ideation fallback. NOT used for Claude —
Claude ideation runs only in the Routine (rule 4). Respect free-tier quotas (rule 13).

STATUS: stub.
"""
from __future__ import annotations


def generate(prompt: str, *, json: bool = False, max_tokens: int = 1024) -> str:
    """Generate text via Gemini; on error/quota, fail over to Groq. Return raw text.

    Set json=True when the prompt asks for a JSON object (callers parse the result).
    """
    raise NotImplementedError("llm.generate — see docs/02-implementation-plan.md §4")
