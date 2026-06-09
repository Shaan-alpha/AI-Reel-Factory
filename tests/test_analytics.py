"""Tests for the analytics module (Module 10) — stats parsing + collection, fully mocked."""
from __future__ import annotations

from src import analytics


class _FakeYouTube:
    def __init__(self, items):
        self._items = items

    def videos(self):
        return self

    def list(self, part, id):  # noqa: A002 — mirrors the API kwarg
        self._ids = id.split(",")
        return self

    def execute(self):
        return {"items": [it for it in self._items if it["id"] in self._ids]}


def test_fetch_stats_parses_counts():
    yt = _FakeYouTube([
        {"id": "v1", "statistics": {"viewCount": "1500", "likeCount": "42", "commentCount": "7"}},
        {"id": "v2", "statistics": {"viewCount": "10"}},  # likes/comments hidden
    ])
    out = analytics._fetch_stats(yt, ["v1", "v2"])
    assert out["v1"] == {"views": 1500, "likes": 42, "comments": 7}
    assert out["v2"] == {"views": 10, "likes": None, "comments": None}


def test_collect_stats_records_each_post(monkeypatch):
    monkeypatch.setattr(analytics.db, "get_published_posts",
                        lambda plat="youtube": [{"id": 1, "external_id": "v1"},
                                                {"id": 2, "external_id": "v2"}])
    monkeypatch.setattr(analytics, "_youtube_client", lambda: object())
    monkeypatch.setattr(analytics, "_fetch_stats",
                        lambda yt, vids: {"v1": {"views": 100, "likes": 5, "comments": 1},
                                          "v2": {"views": 9, "likes": None, "comments": None}})
    recorded = []
    monkeypatch.setattr(analytics.db, "insert_analytics",
                        lambda pid, views, likes=None, comments=None: recorded.append((pid, views)))
    assert analytics.collect_stats() == 2
    assert recorded == [(1, 100), (2, 9)]


def test_collect_stats_no_posts(monkeypatch):
    monkeypatch.setattr(analytics.db, "get_published_posts", lambda plat="youtube": [])
    assert analytics.collect_stats() == 0
