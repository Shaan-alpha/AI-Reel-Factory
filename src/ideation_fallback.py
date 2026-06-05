"""Module 1 (fallback) — free-API ideation when the Claude Routine didn't run.

Contract:
    what it does : produces the same idea rows as routines/ideation.md, via Gemini/Groq.
    how to use   : `run_fallback_ideation()` — called by the orchestrator only when
                   Supabase has no pending ideas for today (rule 11/12).
    depends on   : src.llm, src.db, src.config.

ToS (rule 4): this uses the Gemini/Groq DEVELOPER APIs — never Claude. Same JSON contract
and the same sensitivity/sourcing rules as the Routine (docs/08-news-niche-playbook.md).

STATUS: stub. Mirror routines/ideation.md exactly so output is interchangeable.
"""
from __future__ import annotations


def run_fallback_ideation() -> int:
    """Generate 15–20 ideas and insert them as 'pending'. Return the count inserted."""
    raise NotImplementedError(
        "ideation_fallback.run_fallback_ideation — see docs/02-implementation-plan.md §2"
    )
