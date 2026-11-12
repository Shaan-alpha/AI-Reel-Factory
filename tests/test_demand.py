"""Demand signals for picking stories for Indian viewers (design 8.3): Wikipedia's India list and
comparable channels' Shorts. Hand-built responses only: no network."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src import demand


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _wiki_payload(articles):
    return {"items": [{"country": "IN", "access": "all-access",
                       "articles": [{"article": a, "project": "en.wikipedia", "views_ceil": v,
                                     "rank": i + 1} for i, (a, v) in enumerate(articles)]}]}


def test_wikipedia_spikes_rank_by_views_over_the_prior_week(monkeypatch):
    today = date(2026, 11, 12)
    yesterday = today - timedelta(days=1)
    urls = []

    def _get(url, headers=None, timeout=None):
        urls.append(url)
        day = date(*map(int, url.rsplit("/", 3)[-3:]))
        if day == yesterday:
            return _Resp(payload=_wiki_payload([("Main_Page", 900000), ("Special:Search", 50000),
                                                ("-", 40000), ("Sunita_Williams", 50000),
                                                ("Cricket", 80000)]))
        if day == yesterday - timedelta(days=3):
            return _Resp(status=404, payload={"detail": "not found"})  # a missing day is zero
        return _Resp(payload=_wiki_payload([("Sunita_Williams", 5000), ("Cricket", 80000)]))

    monkeypatch.setattr(demand.requests, "get", _get)
    spikes = demand.wikipedia_india_spikes(today=today)
    assert [s["title"] for s in spikes] == ["Sunita Williams", "Cricket"]
    assert spikes[0]["views"] == 50000 and spikes[0]["ratio"] == 10.0
    assert spikes[1]["ratio"] == 1.0
    assert len(urls) == 8
    assert all("/top-per-country/IN/all-access/" in u for u in urls)
    assert urls[0].endswith("/2026/11/11") and urls[-1].endswith("/2026/11/04")


def _feed(entries, author="FactTechz"):
    body = "".join(
        f"<entry><title>{t}</title><link rel=\"alternate\" href=\"{link}\"/>"
        f"<published>{published}</published><media:group><media:community>"
        f"<media:statistics views=\"{views}\"/></media:community></media:group></entry>"
        for t, link, published, views in entries)
    return ("<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:media=\"http://search.yahoo.com/mrss/\">"
            f"<author><name>{author}</name></author>{body}</feed>")


def test_channel_spikes_compare_each_short_with_its_channel(monkeypatch):
    now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    ten_hours_ago = (now - timedelta(hours=10)).isoformat()
    old = (now - timedelta(hours=100)).isoformat()
    entries = [("Slow one", "https://www.youtube.com/shorts/a", ten_hours_ago, 1000),
               ("Steady one", "https://www.youtube.com/shorts/b", ten_hours_ago, 1200),
               ("Hit", "https://www.youtube.com/shorts/c", ten_hours_ago, 9000),
               ("Long video", "https://www.youtube.com/watch?v=d", ten_hours_ago, 99000),
               ("Old short", "https://www.youtube.com/shorts/e", old, 11000)]
    monkeypatch.setattr(demand.requests, "get",
                        lambda url, headers=None, timeout=None: _Resp(text=_feed(entries)))
    spikes = demand.channel_spikes(["UCX"], now=now)
    assert [s["title"] for s in spikes] == ["Hit"]
    assert spikes[0]["channel"] == "FactTechz" and spikes[0]["views"] == 9000
    assert abs(spikes[0]["ratio"] - 7.8) < 0.1  # 900 an hour against the channel's median 115


def test_demand_lines_survive_every_source_failing(monkeypatch):
    def _down(*a, **k):
        raise ConnectionError("no network")

    monkeypatch.setattr(demand.requests, "get", _down)
    assert demand.demand_lines() == []


def test_wikimedia_requests_carry_no_contact_details(monkeypatch):
    seen = []

    def _get(url, headers=None, timeout=None):
        seen.append((headers or {}).get("User-Agent", ""))
        return _Resp(payload=_wiki_payload([]))

    monkeypatch.setattr(demand.requests, "get", _get)
    demand.wikipedia_india_spikes(today=date(2026, 11, 12))
    assert seen and all("@" not in ua and "http" not in ua for ua in seen)


def _wiki_payload_projects(rows):
    return {"items": [{"articles": [{"article": a, "project": p, "views_ceil": v, "rank": i + 1}
                                    for i, (a, p, v) in enumerate(rows)]}]}


def test_an_article_missing_from_a_day_counts_at_that_days_floor(monkeypatch):
    """The list holds only the top pages: absent means below its last entry, not zero views. Live
    on 2026-11-12, counting it as zero gave "Jensen Huang, 46200x its usual"."""
    today = date(2026, 11, 12)

    def _get(url, headers=None, timeout=None):
        day = date(*map(int, url.rsplit("/", 3)[-3:]))
        if day == today - timedelta(days=1):
            return _Resp(payload=_wiki_payload_projects([("Jensen_Huang", "en.wikipedia", 46200),
                                                         ("Cricket", "en.wikipedia", 4000)]))
        return _Resp(payload=_wiki_payload_projects([("Cricket", "en.wikipedia", 4000)]))

    monkeypatch.setattr(demand.requests, "get", _get)
    spikes = demand.wikipedia_india_spikes(today=today, min_views=1000)
    assert spikes[0]["title"] == "Jensen Huang" and spikes[0]["ratio"] == 11.6  # 46,200 / 4,000


def test_other_projects_and_namespaces_are_dropped(monkeypatch):
    rows = [("Speciel:Søgning", "da.wikipedia", 10700), ("Special:Search", "en.wikipedia", 9000),
            ("Ramayana:_Part_1", "en.wikipedia", 9000), ("दिवाली", "hi.wikipedia", 8000),
            ("Paris", "fr.wikipedia", 9000)]
    monkeypatch.setattr(demand.requests, "get",
                        lambda url, headers=None, timeout=None: _Resp(payload=_wiki_payload_projects(rows)))
    titles = {s["title"] for s in demand.wikipedia_india_spikes(today=date(2026, 11, 12))}
    assert titles == {"Ramayana: Part 1", "दिवाली"}
