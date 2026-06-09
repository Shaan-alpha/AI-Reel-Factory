"""Tests for the trends module — RSS parse + best-effort failure handling (no network)."""
from __future__ import annotations

from src import trends

_RSS = """<?xml version="1.0"?>
<rss><channel><title>Daily Search Trends</title>
  <item><title>India vs Australia</title></item>
  <item><title>ISRO launch</title></item>
  <item><title>  Budget 2026  </title></item>
</channel></rss>"""


def test_parse_extracts_item_titles_only():
    out = trends._parse(_RSS)
    assert out == ["India vs Australia", "ISRO launch", "Budget 2026"]  # channel title skipped, trimmed


def test_fetch_trending_returns_empty_on_error(monkeypatch):
    def _boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(trends.requests, "get", _boom)
    assert trends.fetch_trending() == []  # best-effort: never raises


def test_fetch_trending_limits(monkeypatch):
    class _Resp:
        text = _RSS
        def raise_for_status(self):
            pass
    monkeypatch.setattr(trends.requests, "get", lambda *a, **k: _Resp())
    assert trends.fetch_trending(limit=2) == ["India vs Australia", "ISRO launch"]
