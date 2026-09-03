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


# --- real article links (2026-09-03) ------------------------------------------------------
# The feed carries a live <link> and a publisher <source> for every headline, and ideation was
# throwing both away — then asking the LLM to remember source URLs, which it cannot do. Measured
# on the live feed: 38 items, every link HTTP 200, including the exact stories the model was
# citing with invented `articleshow/115000000.cms`-style URLs.

_SAMPLE_RSS_WITH_SOURCE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Top stories - Google News</title>
<item><title>Nepal flood toll passes 1,270 - Al Jazeera</title>
  <link>https://news.google.com/rss/articles/AAA</link><source url="https://aljazeera.com">Al Jazeera</source></item>
<item><title>Nepal floods: rescue continues - BBC</title>
  <link>https://news.google.com/rss/articles/BBB</link><source url="https://bbc.com">BBC</source></item>
</channel></rss>"""


def test_fetch_stories_keeps_the_article_link_and_publisher():
    with mock.patch("src.news.requests.get", return_value=_resp(_SAMPLE_RSS_WITH_SOURCE)):
        out = news.fetch_stories(10)
    assert out == [
        {"title": "Nepal flood toll passes 1,270 - Al Jazeera",
         "url": "https://news.google.com/rss/articles/AAA", "source": "Al Jazeera"},
        {"title": "Nepal floods: rescue continues - BBC",
         "url": "https://news.google.com/rss/articles/BBB", "source": "BBC"},
    ]


def test_fetch_stories_skips_items_with_no_link():
    """A citation is the whole point here — a title with no URL is not a usable story."""
    rss = _SAMPLE_RSS_WITH_SOURCE.replace("<link>https://news.google.com/rss/articles/AAA</link>", "")
    with mock.patch("src.news.requests.get", return_value=_resp(rss)):
        out = news.fetch_stories(10)
    assert [s["title"] for s in out] == ["Nepal floods: rescue continues - BBC"]


def test_fetch_stories_best_effort_on_error():
    with mock.patch("src.news.requests.get", side_effect=ConnectionError("offline")):
        assert news.fetch_stories() == []


# --- per-story search (2026-09-03) --------------------------------------------------------
# The top-stories feed only carries whatever is on the front page, so an idea about a story that
# has scrolled off it matches nothing. Google News' RSS *search* endpoint is the same free,
# key-less feed filtered by query — measured live: 49-100 results per query, several independent
# outlets each. That is how an under-sourced idea reaches MIN_SOURCES without spending API quota.

def test_search_stories_queries_the_rss_search_endpoint():
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _resp(_SAMPLE_RSS_WITH_SOURCE)

    with mock.patch("src.news.requests.get", side_effect=fake_get):
        out = news.search_stories("Nepal floods & India", limit=1)

    assert "news.google.com/rss/search?q=" in captured["url"]
    assert "Nepal%20floods%20%26%20India" in captured["url"]  # query is URL-encoded
    assert out == [{"title": "Nepal flood toll passes 1,270 - Al Jazeera",
                    "url": "https://news.google.com/rss/articles/AAA", "source": "Al Jazeera"}]


def test_search_stories_is_best_effort():
    with mock.patch("src.news.requests.get", side_effect=ConnectionError("offline")):
        assert news.search_stories("anything") == []


def test_search_stories_returns_nothing_for_an_empty_query():
    """Guard: an empty q returns Google's whole front page, which would cite unrelated articles."""
    with mock.patch("src.news.requests.get", side_effect=AssertionError("must not request")):
        assert news.search_stories("   ") == []
