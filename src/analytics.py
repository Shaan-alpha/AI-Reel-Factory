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


def _fetch_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Return {video_id: {views, likes, comments}} via videos.list (batched 50/call)."""
    out: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = youtube.videos().list(part="statistics", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            s = item.get("statistics", {})
            out[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)) if "likeCount" in s else None,
                "comments": int(s.get("commentCount", 0)) if "commentCount" in s else None,
            }
    return out


def collect_stats() -> int:
    """Snapshot stats for every published Short into the analytics table. Returns #recorded."""
    posts = db.get_published_posts("youtube")
    by_vid = {p["external_id"]: p for p in posts if p.get("external_id")}
    if not by_vid:
        log.info("analytics: no published posts yet.")
        return 0

    stats = _fetch_stats(_youtube_client(), list(by_vid))
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
    log.info("analytics: recorded %d snapshots.", recorded)
    return recorded


if __name__ == "__main__":
    import logging as _l
    _l.basicConfig(level=_l.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    collect_stats()
