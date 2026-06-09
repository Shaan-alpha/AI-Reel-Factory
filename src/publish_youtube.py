"""Module 9 — Publish to YouTube.

Contract:
    what it does : uploads the final reel via YouTube Data API v3 and records the result.
    input        : video_path, metadata {title, description, tags, ...}, script_id.
    output       : (video_id, url) — also written to the posts table; local file deleted.
    depends on   : google-api-python-client, google-auth(-oauthlib), src.db, src.config.

AI DISCLOSURE (docs/08 §2): sets `status.containsSyntheticMedia` (the official "altered or
synthetic content" flag, settable via the Data API since 2024-10) when AI_DISCLOSURE=true,
plus a disclosure line in the description (added by the scriptwriter). Appends #Shorts so
YouTube classifies the upload as a Short. ASSET POLICY (rule 15): delete the local .mp4 after
a successful upload. IDEMPOTENT (rule 12): check `posts` before uploading so a cron retry
never double-publishes. QUOTA (rule 13): videos.insert costs ~1600 units; the default 10k/day
quota allows ~6 uploads — fine for 4-5 Shorts/day, but don't add other heavy calls.
"""
from __future__ import annotations

import logging
import os

from src import config, db

log = logging.getLogger(__name__)

_PLATFORM = "youtube"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _youtube_client():
    """Build an authenticated YouTube Data API client from the .env refresh token."""
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


def _cap_tags(tags: list[str], limit: int = 480) -> list[str]:
    """Keep tags within YouTube's ~500-char total budget (quotes count); preserve order."""
    out, used = [], 0
    for t in tags:
        cost = len(t) + (3 if " " in t else 1)  # quoted tags with spaces cost extra
        if used + cost > limit:
            break
        out.append(t)
        used += cost
    return out


def _build_body(metadata: dict) -> dict:
    """Map pipeline metadata → a videos.insert request body. Enforces #Shorts + disclosure."""
    title = (metadata.get("title") or "").replace("<", "").replace(">", "").strip()[:100]
    if not title:
        raise ValueError("publish: metadata['title'] is required.")

    desc = metadata.get("description") or ""
    if "#shorts" not in desc.lower():
        desc = (desc.rstrip() + "\n\n#Shorts").strip()

    tags = [str(t).lstrip("#").strip() for t in (metadata.get("tags") or []) if str(t).strip()]
    tags = _cap_tags(tags)  # YouTube allows ~500 chars of tags total
    category = str(metadata.get("category_id") or config.get("YOUTUBE_CATEGORY_ID", "25"))
    privacy = metadata.get("privacy") or config.get("YOUTUBE_PRIVACY", "public")
    disclose = str(config.get("AI_DISCLOSURE", "true")).lower() == "true"

    return {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": category},
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": disclose,  # AI-disclosure flag (docs/08 §2)
        },
    }


def _upload(youtube, body: dict, video_path: str) -> dict:
    """Resumable upload of the reel; returns the inserted video resource."""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response


def publish(video_path: str, metadata: dict, script_id: int) -> tuple[str, str]:
    """Upload the reel, set disclosure, record the post, delete the local file. Return (id, url)."""
    if not os.path.exists(video_path):
        raise ValueError(f"publish: video not found: {video_path}")

    # Idempotency (rule 12): if this script already has a YouTube post, don't re-upload.
    existing = db.find_post(script_id, _PLATFORM)
    if existing and existing.get("external_id"):
        log.info("publish: script %s already on YouTube (%s); skipping upload",
                 script_id, existing["external_id"])
        return existing["external_id"], existing.get("url") or ""

    body = _build_body(metadata)
    log.info("publish: uploading %s (privacy=%s, synthetic=%s)",
             video_path, body["status"]["privacyStatus"], body["status"]["containsSyntheticMedia"])
    response = _upload(_youtube_client(), body, video_path)

    video_id = response["id"]
    url = f"https://www.youtube.com/shorts/{video_id}"
    db.insert_post(script_id, _PLATFORM, video_id, url, "published")

    # Asset policy (rule 15): the upload is the source of truth now — drop the local render.
    try:
        os.remove(video_path)
    except OSError as e:
        log.warning("publish: uploaded but could not delete %s (%s)", video_path, e)

    log.info("publish: live → %s", url)
    return video_id, url
