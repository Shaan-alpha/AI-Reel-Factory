"""Module 3 — Scriptwriter.

Contract:
    what it does : turns an approved idea (+ its sources) into a script via a template.
    input        : idea dict {id, title, hook, angle, sources, ...}; template name (default 'N').
    output       : {script_id, script_body, caption, hashtags[]} — also written to `scripts`.
    depends on   : src.llm, src.db, templates/*.md (design source), src.config.

ORIGINALITY IS THE MONETIZATION GATE (docs/08 §1): the script's core value is the
"why it matters" ANALYSIS, not a summary. Rewrite facts in own words + cite. Caption must
include source links + an AI-disclosure line. Keyword-rich title (SEO). Append #Shorts.

The compliance requirements (source links, AI-disclosure line, #Shorts) are enforced in
code AFTER the LLM responds — never trusted to the model, because they gate monetization.
The executable prompt below mirrors templates/template-N-news-impact.md (the design source);
keep the two in sync.
"""
from __future__ import annotations

import json
import logging

from src import db, llm

log = logging.getLogger(__name__)

# Minimal compliant disclosure (docs/08 §2). The primary disclosure is YouTube's
# synthetic-content FLAG set on upload (publish_youtube); this short line is the discreet
# description backup. Removing disclosure entirely risks forced labels + YPP suspension and
# does NOT help reach (researched 2026-06-09), so we keep a minimal honest line.
DISCLOSURE_LINE = "AI-generated narration; stock visuals."

# Only Template N is in the Phase-1 MVP (rule 9 / YAGNI). The others exist as docs.
_SUPPORTED_TEMPLATES = ("N",)

_PROMPT_N = """You are the scriptwriter for "But It Matters" — punchy, fast-paced YouTube Shorts \
that make people STOP scrolling. Your voice is NATURAL and conversational with a bit of edge — \
like a sharp friend who tells you something wild and makes it click. Energetic and gripping, \
never a stiff news-anchor, never forced or corny. Every FACT stays 100% accurate.

IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES:
{sources}

Write a ~110-130 word (<=45s) narration that FLOWS naturally when spoken out loud:
1. HOOK (first 3s): a scroll-stopping opener — a surprising fact, bold claim, or curiosity gap \
that makes the viewer go "wait, what?". Make it THRILLING and specific. No "in this video", no \
throat-clearing.
2. WHAT HAPPENED: 1-2 real facts in your own words, citing the source out loud ("according to ..."). \
Keep it true — the energy is in the delivery, never in exaggeration.
3. WHY IT MATTERS: the real stakes, with a little bite — why anyone should actually care.
4. PAYOFF: what it means for you / India / the world.
5. CTA: one natural, snappy line to follow or comment.

WRITE FOR THE EAR: short punchy sentences, contractions, natural rhythm, a touch of wit. It must \
sound like a real person talking, not an essay. No hateful or personal attacks; punch at ideas \
and irony, not people.

Return ONLY a JSON object, no markdown fences:
{{"script_body": "the spoken narration", "caption": "keyword-rich SEO description \
including the source link(s)", "hashtags": ["#keyword", "#Shorts"]}}
"""


def _build_prompt(idea: dict, template: str) -> str:
    if template != "N":  # only N is wired in MVP; guard keeps unsupported templates loud
        raise ValueError(
            f"unsupported template {template!r} (MVP supports {_SUPPORTED_TEMPLATES}); "
            "see templates/ for the others (Phase 2)."
        )
    sources = idea.get("sources") or []
    sources_block = "\n".join(f"- {s}" for s in sources) or "- (none provided)"
    return _PROMPT_N.format(
        title=idea.get("title", ""),
        hook=idea.get("hook", ""),
        angle=idea.get("angle", ""),
        sources=sources_block,
    )


def _parse_llm_json(raw: str) -> dict:
    """Extract the JSON object from the LLM reply (tolerant of fences / surrounding prose)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"scriptwriter: no JSON object in LLM reply: {raw[:200]!r}")
    return json.loads(raw[start : end + 1], strict=False)  # tolerate raw control chars in strings


def _ensure_sources(caption: str, sources: list[str]) -> str:
    """Guarantee every source URL is present in the caption (copyright/sourcing gate)."""
    missing = [s for s in sources if s and s not in caption]
    if not missing:
        return caption
    block = "Sources: " + " | ".join(missing)
    return f"{caption.rstrip()}\n\n{block}" if caption.strip() else block


def _ensure_disclosure(caption: str) -> str:
    """Guarantee the AI-disclosure line is present (docs/08 §2 — required)."""
    if "ai-generated" in caption.lower():
        return caption
    return f"{caption.rstrip()}\n{DISCLOSURE_LINE}" if caption.strip() else DISCLOSURE_LINE


def _ensure_shorts(hashtags: list[str]) -> list[str]:
    """Guarantee #Shorts is present (YouTube classifies the upload as a Short)."""
    if any(h.lower() == "#shorts" for h in hashtags):
        return hashtags
    return [*hashtags, "#Shorts"]


def write_script(idea: dict, template: str = "N") -> dict:
    """Generate {script_body, caption, hashtags[]} for an approved idea and persist it.

    Returns the same dict plus the new `script_id`. Raises ValueError if the LLM reply
    can't be parsed into a non-empty script (caller skips that one reel — rule 14: soft on
    runtime). Compliance fields (sources, disclosure, #Shorts) are enforced here, not trusted
    to the model.
    """
    idea_id = idea.get("id")
    if idea_id is None:
        raise ValueError("scriptwriter: idea has no 'id' (must be a persisted ideas row).")

    raw = llm.generate(_build_prompt(idea, template), json=True, max_tokens=2048)
    data = _parse_llm_json(raw)

    body = (data.get("script_body") or "").strip()
    if not body:
        raise ValueError(f"scriptwriter: empty script_body for idea {idea_id}.")

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = _ensure_shorts([str(h) for h in hashtags])

    caption = _ensure_disclosure(_ensure_sources(data.get("caption") or "", idea.get("sources") or []))

    words = len(body.split())
    if not 90 <= words <= 200:  # ~130-150 target; warn on a wild miss, don't block (rule 14)
        log.warning("scriptwriter: idea %s script is %d words (target ~130-150)", idea_id, words)

    script_id = db.insert_script(idea_id, template, body, caption, hashtags)
    return {"script_id": script_id, "script_body": body, "caption": caption, "hashtags": hashtags}
