"""Curated news headlines — free Google News RSS to ground ideation in REAL current stories.

Contract:
    what it does : fetches today's news stories (India locale) to seed ideation with real,
                   current stories — not just trending search noise.
    how to use   : `fetch_stories()` → [{title, url, source}]; `fetch_headlines()` → titles only.
    depends on   : requests + stdlib XML (Google News RSS — no API key, no quota).

Best-effort by design (rule 11): if the feed is unreachable, returns [] and ideation proceeds on
trends + the model's own knowledge. No secrets, free, machine-off friendly.
"""
from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from src import config

log = logging.getLogger(__name__)

# Google News "top stories" RSS for a locale — no auth, no key. Override the whole URL via
# NEWS_RSS_URL (e.g. a topic feed: news.google.com/rss/search?q=ISRO&hl=en-IN&gl=IN&ceid=IN:en).
_DEFAULT_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
# The same free feed, filtered by query — no key, no quota. Used to source an idea whose
# story has already scrolled off the top-stories front page.
_SEARCH_URL = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
# Section feeds of the same edition. The front page alone made the pool almost all geopolitics
# and conflict (audit 2026-09-27); these widen it without a key or quota.
_TOPIC_URL = "https://news.google.com/rss/headlines/section/topic/{topic}?hl=en-IN&gl=IN&ceid=IN:en"
_DEFAULT_TOPICS = "WORLD,BUSINESS,TECHNOLOGY,SCIENCE"  # HEALTH left out: journal items, medical claims
_TIMEOUT = 20


def _get_stories(url: str) -> list[dict]:
    resp = requests.get(url, timeout=_TIMEOUT,
                        headers={"User-Agent": "Mozilla/5.0 (AI-Reel-Factory news)"})
    resp.raise_for_status()
    return _parse_stories(resp.text)


def fetch_stories(limit: int = 12) -> list[dict]:
    """Return up to `limit` current stories as {title, url, source}. [] on failure.

    The `url` is the feed's own article link and the `source` its publisher name. Both were
    parsed away until 2026-09-03, which is why ideation had to ask the LLM to supply source
    URLs from memory — it cannot, so it invented them (placeholder ids like
    `articleshow/115000000.cms`), the liveness probe 404'd them, and every idea citing only
    invented links was dropped. These links are real and live, so ideas keep their sources.
    """
    # `or _DEFAULT_URL` (not config.get's default arg): an empty NEWS_RSS_URL repo var reaches
    # us as "" in CI, which would otherwise become an invalid request URL.
    url = config.get("NEWS_RSS_URL") or _DEFAULT_URL
    feeds: list[list[dict]] = []
    try:
        feeds.append(_get_stories(url))
    except Exception as e:  # noqa: BLE001 — headlines are a nice-to-have, never block ideation
        log.warning("news: could not fetch headlines (%s)", e)
    topics = [t.strip().upper() for t in
              (config.get("NEWS_TOPICS", _DEFAULT_TOPICS) or "").split(",") if t.strip()]
    for topic in topics:
        try:
            feeds.append(_get_stories(_TOPIC_URL.format(topic=urllib.parse.quote(topic))))
        except Exception as e:  # noqa: BLE001 — one section down costs only that section
            log.warning("news: %s section unavailable (%s)", topic, e)
    # Interleave, so the front page cannot fill the pool before any section is heard.
    stories, seen = [], set()
    for rank in range(max((len(f) for f in feeds), default=0)):
        for feed in feeds:
            if rank < len(feed) and feed[rank]["url"] not in seen:
                seen.add(feed[rank]["url"])
                stories.append(feed[rank])
    log.info("news: %d stories from %d feed(s)", len(stories), len(feeds))
    return stories[:limit]


def search_stories(query: str, limit: int = 6) -> list[dict]:
    """Stories matching `query` as {title, url, source}. [] on failure or an empty query.

    Independent outlets covering one event is exactly what MIN_SOURCES asks for, and this gets
    them for free — no API key and no quota, so it still works on a day the grounded search has
    spent its 20 free requests (rule 13). An empty query is refused rather than sent: Google
    answers it with the general front page, which would attach unrelated articles to an idea.
    """
    query = (query or "").strip()
    if not query:
        return []
    # Recency: an unbounded search attached a two-year-old article to a 2026 flood story
    # (live, 2026-09-27). Google News reads `when:3d` as "the last three days".
    window = (config.get("NEWS_SEARCH_WINDOW", "3d") or "").strip()
    url = _SEARCH_URL.format(q=urllib.parse.quote(f"{query} when:{window}" if window else query))
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (AI-Reel-Factory news)"},
        )
        resp.raise_for_status()
        stories = _parse_stories(resp.text)
    except Exception as e:  # noqa: BLE001 — a search miss must never block ideation (rule 11)
        log.warning("news: search for %r failed (%s)", query, e)
        return []
    log.info("news: %d stories for %r", len(stories), query)
    return stories[:limit]


def fetch_headlines(limit: int = 12) -> list[str]:
    """Return up to `limit` current headline titles (e.g. 'Headline - Source'). [] on failure."""
    return [s["title"] for s in fetch_stories(limit)]


def _item_source(item) -> str:
    """The publisher name from <source>, namespace-tolerant. '' when the feed omits it."""
    for el in item:
        if el.tag.rsplit("}", 1)[-1] == "source" and (el.text or "").strip():
            return el.text.strip()
    return ""


def _parse_stories(xml_text: str) -> list[dict]:
    """Extract {title, url, source} per <item> (skips the channel title and link-less items)."""
    root = ET.fromstring(xml_text)
    stories = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:  # a headline with no URL cannot be cited, so it is not a story
            story = {"title": title, "url": link, "source": _item_source(item)}
            published = (item.findtext("pubDate") or "").strip()
            if published:
                story["published"] = published
            stories.append(story)
    return stories


def _parse(xml_text: str) -> list[str]:
    """Extract <item><title> values from the news RSS (skips the channel title)."""
    return [s["title"] for s in _parse_stories(xml_text)]
