"""Trending topics — free daily India trends to make ideation timely (not generic).

Contract:
    what it does : fetches today's trending search topics in India to seed ideation.
    how to use   : `fetch_trending()` → list of trending topic strings (best-effort).
    depends on   : requests + stdlib XML (Google Trends RSS — no API key, no quota).

Best-effort by design (rule 11): if the feed is unreachable, returns [] and ideation simply
proceeds without trend seeding. No secrets, free, machine-off friendly.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from src import config

log = logging.getLogger(__name__)

# Google Trends "trending now" RSS for a geo — no auth, no key. Override geo via TRENDS_GEO.
_RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"
_TIMEOUT = 20


# Generic search-trend noise that is never an impact-news story (best-effort, tunable).
# Trends are only a SUPPLEMENTARY flavour signal now (news is the primary anchor), so
# over-filtering here is acceptable — the news feed carries the real stories.
_NOISE_SUBSTRINGS = (
    "weather", "storm", "temperature", "forecast", "calendar", "horoscope",
    "rashifal", "panchang", "purnima", "ekadashi", "amavasya", "predictor",
    "dream11", "fantasy xi", "live score", "scorecard", "lottery", "result today",
)
_NOISE_PATTERNS = (
    re.compile(r"\bvs\.?\b", re.I),   # "X vs Y" sports/match matchups
    re.compile(r"\bv/s\b", re.I),
)


def _is_noise(topic: str) -> bool:
    """True for generic search noise (weather/calendar/sports-score) that isn't a story."""
    low = topic.lower()
    if any(s in low for s in _NOISE_SUBSTRINGS):
        return True
    return any(p.search(topic) for p in _NOISE_PATTERNS)


def fetch_trending(limit: int = 15) -> list[str]:
    """Return up to `limit` trending search topics for the configured geo (default IN). [] on failure."""
    geo = config.get("TRENDS_GEO", "IN")
    try:
        resp = requests.get(
            _RSS_URL.format(geo=geo), timeout=_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (AI-Reel-Factory trends)"},
        )
        resp.raise_for_status()
        topics = [t for t in _parse(resp.text) if not _is_noise(t)]
    except Exception as e:  # noqa: BLE001 — trends are a nice-to-have, never block ideation
        log.warning("trends: could not fetch trending topics (%s)", e)
        return []
    log.info("trends: %d trending topics for geo=%s", len(topics), geo)
    return topics[:limit]


def _parse(xml_text: str) -> list[str]:
    """Extract <item><title> values from the Trends RSS (skips the channel title)."""
    root = ET.fromstring(xml_text)
    titles = []
    for item in root.iter("item"):
        t = item.findtext("title")
        if t and t.strip():
            titles.append(t.strip())
    return titles
