"""Unit tests for `db.top_performing_titles` — the analytics → ideation feedback loop.

No live creds: a fake PostgREST client stands in for Supabase, so these run in CI.

The thing under test is easy to get wrong because `analytics` is a TIME SERIES — every
`collect_stats()` run appends one snapshot per published post. Ranking raw snapshot rows
ranks *snapshots*, not videos, so one popular Short's daily history can occupy every top
slot and starve the winners list. These tests pin the collapse-then-rank behaviour.
"""
from __future__ import annotations

import pytest

from src import db


class _FakeQuery:
    """Minimal stand-in for the supabase-py query builder (chainable, terminal .execute())."""

    def __init__(self, table: str, store: "_FakeClient"):
        self._table, self._store = table, store
        self._limit: int | None = None
        self._count = False
        self._order: tuple[str, bool] | None = None

    def select(self, *_a, **kw):
        self._count = kw.get("count") == "exact"
        return self

    def order(self, column, **kw):
        # Honoured, not ignored: ordering by `views` vs `id` is the whole difference between
        # the starved ranking and the correct one, so a fake that drops it tests nothing.
        self._order = (column, kw.get("desc", False))
        return self

    def eq(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    @property
    def not_(self):
        return self

    def is_(self, *_a, **_kw):
        return self

    def execute(self):
        if self._table == "posts":
            rows = self._store.posts
            return type("R", (), {"data": rows, "count": len(rows)})()
        rows = list(self._store.analytics)
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col) or 0, reverse=desc)
        self._store.window_asked = self._limit
        rows = rows[: self._limit] if self._limit else rows
        return type("R", (), {"data": rows, "count": len(rows)})()


class _FakeClient:
    def __init__(self, analytics: list[dict], posts: list[dict]):
        # `analytics` must be newest-first, mirroring `.order("id", desc=True)`.
        self.analytics, self.posts = analytics, posts
        self.window_asked: int | None = None

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self)


def _snapshot(post_id: int, views: int, title: str, row_id: int = 0) -> dict:
    return {
        "id": row_id,
        "post_id": post_id,
        "views": views,
        "posts": {"scripts": {"title": title, "ideas": {"title": f"idea-{post_id}"}}},
    }


def _install(monkeypatch, analytics, posts) -> _FakeClient:
    fake = _FakeClient(analytics, posts)
    monkeypatch.setattr(db, "get_client", lambda: fake)
    return fake


def test_repeated_snapshots_do_not_starve_the_winners_list(monkeypatch):
    """The regression: 6 videos exist, but a runaway hit's daily history floods the window.

    Mirrors production on 2026-08-25 (72 posts / 3,454 snapshots), where the top-24 window
    covered only 3 distinct videos and ideation received 3 winners after asking for 6.
    """
    # 40 daily passes over 6 published Shorts, exactly as collect_stats() writes them.
    # Post 1 is a breakout, so EVERY one of its 40 snapshots outranks every other video.
    analytics, row_id = [], 0
    for day in range(40):
        for pid in range(1, 7):
            row_id += 1
            views = 9_000 + day if pid == 1 else (1_000 - pid) + day
            analytics.append(_snapshot(pid, views, f"Video {pid}", row_id))

    _install(monkeypatch, analytics, [{"id": p} for p in range(1, 7)])
    out = db.top_performing_titles(6)

    assert len(out) == 6, f"asked for 6 distinct winners, got {len(out)}: {out}"
    assert len(set(out)) == 6
    assert sum('"Video 1"' in o for o in out) == 1, "the breakout must appear exactly once"
    assert out[0] == '"Video 1" — 9,039 views', "and it must lead, at its LATEST view count"


def test_uses_the_latest_snapshot_not_a_stale_one(monkeypatch):
    """Views only ever rise, so a post's newest snapshot is its true standing."""
    analytics = [
        _snapshot(1, 12, "Grew Overnight", row_id=1),  # yesterday's reading
        _snapshot(2, 900, "Steady", row_id=2),
        _snapshot(1, 5_000, "Grew Overnight", row_id=3),  # today's — the true standing
    ]
    _install(monkeypatch, analytics, [{"id": 1}, {"id": 2}])
    out = db.top_performing_titles(5)

    assert out[0] == '"Grew Overnight" — 5,000 views'
    assert len(out) == 2


def test_window_scales_with_the_post_count(monkeypatch):
    """A fixed window silently decays as snapshots pile up; it must track the channel size."""
    analytics = [_snapshot(p, 100 + p, f"V{p}") for p in range(1, 51)]
    fake = _install(monkeypatch, analytics, [{"id": p} for p in range(1, 51)])
    db.top_performing_titles(8)

    assert fake.window_asked >= 50, (
        f"window {fake.window_asked} cannot cover 50 posts' latest snapshots"
    )


def test_falls_back_to_the_idea_title_and_skips_malformed_rows(monkeypatch):
    analytics = [
        {"post_id": 1, "views": 500, "posts": {"scripts": {"title": None,
                                                           "ideas": {"title": "Idea Title"}}}},
        {"post_id": 2, "views": 400, "posts": None},          # orphaned embed
        {"post_id": 3, "views": 300, "posts": {"scripts": {}}},  # no title at all
    ]
    _install(monkeypatch, analytics, [{"id": 1}, {"id": 2}, {"id": 3}])
    assert db.top_performing_titles(5) == ['"Idea Title" — 500 views']


def test_no_published_posts_returns_empty(monkeypatch):
    _install(monkeypatch, [], [])
    assert db.top_performing_titles() == []


# --- posts.published_at must actually be written -------------------------------------------

class _CapturingInsert:
    """Captures the row handed to .insert() and returns a plausible PostgREST response."""

    def __init__(self):
        self.row = None

    def table(self, _name):
        return self

    def insert(self, row):
        self.row = row
        return self

    def execute(self):
        return type("R", (), {"data": [{"id": 1}]})()


def test_insert_post_stamps_published_at(monkeypatch):
    """Every one of the 75 live rows had published_at=NULL because insert_post never set it.

    The column has no DB default, so the operator's own dashboard lied: the Telegram bot's
    /today filters `published_at=gte.<IST midnight>` and therefore always reported 0 Shorts,
    and /latest orders by a column that was NULL for every row.
    """
    fake = _CapturingInsert()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    db.insert_post(script_id=1, platform="youtube", external_id="abc", url="u", status="published")
    assert fake.row.get("published_at"), "published_at must be stamped at insert time"
    # ISO-8601 UTC, which is what PostgREST's timestamptz filters compare against.
    from datetime import datetime
    parsed = datetime.fromisoformat(fake.row["published_at"])
    assert parsed.tzinfo is not None, "must be timezone-aware or the IST window comparison drifts"
