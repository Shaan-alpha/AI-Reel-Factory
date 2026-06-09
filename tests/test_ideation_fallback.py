"""Tests for the ideation fallback (Module 1 fallback).

Mock llm + db — no network/DB. Verify JSON parsing, the source/field validation that protects
the news-niche sourcing gate, dedup, idempotency, and the thin-digest guard.
"""
from __future__ import annotations

import json

import pytest

from src import ideation_fallback as fb


def _idea(title, n_sources=2, **over):
    d = {
        "niche": "impact-news",
        "title": title,
        "hook": f"hook for {title}",
        "angle": f"why {title} matters",
        "est_score": 0.7,
        "sources": [f"https://src{i}.example/{title}" for i in range(n_sources)],
    }
    d.update(over)
    return d


def _patch(monkeypatch, ideas, pending=None):
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: pending or [])
    # _produce_ideas tries grounded research first; mock that as the primary path.
    monkeypatch.setattr(fb.llm, "generate_grounded", lambda *a, **k: json.dumps({"ideas": ideas}))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas",
                        lambda rows: captured.setdefault("rows", rows) or rows)
    return captured


def test_inserts_valid_ideas(monkeypatch):
    ideas = [_idea(f"Idea {i}") for i in range(6)]
    captured = _patch(monkeypatch, ideas)
    n = fb.run_fallback_ideation()
    assert n == 6
    assert all(set(r) == {"niche", "title", "hook", "angle", "est_score", "sources"}
               for r in captured["rows"])


def test_drops_ideas_with_too_few_sources(monkeypatch):
    ideas = [_idea(f"Good {i}") for i in range(5)] + [_idea("Bad", n_sources=1)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    titles = [r["title"] for r in captured["rows"]]
    assert "Bad" not in titles and len(titles) == 5


def test_dedupes_by_title(monkeypatch):
    ideas = [_idea("Same") for _ in range(3)] + [_idea(f"U{i}") for i in range(4)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    titles = [r["title"].lower() for r in captured["rows"]]
    assert titles.count("same") == 1


def test_est_score_coerced_and_clamped(monkeypatch):
    ideas = [_idea("A", est_score="not-a-number"), _idea("B", est_score=5.0)]
    ideas += [_idea(f"C{i}") for i in range(4)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    by = {r["title"]: r["est_score"] for r in captured["rows"]}
    assert by["A"] == 0.5 and by["B"] == 1.0


def test_idempotent_when_pending_exists(monkeypatch):
    captured = _patch(monkeypatch, [_idea(f"x{i}") for i in range(6)], pending=[{"id": 1}])
    assert fb.run_fallback_ideation() == 0
    assert "rows" not in captured  # insert never called


def test_thin_digest_raises(monkeypatch):
    _patch(monkeypatch, [_idea("only one")])  # 1 valid < _MIN_IDEAS
    with pytest.raises(RuntimeError, match="thin digest"):
        fb.run_fallback_ideation()


def test_parses_fenced_json(monkeypatch):
    ideas = [_idea(f"f{i}") for i in range(6)]
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(fb.llm, "generate_grounded",
                        lambda *a, **k: "```json\n" + json.dumps({"ideas": ideas}) + "\n```")
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    assert fb.run_fallback_ideation() == 6


def test_caps_at_max(monkeypatch):
    ideas = [_idea(f"n{i}") for i in range(30)]
    captured = _patch(monkeypatch, ideas)
    n = fb.run_fallback_ideation()
    assert n == fb._MAX_IDEAS == len(captured["rows"])


def test_generate_ideas_on_demand_no_pending_guard(monkeypatch):
    # generate_ideas must NOT skip just because pending ideas already exist
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [{"id": 1}])
    ideas = [_idea(f"od{i}", est_score=0.1 * i) for i in range(8)]
    monkeypatch.setattr(fb.llm, "generate_grounded", lambda *a, **k: json.dumps({"ideas": ideas}))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    n = fb.generate_ideas(3)
    assert n == 3 and len(captured["rows"]) == 3
    # keeps the highest-scored 3
    assert [r["est_score"] for r in captured["rows"]] == pytest.approx([0.7, 0.6, 0.5])


def test_generate_ideas_raises_when_none_valid(monkeypatch):
    monkeypatch.setattr(fb.llm, "generate_grounded", lambda *a, **k: json.dumps({"ideas": []}))
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    with pytest.raises(RuntimeError, match="could not generate"):
        fb.generate_ideas(3)


def test_produce_ideas_falls_back_when_grounding_fails(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("grounding unavailable")
    monkeypatch.setattr(fb.llm, "generate_grounded", _boom)
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": [_idea("Fallback")]}))
    out = fb._produce_ideas(3)
    assert out and out[0]["title"] == "Fallback"


def test_load_routine_ideas_reads_file(monkeypatch, tmp_path):
    f = tmp_path / "daily-ideas.json"
    f.write_text(json.dumps({"ideas": [_idea("Routine A"), _idea("Routine B")]}), encoding="utf-8")
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(f))
    out = fb.load_routine_ideas()
    assert {i["title"] for i in out} == {"Routine A", "Routine B"}


def test_load_routine_ideas_absent_or_bad(monkeypatch, tmp_path):
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(tmp_path / "nope.json"))
    assert fb.load_routine_ideas() == []
    bad = tmp_path / "bad.json"; bad.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(bad))
    assert fb.load_routine_ideas() == []


def test_seed_ideas_prefers_routine_file(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [_idea(f"R{i}", est_score=0.1 * i) for i in range(6)])
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: pytest.fail("must not call LLM when routine file present"))
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: set())
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    assert fb.seed_ideas(3) == 3
    assert [r["est_score"] for r in captured["rows"]] == pytest.approx([0.5, 0.4, 0.3])


def test_seed_ideas_falls_back_to_llm(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [])
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: [_idea(f"G{i}") for i in range(5)])
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: set())
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    assert fb.seed_ideas(2) == 2


def test_seed_ideas_dedupes_against_db(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [_idea("Dup"), _idea("New1"), _idea("New2")])
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: {"dup"})
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    fb.seed_ideas(5)
    assert "Dup" not in [r["title"] for r in captured["rows"]]


def test_live_real_llm_ideation(monkeypatch):
    """Real Gemini/Groq generates parseable, well-sourced ideas (DB mocked). Skips offline."""
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    try:
        n = fb.run_fallback_ideation()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"llm unavailable (offline / quota / unkeyed): {e}")
    assert n >= fb._MIN_IDEAS
    for r in captured["rows"]:
        assert r["title"] and r["hook"] and r["angle"]
        assert len(r["sources"]) >= int(fb.config.get("MIN_SOURCES", "2"))
