"""Records for measuring (design sections 10 and 13): the format stamp, the upload read-back, one
row per attempt, and the Analytics metrics. Each write must survive the operator not having run
the new SQL yet: a missing column or table costs the record, never a reel."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
