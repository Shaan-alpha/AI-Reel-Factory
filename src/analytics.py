"""Module 10 — Analytics (learn what works).

Contract:
    what it does : pulls each published Short's public stats (views/likes/comments) from the
                   YouTube Data API and records them; the best topics feed back into ideation.
    how to use   : `collect_stats()` (run by .github/workflows/analytics.yml); ideation reads
                   `db.top_performing_titles()`.
    depends on   : google-api-python-client, google-auth, src.db, src.config.

Free + read-only: uses the `youtube.readonly` scope (already granted) and `videos.list?
part=statistics` (no YouTube Analytics API / no extra scope). Retention isn't in the public
Data API, so we learn from views/likes/comments — enough to bias ideation toward winners.
Idempotent-friendly: each run inserts a fresh snapshot row (time series), never double-counts.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from src import config, db

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def _youtube_client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=config.require("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.require("YOUTUBE_CLIENT_ID"),
        client_secret=config.require("YOUTUBE_CLIENT_SECRET"),
        scopes=_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# videos.list still returns a taken-down video, with this uploadStatus and no real stats.
_TAKEN_DOWN = {"rejected", "deleted", "failed"}


def _fetch_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Return {video_id: {views, likes, comments}} via videos.list (batched 50/call)."""
    out: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        # snippet and status cost nothing extra (one unit per call either way): snippet carries
        # the real title, status a takedown, which leaves the video listed with no stats.
        resp = youtube.videos().list(part="snippet,statistics,status",
                                     id=",".join(batch)).execute()
        for item in resp.get("items", []):
            if (item.get("status") or {}).get("uploadStatus") in _TAKEN_DOWN:
                continue  # reported by _flag_removed like a deleted video
            s = item.get("statistics", {})
            out[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)) if "likeCount" in s else None,
                "comments": int(s.get("commentCount", 0)) if "commentCount" in s else None,
                "title": (item.get("snippet") or {}).get("title"),
            }
    return out


def _flag_removed(by_vid: dict[str, dict], stats: dict[str, dict]) -> list[str]:
    """Say on Telegram which Shorts are gone from YouTube, then mark them 'removed'.

    The owner's token sees private and unlisted videos too, so an id missing from the stats is
    gone: deleted, or taken down (_fetch_stats leaves those out). Marked rows leave
    get_published_posts, so each one is reported once. The alert goes FIRST: the old order marked
    the rows, then failed to send (analytics.yml passed no Telegram secrets), so 9 removals were
    never reported and could never be again. Unsent now means unmarked, so the next run retries."""
    gone = [vid for vid in by_vid if vid not in stats]
    if not gone:
        return gone
    log.warning("analytics: %d Short(s) no longer on YouTube: %s", len(gone), gone)
    try:
        from src import approval

        approval._api("sendMessage", chat_id=config.require("TELEGRAM_CHAT_ID"),
                      text=f"🗑️ {len(gone)} Short(s) are no longer on YouTube (deleted or "
                           f"taken down): " + ", ".join(gone))
    except Exception as e:  # noqa: BLE001 — alerting must never cost the snapshots
        log.error("analytics: removal alert not sent (%s); the next run tries again", e)
        return gone
    for vid in gone:
        try:
            db.set_post_status(by_vid[vid]["id"], "removed")
        except Exception as e:  # noqa: BLE001 — bookkeeping only (rule 14)
            log.warning("analytics: could not mark %s removed (%s)", vid, e)
    return gone


def collect_stats() -> int:
    """Snapshot stats for every published Short into the analytics table. Returns #recorded."""
    posts = db.get_published_posts("youtube")
    by_vid = {p["external_id"]: p for p in posts if p.get("external_id")}
    if not by_vid:
        log.info("analytics: no published posts yet.")
        return 0

    stats = _fetch_stats(_youtube_client(), list(by_vid))
    _flag_removed(by_vid, stats)
    recorded = 0
    for vid, st in stats.items():
        post = by_vid.get(vid)
        if not post:
            continue
        try:
            db.insert_analytics(post["id"], st["views"], st["likes"], st["comments"])
            recorded += 1
        except Exception as e:  # noqa: BLE001 — one bad row shouldn't stop the pull
            log.warning("analytics: failed to record %s (%s)", vid, e)
        # Scripts from before titles were saved fell back to the dry idea title ("... Explained")
        # in the winners list, the very style the ideation prompt bans. YouTube has the real one.
        if st.get("title") and post.get("script_id"):
            try:
                db.backfill_script_title(post["script_id"], st["title"])
            except Exception as e:  # noqa: BLE001
                log.warning("analytics: title backfill failed for %s (%s)", vid, e)
    log.info("analytics: recorded %d snapshots.", recorded)

    # Retention is a no-op unless ANALYTICS_KEEP_PER_POST is set (see db.prune_analytics), but it
    # has to be invoked from somewhere or the setting is one an operator can tune with no effect.
    # Best-effort: housekeeping must never cost us the snapshots we just pulled (rule 14).
    try:
        dropped = db.prune_analytics()
        if dropped:
            log.info("analytics: pruned %d old snapshot(s).", dropped)
    except Exception as e:  # noqa: BLE001
        log.warning("analytics: retention pass failed (%s); snapshots are recorded regardless", e)
    return recorded


# --- retention, audience and traffic per Short (design 10.1) ----------------------------------
# The public view count cannot say whether viewers left at frame 1 or second 5, or whether they
# were in India. The YouTube Analytics API can. It was enabled on the OAuth client's Google Cloud
# project on 2026-11-12, and today's refresh token then read these reports with no new consent.

_TOTALS = "views,engagedViews,averageViewDuration,averageViewPercentage,subscribersGained"
_WINDOW_DAYS = 7


def _analytics_client():
    """YouTube Analytics v2 from the pipeline's refresh token, with the token's own grants."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=config.require("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.require("YOUTUBE_CLIENT_ID"),
        client_secret=config.require("YOUTUBE_CLIENT_SECRET"),
        scopes=None,
    )
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _rows(yta, video_id: str, start: date, end: date, metrics: str,
          dimensions: str | None = None, **extra) -> list:
    kw = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
          "metrics": metrics, "filters": f"video=={video_id}", **extra}
    if dimensions:
        kw["dimensions"] = dimensions
    return yta.reports().query(**kw).execute().get("rows") or []


def _video_metrics(yta, video_id: str, start: date, end: date) -> dict:
    """One Short's window: totals, the India share, top countries, traffic sources, and the
    retention curve. A video with no data comes back as zeros and empties, never an error.

    The country report leaves out countries below YouTube's privacy threshold (live on
    2026-11-12: 88 of a Short's 372 views were attributed), so `india_share` is a lower bound."""
    totals = (list((_rows(yta, video_id, start, end, _TOTALS) or [[]])[0]) + [0] * 5)[:5]
    views, engaged, avg_seconds, avg_pct, subs = (x or 0 for x in totals)
    countries = {r[0]: int(r[1]) for r in _rows(yta, video_id, start, end, "views", "country",
                                               sort="-views", maxResults=10)}
    traffic = {r[0]: int(r[1]) for r in _rows(yta, video_id, start, end, "views",
                                             "insightTrafficSourceType")}
    try:
        retention = [[float(r[0]), float(r[1])] for r in
                     _rows(yta, video_id, start, end, "audienceWatchRatio", "elapsedVideoTimeRatio")]
    except Exception as e:  # noqa: BLE001 — the curve is the most likely report to be refused
        log.warning("analytics: no retention curve for %s (%s)", video_id, e)
        retention = None
    views = int(views)
    return {"views": views, "engaged_views": int(engaged), "avg_view_seconds": float(avg_seconds),
            "avg_view_pct": float(avg_pct), "subscribers_gained": int(subs),
            "india_share": round(countries.get("IN", 0) / views, 4) if views else None,
            "countries": countries, "traffic": traffic, "retention": retention}


def collect_metrics(min_age_days: int = 9, limit: int = 120) -> int:
    """Pull the first-week window for every Short old enough to have it (7 days, plus 2 of
    reporting lag) and not measured yet. The first runs backfill the old Shorts: that is the
    baseline the relaunch is judged against. At most `limit` posts a run. Returns posts measured."""
    posts = db.posts_needing_metrics(min_age_days=min_age_days)[:limit]
    if not posts:
        log.info("analytics: no Shorts waiting for metrics.")
        return 0
    yta = _analytics_client()
    measured = 0
    for post in posts:
        published = db._parse_time(post.get("published_at"))
        if not published or not post.get("external_id"):
            continue
        start = published.date()
        try:
            metrics = _video_metrics(yta, post["external_id"], start,
                                     start + timedelta(days=_WINDOW_DAYS - 1))
        except Exception as e:  # noqa: BLE001 — one video never stops the rest
            log.warning("analytics: metrics failed for %s (%s)", post.get("external_id"), e)
            continue
        db.upsert_post_metrics(post["id"], _WINDOW_DAYS, metrics)
        measured += 1
    log.info("analytics: measured %d Short(s) from the Analytics API.", measured)
    return measured


if __name__ == "__main__":
    import logging as _l
    _l.basicConfig(level=_l.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    collect_stats()
    try:  # never at the cost of the view snapshots, which are already stored (rule 14)
        collect_metrics()
    except Exception as e:  # noqa: BLE001
        log.warning("analytics: the metrics pull failed (%s)", e)
