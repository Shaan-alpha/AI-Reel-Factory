"""Demand signals: what India is looking up, and what Indian Shorts viewers are watching now.

Contract:
    what it does : turns two free, keyless public feeds into short lines for the story picker.
    how to use   : `demand_lines()` -> list[str] (empty when nothing could be read).
    depends on   : requests + stdlib XML. No key, no quota, no account.

1. Wikimedia's daily most-viewed pages for India, each article scored as yesterday's views over
   its own median for the week before, so evergreen pages do not rank (India report, "Three free
   feeds"). About 8 requests a run, inside the anonymous rate limit, with a generic User-Agent
   and no contact details.
2. The public upload feeds of comparable Hindi explainer channels: a Short earning views an hour
   well above its own channel's median pace is a story Indian viewers are watching now.

Nobody has tested whether these predict views for a small channel (design 8.3); the picker
records which lines a story matched, so the retention data can answer it. Everything here is
best-effort (rule 11): a source that fails costs its lines, never ideation.
"""
from __future__ import annotations

import logging
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import requests

from src import config

log = logging.getLogger(__name__)

_WIKI_URL = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/IN/all-access/"
             "{y}/{m:02d}/{d:02d}")
_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
_USER_AGENT = "news-shorts-demand/1.0"  # generic on purpose: no contact details leave this machine
_TIMEOUT = 20
_SKIP_PAGES = ("Main_Page", "-")
# A namespace page ("Special:Search", Danish "Speciel:Søgning"): a colon straight after the first
# word. An article title's colon is followed by a space ("Ramayana:_Part_1").
_NAMESPACE_RE = re.compile(r"^[^_:]+:[^_]")
# English and the Indian-language Wikipedias; India's list also carries other projects' pages.
_PROJECTS = frozenset(f"{code}.wikipedia" for code in
                      ("en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "or", "as", "ur"))
# The twelve channels the India research sampled (research_notes, 2026-11-10). DEMAND_CHANNELS
# (comma list) replaces them.
_DEFAULT_CHANNELS = (
    "UCGdPm5Aq081vVD7ih9jZf6Q,UCglXlpWjIi95auM3umWWLdw,UCzwCEE_PchiBULMnAJqhGVg,"
    "UCwAdQUuPT6laN-AQR17fe1g,UCw5hEVOTfz_AfzsNFWyNlNg,UCsDTy8jvHcwMvSZf_JGi-FA,"
    "UCmTM_hPCeckqN3cPWtYZZcg,UCXUJJNoP1QupwsYIWFXmsZg,UCVOTBwF0vnSxMRIbfSE_K_g,"
    "UCRzYN32xtBf3Yxsx5BvJWJw,UCOhHO2ICt0ti9KAh-QHvttQ,UCKZozRVHRYsYHGEyNKuhhdA")
_NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}
_MAX_LINES = 8


def _wiki_day(day: date) -> tuple[dict[str, int], int]:
    """(article -> views, the list's smallest entry) for one day of the India list; ({}, 0) for a
    missing day or any failure."""
    url = _WIKI_URL.format(y=day.year, m=day.month, d=day.day)
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
        if resp.status_code == 404:  # Wikimedia skips the odd day
            return {}, 0
        resp.raise_for_status()
        articles = resp.json()["items"][0]["articles"]
    except Exception as e:  # noqa: BLE001 — one day lost is one day lost
        log.warning("demand: Wikipedia India list for %s unavailable (%s)", day, e)
        return {}, 0
    views: dict[str, int] = {}
    floor = min((int(a.get("views_ceil") or a.get("views") or 0) for a in articles), default=0)
    for a in articles:
        name = str(a.get("article") or "")
        if (not name or name in _SKIP_PAGES or _NAMESPACE_RE.match(name)
                or a.get("project", "en.wikipedia") not in _PROJECTS):
            continue
        views[name] = views.get(name, 0) + int(a.get("views_ceil") or a.get("views") or 0)
    return views, floor


def wikipedia_india_spikes(days: int = 8, top: int = 15, min_views: int = 5000,
                           today: date | None = None) -> list[dict]:
    """Yesterday's India articles by views over their own median for the week before.

    The list holds only the top pages, so an article absent on a day had at most that day's
    smallest entry: it counts at that floor, which keeps the ratio a fair lower bound instead of
    views over zero (live on 2026-11-12: "46200x its usual")."""
    today = today or datetime.now(timezone.utc).date()
    daily = [_wiki_day(today - timedelta(days=i)) for i in range(1, days + 1)]
    (latest, _), prior = daily[0], daily[1:]
    spikes = []
    for name, views in latest.items():
        if views < min_views:
            continue
        usual = statistics.median([day.get(name, floor) for day, floor in prior]) if prior else 0
        spikes.append({"title": name.replace("_", " "), "views": views,
                       "ratio": round(views / max(usual, 1), 1)})
    return sorted(spikes, key=lambda s: -s["ratio"])[:top]


def _channel_shorts(channel_id: str, now: datetime) -> tuple[str, list[dict]]:
    resp = requests.get(_FEED_URL.format(cid=channel_id), timeout=_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    author = root.find("a:author/a:name", _NS)
    channel = (author.text or "").strip() if author is not None else channel_id
    shorts = []
    for entry in root.findall("a:entry", _NS):
        link = entry.find("a:link", _NS)
        href = link.get("href", "") if link is not None else ""
        if "/shorts/" not in href:
            continue
        published = datetime.fromisoformat(entry.findtext("a:published", "", _NS))
        stats = entry.find("media:group/media:community/media:statistics", _NS)
        views = int(stats.get("views") or 0) if stats is not None else 0
        hours = max((now - published).total_seconds() / 3600, 1.0)
        shorts.append({"title": (entry.findtext("a:title", "", _NS) or "").strip(),
                       "views": views, "hours": hours, "pace": views / hours})
    return channel, shorts


def channel_spikes(channel_ids: list[str] | None = None, max_age_hours: float = 72,
                   min_ratio: float = 2.0, now: datetime | None = None) -> list[dict]:
    """Recent Shorts pacing well ahead of their own channel's median, best first."""
    now = now or datetime.now(timezone.utc)
    ids = channel_ids or [c.strip() for c in
                          (config.get("DEMAND_CHANNELS") or _DEFAULT_CHANNELS).split(",")
                          if c.strip()]
    spikes = []
    for cid in ids:
        try:
            channel, shorts = _channel_shorts(cid, now)
        except Exception as e:  # noqa: BLE001 — one channel down costs that channel
            log.warning("demand: feed for %s unavailable (%s)", cid, e)
            continue
        if len(shorts) < 3:
            continue
        norm = statistics.median(s["pace"] for s in shorts)
        for s in shorts:
            if s["hours"] <= max_age_hours and norm > 0 and s["pace"] / norm >= min_ratio:
                spikes.append({"channel": channel, "title": s["title"], "views": s["views"],
                               "ratio": round(s["pace"] / norm, 1)})
    return sorted(spikes, key=lambda s: -s["ratio"])


def demand_lines() -> list[str]:
    """Both signals as short lines for the picker's prompt. [] when neither could be read."""
    lines: list[str] = []
    try:
        for s in wikipedia_india_spikes()[:_MAX_LINES]:
            lines.append(f'India on Wikipedia yesterday: "{s["title"]}", {s["views"]:,} views, '
                         f'{s["ratio"]:g}x its usual')
    except Exception as e:  # noqa: BLE001
        log.warning("demand: Wikipedia signal failed (%s)", e)
    try:
        for s in channel_spikes()[:_MAX_LINES]:
            lines.append(f'Indian Shorts now: "{s["title"]}" ({s["channel"]}), {s["ratio"]:g}x '
                         f"that channel's usual pace")
    except Exception as e:  # noqa: BLE001
        log.warning("demand: channel signal failed (%s)", e)
    return lines
