"""Records for measuring (design sections 10 and 13): the format stamp, the upload read-back, one
row per attempt, and the Analytics metrics. Each write must survive the operator not having run
the new SQL yet: a missing column or table costs the record, never a reel."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from postgrest.exceptions import APIError

from src import db

_NO_COLUMN = {"code": "PGRST204",
              "message": "Could not find the 'format' column of 'posts' in the schema cache"}
_NO_TABLE = {"code": "PGRST205",
             "message": "Could not find the table 'public.reel_attempts' in the schema cache"}


class _Fake:
    """A Supabase stand-in: records every call; `errors` are raised by the next executes."""

    def __init__(self, data=None, errors=None):
        self.calls, self.data, self.errors = [], data or {}, list(errors or [])
        self._table = None

    def table(self, name):
        self._table = name
        return self

    def _record(self, op, *args, **kwargs):
        self.calls.append((op, self._table, args, kwargs))
        return self

    def insert(self, row):
        return self._record("insert", row)

    def update(self, row):
        return self._record("update", row)

    def upsert(self, row, **kwargs):
        return self._record("upsert", row, **kwargs)

    def select(self, *cols):
        return self._record("select", *cols)

    @property
    def not_(self):
        return self

    def __getattr__(self, _name):  # eq, neq, is_, gte, ... are filters: ignore them
        return lambda *a, **k: self

    def execute(self):
        if self.errors:
            raise APIError(self.errors.pop(0))
        return type("R", (), {"data": self.data.get(self._table, [{"id": 11}])})()


def _use(monkeypatch, fake):
    monkeypatch.setattr(db, "get_client", lambda: fake)
    db._WARNED.clear()
    return fake


def test_insert_post_writes_the_format(monkeypatch):
    fake = _use(monkeypatch, _Fake())
    db.insert_post(1, "youtube", "V1", "u", "published", format={"version": 1, "language": "en"})
    assert fake.calls[0][2][0]["format"] == {"version": 1, "language": "en"}


def test_insert_post_retries_without_format_when_the_column_is_missing(monkeypatch):
    fake = _use(monkeypatch, _Fake(errors=[_NO_COLUMN]))
    post_id = db.insert_post(1, "youtube", "V1", "u", "published", format={"version": 1})
    inserts = [c for c in fake.calls if c[0] == "insert"]
    assert len(inserts) == 2 and "format" not in inserts[1][2][0]
    assert post_id == 11


def test_start_attempt_returns_none_when_the_table_is_missing(monkeypatch):
    _use(monkeypatch, _Fake(errors=[_NO_TABLE]))
    assert db.start_attempt(5) is None
    db.finish_attempt(None, outcome="failed", stage="voice")  # a no-op, and no error


def test_finish_attempt_never_raises(monkeypatch):
    def _down():
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr(db, "get_client", _down)
    db.finish_attempt(3, outcome="published", stage="upload", downgrades=["fallback-voice"])


def test_set_post_readback_skips_a_missing_column(monkeypatch):
    _use(monkeypatch, _Fake(errors=[_NO_COLUMN]))
    db.set_post_readback(4, {"containsSyntheticMedia": None})  # logged once, never raised


def test_posts_needing_metrics_skips_posts_already_measured_and_young_posts(monkeypatch):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=12)).isoformat()
    young = (now - timedelta(days=3)).isoformat()
    posts = [{"id": 1, "external_id": "A", "published_at": old},
             {"id": 2, "external_id": "B", "published_at": young},
             {"id": 3, "external_id": "C", "published_at": old}]
    _use(monkeypatch, _Fake(data={"posts": posts, "post_metrics": [{"post_id": 1}]}))
    assert [p["id"] for p in db.posts_needing_metrics(min_age_days=9)] == [3]


def test_posts_needing_metrics_is_empty_when_the_table_is_missing(monkeypatch):
    _use(monkeypatch, _Fake(data={"posts": []}, errors=[_NO_TABLE]))
    assert db.posts_needing_metrics() == []


def test_upsert_post_metrics_uses_post_and_window_as_the_key(monkeypatch):
    fake = _use(monkeypatch, _Fake())
    db.upsert_post_metrics(7, 7, {"views": 100, "india_share": 0.6})
    op, table, args, kwargs = fake.calls[0]
    assert (op, table) == ("upsert", "post_metrics")
    assert args[0]["post_id"] == 7 and args[0]["window_days"] == 7 and args[0]["views"] == 100
    assert kwargs["on_conflict"] == "post_id,window_days"


def test_backfill_post_published_at_only_fills_an_empty_date(monkeypatch):
    fake = _use(monkeypatch, _Fake())
    db.backfill_post_published_at(4, "2026-07-01T10:00:00Z")
    op, table, args, _ = fake.calls[0]
    assert (op, table) == ("update", "posts") and args[0] == {"published_at": "2026-07-01T10:00:00Z"}


def test_ideas_insert_retries_without_the_new_columns(monkeypatch):
    fake = _use(monkeypatch, _Fake(errors=[{"code": "PGRST204",
                                            "message": "Could not find the 'rank_score' column"}]))
    db.insert_ideas([{"title": "T", "niche": "tech", "rank_score": 0.8, "demand": []}])
    inserts = [c for c in fake.calls if c[0] == "insert"]
    assert len(inserts) == 2
    assert "rank_score" not in inserts[1][2][0][0] and "demand" not in inserts[1][2][0][0]


def test_expired_ideas_are_not_recent(monkeypatch):
    filters = []

    class _Q:
        def table(self, _n):
            return self

        def select(self, *_a):
            return self

        def gte(self, *a):
            filters.append(("gte",) + a)
            return self

        def neq(self, *a):
            filters.append(("neq",) + a)
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr(db, "get_client", lambda: _Q())
    db.recent_ideas(10)
    assert ("neq", "status", "expired") in filters


def test_insert_script_stores_the_structure_and_survives_a_missing_column(monkeypatch):
    fake = _use(monkeypatch, _Fake())
    db.insert_script(1, "N", "body", "cap", [], title="T", structure="belief")
    assert fake.calls[0][2][0]["structure"] == "belief"
    fake = _use(monkeypatch, _Fake(errors=[_NO_COLUMN]))
    script_id = db.insert_script(1, "N", "body", "cap", [], title="T", structure="belief")
    inserts = [c for c in fake.calls if c[0] == "insert"]
    assert len(inserts) == 2 and "structure" not in inserts[1][2][0]
    assert inserts[1][2][0]["title"] == "T" and script_id == 11


def test_set_script_spoken_survives_a_missing_column(monkeypatch):
    fake = _use(monkeypatch, _Fake())
    db.set_script_spoken(5, {"language": "hi", "lines": []})
    assert fake.calls[0][0] == "update" and fake.calls[0][2][0] == {
        "spoken": {"language": "hi", "lines": []}}
    _use(monkeypatch, _Fake(errors=[_NO_COLUMN]))
    db.set_script_spoken(5, {"language": "hi", "lines": []})  # logged once, never raised


# --- ai_video_jobs, the Higgsfield ledger (design 6.7 and 13) --------------------------------

_NO_LEDGER = {"code": "PGRST205",
              "message": "Could not find the table 'public.ai_video_jobs' in the schema cache"}


class _Ledger(_Fake):
    """_Fake that records the filters (eq, in_, gte, order) instead of ignoring them."""

    def __init__(self, data=None, errors=None):
        super().__init__(data, errors)
        self.filters = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _filter(*args, **_kwargs):
            self.filters.append((name, args))
            return self

        return _filter


def _gte(fake) -> tuple[str, datetime]:
    (column, value), = [a for n, a in fake.filters if n == "gte"]
    return column, datetime.fromisoformat(value)


def test_reserve_stamps_a_fresh_key_and_status(monkeypatch):
    import uuid

    fake = _use(monkeypatch, _Ledger(data={"ai_video_jobs": [{"id": 7}]}))
    row = db.reserve_ai_video_job(5, 0, "kling-video/v2.5-turbo/standard/image-to-video", 0.17912)
    (op, table, (sent,), _), = fake.calls
    assert (op, table) == ("insert", "ai_video_jobs")
    assert {k: sent[k] for k in ("idea_id", "shot", "status", "cost_usd")} == {
        "idea_id": 5, "shot": 0, "status": "reserved", "cost_usd": 0.1791}
    assert sent["endpoint"] == "kling-video/v2.5-turbo/standard/image-to-video"
    uuid.UUID(sent["idempotency_key"])
    stamped = datetime.fromisoformat(sent["created_at"])
    assert abs(datetime.now(timezone.utc) - stamped) < timedelta(minutes=1)
    assert row["id"] == 7 and row["idempotency_key"] == sent["idempotency_key"]
    assert db.reserve_ai_video_job(5, 1, "e", 0.179)["idempotency_key"] != row["idempotency_key"]


def test_update_writes_the_fields(monkeypatch):
    fake = _use(monkeypatch, _Ledger())
    db.update_ai_video_job(7, status="submitted", request_id="0b6f2a4e")
    (op, table, (sent,), _), = fake.calls
    assert (op, table, sent) == ("update", "ai_video_jobs",
                                 {"status": "submitted", "request_id": "0b6f2a4e"})
    assert ("eq", ("id", 7)) in fake.filters


def test_reads_filter_by_idea_age_and_status(monkeypatch):
    rows = [{"id": 1, "status": "completed", "shot": 0}]
    fake = _use(monkeypatch, _Ledger(data={"ai_video_jobs": rows}))
    now = datetime.now(timezone.utc)

    assert db.ai_video_jobs_for_idea(5) == rows
    assert ("eq", ("idea_id", 5)) in fake.filters
    column, cutoff = _gte(fake)
    assert column == "created_at" and timedelta(days=6, hours=23) < now - cutoff < timedelta(days=7, minutes=1)

    fake.filters.clear()
    assert db.open_ai_video_jobs() == rows
    statuses = [list(a[1]) for n, a in fake.filters if n == "in_" and a[0] == "status"]
    assert statuses == [["submitted", "late"]]
    column, cutoff = _gte(fake)
    assert timedelta(days=6, hours=23) < now - cutoff < timedelta(days=7, minutes=1)

    fake.filters.clear()
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    assert db.ai_video_jobs_since(since) == rows
    assert _gte(fake) == ("created_at", since)


def test_the_months_spend_sums_cost(monkeypatch):
    rows = [{"cost_usd": "0.1790"}, {"cost_usd": 0.179}, {"cost_usd": None}, {"cost_usd": 0}]
    fake = _use(monkeypatch, _Ledger(data={"ai_video_jobs": rows}))
    assert db.ai_video_spend_this_month() == 0.358
    column, start = _gte(fake)
    now = datetime.now(timezone.utc)
    assert column == "created_at"
    assert start == now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def test_a_missing_ledger_table_is_unavailable_not_empty(monkeypatch):
    """No table must never read as "nothing bought": a caller that took [] for an empty ledger
    would buy every shot again (design 6.2 step 6: a failed ledger read means nothing is bought)."""
    calls = [lambda: db.reserve_ai_video_job(5, 0, "e", 0.179),
             lambda: db.update_ai_video_job(7, status="late"),
             lambda: db.ai_video_jobs_for_idea(5),
             db.open_ai_video_jobs,
             lambda: db.ai_video_jobs_since(datetime.now(timezone.utc)),
             db.ai_video_spend_this_month]
    for call in calls:
        _use(monkeypatch, _Ledger(errors=[_NO_LEDGER]))
        with pytest.raises(db.LedgerUnavailable):
            call()


def test_a_failed_ledger_read_raises(monkeypatch):
    _use(monkeypatch, _Ledger(errors=[{"code": "57014", "message": "statement timeout"}]))
    with pytest.raises(APIError):
        db.ai_video_jobs_for_idea(5)


def test_a_reservation_without_a_row_back_raises(monkeypatch):
    _use(monkeypatch, _Ledger(data={"ai_video_jobs": []}))
    with pytest.raises(RuntimeError):
        db.reserve_ai_video_job(5, 0, "e", 0.179)
