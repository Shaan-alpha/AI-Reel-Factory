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
# so a cron retry skips it (rule 12: idempotent reruns). 'passed' is a soft skip from the
# Telegram digest — not posted, but distinct from a hard 'rejected'.
IDEA_STATUSES = ("pending", "approved", "rejected", "passed", "produced")


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


def existing_idea_titles() -> set[str]:
    """Lowercased titles of every idea already in the table (any status) — for dedup."""
    rows = get_client().table("ideas").select("title").execute().data
    return {r["title"].lower() for r in rows if r.get("title")}


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


def get_published_posts(platform: str = "youtube") -> list[dict]:
    """Posts that actually shipped (have an external_id) — the analytics targets."""
    return (
        get_client().table("posts").select("*")
        .eq("platform", platform).not_.is_("external_id", "null").execute().data
    )


def insert_analytics(post_id: int, views: int, likes: int | None = None,
                     comments: int | None = None) -> None:
    """Record a metrics snapshot for a post (analytics table; pulled_at defaults to now())."""
    get_client().table("analytics").insert(
        {"post_id": post_id, "views": views, "likes": likes, "comments": comments}
    ).execute()


def top_performing_titles(limit: int = 8) -> list[str]:
    """Idea titles of the best-viewed Shorts (analytics → posts → scripts → ideas).

    Feeds the ideation prompt so it makes fresh variants of what's working. [] if no data.
    """
    rows = (
        get_client().table("analytics")
        .select("views, posts(scripts(ideas(title)))")
        .order("views", desc=True).limit(limit * 4).execute().data
    )
    titles: list[str] = []
    seen: set[str] = set()
    for r in rows:
        try:
            title = r["posts"]["scripts"]["ideas"]["title"]
        except (TypeError, KeyError):
            continue
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def get_published_post_for_idea(idea_id: int, platform: str = "youtube") -> dict | None:
    """Return an existing published post for this idea (via its scripts), or None.

    Idea-level idempotency (rule 12): produce_one checks this BEFORE writing a new script, so a
    retry after a post-publish hiccup can't double-upload (scripts get a fresh id each run, so a
    script-id check alone would miss it)."""
    scripts = get_client().table("scripts").select("id").eq("idea_id", idea_id).execute().data
    sids = [s["id"] for s in scripts]
    if not sids:
        return None
    rows = (
        get_client().table("posts").select("*")
        .in_("script_id", sids).eq("platform", platform)
        .not_.is_("external_id", "null").limit(1).execute().data
    )
    return rows[0] if rows else None


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
