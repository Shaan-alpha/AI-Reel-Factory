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
import re

from src import config, db, llm, news, trends

log = logging.getLogger(__name__)

_MAX_IDEAS = 20
_MIN_IDEAS = 5  # below this, treat the run as failed rather than ship a thin digest

# Columns the `ideas` table actually has — `share_score` is ranking-only, never persisted.
_ROW_KEYS = ("niche", "title", "hook", "angle", "est_score", "sources")


def _to_rows(ideas: list[dict]) -> list[dict]:
    """Project validated ideas to the DB columns (drops ranking-only fields like share_score)."""
    return [{k: idea[k] for k in _ROW_KEYS} for idea in ideas]


def _rank_key(idea: dict):
    """Sort key: share_score first (virality), est_score as tiebreaker. Highest first."""
    return (-idea.get("share_score", idea["est_score"]), -idea["est_score"])


# Tiny stopword set so near-identical titles overlap on meaningful words, not glue words.
_STOPWORDS = {"the", "a", "an", "of", "to", "in", "for", "and", "is", "on", "with",
              "at", "by", "from", "as", "new", "today"}


def _tokens(title: str) -> set[str]:
    """Significant lowercased word tokens of a title (numbers kept, stopwords dropped)."""
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOPWORDS}

# The daily Anthropic Routine (Claude + web research) commits its ideas here; the on-demand
# flow prefers these over the Gemini/Groq fallback. See routines/ideation.md.
_ROUTINE_IDEAS_FILE = "data/daily-ideas.json"

_PROMPT = """You are the ideation engine for "But It Matters", a channel of daily, punchy \
**25-30 second** news/info Shorts (India + world). Turn the SELECTED stories below into {n} \
TIMELY ideas a human will approve 4-5 of — each a single crisp on-point fact that still carries \
one honest "why it matters" angle (not a bare summary), with strong scroll-stopping, \
share-worthy potential.

SELECTED DISTINCT STORIES (write EXACTLY ONE idea per story, in order; NEVER two ideas on the \
same event):
{selected}

PRIMARY ANCHOR — REAL CURRENT HEADLINES (verify the facts against these; prefer these real \
stories over generic evergreen topics):
{headlines}

SUPPLEMENTARY TREND SIGNAL (optional flavour only; ignore generic weather/calendar/sports-score noise):
{trending}

WINNING TITLE STYLES ON THIS CHANNEL (these actual published titles + view counts show what the \
feed rewards — copy the ENERGY and framing, never the exact title; if empty, ignore):
{winners}

HONEST SCROLL APPEAL: pick the angle a smart person finds genuinely surprising or consequential \
— real stakes, money & power, conflict with real consequences, science/space, big human impact. \
The hook must be a TRUE curiosity gap the explainer can actually CLOSE (a bait topic the facts \
can't support gets suppressed). Apply a SHARE TEST: would someone send this to a friend? Set \
share_score by that; set est_score by how strong an HONEST hook plus a real "why it matters" \
angle the story supports — never by how dramatic a title you could slap on it.

SCORE CALIBRATION (IMPORTANT): RANK the ideas against each OTHER and SPREAD the scores across the \
full 0.0-1.0 range — do NOT give everything ~1.0. The strongest single idea may approach 1.0, the \
weakest should sit near 0.3-0.5, and the rest in between. Use DISTINCT share_score values so the \
list has a clear best-to-worst order; est_score may differ from share_score per idea.

ACCURACY (CRITICAL — this is the #1 rule): propose only REAL, verifiable developments that \
ACTUALLY happened recently. NEVER invent product names, version numbers, launches, statistics, \
quotes, or events, and never attribute a claim to a company/person unless it's real. If unsure a \
thing genuinely happened, DO NOT make it up — choose a different real story. When unsure, \
generalize truthfully rather than invent specifics. Fabricated news = instant demonetization and strikes.

FRAMING RULES (monetization safety): strictly NEUTRAL and factual — explain what happened and \
why it matters; never take political sides or editorialize. Politics, government actions, and \
court rulings ARE allowed when covered neutrally and well-sourced. EXCLUDE only: communal/ \
religious incitement or hate; anything that could inflame violence; unverified rumors/claims \
stated as fact; deepfakes/impersonation; graphic tragedy exploitation; medical/financial advice \
stated as fact.

Each idea: a PUNCHY, curiosity-driven title honest to the story (NOT a dry "X explained" search \
title, NOT a bait title the facts can't back); a story that lands in 25-30 seconds (a single \
development with a sharp angle, not a deep-dive); >= {min_src} reputable, independent source URLs \
from real outlets (never invent URLs); a "hook" that is a genuine first-2-seconds scroll-stopper \
(one surprising true fact); and a share_score.

Return ONLY JSON:
{{"ideas": [{{"niche": "impact-news", "title": "...", "hook": "the first 3 seconds", \
"angle": "the original why-it-matters take", "est_score": 0.0, "share_score": 0.0, \
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
    kept_tokens: list[set[str]] = []
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
        toks = _tokens(title)
        if toks and any(len(toks & kt) / len(toks | kt) >= 0.6 for kt in kept_tokens):
            log.debug("ideation_fallback: dropping near-duplicate %r", title)
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
        try:
            share = float(idea.get("share_score", est))
        except (TypeError, ValueError):
            share = est
        share = min(1.0, max(0.0, share))

        seen_titles.add(title.lower())
        kept_tokens.append(toks)
        clean.append({"niche": niche, "title": title, "hook": hook, "angle": angle,
                      "est_score": est, "share_score": share, "sources": sources})
        if len(clean) >= _MAX_IDEAS:
            break
    return clean


_STAGE1_PROMPT = """You are the story scout for "But It Matters", a channel of daily 25-30 \
second news/info Shorts (India + world). From the REAL headlines below, choose the {n} MOST \
share-worthy, DISTINCT stories to turn into Shorts today.

PRIMARY SOURCE — REAL CURRENT HEADLINES (choose from THESE; cluster items about the same event \
into ONE story):
{headlines}

SUPPLEMENTARY TREND SIGNAL (optional flavour only; ignore generic weather/calendar/sports-score noise):
{trending}

WINNING STYLES ON THIS CHANNEL (what the feed rewards; pick stories with similar pull — if empty, ignore):
{winners}

RULES:
- Pick {n} DISTINCT stories — NEVER two about the same event. Spread them across DIFFERENT \
categories (world affairs, economy & business, science & space, technology & AI, health, \
climate & energy, India infrastructure, government & policy, sports, notable world events).
- Prefer stories a smart person would actually SEND TO A FRIEND: real stakes, money & power, \
genuine surprise, big human impact. Apply a SHARE test, not a clickbait test.
- Compliance (hard line): only real, verifiable developments; neutral framing; exclude \
communal/religious incitement, calls to violence, unverified rumour-as-fact, deepfakes, \
graphic tragedy exploitation, medical/financial advice.

Return ONLY a JSON object:
{{"stories": [{{"story": "one-line description of the single development", "category": "...", \
"why_shareworthy": "why someone would share this"}}]}}
"""


def _select_stories(target: int, headlines: list[str], trending: list[str],
                    winners: list[str]) -> list[dict]:
    """Stage 1: cluster real headlines into `target` DISTINCT share-worthy stories.

    Cheap, no-web pass routed to Groq first (rule 13) so Gemini's scarce grounded RPD is
    reserved for Stage 2. Returns [] when there are no headlines or on any failure (rule 11),
    so the caller falls back to expanding from headlines directly.
    """
    if not headlines:
        return []
    prompt = _STAGE1_PROMPT.format(
        n=target,
        headlines="\n".join(f"- {h}" for h in headlines),
        trending="\n".join(f"- {t}" for t in trending) or "- (none)",
        winners="\n".join(f"- {w}" for w in winners) or "- (no performance data yet)",
    )
    try:
        raw = llm.generate(prompt, json=True, max_tokens=2048, prefer_groq=True)
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1], strict=False)
        stories = data.get("stories", []) if isinstance(data, dict) else []
        out: list[dict] = []
        for s in stories:
            if isinstance(s, dict) and str(s.get("story", "")).strip():
                out.append({
                    "story": str(s["story"]).strip(),
                    "category": str(s.get("category", "")).strip(),
                    "why_shareworthy": str(s.get("why_shareworthy", "")).strip(),
                })
        return out[:target]
    except Exception as e:  # noqa: BLE001 — selection is best-effort; never block ideation
        log.warning("ideation: stage-1 story selection failed (%s); expanding from headlines", e)
        return []


def _produce_ideas(target: int) -> list[dict]:
    """Two-stage: select DISTINCT share-worthy stories (Stage 1), then expand them (Stage 2).

    Stage 1 (Groq) clusters real headlines into distinct stories — the anti-clustering /
    diversity mechanism. Stage 2 expands via Gemini Google Search grounding for current,
    well-sourced ideas, falling back to ungrounded generation if grounding is unavailable.
    Freshness survives a grounding outage because Stage 2 still expands real current headlines.
    """
    topics = trends.fetch_trending(15)
    trending_block = "\n".join(f"- {t}" for t in topics) or \
        "- (live trends unavailable — rely on the headlines below)"
    headlines = news.fetch_headlines(12)
    headlines_block = "\n".join(f"- {h}" for h in headlines) or \
        "- (no live headlines — use your knowledge of today's biggest REAL stories)"
    try:
        winners = db.top_performing_titles(6)
    except Exception as e:  # noqa: BLE001 — analytics feedback is best-effort
        log.warning("ideation: could not load past winners (%s)", e)
        winners = []
    winners_block = "\n".join(f"- {w}" for w in winners) or "- (no performance data yet)"

    stories = _select_stories(target, headlines, topics, winners)
    if stories:
        selected_block = "\n".join(
            f"- {s['story']}" + (f" [{s['category']}]" if s["category"] else "")
            for s in stories
        )
    else:
        selected_block = ("- (no pre-selected stories — choose DISTINCT, current, "
                          "share-worthy stories yourself; never two on the same event)")

    prompt = _PROMPT.format(n=target, min_src=config.get("MIN_SOURCES", "2"),
                            selected=selected_block, trending=trending_block,
                            headlines=headlines_block, winners=winners_block)
    # Stage 2: web-grounded first, INCLUDING the parse — grounded JSON is sometimes
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

    inserted = db.insert_ideas(_to_rows(clean))
    log.info("ideation_fallback: inserted %d pending ideas.", len(inserted))
    return len(inserted)


def generate_ideas(n: int = 3) -> int:
    """On-demand: generate the best ~n fresh ideas and insert as 'pending'. Return the count.

    Unlike run_fallback_ideation, this has NO pending-queue guard — an explicit on-demand
    request always produces fresh options (the operator picks via the digest buttons).
    """
    n = max(1, n)
    clean = sorted(_produce_ideas(max(n * 2, 4)), key=_rank_key)[:n]
    if not clean:
        raise RuntimeError("ideation: could not generate any valid idea.")
    inserted = db.insert_ideas(_to_rows(clean))
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
    fresh = sorted((i for i in pool if i["title"].lower() not in seen), key=_rank_key)[:n]
    if not fresh:
        raise RuntimeError(f"ideation: no fresh ideas to seed (source: {source}).")
    log.info("ideation: seeding %d idea(s) from %s.", len(fresh), source)
    return len(db.insert_ideas(_to_rows(fresh)))
