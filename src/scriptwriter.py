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

from urllib.parse import urlparse

from src import config, db, llm

log = logging.getLogger(__name__)

# Minimal compliant disclosure (docs/08 §2). The primary disclosure is YouTube's
# synthetic-content FLAG set on upload (publish_youtube); this short line is the discreet
# description backup. Removing disclosure entirely risks forced labels + YPP suspension and
# does NOT help reach (researched 2026-06-09), so we keep a minimal honest line.
DISCLOSURE_LINE = "AI-generated narration and music; stock visuals."
# With VISUAL_SOURCE=ai (the live setting) the reel shows Flux images, not stock footage, so the
# line above under-disclosed on every reel. Over-disclosing is safe; under-disclosing is not.
DISCLOSURE_LINE_AI = "AI-generated narration, images and music."
# Music joined both lines on 2026-09-29: the beds in assets/music are generated with Google Lyria
# (tools/generate_music_beds.py). With the music switched off the line over-discloses, which is
# the safe direction.

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

Write a **25-30 SECOND** narration — about **55-70 words**, and NEVER more than {max_words} \
(count them before you answer: at ~2.5 words a second, 70 words already fills 28 seconds). \
Sarcastic, witty, and roasting, but the facts stay straight. Structure it:
1. DISORIENTING HOOK (first ~2s): the single most surprising or absurd TRUE fact, stated instantly \
with a dry edge. No "in this video", no throat-clearing, no fake hype.
2. THE ABSURDITY (2-3 crisp sentences): exactly what happened, in your own words, accurate — with a \
sarcastic aside on the absurdity (never changing a fact).
3. RETENTION BRIDGE & THE POINT (1-2 sentences): "Here's why it actually matters..." — the real \
consequence or "so what", said straight and honest.
4. PUNCHY CLOSE: a witty last line that loops naturally back to the opening hook (a 2-3 word \
CTA is optional).
Every sentence has to earn its place: a tight 25-second read beats a padded 30. Read it aloud to \
check the comedic timing.

WRITE FOR THE EAR: short punchy sentences, contractions, natural rhythm, dry comic timing. Sound \
like a sharp, sarcastic friend who finds the absurdity in the news but means the serious parts — \
not an essay. No hateful or personal attacks; roast situations and irony, not people \
(harassment = demonetization). Plain text only: no markdown, no *asterisks* for emphasis (the \
voice cannot hear them) — use "..." and the delivery tags below.

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
- "title": a clear, curiosity-driven YouTube title that is TRUE to the video, front-loading the most interesting REAL word. Short wins on this channel: aim for 40-55 characters, never more than 70.
- "caption": an ATTRACTIVE, high-retention YouTube description structured cleanly:
  Line 1: A gripping curiosity hook with a relevant emoji (YouTube shows ~2 lines in-feed to make viewers click 'more').
  Line 2: A 1-2 sentence compelling summary of why this matters + a comment trigger question (e.g., "💬 What's your take on this? Comment below!").
  NO links and no "Sources" line: the real, fetched sources are attached automatically, and a \
remembered URL is usually a dead one.
- "tags": 12-15 specific high-traffic search terms & long-tail phrases people type on YouTube (topic, key figures, orgs, category, and close search intent synonyms). No '#'.
- "key_points": 2-3 ULTRA-SHORT on-screen text cards (<=4 words each) — punchiest facts or numbers.

Return ONLY a JSON object, no markdown fences. Write every line break inside a string as the \
two-character escape \\n — a raw newline inside a JSON string is invalid JSON. Inside a string, \
put any quoted word in SINGLE quotes ('like this'): a raw double quote ends the string.
{{"title": "the honest, gripping title", "script_body": "the spoken narration", "caption": "emoji hook line first\\n\\nwhy it matters summary + 💬 comment question", "hashtags": ["#keyword", "#Shorts"], "tags": ["high traffic search term", "long tail phrase"], "key_points": ["short card", "another"]}}
"""


# Stories where the channel's sarcasm would read as mocking victims (docs/08 excludes graphic
# tragedy exploitation). The audit found the fixed sarcastic voice applied to war strikes and a
# child-abuse story. Matched on the idea's own words, so the tone is decided before writing.
# Widened 2026-10-09: 'Russian missiles kill 3', an air crash and a terror attack all read as
# 'sarcastic' because the base and -ing forms were missing (ideas 178, 180, 211). Words that
# also name everyday news (strike, crash, attack, collapse, missing, shot) count only in their
# tragedy phrasing, so a bank strike or a market crash keeps the channel voice. Over-matching
# costs only a calm read; under-matching is the docs/08 exclusion.
_SOMBER_RE = re.compile(
    r"(?i)\b(?:kill(?:s|ed|ing)?|dead|deadl(?:y|ier|iest)|deaths?|died|dies|"
    r"fatal(?:ly|ities)?|massacre|"
    r"mass shootings?|shootings?|(?:was|were|been|being) shot|shot dead|gunned down|gunfire|"
    r"stabb(?:ed|ing)|murder(?:ed|s)?|lynch(?:ed|ing)?|bombing|blasts?|explosions?|suicide|"
    r"genocide|war crimes?|hostages?|famine|casualties|victims?|injur(?:ed|ies)|wounded|"
    r"(?:air|missile|drone) ?strikes?|(?:terror(?:ist)?|suicide|drone|missile|militant|bomb|"
    r"knife|acid|mob|grenade) attacks?|(?:plane|air|train|bus|car|road|helicopter|jet|flight) "
    r"crash(?:es|ed)?|derail(?:ed|ment)|stampedes?|(?:building|bridge|wall|roof|mine|tunnel|dam) "
    r"collaps\w*|drown(?:s|ed|ing)?|capsiz(?:ed|es)?|cyclones?|hurricanes?|tsunamis?|"
    r"wildfires?|riots?|child abuse|sexual (?:abuse|assault)|rape|trafficking|earthquakes?|"
    r"landslides?|floods? (?:kill|death|toll)|death toll|funeral|mourning|"
    r"lost (?:their|his|her) lives?|bod(?:y|ies) (?:found|recovered)|"
    r"(?:went|gone|go|remain|remains|still|are|is) missing)\b")

_SOMBER_NOTE = """

TONE OVERRIDE — this story involves loss of life or serious harm to people. Drop the sarcasm and
the jokes entirely: calm, respectful and direct, with no irony about the people affected. Use
only [serious] or [pause] as delivery tags. The "why it matters" turn is still required:
open it plainly with "Here's why it matters" (live 2026-09-27, a somber draft dropped it)."""


def tone_for(idea: dict, body: str = "") -> str:
    """'somber' for stories about deaths or serious harm, else 'sarcastic' (the channel voice).
    Off with ENABLE_SOMBER_TONE=false.

    `body` (the finished narration) catches what the idea's own words did not: idea 211's
    pitch read as sarcastic while its script said 'killed a woman'."""
    if not config.get_bool("ENABLE_SOMBER_TONE", True):
        return "sarcastic"
    text = " ".join(str(idea.get(k) or "") for k in ("title", "hook", "angle")) + " " + body
    return "somber" if _SOMBER_RE.search(text) else "sarcastic"


def _copies_the_angle(body: str, angle: str, run: int = 8) -> bool:
    """True if the narration repeats `run` or more consecutive words of the ideation angle.

    The audit found the 'why it matters' payoff was often the angle pasted verbatim: the
    originality signal (docs/08 §1) written by the idea generator, not the writer."""
    a = re.findall(r"[a-z0-9']+", (angle or "").lower())
    b = " " + " ".join(re.findall(r"[a-z0-9']+", (body or "").lower())) + " "
    return any(f" {' '.join(a[i:i + run])} " in b for i in range(max(0, len(a) - run + 1)))


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
        max_words=_max_words(),
    )
    # The human "why it matters" take is the originality + anti-"AI-slop" signal (2026 policy).
    if config.get_bool("ENABLE_HUMAN_ANGLE", True):
        prompt += ("\n\nEMPHASIS: the \"why it matters\" analysis is the point of the video — make "
                   "it a genuine, specific human take, not a generic restatement. Develop the "
                   "ANGLE in your own words: never copy its sentences.")
    if tone_for(idea) == "somber":
        prompt += _SOMBER_NOTE
    return llm.today_line() + prompt


_TITLE_MAX = 70


def _fit_title(title: str, limit: int = _TITLE_MAX) -> str:
    """Hold the title to `limit` characters: the prompt asks, this makes it true. An 84-character
    title ("...Last Minute—Why It Almost Crashed the System") overflowed even the smallest hook
    banner. Cut at the first dash or colon when the head still reads as a title, else at a word."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if len(title) <= limit:
        return title
    for sep in ("—", " – ", " - ", ": "):
        head = title.split(sep)[0].strip()
        if 20 <= len(head) <= limit:
            return head
    return title[:limit].rsplit(" ", 1)[0].rstrip(" :,;-—")


def _max_words() -> int:
    try:
        return max(30, int(config.get("SCRIPT_MAX_WORDS", "80")))
    except (TypeError, ValueError):
        return 80


def _parse_llm_json(raw: str) -> dict:
    """Extract the JSON object from the LLM reply (tolerant of fences / surrounding prose).

    Through llm.parse_json_object, which also repairs raw double quotes inside strings. Before
    it, the channel's own scare quotes ('the US just "destroyed" five...') made the grounded
    write unparseable, and both 2026-09-22 scripts were written UNGROUNDED."""
    try:
        return llm.parse_json_object(raw)
    except ValueError as e:
        raise ValueError(f"scriptwriter: no JSON object in LLM reply ({e})") from e


# Claude has no web access here, so it writes from what Gemini found. The grounded draft is its
# fact base; everything that is craft rather than fact is Claude's to redo.
_CLAUDE_DRAFT_NOTE = """

RESEARCH DRAFT — written by a model that searched the live web for this story while writing it, \
so its facts were checked against current reporting. You have no web access, so ignore the \
instruction above to use web search: this draft and the SOURCES are your fact base. Every name, \
number, date, quote and claim you state must already be in one of them, unchanged, and you add \
none. Everything else is yours to rewrite: the hook, the wording, the rhythm, the jokes, the \
title, the caption and the tags. Write the best script you can, in the JSON format above.
{draft}"""

# --- Claude adds no facts: checked in code, not only asked for ---------------------------------
# The fact-check gate waives a claim it cannot confirm when nothing contradicts it, and Claude
# cannot search. So a number or a name Claude brings from memory would reach the gate as
# "couldn't confirm" and ship. Every number and every proper name in Claude's script must
# therefore already be in the grounded draft or the idea, or the draft ships instead.
# "one" is left out of the spelled numbers: it is a pronoun far more often than a count.
_SPELLED_NUMBERS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
    "thousand": "1000", "lakh": "100000", "million": "1000000", "crore": "10000000",
    "billion": "1000000000", "trillion": "1000000000000",
}
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CAPITALISED_RE = re.compile(r"(?<![\w'’])[A-Z][\w'’\-]*")  # not the 'P' of 'iPhone'
# A capitalised word after one of these is mid-sentence, so it is a name, not a sentence start.
# Dashes count: "the man responsible — Somanath" is a name after a dash.
_MID_SENTENCE_BEFORE = ",;'’—–-"


def _numbers(text: str) -> set[str]:
    found = {n.replace(",", "").rstrip(".") for n in _NUMBER_RE.findall(text)}
    found |= {_SPELLED_NUMBERS[w] for w in re.findall(r"[a-z]+", text.lower())
              if w in _SPELLED_NUMBERS}
    return found


def _bare(word: str) -> str:
    """'ISRO's' -> 'isro'."""
    return re.sub(r"['’]s$", "", word).strip("'’-").lower()


def _new_names(body: str, known: set[str]) -> list[str]:
    """Proper names in `body` that `known` (lower-cased source words) does not account for.

    A capitalised word counts as a name mid-sentence, or anywhere when it is an acronym. A
    sentence start is not checked, since "Here's" and "Turns" are capitalised there too. A word
    matches a known one sharing its first four letters, so "Indian" is accounted for by
    "India" and "Pakistani" by "Pakistan"."""
    names = []
    for m in _CAPITALISED_RE.finditer(body):
        word = re.sub(r"['’]s$", "", m.group())
        before = body[:m.start()].rstrip()
        mid = bool(before) and (before[-1].isalnum() or before[-1] in _MID_SENTENCE_BEFORE)
        acronym = len(word) >= 2 and word.isupper()
        bare = _bare(word)
        if not (mid or acronym) or len(bare) < 2 or word.startswith(("I'", "I’")):
            continue
        stem = bare[:4]
        if bare in known or (len(bare) >= 4 and any(k.startswith(stem) for k in known)):
            continue
        names.append(word)
    return names


def _added_facts(data: dict, source_text: str) -> list[str]:
    """Numbers and names in Claude's script that the draft and the idea do not contain.

    Numbers are checked in everything that is published: the narration, the title, the
    on-screen key points and the description. Names only in the narration: titles and key
    points are often in Title Case or capitals, where every word would look like a name."""
    kp = data.get("key_points")
    published = " ".join([str(data.get("script_body") or ""), str(data.get("title") or ""),
                          str(data.get("caption") or ""),
                          " ".join(map(str, kp)) if isinstance(kp, list) else ""])
    added = sorted(_numbers(published) - _numbers(source_text), key=len)
    known = {_bare(w) for w in re.findall(r"[\w'’\-]+", source_text)}
    return added + _new_names(str(data.get("script_body") or ""), known)


def _idea_lines(prompt: str) -> str:
    """The prompt's facts: the date line, IDEA, HOOK, ANGLE and the source links. Not the
    instructions: their numbers ("40-55 characters", "12-15 search terms") are not facts."""
    keep = re.compile(r"^(?:TODAY'S DATE:|IDEA:|HOOK:|ANGLE\b|- https?://)")
    return "\n".join(line for line in prompt.splitlines() if keep.match(line))


# Why Claude did not write a script, by kind, when the operator should hear about it: these
# repeat on every reel until someone acts. Transient errors and a dropped reply are only logged.
_CLAUDE_ISSUE_KINDS = ("no-key", "config", "ledger", "budget", "misconfigured")


def _claude_write(prompt: str, draft: dict) -> tuple[dict | None, dict | None]:
    """Claude's version of the script, or None to ship the grounded draft, plus the reason
    worth reporting when Claude could not write (None otherwise). Fail-soft (rule 11): no key, a
    spent budget, an API error, an unusable reply or an added fact all return None."""
    note = _CLAUDE_DRAFT_NOTE.format(draft=json.dumps(draft, ensure_ascii=False))
    try:
        data = _parse_llm_json(llm.generate_claude(prompt + note, purpose="script"))
    except llm.ClaudeUnavailable as e:
        log.info("scriptwriter: Claude not used (%s); shipping the grounded draft", e)
        return None, ({"kind": e.kind, "reason": str(e)} if e.kind in _CLAUDE_ISSUE_KINDS
                      else None)
    except llm.ClaudeMisconfigured as e:
        log.error("scriptwriter: Claude rejected its configuration (%s); shipping the grounded "
                  "draft", e)
        return None, {"kind": "misconfigured", "reason": str(e)}
    except Exception as e:  # noqa: BLE001 — Claude is best-effort; Gemini stays behind it
        log.warning("scriptwriter: Claude write failed (%s); shipping the grounded draft", e)
        return None, None
    if not (data.get("script_body") or "").strip():
        log.warning("scriptwriter: Claude returned no script_body; shipping the grounded draft")
        return None, None
    added = _added_facts(data, _idea_lines(prompt) + "\n" + json.dumps(draft, ensure_ascii=False))
    if added:
        log.warning("scriptwriter: Claude's script adds %s, which the grounded draft does not "
                    "carry; shipping the draft", ", ".join(added))
        return None, None
    return data, None


def _generate_script_json(prompt: str) -> dict:
    """Write the script: Gemini researches it with live web-grounding, then Claude writes the
    final version from that draft. Each step falls back: no Claude, or a Claude script that
    adds a fact, means the grounded draft ships; no usable draft means ungrounded Gemini → Groq,
    and no Claude call, since Claude would have nothing to take its facts from.
    Grounding is the accuracy guard for a public channel: it lets the model catch a fabricated
    premise instead of repeating it, and the draft carries those checked facts to Claude.

    The result carries `writer` (claude | gemini-grounded | gemini) and, when Claude could not
    write for a reason that repeats until someone acts, `claude_issue` {kind, reason}.

    ENABLE_GROUNDED_SCRIPT=false skips the grounded attempt entirely. It exists because on the
    Developer API this call is one of the 7 a 3-reel run spends from the single 20/day grounded
    budget shared with ideation and `factcheck.verify` (audit 2026-09-03; production has run on
    Vertex, without that cap, since 2026-09-04) — and when that budget runs dry it is the
    fact-check GATE that stops working. If one of the two has to go, the gate is worth more: it
    re-verifies the finished script, so a fabricated premise is still caught downstream. Default
    stays ON — this is a lever for a busy day, not a silent quality cut.

    ENABLE_CLAUDE_SCRIPT=false skips Claude, which is also what happens without
    ANTHROPIC_API_KEY or once the month's budget is spent (llm.generate_claude)."""
    draft = None
    if config.get_bool("ENABLE_GROUNDED_SCRIPT", True):
        try:
            data = _parse_llm_json(llm.generate_grounded(prompt, max_tokens=2048))
            if (data.get("script_body") or "").strip():
                draft = data
        except Exception as e:  # noqa: BLE001 — grounded write is best-effort; fall back
            log.warning("scriptwriter: grounded write unusable (%s)", e)
    else:
        log.info("scriptwriter: grounded write disabled.")
    if draft is None:
        log.info("scriptwriter: no grounded draft, so no Claude call; using ungrounded JSON mode.")
        return {**_parse_llm_json(llm.generate(prompt, json=True, max_tokens=2048)),
                "writer": "gemini"}
    if not config.get_bool("ENABLE_CLAUDE_SCRIPT", True):
        return {**draft, "writer": "gemini-grounded"}
    written, issue = _claude_write(prompt, draft)
    if written:
        return {**written, "writer": "claude"}
    return {**draft, "writer": "gemini-grounded", "claude_issue": issue}


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
and intensify the DELIVERY. Keep it a tight 25-30 SECOND bite (at most {max_words} words) — sharpen \
wording but NEVER lengthen it — and keep the closing loop-back line.

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
            llm.generate(_PUNCHUP_PROMPT.format(title=title, body=body, max_words=_max_words()),
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
    max_words = _max_words()
    # Live 2026-09-27 (idea 312): a punched-up opening came back without the 'why it matters'
    # turn, and nothing checked — the originality signal (docs/08 §1) is not the hook doctor's
    # to delete.
    if _WHY_IT_MATTERS_RE.search(body) and not _WHY_IT_MATTERS_RE.search(new_body):
        log.info("scriptwriter: punch-up dropped the 'why it matters' turn; keeping original.")
        return title, body
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


# A call to action is the cheapest sentence in the script: it carries no fact and no payoff.
_CTA_RE = re.compile(r"(?i)\b(subscribe|follow (?:us|for|along)|hit (?:the )?(?:like|bell)|"
                     r"like and share|comment below|drop a comment|share this)\b")


def _sentences(body: str) -> list[str]:
    """Split into sentences; a delivery tag stays with the sentence it introduces."""
    out, last = [], 0
    for m in _SENTENCE_END_RE.finditer(body):
        out.append(body[last:m.end()].strip())
        last = m.end()
    out.append(body[last:].strip())
    return [x for x in out if x]


def _truncate_to_words(body: str, max_words: int) -> str:
    """Hard length backstop: drop WHOLE sentences until the body fits max_words. Deterministic.

    Delivery tags are carried through with their sentence and do not count toward the cap.

    Two protected sentences: the hook (first) and the 'why it matters' turn, which is the
    originality signal the monetization gate turns on (docs/08 §1). Everything else goes in
    order of how little it costs: the call to action, then the loop-back close, then the setup
    from its end backwards, then any extra payoff detail.

    The old version kept the front and cut at the cap. When the head's first sentence was longer
    than its budget there was no full stop to cut back to, so it returned a raw mid-sentence
    word cut, which is how published script 267 went out reading '...who have been, shall we
    say, *at odds* in the West Asia [serious] But it matters because...'. It also spent the cut
    on the facts while keeping 'Subscribe for more'. A sentence is now never cut in half.
    """
    if len(_visible_words(body)) <= max_words:
        return body
    sents = _sentences(body)
    if len(sents) <= 1:  # one enormous sentence: nothing whole to drop, so keep the old cut
        kept, spoken = [], 0
        for m in _PIECE_RE.finditer(body):
            piece = m.group(0)
            if not (piece.startswith("[") and piece.endswith("]")):
                if spoken >= max_words:
                    break
                spoken += 1
            kept.append(piece)
        return " ".join(kept).strip()

    bridge = next((i for i, x in enumerate(sents) if _WHY_IT_MATTERS_RE.search(x)), None)
    # The loop-back close is the last sentence that is not a call to action.
    last = max((i for i, x in enumerate(sents) if not _CTA_RE.search(x)), default=len(sents) - 1)
    cost: dict[int, tuple[int, int]] = {}
    for i, sent in enumerate(sents):
        if i == 0 or i == bridge:
            continue
        if _CTA_RE.search(sent):
            cost[i] = (0, -i)
        elif bridge is not None and i > bridge:
            cost[i] = (1, -i) if i == last else (3, -i)
        else:
            cost[i] = (2, -i)
    keep = set(range(len(sents)))

    def _joined() -> str:
        return " ".join(sents[j] for j in sorted(keep))

    for i in sorted(cost, key=cost.get):
        if len(_visible_words(_joined())) <= max_words:
            break
        keep.discard(i)
    return _joined()


_TIGHTEN_PROMPT = """Cut this YouTube Shorts narration to between {floor} and {max_words} spoken \
words, aiming for {target}. It is {words} now. Delivery tags in [square brackets] are not words; \
keep the ones whose sentence stays.

NARRATION:
{body}

RULES:
- Keep the opening hook and the "why it matters" turn, word for word where you can.
- Cut in this order: the call to action, filler words and repeated phrases, then jokes and \
asides that carry no fact. Keep what happened: the facts are why anyone watches.
- NEVER add, change or invent a fact, name, number, date or quote. Only delete and re-join.
- Every sentence must be complete. Plain text, no markdown.

Return ONLY a JSON object, no fences. Put any quoted word in SINGLE quotes:
{{"script_body": "the tightened narration"}}
"""


def _tighten(body: str, max_words: int) -> str | None:
    """An LLM edit down to the cap that keeps every fact, or None to fall back to truncation.

    Every script since 2026-08-26 came back over the cap (82-128 words) and lost 30-50 words of
    context to the backstop. Deleting and re-joining is an editing job a model does well; the
    fact-check re-verifies the finished script either way. The result is only taken if it fits,
    is still a real script, and kept the 'why it matters' turn."""
    words = len(_visible_words(body))
    floor, target = max_words - 20, max_words - 8
    try:
        # 4096, not 1024: both providers count reasoning against max_tokens. At 1024 idea 488
        # (87 words) failed on Groq ("max completion tokens reached") and on Gemini (the JSON
        # cut off mid-string), so its reel shipped at 42 s. Unused budget costs nothing.
        data = _parse_llm_json(llm.generate(
            _TIGHTEN_PROMPT.format(max_words=max_words, floor=floor, target=target,
                                   words=words, body=body),
            json=True, max_tokens=4096, prefer_groq=True))
    except Exception as e:  # noqa: BLE001 — the deterministic backstop still runs
        log.warning("scriptwriter: tighten pass failed (%s); truncating instead.", e)
        return None
    new = _strip_markdown(str(data.get("script_body") or "").strip())
    n = len(_visible_words(new))
    if not new or n > max_words or n < max(40, floor - 10):
        log.info("scriptwriter: tighten pass unusable (%d words); truncating instead.", n)
        return None
    if _WHY_IT_MATTERS_RE.search(body) and not _WHY_IT_MATTERS_RE.search(new):
        log.info("scriptwriter: tighten pass dropped the 'why it matters' turn; truncating.")
        return None
    return new


def _strip_markdown(body: str) -> str:
    """Remove *emphasis* the model sometimes writes. 4 of the last 20 stored scripts carried it
    ('*that*', '*at odds*', '*poof*'); nothing downstream strips it and a voice cannot say it."""
    body = re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"\1", body)
    return body.replace("*", "")


def _enforce_length(body: str, idea_id) -> str:
    """Bring the body under SCRIPT_MAX_WORDS: the tighten pass first, truncation as backstop."""
    max_words = _max_words()
    words = len(_visible_words(body))
    if words <= max_words:
        return body
    log.warning("scriptwriter: idea %s script %d words > %d cap; tightening.",
                idea_id, words, max_words)
    if config.get_bool("ENABLE_SCRIPT_TIGHTEN", True):
        tight = _tighten(body, max_words)
        if tight:
            log.info("scriptwriter: idea %s tightened %d -> %d words.",
                     idea_id, words, len(_visible_words(tight)))
            return tight
    return _truncate_to_words(body, max_words)


_URL_RE = re.compile(r"https?://\S+")
_SOURCES_LINE_RE = re.compile(r"(?im)^[ \t]*sources?[ \t]*:.*$")
_MAX_CAPTION_SOURCES = 3


def _publishable_sources(sources: list[str]) -> list[str]:
    """The sources worth printing: publisher links first, one per outlet, then Google News
    links, at most three. Unresolved grounding redirects (vertexaisearch.cloud.google.com) are
    left out: they expire, and some 404 from the start. One is kept only if nothing else exists,
    since a reel with no citation at all is the worse failure (docs/08)."""
    seen, publisher, gnews, redirects = set(), [], [], []
    for raw in sources or []:
        url = str(raw).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = urlparse(url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        if "grounding-api-redirect" in url or host.endswith("vertexaisearch.cloud.google.com"):
            redirects.append(url)
        elif host == "news.google.com":
            gnews.append(url)
        elif host and host not in seen:
            seen.add(host)
            publisher.append(url)
    return (publisher + gnews)[:_MAX_CAPTION_SOURCES] or redirects[:1]


def _ensure_sources(caption: str, sources: list[str]) -> str:
    """Exactly ONE 'Sources:' block, built from the idea's fetched sources (sourcing gate).

    The model used to write its own 'Sources:' line from memory, and this function then added
    the real sources under a SECOND header. Every recent description had both, and 12 of the 53
    model-written links were dead (404/400). Links and 'Sources' lines in the model's caption
    are now removed and only the vetted list is printed."""
    text = _URL_RE.sub("", _SOURCES_LINE_RE.sub("", caption or ""))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    usable = _publishable_sources(sources)
    if not usable:
        return text
    # One per line: Google News links run 249-884 characters, so joined they are a wall.
    block = "Sources:" + "".join("\n" + u for u in usable)
    return f"{text}\n\n{block}" if text else block


def _disclosure_line() -> str:
    """The disclosure that matches what the reel shows (VISUAL_SOURCE=ai means Flux images)."""
    source = str(config.get("VISUAL_SOURCE", "photos") or "").strip().lower()
    return DISCLOSURE_LINE_AI if source == "ai" else DISCLOSURE_LINE


def _ensure_disclosure(caption: str) -> str:
    """Guarantee the AI-disclosure line is present (docs/08 §2 — required), as its own paragraph.

    It used to be skipped whenever 'ai-generated' appeared ANYWHERE (a hook about AI-generated
    art, a source URL), and otherwise sat glued under the last source link."""
    line = _disclosure_line()
    if line.lower() in caption.lower():
        return caption
    return f"{caption.rstrip()}\n\n{line}" if caption.strip() else line


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


_REPAIR_PROMPT = """A fact-checker blocked this YouTube Shorts narration about: {topic}
Its findings (each quotes a claim it judged false, sometimes with what is true instead):
{findings}

NARRATION:
{body}

Use web search to establish what is actually true about each flagged claim, then rewrite ONLY
those sentences so they are accurate. Keep every other sentence word for word, including its
delivery tags. The narration must still OPEN with a complete, accurate hook sentence that says
what happened: if the flagged claim was the opening, replace it with a corrected opening, never
just delete it. Never start with a delivery tag or with "Because", "And", "But" or "So". Keep the
"why it matters" turn. At most {max_words} spoken words. Plain text, no markdown.

Return ONLY a JSON object, no fences. Put any quoted word in SINGLE quotes:
{{"script_body": "the corrected narration"}}
"""


def repair_script(body: str, findings: list[str], topic: str | None = None) -> str | None:
    """Rewrite only what the fact-check blocked; None if the rewrite is unusable.

    A block used to throw the whole reel away, although the checker's findings usually say
    exactly what is true instead (idea 308: "the bill has already been signed into law"). The
    caller re-verifies the result with the gate, so this can only ever make a reel eligible, never
    wave a false claim through."""
    if not findings:
        return None
    max_words = _max_words()
    # Today's date, like the writer and the gate: a grounded rewrite without it dated September
    # news to June (STATUS 2026-09-28).
    prompt = llm.today_line() + _REPAIR_PROMPT.format(topic=topic or "the news story",
                                   findings="\n".join(f"- {f}" for f in findings[:6]),
                                   body=body, max_words=max_words)
    try:
        # Grounded: a finding often names the false claim without saying what is true, so the
        # rewrite has to look it up. Ungrounded JSON mode is the fallback.
        try:
            raw = llm.generate_grounded(prompt, max_tokens=2048)
        except Exception as e:  # noqa: BLE001
            log.warning("scriptwriter: grounded repair unavailable (%s); ungrounded", e)
            raw = llm.generate(prompt, json=True, max_tokens=4096)  # room for reasoning, as _tighten
        data = _parse_llm_json(raw)
    except Exception as e:  # noqa: BLE001 — the block stands
        log.warning("scriptwriter: repair pass failed (%s)", e)
        return None
    new = _enforce_length(_strip_markdown(str(data.get("script_body") or "").strip()), "repair")
    if not _opens_with_a_hook(new):
        # Live 2026-09-27 (idea 308): the first repair deleted the flagged opening and left the
        # reel starting "[pause] [sarcastic] Because nothing screams...". It passed the gate.
        log.warning("scriptwriter: repair lost the opening hook; the block stands.")
        return None
    if len(_visible_words(new)) < 40:
        return None
    if _WHY_IT_MATTERS_RE.search(body) and not _WHY_IT_MATTERS_RE.search(new):
        return None
    return _ensure_delivery_tag(new)


_DANGLING_OPENERS = ("because", "and", "but", "so", "which", "or")


def _opens_with_a_hook(body: str) -> bool:
    """True if the narration starts with a real sentence: no leading tag, no dangling
    conjunction, at least five spoken words before the first full stop."""
    text = (body or "").lstrip()
    if not text or text.startswith("["):
        return False
    first = _sentences(text)[0] if _sentences(text) else text
    words = _visible_words(first)
    return len(words) >= 5 and words[0].strip("'\"").lower() not in _DANGLING_OPENERS


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

    body = _strip_markdown((data.get("script_body") or "").strip())
    if not body:
        raise ValueError(f"scriptwriter: empty script_body for idea {idea_id}.")

    # SEO extras (used by publish for title + tags; fall back to the idea title downstream).
    title = _fit_title((data.get("title") or "").strip())

    # Fit the cap BEFORE the punch-up: the punch-up only accepts a rewrite that is under the cap,
    # so on the 100-word drafts every run was producing it could not act (9 of 16 logged
    # decisions were "unusable").
    body = _enforce_length(body, idea_id)

    # Scroll-stop judge: punch up a weak hook+title before we spend a render (fail-soft, no new facts).
    # Never on a somber story: a calm opening scores low, and the rewrite is shock copy, which
    # becomes the YouTube title and the frame-1 banner of a story about deaths.
    if config.get_bool("ENABLE_HOOK_JUDGE", True) and tone_for(idea, body) != "somber":
        title, body = _punch_up_hook(title, body)
        title = _fit_title(title)  # the punch-up writes its own title, and nothing capped it

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = _ensure_shorts([str(h) for h in hashtags])

    # Markdown is stripped from the caption too: YouTube prints '*you*' with the asterisks.
    caption = _ensure_disclosure(_ensure_sources(_strip_markdown(data.get("caption") or ""),
                                                 idea.get("sources") or []))

    tags = data.get("tags")
    tags = [str(t).lstrip("#").strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []

    # Short on-screen text cards (story-specific visuals, burned by subtitles over the B-roll).
    kp = data.get("key_points")
    key_points = ([str(p).strip() for p in kp if str(p).strip()][:5]
                  if isinstance(kp, list) else [])

    body = _enforce_length(body, idea_id)  # the punch-up is capped too; this is a no-op then
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

    if _copies_the_angle(body, idea.get("angle", "")):
        log.warning("scriptwriter: idea %s repeats the ideation angle word for word; the payoff "
                    "should be the writer's own analysis (docs/08 §1). Review it.", idea_id)

    # After the word cap, so truncation can never cut the tag back off. Tags are not spoken
    # words (_visible_words ignores them), so this cannot push the script over the cap.
    body = _ensure_delivery_tag(body)

    # Persist the published title too, so the analytics loop can learn which title STYLE wins
    # (db.top_performing_titles) — the dry idea title is a poor proxy for what viewers tapped.
    script_id = db.insert_script(idea_id, template, body, caption, hashtags, title or None)
    return {"script_id": script_id, "script_body": body, "caption": caption,
            "hashtags": hashtags, "title": title, "tags": tags, "key_points": key_points,
            "tone": tone_for(idea, body), "writer": data.get("writer"),
            "claude_issue": data.get("claude_issue")}
