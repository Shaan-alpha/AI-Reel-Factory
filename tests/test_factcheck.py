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
    """Measured 2026-07-27: every model except gemini-2.5-flash returns `limit: 0` (no free
    allowance) on this account. A non-None default would make the gate fail every single time —
    permanently fail-open, which is worse than having no gate."""
    monkeypatch.delenv("FACTCHECK_MODEL", raising=False)
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
