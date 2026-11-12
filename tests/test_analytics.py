"""Tests for the analytics module (Module 10) — stats parsing + collection, fully mocked."""
from __future__ import annotations

import pytest

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
    assert out["v1"] == {"views": 1500, "likes": 42, "comments": 7, "title": None}
    assert out["v2"] == {"views": 10, "likes": None, "comments": None, "title": None}


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


def test_collect_stats_applies_the_retention_lever(monkeypatch):
    """prune_analytics is a no-op unless ANALYTICS_KEEP_PER_POST is set — but it has to be CALLED
    from somewhere, or it is exactly the dead setting this audit complained about."""
    monkeypatch.setattr(analytics.db, "get_published_posts",
                        lambda platform="youtube": [{"id": 1, "external_id": "v1"}])
    monkeypatch.setattr(analytics, "_youtube_client", lambda: object())
    monkeypatch.setattr(analytics, "_fetch_stats",
                        lambda yt, ids: {"v1": {"views": 5, "likes": 1, "comments": 0}})
    monkeypatch.setattr(analytics.db, "insert_analytics", lambda *a, **k: None)
    pruned = []
    monkeypatch.setattr(analytics.db, "prune_analytics", lambda: pruned.append(True) or 0)

    assert analytics.collect_stats() == 1
    assert pruned, "collect_stats must give the retention lever a chance to run"


def test_a_failing_prune_never_loses_the_snapshots(monkeypatch):
    """Retention is housekeeping; the stats pull is the point (rule 14)."""
    monkeypatch.setattr(analytics.db, "get_published_posts",
                        lambda platform="youtube": [{"id": 1, "external_id": "v1"}])
    monkeypatch.setattr(analytics, "_youtube_client", lambda: object())
    monkeypatch.setattr(analytics, "_fetch_stats",
                        lambda yt, ids: {"v1": {"views": 5, "likes": None, "comments": None}})
    monkeypatch.setattr(analytics.db, "insert_analytics", lambda *a, **k: None)

    def _boom():
        raise RuntimeError("delete failed")

    monkeypatch.setattr(analytics.db, "prune_analytics", _boom)
    assert analytics.collect_stats() == 1


def test_a_short_gone_from_youtube_is_marked_and_reported_once(monkeypatch):
    marked, sent = [], []
    monkeypatch.setattr(analytics.db, "set_post_status", lambda pid, st: marked.append((pid, st)))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    from src import approval
    monkeypatch.setattr(approval, "_api", lambda method, **k: sent.append(k["text"]))
    gone = analytics._flag_removed({"AAA": {"id": 1}, "BBB": {"id": 2}}, {"AAA": {"views": 5}})
    assert gone == ["BBB"] and marked == [(2, "removed")]
    assert sent and "BBB" in sent[0]


def test_an_unsent_removal_alert_is_retried_next_run(monkeypatch):
    """Marking first meant a failed send was never repeated: 9 removals were never reported."""
    from src import approval

    def _down(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(approval, "_api", _down)
    marked = []
    monkeypatch.setattr(analytics.db, "set_post_status", lambda pid, s: marked.append(pid))
    analytics._flag_removed({"AAA": {"id": 1}}, {})
    assert marked == []  # still a target, so tomorrow's run reports it


def test_a_taken_down_short_counts_as_removed():
    class _YT:
        def videos(self):
            return self

        def list(self, **k):
            assert "status" in k["part"]
            return self

        def execute(self):
            return {"items": [
                {"id": "UP", "statistics": {"viewCount": "9"}, "status": {"uploadStatus": "processed"}},
                {"id": "GONE", "statistics": {}, "status": {"uploadStatus": "rejected"}},
            ]}

    stats = analytics._fetch_stats(_YT(), ["UP", "GONE"])
    assert "UP" in stats and "GONE" not in stats


def test_nothing_is_reported_when_every_short_is_still_up(monkeypatch):
    monkeypatch.setattr(analytics.db, "set_post_status", lambda *a: pytest.fail("nothing gone"))
    assert analytics._flag_removed({"AAA": {"id": 1}}, {"AAA": {"views": 5}}) == []


def test_the_real_youtube_title_is_backfilled_onto_old_scripts(monkeypatch):
    """Old scripts had no title, so the winners list showed the dry idea title instead."""
    monkeypatch.setattr(analytics.db, "get_published_posts",
                        lambda platform="youtube": [{"id": 1, "external_id": "AAA", "script_id": 9}])
    monkeypatch.setattr(analytics, "_youtube_client", lambda: None)
    monkeypatch.setattr(analytics, "_fetch_stats", lambda yt, ids: {
        "AAA": {"views": 5, "likes": 1, "comments": 0, "title": "Oil Export Wars"}})
    monkeypatch.setattr(analytics.db, "insert_analytics", lambda *a: None)
    monkeypatch.setattr(analytics.db, "prune_analytics", lambda: 0)
    filled = []
    monkeypatch.setattr(analytics.db, "backfill_script_title", lambda sid, t: filled.append((sid, t)))
    analytics.collect_stats()
    assert filled == [(9, "Oil Export Wars")]


# --- retention, audience and traffic per Short (design 10.1) ----------------------------------

from datetime import date  # noqa: E402

from googleapiclient.errors import HttpError  # noqa: E402


class _FakeAnalytics:
    """reports().query(**kw).execute() answers by the query's dimensions."""

    def __init__(self, answers, fail_for=()):
        self.answers, self.fail_for, self.queries = answers, set(fail_for), []

    def reports(self):
        return self

    def query(self, **kw):
        self.queries.append(kw)
        self._kw = kw
        return self

    def execute(self):
        if any(f"video=={v}" == self._kw.get("filters") for v in self.fail_for):
            raise HttpError(type("Resp", (), {"status": 500, "reason": "boom"})(), b"{}")
        return self.answers.get(self._kw.get("dimensions"), {})


_FULL = {
    None: {"rows": [[100, 40, 20, 71.5, 2]]},
    "country": {"rows": [["IN", 60], ["US", 40]]},
    "insightTrafficSourceType": {"rows": [["SHORTS", 90], ["YT_SEARCH", 10]]},
    "elapsedVideoTimeRatio": {"rows": [[0.01, 1.2], [0.5, 0.6], [1.0, 0.3]]},
}


def test_video_metrics_parses_totals_countries_traffic_and_retention():
    yta = _FakeAnalytics(_FULL)
    m = analytics._video_metrics(yta, "V1", date(2026, 11, 1), date(2026, 11, 7))
    assert m["views"] == 100 and m["engaged_views"] == 40 and m["avg_view_seconds"] == 20
    assert m["avg_view_pct"] == 71.5 and m["subscribers_gained"] == 2
    assert m["india_share"] == 0.6 and m["countries"] == {"IN": 60, "US": 40}
    assert m["traffic"] == {"SHORTS": 90, "YT_SEARCH": 10}
    assert m["retention"] == [[0.01, 1.2], [0.5, 0.6], [1.0, 0.3]]
    assert all(q["filters"] == "video==V1" and q["startDate"] == "2026-11-01"
               and q["endDate"] == "2026-11-07" for q in yta.queries)


def test_video_metrics_with_no_rows_stores_zeros():
    m = analytics._video_metrics(_FakeAnalytics({}), "V1", date(2026, 11, 1), date(2026, 11, 7))
    assert m["views"] == 0 and m["india_share"] is None
    assert m["countries"] == {} and m["traffic"] == {} and m["retention"] == []


def test_collect_metrics_measures_each_post_once_and_survives_an_error(monkeypatch):
    posts = [{"id": 1, "external_id": "BAD", "published_at": "2026-10-01T10:00:00+00:00"},
             {"id": 2, "external_id": "V2", "published_at": "2026-10-02T10:00:00+00:00"}]
    monkeypatch.setattr(analytics.db, "posts_needing_metrics", lambda **k: posts)
    stored = []
    monkeypatch.setattr(analytics.db, "upsert_post_metrics",
                        lambda post_id, window_days, metrics: stored.append((post_id, window_days)))
    monkeypatch.setattr(analytics, "_analytics_client", lambda: _FakeAnalytics(_FULL, {"BAD"}))
    assert analytics.collect_metrics() == 1
    assert stored == [(2, 7)]
