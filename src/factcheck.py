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
  · the checker answers but its JSON is broken  -> repaired if it is only stray quotes, else asked
                                                   ONCE more; only then treated as an outage
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

TODAY'S DATE: {today} (UTC). Events from the last few days are current news, not the future, and \
"this year" means {year}.

SCRIPT TO CHECK:
{body}
{on_screen}
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
When a finding quotes the script, use SINGLE quotes ('like this') — a double quote inside a \
string ends the string and breaks the JSON.
"""


# Moved to llm (2026-09-27) so the scriptwriter, ideation and visuals share the repair that
# stopped this gate falling open on a quote mark. Kept under its old name for callers.
_escape_stray_quotes = llm.escape_stray_quotes


def _parse(raw: str) -> dict:
    """Pull the JSON object out of the model's reply. Tolerates fences, stray prose, and raw
    double quotes inside a finding (see `_escape_stray_quotes`). Raises ValueError if unusable."""
    if "{" not in (raw or ""):
        raise ValueError("fact check: no JSON object in response")
    try:
        data = llm.parse_json(raw[raw.find("{"):])
    except ValueError as e:
        raise ValueError(f"fact check: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("fact check: reply is not a JSON object")
    return data


# The gate's own chain on Vertex (operator, 2026-09-27). gemini-3.5-flash is the stronger
# checker: in one sample it caught the 314 "press briefing" error that gemini-2.5-flash waived as
# minor on 315. About $0.003-0.004 a check; the grounding itself is inside Vertex's free 5,000 a
# month. Flash-Lite behind it takes over if 3.5 Flash is ever withdrawn.
_VERTEX_CHECKER = "gemini-3.5-flash,gemini-3.5-flash-lite"


def _model() -> str | None:
    """Which model (or comma-separated chain) runs the check. None = the grounded chain.

    Backend-dependent. On the Developer API (API key) only `gemini-2.5-flash` has free grounded
    search — every 3.x model 429s with no allowance (measured 2026-08-07) — so the default there
    stays None. On Vertex, which CI runs, Gemini 3 models ground and the gate gets its own chain.
    """
    explicit = config.get("FACTCHECK_MODEL")
    if explicit:
        return explicit
    return _VERTEX_CHECKER if llm._use_vertex() else None


def _api_key() -> str | None:
    """A dedicated Gemini key for the gate, or None to share GEMINI_API_KEY.

    Free grounded search is 20 requests/day and is metered per PROJECT as well as per model.
    Ideation (1/run), the scriptwriter (1/reel) and this gate (1/reel) all draw on the same
    bucket, so a 3-reel run costs 7 and a third run in a day exhausts it — measured live on
    2026-09-03 (`429 ... limit: 20, model: gemini-2.5-flash`). When it runs dry the gate
    cannot run at all, and under the default FACTCHECK_STRICT=false that means reels ship
    UNVERIFIED. Pointing the gate at a second free key gives it an allowance nothing else
    can spend — the same isolation GEMINI_TTS_API_KEY already provides for TTS.
    """
    return (config.get("FACTCHECK_API_KEY") or "").strip() or None


def enabled() -> bool:
    return config.get_bool("ENABLE_FACT_CHECK", True)


def gate_ran(result: dict) -> bool:
    """Did the check actually reach a verdict? False when it was disabled or unavailable.

    `ok=True` alone does not mean "verified": it is also what a fail-open returns. Callers
    that need to know whether the accuracy gate was really in place must ask this, or a
    quota outage looks exactly like a pass (audit 2026-09-03).
    """
    return str(result.get("reason", "")) in ("pass", "fail")


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


# Errors that mean the CREDENTIAL is wrong rather than merely spent. Measured 2026-09-04: a
# key from a NEW Google Cloud project cannot do grounded search at all — gemini-2.5-flash
# answers 404 "no longer available to new users" (it is grandfathered to projects that
# already had it) and every other model 429s with an empty violation list, i.e. no allowance.
# So a well-meant FACTCHECK_API_KEY can be a key that never works, and pointing the gate at
# one made it fail on EVERY reel — permanently fail-open, strictly worse than sharing one
# budget with ideation. A wrong key must cost us the isolation, never the gate.
_MISCONFIGURED = ("404", "not_found", "403", "permission_denied", "api key not valid",
                  "invalid_argument", "api_key_invalid")


def _is_misconfigured(exc: Exception) -> bool:
    """True when the dedicated key/project is wrong, as opposed to out of quota."""
    text = str(exc).lower()
    if "429" in text or "resource_exhausted" in text:
        return False  # the isolation is working and merely spent — do NOT spend the shared key
    return any(m in text for m in _MISCONFIGURED)


def _ask_checker(prompt: str) -> str:
    """Run the grounded check on the dedicated key, falling back to the shared one if that
    key is misconfigured (never if it is merely exhausted — see `_is_misconfigured`)."""
    key = _api_key()
    try:
        return llm.generate_grounded(prompt, max_tokens=2048, model=_model(), api_key=key)
    except Exception as e:  # noqa: BLE001 — decide fall-back-vs-propagate from the error
        if key is None or not _is_misconfigured(e):
            raise
        log.warning("factcheck: FACTCHECK_API_KEY cannot run the check (%s); falling back to "
                    "the shared GEMINI_API_KEY. That key has no grounded search — a key from a "
                    "NEW Google Cloud project does not get one.", str(e)[:160])
        return llm.generate_grounded(prompt, max_tokens=2048, model=_model(), api_key=None)


def _samples() -> int:
    """How many independent checks to run; a finding from ANY of them counts (1-3, default 1).

    The verdict is one sample of a search-backed model, and it varies: measured 2026-09-27, the
    same script passed 2 of 5 runs and another 3 of 5, and temperature 0 does not fix it because
    the search results differ run to run. That is how idea 314 was blocked for a claim that
    idea 315 then shipped with. Two samples roughly halve the chance a real contradiction slips
    through, at one extra grounded call (well inside Vertex's free allowance)."""
    try:
        return max(1, min(3, int(config.get("FACTCHECK_SAMPLES", "1"))))
    except (TypeError, ValueError):
        return 1


def _check_once(prompt: str) -> tuple[dict, str]:
    """One checker verdict and its raw reply. An unreadable reply is asked for once more."""
    raw = _ask_checker(prompt)
    try:
        return _parse(raw), raw
    except ValueError as e:  # JSONDecodeError included
        # A reply we cannot read is not an outage: the checker RAN and reached a verdict we
        # failed to parse. Falling open on it shipped idea 291 unverified (2026-09-12) with a
        # claim the gate blocks 6 times out of 6. One more ask is cheap — Vertex allows 1,500
        # grounded requests a day — and far cheaper than a public false claim.
        log.warning("factcheck: could not parse the checker's reply (%s); asking once more. "
                    "Raw reply: %s", e, raw.strip()[:1500])
        raw = _ask_checker(prompt)
        return _parse(raw), raw


def verify(script_body: str, sources: list[str] | None = None, title: str = "",
           on_screen: list[str] | None = None) -> dict:
    """Re-check a finished script. Returns {ok, unsupported, checked, reason}.

    `ok=False` means BLOCK the reel. A checker failure returns ok=True with a reason, because a
    Gemini outage must not take the day's batch down with it (rule 14) — the scriptwriter's own
    grounding is still in place underneath.

    `on_screen` is the other published text: the key-point cards burned into the video and the
    description summary. They were never checked, yet a viewer reads them as claims too.
    """
    body = (script_body or "").strip()
    if not body:
        return {"ok": False, "unsupported": ["empty script"], "minor": [], "checked": 0,
                "reason": "empty"}
    if not enabled():
        return {"ok": True, "unsupported": [], "minor": [], "checked": 0, "reason": "disabled"}

    from datetime import datetime, timezone

    src_block = "\n".join(f"- {s}" for s in (sources or [])) or "- (none provided)"
    extra = [str(t).strip() for t in (on_screen or []) if str(t).strip()]
    screen_block = ("\nALSO PUBLISHED WITH IT (on-screen cards and the description; check these "
                    "claims too):\n" + "\n".join(f"- {t}" for t in extra) + "\n") if extra else ""
    today = datetime.now(timezone.utc).date()
    prompt = _PROMPT.format(body=f"{title}\n\n{body}".strip(), sources=src_block,
                            on_screen=screen_block, today=today.isoformat(), year=today.year)

    raw = ""
    try:
        data, raw = _check_once(prompt)
        for extra_sample in range(_samples() - 1):
            try:
                more, more_raw = _check_once(prompt)
            except Exception as e:  # noqa: BLE001 — one verdict in hand is enough to decide on
                log.warning("factcheck: extra sample %d could not run (%s)", extra_sample + 2, e)
                continue
            data = _merge_samples(data, more)
            raw = f"{raw.strip()}\n--- sample {extra_sample + 2} ---\n{more_raw.strip()}"
    except Exception as e:  # noqa: BLE001 — checker outage (rules 13, 14)
        # Grounded search shares one free-tier bucket with ideation and the scriptwriter, so a
        # busy day can exhaust it and leave the gate unable to run. FACTCHECK_STRICT decides
        # which risk the operator prefers: fail-open keeps the batch shipping but means the gate
        # silently is not there, fail-closed guarantees the gate but loses reels to an outage.
        strict = config.get_bool("FACTCHECK_STRICT", False)
        log.warning("factcheck: verification UNAVAILABLE (%s) — %s", e,
                    "blocking (FACTCHECK_STRICT)" if strict else
                    "allowing through UNVERIFIED; set FACTCHECK_STRICT=true to block instead")
        if raw.strip():  # without this the reply that defeated the parser is lost for good
            log.warning("factcheck: raw checker reply that could not be used: %s",
                        raw.strip()[:1500])
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
        # A kill is expensive and the grading is the model's, not ours — so record verbatim what
        # it returned. Without this the flattened strings are all that survive, and a model that
        # mis-sorted a finding is indistinguishable from _findings() harvesting one of the
        # undocumented `critical`/`unsupported` keys. Different causes, different fixes; three
        # real reels died in August with no way to tell them apart.
        log.warning("factcheck: raw checker reply for the block above: %s", raw.strip()[:1500])
    else:
        log.info("factcheck: passed (%d claims checked)", checked)
    if minor and ok:  # shipped anyway, but loudly — a rising count means the writer is drifting
        log.warning("factcheck: %d minor issue(s) WAIVED (not fabrication, reel proceeds): %s",
                    len(minor), " | ".join(minor[:3]))
    elif minor:
        log.warning("factcheck: %d minor issue(s) alongside the block: %s",
                    len(minor), " | ".join(minor[:3]))
    return {"ok": ok, "unsupported": blocking, "minor": minor, "checked": checked,
            "reason": "fail" if not ok else "pass"}


def _merge_samples(a: dict, b: dict) -> dict:
    """Two verdicts as one: a finding from either counts, and a 'fail' from either stands."""
    def _list(d: dict, key: str) -> list:
        v = d.get(key)
        return list(v) if isinstance(v, list) else []

    merged = dict(a)
    for key in ("blocking", "critical", "unsupported", "minor", "waived"):
        items = _list(a, key) + [x for x in _list(b, key) if x not in _list(a, key)]
        if items:
            merged[key] = items
    try:
        merged["checked"] = max(int(a.get("checked") or 0), int(b.get("checked") or 0))
    except (TypeError, ValueError):
        pass
    if "fail" in (str(a.get("verdict", "")).lower(), str(b.get("verdict", "")).lower()):
        merged["verdict"] = "fail"
    return merged


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
