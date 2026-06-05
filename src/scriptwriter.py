"""Module 3 — Scriptwriter.

Contract:
    what it does : turns an approved idea (+ its sources) into a script via a template.
    input        : idea dict {title, hook, angle, sources, ...}; template name (default 'N').
    output       : {script_body, caption, hashtags[]} — also written to the scripts table.
    depends on   : src.llm, src.db, templates/*.md, src.config.

ORIGINALITY IS THE MONETIZATION GATE (docs/08 §1): the script's core value is the
"why it matters" ANALYSIS, not a summary. Rewrite facts in own words + cite. Caption must
include source links + an AI-disclosure line. Keyword-rich title (SEO). Append #Shorts.

STATUS: stub.
"""
from __future__ import annotations


def write_script(idea: dict, template: str = "N") -> dict:
    """Generate {script_body, caption, hashtags[]} for an approved idea and persist it."""
    raise NotImplementedError("scriptwriter.write_script — see docs/02-implementation-plan.md §4")
