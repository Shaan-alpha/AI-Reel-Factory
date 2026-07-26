"""Module 11 — Fact check (independent post-write verification).

Contract:
    what it does : re-checks a FINISHED script against live web search + its own sources, and
                   reports any claim it cannot support.
    input        : script_body (str), sources (list[str]), optional title.
    output       : {"ok": bool, "unsupported": list[str], "checked": int, "reason": str}
    depends on   : src.llm (Gemini grounded search), src.config.

Why this exists. The scriptwriter already writes with grounding, but that is the SAME pass that
invents the framing — a model marking its own homework in the same breath. Since the operator
moved the channel from neutral explainer to truth-first commentary (2026-07-27), the script may
now reach a verdict and name who is responsible. That freedom is only safe if the underlying
facts are load-bearing, so verification stops being advisory and becomes a gate: accuracy is the
monetization gate (rule 6), and a strike costs far more than a skipped reel.

Deliberately a SEPARATE pass with a different prompt, so the check is adversarial rather than
self-confirming: it is told to assume nothing from the script and to treat "cannot verify" as
failure, not as a pass.

Failure semantics differ on purpose (rules 11, 14):
  · verdict says a claim is unsupported  -> the reel is BLOCKED (this is the point of the gate)
  · the checker ITSELF errors or is out of quota -> logged, and the reel proceeds
A grounding outage must not silently halt the day's batch; only a real verdict may.
"""
from __future__ import annotations

import json
import logging
import re

from src import config, llm

log = logging.getLogger(__name__)

_PROMPT = """You are a hostile fact-checker for a news channel. A script has already been \
written and is about to be published to millions of people. Your job is to STOP anything that \
cannot be proven, not to be agreeable.

SCRIPT TO CHECK:
{body}

SOURCES THE WRITER CLAIMS TO HAVE USED:
{sources}

Method — follow it exactly:
1. Extract every LOAD-BEARING factual claim: things that happened, numbers, dates, names, \
attributions, causal statements ("X caused Y"), and any statement assigning responsibility.
2. Use web search to check each claim independently. Do NOT assume the script or its source list \
is correct — the sources may not say what the writer thinks they say.
3. Mark a claim "unsupported" if ANY of these hold: you cannot find corroboration; the real \
figure, date or name differs; the attribution is wrong; a causal or blame claim goes further \
than the evidence; or the event is real but the script overstates its scale or certainty.

CRITICAL: "I could not verify this" means UNSUPPORTED. Absence of evidence is failure, not a \
pass. It is far better to block a true story than to publish a false one.

NOT your concern: tone, sarcasm, opinion, or whether the take is harsh. A sharply worded verdict \
that the evidence supports is FINE. You are checking facts, not manners.

Return ONLY a JSON object, no markdown fences:
{{"checked": <how many claims you examined>, "unsupported": ["the exact claim, and why it fails", \
"..."], "verdict": "pass" or "fail"}}
If every claim checks out, "unsupported" is an empty list and "verdict" is "pass".
"""


def _parse(raw: str) -> dict:
    """Pull the JSON object out of the model's reply. Tolerates fences and stray prose."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("fact check: no JSON object in response")
    return json.loads(raw[start : end + 1], strict=False)


def _model() -> str | None:
    """Which model runs the check. None = use GEMINI_MODEL.

    Free-tier quota IS metered per model, which suggests pointing the checker at its own model
    to avoid competing with ideation and the scriptwriter. Measured 2026-07-27: that does not
    work on this account. Every alternative returns `limit: 0` — no free allowance at all —
    while `gemini-2.5-flash` is the only grounded model with a real free budget (20/day). A
    non-default here therefore makes the gate fail EVERY time, i.e. permanently fail-open, which
    is worse than no gate. Leave it unset unless the account has paid quota.
    """
    return config.get("FACTCHECK_MODEL") or None


def enabled() -> bool:
    return config.get_bool("ENABLE_FACT_CHECK", True)


def verify(script_body: str, sources: list[str] | None = None, title: str = "") -> dict:
    """Re-check a finished script. Returns {ok, unsupported, checked, reason}.

    `ok=False` means BLOCK the reel. A checker failure returns ok=True with a reason, because a
    Gemini outage must not take the day's batch down with it (rule 14) — the scriptwriter's own
    grounding is still in place underneath.
    """
    body = (script_body or "").strip()
    if not body:
        return {"ok": False, "unsupported": ["empty script"], "checked": 0, "reason": "empty"}
    if not enabled():
        return {"ok": True, "unsupported": [], "checked": 0, "reason": "disabled"}

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
                "checked": 0, "reason": f"checker-failed: {e}"}

    raw_unsupported = data.get("unsupported")
    unsupported = [str(c).strip() for c in raw_unsupported
                   if str(c).strip()] if isinstance(raw_unsupported, list) else []
    try:
        checked = int(data.get("checked") or 0)
    except (TypeError, ValueError):
        checked = 0

    verdict = str(data.get("verdict", "")).strip().lower()
    # Trust the CLAIM LIST over the verdict word: a model that lists problems then says "pass"
    # is the exact failure this gate exists to catch.
    ok = not unsupported and verdict != "fail"

    if not ok:
        log.warning("factcheck: BLOCKED — %d unsupported claim(s): %s",
                    len(unsupported), " | ".join(unsupported[:3]) or verdict)
    else:
        log.info("factcheck: passed (%d claims checked)", checked)
    return {"ok": ok, "unsupported": unsupported, "checked": checked, "reason": verdict or "pass"}


def summary(result: dict, limit: int = 3) -> str:
    """One-line, Telegram-safe reason for an operator alert."""
    items = result.get("unsupported") or []
    if not items:
        return result.get("reason", "unknown")
    text = "; ".join(re.sub(r"\s+", " ", str(i)) for i in items[:limit])
    extra = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return text[:400] + extra
