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

from datetime import datetime, timedelta, timezone
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


def expire_stale_pending_ideas(max_age_hours: int | None = None) -> int:
    """Mark pending ideas older than `max_age_hours` as 'passed'. Returns how many. 0 = disabled.

    `make_on_demand` PREFERS whatever is already pending, and `_release_failed_idea` puts a reel
    that died mid-chain back to 'pending'. Nothing ever aged those out, so a story from two days
    ago could be re-proposed as today's digest — on a channel whose entire premise is "today".
    'passed' rather than 'rejected': it was never judged bad, it just went cold, and the
    distinction is what keeps `rejected` meaningful as a signal (IDEA_STATUSES).

    Set IDEA_MAX_AGE_HOURS=0 to switch it off.
    """
    if max_age_hours is None:
        try:
            max_age_hours = int(config.get("IDEA_MAX_AGE_HOURS", "24"))
        except (TypeError, ValueError):
            max_age_hours = 24
    if max_age_hours <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    rows = (
        get_client().table("ideas").update({"status": "passed"})
        .eq("status", "pending").lt("created_at", cutoff).execute().data
    )
    return len(rows or [])


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
    """Record a published/queued output; return its id.

    `published_at` is stamped HERE. The column has no database default, and nothing else ever
    set it, so all 75 live rows carried NULL — which silently broke the operator's only
    dashboard: the Telegram bot's /today filters `published_at=gte.<IST midnight>` (a NULL
    matches no range, so it always answered "0 Shorts today") and /latest orders by it.
    Timezone-aware UTC, because the bot compares against an IST-midnight boundary.
    """
    row = {"script_id": script_id, "platform": platform,
           "external_id": external_id, "url": url, "status": status,
           "published_at": datetime.now(timezone.utc).isoformat()}
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


def prune_analytics(keep_per_post: int | None = None) -> int:
    """Keep only the newest `keep_per_post` snapshots per post. Returns rows deleted.

    OPT-IN and off by default: `analytics` is a time series and deleting it destroys the history
    `top_performing_titles` learns from. Measured on the live DB 2026-09-03 — 4,049 rows for 76
    posts, growing ~76/day — which is nowhere near Supabase's 500 MB ceiling (rule 13), so this
    exists as a lever for later rather than a default that quietly bins data. Set
    ANALYTICS_KEEP_PER_POST to switch it on.
    """
    if keep_per_post is None:
        raw = (config.get("ANALYTICS_KEEP_PER_POST") or "").strip()
        if not raw:
            return 0
        try:
            keep_per_post = int(raw)
        except ValueError:
            return 0
    if keep_per_post < 1:
        return 0

    client = get_client()
    rows = client.table("analytics").select("id, post_id").order("id", desc=True).execute().data
    seen: dict = {}
    doomed: list[int] = []
    for r in rows:  # newest first, so anything past the keep-window for its post is surplus
        pid = r.get("post_id")
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > keep_per_post:
            doomed.append(r["id"])
    for i in range(0, len(doomed), 200):  # chunked: a huge `in_` filter blows the URL length
        client.table("analytics").delete().in_("id", doomed[i : i + 200]).execute()
    return len(doomed)


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
