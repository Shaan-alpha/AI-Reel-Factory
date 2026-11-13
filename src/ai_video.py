"""AI-video shots: FLUX stills animated by Kling on Higgsfield (design Part A).

Stage 3a holds the money's bookkeeping; stage 3b adds one reel's shots (sizing, the shot planner,
stills, buying, waiting, settling).

Contract:
    sweep()           -> {"settled", "left", "errors"} counts. Settles the Higgsfield jobs that
                         earlier runs left open. Never raises.
    spend_line(since) -> the run's Higgsfield spend for Telegram, read from the ledger, or None.
    depends on        : src.db (the ai_video_jobs ledger), src.higgsfield (free status calls).

Higgsfield has no spend cap in code, by the operator's choice (2026-11-10): every job is reserved
in the ledger before it is bought, and every dollar is reported. These lines are that report.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src import config, db, higgsfield

log = logging.getLogger(__name__)

_NOT_CHARGED = frozenset({"failed", "nsfw", "canceled"})
# Paid and not on screen: a job that finished after its reel moved on (late), or whose submit
# never answered (reserved, counted at its quote because it may have been charged).
_PAID_UNUSED = frozenset({"late", "reserved", "submitted"})


def _have_key() -> bool:
    return bool((config.get("HF_API_KEY") or "").strip())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settlement(state: dict) -> dict | None:
    """The ledger fields for a job Higgsfield reports as finished; None while it still runs."""
    status = state.get("status")
    if status == "completed":
        return {"status": "completed", "result_url": (state.get("video") or {}).get("url"),
                "settled_at": _now()}
    if status in _NOT_CHARGED:
        return {"status": status, "cost_usd": 0, "settled_at": _now()}
    return None


def sweep() -> dict:
    """Settle the jobs earlier runs left open (design 6.7).

    Every `submitted` or `late` row under 7 days old is re-read: `completed` gets its URL (it was
    paid for, so it keeps its cost, and a later reel of the same idea may reuse the clip), and
    `failed`, `nsfw` or `canceled` cost 0. A job still running, or one whose status call fails,
    is left for the next sweep. Status calls are free. Runs only when HF_API_KEY is set, and is
    bookkeeping: it never raises."""
    counts = {"settled": 0, "left": 0, "errors": 0}
    if not _have_key():
        return counts
    try:
        rows = db.open_ai_video_jobs()
    except Exception as e:  # noqa: BLE001 — LedgerUnavailable included; the run goes on
        log.warning("ai_video: no sweep, the ledger could not be read (%s)", e)
        return counts
    for done, row in enumerate(rows):
        if not row.get("request_id"):  # never answered: nothing to read, it stays at its quote
            counts["left"] += 1
            continue
        try:
            fields = _settlement(higgsfield.status(row["request_id"]))
            if fields is None:
                counts["left"] += 1
                continue
            db.update_ai_video_job(row["id"], **fields)
            counts["settled"] += 1
        except Exception as e:  # noqa: BLE001 — one row's failure leaves it for the next sweep
            counts["errors"] += 1
            log.warning("ai_video: sweep left job %s open (%s)", row.get("id"),
                        higgsfield.redact(e))
            if getattr(e, "kind", None) == "auth":  # every further call would be refused too
                counts["left"] += len(rows) - done - 1
                break
    if any(counts.values()):
        log.info("ai_video: sweep %s", counts)
    return counts


def _clips(n: int) -> str:
    return f"{n} clip" if n == 1 else f"{n} clips"


def spend_line(since: datetime) -> str | None:
    """This run's Higgsfield spend for Telegram (design 6.8), from the ledger: clips bought,
    dollars, clips paid for and not used, and the month to date. None when this run reserved
    nothing, when HF_API_KEY is unset (nothing can have been bought), or when the ledger cannot
    be read. A clip that was paid for and then failed its download or gate is still `completed`
    in the ledger, so the reel's own report (stage 3b) is where that one shows."""
    if not _have_key():
        return None
    try:
        rows = db.ai_video_jobs_since(since)
        if not rows:
            return None
        month = db.ai_video_spend_this_month()
    except Exception as e:  # noqa: BLE001 — a report must never fail a run
        log.warning("ai_video: no spend line, the ledger could not be read (%s)", e)
        return None
    paid = [r for r in rows if float(r.get("cost_usd") or 0) > 0]
    dollars = sum(float(r["cost_usd"]) for r in paid)
    unused = sum(1 for r in paid if r.get("status") in _PAID_UNUSED)
    line = f"🎞️ AI video this run: {_clips(len(paid))}, ${dollars:.2f}"
    if unused:
        line += f" ({unused} paid, not used)"
    return f"{line}; ${month:.2f} this month."
