"""Tests for the news module — curated headlines that ground ideation in real stories.

Mocks requests, so no network — verifies RSS parsing, the limit, and best-effort failure.
"""
from __future__ import annotations

from unittest import mock

from src import news

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Top stories - Google News</title>
<item><title>ISRO tests reusable rocket - The Hindu</title><link>https://a</link></item>
<item><title>India unveils new gas policy - Reuters</title><link>https://b</link></item>
<item><title>Monsoon arrives early - PTI</title><link>https://c</link></item>
</channel></rss>"""


def _resp(text):
    r = mock.Mock()
    r.raise_for_status = mock.Mock()
    r.text = text
    return r


def test_fetch_headlines_parses_item_titles():
    with mock.patch("src.news.requests.get", return_value=_resp(_SAMPLE_RSS)):
        out = news.fetch_headlines(10)
    assert out == [
        "ISRO tests reusable rocket - The Hindu",
        "India unveils new gas policy - Reuters",
        "Monsoon arrives early - PTI",
    ]  # channel <title> skipped, item titles kept in order


def test_fetch_headlines_respects_limit():
    with mock.patch("src.news.requests.get", return_value=_resp(_SAMPLE_RSS)):
        assert news.fetch_headlines(2) == [
            "ISRO tests reusable rocket - The Hindu",
            "India unveils new gas policy - Reuters",
        ]


def test_fetch_headlines_best_effort_on_error():
    with mock.patch("src.news.requests.get", side_effect=ConnectionError("offline")):
        assert news.fetch_headlines() == []   # never raises; ideation proceeds without it


def test_empty_news_rss_url_env_falls_back_to_default(monkeypatch):
    # an unset repo var arrives as "" in CI — it must NOT become the request URL (regression)
    monkeypatch.setenv("NEWS_RSS_URL", "")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _resp(_SAMPLE_RSS)

    with mock.patch("src.news.requests.get", side_effect=fake_get):
        news.fetch_headlines(2)
    assert captured["url"].startswith("https://news.google.com")
