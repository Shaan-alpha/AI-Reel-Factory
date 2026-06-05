"""Integration tests for src.db against the live Supabase project.

Skips automatically when SUPABASE creds are absent (e.g. CI without secrets), so the
default `pytest` run stays green. With `.env` present, runs a full CRUD cycle and cleans
up after itself. Run: `pytest` (this module self-skips when creds are absent).
"""
import os

import pytest

# Importing src.db loads .env via src.config, so creds are populated before this check.
from src import db

pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")),
    reason="needs live Supabase creds (.env / Actions secrets)",
)

_MARK = "__pytest_dbtest__"


def test_full_idea_to_post_cycle():
    client = db.get_client()
    inserted = db.insert_ideas([{
        "niche": "impact-news", "title": _MARK, "hook": "h", "angle": "a",
        "est_score": 0.9, "sources": ["https://example.com/a", "https://example.com/b"],
    }])
    assert inserted and inserted[0]["status"] == "pending"
    idea_id = inserted[0]["id"]
    script_id = None
    try:
        # pending -> appears in digest queue
        assert any(r["id"] == idea_id for r in db.get_pending_ideas())

        # approve -> appears in production queue
        db.set_idea_status(idea_id, "approved")
        assert any(r["id"] == idea_id for r in db.get_approved_ideas())

        # script + post
        script_id = db.insert_script(idea_id, "N", "body text", "caption", ["#Shorts"])
        assert isinstance(script_id, int)
        post_id = db.insert_post(script_id, "youtube", "vid_xyz", "https://youtu.be/xyz",
                                 "published")
        assert isinstance(post_id, int)

        # idempotency helper finds it
        found = db.find_post(script_id, "youtube")
        assert found and found["external_id"] == "vid_xyz"

        # produced -> drops out of the approved queue
        db.set_idea_status(idea_id, "produced")
        assert all(r["id"] != idea_id for r in db.get_approved_ideas())
    finally:
        # clean up in FK order: posts -> scripts -> ideas
        if script_id is not None:
            client.table("posts").delete().eq("script_id", script_id).execute()
            client.table("scripts").delete().eq("id", script_id).execute()
        client.table("ideas").delete().eq("id", idea_id).execute()


def test_set_idea_status_rejects_unknown():
    with pytest.raises(ValueError):
        db.set_idea_status(1, "bogus")
