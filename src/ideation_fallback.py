"""Module 1 (fallback) — free-API ideation when the Claude Routine didn't run.

Contract:
    what it does : produces the same idea rows as routines/ideation.md, via Gemini/Groq.
    how to use   : `run_fallback_ideation()` — called by the orchestrator only when
                   Supabase has no pending ideas for today (rule 11/12).
    depends on   : src.llm, src.db, src.config.

ToS (rule 4): this uses the Gemini/Groq DEVELOPER APIs — never Claude. Same JSON contract
and the same sensitivity/sourcing rules as the Routine (docs/08-news-niche-playbook.md).

CAVEAT (honesty over polish): unlike the Claude Routine, the free dev APIs have no live web
search here, so model-supplied source URLs may be stale/uncertain. This is a rare-day backup;
the human Telegram approval is the safety net, and the scriptwriter still cites sources. Ideas
that don't carry >= MIN_SOURCES plausible URLs are dropped rather than shipped unsourced.
"""
from __future__ import annotations

import json
import logging
import os
import re

import requests

from urllib.parse import urljoin, urlparse

from src import config, db, llm, news, trends

log = logging.getLogger(__name__)

_MAX_IDEAS = 20
_MIN_IDEAS = 5  # below this, treat the run as failed rather than ship a thin digest

# Columns the `ideas` table actually has — `share_score` is ranking-only, never persisted.
_ROW_KEYS = ("niche", "title", "hook", "angle", "est_score", "sources")


def _to_rows(ideas: list[dict]) -> list[dict]:
    """Project validated ideas to the DB columns (drops ranking-only fields like share_score)."""
    return [{k: idea[k] for k in _ROW_KEYS} for idea in ideas]


def _rank_key(idea: dict):
    """Sort key: share_score first (virality), est_score as tiebreaker. Highest first."""
    return (-idea.get("share_score", idea["est_score"]), -idea["est_score"])


# Tiny stopword set so near-identical titles overlap on meaningful words, not glue words.
_STOPWORDS = {"the", "a", "an", "of", "to", "in", "for", "and", "is", "on", "with",
              "at", "by", "from", "as", "new", "today"}


def _tokens(title: str) -> set[str]:
    """Significant lowercased word tokens of a title (numbers kept, stopwords dropped)."""
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOPWORDS}

# The daily Anthropic Routine (Claude + web research) commits its ideas here; the on-demand
# flow prefers these over the Gemini/Groq fallback. See routines/ideation.md.
_ROUTINE_IDEAS_FILE = "data/daily-ideas.json"

_PROMPT = """You are the ideation engine for "But It Matters", a channel of daily, punchy \
**25-30 second** news/info Shorts (India + world). Turn the SELECTED stories below into {n} \
TIMELY ideas a human will approve 4-5 of — each a single crisp on-point fact that still carries \
one honest "why it matters" angle (not a bare summary), with strong scroll-stopping, \
share-worthy potential.

SELECTED DISTINCT STORIES (write EXACTLY ONE idea per story, in order; NEVER two ideas on the \
same event):
{selected}

PRIMARY ANCHOR — REAL CURRENT HEADLINES (verify the facts against these; prefer these real \
stories over generic evergreen topics):
{headlines}

SUPPLEMENTARY TREND SIGNAL (optional flavour only; ignore generic weather/calendar/sports-score noise):
{trending}

WINNING TITLE STYLES ON THIS CHANNEL (these actual published titles + view counts show what the \
feed rewards — copy the ENERGY and framing, never the exact title; if empty, ignore):
{winners}

HONEST SCROLL APPEAL: pick the angle a smart person finds genuinely surprising or consequential \
— real stakes, money & power, conflict with real consequences, science/space, big human impact. \
The hook must be a TRUE curiosity gap the explainer can actually CLOSE (a bait topic the facts \
can't support gets suppressed). Apply a SHARE TEST: would someone send this to a friend? Set \
share_score by that; set est_score by how strong an HONEST hook plus a real "why it matters" \
angle the story supports — never by how dramatic a title you could slap on it.

SCORE CALIBRATION (IMPORTANT): RANK the ideas against each OTHER and SPREAD the scores across the \
full 0.0-1.0 range — do NOT give everything ~1.0. The strongest single idea may approach 1.0, the \
weakest should sit near 0.3-0.5, and the rest in between. Use DISTINCT share_score values so the \
list has a clear best-to-worst order; est_score may differ from share_score per idea.

ACCURACY (CRITICAL — this is the #1 rule): propose only REAL, verifiable developments that \
ACTUALLY happened recently. NEVER invent product names, version numbers, launches, statistics, \
quotes, or events, and never attribute a claim to a company/person unless it's real. If unsure a \
thing genuinely happened, DO NOT make it up — choose a different real story. When unsure, \
generalize truthfully rather than invent specifics. Fabricated news = instant demonetization and strikes.

FRAMING RULES: the standard is TRUTH, not neutrality. Say what the evidence actually supports, \
even when that is unflattering to a government, company or party — a well-sourced conclusion is \
not "taking a side". You MAY reach a verdict and say plainly who is responsible, provided every \
load-bearing fact is verifiable and cited. What you may NOT do is assert anything you cannot \
source: an unverifiable claim is worthless however satisfying it sounds. Politics, government \
actions and court rulings are fully in scope. EXCLUDE only: communal/religious incitement or \
hate; anything that could inflame violence; unverified rumors/claims stated as fact; deepfakes/ \
impersonation; graphic tragedy exploitation; medical/financial advice stated as fact.

Each idea: a PUNCHY, curiosity-driven title honest to the story (NOT a dry "X explained" search \
title, NOT a bait title the facts can't back); a story that lands in 25-30 seconds (a single \
development with a sharp angle, not a deep-dive); a "hook" that is a genuine first-2-seconds \
scroll-stopper (one surprising true fact); and a share_score.

SOURCES — READ THIS CAREFULLY: real citations are attached AUTOMATICALLY from the live search \
and the news feed above, so you do NOT need to supply them. Put a URL in "sources" ONLY if you \
are certain that exact page exists; otherwise return "sources": []. An empty list is CORRECT \
and costs nothing. A guessed or pattern-matched URL is worse than none: it 404s, the idea is \
discarded, and >= {min_src} real sources are needed to ship.

Return ONLY JSON:
{{"ideas": [{{"niche": "impact-news", "title": "...", "hook": "the first 3 seconds", \
"angle": "the original why-it-matters take", "est_score": 0.0, "share_score": 0.0, \
"sources": ["https://...", "https://..."]}}]}}
"""


# Ideation is the one grounded caller that needs the search's CITATIONS, not just grounded
# text: they become each idea's sources. Measured 2026-09-27 on Vertex with the real ideation
# prompt, two runs per model: gemini-2.5-flash returned 15 and 18 citations, while
# gemini-3.5-flash-lite, gemini-3.5-flash and gemini-3.8-flash all SEARCHED (3 queries each) but
# returned ZERO citation chunks. So ideation stays on 2.5 until Vertex retires it (2026-10-20),
# then the 404 moves it to 3.5-flash-lite, where sources come from the news feed and the Google
# News search top-up (which gave every idea two real sources in the same live run).
_VERTEX_IDEATION_CHAIN = "gemini-2.5-flash,gemini-3.5-flash-lite"


def _ideation_model() -> str | None:
    """IDEATION_MODEL, or on Vertex the citation-bearing chain above. None = the grounded chain."""
    explicit = config.get("IDEATION_MODEL")
    if explicit:
        return explicit
    return _VERTEX_IDEATION_CHAIN if llm._use_vertex() else None


def _parse_ideas(raw: str) -> list[dict]:
    # llm.parse_json: a bare array, text after the JSON and raw quotes inside strings all parse
    # (the old first-{-to-last-} slice turned a bare array into "Extra data").
    try:
        data = llm.parse_json(raw)
    except ValueError as e:
        raise ValueError(f"ideation_fallback: {e}") from e
    ideas = data.get("ideas", []) if isinstance(data, dict) else data
    if not isinstance(ideas, list):
        raise ValueError("ideation_fallback: 'ideas' is not a list.")
    return ideas


def _clean_sources(raw_sources) -> list[str]:
    if not isinstance(raw_sources, list):
        return []
    seen, out = set(), []
    for s in raw_sources:
        s = str(s).strip()
        if s.lower().startswith(("http://", "https://")) and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# Codes that mean the publisher itself says the page does not exist. Deliberately NARROW:
# news sites answer 401/403 to anything that looks like a bot (NDTV and Bloomberg both did,
# measured 2026-09-01), and treating those as dead would bin good ideas citing real articles.
_DEAD_CODES = (404, 410)
_SOURCE_TIMEOUT = 12
# A browser UA, because several publishers 403 the python-requests default outright — which
# would make the check useless rather than merely conservative.
_SOURCE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _url_is_dead(url: str) -> bool:
    """True only when the publisher answers 404/410 for `url`.

    `_clean_sources` checks that a source merely STARTS WITH http, which is the whole of what
    this module used to mean by "sourced+validated". Measured against the live channel on
    2026-09-01: of 167 source URLs on 75 published Shorts, 91 were hard 404s and 23 reels cited
    no live article at all — some with placeholder ids (`articleshow/12345678.cms`), some real
    articles about an entirely different story. Citing sources that do not exist is the
    originality/monetization gate failing (docs/08 §1), and it is also what the fact-checker
    kept (correctly) blocking reels over.

    Fail-SOFT by design (rule 14): any transport error, timeout or odd status returns False, so
    a network blip can never empty the digest. This drops only what a publisher actively denies.
    """
    try:
        resp = requests.get(url, timeout=_SOURCE_TIMEOUT, allow_redirects=True,
                            stream=True, headers={"User-Agent": _SOURCE_UA})
        try:
            return resp.status_code in _DEAD_CODES
        finally:
            resp.close()  # stream=True: don't pull the body just to read a status line
    except Exception:  # noqa: BLE001 — a failed probe is NOT evidence the article is missing
        return False


# How much of the smaller token set two titles must share to count as the same story, plus a
# floor on the raw overlap. One common word ("india", "trump") is coincidence; a punchy rewrite
# of a headline reliably keeps 2+ of its distinctive nouns and numbers.
_STORY_MATCH_RATIO = 0.4
_STORY_MATCH_MIN_TOKENS = 2


def _match_story_urls(idea: dict, stories: list[dict]) -> list[str]:
    """Feed article URLs for the story this idea is actually about ([] if none match).

    The news feed carries several outlets per event, so a matched idea usually comes away with
    two INDEPENDENT publishers — which is exactly what MIN_SOURCES asks for, obtained without
    spending any quota and without trusting the model to remember a URL.
    """
    idea_toks = _tokens(f"{idea.get('title', '')} {idea.get('hook', '')}")
    if not idea_toks:
        return []
    out = []
    for story in stories:
        story_toks = _tokens(story.get("title", ""))
        if not story_toks:
            continue
        shared = idea_toks & story_toks
        if len(shared) >= _STORY_MATCH_MIN_TOKENS and                 len(shared) / min(len(idea_toks), len(story_toks)) >= _STORY_MATCH_RATIO:
            url = (story.get("url") or "").strip()
            if url and url not in out:
                out.append(url)
    return out


def _is_homepage(url: str) -> bool:
    """True for a bare site root ('https://www.bbc.com/') — never a citation for a claim.

    A homepage always answers 200, so `_url_is_dead` waves it through, but it supports
    nothing: tomorrow it shows different stories entirely. Seen in the live 2026-09-03 check,
    where the model answered with bbc.com/ and timesofindia.indiatimes.com/ once it was told
    not to guess article paths. Citing those is the same docs/08 §1 failure as citing a 404.
    """
    try:
        return urlparse(url).path.strip("/") == "" and not urlparse(url).query
    except ValueError:  # noqa: BLE001 — an unparseable URL is not a usable citation either
        return True


def _resolve_redirect(url: str) -> str:
    """The publisher URL a citation redirect points to; `url` unchanged on failure.

    Grounded citations arrive as `vertexaisearch.cloud.google.com/grounding-api-redirect/…`
    links, which read as noise in a YouTube description and expire. Resolving them once, here,
    stores the real article URL instead. Best-effort: a failed probe must never cost us a
    citation we genuinely have (rule 11).

    ONE hop, read from Google's own `Location` header. Following the whole chain meant the
    publisher had to answer too, and a slow or bot-blocking one (the Washington Post resets bot
    traffic) left the raw redirect in stored and published sources even though Google had
    already said where it pointed (probed 2026-09-27: 302 with the WaPo URL).
    """
    try:
        resp = requests.get(url, timeout=_SOURCE_TIMEOUT, allow_redirects=False,
                            headers={"User-Agent": _SOURCE_UA})
        try:
            location = resp.headers.get("Location") if 300 <= resp.status_code < 400 else None
        finally:
            resp.close()
        return urljoin(url, location) if location else url
    except Exception:  # noqa: BLE001 — keep the redirect rather than lose the source
        return url


# Words too common in news slugs to show that an article is about THIS story.
_GENERIC_SLUG_TOKENS = {"news", "india", "world", "live", "latest", "update", "updates", "article",
                        "story", "report", "says", "said", "amp", "html", "htm", "cms", "php",
                        "articleshow", "business", "politics", "national", "international"}


def _slug_tokens(url: str) -> set[str]:
    try:
        path = urlparse(url).path
    except ValueError:
        return set()
    return {t for t in _tokens(re.sub(r"[-_/.]+", " ", path))
            if len(t) > 1 and not t.isdigit() and t not in _GENERIC_SLUG_TOKENS}


def _cites_this_story(idea: dict, url: str) -> bool:
    """False when a descriptive article slug shares no distinctive word with the idea.

    Published idea 301 (Iran and the UAE) went out citing three UCC articles from the same batch,
    after the 2026-09-13 attribution fix. Grounding offsets are approximate, so a resolved URL
    whose slug plainly names another story is dropped. A slug with fewer than three words (an id,
    '/a/12345') says nothing either way and is kept."""
    slug = _slug_tokens(url)
    if len(slug) < 3:
        return True
    idea_toks = _tokens(" ".join(str(idea.get(k) or "") for k in ("title", "hook", "angle")))
    return bool(slug & (idea_toks - _GENERIC_SLUG_TOKENS))


def _idea_spans(raw: str, ideas: list[dict]) -> list[tuple[int, int]]:
    """Character span of each idea's object in the raw reply — its title, up to the next title.

    Grounding supports are offsets into that reply, so this is what lets a citation be pinned to
    the idea it actually backs instead of being smeared across all of them.
    """
    starts = []
    cursor = 0
    for idea in ideas:
        at = raw.find(str(idea.get("title", "")), cursor) if idea.get("title") else -1
        starts.append(at)
        if at >= 0:
            cursor = at + 1
    spans = []
    for i, start in enumerate(starts):
        if start < 0:
            spans.append((-1, -1))
            continue
        nxt = next((s for s in starts[i + 1:] if s > start), len(raw))
        spans.append((start, nxt))
    return spans


def _content_ranges(raw: str, idea: dict, lo: int, hi: int) -> list[tuple[int, int]]:
    """Where this idea's OWN words — title, hook, angle — sit inside its span of the raw reply.

    Tried verbatim and then JSON-escaped, because the parsed value of a string holding a quote
    or a newline is not what appears in the reply text.
    """
    out = []
    for key in ("title", "hook", "angle"):
        val = str(idea.get(key) or "")
        if not val:
            continue
        for needle in (val, json.dumps(val, ensure_ascii=False)[1:-1]):
            at = raw.find(needle, lo, hi)
            if at >= 0:
                out.append((at, at + len(needle)))
                break
    return out


def _overlap(s: int, e: int, ranges: list[tuple[int, int]]) -> int:
    return sum(max(0, min(e, b) - max(s, a)) for a, b in ranges)


def _citations_by_idea(ideas: list[dict], raw: str, grounded: list[dict]) -> list[list[dict]]:
    """Which grounded citations back which idea — each support credited to ONE idea.

    A support segment is a run of the reply text, and those runs do not respect JSON object
    boundaries: measured live on 2026-09-13, supports ran from the tail of one idea
    (`"est_score": 0.85, "sources": [] }, { "niche": …`) into the next idea's title and hook. The
    old rule credited a citation to every idea its span merely TOUCHED, so an idea kept picking
    up its neighbour's articles. A support now goes to the idea whose own words it covers most,
    falling back to raw span overlap only for a support that covers no idea's words at all.

    A citation with no span at all is unattributable. It belongs to the idea only when the reply
    holds exactly one; in a multi-idea reply it is dropped, because a citation for the wrong
    story is worse than none (docs/08 §1) and `_search_for_more` tops up an idea that runs short
    from a search for ITS title. Handing such citations to every idea is what shipped a Houthi
    Short citing a Nagpur bank robbery (ideas 291/292, 2026-09-12).
    """
    owned: list[list[dict]] = [[] for _ in ideas]
    if len(ideas) == 1:
        owned[0] = list(grounded)
        return owned
    spans = _idea_spans(raw, ideas)
    content = [_content_ranges(raw, idea, lo, hi) if lo >= 0 else []
               for idea, (lo, hi) in zip(ideas, spans)]
    for g in grounded:
        owners: set[int] = set()
        for s, e in g.get("spans", []):
            scores = [_overlap(s, e, ranges) for ranges in content]
            if not any(scores):
                scores = [_overlap(s, e, [span]) if span[0] >= 0 else 0 for span in spans]
            best = max(scores, default=0)
            if best > 0:
                owners.update(i for i, score in enumerate(scores) if score == best)
        for i in sorted(owners):
            owned[i].append(g)
    return owned


def _attach_real_sources(ideas: list[dict], raw: str, grounded: list[dict],
                         stories: list[dict]) -> list[dict]:
    """Replace each idea's sources with REAL ones, best first. Mutates and returns `ideas`.

    Order is the operator's choice (2026-09-03): a resolved publisher URL from the grounded
    search first, then the news feed's own article link for the story the idea came from, then
    whatever the model wrote — kept last, and only because `_validate_and_clean` still probes it,
    so a genuine URL the model happened to know is not thrown away while an invented one is.
    Which grounded citation belongs to which idea is `_citations_by_idea`'s call.
    """
    resolved: dict[str, str] = {}

    for idea, mine in zip(ideas, _citations_by_idea(ideas, raw, grounded)):
        publisher = []
        for g in mine:
            uri = g.get("uri", "")
            if not uri:
                continue
            if uri not in resolved:
                resolved[uri] = _resolve_redirect(uri)
            if not _cites_this_story(idea, resolved[uri]):
                log.info("ideation_fallback: %r: dropped a citation about another story: %s",
                         idea.get("title"), resolved[uri][:120])
                continue
            if resolved[uri] not in publisher:
                publisher.append(resolved[uri])
        # A homepage is dropped wherever it came from: it is live, and it cites nothing.
        model_written = [u for u in _clean_sources(idea.get("sources")) if not _is_homepage(u)]
        fetched = [u for u in [*publisher, *_match_story_urls(idea, stories)]
                   if not _is_homepage(u)]
        merged: list[str] = []
        for url in [*fetched, *model_written]:
            if url not in merged and not _is_homepage(url):
                merged.append(url)
        idea["sources"] = _search_for_more(idea, merged,
                                           trusted=len(dict.fromkeys(fetched)))
    return ideas


def _search_query(idea: dict) -> str:
    """A news-search query from an idea's title, with figures left intact.

    Splitting on every non-alphanumeric turned "1,250 Dead" into "1 250 Dead" — two useless
    tokens in place of the single most distinctive term in the headline, which is why that
    search came back with 2 results instead of dozens (live, 2026-09-03).
    """
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9',.]*", str(idea.get("title", "")))
    return " ".join(w.strip(".,'") for w in words if w.strip(".,'"))


def _search_for_more(idea: dict, found: list[str], trusted: int | None = None) -> list[str]:
    """Top `found` up to MIN_SOURCES using the free Google News RSS search. Never raises.

    The top-stories feed only carries the front page, and grounded search has 20 free calls a
    day (rule 13) — on 2026-09-03 the live check found it already spent. This path costs one
    key-less HTTP request and only runs for an idea that is actually short, so a well-sourced
    batch adds no requests at all.

    `trusted` is how many of `found` we actually FETCHED (grounded citations and feed
    articles). It exists because a URL the model merely asserted is not evidence of anything:
    counting one toward the minimum let an idea skip this search and then be dropped moments
    later when the liveness probe 404'd that same URL — the exact shape of the live failure.
    """
    min_src = int(config.get("MIN_SOURCES", "2"))
    have = len(found) if trusted is None else trusted
    if have >= min_src or not config.get_bool("ENABLE_SOURCE_SEARCH", True):
        return found
    query = _search_query(idea)
    results = news.search_stories(query, limit=max(min_src * 4, 8))
    out = list(found)
    # Two passes: one publisher at most on the first, so ">= MIN_SOURCES sources" means
    # INDEPENDENT outlets corroborating each other (docs/08 §1) rather than one outlet's story
    # counted twice. The second pass then fills from repeats rather than leave a true story
    # unsourced — for a domestic item only PTI ran, one outlet twice still beats dropping it.
    for unique_publishers in (True, False):
        seen_publishers: set[str] = set()
        for story in results:
            url = (story.get("url") or "").strip()
            publisher = (story.get("source") or "").strip().lower()
            if not url or url in out or _is_homepage(url):
                continue
            if unique_publishers and publisher and publisher in seen_publishers:
                continue
            seen_publishers.add(publisher)
            out.append(url)
            if len(out) >= min_src:
                break
        if len(out) >= min_src:
            break
    if len(out) > len(found):
        log.info("ideation: search found %d more source(s) for %r",
                 len(out) - len(found), idea.get("title"))
    return out


def _validate_and_clean(ideas: list[dict], existing: list[dict] | None = None) -> list[dict]:
    """Keep well-formed, sufficiently-sourced, de-duplicated ideas; coerce fields.

    `existing` seeds the de-duplication with an earlier batch, so a second pass topping up a
    thin grounded result cannot re-propose what the first pass already kept — and the sources
    already probed in that first pass are not probed again (rule 13).
    """
    min_src = int(config.get("MIN_SOURCES", "2"))
    niche = config.get("NICHE", "impact-news")
    check_sources = config.get_bool("ENABLE_SOURCE_CHECK", True)
    seen_titles: set[str] = {str(i.get("title", "")).lower() for i in (existing or [])}
    kept_tokens: list[set[str]] = [_tokens(str(i.get("title", ""))) for i in (existing or [])]
    clean: list[dict] = []

    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        title = str(idea.get("title", "")).strip()
        hook = str(idea.get("hook", "")).strip()
        angle = str(idea.get("angle", "")).strip()
        if not (title and hook and angle):
            continue
        if title.lower() in seen_titles:
            continue
        toks = _tokens(title)
        if toks and any(len(toks & kt) / len(toks | kt) >= 0.6 for kt in kept_tokens):
            log.debug("ideation_fallback: dropping near-duplicate %r", title)
            continue
        sources = _clean_sources(idea.get("sources"))
        if check_sources and sources:
            live = [s for s in sources if not _url_is_dead(s)]
            if len(live) < len(sources):
                log.warning("ideation_fallback: %r cited %d dead link(s): %s",
                            title, len(sources) - len(live),
                            [s for s in sources if s not in live])
            sources = live
        if len(sources) < min_src:
            log.info("ideation_fallback: dropping %r (%d live source(s) < %d required)",
                     title, len(sources), min_src)
            continue
        try:
            est = float(idea.get("est_score", 0.5))
        except (TypeError, ValueError):
            est = 0.5
        est = min(1.0, max(0.0, est))
        try:
            share = float(idea.get("share_score", est))
        except (TypeError, ValueError):
            share = est
        share = min(1.0, max(0.0, share))

        seen_titles.add(title.lower())
        kept_tokens.append(toks)
        clean.append({"niche": niche, "title": title, "hook": hook, "angle": angle,
                      "est_score": est, "share_score": share, "sources": sources})
        if len(clean) >= _MAX_IDEAS:
            break
    return clean


_STAGE1_PROMPT = """You are the story scout for "But It Matters", a channel of daily 25-30 \
second news/info Shorts (India + world). From the REAL headlines below, choose the {n} MOST \
share-worthy, DISTINCT stories to turn into Shorts today.

PRIMARY SOURCE — REAL CURRENT HEADLINES (choose from THESE; cluster items about the same event \
into ONE story):
{headlines}

SUPPLEMENTARY TREND SIGNAL (optional flavour only; ignore generic weather/calendar/sports-score noise):
{trending}

WINNING STYLES ON THIS CHANNEL (what the feed rewards; pick stories with similar pull — if empty, ignore):
{winners}

RULES:
- Pick {n} DISTINCT stories — NEVER two about the same event. Spread them across DIFFERENT \
categories (world affairs, economy & business, science & space, technology & AI, health, \
climate & energy, India infrastructure, government & policy, sports, notable world events).
- Prefer stories a smart person would actually SEND TO A FRIEND: real stakes, money & power, \
genuine surprise, big human impact. Apply a SHARE test, not a clickbait test.
- Compliance (hard line): only real, VERIFIABLE developments — a viewpoint is fine, an \
  unsourceable claim is not; exclude \
communal/religious incitement, calls to violence, unverified rumour-as-fact, deepfakes, \
graphic tragedy exploitation, medical/financial advice.

Return ONLY a JSON object:
{{"stories": [{{"story": "one-line description of the single development", "category": "...", \
"why_shareworthy": "why someone would share this"}}]}}
"""


def _select_stories(target: int, headlines: list[str], trending: list[str],
                    winners: list[str]) -> list[dict]:
    """Stage 1: cluster real headlines into `target` DISTINCT share-worthy stories.

    Cheap, no-web pass routed to Groq first (rule 13) so Gemini's scarce grounded RPD is
    reserved for Stage 2. Returns [] when there are no headlines or on any failure (rule 11),
    so the caller falls back to expanding from headlines directly.
    """
    if not headlines:
        return []
    prompt = _STAGE1_PROMPT.format(
        n=target,
        headlines="\n".join(f"- {h}" for h in headlines),
        trending="\n".join(f"- {t}" for t in trending) or "- (none)",
        winners="\n".join(f"- {w}" for w in winners) or "- (no performance data yet)",
    )
    try:
        raw = llm.generate(prompt, json=True, max_tokens=2048, prefer_groq=True)
        data = llm.parse_json(raw)
        stories = (data.get("stories", []) if isinstance(data, dict)
                   else data if isinstance(data, list) else [])
        out: list[dict] = []
        for s in stories:
            if isinstance(s, dict) and str(s.get("story", "")).strip():
                out.append({
                    "story": str(s["story"]).strip(),
                    "category": str(s.get("category", "")).strip(),
                    "why_shareworthy": str(s.get("why_shareworthy", "")).strip(),
                })
        return out[:target]
    except Exception as e:  # noqa: BLE001 — selection is best-effort; never block ideation
        log.warning("ideation: stage-1 story selection failed (%s); expanding from headlines", e)
        return []


def _produce_ideas(target: int) -> list[dict]:
    """Two-stage: select DISTINCT share-worthy stories (Stage 1), then expand them (Stage 2).

    Stage 1 (Groq) clusters real headlines into distinct stories — the anti-clustering /
    diversity mechanism. Stage 2 expands via Gemini Google Search grounding for current,
    well-sourced ideas, falling back to ungrounded generation if grounding is unavailable.
    Freshness survives a grounding outage because Stage 2 still expands real current headlines.
    """
    topics = trends.fetch_trending(15)
    trending_block = "\n".join(f"- {t}" for t in topics) or \
        "- (live trends unavailable — rely on the headlines below)"
    # Stories, not bare headlines: each carries the feed's own live article URL, which is what
    # lets an idea be cited from something we actually fetched instead of from model memory.
    feed_stories = news.fetch_stories(12)
    headlines = [s["title"] for s in feed_stories]
    headlines_block = "\n".join(f"- {h}" for h in headlines) or \
        "- (no live headlines — use your knowledge of today's biggest REAL stories)"
    try:
        winners = db.top_performing_titles(6)
    except Exception as e:  # noqa: BLE001 — analytics feedback is best-effort
        log.warning("ideation: could not load past winners (%s)", e)
        winners = []
    winners_block = "\n".join(f"- {w}" for w in winners) or "- (no performance data yet)"

    stories = _select_stories(target, headlines, topics, winners)
    if stories:
        selected_block = "\n".join(
            f"- {s['story']}" + (f" [{s['category']}]" if s["category"] else "")
            for s in stories
        )
    else:
        selected_block = ("- (no pre-selected stories — choose DISTINCT, current, "
                          "share-worthy stories yourself; never two on the same event)")

    prompt = _PROMPT.format(n=target, min_src=config.get("MIN_SOURCES", "2"),
                            selected=selected_block, trending=trending_block,
                            headlines=headlines_block, winners=winners_block)
    # Stage 2: web-grounded first, INCLUDING the parse — grounded JSON is sometimes
    # malformed/truncated, so any failure falls back to the reliable ungrounded JSON-mode call.
    clean: list[dict] = []
    try:
        raw, grounded = llm.generate_grounded_with_sources(prompt, max_tokens=8192,
                                                           model=_ideation_model())
        parsed = _parse_ideas(raw)
        clean = _validate_and_clean(_attach_real_sources(parsed, raw, grounded, feed_stories))
        if not clean:
            raise ValueError("grounded response yielded no valid ideas")
    except Exception as e:  # noqa: BLE001 — grounding is best-effort; never block ideation
        log.warning("ideation: grounded research unusable (%s); using ungrounded JSON mode", e)

    # Top up on a THIN result, not only an empty one. Accepting whatever the grounded pass
    # happened to yield is how a request for 3 ideas shipped a digest of 1 (STATUS 2026-09-01):
    # validation legitimately culls ideas, yet only a TOTAL grounded failure used to trigger the
    # second pass. Skipped entirely when grounding already met the target (rule 13).
    if len(clean) >= target:
        return clean
    log.info("ideation: grounded pass yielded %d of %d; topping up ungrounded.", len(clean), target)
    try:
        raw = llm.generate(prompt, json=True, max_tokens=4096)
        parsed = _attach_real_sources(_parse_ideas(raw), raw, [], feed_stories)
        clean = clean + _validate_and_clean(parsed, existing=clean)
    except Exception as e:  # noqa: BLE001 — the top-up is a bonus; keep what we already have
        log.warning("ideation: ungrounded top-up failed (%s); keeping %d idea(s)", e, len(clean))
    return clean[:_MAX_IDEAS]


def run_fallback_ideation() -> int:
    """Generate 15-20 ideas and insert them as 'pending'. Return the count inserted.

    Idempotent (rule 12): if pending ideas already exist, do nothing and return 0 — a cron
    retry must not stack a second digest.
    """
    if db.get_pending_ideas():
        log.info("ideation_fallback: pending ideas already exist; skipping (idempotent).")
        return 0

    clean = _produce_ideas(18)
    if len(clean) < _MIN_IDEAS:
        raise RuntimeError(
            f"ideation_fallback: only {len(clean)} valid ideas (need >= {_MIN_IDEAS}); "
            "not inserting a thin digest."
        )

    inserted = db.insert_ideas(_to_rows(clean))
    log.info("ideation_fallback: inserted %d pending ideas.", len(inserted))
    return len(inserted)


def generate_ideas(n: int = 3) -> int:
    """On-demand: generate the best ~n fresh ideas and insert as 'pending'. Return the count.

    Unlike run_fallback_ideation, this has NO pending-queue guard — an explicit on-demand
    request always produces fresh options (the operator picks via the digest buttons).
    """
    n = max(1, n)
    clean = sorted(_produce_ideas(max(n * 2, 4)), key=_rank_key)[:n]
    if not clean:
        raise RuntimeError("ideation: could not generate any valid idea.")
    inserted = db.insert_ideas(_to_rows(clean))
    log.info("ideation: generated %d on-demand idea(s).", len(inserted))
    return len(inserted)


def load_routine_ideas() -> list[dict]:
    """Load + validate ideas the daily Anthropic Routine committed to the repo. [] if none."""
    if not os.path.exists(_ROUTINE_IDEAS_FILE):
        return []
    try:
        with open(_ROUTINE_IDEAS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("ideation: could not read %s (%s)", _ROUTINE_IDEAS_FILE, e)
        return []
    ideas = raw.get("ideas", []) if isinstance(raw, dict) else raw
    return _validate_and_clean(ideas if isinstance(ideas, list) else [])


def _recent_ideas() -> list[dict]:
    try:
        return db.recent_ideas(int(config.get("IDEA_DEDUP_DAYS", "10")))
    except Exception as e:  # noqa: BLE001 — story dedup is a guard, not a dependency (rule 14)
        log.warning("ideation: could not load recent ideas for story dedup (%s)", e)
        return []


def _repeats_recent_story(idea: dict, recent: list[dict]) -> bool:
    """True if `idea` is a story already pitched in the last IDEA_DEDUP_DAYS, under any title.

    Title-only dedup let a story the fact-check had BLOCKED (314) return 47 minutes later under
    a new title (315) and ship the same claim; the Telegram/NEET story came back three times.
    A shared source link, or the same distinctive words, is the same story. Rejected, blocked,
    produced or still pending, it does not come back."""
    mine_src = {u for u in _clean_sources(idea.get("sources")) if not _is_homepage(u)}
    mine = _tokens(f"{idea.get('title', '')} {idea.get('hook', '')}")
    for old in recent:
        theirs_src = {u for u in _clean_sources(old.get("sources")) if not _is_homepage(u)}
        shared_src = mine_src & theirs_src
        theirs = _tokens(f"{old.get('title', '')} {old.get('hook', '')}")
        shared = mine & theirs
        same_words = (mine and theirs and len(shared) >= _STORY_MATCH_MIN_TOKENS + 1
                      and len(shared) / min(len(mine), len(theirs)) >= _STORY_MATCH_RATIO)
        if shared_src or same_words:
            log.info("ideation: %r repeats recent idea %s (%s, %s); skipped.", idea.get("title"),
                     old.get("id"), old.get("status"), "same source" if shared_src else "same story")
            return True
    return False


def seed_ideas(n: int = 3) -> int:
    """Seed ~n fresh 'pending' ideas for the on-demand digest. Return the count inserted.

    Prefers the daily Routine's web-researched ideas (data/daily-ideas.json); falls back to
    the Gemini/Groq generator when that file is absent/empty. De-duplicates against ideas
    already in the table so repeated triggers don't re-propose the same ones.
    """
    n = max(1, n)
    routine = load_routine_ideas()
    pool = routine if routine else _produce_ideas(max(n * 2, 4))
    source = "routine file" if routine else "gemini/groq fallback"

    seen = db.existing_idea_titles()
    recent = _recent_ideas()
    pool = [i for i in pool if not _repeats_recent_story(i, recent)]
    fresh = sorted((i for i in pool if i["title"].lower() not in seen), key=_rank_key)[:n]
    if not fresh:
        raise RuntimeError(f"ideation: no fresh ideas to seed (source: {source}).")
    log.info("ideation: seeding %d idea(s) from %s.", len(fresh), source)
    return len(db.insert_ideas(_to_rows(fresh)))
