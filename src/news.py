"""Curated news headlines — free Google News RSS to ground ideation in REAL current stories.

Contract:
    what it does : fetches today's news headlines (India locale) to seed ideation with real,
                   current stories — not just trending search noise.
    how to use   : `fetch_headlines()` → list of headline strings (best-effort).
    depends on   : requests + stdlib XML (Google News RSS — no API key, no quota).

Best-effort by design (rule 11): if the feed is unreachable, returns [] and ideation proceeds on
trends + the model's own knowledge. No secrets, free, machine-off friendly.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from src import config

log = logging.getLogger(__name__)

# Google News "top stories" RSS for a locale — no auth, no key. Override the whole URL via
# NEWS_RSS_URL (e.g. a topic feed: news.google.com/rss/search?q=ISRO&hl=en-IN&gl=IN&ceid=IN:en).
_DEFAULT_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
_TIMEOUT = 20


def fetch_headlines(limit: int = 12) -> list[str]:
    """Return up to `limit` current headline titles (e.g. 'Headline - Source'). [] on failure."""
    # `or _DEFAULT_URL` (not config.get's default arg): an empty NEWS_RSS_URL repo var reaches
    # us as "" in CI, which would otherwise become an invalid request URL.
    url = config.get("NEWS_RSS_URL") or _DEFAULT_URL
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (AI-Reel-Factory news)"},
        )
        resp.raise_for_status()
        titles = _parse(resp.text)
    except Exception as e:  # noqa: BLE001 — headlines are a nice-to-have, never block ideation
        log.warning("news: could not fetch headlines (%s)", e)
        return []
    log.info("news: %d headlines", len(titles))
    return titles[:limit]


def _parse(xml_text: str) -> list[str]:
    """Extract <item><title> values from the news RSS (skips the channel title)."""
    root = ET.fromstring(xml_text)
    titles = []
    for item in root.iter("item"):
        t = item.findtext("title")
        if t and t.strip():
            titles.append(t.strip())
    return titles
