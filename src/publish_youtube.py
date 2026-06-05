"""Module 9 — Publish to YouTube.

Contract:
    what it does : uploads the final reel via YouTube Data API v3 and records the result.
    input        : video_path, metadata {title, description, tags, ...}, script_id.
    output       : (video_id, url) — also written to the posts table; local file deleted.
    depends on   : google-api-python-client, google-auth(-oauthlib), src.db, src.config.

AI DISCLOSURE (docs/08 §2): set the altered/synthetic-content flag (AI_DISCLOSURE) + a
disclosure line in the description. Append #Shorts to title. ASSET POLICY (rule 15): delete
the local .mp4 after a successful upload. IDEMPOTENT (rule 12): check posts before uploading
so a cron retry never double-publishes. Respect the ~100 uploads/day quota (rule 13).

STATUS: stub.
"""
from __future__ import annotations


def publish(video_path: str, metadata: dict, script_id: int) -> tuple[str, str]:
    """Upload the reel, set disclosure, record the post, delete the local file. Return (id, url)."""
    raise NotImplementedError("publish_youtube.publish — see docs/02-implementation-plan.md §9")
