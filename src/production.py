"""Orchestrator — the daily production pipeline (Module 10 in docs/02 §10).

Contract:
    what it does : for each approved idea, runs script -> voice -> visuals -> assemble ->
                   subtitle -> publish -> record -> cleanup. One reel failing is logged and
                   skipped; the batch continues (rule 14: fail soft on runtime).
    how to use   : `python -m src.production` (invoked by .github/workflows/production.yml).
    depends on   : all src modules + src.config.

On run: validate config, then bootstrap ideas+digest if the queue is dry (fallback ideation,
rule 11/12), drain any Telegram approvals (best-effort), and produce the approved queue.
Idempotent — produced ideas are skipped and already-published scripts never re-upload (rule 12).

STATUS: wired last, after every module passed in isolation (rule 7).
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile

from src import (
    approval,
    assembly,
    config,
    db,
    ideation_fallback,
    publish_youtube,
    scriptwriter,
    subtitles,
    visuals,
    voice,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("production")

_PLATFORM = "youtube"


def _work_root() -> str:
    root = config.get("WORK_DIR") or os.path.join(tempfile.gettempdir(), "ai-reel-factory")
    os.makedirs(root, exist_ok=True)
    return root


def _build_metadata(idea: dict, script: dict) -> dict:
    """Map an idea + its script into YouTube upload metadata (publish enforces disclosure/#Shorts)."""
    return {
        "title": idea.get("title", ""),
        "description": script.get("caption", ""),
        "tags": script.get("hashtags", []),
    }


def produce_one(idea: dict, work_root: str) -> tuple[str, str]:
    """Run the full chain for one approved idea. Returns (video_id, url). Idempotent."""
    idea_id = idea["id"]
    script = scriptwriter.write_script(idea)
    script_id = script["script_id"]

    # Idempotency (rule 12): if this script already published, mark produced and bail.
    existing = db.find_post(script_id, _PLATFORM)
    if existing and existing.get("external_id"):
        db.set_idea_status(idea_id, "produced")
        log.info("produce: idea %s already published (%s); skipping render.",
                 idea_id, existing["external_id"])
        return existing["external_id"], existing.get("url") or ""

    work = os.path.join(work_root, f"idea_{idea_id}")
    os.makedirs(work, exist_ok=True)
    try:
        audio, duration = voice.synthesize(script["script_body"], work)
        keywords = visuals.extract_keywords(script["script_body"])
        clips = visuals.fetch_broll(keywords, duration, work)
        raw = assembly.assemble(audio, clips, os.path.join(work, "reel_raw.mp4"))
        final = subtitles.burn_captions(raw, audio, os.path.join(work, "reel_final.mp4"))
        video_id, url = publish_youtube.publish(final, _build_metadata(idea, script), script_id)
        db.set_idea_status(idea_id, "produced")
        return video_id, url
    finally:
        shutil.rmtree(work, ignore_errors=True)  # render artifacts are disposable (rule 15)


def _notify_failure(idea: dict, error: Exception) -> None:
    """Best-effort Telegram alert on a hard per-reel failure (rule 13). Never raises."""
    try:
        approval._api("sendMessage", chat_id=config.require("TELEGRAM_CHAT_ID"),
                      text=f"⚠️ Reel failed for idea {idea.get('id')} "
                           f"({idea.get('title')!r}): {type(error).__name__}: {error}")
    except Exception:  # noqa: BLE001 — alerting must never break the batch
        log.warning("production: failure alert could not be sent.")


def run_production(limit: int | None = None) -> dict:
    """Produce the approved queue (capped). One failure is logged + skipped (rule 14)."""
    cap = limit if limit is not None else int(config.get("DAILY_REEL_CAP", "5"))
    approved = db.get_approved_ideas()[:cap]
    if not approved:
        log.info("production: no approved ideas to produce.")
        return {"published": [], "failed": []}

    work_root = _work_root()
    published, failed = [], []
    for idea in approved:
        try:
            video_id, url = produce_one(idea, work_root)
            published.append({"idea_id": idea["id"], "video_id": video_id, "url": url})
            log.info("production: published idea %s -> %s", idea["id"], url)
        except Exception as e:  # noqa: BLE001 — fail soft per reel; keep the batch alive
            log.exception("production: idea %s failed", idea.get("id"))
            failed.append({"idea_id": idea.get("id"), "error": f"{type(e).__name__}: {e}"})
            _notify_failure(idea, e)
    return {"published": published, "failed": failed}


def ensure_ideas_and_digest() -> int:
    """If the queue is dry, run fallback ideation and send the digest. Return #ideas created."""
    if db.get_pending_ideas() or db.get_approved_ideas():
        return 0
    if str(config.get("ENABLE_FALLBACK_IDEATION", "true")).lower() != "true":
        log.info("production: queue empty and fallback ideation disabled.")
        return 0
    n = ideation_fallback.run_fallback_ideation()
    if n:
        approval.send_digest()
    return n


def _notify(text: str) -> None:
    """Best-effort Telegram message (links, status). Never raises."""
    try:
        approval._api("sendMessage", chat_id=config.require("TELEGRAM_CHAT_ID"), text=text)
    except Exception:  # noqa: BLE001
        log.warning("production: notify failed: %s", text)


def run() -> None:
    """Run one production cycle. See module docstring for the step order."""
    config.validate()  # fail loud on misconfig (rule 14)

    ensure_ideas_and_digest()

    try:  # apply any queued approvals; Telegram being down must not block production
        approval.process_responses(max_seconds=int(config.get("DRAIN_SECONDS", "20")))
    except Exception as e:  # noqa: BLE001
        log.warning("production: approval drain failed (continuing): %s", e)

    summary = run_production()
    log.info("production: done — %d published, %d failed.",
             len(summary["published"]), len(summary["failed"]))


def make_on_demand(num_ideas: int = 3, wait_minutes: int = 20) -> dict:
    """On-demand 'make a Short': propose fresh ideas to Telegram, wait for taps, produce the
    approved ones, and reply with the links. Triggered by the make-short workflow button."""
    config.validate()
    # Prefer ideas already queued (the daily Anthropic Routine inserts these straight into
    # Supabase). Only generate via the Gemini/Groq fallback when the queue is empty.
    existing = db.get_pending_ideas()
    if existing:
        n = len(existing)
        log.info("make_on_demand: %d pending idea(s) already queued (Routine).", n)
    else:
        n = ideation_fallback.seed_ideas(num_ideas)
    _notify(f"🎬 {n} idea(s) ready — tap ✅ Make it on what you want "
            f"(waiting up to {wait_minutes} min).")
    approval.send_digest()
    approval.process_responses(max_seconds=wait_minutes * 60)

    summary = run_production()
    if summary["published"]:
        for p in summary["published"]:
            _notify(f"✅ Published: {p['url']}")
    else:
        _notify("Nothing approved — no Short produced this time.")
    log.info("make_on_demand: %d published, %d failed.",
             len(summary["published"]), len(summary["failed"]))
    return summary


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "make":
        make_on_demand(int(os.environ.get("IDEAS", "3")), int(os.environ.get("WAIT_MIN", "20")))
    else:
        run()
