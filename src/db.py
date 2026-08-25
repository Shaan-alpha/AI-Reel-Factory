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
                  hashtags: list[str], title: str | None = None) -> int:
    """Persist a generated script; return its id.

    `title` is the punchy PUBLISHED YouTube title — stored so the analytics loop can learn
    which title STYLE wins (the dry idea title is a poor proxy; the published one is what
    viewers actually saw and tapped). Optional for back-compat with older callers/tests.
    """
    row = {"idea_id": idea_id, "template": template, "body": body,
           "caption": caption, "hashtags": hashtags}
    if title:
        row["title"] = title
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
    """Best-viewed Shorts as "PUBLISHED TITLE — N views" (analytics → posts → scripts → ideas).

    Returns the PUBLISHED YouTube title (the punchy one viewers tapped) with its view count,
    so ideation learns the winning *style*, not just the topic. Falls back to the idea title
    for older rows that pre-date title persistence. Feeds the ideation prompt. [] if no data.

    `analytics` is a TIME SERIES — `collect_stats()` appends one snapshot per published post on
    every run — so ranking raw snapshot rows ranks *snapshots*, not videos: one breakout Short's
    own daily history occupies slot after slot, and the window runs dry before it has seen
    `limit` DISTINCT videos. It also decays as the channel ages, because each extra day adds
    another snapshot per post while the window stays fixed. Measured on the live DB 2026-08-25:
    72 posts / 3,454 snapshots, the top-24 window covered **3 distinct videos**, so ideation was
    handed 3 winners after asking for 6.

    So: collapse to ONE row per post FIRST — its newest snapshot, which for a monotonically
    rising view count is also its highest — and only then rank.
    """
    client = get_client()
    # A full collect_stats() pass writes one row per published post, so the newest
    # (published posts × 3) rows contain every post's latest snapshot with room to spare
    # even if a pass or two was partial (rule 14: one bad row never stops the pull).
    n_posts = (
        client.table("posts").select("id", count="exact")
        .eq("platform", "youtube").not_.is_("external_id", "null").limit(1).execute().count
    ) or 0
    if not n_posts:
        return []
    rows = (
        client.table("analytics")
        .select("post_id, views, posts(scripts(title, ideas(title)))")
        .order("id", desc=True).limit(max(n_posts * 3, limit * 4)).execute().data
    )

    latest: dict = {}
    for r in rows:  # newest-first, so the FIRST row seen for a post is its current standing
        pid = r.get("post_id")
        if pid is not None and pid not in latest:
            latest[pid] = r

    out: list[str] = []
    seen: set[str] = set()
    for r in sorted(latest.values(), key=lambda x: int(x.get("views") or 0), reverse=True):
        try:
            script = r["posts"]["scripts"]
            title = (script.get("title") or "").strip() or script["ideas"]["title"]
            views = int(r.get("views") or 0)
        except (TypeError, KeyError):
            continue
        if title and title.lower() not in seen:
            seen.add(title.lower())
            out.append(f'"{title}" — {views:,} views')
        if len(out) >= limit:
            break
    return out


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
