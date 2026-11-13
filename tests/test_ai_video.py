"""AI-video shots (design Part A). Stage 3a: the ledger sweep and the run's spend line (6.7, 6.8).

Nothing here reaches Higgsfield or the database: both are replaced per test."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src import ai_video, db, higgsfield

ZERO = {"settled": 0, "left": 0, "errors": 0}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "abc123:def456")


def _ledger(monkeypatch, rows) -> list:
    updates = []
    monkeypatch.setattr(db, "open_ai_video_jobs", lambda days=7: rows)
    monkeypatch.setattr(db, "update_ai_video_job",
                        lambda row_id, **fields: updates.append((row_id, fields)))
    return updates


def _answers(monkeypatch, answers: dict) -> list:
    asked = []

    def status(request_id):
        asked.append(request_id)
        answer = answers[request_id]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(higgsfield, "status", status)
    return asked


def test_the_sweep_settles_what_it_can(monkeypatch):
    rows = [{"id": i, "request_id": f"job-000{i}", "status": s, "cost_usd": 0.179}
            for i, s in enumerate(["submitted", "late", "submitted", "late", "submitted",
                                   "submitted"], start=1)]
    _answers(monkeypatch, {
        "job-0001": {"status": "completed", "video": {"url": "https://cdn.example/v1.mp4"}},
        "job-0002": {"status": "failed", "error": "Generation failed"},
        "job-0003": {"status": "nsfw"},
        "job-0004": {"status": "canceled"},
        "job-0005": {"status": "in_progress"},
        "job-0006": higgsfield.HiggsfieldError("unavailable", "read timed out"),
    })
    updates = _ledger(monkeypatch, rows)

    assert ai_video.sweep() == {"settled": 4, "left": 1, "errors": 1}
    settled = dict(updates)
    # Completed was paid for: it keeps its quote and gains the URL a later reel may reuse.
    assert settled[1]["status"] == "completed"
    assert settled[1]["result_url"] == "https://cdn.example/v1.mp4"
    assert "cost_usd" not in settled[1]
    for row_id, status in ((2, "failed"), (3, "nsfw"), (4, "canceled")):
        assert (settled[row_id]["status"], settled[row_id]["cost_usd"]) == (status, 0)
    for fields in settled.values():
        assert datetime.fromisoformat(fields["settled_at"]).tzinfo is not None
    assert 5 not in settled and 6 not in settled  # still running, or unreadable: next sweep


def test_a_reserved_row_is_not_read(monkeypatch):
    """Its submit never answered, so there is no request to read; it stays at its quote."""
    asked = _answers(monkeypatch, {})
    updates = _ledger(monkeypatch, [{"id": 9, "request_id": None, "status": "reserved",
                                     "cost_usd": 0.179}])
    assert ai_video.sweep() == {"settled": 0, "left": 1, "errors": 0}
    assert asked == [] and updates == []


def test_a_refused_key_stops_the_sweep(monkeypatch):
    rows = [{"id": i, "request_id": f"job-000{i}", "status": "submitted"} for i in (1, 2, 3)]
    asked = _answers(monkeypatch, {r["request_id"]: higgsfield.HiggsfieldError("auth", "401")
                                   for r in rows})
    _ledger(monkeypatch, rows)
    assert ai_video.sweep() == {"settled": 0, "left": 2, "errors": 1}
    assert asked == ["job-0001"]


def test_no_key_or_no_table_means_no_sweep(monkeypatch):
    read = []
    monkeypatch.setattr(db, "open_ai_video_jobs", lambda days=7: read.append(days) or [])
    monkeypatch.delenv("HF_API_KEY")
    assert ai_video.sweep() == ZERO
    assert read == []

    def missing(days=7):
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setenv("HF_API_KEY", "abc123:def456")
    monkeypatch.setattr(db, "open_ai_video_jobs", missing)
    assert ai_video.sweep() == ZERO

    def broken(days=7):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "open_ai_video_jobs", broken)
    assert ai_video.sweep() == ZERO


def test_spend_line(monkeypatch):
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    rows = ([{"status": "completed", "cost_usd": 0.179}] * 4
            + [{"status": "late", "cost_usd": "0.1790"}, {"status": "reserved", "cost_usd": 0.179},
               {"status": "failed", "cost_usd": 0}, {"status": "refused", "cost_usd": 0}])
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: rows if s == since else [])
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 14.3)
    assert ai_video.spend_line(since) == (
        "🎞️ AI video this run: 6 clips, $1.07 (2 paid, not used); $14.30 this month.")

    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: [{"status": "completed",
                                                               "cost_usd": 0.179}])
    assert ai_video.spend_line(since) == "🎞️ AI video this run: 1 clip, $0.18; $14.30 this month."


def test_no_spend_line_without_purchases_a_key_or_a_ledger(monkeypatch):
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 14.3)
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: [])
    assert ai_video.spend_line(since) is None

    def missing(s):
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setattr(db, "ai_video_jobs_since", missing)
    assert ai_video.spend_line(since) is None

    read = []
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: read.append(s) or [])
    monkeypatch.delenv("HF_API_KEY")
    assert ai_video.spend_line(since) is None
    assert read == []  # an English run without the key never reads the ledger
