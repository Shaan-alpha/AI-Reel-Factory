"""Hinglish narration (design 7): the two-text lines, their checks, and the spoken numbers.

The pairs are test 4's (research_notes/Spikes 2026-11-10/code/spike4.py), which the operator
approved by ear, with the digits restored in the Hindi (design 7.2: numbers stay digits; code
turns them into words) and the two Hindi number words written as the English had them.
"""
from __future__ import annotations

import pytest

from src import hinglish

EN = [
    "On November 18, Voyager 1 becomes the first human-made object one full light-day from Earth.",
    "That's 25.9 billion kilometres.",
    "Send it a message, and the reply takes two days.",
    "It runs on decaying plutonium, losing about four watts a year.",
    "Here's why it matters:",
    "The only machines in interstellar space launched in 1977, and they're still talking to us.",
]
HI = [
    "18 November को Voyager 1, Earth से पूरे एक light-day दूर पहुँचने वाली, इंसान की बनाई पहली "
    "चीज़ बन जाएगा।",
    "यानी 25.9 billion kilometres।",
    "इसे message भेजो, तो reply आने में two दिन लगते हैं।",
    "ये decaying plutonium पर चलता है, और हर साल करीब four watts खो रहा है।",
    "और ये matter क्यों करता है?",
    "Interstellar space तक पहुँची इकलौती machines 1977 में launch हुई थीं, और आज भी हमसे बात कर "
    "रही हैं।",
]


def _lines(hi=None):
    return [{"i": i, "hi": h, "parts": []} for i, h in enumerate(hi or HI, 1)]


def _with(n, text):
    hi = list(HI)
    hi[n - 1] = text
    return _lines(hi)


# --- the English side ------------------------------------------------------------------------

def test_english_lines_are_the_sentences_without_tags():
    body = "ISRO's rocket landed in the U.S. today. [serious] Here's why it matters: costs fall."
    assert hinglish.english_lines(body) == ["ISRO's rocket landed in the U.S. today.",
                                            "Here's why it matters: costs fall."]


# --- the checks (design 7.3) -----------------------------------------------------------------

def test_test_4s_lines_pass():
    assert hinglish.check(EN, _lines()) == []


def test_a_missing_or_repeated_line_fails():
    assert hinglish.check(EN, _lines()[:5])
    repeated = _lines()
    repeated[1]["i"] = 1
    assert hinglish.check(EN, repeated)
    extra = _lines()
    extra[5]["i"] = 7
    assert hinglish.check(EN, extra)


def test_hindi_number_words_and_changed_digits_fail():
    assert any("दो" in f for f in hinglish.check(EN, _with(3, HI[2].replace("two", "दो"))))
    assert hinglish.check(EN, _with(2, HI[1].replace("25.9", "26.9")))
    assert hinglish.check(EN, _with(4, HI[3] + " 3 बार।"))
    # एक is also the article "a": it is not counted as a number word.
    assert hinglish.check(EN, _lines()) == []


def test_a_name_must_stay_in_latin():
    failures = hinglish.check(EN, _with(1, HI[0].replace("Voyager", "वॉयेजर")))
    assert any("Voyager" in f for f in failures)


def test_a_capital_after_a_colon_is_not_a_name():
    en = ["Here's why it matters: Prices will rise for Indian buyers this month."]
    hi = ["ये क्यों matter करता है: Indian buyers के लिए इसी महीने prices बढ़ेंगी।"]
    failures = hinglish.check(en, [{"i": 1, "hi": hi[0], "parts": []}], min_seconds=0)
    assert not any("Prices" in f for f in failures)


def test_scripts_are_checked():
    assert hinglish.check(EN, _with(2, "That is 25.9 billion kilometres."))  # no Devanagari
    assert hinglish.check(EN, _with(2, "यानी 25.9 billion kilometres। Ж"))
    assert hinglish.check(EN, _with(2, "यानी 25.9 billion kilometres। 🚀"))
    joined = _with(2, "यानी 25.9 billion kilo‍metres‌।")
    assert not any("character" in f for f in hinglish.check(EN, joined))


def test_the_spoken_length_must_fit(monkeypatch):
    for k in ("HINGLISH_MIN_SECONDS", "HINGLISH_MAX_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    short = [{"i": 1, "hi": "यह " * 40 + "।", "parts": []}]
    assert any("seconds" in f for f in hinglish.check(["A short line."], short))
    assert hinglish.spoken_seconds(" ".join(["word"] * 29)) == pytest.approx(10.0)
    assert hinglish.check(EN, _lines()) == []


# --- spoken numbers (design 7.3) -------------------------------------------------------------

@pytest.mark.parametrize("text, said", [
    ("1977 में", "nineteen seventy-seven में"),
    ("2005 में", "two thousand five में"),
    ("2026 में", "twenty twenty-six में"),
    ("1905 में", "nineteen oh five में"),
    ("25.9 billion kilometres", "twenty-five point nine billion kilometres"),
    ("40% लोग", "forty percent लोग"),
    ("₹500 का", "five hundred rupees का"),
    ("$2 billion", "two billion dollars"),
    ("₹5 crore", "five crore rupees"),
    ("18th November", "eighteenth November"),
    ("1,250 jobs", "one thousand two hundred fifty jobs"),
    ("1,25,000 students", "one lakh twenty-five thousand students"),
    ("1500 crore", "one thousand five hundred crore"),
    ("2000 crore", "two thousand crore"),
    ("Voyager 1 से", "Voyager one से"),
    ("COVID-19 के बाद", "COVID-nineteen के बाद"),
    ("3.14", "three point one four"),
    # After a Hindi vowel sign the space before a number used to be swallowed.
    ("यानी 25.9 billion", "यानी twenty-five point nine billion"),
    ("हर साल ₹ 500 का", "हर साल five hundred rupees का"),
])
def test_say_numbers(text, said):
    assert hinglish.say_numbers(text) == said


def test_say_numbers_leaves_words_alone():
    assert hinglish.say_numbers("G20 और ISRO") == "G20 और ISRO"


# --- rendering (design 7.2) ------------------------------------------------------------------

import json  # noqa: E402

from src import llm  # noqa: E402

_REPLY = json.dumps({"lines": [{"i": i, "hi": h, "parts": [{"hi": h, "en": e}]}
                               for i, (h, e) in enumerate(zip(HI, EN), 1)]})


def test_claude_renders_with_the_schema_and_purpose(monkeypatch):
    seen = {}

    def _claude(prompt, **k):
        seen.update(k, prompt=prompt)
        return _REPLY

    monkeypatch.setattr(hinglish.llm, "generate_claude", _claude)
    lines, renderer = hinglish.render(EN, "Voyager 1 nears a light-day", "plain")
    assert renderer == "claude" and len(lines) == 6 and lines[1]["hi"] == HI[1]
    assert seen["purpose"] == "hinglish" and seen["fallbacks"] is True
    item = seen["schema"]["properties"]["lines"]["items"]
    assert set(item["required"]) == {"i", "hi", "parts"} and "en" not in item["properties"]
    prompt = seen["prompt"]
    assert "1. " + EN[0] in prompt and "6. " + EN[5] in prompt
    assert "Voyager 1 nears a light-day" in prompt and "plain" in prompt
    for rule in ("Devanagari", "Latin script", "digits", "Hindi number word", "12 words", "।",
                 "parts"):
        assert rule in prompt, rule


def test_gemini_then_groq_render_when_claude_cannot(monkeypatch):
    order = []

    def _claude(prompt, **k):
        order.append("claude")
        raise llm.ClaudeUnavailable("no key", "no-key")

    def _with(provider, prompt, **k):
        order.append(provider)
        if provider == "gemini":
            raise RuntimeError("gemini down")
        return _REPLY

    monkeypatch.setattr(hinglish.llm, "generate_claude", _claude)
    monkeypatch.setattr(hinglish.llm, "generate_with", _with)
    lines, renderer = hinglish.render(EN, "t", "plain")
    assert order == ["claude", "gemini", "groq"] and renderer == "groq" and len(lines) == 6


def test_no_renderer_raises(monkeypatch):
    monkeypatch.setattr(hinglish.llm, "generate_claude",
                        lambda p, **k: (_ for _ in ()).throw(RuntimeError("refusal")))
    monkeypatch.setattr(hinglish.llm, "generate_with", lambda provider, p, **k: "not json")
    with pytest.raises(RuntimeError, match="no renderer"):
        hinglish.render(EN, "t", "plain")


def test_a_retry_carries_the_failures(monkeypatch):
    seen = {}
    monkeypatch.setattr(hinglish.llm, "generate_claude",
                        lambda prompt, **k: seen.update(prompt=prompt) or _REPLY)
    hinglish.render(EN, "t", "plain", failures=["line 2: the number 25.9 is missing"])
    assert "line 2: the number 25.9 is missing" in seen["prompt"]


# --- the meaning check (design 7.4) ----------------------------------------------------------

def _verdicts(*different):
    return json.dumps({"lines": [{"i": i, "same": i not in different,
                                  "why": "it adds 'almost'" if i in different else ""}
                                 for i in range(1, 7)]})


def test_the_checker_is_never_the_renderer(monkeypatch):
    used = []
    monkeypatch.setattr(hinglish.llm, "generate_with",
                        lambda provider, p, **k: used.append(provider) or _verdicts())
    for renderer, checker in (("claude", "gemini"), ("gemini", "groq"), ("groq", "gemini")):
        failures, who = hinglish.meaning_check(EN, _lines(), renderer)
        assert failures == [] and who == checker
    assert used == ["gemini", "groq", "gemini"]


def test_a_line_judged_different_fails(monkeypatch):
    monkeypatch.setattr(hinglish.llm, "generate_with", lambda provider, p, **k: _verdicts(2))
    failures, _ = hinglish.meaning_check(EN, _lines(), "claude")
    assert len(failures) == 1 and "line 2" in failures[0] and "almost" in failures[0]


def test_a_line_without_a_verdict_fails(monkeypatch):
    partial = json.dumps({"lines": [{"i": i, "same": True, "why": ""} for i in range(1, 6)]})
    monkeypatch.setattr(hinglish.llm, "generate_with", lambda provider, p, **k: partial)
    failures, _ = hinglish.meaning_check(EN, _lines(), "claude")
    assert any("line 6" in f for f in failures)


def test_a_checker_that_cannot_run_fails_when_strict(monkeypatch):
    def _down(provider, p, **k):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(hinglish.llm, "generate_with", _down)
    monkeypatch.delenv("HINGLISH_STRICT", raising=False)
    failures, _ = hinglish.meaning_check(EN, _lines(), "claude")
    assert failures and "could not run" in failures[0]
    monkeypatch.setenv("HINGLISH_STRICT", "false")
    assert hinglish.meaning_check(EN, _lines(), "claude")[0] == []


def test_every_verdict_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(hinglish.llm, "generate_with", lambda provider, p, **k: _verdicts(2))
    with caplog.at_level("INFO"):
        hinglish.meaning_check(EN, _lines(), "claude")
    for i in range(1, 7):
        assert f"line {i}" in caplog.text


# --- script to spoken lines (design 7.3-7.4) -------------------------------------------------

BODY = " ".join(EN[:4] + ["[serious] And here's why it matters."] + EN[5:])


def _renders(monkeypatch, *results):
    """render() answers from `results` in turn; each is a list of lines or an exception."""
    calls = []

    def _render(en, title, tone, failures=None):
        calls.append(failures)
        step = results[min(len(calls), len(results)) - 1]
        if isinstance(step, Exception):
            raise step
        return step, "claude"

    monkeypatch.setattr(hinglish, "render", _render)
    return calls


def test_to_hinglish_passes_and_speaks_numbers(monkeypatch):
    _renders(monkeypatch, _lines())
    monkeypatch.setattr(hinglish, "meaning_check", lambda en, lines, r: ([], "gemini"))
    spoken, reason = hinglish.to_hinglish(BODY, "Voyager", "plain")
    assert reason == "" and spoken["language"] == "hi"
    assert spoken["renderer"] == "claude" and spoken["checker"] == "gemini"
    assert [line["en"] for line in spoken["lines"]] == hinglish.english_lines(BODY)
    assert "eighteen November" in spoken["said"]
    assert "twenty-five point nine billion" in spoken["said"]
    assert "nineteen seventy-seven" in spoken["said"]
    assert spoken["lines"][1]["said"] == "यानी twenty-five point nine billion kilometres।"


def test_one_failed_check_is_retried_with_its_failures(monkeypatch):
    calls = _renders(monkeypatch, _lines()[:5], _lines())
    monkeypatch.setattr(hinglish, "meaning_check", lambda en, lines, r: ([], "gemini"))
    spoken, _ = hinglish.to_hinglish(BODY, "t", "plain")
    assert spoken and calls[0] is None and calls[1] and "missing" in calls[1][0]


def test_two_failed_checks_end_hinglish(monkeypatch):
    _renders(monkeypatch, _lines()[:5], _lines()[:5])
    spoken, reason = hinglish.to_hinglish(BODY, "t", "plain")
    assert spoken is None and "missing" in reason


def test_a_failed_meaning_check_is_retried_once(monkeypatch):
    calls = _renders(monkeypatch, _lines(), _lines())
    verdicts = iter([(["line 2: the meaning differs from the English"], "gemini"),
                     ([], "gemini")])
    monkeypatch.setattr(hinglish, "meaning_check", lambda en, lines, r: next(verdicts))
    spoken, _ = hinglish.to_hinglish(BODY, "t", "plain")
    assert spoken and "line 2" in calls[1][0]


def test_no_renderer_ends_hinglish(monkeypatch):
    _renders(monkeypatch, RuntimeError("hinglish: no renderer answered"))
    spoken, reason = hinglish.to_hinglish(BODY, "t", "plain")
    assert spoken is None and "no renderer" in reason
