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
import re

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


def preflight() -> None:
    """Prove the refresh token still works and may upload, BEFORE the digest and the render.

    A revoked or expired token used to surface only at the upload: after the operator's taps,
    the fact-check and the full render had all been spent. A refresh costs no quota. A token the
    server rejects is a misconfiguration and stops the run (rule 14: fail loud); a network blip
    here is only logged, so it cannot cost a run on its own."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials(  # no scopes: report what the token really carries
        token=None,
        refresh_token=config.require("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.require("YOUTUBE_CLIENT_ID"),
        client_secret=config.require("YOUTUBE_CLIENT_SECRET"),
    )
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise RuntimeError(f"publish: the YouTube token was refused ({e}). Re-run "
                           "tools/get_youtube_token.py and update the YOUTUBE_REFRESH_TOKEN "
                           "secret.") from e
    except Exception as e:  # noqa: BLE001 — a transport blip is not a verdict on the token
        log.warning("publish: YouTube pre-flight could not reach Google (%s); continuing.", e)
        return
    granted = set(getattr(creds, "granted_scopes", None) or [])
    if granted and _SCOPES[0] not in granted:
        raise RuntimeError("publish: the YouTube token has no upload scope. Re-run "
                           "tools/get_youtube_token.py and update the YOUTUBE_REFRESH_TOKEN "
                           "secret.")


def _clean_tag(tag: str) -> str:
    """A tag YouTube accepts: no '<', '>' or comma (each is an invalidTags error), no '#'."""
    return re.sub(r"[<>,]", " ", str(tag)).lstrip("#").strip()


_DESC_BYTES = 5000


def _clean_description(desc: str) -> str:
    """A description YouTube accepts: no '<' or '>' (invalidDescription) and at most 5,000
    BYTES, which ₹ and emoji reach sooner than 5,000 characters. When it must shorten, it cuts
    the body and keeps the closing lines whole (disclosure, footer, #Shorts)."""
    desc = desc.replace("<", "‹").replace(">", "›")
    if len(desc.encode("utf-8")) <= _DESC_BYTES:
        return desc
    split = max(0, len(desc) - 1200)
    split = desc.rfind("\n", 0, split + 1) if "\n" in desc[:split + 1] else split
    head, tail = desc[:split], desc[split:]
    budget = _DESC_BYTES - len(tail.encode("utf-8"))
    head = head.encode("utf-8")[:max(0, budget)].decode("utf-8", "ignore").rstrip()
    return (head + tail).encode("utf-8")[:_DESC_BYTES].decode("utf-8", "ignore")


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
    desc = _clean_description(desc)

    tags = [_clean_tag(t) for t in (metadata.get("tags") or [])]
    tags = [t for t in tags if t]
    tags = _cap_tags(tags)  # YouTube allows ~500 chars of tags total
    category = str(metadata.get("category_id") or config.get("YOUTUBE_CATEGORY_ID", "25"))
    privacy = metadata.get("privacy") or config.get("YOUTUBE_PRIVACY", "public")
    disclose = config.get_bool("AI_DISCLOSURE", True)

    return {
        # Language set explicitly: left to detection, 79 of 88 videos had none and one English
        # reel (59Mmuej_mes) was tagged Hindi.
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": category,
                    "defaultLanguage": config.get("YOUTUBE_LANGUAGE", "en"),
                    "defaultAudioLanguage": config.get("YOUTUBE_LANGUAGE", "en")},
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": disclose,  # AI-disclosure flag (docs/08 §2)
        },
    }


def _upload(youtube, body: dict, video_path: str) -> dict:
    """Resumable upload of the reel; returns the inserted video resource."""
    from googleapiclient.http import MediaFileUpload

    import http.client
    import random
    import time

    import httplib2
    from google.auth.exceptions import TransportError
    from googleapiclient.errors import HttpError

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response, failures = None, 0
    # A resumable upload can pick up where it stopped, so a 5xx or a dropped socket costs one
    # chunk, not the reel. Without this, one blip threw away the voice, render and fact-check
    # already spent on it.
    while response is None:
        try:
            _status, response = request.next_chunk()
        # OSError covers ConnectionError, socket timeouts and ssl.SSLError (an SSLEOFError on a
        # chunk used to lose the reel); httplib2 and http.client raise their own protocol errors.
        # A RefreshError is not a TransportError, so a dead token still fails at once.
        except (HttpError, OSError, httplib2.HttpLib2Error, http.client.HTTPException,
                TransportError) as e:
            code = getattr(getattr(e, "resp", None), "status", None)
            if isinstance(e, HttpError) and code not in (500, 502, 503, 504):
                if code == 403 and "quota" in str(e).lower():
                    raise RuntimeError(f"publish: YouTube upload quota exhausted ({e})") from e
                raise
            failures += 1
            if failures > 5:
                raise
            wait = min(60.0, 2 ** failures) + random.random()
            log.warning("publish: upload interrupted (%s); retry %d/5 in %.0fs",
                        str(e)[:160], failures, wait)
            time.sleep(wait)
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
    # The upload is IRREVERSIBLE; the row is not. If this insert raises and we let it propagate,
    # produce_one never marks the idea 'produced', the idea returns to the queue, and the next
    # run uploads the same reel again — because BOTH idempotency guards (find_post and
    # get_published_post_for_idea) key off the row that was never written. A missing analytics
    # row is far cheaper than a duplicate public video, so swallow it and shout (rule 14).
    try:
        db.insert_post(script_id, _PLATFORM, video_id, url, "published",
                       voice=metadata.get("voice"))
    except Exception as e:  # noqa: BLE001 — never turn a recorded upload into a repeated one
        log.error("publish: video %s IS LIVE at %s but its post row could not be written (%s). "
                  "Reconcile manually — analytics will miss it, and the idempotency guard for "
                  "script %s is now blind.", video_id, url, e, script_id)
        try:  # a log line nobody reads was the only trace; the operator reads Telegram
            from src import approval

            approval._api("sendMessage", chat_id=config.require("TELEGRAM_CHAT_ID"),
                          text=f"⚠️ {url} is live, but its posts row (script {script_id}) could "
                               f"not be saved. Add it by hand, and don't approve the idea again.")
        except Exception:  # noqa: BLE001
            log.warning("publish: the missing-row alert could not be sent either.")

    # Asset policy (rule 15): the upload is the source of truth now — drop the local render.
    try:
        os.remove(video_path)
    except OSError as e:
        log.warning("publish: uploaded but could not delete %s (%s)", video_path, e)

    log.info("publish: live → %s", url)
    return video_id, url
