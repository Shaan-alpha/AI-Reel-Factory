"""Module 3 — Scriptwriter.

Contract:
    what it does : turns an approved idea (+ its sources) into a script via a template.
    input        : idea dict {id, title, hook, angle, sources, ...}; template name (default 'N').
    output       : {script_id, script_body, caption, hashtags[]} — also written to `scripts`.
    depends on   : src.llm, src.db, templates/*.md (design source), src.config.

ORIGINALITY IS THE MONETIZATION GATE (docs/08 §1): the script's core value is the
"why it matters" ANALYSIS, not a summary. Rewrite facts in own words + cite. Caption must
include source links + an AI-disclosure line. Keyword-rich title (SEO).

The compliance requirements (source links, AI-disclosure line) are enforced in code AFTER the
LLM responds — never trusted to the model, because they gate monetization. #Shorts is no longer
added (design 9.9); production composes the hashtag line.
The executable prompt below mirrors templates/template-N-news-impact.md (the design source);
keep the two in sync.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

from urllib.parse import urlparse

from src import config, db, llm
from src.text import sentence_ends, split_sentences

log = logging.getLogger(__name__)

# Minimal compliant disclosure (docs/08 §2). The primary disclosure is YouTube's
# synthetic-content FLAG set on upload (publish_youtube); this short line is the discreet
# description backup. Removing disclosure entirely risks forced labels + YPP suspension and
# does NOT help reach (researched 2026-06-09), so we keep a minimal honest line.
DISCLOSURE_LINE = "AI-generated narration and music; stock visuals."
# With VISUAL_SOURCE=ai (the live setting) the reel shows Flux images, not stock footage, so the
# line above under-disclosed on every reel. Over-disclosing is safe; under-disclosing is not.
DISCLOSURE_LINE_AI = "AI-generated narration, images and music."
# The AI-video format (design 9.9): the shots themselves are generated video.
DISCLOSURE_LINE_AI_VIDEO = "AI-generated narration, video and music."
# Music joined both lines on 2026-09-29: the beds in assets/music are generated with Google Lyria
# (tools/generate_music_beds.py). With the music switched off the line over-discloses, which is
# the safe direction.

# Only Template N is in the Phase-1 MVP (rule 9 / YAGNI). The others exist as docs.
_SUPPORTED_TEMPLATES = ("N",)

_PROMPT_N = """You write the narration for "But It Matters", 25-35 second explainer Shorts for \
Indian viewers: Indians aged about 18-34 watching on a phone, at home in Hindi and English, who \
care about what changes their money, jobs, exams, safety, gadgets and the country's standing. You \
are a clear, curious, confident explainer, like a well-read friend: no sarcasm, no mockery, no \
jokes at anyone's expense. The title and the opening sit honestly on what the video delivers: a \
click-then-bounce from an over-claim gets the channel suppressed.

IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES:
{sources}

SENTENCE ONE states the story's newest or most extreme true fact, with its subject and the \
Indian stake in its first clause. It never opens on a wind-up word, a date, a day or a greeting.

THEN THIS STRUCTURE:
{structure}

THE PAYOFF (the "why it matters" sentence) says what changes for a person in India: a price, a \
rule, a date, a risk, a job, taken from the sources. When the story has no Indian stake, it says \
what changes for anyone, just as concretely. It is your own analysis, never the angle's words.

LENGTH: about {target_seconds} seconds read aloud, about {target_words} words, never more than \
{max_words}. No intro, no sign-off, no call to action. Every sentence earns its place.

WRITE FOR THE EAR: short sentences, contractions, a natural rhythm. Plain text only: no markdown \
and no *asterisks* for emphasis (the voice cannot hear them). Use "..." for a deliberate beat. Add \
at most two delivery tags, chosen from [pause], [serious] and [curious]; [serious] belongs on the \
payoff when the subject deserves it. Tags are stage direction, never narration, and never open \
the script.

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

ALSO produce, for the feed and for search:
- "title": in English, at most 7 words and 44 characters, the searchable name first, stating the \
claim the reel delivers. It is also the banner on the first frame, so it must be short.
- "caption": two lines. Line 1 restates the claim with its main keyword. Line 2 is one sentence on \
why it matters. No links and no "Sources" line (the fetched sources are attached in code, and a \
remembered URL is usually a dead one), and no question to the viewer.
- "hashtags": at most two, each naming the story's subject or event.
- "tags": at most six search terms: the names in the story and their alternate spellings (Hindi \
spellings allowed). No '#'.
- "key_points": 2-3 very short on-screen text cards (4 words or fewer each), the plainest facts or \
numbers.
- "key_number": the one number that carries the story (a count, an amount, a percentage, a date \
or a year), copied exactly as it is written in script_body, with its unit when the unit is \
written next to it ("286 days", "40%"); an empty string when the story has none.
- "payoff": the "why it matters" sentence, copied exactly from script_body.
- "optional": the sentences that could be cut without losing the story (never sentence one or \
the payoff), each copied exactly from script_body; an empty list when there are none.
- "structure": the structure you followed: what-happened, number or belief.

Return ONLY a JSON object, no markdown fences. Write every line break inside a string as the \
two-character escape \\n — a raw newline inside a JSON string is invalid JSON. Inside a string, \
put any quoted word in SINGLE quotes ('like this'): a raw double quote ends the string.
{{"title": "the title", "script_body": "the spoken narration", "caption": "line one\\nline two", "hashtags": ["#subject"], "tags": ["a name", "another spelling"], "key_points": ["card", "card"], "key_number": "the number", "payoff": "the why-it-matters sentence", "optional": ["a sentence that could go"], "structure": "what-happened"}}
"""


# Stories that take the calm, respectful read (docs/08 excludes graphic tragedy exploitation).
# The audit found the old fixed sarcastic voice applied to war strikes and a child-abuse story;
# the voice is plain since 2026-11-12, and a story about deaths still gets the somber note and
# the somber voice. Matched on the idea's own words, so the tone is decided before writing.
# Widened 2026-10-09: 'Russian missiles kill 3', an air crash and a terror attack all read as
# not somber because the base and -ing forms were missing (ideas 178, 180, 211). Words that
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

TONE — this story involves loss of life or serious harm to people. Calm, respectful and direct,
with no irony about the people affected, and only [serious] or [pause] as delivery tags. The
"why it matters" sentence is still required, stated plainly (live 2026-09-27, a somber draft
dropped it), and "payoff" still marks it."""


def tone_for(idea: dict, body: str = "") -> str:
    """'somber' for stories about deaths or serious harm, else 'plain' (the channel voice).
    Off with ENABLE_SOMBER_TONE=false.

    `body` (the finished narration) catches what the idea's own words did not: idea 211's
    pitch read as not somber while its script said 'killed a woman'."""
    if not config.get_bool("ENABLE_SOMBER_TONE", True):
        return "plain"
    text = " ".join(str(idea.get(k) or "") for k in ("title", "hook", "angle")) + " " + body
    return "somber" if _SOMBER_RE.search(text) else "plain"


def _copies_the_angle(body: str, angle: str, run: int = 8) -> bool:
    """True if the narration repeats `run` or more consecutive words of the ideation angle.

    The audit found the 'why it matters' payoff was often the angle pasted verbatim: the
    originality signal (docs/08 §1) written by the idea generator, not the writer."""
    a = re.findall(r"[a-z0-9']+", (angle or "").lower())
    b = " " + " ".join(re.findall(r"[a-z0-9']+", (body or "").lower())) + " "
    return any(f" {' '.join(a[i:i + run])} " in b for i in range(max(0, len(a) - run + 1)))


# Design 9.3: the true surprising fact is always sentence one; a structure is what follows it.
# Each block describes moves, never phrases to copy.
_FALL_BACK = (" If the sources do not support this, follow what-happened instead and say so in "
              "\"structure\".")
STRUCTURES = {
    "what-happened": ("After sentence one: how it happened, then why it matters, then what is "
                      "scheduled next, only when the sources record a scheduled step."),
    "number": ("Sentence one's fact is a number. After it: what the number measures, what it "
               "compares with, then why it matters." + _FALL_BACK),
    "belief": ("After sentence one: the common belief this fact overturns, stated as a belief and "
               "only when a source records that belief; then the evidence; then why it matters."
               + _FALL_BACK),
}


def structure_for(idea: dict) -> str:
    """This idea's structure: a hash of its id, so a rerun gets the same one and a digest's size
    cannot lock the choice; a somber story always takes what-happened (design 9.3)."""
    if tone_for(idea) == "somber":
        return "what-happened"
    names = list(STRUCTURES)
    return names[int(hashlib.sha1(str(idea.get("id")).encode()).hexdigest(), 16) % len(names)]


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
        structure=STRUCTURES[structure_for(idea)],
        target_seconds=f"{_seconds('SCRIPT_TARGET_SECONDS', 27):g}",
        target_words=_target_words(),
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


# Design 9.4: one title, which is also the frame-1 banner. At 44 characters it always fits the
# banner at full size (three lines of 16); titles of 7 words or fewer were picked up 15 of 23 times
# against 3 of 17 since late July.
_TITLE_MAX = 44
_TITLE_MAX_WORDS = 7

_SHORTEN_TITLE_PROMPT = """Shorten this YouTube Shorts title to at most {max_words} words and at \
most {max_chars} characters. Put the searchable name first, and state the claim the video \
delivers. Use only what the title or the narration already says: add no number, name or claim.

TITLE: {title}
NARRATION: {body}

Return ONLY a JSON object: {{"title": "the shortened title"}}"""


def _title_fits(title: str) -> bool:
    return len(title) <= _TITLE_MAX and len(title.split()) <= _TITLE_MAX_WORDS


def _cut_title(title: str) -> str:
    """The mechanical fit: the head before a dash or colon when it fits and still reads as a title
    (an 84-character "...Last Minute—Why It Almost Crashed the System" overflowed the banner),
    else the longest run of whole words from the start that fits."""
    for sep in ("—", " – ", " - ", ": "):
        head = title.split(sep)[0].strip()
        if head != title and len(head) >= 20 and _title_fits(head):
            return head
    words = title.split()[:_TITLE_MAX_WORDS]
    while words and len(" ".join(words)) > _TITLE_MAX:
        words.pop()
    # A single word longer than the limit has no boundary to cut at.
    return " ".join(words).rstrip(" :,;-—–") or title[:_TITLE_MAX].strip()


def _shorten_title(title: str, body: str) -> str:
    """Hold the title to 7 words and 44 characters: the prompt asks, this makes it true. Over
    either limit the model is asked once to shorten it, and its answer is taken only within both
    limits and with no number the title and the narration lack; else the title is cut at a word.
    Never raises."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if _title_fits(title):
        return title
    new = ""
    try:
        data = _parse_llm_json(llm.generate(
            _SHORTEN_TITLE_PROMPT.format(max_words=_TITLE_MAX_WORDS, max_chars=_TITLE_MAX,
                                         title=title, body=body),
            json=True, max_tokens=512))
        new = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()
    except Exception as e:  # noqa: BLE001 — the word cut below is the fallback
        log.warning("scriptwriter: title shortening failed (%s)", e)
    if new:
        added = _added_facts({"title": new}, f"{title}\n{body}")
        if _title_fits(new) and not added:
            log.info("scriptwriter: title shortened to %r", new)
            return new
        log.warning("scriptwriter: shortened title refused (%s)",
                    f"adds {added}" if added else f"{new!r} is still too long")
    return _cut_title(title)


# Design 9.5: the budget is set in seconds and converted to words at 2.2 a second.
_WORDS_PER_SECOND = 2.2


def _seconds(key: str, default: float) -> float:
    try:
        return float(config.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _max_words() -> int:
    """The spoken-word cap: SCRIPT_MAX_WORDS when set, else SCRIPT_MAX_SECONDS (33 s, 73 words)."""
    try:
        return max(30, int(config.get("SCRIPT_MAX_WORDS")))
    except (TypeError, ValueError):
        return max(30, round(_seconds("SCRIPT_MAX_SECONDS", 33) * _WORDS_PER_SECOND))


def _target_words() -> int:
    """The length the writer aims at: SCRIPT_TARGET_SECONDS (27 s, 59 words)."""
    return max(20, round(_seconds("SCRIPT_TARGET_SECONDS", 27) * _WORDS_PER_SECOND))


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

RESEARCH DRAFT — {searched}. You have no web access, so ignore the instruction above to use web \
search: this draft and the SOURCES are your fact base. Every name, number, date, quote and claim \
you state must already be in one of them, unchanged, and you add none. Everything else is yours \
to rewrite: the opening, the wording, the rhythm, the title, the caption and the tags. Write the \
best script you can, in the JSON format above.
{draft}"""
_DRAFT_SEARCHED = ("written by a model that searched the live web for this story while writing it, "
                   "so its facts were checked against current reporting")
_DRAFT_UNSEARCHED = ("a draft whose search could not be confirmed, so its facts are no stronger "
                     "than the SOURCES")

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


def _claude_write(prompt: str, draft: dict,
                  searched: bool = False) -> tuple[dict | None, dict | None]:
    """Claude's version of the script, or None to ship the grounded draft, plus the reason
    worth reporting when Claude could not write (None otherwise). Fail-soft (rule 11): no key, a
    spent budget, an API error, an unusable reply or an added fact all return None.

    `searched` (the draft came back with search citations) decides whether Claude is told the
    draft's facts were checked against current reporting."""
    note = _CLAUDE_DRAFT_NOTE.format(searched=_DRAFT_SEARCHED if searched else _DRAFT_UNSEARCHED,
                                     draft=json.dumps(draft, ensure_ascii=False))
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
    # The fact base is what the draft publishes, not its bookkeeping: a mark like
    # "payoff_index": 3 made "three" look like a sourced fact (final review, 2026-11-12).
    facts = {k: draft[k] for k in _DRAFT_FACT_KEYS if k in draft}
    added = _added_facts(data, _idea_lines(prompt) + "\n" + json.dumps(facts, ensure_ascii=False))
    if added:
        log.warning("scriptwriter: Claude's script adds %s, which the grounded draft does not "
                    "carry; shipping the draft", ", ".join(added))
        return None, None
    return data, None


# The draft fields that carry facts; the rest (the writer's marks, its structure) do not.
_DRAFT_FACT_KEYS = ("title", "script_body", "caption", "key_points", "tags", "hashtags")


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
    # What the draft's search did (design 9.7): the number of real citations behind it, so
    # "the draft searched" is measured, and Claude is told it only when it is true.
    meta: dict = {}
    if config.get_bool("ENABLE_GROUNDED_SCRIPT", True):
        try:
            data = _parse_llm_json(llm.generate_grounded(prompt, max_tokens=2048, meta=meta))
            if (data.get("script_body") or "").strip():
                draft = data
        except Exception as e:  # noqa: BLE001 — grounded write is best-effort; fall back
            log.warning("scriptwriter: grounded write unusable (%s)", e)
    else:
        log.info("scriptwriter: grounded write disabled.")
    if draft is None:
        log.info("scriptwriter: no grounded draft, so no Claude call; using ungrounded JSON mode.")
        return {**_parse_llm_json(llm.generate(prompt, json=True, max_tokens=2048)),
                "writer": "gemini", "grounding": {"draft_citations": None}}
    grounding = {"draft_citations": meta.get("citations")}
    if not config.get_bool("ENABLE_CLAUDE_SCRIPT", True):
        return {**draft, "writer": "gemini-grounded", "grounding": grounding}
    written, issue = _claude_write(prompt, draft, searched=bool(meta.get("citations")))
    if written:
        return {**written, "writer": "claude", "grounding": grounding}
    return {**draft, "writer": "gemini-grounded", "claude_issue": issue, "grounding": grounding}


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
    # The opening check runs before the punch-up, so a rewrite that reopens on "So, ..." or a date
    # would ship unchecked (final review, 2026-11-12): it must pass the same check.
    if new_body and opening_problem(new_body) is not None:
        log.info("scriptwriter: punch-up broke the opening (%s); keeping original.",
                 opening_problem(new_body))
        return title, body
    # Every model-written rewrite passes the added-facts guard (design 9.6): the prompt forbids
    # new facts, and this makes it true.
    added = _added_facts({"script_body": new_body, "title": new_title}, f"{title}\n{body}")
    if added:
        log.info("scriptwriter: punch-up adds %s; keeping original.", ", ".join(added))
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


def _words_of(text: str) -> list[str]:
    """A sentence's spoken words, lower-cased, without punctuation or tags: how a sentence the
    writer copied is compared with ours."""
    out = []
    for word in _visible_words(text or ""):
        word = re.sub(r"[^\w']", "", word.lower().replace("’", "'"))
        if word:
            out.append(word)
    return out


def _locate(body: str, sentence: str | None) -> list[int]:
    """The indices of our sentences that together are `sentence`, one the writer copied from its
    script (its payoff, or one it marked optional); [] when it is not there.

    The writer marks sentences by their text, not their position (design 9.1, 9.5), because it
    counts sentences its own way: "The winner is... India." is one sentence to it and two to our
    splitter, so an index landed one sentence early (final review, 2026-11-12). Matched on the
    exact run of spoken words, so a sentence our splitter cuts in two is still found whole, and
    following the text through every cut and rewrite keeps the mark on the right sentence."""
    target = _words_of(sentence or "")
    if len(target) < 2:
        return []
    words = [_words_of(s) for s in _sentences(body)]
    for i in range(len(words)):
        got: list[str] = []
        for j in range(i, len(words)):
            got += words[j]
            if got == target:
                return list(range(i, j + 1))
            if got != target[:len(got)]:
                break
    return []


def _payoff_start(body: str, payoff: str | None = None) -> int | None:
    """Offset where the 'why it matters' sentence begins, or None when it cannot be placed.

    The writer's marked `payoff` (its text) is used when it is in the body and is not sentence
    one, which needs no tag and must never open on one; otherwise the bridge phrase is matched,
    as before the writer marked its payoff."""
    span = _locate(body, payoff)
    if span and span[0] > 0:
        return sentence_ends(body)[span[0] - 1]
    m = _WHY_IT_MATTERS_RE.search(body)
    if not m:
        return None
    starts = sentence_ends(body, 0, m.start())
    return starts[-1] if starts else 0


# A call to action is the cheapest sentence in the script: it carries no fact and no payoff.
_CTA_RE = re.compile(r"(?i)\b(subscribe|follow (?:us|for|along)|hit (?:the )?(?:like|bell)|"
                     r"like and share|comment below|drop a comment|share this)\b")


def _sentences(body: str) -> list[str]:
    """Split into sentences; a delivery tag stays with the sentence it introduces."""
    return split_sentences(body)


def _truncate_to_words(body: str, max_words: int, payoff: list[int] | None = None) -> str:
    """Hard length backstop: drop WHOLE sentences until the body fits max_words. Deterministic.

    Delivery tags are carried through with their sentence and do not count toward the cap.

    Two protected sentences: the hook (first) and the 'why it matters' turn, which is the
    originality signal the monetization gate turns on (docs/08 §1); `payoff` (our sentence
    indices, from `_locate`) names that turn when the writer marked it, else the bridge phrase is
    matched. Everything else goes in
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

    protected = {i for i in (payoff or []) if 0 <= i < len(sents)}
    if not protected:
        bridge = next((i for i, x in enumerate(sents) if _WHY_IT_MATTERS_RE.search(x)), None)
        protected = {bridge} if bridge is not None else set()
    bridge = max(protected) if protected else None  # the payoff's last sentence
    # The loop-back close is the last sentence that is not a call to action.
    last = max((i for i, x in enumerate(sents) if not _CTA_RE.search(x)), default=len(sents) - 1)
    cost: dict[int, tuple[int, int]] = {}
    for i, sent in enumerate(sents):
        if i == 0 or i in protected:
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


def _drop_optional(body: str, optional: list[str], payoff: str | None, max_words: int) -> str:
    """Drop the sentences the writer marked optional (their text), from the end, until the body
    fits; never sentence one or the payoff (design 9.5). The result may still be over the cap."""
    sents = _sentences(body)
    protected = {0, *_locate(body, payoff)}
    spans = {tuple(sp) for sp in (_locate(body, s) for s in optional) if sp}
    keep = set(range(len(sents)))
    for span in sorted((sp for sp in spans if not protected & set(sp)), reverse=True):
        if len(_visible_words(" ".join(sents[j] for j in sorted(keep)))) <= max_words:
            break
        keep -= set(span)
    return " ".join(sents[j] for j in sorted(keep))


def _enforce_length(body: str, idea_id, optional: list[str] | None = None,
                    payoff: str | None = None) -> str:
    """Bring the body under the cap (design 9.5): the sentences the writer marked optional, from
    the end; then the tighten rewrite, retired by default (ENABLE_SCRIPT_TIGHTEN); then whole
    sentences, keeping sentence one and the payoff (`payoff`, its text, when the writer marked
    it). The writer's marks are found by their text (`_locate`)."""
    max_words = _max_words()
    words = len(_visible_words(body))
    if words <= max_words:
        return body
    log.warning("scriptwriter: idea %s script %d words > %d cap; cutting.",
                idea_id, words, max_words)
    if optional:
        body = _drop_optional(body, optional, payoff, max_words)
        if len(_visible_words(body)) <= max_words:
            log.info("scriptwriter: idea %s fits after its optional sentences (%d words).",
                     idea_id, len(_visible_words(body)))
            return body
    if config.get_bool("ENABLE_SCRIPT_TIGHTEN", False):
        tight = _tighten(body, max_words)
        if tight:
            log.info("scriptwriter: idea %s tightened %d -> %d words.",
                     idea_id, words, len(_visible_words(tight)))
            return tight
    return _truncate_to_words(body, max_words, payoff=_locate(body, payoff) or None)


_URL_RE = re.compile(r"https?://\S+")
_SOURCES_LINE_RE = re.compile(r"(?im)^[ \t]*sources?[ \t]*:.*$")
_MAX_CAPTION_SOURCES = 3


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _publishable_sources(sources: list[str]) -> list[str]:
    """The sources worth printing: publisher links, one per outlet, at most three (design 9.9:
    61% of the newest 30 descriptions' links were aggregators). A Google News link is kept only
    when there is no publisher, and an unresolved grounding redirect (it expires, and some 404
    from the start) only when there is nothing else: a reel with no citation at all is the worse
    failure (docs/08)."""
    seen, publisher, gnews, redirects = set(), [], [], []
    for raw in sources or []:
        url = str(raw).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = _host(url)
        if "grounding-api-redirect" in url or host.endswith("vertexaisearch.cloud.google.com"):
            redirects.append(url)
        elif host == "news.google.com":
            gnews.append(url)
        elif host and host not in seen:
            seen.add(host)
            publisher.append(url)
    return publisher[:_MAX_CAPTION_SOURCES] or gnews[:1] or redirects[:1]


# How a source is named in the description; any other host is printed as it is.
_PUBLISHER_NAMES = {
    "thehindu.com": "The Hindu", "indianexpress.com": "The Indian Express",
    "hindustantimes.com": "Hindustan Times", "timesofindia.indiatimes.com": "The Times of India",
    "economictimes.indiatimes.com": "The Economic Times", "livemint.com": "Mint",
    "business-standard.com": "Business Standard", "ndtv.com": "NDTV", "indiatoday.in": "India Today",
    "news18.com": "News18", "thehindubusinessline.com": "BusinessLine", "theprint.in": "ThePrint",
    "scroll.in": "Scroll", "thewire.in": "The Wire", "moneycontrol.com": "Moneycontrol",
    "deccanherald.com": "Deccan Herald", "firstpost.com": "Firstpost", "pib.gov.in": "PIB",
    "isro.gov.in": "ISRO", "reuters.com": "Reuters", "apnews.com": "AP News", "afp.com": "AFP",
    "bbc.com": "BBC", "bbc.co.uk": "BBC", "aljazeera.com": "Al Jazeera",
    "theguardian.com": "The Guardian", "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post", "wsj.com": "The Wall Street Journal",
    "bloomberg.com": "Bloomberg", "ft.com": "Financial Times", "cnn.com": "CNN",
    "cnbc.com": "CNBC", "dw.com": "DW", "france24.com": "France 24", "nasa.gov": "NASA",
    "who.int": "WHO", "techcrunch.com": "TechCrunch", "theverge.com": "The Verge",
    "news.google.com": "Google News", "vertexaisearch.cloud.google.com": "Google Search",
}


def _publisher_name(url: str) -> str:
    host = _host(url)
    return _PUBLISHER_NAMES.get(host, host)


def _ensure_sources(caption: str, sources: list[str]) -> str:
    """Exactly ONE 'Sources:' block, built from the idea's fetched sources (sourcing gate), each
    line the publisher's name and its own link (design 9.9).

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
    block = "Sources:" + "".join(f"\n{_publisher_name(u)}: {u}" for u in usable)
    return f"{text}\n\n{block}" if text else block


def caption_for(summary: str, sources: list[str]) -> str:
    """The published caption from its summary (the claim and why it matters): markdown and any
    model-written links removed, the vetted sources added, then the disclosure line. Used for
    the writer's caption and for one the fact-check repair corrected."""
    return _ensure_disclosure(_ensure_sources(_strip_markdown(summary or ""), sources or []))


def _disclosure_line() -> str:
    """The disclosure that matches what the reel shows: VISUAL_SOURCE=ai_video means AI video
    shots, ai means Flux images, anything else stock (design 9.9)."""
    source = str(config.get("VISUAL_SOURCE", "photos") or "").strip().lower()
    if source == "ai_video":
        return DISCLOSURE_LINE_AI_VIDEO
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


def _ensure_delivery_tag(body: str, payoff: str | None = None) -> str:
    """Guarantee the script carries at least one delivery tag, on the 'why it matters' turn
    (`payoff`, the sentence the writer marked, when it is in the body; else the bridge phrase).

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

    at = _payoff_start(body, payoff)
    if at is None:
        log.info("scriptwriter: no delivery tag and no 'why it matters' sentence found; "
                 "leaving the script untagged rather than guessing a placement.")
        return body
    log.info("scriptwriter: script had no delivery tag; inserted [serious] on the payoff turn.")
    return f"{body[:at]}[serious] {body[at:]}".strip()


_REPAIR_PROMPT = """A fact-checker blocked this YouTube Shorts narration about: {topic}
Its findings (each quotes a claim it judged false, sometimes with what is true instead):
{findings}

TITLE: {title}
DESCRIPTION: {summary}
ON-SCREEN CARDS: {cards}
NARRATION:
{body}

Use web search to check what is actually true about each flagged claim, then rewrite ONLY those
sentences so they are accurate. State only what the findings, the narration, the title, the
description or the cards already carry: when the truth needs a number or a name that none of
them has, remove the claim instead. Keep every other sentence word for word, including its
delivery tags. The narration must still OPEN with a complete, accurate sentence that says what
happened: if the flagged claim was the opening, replace it with a corrected opening, never just
delete it. Never start with a delivery tag or with "Because", "And", "But" or "So". Keep a "why it
matters" sentence. At most {max_words} spoken words. Plain text, no markdown. Correct the title
(at most {title_words} words and {title_chars} characters), the description and the cards too when
a finding is about them; otherwise return them unchanged.

Return ONLY a JSON object, no fences. Put any quoted word in SINGLE quotes, and write a line break
inside a string as \\n:
{{"script_body": "the corrected narration", "payoff": "its why-it-matters sentence, copied exactly", "title": "the title", "description": "the description", "key_points": ["card"]}}
"""


def repair_script(body: str, findings: list[str], topic: str | None = None,
                  title: str | None = None, summary: str | None = None,
                  key_points: list[str] | None = None,
                  payoff: str | None = None) -> dict | None:
    """Rewrite only what the fact-check blocked: {"script_body", "title", "summary",
    "key_points", "payoff"}, or None if the rewrite is unusable.

    A block used to throw the whole reel away, although the checker's findings usually say
    exactly what is true instead (idea 308: "the bill has already been signed into law"). The
    caller re-verifies the result, title, description (`summary`, the caption before its sources)
    and cards included, with the gate, so this can only ever make a reel eligible, never wave a
    false claim through (design 9.6). Like every model-written rewrite it adds no number or name
    that what it was given lacks, and it keeps a "why it matters" sentence: the writer's `payoff`
    as it was, or the one the repair marks."""
    if not findings:
        return None
    max_words = _max_words()
    title = (title or "").strip()
    summary = (summary or "").strip()
    cards = [str(c).strip() for c in (key_points or []) if str(c).strip()]
    # Today's date, like the writer and the gate: a grounded rewrite without it dated September
    # news to June (STATUS 2026-09-28).
    prompt = llm.today_line() + _REPAIR_PROMPT.format(topic=topic or "the news story",
                                   findings="\n".join(f"- {f}" for f in findings[:6]),
                                   title=title or "(none)", summary=summary or "(none)",
                                   cards="; ".join(cards) or "(none)", body=body,
                                   max_words=max_words, title_words=_TITLE_MAX_WORDS,
                                   title_chars=_TITLE_MAX)
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
    raw_new = _strip_markdown(str(data.get("script_body") or "").strip())
    # The payoff: the writer's, kept as it was, or the one the repair marks after rewriting it.
    marked = data.get("payoff")
    marked = marked.strip() if isinstance(marked, str) else ""
    if payoff and _locate(raw_new, payoff):
        payoff_new = payoff
    elif marked and _locate(raw_new, marked):
        payoff_new = marked
    else:
        payoff_new = None
    new = _enforce_length(raw_new, "repair", payoff=payoff_new)
    if not _opens_with_a_hook(new):
        # Live 2026-09-27 (idea 308): the first repair deleted the flagged opening and left the
        # reel starting "[pause] [sarcastic] Because nothing screams...". It passed the gate.
        log.warning("scriptwriter: repair lost the opening hook; the block stands.")
        return None
    if len(_visible_words(new)) < 40:
        return None
    # The bridge phrase was the only check here, and the new brief no longer asks for it, so a
    # repair could delete the payoff and pass (final review, 2026-11-12).
    payoff_new = payoff_new if payoff_new and _locate(new, payoff_new) else None
    if ((payoff or _WHY_IT_MATTERS_RE.search(body)) and payoff_new is None
            and not _WHY_IT_MATTERS_RE.search(new)):
        log.warning("scriptwriter: repair lost the 'why it matters' sentence; the block stands.")
        return None
    source_text = "\n".join([body, title, summary, *cards, topic or "", *map(str, findings)])
    added = _added_facts({"script_body": new}, source_text)
    if added:
        log.warning("scriptwriter: repair adds %s, which nothing it was given carries; the block "
                    "stands.", ", ".join(added))
        return None
    new_title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()
    if new_title and new_title != title:
        if _added_facts({"title": new_title}, source_text):
            log.warning("scriptwriter: repaired title %r adds a number; keeping the title.",
                        new_title)
            new_title = title
        else:
            new_title = _shorten_title(new_title, new)
    # The description and the cards are published claims too (design 9.6): repaired when a
    # finding is about them, and kept as they were if the repair adds a number to them.
    new_summary = _strip_markdown(str(data.get("description") or "").strip())
    if new_summary and new_summary != summary and _added_facts({"caption": new_summary},
                                                               source_text):
        log.warning("scriptwriter: repaired description adds a number; keeping the description.")
        new_summary = summary
    new_cards = data.get("key_points")
    new_cards = ([str(c).strip() for c in new_cards if str(c).strip()][:5]
                 if isinstance(new_cards, list) else [])
    if new_cards and new_cards != cards and _added_facts({"key_points": new_cards}, source_text):
        log.warning("scriptwriter: repaired cards add a number; keeping the cards.")
        new_cards = cards
    return {"script_body": _ensure_delivery_tag(new, payoff_new), "title": new_title or title,
            "summary": new_summary or summary, "key_points": new_cards or cards,
            "payoff": payoff_new}


_DANGLING_OPENERS = ("because", "and", "but", "so", "which", "or")


# Openers that wind up instead of stating the news (design 9.2). Scripts that started on one were
# picked up (100+ views) 9 times in 41, against 21 in 46 for scripts starting on the subject, and
# the gap held within the same topic and month (audit data 4, checked 2026-11-12).
# A word alone is a wind-up only in context (final review, 2026-11-12): "So far this year" and
# "So India banned" are not "So, ...", "Imagine Dragons" and "Let's Encrypt" are names.
_PHRASE_WIND_UPS = ("did you know", "picture this", "ever wondered", "guess what")
_COMMA_WIND_UPS = ("so", "okay", "ok", "alright")   # set off by a comma or dash
_LOWER_WIND_UPS = ("imagine", "here's", "let's")    # before a lower-case word
# Never wind-ups, never cut: removing one turns a hedged claim into a flat one before the gate.
_HEDGES = ("apparently", "reportedly", "allegedly")
_SET_OFF = (",", "—", "–", "-")
_DATE_WORDS = frozenset((
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "sept", "oct", "nov", "dec", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "yesterday", "today", "tonight"))
_OPENING_PROMPT = """Rewrite ONLY the first sentence of this YouTube Shorts narration.
The problem with it: {problem}.

The new first sentence states the story's newest or most surprising true fact, with its subject
in the first few words. It does not start with a wind-up word, a date, a day or a greeting. It
uses only facts already in the narration: no new number, name, date or claim. At most 20 words.

NARRATION:
{body}

Output ONE valid JSON object and nothing else, no markdown or fences:
{{"first_sentence": "..."}}"""


def _plain(token: str) -> str:
    """A token lower-cased, curly apostrophes made straight, surrounding punctuation dropped."""
    return token.replace("’", "'").strip("\"'“”‘,.:;!?—–-").lower()


def _plain_words(sentence: str) -> list[str]:
    """Spoken words, lower-cased, without the punctuation around them."""
    return [_plain(w) for w in _visible_words(sentence)]


def _set_off(token: str) -> bool:
    """True when a token ends in a comma or a dash ("So," or "So—")."""
    return token.rstrip("\"'”’").endswith(_SET_OFF)


def _wind_up(raw: list[str]) -> tuple[str, int] | None:
    """(the wind-up, how many tokens it spans) at the start of a sentence's tokens, or None."""
    if not raw:
        return None
    plain = [_plain(t) for t in raw]
    for w in _PHRASE_WIND_UPS:
        n = len(w.split())
        if " ".join(plain[:n]) == w:
            return w, n
    lower_next = len(raw) > 1 and raw[1][:1].islower()
    if plain[0] in _COMMA_WIND_UPS and (_set_off(raw[0]) or (plain[0] != "so" and lower_next)):
        return plain[0], 1
    if plain[0] in _LOWER_WIND_UPS and lower_next:
        return plain[0], 1
    return None


def opening_problem(body: str) -> str | None:
    """What is wrong with the narration's opening, or None when it starts on the news.

    Checked on every script before the fact-check (it used to run only inside the repair pass):
    no leading tag, at least five spoken words in sentence one, no wind-up word, no date or day
    first, no dangling conjunction. A hedge ("Apparently, ...") is fine."""
    text = (body or "").lstrip()
    if not text:
        return "the script is empty"
    if text.startswith("["):
        return "it opens on a delivery tag"
    sentences = _sentences(text)
    raw = _visible_words(sentences[0] if sentences else text)
    words = [_plain(t) for t in raw]
    if len(words) < 5:
        return "the first sentence has fewer than five words"
    found = _wind_up(raw)
    if found:
        return f"it opens on the wind-up '{found[0]}'"
    i = 1 if words[0] in ("on", "in", "by") else 0
    if words[i] in _DATE_WORDS or re.fullmatch(r"(?:19|20)\d\d", words[i]):
        return "it opens on a date or a day"
    if words[0] in _DANGLING_OPENERS and words[:2] != ["so", "far"]:
        return f"it opens on the conjunction '{words[0]}'"
    return None


def _cut_wind_up(sentence: str) -> str | None:
    """The sentence without its leading wind-up, capitalised, or None.

    Cut only where what is left is still the sentence: a wind-up set off by a comma or dash
    ("So, India banned ...") or "Did you know that ...", whose "that" goes too and whose question
    mark becomes a full stop. Anything else is left for the rewrite: cutting "Did you know" alone
    left "That India has 28 states now?" (final review, 2026-11-12)."""
    raw = sentence.split()
    found = _wind_up(_visible_words(sentence))
    if not found:
        return None
    w, n = found
    rest_tokens = raw[n:]
    if w == "did you know" and rest_tokens and _plain(rest_tokens[0]) == "that":
        rest_tokens = rest_tokens[1:]
    elif not _set_off(raw[n - 1]):
        return None
    rest = " ".join(rest_tokens).lstrip(" ,—–-")
    if w == "did you know" and rest.endswith("?"):
        rest = rest[:-1] + "."
    if len(_visible_words(rest)) < 5:
        return None
    return rest[0].upper() + rest[1:]


def _fix_opening(body: str, problem: str, source_text: str) -> str:
    """Fix the opening `opening_problem` found: one rewrite of sentence one, refused if it adds a
    number or a name `source_text` lacks; else a leading wind-up is cut when five words or more
    remain; else the body is kept as written. Never raises, never blocks a reel."""
    ends = sentence_ends(body)
    first, rest = (body[:ends[0]].strip(), body[ends[0]:].strip()) if ends else (body.strip(), "")
    new_first = ""
    try:
        data = _parse_llm_json(llm.generate(_OPENING_PROMPT.format(problem=problem, body=body),
                                            json=True, max_tokens=1024))
        new_first = str(data.get("first_sentence") or "").strip()
    except Exception as e:  # noqa: BLE001 — the mechanical cut below is the fallback
        log.warning("scriptwriter: opening rewrite failed (%s)", e)
    if new_first:
        candidate = f"{new_first} {rest}".strip()
        added = _added_facts({"script_body": new_first}, source_text)
        if opening_problem(candidate) is None and not added:
            log.info("scriptwriter: opening rewritten (%s).", problem)
            return candidate
        log.warning("scriptwriter: opening rewrite refused (%s).",
                    f"adds {added}" if added else opening_problem(candidate))
    cut = _cut_wind_up(first) if "wind-up" in problem else None
    if cut and opening_problem(f"{cut} {rest}".strip()) is None:
        log.info("scriptwriter: leading wind-up cut (%s).", problem)
        return f"{cut} {rest}".strip()
    log.warning("scriptwriter: opening left as written (%s).", problem)
    return body


def _opens_with_a_hook(body: str) -> bool:
    """True if the narration starts with a real sentence (see `opening_problem`)."""
    return opening_problem(body) is None


_KEY_NUMBER_MAX = 20  # characters: the number card is large (design 11.5)


def checked_key_number(value, body: str) -> str:
    """The writer's key number when it is copied exactly from the narration (design 11.5): it
    has a digit, it fits the card, and it occurs in `body` as a whole phrase, never inside a
    longer number ("2" in "2,000", "286" in "1286"). Otherwise "", and no number card shows: a
    wrong number on screen is worse than none."""
    number = re.sub(r"[\s.,;:!?]+$", "", str(value or "").strip())
    if not (number and body) or not re.search(r"\d", number) or len(number) > _KEY_NUMBER_MAX:
        return ""
    whole = r"(?<!\w)(?<!\d[.,])" + re.escape(number) + r"(?!\w)(?![.,]\d)"
    return number if re.search(whole, body, re.IGNORECASE) else ""


def write_script(idea: dict, template: str = "N") -> dict:
    """Generate {script_body, caption, hashtags[]} for an approved idea and persist it.

    Returns the same dict plus the new `script_id`. Raises ValueError if the LLM reply
    can't be parsed into a non-empty script (caller skips that one reel — rule 14: soft on
    runtime). Compliance fields (sources, disclosure) are enforced here, not trusted
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
    # With no title from the writer, the idea's own title is held to the same limits here, so the
    # fact-check and the banner see the title that is published.
    title = _shorten_title(str(data.get("title") or idea.get("title") or "").strip(), body)

    # The writer copies its payoff and the sentences it could lose (design 9.1, 9.5); they are
    # found by their text through every cut and rewrite (`_locate`). Without the marks, or with
    # a payoff that is not in the script, everything below works as it did: the bridge phrase
    # locates the payoff.
    payoff = data.get("payoff")
    payoff = payoff.strip() if isinstance(payoff, str) and payoff.strip() else None
    if payoff and not _locate(body, payoff):
        log.warning("scriptwriter: idea %s marked a payoff that is not a sentence of its script "
                    "(%r); using the bridge phrase instead", idea_id, payoff[:80])
        payoff = None
    optional = data.get("optional")
    optional = [s for s in optional if isinstance(s, str)] if isinstance(optional, list) else []

    # Fit the cap BEFORE the punch-up: the punch-up only accepts a rewrite that is under the cap,
    # so on the 100-word drafts every run was producing it could not act (9 of 16 logged
    # decisions were "unusable").
    body = _enforce_length(body, idea_id, optional, payoff)

    # The opening, on every script and before the gate (design 9.2): sentence one states the news.
    problem = opening_problem(body)
    if problem:
        source = " ".join([body, *(str(idea.get(k) or "") for k in ("title", "hook", "angle"))])
        body = _fix_opening(body, problem, source)

    # Scroll-stop judge: punch up a weak hook+title before we spend a render (fail-soft, no new facts).
    # Never on a somber story: a calm opening scores low, and the rewrite is shock copy, which
    # becomes the YouTube title and the frame-1 banner of a story about deaths. Off by default
    # since 2026-11-12 (design 9.2): a cheaper model rewrote the writer's opening on a "shock" score.
    if config.get_bool("ENABLE_HOOK_JUDGE", False) and tone_for(idea, body) != "somber":
        title, body = _punch_up_hook(title, body)
        title = _shorten_title(title, body)  # the punch-up writes its own title

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list):
        hashtags = []
    hashtags = [str(h).strip() for h in hashtags if str(h).strip()]

    # Markdown is stripped from the caption too: YouTube prints '*you*' with the asterisks.
    caption = caption_for(str(data.get("caption") or ""), idea.get("sources") or [])

    tags = data.get("tags")
    tags = [str(t).lstrip("#").strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []

    # Short on-screen text cards (story-specific visuals, burned by subtitles over the B-roll).
    kp = data.get("key_points")
    key_points = ([str(p).strip() for p in kp if str(p).strip()][:5]
                  if isinstance(kp, list) else [])

    # The punch-up is capped too; this is a no-op without it.
    body = _enforce_length(body, idea_id, payoff=payoff)
    # The marked payoff, if it survived the opening fix and any punch-up.
    payoff_now = payoff if payoff and _locate(body, payoff) else None
    if len(_visible_words(body)) < 50:
        log.warning("scriptwriter: idea %s script is short (%d words)",
                    idea_id, len(_visible_words(body)))

    # ORIGINALITY SIGNAL, not a style nit (docs/08 §1). A script with no "why it matters" turn is
    # a bare summary, which is exactly what YouTube's inauthentic-content policy demotes and what
    # the monetization gate turns on. Found live on script 158 (2026-08-07), where it was
    # invisible because nothing checked. Warn rather than block: accuracy already has a hard gate
    # (factcheck), and stacking a second blocking gate on a SOFT quality judgement would cost
    # reels for something a human should eyeball (rule 14 — soft on runtime). The writer's marked
    # payoff counts; the bridge phrase is the check only when there is no mark.
    if payoff_now is None and not _WHY_IT_MATTERS_RE.search(body):
        log.warning("scriptwriter: idea %s has NO 'why it matters' turn — that makes it a bare "
                    "summary, which is the originality/monetization risk (docs/08 §1). Review it.",
                    idea_id)

    if _copies_the_angle(body, idea.get("angle", "")):
        log.warning("scriptwriter: idea %s repeats the ideation angle word for word; the payoff "
                    "should be the writer's own analysis (docs/08 §1). Review it.", idea_id)

    # After the word cap, so truncation can never cut the tag back off. Tags are not spoken
    # words (_visible_words ignores them), so this cannot push the script over the cap.
    body = _ensure_delivery_tag(body, payoff_now)

    # The writer may fall back to what-happened and says so; anything else keeps the chosen one.
    said = str(data.get("structure") or "").strip().lower()
    structure = said if said in STRUCTURES else structure_for(idea)

    # Persist the published title too, so the analytics loop can learn which title STYLE wins
    # (db.top_performing_titles) — the dry idea title is a poor proxy for what viewers tapped.
    script_id = db.insert_script(idea_id, template, body, caption, hashtags, title or None,
                                 structure=structure)
    return {"script_id": script_id, "script_body": body, "caption": caption,
            "hashtags": hashtags, "title": title, "tags": tags, "key_points": key_points,
            "tone": tone_for(idea, body), "writer": data.get("writer"),
            "claude_issue": data.get("claude_issue"), "structure": structure,
            "grounding": data.get("grounding") or {"draft_citations": None},
            "payoff": payoff_now, "key_number": checked_key_number(data.get("key_number"), body)}
