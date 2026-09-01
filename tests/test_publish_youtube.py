"""Tests for the publish_youtube module (Module 9).

All mocked — no real upload. They verify body construction (disclosure flag, #Shorts, title
limit), idempotency, the record→delete flow, and input validation. A real upload to the live
channel is intentionally NOT done here; a guarded manual smoke test lives at the bottom and is
skipped unless YOUTUBE_LIVE_UPLOAD_TEST=1 is explicitly set.
"""
from __future__ import annotations

import os

import pytest

from src import publish_youtube as pub


# --- body construction -----------------------------------------------------------------

def test_cap_tags_stays_within_budget():
    many = [f"tag number {i}" for i in range(100)]
    capped = pub._cap_tags(many, limit=100)
    assert capped == many[: len(capped)] and len(capped) < len(many)


def test_build_body_sets_disclosure_and_shorts(monkeypatch):
    monkeypatch.setenv("AI_DISCLOSURE", "true")
    body = pub._build_body({
        "title": "ISRO reusable rocket, explained — why it matters",
        "description": "Cheaper launches. Sources: https://x.com",
        "tags": ["#ISRO", "space", "#Shorts"],
    })
    assert body["status"]["containsSyntheticMedia"] is True
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert "#Shorts" in body["snippet"]["description"]
    assert body["snippet"]["tags"] == ["ISRO", "space", "Shorts"]  # '#' stripped
    assert body["snippet"]["categoryId"] == "25"


def test_build_body_disclosure_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI_DISCLOSURE", "false")
    body = pub._build_body({"title": "t", "description": "d #Shorts"})
    assert body["status"]["containsSyntheticMedia"] is False
    # already has #Shorts → not duplicated
    assert body["snippet"]["description"].count("#Shorts") == 1


def test_build_body_truncates_title_and_requires_it():
    long = "x" * 130
    assert len(pub._build_body({"title": long})["snippet"]["title"]) == 100
    with pytest.raises(ValueError, match="title.* required"):
        pub._build_body({"title": "   "})


def test_build_body_privacy_default_and_override(monkeypatch):
    monkeypatch.delenv("YOUTUBE_PRIVACY", raising=False)
    assert pub._build_body({"title": "t"})["status"]["privacyStatus"] == "public"
    assert pub._build_body({"title": "t", "privacy": "private"})["status"]["privacyStatus"] == "private"


# --- publish flow ----------------------------------------------------------------------

def test_publish_idempotent_skips_upload(monkeypatch, tmp_path):
    video = tmp_path / "reel.mp4"; video.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(pub.db, "find_post",
                        lambda sid, plat: {"external_id": "vid123", "url": "https://youtu.be/vid123"})

    def _boom(*a, **k):
        raise AssertionError("should not upload when already published")
    monkeypatch.setattr(pub, "_youtube_client", _boom)
    monkeypatch.setattr(pub, "_upload", _boom)

    vid, url = pub.publish(str(video), {"title": "t"}, script_id=5)
    assert vid == "vid123" and url == "https://youtu.be/vid123"
    assert os.path.exists(video)  # not deleted on a skip


def test_publish_uploads_records_and_deletes(monkeypatch, tmp_path):
    video = tmp_path / "reel.mp4"; video.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(pub.db, "find_post", lambda sid, plat: None)
    monkeypatch.setattr(pub, "_youtube_client", lambda: object())
    monkeypatch.setattr(pub, "_upload", lambda yt, body, path: {"id": "NEWID"})

    recorded = {}
    monkeypatch.setattr(pub.db, "insert_post",
                        lambda sid, plat, ext, url, status: recorded.update(
                            sid=sid, plat=plat, ext=ext, url=url, status=status) or 1)

    vid, url = pub.publish(str(video), {"title": "My Short", "description": "d"}, script_id=9)
    assert vid == "NEWID"
    assert url == "https://www.youtube.com/shorts/NEWID"
    assert recorded == {"sid": 9, "plat": "youtube", "ext": "NEWID", "url": url, "status": "published"}
    assert not os.path.exists(video)  # local render deleted (rule 15)


def test_publish_missing_video_raises(tmp_path):
    with pytest.raises(ValueError, match="video not found"):
        pub.publish(str(tmp_path / "ghost.mp4"), {"title": "t"}, script_id=1)


# --- guarded live smoke test (off by default) ------------------------------------------

@pytest.mark.skipif(os.environ.get("YOUTUBE_LIVE_UPLOAD_TEST") != "1",
                    reason="set YOUTUBE_LIVE_UPLOAD_TEST=1 to upload a real PRIVATE test Short")
def test_live_private_upload(tmp_path):
    from src import assembly, visuals, voice
    audio, dur = voice.synthesize("This is a private upload test for But It Matters.", str(tmp_path))
    clips = visuals.fetch_broll(["abstract", "technology"], target_seconds=dur, out_dir=str(tmp_path))
    reel = assembly.assemble(audio, clips, str(tmp_path / "reel.mp4"))
    vid, url = pub.publish(reel, {
        "title": "But It Matters — API upload test (private)",
        "description": "Automated test upload.\nNarration is AI-generated; visuals are stock.",
        "tags": ["test"], "privacy": "private",
    }, script_id=-1)
    assert vid and url.startswith("https://www.youtube.com/shorts/")


def test_publish_survives_a_failed_post_insert(monkeypatch, tmp_path, caplog):
    """A DB hiccup AFTER the upload must not cost us a duplicate public video.

    The upload is irreversible; the row is not. If insert_post raises, the old behaviour
    propagated it out of publish() -> produce_one never ran set_idea_status("produced") ->
    the idea went back into the queue -> the next run uploaded the SAME reel again, because
    the idempotency guards (find_post / get_published_post_for_idea) both key off the row that
    was never written. Losing an analytics row is much cheaper than publishing a duplicate, so
    the id is returned and the failure is logged loudly for reconciliation.
    """
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(pub.db, "find_post", lambda sid, plat: None)
    monkeypatch.setattr(pub, "_youtube_client", lambda: object())
    monkeypatch.setattr(pub, "_upload", lambda yt, body, path: {"id": "NEWID"})

    def _db_down(*a, **k):
        raise RuntimeError("supabase unreachable")
    monkeypatch.setattr(pub.db, "insert_post", _db_down)

    with caplog.at_level("ERROR"):
        video_id, url = pub.publish(str(video), {"title": "t", "description": "d", "tags": []}, 1)

    assert video_id == "NEWID" and url.endswith("NEWID")
    assert any("NEWID" in r.getMessage() for r in caplog.records), \
        "the orphaned video id must be logged for reconciliation"
