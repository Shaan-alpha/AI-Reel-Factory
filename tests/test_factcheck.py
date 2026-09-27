"""Tests for src/factcheck.py — the independent post-write verification gate.

The grounded LLM call is mocked throughout, so these need no key and no network. What they pin
is the GATE's behaviour, which is where the risk lives: a FABRICATED claim must block, a merely
imprecise one must not, and a broken checker must not block either.

The severity split (2026-08-07) is the load-bearing part — before it, every discrepancy blocked
and most ideas died over differences that changed nothing.
"""
from __future__ import annotations

import pytest

from src import factcheck


def _mock_grounded(monkeypatch, payload: str):
    monkeypatch.setattr(factcheck.llm, "generate_grounded", lambda *a, **k: payload)


def test_clean_script_passes(monkeypatch):
    _mock_grounded(monkeypatch, '{"checked": 4, "unsupported": [], "verdict": "pass"}')
    r = factcheck.verify("India cut tariffs on solar panels.", ["https://pib.gov.in/x"])
    assert r["ok"] is True
    assert r["checked"] == 4


def test_unsupported_claim_blocks_the_reel(monkeypatch):
    _mock_grounded(monkeypatch, '{"checked": 3, "blocking": ["the 40% figure is invented"],'
                                ' "minor": [], "verdict": "fail"}')
    r = factcheck.verify("Prices fell 40 percent.", ["https://example.com"])
    assert r["ok"] is False
    assert "40%" in r["unsupported"][0] or "40" in r["unsupported"][0]


def test_claim_list_overrides_a_contradictory_pass_verdict(monkeypatch):
    """A model that lists a BLOCKING problem then says 'pass' is what this gate exists to catch."""
    _mock_grounded(monkeypatch, '{"checked": 2, "blocking": ["the ruling never happened"],'
                                ' "minor": [], "verdict": "pass"}')
    assert factcheck.verify("The court struck it down in March.", [])["ok"] is False


# --- severity grading (2026-08-07): imprecision must not kill a true story ------------------

def test_minor_findings_are_waived_not_blocked(monkeypatch):
    """The operator's complaint: reels died over 'very minute differences'. They now ship."""
    _mock_grounded(monkeypatch, '{"checked": 6, "blocking": [],'
                                ' "minor": ["script says 12,000; the filing says 12,400"],'
                                ' "verdict": "pass"}')
    r = factcheck.verify("About 12,000 homes lost power.", ["https://example.com"])
    assert r["ok"] is True
    assert r["unsupported"] == []
    assert len(r["minor"]) == 1


def test_a_fail_verdict_over_only_minor_findings_still_ships(monkeypatch):
    """Grading outranks the verdict WORD in both directions — this is the over-blocking case.

    A checker that finds nothing but rounding and then reflexively stamps 'fail' is exactly the
    behaviour that was killing most ideas.
    """
    _mock_grounded(monkeypatch, '{"checked": 4, "blocking": [],'
                                ' "minor": ["figure rounded", "date off by one day"],'
                                ' "verdict": "fail"}')
    r = factcheck.verify("Roughly 5 lakh people voted on Tuesday.", [])
    assert r["ok"] is True, "rounding and a one-day date slip must not kill a true story"
    assert len(r["minor"]) == 2


def test_one_blocking_finding_beats_any_number_of_minor_ones(monkeypatch):
    _mock_grounded(monkeypatch, '{"checked": 9, "blocking": ["the CEO never said this"],'
                                ' "minor": ["a", "b", "c"], "verdict": "pass"}')
    r = factcheck.verify("The CEO said the plant would close.", [])
    assert r["ok"] is False
    assert r["unsupported"] == ["the CEO never said this"]


def test_ungraded_legacy_shape_is_treated_as_blocking(monkeypatch):
    """If the checker ignores the two-bucket schema it has graded nothing.

    Degrade toward the strict behaviour: an ungraded finding blocks. Waving it through would
    fail-open on a real fabrication, which is the one outcome this gate cannot have.
    """
    _mock_grounded(monkeypatch, '{"checked": 3, "unsupported": ["the launch was invented"],'
                                ' "verdict": "fail"}')
    r = factcheck.verify("They launched it yesterday.", [])
    assert r["ok"] is False
    assert r["unsupported"] == ["the launch was invented"]


def test_severity_any_restores_block_on_everything(monkeypatch):
    """Escape hatch: if grading ever waves through something it shouldn't, this is the undo."""
    monkeypatch.setenv("FACTCHECK_SEVERITY", "any")
    _mock_grounded(monkeypatch, '{"checked": 3, "blocking": [], "minor": ["rounded a figure"],'
                                ' "verdict": "pass"}')
    r = factcheck.verify("About 12,000 homes.", [])
    assert r["ok"] is False
    assert r["unsupported"] == ["rounded a figure"]
    assert r["minor"] == []


def test_critical_only_is_the_default(monkeypatch):
    monkeypatch.delenv("FACTCHECK_SEVERITY", raising=False)
    assert factcheck.severity_gate() == "critical"


def test_findings_tolerate_objects_and_bare_strings(monkeypatch):
    """A checker that phrases its answer slightly differently must not crash the gate (rule 14) —
    an exception here takes the fail-open path, i.e. no gate at all."""
    _mock_grounded(monkeypatch, '{"checked": 2, "blocking": {"claim": "no such law",'
                                ' "why": "no bill exists"}, "minor": "a rounding nit",'
                                ' "verdict": "fail"}')
    r = factcheck.verify("Parliament passed it.", [])
    assert r["ok"] is False
    assert "no such law" in r["unsupported"][0] and "no bill exists" in r["unsupported"][0]
    assert r["minor"] == ["a rounding nit"]


def test_duplicate_findings_are_collapsed(monkeypatch):
    _mock_grounded(monkeypatch, '{"checked": 2, "blocking": ["same thing", "same thing"],'
                                ' "minor": ["same thing"], "verdict": "fail"}')
    r = factcheck.verify("Body.", [])
    assert r["unsupported"] == ["same thing"]
    assert r["minor"] == [], "a finding already blocking must not also be listed as waived"


def test_fail_verdict_naming_nothing_still_blocks(monkeypatch):
    """Nothing to grade and the checker plainly saw something — the one case the word wins."""
    _mock_grounded(monkeypatch, '{"checked": 2, "blocking": [], "minor": [], "verdict": "fail"}')
    assert factcheck.verify("Something.", [])["ok"] is False


def test_checker_outage_lets_the_reel_through(monkeypatch):
    """A grounding outage must not halt the day's batch (rule 14) — the scriptwriter's own
    grounding is still underneath. Only a real verdict may block."""
    def _boom(*_a, **_k):
        raise RuntimeError("429 quota exhausted")

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _boom)
    r = factcheck.verify("Anything at all.", [])
    assert r["ok"] is True
    assert "checker-failed" in r["reason"]


def test_unparseable_response_lets_the_reel_through(monkeypatch):
    _mock_grounded(monkeypatch, "I am afraid I cannot help with that.")
    r = factcheck.verify("Anything.", [])
    assert r["ok"] is True
    assert "checker-failed" in r["reason"]


def test_empty_script_is_blocked_not_excused(monkeypatch):
    r = factcheck.verify("   ", ["https://example.com"])
    assert r["ok"] is False
    assert r["reason"] == "empty"


def test_disabled_skips_the_call_entirely(monkeypatch):
    monkeypatch.setenv("ENABLE_FACT_CHECK", "false")
    called = []
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda *a, **k: called.append(1) or "{}")
    r = factcheck.verify("Anything.", [])
    assert r["ok"] is True and r["reason"] == "disabled"
    assert called == [], "must not spend a grounded call when disabled"


def test_enabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_FACT_CHECK", raising=False)
    assert factcheck.enabled() is True


def test_prompt_sends_the_sources_and_asks_for_graded_findings(monkeypatch):
    seen = {}

    def _capture(prompt, **_k):
        seen["prompt"] = prompt
        return '{"checked": 1, "blocking": [], "minor": [], "verdict": "pass"}'

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _capture)
    factcheck.verify("Body text.", ["https://a.example", "https://b.example"], title="A Title")
    p = seen["prompt"]
    assert "https://a.example" in p and "https://b.example" in p
    assert "A Title" in p and "Body text." in p
    assert "BLOCKING" in p and "MINOR" in p          # the two buckets it must sort into
    assert "NON-CONFIRMATION does not" in p          # not-found is minor, not fatal
    assert "disagreeing does not make the script wrong" in p   # the operator's own reasoning
    assert "tone" in p.lower()                       # tone/opinion explicitly out of scope


def test_tolerates_json_in_markdown_fences(monkeypatch):
    _mock_grounded(monkeypatch,
                   'Here is my analysis:\n```json\n{"checked": 2, "unsupported": [],'
                   ' "verdict": "pass"}\n```\nHope that helps.')
    assert factcheck.verify("Body.", [])["ok"] is True


# --- a reply the parser could not read (2026-09-12, idea 291) -------------------------------
# The checker ran and — as re-running it on the real script showed, 6 times out of 6 — found the
# story false. But it quoted the script with raw double quotes, json.loads died with "Expecting
# ',' delimiter", and that parse error took the OUTAGE path: the reel shipped unverified.

_RAW_QUOTES = ('{"checked": 6, "blocking": ["The script says Modi and Xi "just held their first '
               'bilateral talks in five years" at BRICS. False: they met in Kazan in October 2024 '
               'and in Tianjin in August 2025."], "minor": ["calls relations "icy", which is '
               'editorial"], "verdict": "fail"}')


def test_the_live_failure_shape_really_is_unparseable_as_plain_json():
    import json
    with pytest.raises(json.JSONDecodeError, match="Expecting ',' delimiter"):
        json.loads(_RAW_QUOTES, strict=False)


def test_raw_quotes_inside_a_finding_still_reach_a_verdict(monkeypatch):
    _mock_grounded(monkeypatch, _RAW_QUOTES)
    r = factcheck.verify("PM Modi and Xi just held their first bilateral talks in five years.", [])
    assert factcheck.gate_ran(r), f"the gate must not fail open on a readable verdict: {r}"
    assert r["ok"] is False
    assert "first bilateral talks in five years" in r["unsupported"][0]
    assert r["minor"] == ["calls relations \"icy\", which is editorial"]


def test_quote_repair_leaves_valid_json_untouched():
    valid = ('{"checked": 2, "blocking": [], "minor": ["says \\"12,000\\", filing says 12,400",'
             ' "a, b"], "verdict": "pass"}')
    assert factcheck._escape_stray_quotes(valid) == valid


def test_an_unreadable_reply_is_asked_again_once(monkeypatch):
    monkeypatch.setenv("FACTCHECK_SAMPLES", "1")  # counts calls for ONE sample
    replies = iter(["Let me check that... the claim is false.",
                    '{"checked": 1, "blocking": ["invented"], "minor": [], "verdict": "fail"}'])
    calls = []
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda *a, **k: calls.append(1) or next(replies))
    r = factcheck.verify("Body.", [])
    assert len(calls) == 2
    assert factcheck.gate_ran(r) and r["ok"] is False


def test_two_unreadable_replies_fail_open_and_log_what_the_checker_said(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda *a, **k: calls.append(1) or "no json here, sorry")
    with caplog.at_level("WARNING"):
        r = factcheck.verify("Body.", [])
    assert len(calls) == 2, "exactly one re-ask — never a loop"
    assert r["ok"] is True and not factcheck.gate_ran(r)
    assert any("no json here, sorry" in rec.getMessage() for rec in caplog.records), \
        "the unreadable reply must be in the log, or the next failure is undiagnosable too"


def test_prompt_asks_for_single_quotes_inside_findings(monkeypatch):
    seen = {}
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda p, **k: seen.setdefault("p", p) and _PASS_REPLY)
    factcheck.verify("Body.", [])
    assert "SINGLE quotes" in seen["p"]


_PASS_REPLY = '{"checked": 1, "blocking": [], "minor": [], "verdict": "pass"}'


def test_tolerates_a_junk_checked_count(monkeypatch):
    _mock_grounded(monkeypatch, '{"checked": "several", "unsupported": [], "verdict": "pass"}')
    r = factcheck.verify("Body.", [])
    assert r["ok"] is True and r["checked"] == 0


def test_summary_is_short_and_single_line():
    r = {"unsupported": ["claim one\nspans lines", "claim two", "claim three", "claim four"]}
    s = factcheck.summary(r)
    assert "\n" not in s
    assert "+1 more" in s


def test_summary_of_a_pass():
    assert factcheck.summary({"unsupported": [], "reason": "pass"}) == "pass"


def test_live_factcheck_catches_a_fabrication():
    """Real grounded check against an invented claim. Gated: needs a Gemini key and quota."""
    import os
    if os.environ.get("FACTCHECK_LIVE_TEST") != "1":
        pytest.skip("set FACTCHECK_LIVE_TEST=1 to run (uses grounded Gemini quota)")
    r = factcheck.verify(
        "Anthropic released Claude Fable 5 yesterday, and India immediately banned it nationwide.",
        ["https://www.anthropic.com"])
    assert r["ok"] is False, f"a fabricated claim should not pass: {r}"


def test_strict_mode_blocks_when_the_checker_is_unavailable(monkeypatch):
    """Grounded search shares one free-tier bucket with ideation and the scriptwriter, so the
    gate CAN be unable to run. Strict mode makes that block instead of silently waving reels
    through unverified."""
    monkeypatch.setenv("FACTCHECK_STRICT", "true")
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 quota")))
    r = factcheck.verify("Anything.", [])
    assert r["ok"] is False
    assert "checker unavailable" in r["unsupported"][0]


def test_fail_open_is_the_default(monkeypatch):
    monkeypatch.delenv("FACTCHECK_STRICT", raising=False)
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 quota")))
    assert factcheck.verify("Anything.", [])["ok"] is True


def test_strict_mode_does_not_affect_a_real_verdict(monkeypatch):
    """Strict only governs checker OUTAGES; a clean pass must still pass."""
    monkeypatch.setenv("FACTCHECK_STRICT", "true")
    _mock_grounded(monkeypatch, '{"checked": 3, "unsupported": [], "verdict": "pass"}')
    assert factcheck.verify("Body.", [])["ok"] is True


def test_default_model_is_none_so_the_shared_free_model_is_used(monkeypatch):
    """Measured 2026-07-27: on the Developer API every model except gemini-2.5-flash returns
    `limit: 0` (no free allowance). A non-None default there would make the gate fail every
    single time — permanently fail-open, which is worse than having no gate."""
    monkeypatch.delenv("FACTCHECK_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_USE_VERTEX", raising=False)
    assert factcheck._model() is None

    seen = {}
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda p, **k: seen.update(k) or '{"checked":1,"unsupported":[],"verdict":"pass"}')
    factcheck.verify("Body.", [])
    assert seen["model"] is None, "must fall through to GEMINI_MODEL, the only free grounded model"


def test_model_override_is_honoured(monkeypatch):
    monkeypatch.setenv("FACTCHECK_MODEL", "gemini-2.5-pro")
    seen = {}
    monkeypatch.setattr(factcheck.llm, "generate_grounded",
                        lambda p, **k: seen.update(k) or '{"checked":1,"unsupported":[],"verdict":"pass"}')
    factcheck.verify("Body.", [])
    assert seen["model"] == "gemini-2.5-pro"


def test_a_block_logs_the_raw_checker_reply(monkeypatch, caplog):
    """When a reel dies, the log must show what the checker actually said.

    Today it shows only the flattened strings, so it is impossible after the fact to tell a
    model that mis-sorted a finding from `verify()` harvesting one of the undocumented
    `critical`/`unsupported` keys — the two have different fixes, and three real reels were
    killed with no way to distinguish them.
    """
    raw = '{"checked": 4, "blocking": ["the 40% figure is invented"], "minor": [], "verdict": "fail"}'
    monkeypatch.setattr(factcheck.llm, "generate_grounded", lambda *a, **k: raw)
    with caplog.at_level("WARNING"):
        out = factcheck.verify("body text", ["https://x.example"], "title")
    assert out["ok"] is False
    assert any("the 40% figure is invented" in r.getMessage() and "checked" in r.getMessage()
               for r in caplog.records), "the raw checker JSON must be logged on a block"


# --- the gate's own quota (2026-09-03 audit) ----------------------------------------------
# Ideation + scriptwriter + this gate share ONE 20/day grounded budget on gemini-2.5-flash. A
# 3-reel run costs 7 calls, so a busy day exhausts it — and with FACTCHECK_STRICT=false the gate
# then fails OPEN, publishing unverified reels. A second free key gives the gate its own budget.

def test_verify_spends_the_dedicated_key_when_one_is_set(monkeypatch):
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.setenv("FACTCHECK_API_KEY", "checker-key")
    seen = {}

    def _fake(prompt, *, max_tokens=2048, model=None, api_key=None):
        seen["api_key"] = api_key
        return '{"checked": 2, "blocking": [], "minor": [], "verdict": "pass"}'

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _fake)
    assert factcheck.verify("a body")["ok"] is True
    assert seen["api_key"] == "checker-key"


def test_verify_falls_back_to_the_shared_key_when_none_is_set(monkeypatch):
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.delenv("FACTCHECK_API_KEY", raising=False)
    seen = {}

    def _fake(prompt, *, max_tokens=2048, model=None, api_key=None):
        seen["api_key"] = api_key
        return '{"checked": 1, "blocking": [], "minor": [], "verdict": "pass"}'

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _fake)
    factcheck.verify("a body")
    assert seen["api_key"] is None  # None => llm uses GEMINI_API_KEY


def test_a_failed_checker_is_reported_as_unverified(monkeypatch):
    """produce_one has to be able to TELL the operator the gate did not run — a fail-open that
    looks exactly like a pass is how unverified reels ship silently (audit 2026-09-03)."""
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.setenv("FACTCHECK_STRICT", "false")

    def _boom(*a, **k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _boom)
    out = factcheck.verify("a body")
    assert out["ok"] is True                      # fail-open, as configured
    assert factcheck.gate_ran(out) is False       # ...but visibly so
    assert "checker-failed" in out["reason"]


def test_gate_ran_is_true_for_a_real_verdict(monkeypatch):
    assert factcheck.gate_ran({"reason": "pass"}) is True
    assert factcheck.gate_ran({"reason": "fail"}) is True
    assert factcheck.gate_ran({"reason": "disabled"}) is False


# --- a MISCONFIGURED dedicated key must not disable the gate (2026-09-04) ------------------
# Measured live: a Gemini key from a NEW Google Cloud project cannot do grounded search at all —
# gemini-2.5-flash 404s ("no longer available to new users") and every other model 429s with no
# allowance. Pointing the gate at such a key made it fail on EVERY reel, i.e. permanently
# fail-open — strictly worse than sharing one budget. A wrong key must degrade to today, not to
# no gate.

_PASS = '{"checked": 2, "blocking": [], "minor": [], "verdict": "pass"}'


def test_a_dedicated_key_that_404s_falls_back_to_the_shared_one(monkeypatch):
    monkeypatch.setenv("FACTCHECK_SAMPLES", "1")  # counts calls for ONE sample
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.setenv("FACTCHECK_API_KEY", "key-from-a-project-with-no-grounding")
    tried = []

    def _fake(prompt, *, max_tokens=2048, model=None, api_key=None):
        tried.append(api_key)
        if api_key is not None:
            raise RuntimeError("404 NOT_FOUND. models/gemini-2.5-flash is no longer available")
        return _PASS

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _fake)
    out = factcheck.verify("a body")

    assert out["ok"] is True
    assert factcheck.gate_ran(out) is True, "the gate must actually run, not fail open"
    assert tried == ["key-from-a-project-with-no-grounding", None]


def test_an_exhausted_dedicated_key_does_not_spend_the_shared_budget(monkeypatch):
    """429 means the isolation is WORKING and merely spent. Falling back would re-introduce the
    competition the dedicated key exists to remove."""
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.setenv("FACTCHECK_API_KEY", "checker-key")
    tried = []

    def _fake(prompt, *, max_tokens=2048, model=None, api_key=None):
        tried.append(api_key)
        raise RuntimeError("429 RESOURCE_EXHAUSTED quotaValue: 20")

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _fake)
    out = factcheck.verify("a body")

    assert tried == ["checker-key"], "a spent dedicated key must not fall back"
    assert factcheck.gate_ran(out) is False


def test_no_dedicated_key_means_exactly_one_attempt(monkeypatch):
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.delenv("FACTCHECK_API_KEY", raising=False)
    tried = []

    def _fake(prompt, *, max_tokens=2048, model=None, api_key=None):
        tried.append(api_key)
        raise RuntimeError("404 NOT_FOUND")

    monkeypatch.setattr(factcheck.llm, "generate_grounded", _fake)
    factcheck.verify("a body")
    assert tried == [None]


# --- 2026-09-27 audit ---------------------------------------------------------------------

def _capture_prompt(monkeypatch, replies):
    seen = []
    it = iter(replies)
    monkeypatch.setattr(factcheck, "_ask_checker", lambda p: seen.append(p) or next(it))
    return seen


_PASS = '{"checked": 3, "blocking": [], "minor": [], "verdict": "pass"}'
_FAIL = '{"checked": 3, "blocking": ["cameras were not turned off"], "minor": [], "verdict": "fail"}'


def test_the_checker_is_told_todays_date(monkeypatch):
    """Without a date the model treated this month's news as the future or a past year."""
    seen = _capture_prompt(monkeypatch, [_PASS])
    factcheck.verify("A claim.", ["https://a.example"])
    assert "TODAY'S DATE: 20" in seen[0]


def test_on_screen_text_is_checked_too(monkeypatch):
    seen = _capture_prompt(monkeypatch, [_PASS])
    factcheck.verify("A claim.", [], on_screen=["100% TARIFFS", "Summary line."])
    assert "100% TARIFFS" in seen[0] and "Summary line." in seen[0]


def test_two_samples_are_the_default(monkeypatch):
    """2026-09-27 on gemini-3.5-flash: the Modi-Xi claim was waived on one run and blocked on
    the next. With two samples, where either blocking counts, that pair blocks."""
    monkeypatch.delenv("FACTCHECK_SAMPLES", raising=False)
    seen = _capture_prompt(monkeypatch, [_PASS, _FAIL])
    assert factcheck.verify("A claim.", [])["ok"] is False
    assert len(seen) == 2


def test_a_could_not_confirm_finding_does_not_block():
    assert factcheck._only_unconfirmed("Could not independently confirm the 40% figure.")
    assert not factcheck._only_unconfirmed("Could not confirm; in fact the bill was signed.")
    assert not factcheck._only_unconfirmed("The quote is invented: no such speech exists.")


def test_the_checker_gets_publisher_links_first_and_no_redirects():
    got = factcheck._checker_sources(["https://news.google.com/rss/articles/X",
                                      "https://vertexaisearch.cloud.google.com/grounding-api-redirect/Y",
                                      "https://www.afp.com/en/story"])
    assert got == ["https://www.afp.com/en/story", "https://news.google.com/rss/articles/X"]


def test_a_second_sample_that_finds_a_contradiction_blocks(monkeypatch):
    """Idea 314 was blocked and near-identical 315 shipped: one sample is a coin toss."""
    monkeypatch.setenv("FACTCHECK_SAMPLES", "2")
    _capture_prompt(monkeypatch, [_PASS, _FAIL])
    result = factcheck.verify("A claim.", [])
    assert result["ok"] is False and "cameras" in result["unsupported"][0]


def test_an_extra_sample_that_cannot_run_does_not_undo_the_first(monkeypatch):
    monkeypatch.setenv("FACTCHECK_SAMPLES", "2")
    calls = []

    def _ask(p):
        calls.append(p)
        if len(calls) > 1:
            raise RuntimeError("503 UNAVAILABLE")
        return _PASS

    monkeypatch.setattr(factcheck, "_ask_checker", _ask)
    result = factcheck.verify("A claim.", [])
    assert result["ok"] is True and factcheck.gate_ran(result)


def test_on_vertex_the_gate_runs_on_the_stronger_3_5_flash(monkeypatch):
    """Operator, 2026-09-27: off the retiring model; 3.5 Flash caught the 314 error."""
    monkeypatch.delenv("FACTCHECK_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    assert factcheck._model() == "gemini-3.5-flash,gemini-3.5-flash-lite"
