"""Module 1 (fallback) — free-API ideation when the Claude Routine didn't run.

Contract:
    what it does : produces the same idea rows as routines/ideation.md, via Gemini/Groq.
    how to use   : `run_fallback_ideation()` — called by the orchestrator only when
                   Supabase has no pending ideas for today (rule 11/12).
    depends on   : src.llm, src.db, src.config.

ToS (rule 4): this uses the Gemini/Groq DEVELOPER APIs — never Claude. Same JSON contract
and the same sensitivity/sourcing rules as the Routine (docs/08-news-niche-playbook.md).

CAVEAT (honesty over polish): unlike the Claude Routine, the free dev APIs have no live web
search here, so model-supplied source URLs may be stale/uncertain. This is a rare-day backup;
the human Telegram approval is the safety net, and the scriptwriter still cites sources. Ideas
that don't carry >= MIN_SOURCES plausible URLs are dropped rather than shipped unsourced.
"""
from __future__ import annotations

import json
import logging

from src import config, db, llm

log = logging.getLogger(__name__)

_MAX_IDEAS = 20
_MIN_IDEAS = 5  # below this, treat the run as failed rather than ship a thin digest

_PROMPT = """You are the ideation engine for "But It Matters", a channel of daily impact \
news/info explainers (India + world), soft/positive-impact lean. Generate {n} ideas a human \
will approve 4-5 of, each enabling ORIGINAL "why it matters" analysis (not a summary).

Lean into: science & space (ISRO, missions), technology & AI, economy & business, health & \
medicine, climate & energy, big constructive policy/law, neutral global affairs, India \
growth/infrastructure, world-firsts & breakthroughs.

EXCLUDE (sensitivity filter): active communal/religious flashpoints, inflammatory partisan \
conflict, unverified election claims, deepfake/impersonation, graphic violence/tragedy \
exploitation, medical/financial advice stated as fact.

Rules: neutral factual framing; one development per idea; keyword-rich search-style titles \
("X explained", "what ... means", "why ... matters", + India/world/year). Provide >= {min_src} \
reputable, independent source URLs per idea from real outlets; do not invent URLs.

Return ONLY JSON:
{{"ideas": [{{"niche": "impact-news", "title": "...", "hook": "the first 3 seconds", \
"angle": "the original why-it-matters take", "est_score": 0.0, \
"sources": ["https://...", "https://..."]}}]}}
"""


def _parse_ideas(raw: str) -> list[dict]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"ideation_fallback: no JSON object in reply: {raw[:200]!r}")
    data = json.loads(raw[start : end + 1])
    ideas = data.get("ideas", data if isinstance(data, list) else [])
    if not isinstance(ideas, list):
        raise ValueError("ideation_fallback: 'ideas' is not a list.")
    return ideas


def _clean_sources(raw_sources) -> list[str]:
    if not isinstance(raw_sources, list):
        return []
    seen, out = set(), []
    for s in raw_sources:
        s = str(s).strip()
        if s.lower().startswith(("http://", "https://")) and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _validate_and_clean(ideas: list[dict]) -> list[dict]:
    """Keep well-formed, sufficiently-sourced, de-duplicated ideas; coerce fields."""
    min_src = int(config.get("MIN_SOURCES", "2"))
    niche = config.get("NICHE", "impact-news")
    seen_titles: set[str] = set()
    clean: list[dict] = []

    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        title = str(idea.get("title", "")).strip()
        hook = str(idea.get("hook", "")).strip()
        angle = str(idea.get("angle", "")).strip()
        if not (title and hook and angle):
            continue
        if title.lower() in seen_titles:
            continue
        sources = _clean_sources(idea.get("sources"))
        if len(sources) < min_src:
            log.debug("ideation_fallback: dropping %r (<%d sources)", title, min_src)
            continue
        try:
            est = float(idea.get("est_score", 0.5))
        except (TypeError, ValueError):
            est = 0.5
        est = min(1.0, max(0.0, est))

        seen_titles.add(title.lower())
        clean.append({"niche": niche, "title": title, "hook": hook, "angle": angle,
                      "est_score": est, "sources": sources})
        if len(clean) >= _MAX_IDEAS:
            break
    return clean


def run_fallback_ideation() -> int:
    """Generate 15-20 ideas and insert them as 'pending'. Return the count inserted.

    Idempotent (rule 12): if pending ideas already exist, do nothing and return 0 — a cron
    retry must not stack a second digest.
    """
    if db.get_pending_ideas():
        log.info("ideation_fallback: pending ideas already exist; skipping (idempotent).")
        return 0

    raw = llm.generate(_PROMPT.format(n=18, min_src=config.get("MIN_SOURCES", "2")),
                       json=True, max_tokens=4096)
    clean = _validate_and_clean(_parse_ideas(raw))
    if len(clean) < _MIN_IDEAS:
        raise RuntimeError(
            f"ideation_fallback: only {len(clean)} valid ideas (need >= {_MIN_IDEAS}); "
            "not inserting a thin digest."
        )

    inserted = db.insert_ideas(clean)
    log.info("ideation_fallback: inserted %d pending ideas.", len(inserted))
    return len(inserted)
