"""Module 3b: Hinglish narration (design 7, Part B).

Contract:
    what it does : turns the fact-checked English script into two-text lines: `en`, the English
                   sentence the gate checked and the subtitles show, and `hi`, the same sentence as
                   spoken Hinglish, which the narrator says.
    how to use   : `to_hinglish(body, title, tone)` -> (spoken record | None, reason).
    depends on   : src.llm (Claude first, then Gemini, then Groq), src.text, src.config.

Behind NARRATION_LANGUAGE=hinglish. Every check here is code, not a model's word: the line count,
the numbers, the names, the scripts and the spoken length (7.3); a second model from another
provider then checks the meaning (7.4). Any failure is retried once with the failures listed; a
second failure ends Hinglish for the reel, which is then narrated in English (7.6). Numbers stay
digits in `hi` and code turns them into English words for the voice, so every spoken number is
the checked one.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from src import config, llm
from src.text import split_sentences

log = logging.getLogger(__name__)

# Measured on test 4: 78 Hinglish words in 27.0 s (design 7.3).
_HINGLISH_WORDS_PER_SECOND = 2.9

_TAG_RE = re.compile(r"\[[^\]]{0,24}\]")


def english_lines(body: str) -> list[str]:
    """The fact-checked script's sentences, delivery tags removed: one Hinglish line each."""
    out = []
    for sentence in split_sentences(body or ""):
        clean = re.sub(r"\s+", " ", _TAG_RE.sub(" ", sentence)).strip()
        if clean:
            out.append(clean)
    return out


# --- spoken numbers (design 7.3) -------------------------------------------------------------

_ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_ORDINAL_WORDS = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                  "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
_CURRENCY = {"₹": ("rupee", "rupees"), "rs": ("rupee", "rupees"), "$": ("dollar", "dollars"),
             "€": ("euro", "euros"), "£": ("pound", "pounds")}
_SCALE_WORDS = ("lakh", "crore", "thousand", "million", "billion", "trillion")
# A four-digit number before one of these is an amount, not a year.
_UNIT_WORDS = _SCALE_WORDS + ("rupees", "dollars", "people", "jobs", "students", "km",
                              "kilometres", "kilometers", "kg", "tonnes", "tons", "units", "mw",
                              "gw", "crores", "lakhs",
                              # the Hindi words that follow an amount in a Hinglish line
                              "लोग", "लोगों", "रुपये", "रुपए", "रुपयों", "साल", "सालों",
                              "किलोमीटर", "मीटर", "टन", "छात्र", "छात्रों", "नौकरियां",
                              "नौकरियों", "गांव", "गांवों", "परिवार", "परिवारों", "बच्चे",
                              "बच्चों")

# Devanagari letters and signs, without the danda (। ॥): a number before a full stop is read.
_DEVANAGARI_WORD = "ऀ-ॣ०-ॿ"

# The space after a currency symbol belongs to the symbol: an optional space of its own let a
# match start at the space after a Hindi vowel sign and swallow it ("यानीtwenty-five"). "Rs" and
# "Rs." count as the rupee sign. The scale may be compound or hyphenated ("₹1.5 lakh crore",
# "₹500-crore"), and the currency is said after the last scale word. A number glued to letters
# ("5G", "10x", "10km", "21वीं") is left for the voice to read, except an ordinal or a decade.
_NUMBER_RE = re.compile(
    r"(?<![\w.,])(?:(?P<cur>[₹$€£]|Rs\.?)\s?)?(?P<num>\d{1,3}(?:,\d{2,3})+|\d+)"
    r"(?:(?P<dec>\.\d+)|:(?P<min>\d{2}))?"
    r"(?:(?P<ord>st|nd|rd|th)|(?P<pct>%)|(?P<decade>s))?"
    r"(?P<scale>(?:[\s-]+(?:" + "|".join(_SCALE_WORDS) + r")\b)+)?"
    r"(?![\w" + _DEVANAGARI_WORD + r"])")
_INDIAN_GROUPS = re.compile(r"\d{1,2}(?:,\d{2})+,\d{3}")


def _below_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    words = [f"{_ONES[hundreds]} hundred"] if hundreds else []
    if rest or not hundreds:
        words.append(_below_100(rest))
    return " ".join(words)


def _cardinal(n: int, indian: bool = False) -> str:
    if n < 1000:
        return _below_1000(n)
    scales = (((10 ** 7, "crore"), (10 ** 5, "lakh"), (10 ** 3, "thousand")) if indian else
              ((10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"),
               (10 ** 3, "thousand")))
    for value, name in scales:
        if n >= value:
            count, rest = divmod(n, value)
            head = f"{_cardinal(count, indian)} {name}"
            return head if not rest else f"{head} {_cardinal(rest, indian)}"
    return _below_1000(n)


def _year(n: int) -> str:
    if 2000 <= n <= 2009:
        return "two thousand" + (f" {_ONES[n % 10]}" if n % 10 else "")
    high, low = divmod(n, 100)
    if not low:
        return f"{_below_100(high)} hundred"
    if low < 10:
        return f"{_below_100(high)} oh {_ONES[low]}"
    return f"{_below_100(high)} {_below_100(low)}"


def _ordinal(n: int) -> str:
    pieces = re.split(r"([ -])", _cardinal(n))
    last = pieces[-1]
    if last in _ORDINAL_WORDS:
        last = _ORDINAL_WORDS[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return "".join(pieces[:-1]) + last


def _plural(words: str) -> str:
    """'nineteen ninety' -> 'nineteen nineties' (a decade, "1990s")."""
    head, _, last = words.rpartition(" ")
    last = last[:-1] + "ies" if last.endswith("y") else last + "s"
    return f"{head} {last}".strip()


def _is_year(raw: str, value: int, m: re.Match, after: str) -> bool:
    if not re.fullmatch(r"\d{4}", raw) or not 1800 <= value <= 2099:
        return False
    if m.group("dec") or m.group("cur") or m.group("pct") or m.group("scale"):
        return False
    return not re.match(r"\s+(?:" + "|".join(_UNIT_WORDS) + r")(?![\w" + _DEVANAGARI_WORD
                        + r"])", after, re.I)


def _say(m: re.Match, text: str) -> str:
    raw, dec, cur = m.group("num"), m.group("dec"), m.group("cur")
    value = int(raw.replace(",", ""))
    scale = " ".join(re.findall(r"[a-z]+", (m.group("scale") or "").lower()))
    after = text[m.end():]
    if m.group("min") is not None:  # a time, "9:30"
        minutes = int(m.group("min"))
        hour = _cardinal(value)
        return hour + (" o'clock" if not minutes else
                       f" oh {_ONES[minutes]}" if minutes < 10 else f" {_below_100(minutes)}")
    if m.group("ord"):
        words = _ordinal(value)
    elif _is_year(raw, value, m, after):
        words = _year(value)
    else:
        words = _cardinal(value, indian=bool(_INDIAN_GROUPS.fullmatch(raw)))
        if dec:
            words += " point " + " ".join(_ONES[int(d)] for d in dec[1:])
    if m.group("decade"):
        words = _plural(words)
    if scale:
        words += f" {scale}"
    if m.group("pct"):
        words += " percent"
    if cur:
        one, many = _CURRENCY["rs" if cur.lower().startswith("rs") else cur]
        words += f" {one if value == 1 and not dec and not scale else many}"
    return words


def say_numbers(text: str) -> str:
    """Every number in `text` as English words, for the voice (design 7.3): years in pairs,
    decimals with "point", Indian grouping in lakh and crore, `%` as percent, currencies after
    the amount, ordinals. A number glued to a word ("G20") is left for the voice to read."""
    return _NUMBER_RE.sub(lambda m: _say(m, m.string), text or "")


def spoken_seconds(said: str) -> float:
    """The estimated length of spoken Hinglish, at the measured 2.9 words a second."""
    return len((said or "").split()) / _HINGLISH_WORDS_PER_SECOND


# --- the checks (design 7.3) -----------------------------------------------------------------

# Hindi number words: the number guard cannot see them, so `hi` may not carry any. एक is exempt,
# being also the article "a".
_HINDI_NUMBER_WORDS = frozenset(unicodedata.normalize("NFD", w) for w in (
    "दो तीन चार पाँच पांच छह छः छे सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह पन्द्रह सोलह सत्रह "
    "अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस चालीस पचास "
    "साठ सत्तर अस्सी नब्बे सौ हज़ार हजार लाख करोड़ करोड अरब").split())
_HI_TOKEN_SPLIT = re.compile(r"[\s,.;:!?।॥()\"'’‘“”—–\-]+")
# "Rs" and "Rs." count as the rupee sign: without them "Rs.900" was invisible to the guard.
_CHECK_NUMBER_RE = re.compile(
    r"(?<![\w.,])(?:[₹$€£]|Rs\.?)?\s?(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d+)?")
_DEVANAGARI_LETTER = re.compile(r"[ऀ-ॣॱ-ॿ]")
_PUNCTUATION = frozenset(".,;:!?'\"()-–—…।॥’‘“”/&")
_SYMBOLS = frozenset("₹$€£%°+")  # "45°C" and "50+" are ordinary in news
_JOINERS = frozenset("‌‍")  # ZWNJ and ZWJ: part of how Devanagari is written
# Capitalised words that start a clause, not names.
_NOT_NAMES = frozenset((
    "I The A An This That These Those It Its Here There But And So Now Why How What When Where "
    "Who If As At In On For With By From To Of Or Yet Still Even Just Then They We You He She "
    "Our Your Their His Her My").split())


def numbers_in(text: str) -> set[str]:
    return {m.group(1).replace(",", "") + (m.group(2) or "")
            for m in _CHECK_NUMBER_RE.finditer(text or "")}


# "U.S." is one name, not the names "U" and "S" (2026-11-13: the retry was told to write a
# "U" in Latin script and could not act on it, and "US" failed).
_ABBREVIATION = re.compile(r"(?:[A-Z]\.){2,}")
_NAME_TOKEN = re.compile(r"(?:[A-Z]\.){2,}|[A-Za-z][A-Za-z'’\-]*")


def names_in(en: str) -> list[str]:
    """Capitalised words that do not start the sentence or a clause after a colon; a dotted
    abbreviation ("U.S.") is one name."""
    tokens = list(_NAME_TOKEN.finditer(en))
    names = []
    for k, m in enumerate(tokens):
        if k == 0 or ":" in en[tokens[k - 1].end():m.start()]:
            continue
        if _ABBREVIATION.fullmatch(m.group(0)):
            names.append(m.group(0))
            continue
        for piece in m.group(0).split("-"):
            piece = re.sub(r"['’]s$", "", piece)
            if piece and piece[0].isupper() and piece not in _NOT_NAMES:
                names.append(piece)
    return names


def _name_written(name: str, hi: str) -> bool:
    """Whether `name` stands in `hi` in Latin script. Capitals do not count ("NVIDIA" is the
    brand's own spelling of Nvidia) and an abbreviation's dots are optional ("US" is "U.S.")."""
    if _ABBREVIATION.fullmatch(name):
        body = r"\.?".join(re.escape(c) for c in name.replace(".", "")) + r"\.?"
    else:
        body = re.escape(name)
    return re.search(rf"(?<![A-Za-z]){body}(?![A-Za-z])", hi, re.IGNORECASE) is not None


def _bad_characters(hi: str) -> list[str]:
    bad = []
    for c in hi:
        if (c.isspace() or c.isdigit() and c.isascii() or c in _PUNCTUATION or c in _SYMBOLS
                or c in _JOINERS or "ऀ" <= c <= "ॿ"
                or c.isalpha() and unicodedata.name(c, "").startswith("LATIN")):
            continue
        bad.append(c)
    return bad


def _band(name: str, default: float) -> float:
    try:
        return float(config.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def check(en_lines: list[str], lines: list[dict], min_seconds: float | None = None,
          max_seconds: float | None = None) -> list[str]:
    """What is wrong with a rendering, as messages for the retry; [] when it passes.

    One line per English sentence, numbered as sent; every number of `en` in `hi` and none
    added, and no Hindi number word; every name of `en` in `hi` in Latin script; Devanagari
    present and no character outside Devanagari, Latin, digits and ordinary punctuation; the
    spoken length inside HINGLISH_MIN_SECONDS-HINGLISH_MAX_SECONDS (24-36 s)."""
    failures: list[str] = []
    numbered = {}
    for line in lines or []:
        try:
            i = int(line.get("i"))
        except (TypeError, ValueError, AttributeError):
            failures.append(f"a line has no usable number: {line!r:.80}")
            continue
        if i in numbered:
            failures.append(f"line {i} appears twice")
        numbered[i] = str(line.get("hi") or "").strip()
    wanted = set(range(1, len(en_lines) + 1))
    if missing := sorted(wanted - set(numbered)):
        failures.append(f"lines {missing} are missing ({len(numbered)} returned for "
                        f"{len(en_lines)} sentences)")
    if extra := sorted(set(numbered) - wanted):
        failures.append(f"lines {extra} do not exist (there are {len(en_lines)} sentences)")

    for i, en in enumerate(en_lines, 1):
        if i not in numbered:
            continue  # reported as missing above
        hi = numbered[i]
        if not hi:
            # Present but blank used to pass every check: a narration missing a sentence.
            failures.append(f"line {i} is empty")
            continue
        for n in sorted(numbers_in(en) - numbers_in(hi)):
            failures.append(f"line {i}: the number {n} is missing; keep it as digits")
        for n in sorted(numbers_in(hi) - numbers_in(en)):
            failures.append(f"line {i}: the number {n} is not in the English")
        tokens = _HI_TOKEN_SPLIT.split(unicodedata.normalize("NFD", hi))
        for word in sorted({t for t in tokens if t in _HINDI_NUMBER_WORDS}):
            failures.append(f"line {i}: the Hindi number word "
                            f"{unicodedata.normalize('NFC', word)!r}; write the number as the "
                            f"English has it")
        for name in names_in(en):
            if not _name_written(name, hi):
                failures.append(f"line {i}: the name {name!r} must appear in Latin script")
        if not _DEVANAGARI_LETTER.search(hi):
            failures.append(f"line {i}: no Devanagari; write the Hindi words in Devanagari")
        if bad := _bad_characters(hi):
            failures.append(f"line {i}: the character(s) {''.join(sorted(set(bad)))!r} are "
                            f"not allowed")

    said = " ".join(say_numbers(numbered[i]) for i in sorted(numbered) if i in wanted)
    low = _band("HINGLISH_MIN_SECONDS", 24) if min_seconds is None else min_seconds
    high = _band("HINGLISH_MAX_SECONDS", 36) if max_seconds is None else max_seconds
    seconds = spoken_seconds(said)
    if not low <= seconds <= high:
        failures.append(f"the spoken length is about {seconds:.1f} seconds, outside "
                        f"{low:g}-{high:g} seconds")
    return failures


# --- rendering (design 7.2) ------------------------------------------------------------------

# The renderer returns each line in spoken order as `parts` too, for the subtitles (7.7). The
# English line is not echoed back: code pairs by number.
_RENDER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["i", "hi", "parts"],
        "properties": {
            "i": {"type": "integer"},
            "hi": {"type": "string"},
            "parts": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["hi", "en"],
                "properties": {"hi": {"type": "string"}, "en": {"type": "string"}}}}}}}}}

_TONES = {"somber": "somber: calm and respectful, about loss of life or serious harm",
          "plain": "plain: a clear, curious, confident explainer"}

# Rules, described as moves, with no phrases to copy (design 9.1's rule holds here too).
_RENDER_PROMPT = """You turn a fact-checked English narration for a YouTube Short into spoken \
Hinglish for viewers in India, line by line.

THE STORY: {title}
TONE: {tone}

ENGLISH LINES (write one Hinglish line for each, with the same number):
{lines}

RULES FOR EACH HINGLISH LINE ("hi"):
- Natural spoken Hinglish of young urban Indian creators: Hindi grammar, with English words where \
an urban speaker would use them; conversational, not news-anchor Hindi.
- Hindi words in Devanagari, English words in Latin script.
- Say exactly what its English line says: nothing added, nothing dropped, no claim softened or \
sharpened.
- Keep every number exactly as the English writes it: digits stay digits, with their %, ₹ or $, \
and a number the English spells as a word stays that English word. Never a Hindi number word.
- Names, places, months, organisations and brands stay in Latin script exactly as in the English.
- Line 1 has at most 12 words, with its subject or its surprise inside the first four; it never \
opens on a date, a place or a greeting, nor on a question about whether the viewer knows.
- End each line with the Hindi full stop । or a question mark. No delivery tags, no emoji.

ALSO give each line its "parts", in spoken order, for the English subtitles: each part pairs a \
stretch of the Hinglish with the English words that say the same thing. The "hi" parts joined \
with single spaces are the line's "hi" exactly. The "en" parts use only that English line's own \
words, regrouped to follow the Hindi order, and together they carry all its numbers and names. \
Two to four parts for a long line, one for a short one.
{failures}
Return ONLY a JSON object: {{"lines": [{{"i": 1, "hi": "...", "parts": [{{"hi": "...", "en": \
"..."}}]}}]}}
"""


def _render_prompt(en_lines: list[str], title: str, tone: str,
                   failures: list[str] | None) -> str:
    numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(en_lines, 1))
    # "all N lines": told only about line 1, a retry once sent back line 1 alone (2026-11-13).
    fixes = (f"\nYOUR LAST VERSION FAILED THESE CHECKS; fix every one, and return all "
             f"{len(en_lines)} lines again, not only the lines named:\n"
             + "\n".join(f"- {f}" for f in failures) + "\n") if failures else ""
    return _RENDER_PROMPT.format(title=title or "(untitled)", tone=_TONES.get(tone, _TONES["plain"]),
                                 lines=numbered, failures=fixes)


def _parse_lines(raw: str) -> list[dict]:
    data = llm.parse_json_object(raw)
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not lines:
        raise ValueError("the reply has no lines")
    out = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        parts = [{"hi": str(p.get("hi") or "").strip(), "en": str(p.get("en") or "").strip()}
                 for p in (line.get("parts") or []) if isinstance(p, dict)]
        # A model may number its lines as text ("1"); every later step looks them up as numbers.
        number = line.get("i")
        try:
            number = int(number)
        except (TypeError, ValueError):
            pass
        out.append({"i": number, "hi": str(line.get("hi") or "").strip(), "parts": parts})
    return out


def render(en_lines: list[str], title: str, tone: str,
           failures: list[str] | None = None) -> tuple[list[dict], str]:
    """The Hinglish lines and who wrote them: Claude (structured output, the refusal fallback on,
    purpose "hinglish" in the claude_spend ledger), then Gemini, then Groq. `failures` are the
    last attempt's check failures, sent back for the retry. Raises RuntimeError when no renderer
    answers with usable lines."""
    prompt = _render_prompt(en_lines, title, tone, failures)
    renderers = (
        ("claude", lambda: llm.generate_claude(prompt, purpose="hinglish",
                                               schema=_RENDER_SCHEMA, fallbacks=True)),
        ("gemini", lambda: llm.generate_with("gemini", prompt, json=True, max_tokens=4096)),
        ("groq", lambda: llm.generate_with("groq", prompt, json=True, max_tokens=4096)),
    )
    errors = []
    for name, call in renderers:
        try:
            return _parse_lines(call()), name
        except Exception as e:  # noqa: BLE001 — the next renderer (rule 11)
            log.warning("hinglish: %s could not render (%s)", name, str(e)[:200])
            errors.append(f"{name}: {str(e)[:120]}")
    raise RuntimeError("hinglish: no renderer answered — " + " | ".join(errors))


# --- the meaning check (design 7.4) ----------------------------------------------------------

# Always another provider than the renderer's, so one model's mistake is not checked by itself.
# The first is design 7.4's checker; the next answers when it cannot run (2026-11-13: Gemini's
# 503 "high demand" sent a rendering that had passed every code check to English narration).
_CHECKERS_FOR = {"claude": ("gemini", "groq"), "gemini": ("groq",), "groq": ("gemini",)}

_MEANING_PROMPT = """You check a translation for a news video. Each numbered pair below is an \
English sentence and the spoken Hinglish line written for it.

{pairs}

For every pair, answer: does the Hinglish say the same as the English, with nothing added, \
nothing dropped, and no claim made stronger or weaker? Wording, word order and the mix of Hindi \
and English are free; only the meaning counts.

Return ONLY a JSON object with one entry per pair: {{"lines": [{{"i": 1, "same": true, "why": \
"what differs, when it does"}}]}}
"""


def meaning_check(en_lines: list[str], lines: list[dict],
                  renderer: str) -> tuple[list[str], str]:
    """Failures from a second model's line-by-line check, and that model's provider. A line
    judged different, or given no verdict, fails. The checker is design 7.4's for the renderer,
    else the next provider independent of it; when none can run, the lines fail under
    HINGLISH_STRICT (default on), or pass with a warning when it is off. Every verdict is logged:
    these checks were tested only on pairs written for the purpose (design 7.4)."""
    by_number = {line.get("i"): str(line.get("hi") or "") for line in lines}
    pairs = "\n".join(f"{i}. EN: {en}\n   HI: {by_number.get(i, '')}"
                      for i, en in enumerate(en_lines, 1))
    checkers = _CHECKERS_FOR.get(renderer, ("gemini", "groq"))
    verdicts, error = None, None
    for checker in checkers:  # never the renderer's own provider
        try:
            data = llm.parse_json_object(llm.generate_with(
                checker, _MEANING_PROMPT.format(pairs=pairs), json=True, max_tokens=2048))
            verdicts = {int(v.get("i")): v for v in data.get("lines") or []
                        if isinstance(v, dict)}
            break
        except Exception as e:  # noqa: BLE001 — the next independent checker, then strict
            log.warning("hinglish: the meaning check (%s) could not run (%s)", checker,
                        str(e)[:200])
            error = e
    if verdicts is None:
        e = error
        if config.get_bool("HINGLISH_STRICT", True):
            log.warning("hinglish: the meaning check (%s) could not run (%s); strict, so it fails",
                        checker, str(e)[:200])
            return [f"the meaning check could not run ({str(e)[:120]})"], checker
        log.warning("hinglish: the meaning check (%s) could not run (%s); HINGLISH_STRICT is "
                    "off, so the lines pass unchecked", checker, str(e)[:200])
        return [], checker
    failures = []
    for i in range(1, len(en_lines) + 1):
        verdict = verdicts.get(i)
        # A model may write the boolean as text ("true"); anything else is not a yes.
        same = bool(verdict) and str(verdict.get("same")).strip().lower() in ("true", "yes")
        why = str((verdict or {}).get("why") or "").strip()
        log.info("hinglish: meaning check by %s: line %d %s%s", checker, i,
                 "same" if same else "DIFFERENT" if verdict else "no verdict",
                 f" ({why})" if why else "")
        if not verdict:
            failures.append(f"line {i}: the meaning check gave no verdict")
        elif not same:
            failures.append(f"line {i}: the meaning differs from the English"
                            + (f" ({why})" if why else ""))
    return failures, checker


# --- script to spoken lines ------------------------------------------------------------------

def _spoken(en_lines: list[str], lines: list[dict], renderer: str, checker: str) -> dict:
    by_number = {int(line["i"]): line for line in lines}
    out = []
    for i, en in enumerate(en_lines, 1):
        hi = by_number[i]["hi"]
        out.append({"en": en, "hi": hi, "said": say_numbers(hi),
                    "parts": by_number[i].get("parts") or []})
    return {"language": "hi", "lines": out, "said": " ".join(line["said"] for line in out),
            "renderer": renderer, "checker": checker}


def to_hinglish(body: str, title: str, tone: str) -> tuple[dict | None, str]:
    """The fact-checked script as checked spoken Hinglish lines, or (None, why not).

    One rendering, the code checks, then the meaning check; any failure sends the whole
    rendering back once with the failures listed, and a second failure ends Hinglish for the
    reel (design 7.3-7.4), which is then narrated in English. The record keeps each line's
    English, its Hinglish and what the voice says (digits as words), for the script row."""
    en = english_lines(body)
    if not en:
        return None, "the script has no sentences"
    failures: list[str] | None = None
    for attempt in (1, 2):
        try:
            lines, renderer = render(en, title, tone, failures)
        except RuntimeError as e:
            return None, str(e)
        failures = check(en, lines)
        checker = None
        if not failures:
            failures, checker = meaning_check(en, lines, renderer)
        if not failures:
            log.info("hinglish: %d lines rendered by %s, meaning checked by %s (attempt %d)",
                     len(en), renderer, checker, attempt)
            return _spoken(en, lines, renderer, checker), ""
        log.warning("hinglish: attempt %d failed its checks: %s", attempt,
                    " | ".join(failures[:5]))
    return None, "two renderings failed their checks: " + "; ".join(failures[:3])
