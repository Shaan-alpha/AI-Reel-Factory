"""Module 5 — Visuals (stock B-roll).

Contract:
    what it does : finds + downloads CC0 vertical B-roll for a script's keywords.
    input        : script_body or keyword list; target duration; output dir.
    output       : list of local clip paths covering the narration length.
    depends on   : Pexels API (primary) -> Pixabay (backup) (rule 11); requests; src.config.

COPYRIGHT SAFETY (docs/08 §3): CC0 stock only — NEVER broadcaster/agency footage. Prefer
maps/charts/data-viz for impact stories. Plan a cut every 5–8s (handled in assembly).

STATUS: stub.
"""
from __future__ import annotations


def fetch_broll(keywords: list[str], target_seconds: float, out_dir: str) -> list[str]:
    """Download enough CC0 vertical clips to cover target_seconds. Pexels then Pixabay."""
    raise NotImplementedError("visuals.fetch_broll — see docs/02-implementation-plan.md §6")


def extract_keywords(script_body: str, n: int = 5) -> list[str]:
    """Pull 3–6 search keywords from the script."""
    raise NotImplementedError("visuals.extract_keywords — see docs/02-implementation-plan.md §6")
