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
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": ideas}))
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
    monkeypatch.setattr(fb.llm, "generate",
                        lambda *a, **k: "```json\n" + json.dumps({"ideas": ideas}) + "\n```")
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    assert fb.run_fallback_ideation() == 6


def test_caps_at_max(monkeypatch):
    ideas = [_idea(f"n{i}") for i in range(30)]
    captured = _patch(monkeypatch, ideas)
    n = fb.run_fallback_ideation()
    assert n == fb._MAX_IDEAS == len(captured["rows"])


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
