# Ideation Diversity & Virality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ideation produce diverse, fresh, share-worthy topics instead of similar/stale ones, by anchoring on the real news feed and selecting distinct stories before expanding them.

**Architecture:** Replace the single batch LLM call with a two-stage flow — Stage 1 (cheap, Groq) clusters real headlines into N *distinct* share-worthy stories; Stage 2 (Gemini grounded → ungrounded fallback) expands them into ideas. Add a `share_score` virality bar, a token-overlap dedup backstop, and a trends noise filter. `share_score` is used for ranking only and is NOT persisted (rows are projected to existing DB columns).

**Tech Stack:** Python 3.13, `google-genai` (Gemini grounding), `groq`, Supabase (`supabase-py`), pytest. Free-tier LLMs only.

## Global Constraints

- **Rule 3 — No self-attribution** in any commit/PR/comment/doc (no `Co-Authored-By`, no "Generated with Claude").
- **Rule 4 — ToS:** ideation uses the Gemini/Groq DEVELOPER APIs only, never Claude.
- **Rule 6 — Compliance gate (hard guards, never relaxed):** only real verifiable developments; ≥ `MIN_SOURCES` (2) real source URLs per idea; strictly neutral framing; exclude communal/religious incitement, calls to violence, unverified rumour-as-fact, deepfakes, graphic tragedy exploitation, medical/financial advice.
- **Rule 11/14 — Fallbacks mandatory, soft on runtime:** trends/news return `[]` on failure; Stage 1 failure → expand from headlines directly; Stage 2 grounded failure → ungrounded expansion. Ideation never dies on one upstream failure.
- **Rule 13 — Quota:** Stage 1 uses `prefer_groq=True` to spare Gemini's scarce free RPD; Stage 2 keeps the grounded Gemini call. ~2 LLM calls/run total.
- **No DB schema change, no workflow change.** Inserted rows contain exactly: `niche, title, hook, angle, est_score, sources`.
- **Conventional commits** (rule 18); keep `STATUS.md` + `CHANGELOG.md` current.
- **Run tests with** `.venv/Scripts/python.exe -m pytest` (Windows venv).

---

## File Structure

- `src/trends.py` — add a best-effort noise filter; demote trends to a supplementary signal.
- `src/ideation_fallback.py` — two-stage `_produce_ideas`, `_select_stories`, `share_score` in `_validate_and_clean`, `_to_rows` projection, `_rank_key`, dedup backstop, rewritten prompts.
- `tests/test_trends.py` — noise-filter case; update the limit test (its sample contains a now-filtered "vs" item).
- `tests/test_ideation_fallback.py` — new cases for selection, share_score ranking, dedup backstop, row projection; existing cases stay green.

---

### Task 1: Trends noise filter

**Files:**
- Modify: `src/trends.py`
- Test: `tests/test_trends.py`

**Interfaces:**
- Produces: `trends._is_noise(topic: str) -> bool`; `trends.fetch_trending(limit)` now returns only non-noise topics.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_trends.py`:

```python
def test_is_noise_filters_junk():
    assert trends._is_noise("weather winter storm warning")
    assert trends._is_noise("june 2026 calendar")
    assert trends._is_noise("germany vs paraguay")
    assert trends._is_noise("snana purnima 2026")
    assert not trends._is_noise("ISRO launch")
    assert not trends._is_noise("Budget 2026")


def test_fetch_trending_drops_noise(monkeypatch):
    rss = (
        '<?xml version="1.0"?><rss><channel><title>Trends</title>'
        '<item><title>shimla weather</title></item>'
        '<item><title>ISRO launch</title></item>'
        '<item><title>germany vs paraguay</title></item>'
        '<item><title>Budget 2026</title></item>'
        '</channel></rss>'
    )
    class _Resp:
        text = rss
        def raise_for_status(self): pass
    monkeypatch.setattr(trends.requests, "get", lambda *a, **k: _Resp())
    assert trends.fetch_trending() == ["ISRO launch", "Budget 2026"]
```

- [ ] **Step 2: Update the existing limit test (its sample now contains a filtered item)**

In `tests/test_trends.py`, `test_fetch_trending_limits` currently expects `["India vs Australia", "ISRO launch"]`, but `"India vs Australia"` is now filtered (`vs` matchup). Replace its assertion:

```python
def test_fetch_trending_limits(monkeypatch):
    class _Resp:
        text = _RSS
        def raise_for_status(self):
            pass
    monkeypatch.setattr(trends.requests, "get", lambda *a, **k: _Resp())
    # "India vs Australia" is now filtered as sports-matchup noise; first two survivors:
    assert trends.fetch_trending(limit=2) == ["ISRO launch", "Budget 2026"]
```

(`test_parse_extracts_item_titles_only` is unchanged — it tests `_parse` directly, which does not filter.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_trends.py -v`
Expected: FAIL — `_is_noise` not defined; `test_fetch_trending_drops_noise` / `test_fetch_trending_limits` fail.

- [ ] **Step 4: Implement the filter**

In `src/trends.py`, add `import re` near the top (after `import logging`), and add above `fetch_trending`:

```python
# Generic search-trend noise that is never an impact-news story (best-effort, tunable).
# Trends are only a SUPPLEMENTARY flavour signal now (news is the primary anchor), so
# over-filtering here is acceptable — the news feed carries the real stories.
_NOISE_SUBSTRINGS = (
    "weather", "storm", "temperature", "forecast", "calendar", "horoscope",
    "rashifal", "panchang", "purnima", "ekadashi", "amavasya", "predictor",
    "dream11", "fantasy xi", "live score", "scorecard", "lottery", "result today",
)
_NOISE_PATTERNS = (
    re.compile(r"\bvs\.?\b", re.I),   # "X vs Y" sports/match matchups
    re.compile(r"\bv/s\b", re.I),
)


def _is_noise(topic: str) -> bool:
    """True for generic search noise (weather/calendar/sports-score) that isn't a story."""
    low = topic.lower()
    if any(s in low for s in _NOISE_SUBSTRINGS):
        return True
    return any(p.search(topic) for p in _NOISE_PATTERNS)
```

Then in `fetch_trending`, change the parse line to filter:

```python
        topics = [t for t in _parse(resp.text) if not _is_noise(t)]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_trends.py -v`
Expected: PASS (all trends tests).

- [ ] **Step 6: Commit**

```bash
git add src/trends.py tests/test_trends.py
git commit -m "feat(trends): filter generic search noise; demote trends to supplementary signal"
```

---

### Task 2: `share_score` validation + DB-row projection

**Files:**
- Modify: `src/ideation_fallback.py`
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Produces: `_validate_and_clean` now attaches `"share_score"` (float 0–1, defaults to `est_score` when absent) to each clean idea. `_to_rows(ideas: list[dict]) -> list[dict]` projects each idea to exactly `niche, title, hook, angle, est_score, sources` (drops `share_score`). `_ROW_KEYS` tuple.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ideation_fallback.py`:

```python
def test_validate_adds_share_score_default_to_est(monkeypatch):
    out = fb._validate_and_clean([_idea("A", est_score=0.8)])
    assert out[0]["share_score"] == 0.8  # defaults to est_score when model omits it


def test_validate_share_score_coerced_and_clamped():
    out = fb._validate_and_clean([
        _idea("A", share_score=5.0),
        _idea("B", share_score="nope", est_score=0.4),
    ])
    by = {r["title"]: r["share_score"] for r in out}
    assert by["A"] == 1.0 and by["B"] == 0.4  # clamp high; bad value -> est_score


def test_to_rows_projects_to_db_columns_only():
    ideas = fb._validate_and_clean([_idea("A", share_score=0.9)])
    rows = fb._to_rows(ideas)
    assert set(rows[0]) == {"niche", "title", "hook", "angle", "est_score", "sources"}
    assert "share_score" not in rows[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -k "share_score or to_rows" -v`
Expected: FAIL — `_to_rows` not defined; `share_score` not in cleaned output.

- [ ] **Step 3: Implement share_score + projection**

In `src/ideation_fallback.py`, inside `_validate_and_clean`, after the `est` clamp block, add the share_score parse, and include it in the appended dict:

```python
        try:
            share = float(idea.get("share_score", est))
        except (TypeError, ValueError):
            share = est
        share = min(1.0, max(0.0, share))

        seen_titles.add(title.lower())
        clean.append({"niche": niche, "title": title, "hook": hook, "angle": angle,
                      "est_score": est, "share_score": share, "sources": sources})
```

Add near the module constants (after `_MIN_IDEAS`):

```python
# Columns the `ideas` table actually has — `share_score` is ranking-only, never persisted.
_ROW_KEYS = ("niche", "title", "hook", "angle", "est_score", "sources")


def _to_rows(ideas: list[dict]) -> list[dict]:
    """Project validated ideas to the DB columns (drops ranking-only fields like share_score)."""
    return [{k: idea[k] for k in _ROW_KEYS} for idea in ideas]
```

- [ ] **Step 4: Wire the three insert sites through `_to_rows`**

In `run_fallback_ideation`, change the insert:

```python
    inserted = db.insert_ideas(_to_rows(clean))
```

In `generate_ideas`, change the insert:

```python
    inserted = db.insert_ideas(_to_rows(clean))
```

In `seed_ideas`, change the insert:

```python
    return len(db.insert_ideas(_to_rows(fresh)))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -v`
Expected: PASS. (`test_inserts_valid_ideas` still asserts exactly the 6 row keys — projection preserves that.)

- [ ] **Step 6: Commit**

```bash
git add src/ideation_fallback.py tests/test_ideation_fallback.py
git commit -m "feat(ideation): add share_score virality field; project rows to DB columns"
```

---

### Task 3: Token-overlap dedup backstop

**Files:**
- Modify: `src/ideation_fallback.py`
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Produces: `_tokens(title: str) -> set[str]`; `_validate_and_clean` rejects a candidate whose token-set Jaccard overlap with any already-kept idea is ≥ 0.6 (same-story near-duplicate).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ideation_fallback.py`:

```python
def test_dedup_backstop_drops_same_story_near_duplicate():
    ideas = [
        _idea("ISRO launches new navigation satellite NVS-02"),
        _idea("ISRO launches new navigation satellite today"),  # same story, reworded
        _idea("RBI cuts repo rate by 25 basis points"),
    ]
    out = fb._validate_and_clean(ideas)
    titles = [o["title"] for o in out]
    assert "RBI cuts repo rate by 25 basis points" in titles
    assert len(titles) == 2  # one of the two ISRO near-duplicates dropped


def test_dedup_backstop_keeps_distinct_short_titles():
    # synthetic distinct titles (used widely in other tests) must NOT be over-merged
    out = fb._validate_and_clean([_idea(f"Idea {i}") for i in range(6)])
    assert len(out) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -k dedup_backstop -v`
Expected: FAIL — both ISRO ideas kept (3 returned, not 2).

- [ ] **Step 3: Implement the backstop**

In `src/ideation_fallback.py`, add `import re` (top, after `import os`) and add near the constants:

```python
# Tiny stopword set so near-identical titles overlap on meaningful words, not glue words.
_STOPWORDS = {"the", "a", "an", "of", "to", "in", "for", "and", "is", "on", "with",
              "at", "by", "from", "as", "new", "today"}


def _tokens(title: str) -> set[str]:
    """Significant lowercased word tokens of a title (numbers kept, stopwords dropped)."""
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOPWORDS}
```

In `_validate_and_clean`, before the loop add a kept-tokens accumulator:

```python
    kept_tokens: list[set[str]] = []
```

Inside the loop, after the exact-title dedup (`if title.lower() in seen_titles: continue`) and before source validation, add the overlap check:

```python
        toks = _tokens(title)
        if toks and any(
            len(toks & kt) / len(toks | kt) >= 0.6 for kt in kept_tokens
        ):
            log.debug("ideation_fallback: dropping near-duplicate %r", title)
            continue
```

Then, where the idea is accepted (right after `seen_titles.add(title.lower())`), record its tokens:

```python
        kept_tokens.append(toks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -v`
Expected: PASS (new dedup tests + all existing).

- [ ] **Step 5: Commit**

```bash
git add src/ideation_fallback.py tests/test_ideation_fallback.py
git commit -m "feat(ideation): token-overlap dedup backstop for same-story near-duplicates"
```

---

### Task 4: Stage-1 distinct-story selection

**Files:**
- Modify: `src/ideation_fallback.py`
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Produces: `_STAGE1_PROMPT` (str); `_select_stories(target: int, headlines: list[str], trending: list[str], winners: list[str]) -> list[dict]` returning `[{"story","category","why_shareworthy"}]`. Returns `[]` when there are no headlines or on any failure (rule 11). Uses `llm.generate(prefer_groq=True, json=True)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ideation_fallback.py`:

```python
def test_select_stories_parses_distinct_stories(monkeypatch):
    payload = {"stories": [
        {"story": "West Asia ceasefire talks", "category": "world", "why_shareworthy": "war stakes"},
        {"story": "Weakest monsoon in 17 years", "category": "climate", "why_shareworthy": "food prices"},
    ]}
    seen = {}
    def _gen(prompt, **kw):
        seen.update(kw)
        return json.dumps(payload)
    monkeypatch.setattr(fb.llm, "generate", _gen)
    out = fb._select_stories(2, ["West Asia ceasefire - The Hindu", "Monsoon fails - PTI"], [], [])
    assert [s["story"] for s in out] == ["West Asia ceasefire talks", "Weakest monsoon in 17 years"]
    assert seen.get("prefer_groq") is True  # spares Gemini RPD (rule 13)


def test_select_stories_empty_without_headlines(monkeypatch):
    monkeypatch.setattr(fb.llm, "generate",
                        lambda *a, **k: pytest.fail("must not call LLM with no headlines"))
    assert fb._select_stories(3, [], ["ISRO"], []) == []


def test_select_stories_returns_empty_on_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("groq down")
    monkeypatch.setattr(fb.llm, "generate", _boom)
    assert fb._select_stories(3, ["a headline"], [], []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -k select_stories -v`
Expected: FAIL — `_select_stories` / `_STAGE1_PROMPT` not defined.

- [ ] **Step 3: Implement Stage 1**

In `src/ideation_fallback.py`, add the prompt (near `_PROMPT`):

```python
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
- Compliance (hard line): only real, verifiable developments; neutral framing; exclude \
communal/religious incitement, calls to violence, unverified rumour-as-fact, deepfakes, \
graphic tragedy exploitation, medical/financial advice.

Return ONLY a JSON object:
{{"stories": [{{"story": "one-line description of the single development", "category": "...", \
"why_shareworthy": "why someone would share this"}}]}}
"""
```

Add the function (above `_produce_ideas`):

```python
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
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1], strict=False)
        stories = data.get("stories", []) if isinstance(data, dict) else []
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -k select_stories -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ideation_fallback.py tests/test_ideation_fallback.py
git commit -m "feat(ideation): stage-1 distinct share-worthy story selection (Groq)"
```

---

### Task 5: Two-stage `_produce_ideas` + prompt rewrite + share-first ranking

**Files:**
- Modify: `src/ideation_fallback.py`
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Consumes: `_select_stories` (Task 4), `_validate_and_clean`/`_to_rows`/`share_score` (Task 2).
- Produces: rewritten `_PROMPT` with a `{selected}` block (still contains "honest", "why it matters", "scroll"); `_produce_ideas` calls Stage 1 then Stage 2 (grounded → ungrounded); `_rank_key(idea) -> tuple` used by `generate_ideas` and `seed_ideas` to rank `share_score`-first, `est_score`-second.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ideation_fallback.py`:

```python
def test_produce_ideas_runs_two_stages(monkeypatch):
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_headlines", lambda *a, **k: ["Real headline - PTI"])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    calls = {"select": 0}
    def _sel(target, headlines, trending, winners):
        calls["select"] += 1
        return [{"story": "Story X", "category": "world", "why_shareworthy": "stakes"}]
    monkeypatch.setattr(fb, "_select_stories", _sel)
    captured = {}
    def _grounded(prompt, **k):
        captured["prompt"] = prompt
        return json.dumps({"ideas": [_idea("Expanded", share_score=0.9)]})
    monkeypatch.setattr(fb.llm, "generate_grounded", _grounded)
    out = fb._produce_ideas(3)
    assert calls["select"] == 1
    assert out and out[0]["title"] == "Expanded"
    assert "Story X" in captured["prompt"]  # selected story flowed into Stage 2


def test_rank_key_orders_by_share_then_est():
    a = {"title": "a", "est_score": 0.9, "share_score": 0.2}
    b = {"title": "b", "est_score": 0.1, "share_score": 0.8}
    assert sorted([a, b], key=fb._rank_key)[0]["title"] == "b"  # higher share wins


def test_generate_ideas_ranks_by_share_score(monkeypatch):
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    ideas = [
        _idea("Low share", est_score=0.9, share_score=0.1),
        _idea("High share", est_score=0.2, share_score=0.9),
        _idea("Mid share", est_score=0.5, share_score=0.5),
    ]
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: fb._validate_and_clean(ideas))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas",
                        lambda rows: captured.setdefault("rows", rows) or rows)
    fb.generate_ideas(2)
    assert [r["title"] for r in captured["rows"]] == ["High share", "Mid share"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py -k "two_stages or rank" -v`
Expected: FAIL — `_rank_key` not defined; `_produce_ideas` doesn't call `_select_stories`; `{selected}` not in prompt.

- [ ] **Step 3: Rewrite `_PROMPT` (Stage 2)**

In `src/ideation_fallback.py`, replace the existing `_PROMPT = """..."""` block with:

```python
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

ACCURACY (CRITICAL — this is the #1 rule): propose only REAL, verifiable developments that \
ACTUALLY happened recently. NEVER invent product names, version numbers, launches, statistics, \
quotes, or events, and never attribute a claim to a company/person unless it's real. If unsure a \
thing genuinely happened, DO NOT make it up — choose a different real story. When unsure, \
generalize truthfully rather than invent specifics. Fabricated news = instant demonetization and strikes.

FRAMING RULES (monetization safety): strictly NEUTRAL and factual — explain what happened and \
why it matters; never take political sides or editorialize. Politics, government actions, and \
court rulings ARE allowed when covered neutrally and well-sourced. EXCLUDE only: communal/ \
religious incitement or hate; anything that could inflame violence; unverified rumors/claims \
stated as fact; deepfakes/impersonation; graphic tragedy exploitation; medical/financial advice \
stated as fact.

Each idea: a PUNCHY, curiosity-driven title honest to the story (NOT a dry "X explained" search \
title, NOT a bait title the facts can't back); a story that lands in 25-30 seconds (a single \
development with a sharp angle, not a deep-dive); >= {min_src} reputable, independent source URLs \
from real outlets (never invent URLs); a "hook" that is a genuine first-2-seconds scroll-stopper \
(one surprising true fact); and a share_score.

Return ONLY JSON:
{{"ideas": [{{"niche": "impact-news", "title": "...", "hook": "the first 3 seconds", \
"angle": "the original why-it-matters take", "est_score": 0.0, "share_score": 0.0, \
"sources": ["https://...", "https://..."]}}]}}
"""
```

- [ ] **Step 4: Rewrite `_produce_ideas` to call Stage 1 then Stage 2**

Replace the body of `_produce_ideas` with:

```python
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
    headlines = news.fetch_headlines(12)
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
    # Stage 2: web-grounded first (incl. the parse — grounded JSON is sometimes malformed),
    # any failure falls back to the reliable ungrounded JSON-mode call.
    try:
        raw = llm.generate_grounded(prompt, max_tokens=8192)
        ideas = _validate_and_clean(_parse_ideas(raw))
        if ideas:
            return ideas
        raise ValueError("grounded response yielded no valid ideas")
    except Exception as e:  # noqa: BLE001 — grounding is best-effort; never block ideation
        log.warning("ideation: grounded research unusable (%s); using ungrounded JSON mode", e)

    raw = llm.generate(prompt, json=True, max_tokens=4096)
    return _validate_and_clean(_parse_ideas(raw))
```

- [ ] **Step 5: Add `_rank_key` and use it for ranking**

Add near the constants:

```python
def _rank_key(idea: dict):
    """Sort key: share_score first (virality), est_score as tiebreaker. Highest first."""
    return (-idea.get("share_score", idea["est_score"]), -idea["est_score"])
```

In `generate_ideas`, replace the sort:

```python
    clean = sorted(_produce_ideas(max(n * 2, 4)), key=_rank_key)[:n]
```

In `seed_ideas`, replace the `fresh = sorted(...)` line:

```python
    fresh = sorted((i for i in pool if i["title"].lower() not in seen), key=_rank_key)[:n]
```

- [ ] **Step 6: Run the full ideation + trends suites**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ideation_fallback.py tests/test_trends.py -v`
Expected: PASS (new two-stage/ranking tests + all existing, including `test_ideation_prompt_dehyped`, `test_seed_ideas_prefers_routine_file`, `test_produce_ideas_falls_back_*`).

- [ ] **Step 7: Commit**

```bash
git add src/ideation_fallback.py tests/test_ideation_fallback.py
git commit -m "feat(ideation): two-stage news-anchored generation + share-first ranking"
```

---

### Task 6: Full suite + docs

**Files:**
- Modify: `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (prior green count + the new tests; the gated live ideation test may skip offline/quota).

- [ ] **Step 2: Update STATUS.md**

Add a dated log entry at the top of the `## Log` section summarizing: trends noise filter; two-stage news-anchored ideation (Stage 1 distinct-story selection via Groq → Stage 2 grounded expansion); `share_score` virality bar + share-first ranking; token-overlap dedup backstop; no DB/workflow change; new test count. Update the **Version** line and `Last updated` date.

- [ ] **Step 3: Update CHANGELOG.md**

Add an entry under a new `## [Unreleased]` (or the next version) `### Added`/`### Changed` describing the same, Keep-a-Changelog style.

- [ ] **Step 4: Commit**

```bash
git add STATUS.md CHANGELOG.md
git commit -m "docs(ideation): log diversity/virality two-stage ideation"
```

---

## Self-Review Notes

- **Spec coverage:** Component 1 → Task 1; Component 2 → Tasks 4–5; Component 3 → Tasks 2–3; Component 4 → Tasks 1 & 5 (prompts). Testing section → tests in every task. Cost/quota → Task 4 (`prefer_groq`). Error handling → Tasks 4 (`[]` fallbacks) & 5 (grounded→ungrounded).
- **No-schema-change guard:** `share_score` is ranking-only and stripped by `_to_rows` before every insert (Task 2) — keeps the `ideas` table and `test_inserts_valid_ideas` unchanged.
- **Existing-test safety:** Stage 1 only fires when headlines are present, so the `_patch`-based tests (headlines `[]`) and the grounding-fallback tests are unaffected. The dedup threshold (0.6) keeps synthetic distinct titles (`Idea 0`…`Idea 5`, `n0`…`n29`) intact (verified: Jaccard 1/3 < 0.6).
- **Type consistency:** `_select_stories` returns `{story,category,why_shareworthy}`; `_produce_ideas` reads `s['story']`/`s['category']`. `_rank_key`/`_validate_and_clean`/`_to_rows` share the `share_score` key. `_ROW_KEYS` is the single source of the DB column set.
