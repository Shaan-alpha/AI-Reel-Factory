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
import os

from src import config, db, llm, trends

log = logging.getLogger(__name__)

_MAX_IDEAS = 20
_MIN_IDEAS = 5  # below this, treat the run as failed rather than ship a thin digest

# The daily Anthropic Routine (Claude + web research) commits its ideas here; the on-demand
# flow prefers these over the Gemini/Groq fallback. See routines/ideation.md.
_ROUTINE_IDEAS_FILE = "data/daily-ideas.json"

_PROMPT = """You are the ideation engine for "But It Matters", a channel of daily news/info \
explainers (India + world). Generate {n} TIMELY, TRENDING ideas a human will approve 4-5 of, \
each enabling ORIGINAL "why it matters" analysis (not a bare summary).

TODAY'S TRENDING IN INDIA (prefer ideas tied to these where a solid, factual explainer fits):
{trending}

Cover what people are searching for NOW across: current affairs, government & policy, major \
court/legal rulings, economy & business, science & space (ISRO), technology & AI, health, \
climate & energy, India infrastructure, sports, and notable world events. Be CURRENT, not generic.

FRAMING RULES (monetization safety): strictly NEUTRAL and factual — explain what happened and \
why it matters; never take political sides or editorialize. Politics, government actions, and \
court rulings ARE allowed when covered neutrally and well-sourced. EXCLUDE only: communal/ \
religious incitement or hate; anything that could inflame violence; unverified rumors/claims \
stated as fact; deepfakes/impersonation; graphic tragedy exploitation; medical/financial advice \
stated as fact.

Each idea: keyword-rich search-style title ("X explained", "what ... means", "why ... matters", \
+ India/world/year); >= {min_src} reputable, independent source URLs from real outlets; never \
invent URLs.

Return ONLY JSON:
{{"ideas": [{{"niche": "impact-news", "title": "...", "hook": "the first 3 seconds", \
"angle": "the original why-it-matters take", "est_score": 0.0, \
"sources": ["https://...", "https://..."]}}]}}
"""


def _parse_ideas(raw: str) -> list[dict]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"ideation_fallback: no JSON object in reply: {raw[:200]!r}")
    # strict=False: grounded LLM JSON often has raw newlines/tabs inside string values.
    data = json.loads(raw[start : end + 1], strict=False)
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


def _produce_ideas(target: int) -> list[dict]:
    """Ask the LLM for ~target ideas and return the validated/cleaned subset.

    Researches the live web via Gemini Google Search grounding for current, well-sourced
    ideas; falls back to ungrounded generation (Gemini→Groq) if grounding is unavailable.
    """
    topics = trends.fetch_trending(15)
    trending_block = "\n".join(f"- {t}" for t in topics) or \
        "- (live trends unavailable — use your own knowledge of today's biggest stories)"
    prompt = _PROMPT.format(n=target, min_src=config.get("MIN_SOURCES", "2"), trending=trending_block)
    # Try web-grounded research first, INCLUDING the parse — grounded JSON is sometimes
    # malformed/truncated, so any failure falls back to the reliable ungrounded JSON-mode call.
    try:
        raw = llm.generate_grounded(prompt, max_tokens=8192)
        ideas = _validate_and_clean(_parse_ideas(raw))
        if ideas:
            return ideas
        raise ValueError("grounded response yielded no valid ideas")
    except Exception as e:  # noqa: BLE001 — grounding is best-effort; never block ideation
        log.warning("ideation: grounded research unusable (%s); using ungrounded JSON mode", e)

    raw = llm.generate(prompt, json=True, max_tokens=4096)
    return _validate_and_clean(_parse_ideas(raw))


def run_fallback_ideation() -> int:
    """Generate 15-20 ideas and insert them as 'pending'. Return the count inserted.

    Idempotent (rule 12): if pending ideas already exist, do nothing and return 0 — a cron
    retry must not stack a second digest.
    """
    if db.get_pending_ideas():
        log.info("ideation_fallback: pending ideas already exist; skipping (idempotent).")
        return 0

    clean = _produce_ideas(18)
    if len(clean) < _MIN_IDEAS:
        raise RuntimeError(
            f"ideation_fallback: only {len(clean)} valid ideas (need >= {_MIN_IDEAS}); "
            "not inserting a thin digest."
        )

    inserted = db.insert_ideas(clean)
    log.info("ideation_fallback: inserted %d pending ideas.", len(inserted))
    return len(inserted)


def generate_ideas(n: int = 3) -> int:
    """On-demand: generate the best ~n fresh ideas and insert as 'pending'. Return the count.

    Unlike run_fallback_ideation, this has NO pending-queue guard — an explicit on-demand
    request always produces fresh options (the operator picks via the digest buttons).
    """
    n = max(1, n)
    clean = sorted(_produce_ideas(max(n * 2, 4)), key=lambda d: -d["est_score"])[:n]
    if not clean:
        raise RuntimeError("ideation: could not generate any valid idea.")
    inserted = db.insert_ideas(clean)
    log.info("ideation: generated %d on-demand idea(s).", len(inserted))
    return len(inserted)


def load_routine_ideas() -> list[dict]:
    """Load + validate ideas the daily Anthropic Routine committed to the repo. [] if none."""
    if not os.path.exists(_ROUTINE_IDEAS_FILE):
        return []
    try:
        with open(_ROUTINE_IDEAS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("ideation: could not read %s (%s)", _ROUTINE_IDEAS_FILE, e)
        return []
    ideas = raw.get("ideas", []) if isinstance(raw, dict) else raw
    return _validate_and_clean(ideas if isinstance(ideas, list) else [])


def seed_ideas(n: int = 3) -> int:
    """Seed ~n fresh 'pending' ideas for the on-demand digest. Return the count inserted.

    Prefers the daily Routine's web-researched ideas (data/daily-ideas.json); falls back to
    the Gemini/Groq generator when that file is absent/empty. De-duplicates against ideas
    already in the table so repeated triggers don't re-propose the same ones.
    """
    n = max(1, n)
    routine = load_routine_ideas()
    pool = routine if routine else _produce_ideas(max(n * 2, 4))
    source = "routine file" if routine else "gemini/groq fallback"

    seen = db.existing_idea_titles()
    fresh = sorted((i for i in pool if i["title"].lower() not in seen),
                   key=lambda d: -d["est_score"])[:n]
    if not fresh:
        raise RuntimeError(f"ideation: no fresh ideas to seed (source: {source}).")
    log.info("ideation: seeding %d idea(s) from %s.", len(fresh), source)
    return len(db.insert_ideas(fresh))
