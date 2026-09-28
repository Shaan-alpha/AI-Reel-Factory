"""LLM helper — Gemini primary, Groq failover (rule 11: fallbacks mandatory).

Contract:
    what it does : one entry point for free-tier text generation; transparent failover.
    how to use   : `from src.llm import generate; text = generate(prompt, json=True)`
    depends on   : google-genai, groq, requests, src.config (GEMINI_API_KEY, GROQ_API_KEY).

Used by the scriptwriter (Module 3) and the ideation fallback. NOT used for Claude —
Claude ideation runs only in the Routine (rule 4). Respect free-tier quotas (rule 13).

Optional third provider: **GitHub Models** — ⚠️ **RETIRED BY GITHUB** (HTTP 410
`github_models_retirement_brownout`, verified 2026-09-01). Still opt-in via ENABLE_GH_MODELS /
PREFER_GH_MODELS and still fails over cleanly, but it can no longer answer, so rule 11's THIRD
link does not currently exist: the live chain is Gemini ↔ Groq only.

SDK note: uses the current **google-genai** SDK (`from google import genai`), not the
deprecated `google-generativeai`. Models are overridable via env (GEMINI_MODEL/GROQ_MODEL)
so we can swap free-tier models without a code change.
"""
from __future__ import annotations

import json as _jsonlib
import logging
import re
import time

from functools import lru_cache

import requests

from src import config

log = logging.getLogger(__name__)

# Free-tier defaults (override via env). Two SEPARATE Gemini models on purpose — measured on this
# account 2026-08-07 (rule 13):
#
#   · plain text  — gemini-3.5/3.6-flash, 3.5/3.1-flash-lite and 3-flash-preview all answered fine
#     while gemini-2.5-flash was returning `limit: 20 ... model: gemini-2.5-flash`. Free quota is
#     metered PER MODEL, so each newer model carries its own untouched daily budget, and 3.6 Flash
#     is a straight quality upgrade over 2.5 Flash for scripts and hooks.
#   · grounded    — Google Search grounding 429s on EVERY 3.x model with an empty quota-violation
#     list (the signature of no free allowance), while gemini-2.5-flash 429s with an explicit
#     `limit: 20`, i.e. a real budget that was merely spent. **gemini-2.5-flash is still the only
#     model with free grounded search**, so grounding stays pinned to it.
#
# Keeping these on one knob was a live footgun: `_gen_gemini_grounded` defaulted to GEMINI_MODEL,
# so "bump GEMINI_MODEL if RPD gets tight" — which .env.example actively advised — would have
# silently killed grounded ideation, the grounded scriptwriter AND the fact-check gate at once.
#
# 2026-09-04, measured on a second key: free grounded search is now CLOSED TO NEW PROJECTS.
# `gemini-2.5-flash` 404s with "no longer available to new users" on a fresh key while still
# serving the original project, and every other model 429s with no allowance on BOTH keys. So
# the 20/day on this one project is the entire grounded budget the pipeline will ever have for
# free — it cannot be widened by minting more keys, only by paying.
#
# 2026-09-27: on Vertex (what CI runs) the picture is different, and time-limited. Google's
# model-versions page lists gemini-2.5-flash for RETIREMENT ON 2026-10-20, replacement
# gemini-3.5-flash-lite, while Gemini 3 models ground fine on Vertex (5,000 grounded prompts/month
# free, then $14/1,000; 3.5 Flash-Lite tokens cost what 2.5 Flash's do). Measured the same day:
# grounded search answers on gemini-3.5-flash-lite and gemini-3.5-flash in this project. So
# GEMINI_GROUNDED_MODEL is now an ordered, comma-separated CHAIN (see _grounded_chain), and
# the default depends on the backend. On Vertex the pipeline moved off gemini-2.5-flash ahead of
# its retirement (operator, 2026-09-27) onto Google's named replacement, gemini-3.5-flash-lite,
# with gemini-3.5-flash behind it. On the Developer API gemini-2.5-flash stays: it is the only
# model with free grounded search there, and a fresh clone runs on that path.
# Text model: gemini-3.8-flash (2026-09-27), Google's listed replacement for 3.6 Flash, served
# on both backends. Its thinking floor is LOW, which _generate_content handles.
_GEMINI_MODEL = config.get("GEMINI_MODEL", "gemini-3.8-flash")
_GEMINI_GROUNDED_MODEL = config.get("GEMINI_GROUNDED_MODEL")  # None = the backend's default
_GROUNDED_DEFAULT_VERTEX = "gemini-3.5-flash-lite,gemini-3.5-flash"
_GROUNDED_DEFAULT_DEV = "gemini-2.5-flash"


def _grounded_chain(model: str | None) -> list[str]:
    """Grounded models to try, in order: `model` if given (a single name or its own chain),
    else GEMINI_GROUNDED_MODEL, else the backend's default chain."""
    raw = model or _GEMINI_GROUNDED_MODEL or (
        _GROUNDED_DEFAULT_VERTEX if _use_vertex() else _GROUNDED_DEFAULT_DEV)
    chain = [m.strip() for m in str(raw).split(",") if m.strip()]
    return chain or [_GROUNDED_DEFAULT_DEV]


def _is_model_gone(exc: Exception) -> bool:
    """True if the backend no longer serves the model (retired, or never available here).

    Vertex answers `404 NOT_FOUND ... Publisher model ... was not found`; the Developer API says
    a model is "no longer available". Anything else (503, 429, 400) is NOT a reason to switch
    models: the fact-check model would change on a blip."""
    text = str(exc).lower()
    return ("404" in text or "not_found" in text) and (
        "not found" in text or "not_found" in text or "no longer available" in text)
# Groq retired `llama-3.3-70b-versatile` — it 404s `model_not_found` (found 2026-08-25, live).
# That left rule 11's mandatory chain with a DEAD second link: every Groq test mocks `_gen_groq`,
# so the suite stayed green while the only fallback under Gemini failed on every call, turning
# Gemini's 20/day free cap into a hard stop for the whole pipeline. `openai/gpt-oss-120b` is the
# most capable model Groq still serves that handles BOTH plain and `json_object` mode, which the
# scriptwriter and keyword extraction both need. (`qwen/qwen3.6-27b` answers plain prompts but
# 400s on JSON and leaks `<think>` reasoning into its output, so it is not a drop-in.)
# `test_configured_groq_model_actually_exists` now pins this against the live API.
_GROQ_MODEL = config.get("GROQ_MODEL", "openai/gpt-oss-120b")


def _use_vertex() -> bool:
    """Serve Gemini through Vertex AI (ADC) instead of the Developer API (API key)?

    Off by default: the API-key path needs no cloud setup and is what a fresh clone can run.
    """
    return config.get_bool("GEMINI_USE_VERTEX", False)


@lru_cache(maxsize=4)
def _gemini_client(api_key: str | None = None):
    """Cached google-genai client. Imported lazily (no SDK at import time).

    TWO backends, because their grounded-search economics differ by two orders of magnitude
    (measured 2026-09-04):

      · Developer API (API key) — free tier is **20 grounded requests/day** on gemini-2.5-flash,
        and that one bucket is shared by ideation, the scriptwriter and `factcheck.verify`. At
        ~21/day of demand it runs dry, and the fact-check gate is what stops working. A second
        free key does not help: grounded search is closed to new projects entirely.
      · Vertex AI (ADC) — the same models with **1,500 grounded requests/day free** on 2.5, and
        gemini-2.5-flash is still served here even though the Developer API 404s it for new
        projects. Auth is Application Default Credentials, so no API key exists to leak — which
        is also the only thing this Google Cloud org allows: its policy blocks BOTH API keys and
        service-account keys, leaving ADC locally and Workload Identity Federation in CI.

    Vertex quota is per PROJECT, so a per-caller `api_key` is meaningless there and ignored.
    Keyed by credential in API-key mode so a dedicated key keeps its own allowance.
    """
    from google import genai

    if _use_vertex():
        return genai.Client(
            vertexai=True,
            project=config.require("GCP_PROJECT"),
            location=config.get("GCP_LOCATION", "global"),
        )
    return genai.Client(api_key=api_key or config.require("GEMINI_API_KEY"))


@lru_cache(maxsize=1)
def _groq_client():
    """Cached Groq client. Imported lazily so the module loads without the SDK."""
    from groq import Groq

    return Groq(api_key=config.require("GROQ_API_KEY"))


def _thinking_cfg(model: str):
    """Least-thinking config for `model` — the knob is NOT the same across generations.

    Thinking is on by default and eats `max_output_tokens`, which is what truncated grounded
    JSON mid-script back in 2026-06. Suppressing it needs a different field per generation:

      · Gemini 2.x — `thinking_budget=0` (0 = DISABLED).
      · Gemini 3.x — `thinking_budget` is REJECTED (400 INVALID_ARGUMENT, verified 2026-08-07 on
        gemini-3.6-flash); it was replaced by `thinking_level`, whose floor is MINIMAL. Thinking
        cannot be switched off entirely on these models, only minimised.

    Sending the 2.x field to a 3.x model 400s every call, which silently drains the whole Gemini
    leg of the fallback chain into Groq (rule 11) — the failover hides it, so it looks like it
    still works. Hence: pick by model, don't assume.
    """
    from google.genai import types

    head = model.split("-")[1] if "-" in model else ""
    if head.startswith("3"):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    return types.ThinkingConfig(thinking_budget=0)


# The refusal is worded differently per backend. Vertex: "Thinking level is unsupported:
# THINKING_LEVEL_MINIMAL". The Developer API: "Thinking level MINIMAL is not supported for this
# model" — which the first version of this check missed, so there every gemini-3.8-flash text
# call failed over to Groq (seen live in a test run, 2026-09-28).
_MINIMAL_REFUSAL_RE = re.compile(r"(?is)thinking[ _]level.{0,40}?(?:unsupported|not supported)")
# Models that refused MINIMAL in this process go straight to LOW: otherwise every call to them
# spends a failed request first.
_MINIMAL_REFUSED: set[str] = set()


def _generate_content(client, *, model: str, contents: str, config):
    """`client.models.generate_content`, retried once at LOW thinking if MINIMAL is refused.

    MINIMAL is not a floor every 3.x model shares: gemini-3.8-flash refuses it (measured
    2026-09-27 on Vertex) and accepts LOW and up. Keyed on the error rather than a version
    table, so the next model that moves the floor costs one extra request instead of every
    Gemini call silently failing over to Groq."""
    from google.genai import types

    def _at_low():
        config.thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)

    level = getattr(getattr(config, "thinking_config", None), "thinking_level", None)
    if model in _MINIMAL_REFUSED and level == types.ThinkingLevel.MINIMAL:
        _at_low()
    try:
        return client.models.generate_content(model=model, contents=contents, config=config)
    except Exception as e:  # noqa: BLE001 — only the one refusal is handled; the rest re-raise
        if not _MINIMAL_REFUSAL_RE.search(str(e)):
            raise
        _MINIMAL_REFUSED.add(model)
        log.warning("llm: %s refuses MINIMAL thinking; using LOW for it from now on", model)
        _at_low()
        return client.models.generate_content(model=model, contents=contents, config=config)


def _gen_gemini(prompt: str, *, json: bool, max_tokens: int) -> str:
    from google.genai import types

    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=_thinking_cfg(_GEMINI_MODEL),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    if json:
        cfg.response_mime_type = "application/json"
    resp = _generate_content(_gemini_client(), model=_GEMINI_MODEL, contents=prompt, config=cfg)
    return resp.text or ""


def _gen_gemini_grounded(prompt: str, *, max_tokens: int, model: str | None = None,
                         api_key: str | None = None) -> str:
    """Gemini with Google Search grounding — live web research with real sources.

    Note: the google_search tool can't combine with forced-JSON mime, so the caller must
    ask for JSON in the prompt text and parse it (grounding still makes the model use real,
    current facts + cite genuine sources).

    Defaults to GEMINI_GROUNDED_MODEL, NOT GEMINI_MODEL: free grounded search exists only on
    gemini-2.5-flash on this account (measured 2026-08-07 — every 3.x model 429s the google_search
    tool with no allowance), so the ungrounded model must be free to move ahead without dragging
    grounding onto a model that cannot do it.

    Free-tier quota is metered **per model** (quotaId GenerateRequestsPerDayPerProjectPerModel),
    so pointing a second grounded consumer at a different model would give it its OWN daily budget
    instead of competing for the shared 20/day bucket (rule 13) — but only among models that HAVE
    a grounded allowance, which today is just the default. See factcheck._model().
    """
    return _gen_gemini_grounded_full(prompt, max_tokens=max_tokens, model=model,
                                     api_key=api_key)[0]


def _text_parts(resp) -> dict[int, tuple[int, str]]:
    """{part index: (character offset of that part in `resp.text`, part text)}.

    Mirrors how the SDK builds `resp.text`: text parts concatenated in order, thought parts
    skipped. Falls back to treating the whole reply as part 0 when the parts are not reachable.
    """
    try:
        raw_parts = list(resp.candidates[0].content.parts or [])
    except (AttributeError, IndexError, TypeError):
        raw_parts = []
    out: dict[int, tuple[int, str]] = {}
    base = 0
    for i, part in enumerate(raw_parts):
        text = getattr(part, "text", None)
        if not isinstance(text, str) or getattr(part, "thought", None) is True:
            continue
        out[i] = (base, text)
        base += len(text)
    if not out:
        out[0] = (0, getattr(resp, "text", "") or "")
    return out


def _support_span(seg, parts: dict[int, tuple[int, str]]) -> tuple[int, int] | None:
    """One support segment as (start, end) character offsets into `resp.text`, or None.

    Three things about the API's numbers, all measured live on Vertex 2026-09-13 and all stated
    in the SDK's own `Segment` docstring:
      · `start_index` is OMITTED when it is 0 (proto3 default), so the SDK hands back None. The
        old `int(None)` raised TypeError on the reply's first support — and the handler around
        the loop then discarded EVERY span, turning all citations "loose" and giving each idea
        in the batch the whole batch's sources (ideas 291/292: 15 shared citations each).
      · offsets are UTF-8 BYTES, not characters. Identical on ASCII, but every ₹, em dash or
        curly quote before the segment (3 bytes, 1 character) pushes it two characters right —
        a few of those and a citation lands on the neighbouring idea.
      · offsets are relative to the PART named by `part_index`, not to the joined text.
    """
    end_b = getattr(seg, "end_index", None)
    if end_b is None:
        return None
    start_b = getattr(seg, "start_index", None) or 0
    part_i = getattr(seg, "part_index", None) or 0
    base, text = parts.get(int(part_i), parts.get(0, (0, "")))
    data = text.encode("utf-8")

    def _chars(n: int) -> int:  # bytes -> characters; a cut mid-codepoint rounds down
        return len(data[: max(0, int(n))].decode("utf-8", "ignore"))

    start, end = base + _chars(start_b), base + _chars(end_b)
    return (start, end) if end > start else None


def _grounded_sources(resp) -> list[dict]:
    """The REAL Google Search citations behind a grounded reply: [{uri, domain, spans}].

    This is the metadata the module used to discard. Without it, callers had no way to learn
    which pages the search actually returned, so `ideation_fallback` asked the MODEL for source
    URLs — and a model cannot recall URLs, so it produced plausible-looking ones with placeholder
    ids (`articleshow/115000000.cms`, `world-asia-68700000`). Measured 2026-09-03: every such URL
    404'd, the liveness probe dropped the ideas, and the on-demand run either shipped a digest of
    one or died with "no fresh ideas to seed".

    `spans` are (start, end) CHARACTER offsets into `resp.text`, from `grounding_supports`, so
    a caller emitting several objects in one reply can attribute each citation to the right one.
    A chunk with no support keeps an empty span list: it is still a real article, merely
    unattributable. Fail-soft (rule 11) — a reply with no grounding metadata yields [].

    The API does not hand over character offsets, and reading its numbers as if it did is how
    every idea in the 2026-09-12 digest came to cite every story (see `_support_span`).
    """
    try:
        gm = resp.candidates[0].grounding_metadata
        chunks = list(gm.grounding_chunks or [])
    except (AttributeError, IndexError, TypeError):
        return []

    parts = _text_parts(resp)
    spans: dict[int, list[tuple[int, int]]] = {}
    for sup in getattr(gm, "grounding_supports", None) or []:
        try:  # per support: one malformed segment must not cost the others their attribution
            span = _support_span(sup.segment, parts)
            if span is None:
                continue
            for idx in sup.grounding_chunk_indices or []:
                spans.setdefault(int(idx), []).append(span)
        except (AttributeError, TypeError, ValueError):  # noqa: BLE001 — spans are a bonus
            continue

    out: list[dict] = []
    for i, chunk in enumerate(chunks):
        web = getattr(chunk, "web", None)
        uri = (getattr(web, "uri", "") or "").strip()
        if uri:
            out.append({"uri": uri, "domain": (getattr(web, "title", "") or "").strip(),
                        "spans": spans.get(i, [])})
    return out


def _gen_gemini_grounded_full(prompt: str, *, max_tokens: int, model: str | None = None,
                              api_key: str | None = None) -> tuple[str, list[dict]]:
    """One grounded call — returns (text, real citations). See `_grounded_sources`.

    Walks `_grounded_chain`: a model the backend no longer serves advances to the next one;
    every other error propagates so `_call_with_retry` can judge it."""
    from google.genai import types

    chain = _grounded_chain(model)
    for i, chosen in enumerate(chain):
        cfg = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            # Search grounding is not a callable function; automatic function calling only makes
            # the newer SDK warn on every grounded call ("Direct use of AFC ... not recommended").
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            # Minimise "thinking" — it eats max_output_tokens and was truncating the grounded
            # JSON reply mid-script, forcing the ungrounded fallback. Per-generation field.
            thinking_config=_thinking_cfg(chosen),
        )
        try:
            resp = _generate_content(_gemini_client(api_key), model=chosen, contents=prompt,
                                     config=cfg)
        except Exception as e:  # noqa: BLE001 — only a retired model moves down the chain
            if i == len(chain) - 1 or not _is_model_gone(e):
                raise
            log.error("llm: grounded model %s is no longer served (%s); moving to %s. Update "
                      "GEMINI_GROUNDED_MODEL.", chosen, str(e)[:160], chain[i + 1])
            continue
        return resp.text or "", _grounded_sources(resp)
    raise RuntimeError("llm: empty grounded model chain")  # unreachable: chain is never empty


def generate_grounded(prompt: str, *, max_tokens: int = 4096, model: str | None = None,
                      api_key: str | None = None) -> str:
    """Generate with live web research (Gemini Google Search grounding). Raises on failure so
    callers can fall back to plain generate(). Gemini-only — Groq has no grounding.

    Pass `model` to spend a DIFFERENT model's free-tier quota (see _gen_gemini_grounded), or
    `api_key` to spend a different PROJECT's. Both matter: measured 2026-09-03, ideation +
    the scriptwriter + the fact-check gate share ONE 20/day grounded budget, a 3-reel run
    costs 7 calls, and once it is gone the gate fails open (factcheck.verify).

    Retried once on a transient error, because this path has NO second provider (Groq has no
    grounding) and its failure is silent: `factcheck.verify` treats a checker outage as
    fail-open under the default FACTCHECK_STRICT=false, so a 503 here does not block a reel —
    it publishes one with the accuracy gate quietly absent.
    """
    def _attempt(p, *, json=False, max_tokens=max_tokens):  # noqa: ARG001 — _call_with_retry's shape
        return _gen_gemini_grounded(p, max_tokens=max_tokens, model=model, api_key=api_key)

    text = _call_with_retry("gemini-grounded", _attempt, prompt, json=False, max_tokens=max_tokens)
    if not text or not text.strip():
        raise RuntimeError("llm.generate_grounded: empty response")
    return text


def generate_grounded_with_sources(prompt: str, *, max_tokens: int = 4096,
                                   model: str | None = None,
                                   api_key: str | None = None) -> tuple[str, list[dict]]:
    """Like `generate_grounded`, but also returns the search's REAL citation URLs.

    Use this wherever the reply is supposed to be SOURCED. Asking the model to write the URLs
    into its own answer does not work — it invents them — so the citations must come from the
    grounding metadata, which is what this exposes (see `_grounded_sources`).
    """
    def _attempt(p, *, json=False, max_tokens=max_tokens):  # noqa: ARG001 — _call_with_retry's shape
        return _gen_gemini_grounded_full(p, max_tokens=max_tokens, model=model,
                                         api_key=api_key)

    text, sources = _call_with_retry("gemini-grounded", _attempt, prompt,
                                     json=False, max_tokens=max_tokens)
    if not text or not text.strip():
        raise RuntimeError("llm.generate_grounded: empty response")
    return text, sources


def today_line() -> str:
    """A date line for prompts that write about the news.

    Models do not know the date. A grounded answer about "today" opened "As of June 7, 2026" in
    September, and the idea-308 draft called a law already signed "headed to the President's
    desk", which the dated fact-check then blocked. Prepended by the scriptwriter and ideation;
    the fact-check prompt carries its own."""
    from datetime import datetime, timezone

    d = datetime.now(timezone.utc).date()
    return (f"TODAY'S DATE: {d.isoformat()} ({d:%A}), UTC. What the sources report from the last "
            f"few days is current news: describe it in the right tense, and never date it to "
            f"another month or year.\n\n")


def escape_stray_quotes(blob: str) -> str:
    """Escape double quotes that sit INSIDE a JSON string instead of ending it.

    A model writing JSON by hand (the grounded path cannot use JSON mode) routinely leaves quotes
    raw: `"script_body": "the US just "destroyed" five..."`. json.loads reads the inner quote as
    the end of the string and dies with "Expecting ',' delimiter". That error shipped idea 291
    unverified from the fact-check (2026-09-12) and wrote both 2026-09-22 scripts UNGROUNDED,
    because this channel's sarcastic voice lives on scare quotes.

    A quote inside a string is taken as CLOSING only when what follows can legally follow a
    string: `:` `]` `}` or the end, or `,` followed by the start of another value. Anything else
    (a letter, a space and then a word) means it was a quote in prose.
    """
    out: list[str] = []
    in_string = escaped = False
    n = len(blob)
    for i, ch in enumerate(blob):
        if not in_string:
            in_string = ch == '"'
            out.append(ch)
            continue
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            j = i + 1
            while j < n and blob[j].isspace():
                j += 1
            nxt = blob[j] if j < n else ""
            if nxt == ",":
                k = j + 1
                while k < n and blob[k].isspace():
                    k += 1
                closes = k >= n or blob[k] in '"{['
            else:
                closes = nxt in ("", ":", "]", "}")
            if closes:
                in_string = False
            else:
                out.append('\\"')
                continue
        out.append(ch)
    return "".join(out)


def parse_json(raw: str):
    """The first JSON object or array in an LLM reply. Raises ValueError if there is none.

    Tolerates fences and prose around it, raw control characters in strings, text AFTER it, and
    raw double quotes inside strings (see `escape_stray_quotes`). The old first-`{`-to-last-`}`
    slice failed on text after the JSON and on a bare array: `[{...}, {...}]` sliced to
    `{...}, {...}` is the "Extra data" that killed ideation's top-up (run 34954327606)."""
    text = raw or ""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"no JSON in LLM reply: {text[:200]!r}")
    blob = text[min(starts):]
    decoder = _jsonlib.JSONDecoder(strict=False)
    try:
        return decoder.raw_decode(blob)[0]
    except _jsonlib.JSONDecodeError:
        try:
            return decoder.raw_decode(escape_stray_quotes(blob))[0]
        except _jsonlib.JSONDecodeError as e:
            raise ValueError(f"unparseable JSON in LLM reply ({e}): {text[:200]!r}") from e


def parse_json_object(raw: str) -> dict:
    """`parse_json`, insisting on an object (the shape every caller's schema has)."""
    data = parse_json(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM reply is JSON but not an object")
    return data


# Upstream states worth ONE retry: capacity and quota-window, not "your request is wrong".
# A 400 is a verdict — retrying it just spends the clock twice for the same answer.
# A dropped connection is retried too (added 2026-09-27): the grounded call has no second
# provider, so under FACTCHECK_STRICT one network blip used to hold a reel back.
_RETRYABLE_MARKERS = ("429", "resource_exhausted", "503", "unavailable", "500", "internal",
                      "504", "deadline", "overloaded", "disconnected", "timed out",
                      "connection reset", "connection aborted")
# Google returns its own advice as `'retryDelay': '46s'`. Honour it rather than guessing.
_RETRY_DELAY_RE = re.compile(r"retrydelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.I)
_DEFAULT_RETRY_WAIT = 2.0


def _retry_wait(exc: Exception) -> float | None:
    """Seconds to wait before retrying `exc`, or None if it is not worth retrying.

    None also covers "retryable, but the API wants longer than a reel is worth": a daily-cap 429
    can name an hour, and stalling a 60-minute job on it is worse than failing over.
    """
    text = str(exc).lower()
    if not any(m in text for m in _RETRYABLE_MARKERS):
        return None
    m = _RETRY_DELAY_RE.search(text)
    wait = float(m.group(1)) if m else _DEFAULT_RETRY_WAIT
    try:
        ceiling = float(config.get("LLM_RETRY_MAX_WAIT", "90"))
    except (TypeError, ValueError):
        ceiling = 90.0
    return wait if wait <= ceiling else None


def _call_with_retry(name: str, fn, prompt: str, *, json: bool, max_tokens: int) -> str:
    """One provider call, retried ONCE on a transient upstream error.

    Rule 11 gives every dependency a fallback, but failing over on a 503 spends the fallback on
    a blip — and when the fallback is itself degraded, that turns a recoverable hiccup into a
    dead reel. Run 32920283763: Gemini 503s, the loop immediately hands the work to a Groq leg
    that 400s on every JSON call, and the reel dies with ~40 minutes of job budget unused, while
    the 429 in the same run carried an explicit `retryDelay: 46s` nobody read.
    """
    try:
        return fn(prompt, json=json, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001 — decide retry-vs-failover from the error itself
        wait = _retry_wait(e)
        if wait is None:
            raise
        log.warning("llm: %s hit a transient error (%s); retrying once in %.1fs", name, e, wait)
        time.sleep(wait)
        return fn(prompt, json=json, max_tokens=max_tokens)


def _gen_groq(prompt: str, *, json: bool, max_tokens: int) -> str:
    # Groq's json_object mode requires the word "json" to appear in the prompt; callers
    # that pass json=True already phrase the prompt as "return a JSON object …".
    #
    # reasoning_effort is LOAD-BEARING, not a tuning knob. The default model is a reasoning
    # model (openai/gpt-oss-*) and Groq bills the reasoning trace against the completion budget.
    # At Groq's default effort the trace alone can consume a small max_tokens, so generation is
    # cut off before a single content token is emitted — and in json_object mode Groq then
    # rejects that empty completion with `400 json_validate_failed` / `failed_generation: ''`.
    # Measured 2026-09-01 on the real visuals keyword prompt at max_tokens=200: default effort
    # 400s, "low" answers in 52 reasoning tokens. That 400 is what left rule 11's chain one-deep
    # for six days, because the model-identity test passes a toy prompt that fits in the trace.
    # Documented values for gpt-oss are low|medium|high (console.groq.com/docs/reasoning).
    kwargs: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "model": _GROQ_MODEL,
        "max_tokens": max_tokens,
        "reasoning_effort": config.get("GROQ_REASONING_EFFORT", "low"),
    }
    if json:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = _groq_client().chat.completions.create(**kwargs)
    except Exception as e:  # noqa: BLE001 — one specific, budget-shaped failure is retried
        # An EMPTY failed_generation means the reasoning trace ate the budget before any content
        # (still seen at 1024 tokens on 2026-09-27). Twice the room usually clears it; anything
        # else re-raises so the chain fails over as before.
        text = str(e)
        if not (json and "json_validate_failed" in text and "'failed_generation': ''" in text):
            raise
        kwargs["max_tokens"] = min(8192, max_tokens * 2)
        resp = _groq_client().chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _github_key() -> str | None:
    """The GitHub Models credential.

    Named GH_MODELS_KEY, not GITHUB_MODELS_KEY: GitHub rejects secret/variable names starting
    with the `GITHUB_` prefix, so the latter could never be created as an Actions secret.
    `GITHUB_TOKEN` is still read because it is the built-in Actions token (usable with
    `permissions: models: read`).

    Deliberately does NOT fall back to GH_PAT: that is the Telegram bot's Actions read+write
    PAT, and this repo's Actions hold the YouTube/Supabase/Telegram secrets — sending it to a
    third-party inference endpoint would widen its blast radius for nothing (rule 5). Use a
    token whose ONLY scope is `models: read`."""
    return config.get("GH_MODELS_KEY") or config.get("GITHUB_TOKEN")


def _github_enabled() -> bool:
    """GitHub Models is OPT-IN, not "on whenever a token exists".

    `GITHUB_TOKEN` shows up in environments incidentally (any Actions job that forwards it), and
    an unconfigured provider silently inserted into the chain costs a doomed HTTP round-trip on
    every call — which delays the Groq failover on exactly the Gemini-quota outages it's there
    to survive (rules 11, 13)."""
    if not _github_key():
        return False
    return (config.get_bool("PREFER_GH_MODELS", False)
            or config.get_bool("ENABLE_GH_MODELS", False))


def _gen_github_models(prompt: str, *, json: bool, max_tokens: int) -> str:
    """GitHub Models inference (OpenAI-compatible chat completions).

    ⚠️ **RETIRED BY GITHUB — this leg cannot contribute a completion.** Verified 2026-09-01:
    both `models.github.ai/catalog/models` and the inference endpoint below return HTTP 410
    `github_models_retirement_brownout`. It stays in the tree because it is opt-in, defaults to
    off, and fails over cleanly — but do NOT count it as rule 11's third link. If a genuine
    third provider is wanted, a second model on the existing Groq key is the cheapest real one.

    Endpoint + model naming per GitHub's REST docs: the host is `models.github.ai/inference`
    (the old `models.inference.ai.azure.com` preview host is retired) and `model` MUST carry its
    publisher prefix, e.g. `openai/gpt-4o-mini`. The token needs the **`models: read`** scope; in
    Actions the job also needs `permissions: models: read`.

    Catalog is OpenAI/DeepSeek/Microsoft/Llama/Mistral/xAI — there is no Anthropic model here,
    so this never becomes a back door around rule 4."""
    key = _github_key()
    if not key:
        raise RuntimeError("github models: GH_MODELS_KEY / GITHUB_TOKEN not set")
    model = config.get("GH_MODEL", "openai/gpt-4o-mini")
    if "/" not in model:  # a bare name 400s on this endpoint; assume the OpenAI publisher
        model = f"openai/{model}"
    payload: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "model": model,
        "max_tokens": max_tokens,
    }
    if json:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://models.github.ai/inference/chat/completions",
        headers={"Authorization": f"Bearer {key}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"github models HTTP {r.status_code}: {r.text[:300]}")
    choices = (r.json() or {}).get("choices") or []
    if not choices:
        raise RuntimeError("github models returned no choices")
    return choices[0].get("message", {}).get("content") or ""


def generate(prompt: str, *, json: bool = False, max_tokens: int = 1024,
             prefer_groq: bool = False) -> str:
    """Generate text via Gemini; on error/quota/empty, fail over to Groq. Return raw text.

    Set json=True when the prompt asks for a JSON object (callers parse the result); every
    provider is put into JSON mode. Raises RuntimeError only if *every* provider fails —
    a single upstream failure never propagates (rule 11). This is the runtime-soft path
    (rule 14): providers are tried in order and failures are logged, not fatal.

    prefer_groq=True tries Groq FIRST (Gemini second). Use it for no-web text tasks (hook
    punch-up, keyword extraction) so Gemini's scarce free RPD (rule 13) is reserved for the
    grounded web research that only Gemini can do — quality on the accuracy-critical path stays.

    GitHub Models joins the chain only when explicitly opted in (see `_github_enabled`):
    ENABLE_GH_MODELS inserts it as a middle fallback, PREFER_GH_MODELS puts it first.
    """
    gemini = ("gemini", _gen_gemini)
    groq = ("groq", _gen_groq)
    github = ("github", _gen_github_models)

    use_github = _github_enabled()
    if prefer_groq:
        order = (groq, github, gemini) if use_github else (groq, gemini)
    elif use_github and config.get_bool("PREFER_GH_MODELS", False):
        order = (github, gemini, groq)
    else:
        order = (gemini, github, groq) if use_github else (gemini, groq)

    errors: list[str] = []
    for name, fn in order:
        try:
            text = _call_with_retry(name, fn, prompt, json=json, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 — failover must catch anything upstream throws
            log.warning("llm: %s failed (%s); failing over", name, e)
            errors.append(f"{name}: {e}")
            continue
        if text and text.strip():
            return text
        log.warning("llm: %s returned an empty response; failing over", name)
        errors.append(f"{name}: empty response")
    raise RuntimeError("llm.generate: all providers failed — " + " | ".join(errors))
