# Phase C — Metadata SEO trims + operator "angle" lever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten YouTube metadata for discoverability (8–12 tags, main keyword first) and add a light, optional operator "angle/hot-take" that the scriptwriter weaves into the why-it-matters beat — the final pieces of the 2026 content-quality overhaul (spec: `docs/superpowers/specs/2026-06-15-content-quality-overhaul-design.md`, sections 3.5 + 3.6).

**Architecture:** Two small, independent changes. (1) `production._build_metadata` reorders + caps tags; the scriptwriter asks for 8–12 tags. (2) A **batch-level** `EPISODE_ANGLE` setting (env / make-short workflow input) is injected into the script prompt — zero DB/webhook surface, fail-soft, default off. The richer **per-idea Telegram-reply** hot-take is documented as a future extension (needs DB + webhook work), intentionally deferred (YAGNI).

**Tech Stack:** Python 3, existing `src.config`/`src.production`/`src.scriptwriter`, GitHub Actions, `pytest`.

**Project rules that bind this plan:** Conventional commits, **no AI self-attribution** (CLAUDE.md rule 3); update STATUS.md + CHANGELOG at the end (rule 1); fail-soft on runtime (rule 14); start on a feature branch off `main` (e.g. `feat/phase-c-metadata-angle`).

---

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/production.py` | Modify | `_build_metadata`: tags = SEO-tags-first + hashtags, deduped, capped to `MAX_TAGS` (12). |
| `src/scriptwriter.py` | Modify | Prompt: tags "10-15" → "8-12"; inject optional `EPISODE_ANGLE` in `_build_prompt`. |
| `tests/test_production.py` | Modify | Update the merge-order test; add the cap test. |
| `tests/test_scriptwriter.py` | Modify | Add `EPISODE_ANGLE` injection on/off tests. |
| `.env.example` | Modify | Document `MAX_TAGS`, `EPISODE_ANGLE`. |
| `.github/workflows/make-short.yml` | Modify | New `angle` input → `EPISODE_ANGLE`; pass `MAX_TAGS`. |
| `.github/workflows/production.yml` | Modify | Pass `EPISODE_ANGLE` (repo var) + `MAX_TAGS`. |
| `STATUS.md`, `CHANGELOG.md` | Modify | Log Phase C; bump to v0.5.0. |

---

## Task 1: Metadata SEO trims (main keyword first, ≤12 tags)

**Files:** Modify `src/production.py`, `src/scriptwriter.py`; Test `tests/test_production.py`.

### Design notes
Research: 8–12 tags, the FIRST tag carries the most weight, >15 dilutes. The scriptwriter already orders `tags` most-important-first, but `_build_metadata` currently lists `hashtags` *before* `tags`, so the first tag ends up being a hashtag like "Shorts". Fix: put SEO `tags` first, then hashtags, dedupe, cap to `MAX_TAGS` (default 12).

- [ ] **Step 1: Update the failing metadata test**

In `tests/test_production.py`, replace `test_build_metadata_prefers_seo_title_and_merges_tags` with the new order + a cap test:

```python
def test_build_metadata_prefers_seo_title_and_merges_tags():
    idea = {"title": "fallback title"}
    script = {"title": "SEO Title", "caption": "desc",
              "hashtags": ["#ISRO", "#Shorts"], "tags": ["isro", "space mission", "rocket"]}
    meta = production._build_metadata(idea, script)
    assert meta["title"] == "SEO Title"
    # SEO tags FIRST (main keyword leads), then hashtags(#-stripped), de-duped, order preserved
    assert meta["tags"] == ["isro", "space mission", "rocket", "Shorts"]


def test_build_metadata_caps_tags(monkeypatch):
    monkeypatch.setenv("MAX_TAGS", "3")
    script = {"title": "T", "caption": "c", "hashtags": ["#a", "#b"],
              "tags": ["one", "two", "three", "four", "five"]}
    meta = production._build_metadata({"title": "T"}, script)
    assert meta["tags"] == ["one", "two", "three"]   # capped, SEO tags first
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_production.py -k "build_metadata" -v`
Expected: `test_build_metadata_prefers_seo_title_and_merges_tags` FAILS (current order is hashtags-first → `["ISRO","Shorts","space mission","rocket"]`); `test_build_metadata_caps_tags` FAILS (no cap).

- [ ] **Step 3: Implement the reorder + cap in `src/production.py`**

Replace the `_build_metadata` body's tag-merge loop:

```python
def _build_metadata(idea: dict, script: dict) -> dict:
    """Map an idea + its script into YouTube upload metadata (publish enforces disclosure/#Shorts).

    Prefers the scriptwriter's SEO title; merges SEO tags FIRST (main keyword leads — highest
    weight) then hashtags, de-duped, capped to MAX_TAGS (research: 8-12, >15 dilutes).
    """
    title = (script.get("title") or idea.get("title") or "").strip()
    seen, tags = set(), []
    for t in [*script.get("tags", []), *script.get("hashtags", [])]:
        t = str(t).lstrip("#").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    try:
        cap = int(config.get("MAX_TAGS", "12"))
    except (TypeError, ValueError):
        cap = 12
    tags = tags[:max(1, cap)]
    return {"title": title, "description": _with_footer(script.get("caption", "")), "tags": tags}
```

(`config` is already imported in `production.py`.)

- [ ] **Step 4: Lower the scriptwriter tag count to 8–12**

In `src/scriptwriter.py` `_PROMPT_N`, change the tags bullet:

```python
- "tags": 8-12 specific search keywords/phrases people would actually type (the topic, the \
people/orgs involved, the category, and close synonyms), MOST IMPORTANT FIRST. No '#'.
```

- [ ] **Step 5: Run the production suite**

Run: `python -m pytest tests/test_production.py -v`
Expected: PASS (both metadata tests green; the rest unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/production.py src/scriptwriter.py tests/test_production.py
git commit -m "feat(seo): SEO tags first + cap to 12 (MAX_TAGS); scriptwriter asks for 8-12"
```

---

## Task 2: Optional operator "angle / hot-take" lever (batch-level)

**Files:** Modify `src/scriptwriter.py`; Test `tests/test_scriptwriter.py`.

### Design notes
A single optional `EPISODE_ANGLE` string (set per run via the make-short workflow input, or a repo var for the cron). When present, it's appended to the script prompt so the scriptwriter weaves the operator's genuine take into the why-it-matters beat — extra originality / the anti-"AI-slop" human signal. Default off (empty); accuracy hard-line unchanged. Applies to the whole batch (simple, no DB/webhook). Per-idea is a future extension (below).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scriptwriter.py`:

```python
def test_episode_angle_injected_when_set(monkeypatch):
    monkeypatch.setenv("EPISODE_ANGLE", "the real story is who pays for it")
    prompt = scriptwriter._build_prompt(IDEA, "N").lower()
    assert "operator's angle" in prompt
    assert "who pays for it" in prompt


def test_episode_angle_absent_by_default(monkeypatch):
    monkeypatch.delenv("EPISODE_ANGLE", raising=False)
    prompt = scriptwriter._build_prompt(IDEA, "N").lower()
    assert "operator's angle" not in prompt
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_scriptwriter.py -k "episode_angle" -v`
Expected: `..._injected...` FAILS (no such text); `..._absent...` PASSES (already absent).

- [ ] **Step 3: Inject `EPISODE_ANGLE` in `src/scriptwriter.py` `_build_prompt`**

After the existing `ENABLE_HUMAN_ANGLE` block, before `return prompt`:

```python
    angle = (config.get("EPISODE_ANGLE") or "").strip()
    if angle:
        prompt += ("\n\nOPERATOR'S ANGLE FOR TODAY (weave this specific human take into the "
                   "\"why it matters\" — every FACT must still be accurate): " + angle)
    return prompt
```

- [ ] **Step 4: Run the scriptwriter suite**

Run: `python -m pytest tests/test_scriptwriter.py -v`
Expected: PASS (both new tests + all existing).

- [ ] **Step 5: Commit**

```bash
git add src/scriptwriter.py tests/test_scriptwriter.py
git commit -m "feat(content): optional EPISODE_ANGLE operator hot-take injected into the script"
```

---

## Task 3: Wire config + workflows; docs; full suite

**Files:** `.env.example`, both workflows, `STATUS.md`, `CHANGELOG.md`.

- [ ] **Step 1: `.env.example`**

Add under Config:

```bash
MAX_TAGS=12                         # cap on YouTube tags (research: 8-12; first tag = main keyword)
EPISODE_ANGLE=                      # optional: a one-line operator take woven into every script this run
```

- [ ] **Step 2: `make-short.yml` — new input + env**

Add an input under `workflow_dispatch.inputs`:

```yaml
      angle:
        description: "Optional: your one-line take/angle for today's batch"
        default: ""
        required: false
```

And in the job `env:` block:

```yaml
          MAX_TAGS: ${{ vars.MAX_TAGS || '12' }}
          EPISODE_ANGLE: ${{ inputs.angle }}
```

- [ ] **Step 3: `production.yml` — env**

In the job `env:` block:

```yaml
          MAX_TAGS: ${{ vars.MAX_TAGS || '12' }}
          EPISODE_ANGLE: ${{ vars.EPISODE_ANGLE }}
```

- [ ] **Step 4: Full suite**

Run: `python -m pytest -q`
Expected: all green (171 + 4 new = 175 passed, 2 skipped). Do not proceed on red (rule 8).

- [ ] **Step 5: STATUS.md + CHANGELOG.md → v0.5.0**

Bump the STATUS version line to `0.5.0` with the new test count; add a STATUS log entry (Phase C: SEO tag order/cap + EPISODE_ANGLE lever). Add a `## [0.5.0] — <date> — Phase C: metadata SEO + operator angle lever` CHANGELOG section.

- [ ] **Step 6: Commit**

```bash
git add .env.example .github/workflows/ STATUS.md CHANGELOG.md
git commit -m "chore(phase-c): wire MAX_TAGS/EPISODE_ANGLE into workflows; docs to v0.5.0"
```

---

## Future extension (NOT in this plan — deferred, YAGNI)

**Per-idea Telegram hot-take.** Richer than the batch-level `EPISODE_ANGLE`: the operator replies to a specific idea's digest message with a take, and only that reel uses it. Requires:
1. `ideas.operator_note` (nullable text) + `ideas.digest_message_id` (to map a reply → idea) — a Supabase migration + `db` helpers.
2. `approval.send_digest` storing each sent `message_id` on its idea.
3. The Vercel webhook (`telegram-bot/api/telegram.py`) + polling `approval.process_responses` detecting a `message` with `reply_to_message` and writing `operator_note`.
4. `scriptwriter.write_script` preferring `idea["operator_note"]` over `EPISODE_ANGLE`.

**Data-viz / maps.** Generate a simple chart (from numeric `key_points`) or a static map for impact stories, as an extra clip. Needs a headless chart dep (e.g. matplotlib) — weigh against the dep/render cost; likely its own small spec first.

---

## Self-review
- **Spec coverage:** 3.5 metadata → Task 1; 3.6 lever → Task 2 (batch-level) + Future (per-idea). Data-viz stretch → Future.
- **No placeholders:** every code/test/command step is concrete. The deferred items are explicitly out of scope, not half-specified inline.
- **Test-order safety:** Task 1 Step 1 rewrites the one test whose expectation changes (hashtags-first → tags-first); all other existing tests are unaffected by the reorder/cap.
- **Naming consistency:** `MAX_TAGS`, `EPISODE_ANGLE` used identically across scriptwriter, production, `.env.example`, and both workflows.
