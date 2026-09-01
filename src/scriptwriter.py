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
import re

from src import config, db, llm

log = logging.getLogger(__name__)

# Minimal compliant disclosure (docs/08 §2). The primary disclosure is YouTube's
# synthetic-content FLAG set on upload (publish_youtube); this short line is the discreet
# description backup. Removing disclosure entirely risks forced labels + YPP suspension and
# does NOT help reach (researched 2026-06-09), so we keep a minimal honest line.
DISCLOSURE_LINE = "AI-generated narration; stock visuals."

# Only Template N is in the Phase-1 MVP (rule 9 / YAGNI). The others exist as docs.
_SUPPORTED_TEMPLATES = ("N",)

_PROMPT_N = """You are the lead viral scriptwriter for "But It Matters" — sharp **25-30 SECOND** YouTube \
Shorts with a SARCASTIC, dryly funny, roasted, but DEAD-SERIOUS voice (think Daily Show / Phil DeFranco \
meets clever friend). You explain real news with razor-sharp wit and a knowing eye-roll at the \
absurdity, then land a genuinely useful, HONEST "why it matters" point. Funny in the DELIVERY, \
never in the facts. Your voice is NATURAL and conversational with real edge — energetic, gripping, \
never a stiff news-anchor. The hook is strong but TRUE: the title and opening must sit honestly \
on what the video actually delivers — a click-then-bounce from an over-claim gets the channel suppressed.

IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES:
{sources}

WHAT WINS ON THIS CHANNEL: a disorienting curiosity gap the video actually CLOSES. Lead with the single \
most surprising, absurd, or high-tension TRUE fact. Follow up immediately with a retention bridge \
("Here's the catch...", "Wait, it gets weirder...") to keep viewers hooked before the payoff. \
Promise == payoff.

Write a **25-30 SECOND** narration — about **65-75 words** (aim for the FULL 25-30 seconds; do not \
cut it short). Sarcastic, witty, and roasting, but the facts stay straight. Structure it:
1. DISORIENTING HOOK (first ~2s): the single most surprising or absurd TRUE fact, stated instantly \
with a dry edge. No "in this video", no throat-clearing, no fake hype.
2. THE ABSURDITY (2-3 crisp sentences): exactly what happened, in your own words, accurate — with a \
sarcastic aside on the absurdity (never changing a fact).
3. RETENTION BRIDGE & THE POINT (1-2 sentences): "Here's why it actually matters..." — the real \
consequence or "so what", said straight and honest.
4. PUNCHY CLOSE: a witty last line that loops naturally back to the opening hook + 2-3 word CTA.
Fill the full 25-30 seconds — don't end early. Read it aloud to check the comedic timing.

WRITE FOR THE EAR: short punchy sentences, contractions, natural rhythm, dry comic timing. Sound \
like a sharp, sarcastic friend who finds the absurdity in the news but means the serious parts — \
not an essay. No hateful or personal attacks; roast situations and irony, not people \
(harassment = demonetization).

DELIVERY DIRECTION (this is how it will be READ ALOUD):
Write for the ear first. Short punchy sentences, contractions, natural rhythm. Use "..." for a \
deliberate beat or hesitation — it changes the timing on every voice engine.
Then add AT LEAST 1 and AT MOST 3 delivery tags. The one that is REQUIRED is a tone tag on the \
"why it matters" turn — that line is the whole point of the video, and read in the same dry \
register as the joke before it, it lands as one more punchline. The rest are optional:
- [pause] or [pause long] for a comic beat before a punchline or the "why it matters" turn.
- [sarcastic], [deadpan] or [dry] immediately before the line whose TONE flips.
- [serious] for the "why it matters" turn when the subject deserves it — this is the one that \
tells the audience you actually mean it.
- [curious] on an opening question, [whispers] on a conspiratorial aside, [tired] on \
institutional absurdity, [mischievously] before a setup you are about to puncture.
Tags are stage direction, never narration — never write a tag the sentence already says out \
loud, and never open the script with one. Fewer is better: a tag on every line reads as noise. \
The failure mode is a narrator who ANNOUNCES the joke; restraint reads as confidence.

ACCURACY (THE ONE HARD LINE): VERIFY the development actually \
happened (use the sources + web search). State ONLY facts you can support. NEVER invent product \
names, version numbers, figures, dates, quotes, or events. Sharpen the FRAMING, never fabricate the \
STORY — a made-up fact gets the channel struck and demonetized.

TRUTH OVER NEUTRALITY: you are NOT required to be even-handed. If the evidence points one way, \
say so plainly and name who is responsible — a well-sourced conclusion is not bias, and hedging a \
clear finding into mush is its own kind of dishonesty. The trade is strict: the sharper your \
verdict, the more certain its supporting facts must be. Every load-bearing claim has to be \
something a viewer could check. Opinion is earned by evidence, never asserted without it. An \
independent fact-check runs on this script before it is voiced, and unsupported claims kill the \
reel — so do not reach for a punchier claim than your sources can carry.

ALSO produce, for the feed + discoverability:
- "title": a clear, curiosity-driven YouTube title (<=70 chars) that is TRUE to the video — front-loading the most interesting REAL word.
- "caption": an ATTRACTIVE, high-retention YouTube description structured cleanly:
  Line 1: A gripping curiosity hook with a relevant emoji (YouTube shows ~2 lines in-feed to make viewers click 'more').
  Line 2: A 1-2 sentence compelling summary of why this matters + a comment trigger question (e.g., "💬 What's your take on this? Comment below!").
  Line 3: The real source link(s).
- "tags": 12-15 specific high-traffic search terms & long-tail phrases people type on YouTube (topic, key figures, orgs, category, and close search intent synonyms). No '#'.
- "key_points": 2-3 ULTRA-SHORT on-screen text cards (<=4 words each) — punchiest facts or numbers.

Return ONLY a JSON object, no markdown fences. Write every line break inside a string as the \
two-character escape \\n — a raw newline inside a JSON string is invalid JSON:
{{"title": "the honest, gripping title", "script_body": "the spoken narration", "caption": "emoji hook line first\\n\\nwhy it matters summary + 💬 comment question\\n\\nSources: ...", "hashtags": ["#keyword", "#Shorts"], "tags": ["high traffic search term", "long tail phrase"], "key_points": ["short card", "another"]}}
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
and intensify the DELIVERY. Keep it a tight 25-30 SECOND bite (~65-75 words) — sharpen wording but \
NEVER lengthen it — and keep the closing CTA / loop-back line.

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
    max_words = int(config.get("SCRIPT_MAX_WORDS", "80"))
    if new_body and 40 <= len(_visible_words(new_body)) <= max_words:  # accept only if it stayed short
        log.info("scriptwriter: punched up a weak hook (score %d).", score)
        return (new_title or title), new_body
    log.info("scriptwriter: punch-up rewrite unusable (score %d); keeping original.", score)
    return title, body


# Delivery tags must be matched against the WHOLE string, not token-by-token: "[pause long]"
# contains a space, so splitting on whitespace yields "[pause" and "long]" and a per-token test
# counts BOTH as spoken words.
_TAG_IN_TEXT_RE = re.compile(r"\[[^\]]*\]")
# A tag, or a run of non-space that does not start a tag (so "three.[pause]" splits cleanly).
_PIECE_RE = re.compile(r"\[[^\]]*\]|[^\s\[]+")


def _visible_words(body: str) -> list[str]:
    """Words the narrator actually SAYS — inline delivery tags ([pause], [sarcastic]) are stage
    direction for the TTS engine, not narration. Counting them would silently shrink the
    25-30s script budget every time the model added one."""
    return _TAG_IN_TEXT_RE.sub(" ", body).split()


def _payoff_start(body: str) -> int | None:
    """Index where the 'why it matters' sentence begins, or None if there is no bridge.

    Shared by the tag floor and the length cap so the two agree on WHERE the payoff is; two
    copies of this walk-back drifting apart is how [curious] came to be emitted-but-stripped.
    """
    m = _WHY_IT_MATTERS_RE.search(body)
    if not m:
        return None
    starts = [e.end() for e in _SENTENCE_END_RE.finditer(body, 0, m.start())]
    return starts[-1] if starts else 0


def _truncate_to_words(body: str, max_words: int) -> str:
    """Hard length backstop: if the body exceeds max_words, cut to the last full sentence
    at or under the cap (so we never end mid-thought). Deterministic.

    Delivery tags are carried through and do not count toward the cap.

    The cap trims from the END, which is precisely where the 'why it matters' turn lives — so
    a long script was silently losing its payoff. Observed live on idea 224 (run 32920283763):
    `104 words > 80 cap; truncating to a sentence.` and then, next line, `has NO 'why it
    matters' turn`. The truncation caused the warning. That turn is the originality signal the
    monetization gate turns on (docs/08 §1), which makes it the most expensive sentence in the
    script to drop, not the cheapest. So when a bridge exists it is RESERVED: the setup is
    trimmed to whatever budget is left after the payoff is paid for.
    """
    if len(_visible_words(body)) <= max_words:
        return body

    start = _payoff_start(body)
    if start is not None:
        payoff = body[start:].strip()
        payoff_words = len(_visible_words(payoff))
        # Only reserve it if the setup still gets a meaningful share; a payoff that alone blows
        # the cap means the writer wrote one enormous closing sentence, and the old
        # keep-the-front behaviour degrades better than emitting the payoff by itself.
        if 0 < payoff_words < max_words:
            head = _truncate_to_words(body[:start].strip(), max_words - payoff_words)
            return f"{head} {payoff}".strip() if head else payoff

    kept, spoken = [], 0
    for m in _PIECE_RE.finditer(body):
        piece = m.group(0)
        if piece.startswith("[") and piece.endswith("]"):
            kept.append(piece)
            continue
        if spoken >= max_words:
            break
        kept.append(piece)
        spoken += 1
    truncated = " ".join(kept)
    ends = list(re.finditer(r"[.!?]", truncated))
    return (truncated[: ends[-1].end()] if ends else truncated).strip()


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


# The retention bridge the prompt asks for ("Here's why it actually matters…"). Matching it is
# how the floor knows WHERE the payoff starts — the tag is worthless in the wrong place.
_WHY_IT_MATTERS_RE = re.compile(
    r"(?i)\b(here'?s why\b|why (?:it|this)(?: actually)? matters\b"
    r"|(?:it|this) (?:actually )?matters because\b|the real (?:point|issue) (?:here )?is\b)")
# Sentence boundary: terminator + whitespace. Used to walk BACK to the start of the sentence the
# bridge lives in, so the tag lands on the whole payoff rather than mid-clause.
_SENTENCE_END_RE = re.compile(r"[.!?…](?:[\"')\]]*)\s+")


def _ensure_delivery_tag(body: str) -> str:
    """Guarantee the script carries at least one delivery tag, on the 'why it matters' turn.

    Measured 2026-08-07 against the last 5 produced scripts: two of them shipped with NO tags at
    all. The prompt says "AT MOST 3 … fewer is better", which permits zero — so on a channel whose
    whole premise is the delivery, ~40% of reels went out with no direction on the read.

    A prompt asks; a guard is what makes it true (the same reasoning as MAX_STYLE_TAGS in voice).
    [serious] is the one worth guaranteeing: the payoff line is both the emotional turn and the
    originality signal that carries the monetization gate (docs/08 §1), and it is the line most
    damaged by being read in the same dry register as the joke before it.

    Fail-soft and conservative: if the script already has any style tag, or the bridge cannot be
    located confidently, the body is returned UNCHANGED. A tag guessed into the wrong sentence
    would be worse than no tag.
    """
    from src import voice  # local import: keeps the tag allow-list in ONE module (rule 7)

    if not config.get_bool("ENABLE_TAG_FLOOR", True) or voice.has_style_tag(body):
        return body

    m = _WHY_IT_MATTERS_RE.search(body)
    if not m:
        log.info("scriptwriter: no delivery tag and no 'why it matters' bridge found; "
                 "leaving the script untagged rather than guessing a placement.")
        return body

    # Walk back to the start of the sentence containing the bridge.
    starts = [e.end() for e in _SENTENCE_END_RE.finditer(body, 0, m.start())]
    at = starts[-1] if starts else 0
    log.info("scriptwriter: script had no delivery tag; inserted [serious] on the payoff turn.")
    return f"{body[:at]}[serious] {body[at:]}".strip()


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

    # Short on-screen text cards (story-specific visuals, burned by subtitles over the B-roll).
    kp = data.get("key_points")
    key_points = ([str(p).strip() for p in kp if str(p).strip()][:5]
                  if isinstance(kp, list) else [])

    max_words = int(config.get("SCRIPT_MAX_WORDS", "80"))
    if len(_visible_words(body)) > max_words:
        log.warning("scriptwriter: idea %s script %d words > %d cap; truncating to a sentence.",
                    idea_id, len(_visible_words(body)), max_words)
        body = _truncate_to_words(body, max_words)
    if len(_visible_words(body)) < 50:
        log.warning("scriptwriter: idea %s script is short (%d words)",
                    idea_id, len(_visible_words(body)))

    # ORIGINALITY SIGNAL, not a style nit (docs/08 §1). A script with no "why it matters" turn is
    # a bare summary, which is exactly what YouTube's inauthentic-content policy demotes and what
    # the monetization gate turns on. Found live on script 158 (2026-08-07), where it was
    # invisible because nothing checked. Warn rather than block: accuracy already has a hard gate
    # (factcheck), and stacking a second blocking gate on a SOFT quality judgement would cost
    # reels for something a human should eyeball (rule 14 — soft on runtime).
    if not _WHY_IT_MATTERS_RE.search(body):
        log.warning("scriptwriter: idea %s has NO 'why it matters' turn — that makes it a bare "
                    "summary, which is the originality/monetization risk (docs/08 §1). Review it.",
                    idea_id)

    # After the word cap, so truncation can never cut the tag back off. Tags are not spoken
    # words (_visible_words ignores them), so this cannot push the script over the cap.
    body = _ensure_delivery_tag(body)

    # Persist the published title too, so the analytics loop can learn which title STYLE wins
    # (db.top_performing_titles) — the dry idea title is a poor proxy for what viewers tapped.
    script_id = db.insert_script(idea_id, template, body, caption, hashtags, title or None)
    return {"script_id": script_id, "script_body": body, "caption": caption,
            "hashtags": hashtags, "title": title, "tags": tags, "key_points": key_points}
