"""Module 11 — Fact check (independent post-write verification).

Contract:
    what it does : re-checks a FINISHED script against live web search + its own sources, grades
                   what it finds, and blocks the reel only on a fabrication-grade problem.
    input        : script_body (str), sources (list[str]), optional title.
    output       : {"ok": bool, "unsupported": list[str], "minor": list[str], "checked": int,
                    "reason": str}   ("unsupported" = the BLOCKING findings; "minor" = waived)
    depends on   : src.llm (Gemini grounded search), src.config.

Why this exists. The scriptwriter already writes with grounding, but that is the SAME pass that
invents the framing — a model marking its own homework in the same breath. Since the operator
moved the channel from neutral explainer to truth-first commentary (2026-07-27), the script may
now reach a verdict and name who is responsible. That freedom is only safe if the underlying
facts are load-bearing, so verification stops being advisory and becomes a gate: accuracy is the
monetization gate (rule 6), and a strike costs far more than a skipped reel.

Deliberately a SEPARATE pass with a different prompt, so the check is adversarial rather than
self-confirming: it is told to assume nothing from the script.

SEVERITY GRADING (operator directive, 2026-08-07). The first version treated every discrepancy as
fatal — including rounding, a date off by a day, a figure two sources count differently, and
anything one search pass simply failed to surface ("absence of evidence is failure"). In practice
that blocked most ideas over differences that changed nothing, which is its own failure mode: a
gate that stops everything protects nothing, it just stops the channel. So findings are now sorted
into two buckets and only the first one blocks:

  · blocking — the story is FALSE: the event didn't happen, a named party is blamed for something
    they didn't do, an invented quote/law/ruling/statistic, a number wrong enough to flip the
    conclusion, or a blame claim no source supports at all.
  · minor    — the story is TRUE but imprecise: rounding, a slightly different figure, wording,
    emphasis, or something simply not confirmed by this pass.

Two rules do most of the work, and both come straight from the operator's reasoning:
  · CONTRADICTION blocks; NON-CONFIRMATION does not. One grounded pass missing a real story is
    routine, and "I couldn't find it" is not evidence that it is false.
  · Two sources disagreeing is not proof the script is wrong. Both can be wrong, both can be
    right, or they can be measuring different things. Only the WEIGHT of evidence blocks.

This loosens precision, NOT the anti-fabrication spine — rule 6's trade ("the sharper the verdict,
the more certain its facts must be") is about invented facts and misplaced blame, and those still
block. `FACTCHECK_SEVERITY=any` restores the old block-on-everything behaviour.

Failure semantics differ on purpose (rules 11, 14):
  · a BLOCKING finding                          -> the reel is BLOCKED (this is the point of the gate)
  · only MINOR findings                         -> logged loudly, and the reel proceeds
  · the checker ITSELF errors or is out of quota -> logged, and the reel proceeds
A grounding outage must not silently halt the day's batch; only a real verdict may.
"""
from __future__ import annotations

import json
import logging
import re

from src import config, llm

log = logging.getLogger(__name__)

_PROMPT = """You are the last check before a news script is published to millions of people. \
Your job is to stop FABRICATION — not to police precision.

SCRIPT TO CHECK:
{body}

SOURCES THE WRITER CLAIMS TO HAVE USED:
{sources}

Method — follow it exactly:
1. Extract every LOAD-BEARING factual claim: things that happened, numbers, dates, names, \
attributions, causal statements ("X caused Y"), and any statement assigning responsibility.
2. Use web search to check each claim independently. Do NOT assume the script or its source list \
is correct — the sources may not say what the writer thinks they say.
3. Sort EVERY problem you find into exactly one of the two buckets below. This is not optional: \
a problem you cannot place in "blocking" belongs in "minor".

BLOCKING — publishing this would mean publishing something FALSE. Only these:
· The event, action or ruling did not happen at all, or did not happen as described.
· A named person or organisation is credited or blamed for something they did not do.
· An invented quote, product, law, court ruling, report or statistic — something that does not \
exist.
· A number wrong by enough to change the conclusion: wrong order of magnitude, wrong direction \
(rose vs fell), or off by more than about a quarter.
· A blame or causation claim that NO source supports — not a weakly supported one, an \
unsupported one.

MINOR — real imperfections that do NOT justify killing the story. Everything else, including:
· Rounding, approximation, or a figure that differs because sources count it differently.
· A date off by a few days when the event itself is real.
· Wording, emphasis, or a claim stated more confidently than you would state it.
· A claim you could not independently confirm but that nothing contradicts.
· Sources that disagree with each other.
· A detail that is not load-bearing — remove it and the story still stands.

Two rules decide most cases:
· CONTRADICTION blocks; NON-CONFIRMATION does not. "I could not find this" is MINOR. "I found \
that this is false" is BLOCKING. One search pass missing a real story is common and is not \
evidence that the story is false.
· Two sources disagreeing does not make the script wrong. Both can be wrong, both can be right, \
or they can be measuring different things. Block only when the WEIGHT of the evidence \
contradicts the script — not when it merely fails to line up exactly.

NOT your concern: tone, sarcasm, opinion, or whether the take is harsh. A sharply worded verdict \
that the evidence supports is FINE. You are checking facts, not manners.

Calibrate: most scripts should pass. If your only objections are precision, phrasing or \
confidence, the verdict is "pass" and every item goes in "minor".

Return ONLY a JSON object, no markdown fences:
{{"checked": <how many claims you examined>, "blocking": ["the exact claim, and what contradicts \
it"], "minor": ["the exact claim, and what is imprecise about it"], "verdict": "pass" or "fail"}}
"verdict" is "fail" if and only if "blocking" is non-empty. Both lists may be empty.
"""


def _parse(raw: str) -> dict:
    """Pull the JSON object out of the model's reply. Tolerates fences and stray prose."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("fact check: no JSON object in response")
    return json.loads(raw[start : end + 1], strict=False)


def _model() -> str | None:
    """Which model runs the check. None = use GEMINI_GROUNDED_MODEL.

    Free-tier quota IS metered per model, which suggests pointing the checker at its own model
    to avoid competing with ideation and the scriptwriter. Measured 2026-07-27: that does not
    work on this account, and **re-measured 2026-08-07 against the current lineup: still true.**
    Grounded search 429s on every 3.x model with an empty quota-violation list (no allowance at
    all), while `gemini-2.5-flash` 429s with an explicit `limit: 20` — a real budget, merely
    spent. It remains the only model with free grounded search. A non-default here therefore
    makes the gate fail EVERY time, i.e. permanently fail-open, which is worse than no gate.
    Leave it unset unless the account has paid quota.
    """
    return config.get("FACTCHECK_MODEL") or None


def enabled() -> bool:
    return config.get_bool("ENABLE_FACT_CHECK", True)


def severity_gate() -> str:
    """Which findings block the reel: "critical" (default) or "any".

    "critical" grades findings and blocks only on fabrication-grade ones. "any" is the original
    2026-07-27 behaviour — every discrepancy blocks — kept as an escape hatch in case the grading
    turns out to wave through something it shouldn't.
    """
    val = (config.get("FACTCHECK_SEVERITY") or "critical").strip().lower()
    return "any" if val in ("any", "all", "strict", "minor") else "critical"


def _findings(data: dict, *keys: str) -> list[str]:
    """Collect one bucket of findings, de-duplicated and flattened to single-line strings.

    Tolerant on purpose: the model may return a bare string instead of a list, or `{"claim":…,
    "why":…}` objects instead of strings. A checker that phrases its answer slightly differently
    must not crash the gate (rule 14) — that would fail-open on a real fabrication.
    """
    out: list[str] = []
    for key in keys:
        val = data.get(key)
        if isinstance(val, (str, dict)):
            val = [val]  # a lone finding sent unwrapped — dropping it would fail-open
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, dict):
                parts = (item.get("claim"), item.get("why") or item.get("reason") or item.get("issue"))
                item = " — ".join(str(p) for p in parts if p) or json.dumps(item, default=str)
            text = re.sub(r"\s+", " ", str(item)).strip()
            if text and text not in out:
                out.append(text)
    return out


def verify(script_body: str, sources: list[str] | None = None, title: str = "") -> dict:
    """Re-check a finished script. Returns {ok, unsupported, checked, reason}.

    `ok=False` means BLOCK the reel. A checker failure returns ok=True with a reason, because a
    Gemini outage must not take the day's batch down with it (rule 14) — the scriptwriter's own
    grounding is still in place underneath.
    """
    body = (script_body or "").strip()
    if not body:
        return {"ok": False, "unsupported": ["empty script"], "minor": [], "checked": 0,
                "reason": "empty"}
    if not enabled():
        return {"ok": True, "unsupported": [], "minor": [], "checked": 0, "reason": "disabled"}

    src_block = "\n".join(f"- {s}" for s in (sources or [])) or "- (none provided)"
    prompt = _PROMPT.format(body=f"{title}\n\n{body}".strip(), sources=src_block)

    try:
        data = _parse(llm.generate_grounded(prompt, max_tokens=2048, model=_model()))
    except Exception as e:  # noqa: BLE001 — checker outage (rules 13, 14)
        # Grounded search shares one free-tier bucket with ideation and the scriptwriter, so a
        # busy day can exhaust it and leave the gate unable to run. FACTCHECK_STRICT decides
        # which risk the operator prefers: fail-open keeps the batch shipping but means the gate
        # silently is not there, fail-closed guarantees the gate but loses reels to an outage.
        strict = config.get_bool("FACTCHECK_STRICT", False)
        log.warning("factcheck: verification UNAVAILABLE (%s) — %s", e,
                    "blocking (FACTCHECK_STRICT)" if strict else
                    "allowing through UNVERIFIED; set FACTCHECK_STRICT=true to block instead")
        return {"ok": not strict, "unsupported": [] if not strict else [f"checker unavailable: {e}"],
                "minor": [], "checked": 0, "reason": f"checker-failed: {e}"}

    # `unsupported` is the pre-grading key. If the checker still answers in that shape it has not
    # graded anything, so those findings are treated as BLOCKING — degrade toward the strict
    # behaviour rather than silently waving an ungraded fabrication through.
    blocking = _findings(data, "blocking", "critical", "unsupported")
    minor = [m for m in _findings(data, "minor", "waived") if m not in blocking]
    if severity_gate() == "any":  # escape hatch: restore block-on-every-discrepancy
        blocking, minor = blocking + minor, []

    try:
        checked = int(data.get("checked") or 0)
    except (TypeError, ValueError):
        checked = 0

    verdict = str(data.get("verdict", "")).strip().lower()
    # A "fail" that names NOTHING is still a fail — there is nothing to grade and the checker
    # plainly saw something. But once findings are graded, the grading outranks the verdict word
    # in both directions: "pass" with a blocking finding blocks (a model marking its own homework
    # is what this gate exists to catch), and "fail" with only nitpicks ships (that over-blocking
    # is what the 2026-08-07 grading exists to stop).
    unnamed_fail = verdict == "fail" and not blocking and not minor
    ok = not blocking and not unnamed_fail

    if not ok:
        log.warning("factcheck: BLOCKED — %d blocking finding(s): %s",
                    len(blocking), " | ".join(blocking[:3]) or "verdict=fail with no detail")
    else:
        log.info("factcheck: passed (%d claims checked)", checked)
    if minor:  # shipped anyway, but loudly — a rising count here means the writer is drifting
        log.warning("factcheck: %d minor issue(s) WAIVED (not fabrication, reel proceeds): %s",
                    len(minor), " | ".join(minor[:3]))
    return {"ok": ok, "unsupported": blocking, "minor": minor, "checked": checked,
            "reason": "fail" if not ok else "pass"}


def summary(result: dict, limit: int = 3) -> str:
    """One-line, Telegram-safe reason for an operator alert — the BLOCKING findings only.

    Waived minor findings are deliberately absent: this string explains why a reel died, and
    padding it with the nitpicks that did NOT kill it is how an operator learns to ignore alerts.
    They are in the run log instead.
    """
    items = result.get("unsupported") or []
    if not items:
        return result.get("reason", "unknown")
    text = "; ".join(re.sub(r"\s+", " ", str(i)) for i in items[:limit])
    extra = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return text[:400] + extra
