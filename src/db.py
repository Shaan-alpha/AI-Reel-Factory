"""Database layer — Supabase Postgres client + typed helpers.

Contract:
    what it does : the only module that talks to Supabase; all state goes through here.
    how to use   : import the helpers below; pass/return plain dicts (typed rows).
    depends on   : supabase-py, src.config (SUPABASE_URL, SUPABASE_KEY = sb_secret_ key).

Tables (see docs/03-setup-guide.md §4): ideas, scripts, posts, analytics, hook_performance.
RLS is enabled on every table; this layer authenticates with the server-side **secret** key
(`sb_secret_…`), which bypasses RLS. Never use the publishable key here. Never store video
here — only rows/metadata (rule 15).
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from src import config

# Allowed idea lifecycle states. 'produced' marks an approved idea whose reel has shipped,
# so a cron retry skips it (rule 12: idempotent reruns).
IDEA_STATUSES = ("pending", "approved", "rejected", "produced")


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Create (once) and return the Supabase client. Fails loud if creds missing (rule 14)."""
    return create_client(config.require("SUPABASE_URL"), config.require("SUPABASE_KEY"))


# --- ideas ----------------------------------------------------------------------------

def insert_ideas(ideas: list[dict]) -> list[dict]:
    """Insert ideation rows (status defaults to 'pending'). Returns the inserted rows."""
    if not ideas:
        return []
    return get_client().table("ideas").insert(ideas).execute().data


def get_pending_ideas() -> list[dict]:
    """Today's pending ideas for the Telegram digest, best-scored first."""
    return (
        get_client().table("ideas").select("*")
        .eq("status", "pending").order("est_score", desc=True).execute().data
    )


def set_idea_status(idea_id: int, status: str) -> None:
    """Set an idea's status. Valid: pending | approved | rejected | produced."""
    if status not in IDEA_STATUSES:
        raise ValueError(f"invalid idea status: {status!r} (allowed: {IDEA_STATUSES})")
    get_client().table("ideas").update({"status": status}).eq("id", idea_id).execute()


def get_approved_ideas() -> list[dict]:
    """Approved, not-yet-produced ideas — the production queue (best-scored first)."""
    return (
        get_client().table("ideas").select("*")
        .eq("status", "approved").order("est_score", desc=True).execute().data
    )


# --- scripts / posts ------------------------------------------------------------------

def insert_script(idea_id: int, template: str, body: str, caption: str,
                  hashtags: list[str]) -> int:
    """Persist a generated script; return its id."""
    row = {"idea_id": idea_id, "template": template, "body": body,
           "caption": caption, "hashtags": hashtags}
    return get_client().table("scripts").insert(row).execute().data[0]["id"]


def insert_post(script_id: int, platform: str, external_id: str, url: str,
                status: str) -> int:
    """Record a published/queued output; return its id."""
    row = {"script_id": script_id, "platform": platform,
           "external_id": external_id, "url": url, "status": status}
    return get_client().table("posts").insert(row).execute().data[0]["id"]


def find_post(script_id: int, platform: str) -> dict | None:
    """Return an existing post for (script_id, platform), or None.

    Used for the idempotency check before publishing so a cron retry never
    double-publishes the same reel (rule 12).
    """
    rows = (
        get_client().table("posts").select("*")
        .eq("script_id", script_id).eq("platform", platform).limit(1).execute().data
    )
    return rows[0] if rows else None
