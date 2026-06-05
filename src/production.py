"""Orchestrator — the daily production pipeline (Module 10 in docs/02 §10).

Contract:
    what it does : for each approved idea, runs script -> voice -> visuals -> assemble ->
                   subtitle -> publish -> record -> cleanup. One reel failing is logged and
                   skipped; the batch continues (rule 14: fail soft on runtime).
    how to use   : `python -m src.production` (invoked by .github/workflows/production.yml).
    depends on   : all src modules + src.config.

On run: validate config, then check Supabase for today's ideas; if empty AND
ENABLE_FALLBACK_IDEATION, fire src.ideation_fallback (rule 11/12). Process approvals, then
produce the approved queue. Idempotent — safe to re-run (rule 12).

STATUS: stub — wired last, after every module passes in isolation (rule 7).
"""
from __future__ import annotations

from src import config


def run() -> None:
    """Run one production cycle. See module docstring for the step order."""
    config.validate()  # fail loud on misconfig (rule 14)
    raise NotImplementedError("production.run — see docs/02-implementation-plan.md §10")


if __name__ == "__main__":
    run()
