"""Database layer — Supabase Postgres client + typed helpers.

Contract:
    what it does : the only module that talks to Supabase; all state goes through here.
    how to use   : import the helpers below; pass/return plain dicts (typed rows).
    depends on   : supabase-py, src.config (SUPABASE_URL, SUPABASE_KEY).

Tables (see docs/03-setup-guide.md §4): ideas, scripts, posts, analytics, hook_performance.
Asset policy (rule 15): never store video here — only rows/metadata.

STATUS: stub. Build first (docs/02-implementation-plan.md §1) and test against Supabase
before any module that depends on it.
"""
from __future__ import annotations


def insert_ideas(ideas: list[dict]) -> None:
    """Insert ideation output rows (status='pending'). Idempotent per day (rule 12)."""
    raise NotImplementedError("db.insert_ideas — see docs/02-implementation-plan.md §1")


def get_pending_ideas() -> list[dict]:
    """Return today's ideas with status='pending' (for the Telegram digest)."""
    raise NotImplementedError("db.get_pending_ideas — see docs/02-implementation-plan.md §1")


def set_idea_status(idea_id: int, status: str) -> None:
    """Set an idea's status to 'approved' | 'rejected'."""
    raise NotImplementedError("db.set_idea_status — see docs/02-implementation-plan.md §1")


def get_approved_ideas() -> list[dict]:
    """Return approved-but-not-yet-produced ideas (the production queue)."""
    raise NotImplementedError("db.get_approved_ideas — see docs/02-implementation-plan.md §1")


def insert_script(idea_id: int, template: str, body: str, caption: str, hashtags: list[str]) -> int:
    """Persist a generated script; return its id."""
    raise NotImplementedError("db.insert_script — see docs/02-implementation-plan.md §1")


def insert_post(script_id: int, platform: str, external_id: str, url: str, status: str) -> int:
    """Record a published/queued output; return its id. Check before insert (rule 12)."""
    raise NotImplementedError("db.insert_post — see docs/02-implementation-plan.md §1")
