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

from src import config, db, llm

log = logging.getLogger(__name__)

# Minimal compliant disclosure (docs/08 §2). The primary disclosure is YouTube's
# synthetic-content FLAG set on upload (publish_youtube); this short line is the discreet
# description backup. Removing disclosure entirely risks forced labels + YPP suspension and
# does NOT help reach (researched 2026-06-09), so we keep a minimal honest line.
DISCLOSURE_LINE = "AI-generated narration; stock visuals."

# Only Template N is in the Phase-1 MVP (rule 9 / YAGNI). The others exist as docs.
_SUPPORTED_TEMPLATES = ("N",)

_PROMPT_N = """You are the scriptwriter for "But It Matters" — fast, punchy YouTube Shorts that \
make people stop scrolling with HONEST curiosity, then reward them with a genuinely useful \
"why it matters" insight. Your voice is NATURAL and conversational with real edge — a sharp \
friend explaining why something actually matters. Energetic and gripping, never a stiff \
news-anchor. The hook is strong but TRUE: the title and opening must sit honestly on what the \
video actually delivers — a click-then-bounce from an over-claim gets the channel suppressed.

IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES:
{sources}

WHAT WINS ON THIS CHANNEL: a curiosity gap the video actually CLOSES. Lead with the single most \
interesting TRUE fact or tension, then pay it off with real analysis. Stories with real stakes — \
money & power, conflict with consequences, science, big human impact — travel, but the pull must \
come from the REAL story framed honestly, never from a title the body can't cash. Promise == payoff.

Write a ~110-130 word (<=45s) narration that FLOWS naturally when spoken out loud:
1. HOOK (first 3s — THE most important line): an honest, scroll-stopping opener — the most \
surprising TRUE fact, a real stakes question, or a genuine curiosity loop you WILL close at the \
end. Make them want the answer, then deliver it. No "in this video", no throat-clearing, no \
over-claim the body can't back up.
2. WHAT HAPPENED: 1-2 real facts in your own words, citing the source out loud ("according to ..."). \
Deliver them with stakes and tension — the drama is in HOW you say a true thing.
3. WHY IT MATTERS: the real stakes, with bite — why this is a bigger deal than it looks.
4. PAYOFF: pay off the loop you opened — the twist / what it really means for you / India / the world.
5. CTA + SEAMLESS LOOP: one punchy line that also loops back into the hook, so when the Short \
auto-replays the last words flow naturally into your first line (Shorts replay = more watch-time = \
more reach). End on a phrase that re-sets the opening question. ("comment if this shocked you", \
"follow before the next one").

WRITE FOR THE EAR: short punchy sentences, contractions, natural rhythm, building tension. Sound \
like a real person who's genuinely amped, not an essay. No hateful or personal attacks; punch at \
situations and irony, not people (harassment = demonetization).

ACCURACY (THE ONE HARD LINE — everything else is hype, this is not): VERIFY the development actually \
happened (use the sources + web search). State ONLY facts you can support. NEVER invent product \
names, version numbers, figures, dates, quotes, or events, and never say "according to <company>" \
unless it's real. Hype the FRAMING, never fabricate the STORY — a made-up fact gets the channel \
struck and demonetized, which kills the views. If the premise doesn't check out, write the most \
dramatic ACCURATE version instead.

ALSO produce, for the feed + discoverability:
- "title": a clear, curiosity-driven YouTube title (<=70 chars) that is TRUE to the video — a \
real curiosity gap, an honest number, or genuine stakes. Front-load the most interesting REAL \
word. It must NOT promise anything the narration doesn't deliver (mismatch gets suppressed). \
Examples of the honest-but-gripping energy: "India's new gas rule quietly changes your kitchen \
bill", "Why Venezuela just out-priced Iraq on oil", "ISRO's rocket landed itself — here's the catch".
- "caption": the YouTube description. FIRST LINE is a second curiosity hook (YouTube shows ~2 lines \
in-feed) — make them tap "more". Then a keyword-rich line for SEO, then the source link(s).
- "tags": 10-15 specific search keywords/phrases people would actually type (the topic, the \
people/orgs involved, the category, and close synonyms). No '#'.

Return ONLY a JSON object, no markdown fences:
{{"title": "the VIRAL title", "script_body": "the spoken narration", "caption": "hook line first, \
then keyword-rich SEO description including the source link(s)", "hashtags": ["#keyword", "#Shorts"], \
"tags": ["search keyword", "another phrase"]}}
"""


def _build_prompt(idea: dict, template: str) -> str:
    if template != "N":  # only N is wired in MVP; guard keeps unsupported templates loud
        raise ValueError(
            f"unsupported template {template!r} (MVP supports {_SUPPORTED_TEMPLATES}); "
            "see templates/ for the others (Phase 2)."
        )
    sources = idea.get("sources") or []
    sources_block = "\n".join(f"- {s}" for s in sources) or "- (none provided)"
    prompt = _PROMPT_N.format(
        title=idea.get("title", ""),
        hook=idea.get("hook", ""),
        angle=idea.get("angle", ""),
        sources=sources_block,
    )
    # The human "why it matters" take is the originality + anti-"AI-slop" signal (2026 policy).
    if config.get_bool("ENABLE_HUMAN_ANGLE", True):
        prompt += ("\n\nEMPHASIS: the \"why it matters\" analysis is the point of the video — make "
                   "it a genuine, specific human take, not a generic restatement.")
    return prompt


def _parse_llm_json(raw: str) -> dict:
    """Extract the JSON object from the LLM reply (tolerant of fences / surrounding prose)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"scriptwriter: no JSON object in LLM reply: {raw[:200]!r}")
    return json.loads(raw[start : end + 1], strict=False)  # tolerate raw control chars in strings


def _generate_script_json(prompt: str) -> dict:
    """Write the script with live web-grounding (verifies facts), falling back to ungrounded
    JSON mode if grounding is unavailable or returns unusable JSON. Accuracy guard for a public
    channel — grounding lets the model catch a fabricated premise instead of repeating it."""
    try:
        data = _parse_llm_json(llm.generate_grounded(prompt, max_tokens=2048))
        if (data.get("script_body") or "").strip():
            return data
    except Exception as e:  # noqa: BLE001 — grounded write is best-effort; fall back
        log.warning("scriptwriter: grounded write unusable (%s); using ungrounded JSON mode", e)
    return _parse_llm_json(llm.generate(prompt, json=True, max_tokens=2048))


# A cheap free-API pass that scores the opening hook and, only if it's weak, sharpens the title +
# opening for more scroll-stop — WITHOUT touching any fact (accuracy is the hard line). Fail-soft:
# any error or a bad rewrite keeps the original. Toggle ENABLE_HOOK_JUDGE; threshold HOOK_MIN_SCORE.
_PUNCHUP_PROMPT = """You are a world-class viral YouTube Shorts hook doctor. You make the first \
3 seconds impossible to scroll past. Below is a Short's title and narration.

TITLE: {title}
NARRATION:
{body}

STEP 1 — Score the CURRENT opening line (the first ~3 seconds) from 1 to 10 on raw scroll-stopping \
power: 10 = a shocking, curiosity-exploding hook nobody could scroll past; 1 = a flat, slow, \
"explainer" intro.

STEP 2 — Rewrite for stronger HONEST pull (only when the score is below 7, i.e. genuinely flat):
- TITLE: a clear curiosity gap or real stakes, front-loading the most interesting TRUE word. It \
must stay honest to the narration — never promise something the body doesn't deliver.
- OPENING: replace the first 1-2 sentences with a stronger TRUE hook — the most surprising fact \
already in the script, or a real question the viewer needs answered. Keep the rest of the narration.

HARD RULE — DO NOT add, remove, or change any FACT, name, number, date, quote, statistic, or claim. \
Every factual statement must stay exactly as true as the original. You may ONLY re-word, re-order, \
and intensify the DELIVERY. Keep the narration roughly the same length (~110-130 words) and keep \
the closing CTA / loop-back line.

OUTPUT — return ONE valid JSON object and NOTHING else. No markdown, no code fences, no commentary:
{{"hook_score": 7, "title": "the punchier title", "script_body": "the full narration with a punchier opening"}}
"""


def _punch_up_hook(title: str, body: str) -> tuple[str, str]:
    """Optionally sharpen a weak hook+title via a cheap LLM pass. Returns (title, body).

    Best-effort (rule 11/14): on any failure, a high score, or an invalid rewrite, returns the
    originals unchanged. Never adds facts — the prompt forbids it and the sources/caption are
    untouched, so monetization compliance is unaffected."""
    if not body.strip():
        return title, body
    try:
        # prefer_groq: this is a no-web creative task → keep Gemini's scarce RPD for grounded
        # research (rule 13). Groq's llama-3.3-70b handles punch-up copy at least as well.
        data = _parse_llm_json(
            llm.generate(_PUNCHUP_PROMPT.format(title=title, body=body),
                         json=True, max_tokens=2048, prefer_groq=True)
        )
    except Exception as e:  # noqa: BLE001 — punch-up is optional; keep the original on any error
        log.warning("scriptwriter: hook punch-up failed (%s); keeping original.", e)
        return title, body

    try:
        score = int(float(data.get("hook_score", 0)))
    except (TypeError, ValueError):
        score = 0
    if score >= int(config.get("HOOK_MIN_SCORE", "7")):
        log.info("scriptwriter: hook already strong (score %d); not rewriting.", score)
        return title, body

    new_body = (data.get("script_body") or "").strip()
    new_title = (data.get("title") or "").strip()
    if new_body and 80 <= len(new_body.split()) <= 220:  # sane rewrite only
        log.info("scriptwriter: punched up a weak hook (score %d).", score)
        return (new_title or title), new_body
    log.info("scriptwriter: punch-up rewrite unusable (score %d); keeping original.", score)
    return title, body


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

    data = _generate_script_json(_build_prompt(idea, template))

    body = (data.get("script_body") or "").strip()
    if not body:
        raise ValueError(f"scriptwriter: empty script_body for idea {idea_id}.")

    # SEO extras (used by publish for title + tags; fall back to the idea title downstream).
    title = (data.get("title") or "").strip()

    # Scroll-stop judge: punch up a weak hook+title before we spend a render (fail-soft, no new facts).
    if config.get_bool("ENABLE_HOOK_JUDGE", True):
        title, body = _punch_up_hook(title, body)

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = _ensure_shorts([str(h) for h in hashtags])

    caption = _ensure_disclosure(_ensure_sources(data.get("caption") or "", idea.get("sources") or []))

    tags = data.get("tags")
    tags = [str(t).lstrip("#").strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []

    words = len(body.split())
    if not 90 <= words <= 200:  # ~130-150 target; warn on a wild miss, don't block (rule 14)
        log.warning("scriptwriter: idea %s script is %d words (target ~130-150)", idea_id, words)

    # Persist the published title too, so the analytics loop can learn which title STYLE wins
    # (db.top_performing_titles) — the dry idea title is a poor proxy for what viewers tapped.
    script_id = db.insert_script(idea_id, template, body, caption, hashtags, title or None)
    return {"script_id": script_id, "script_body": body, "caption": caption,
            "hashtags": hashtags, "title": title, "tags": tags}
