# Stage 0: Safety and Measuring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the design's Stage 0: fixes that protect every reel (one sentence splitter, the opening check, FFmpeg timeouts) and the measurement the relaunch will be judged by (format stamp, one row per attempt, YouTube Analytics per Short, the upload read-back, the audio language, "Published" per reel), plus the bot's argument fix.

**Architecture:** Small changes inside the existing modules, plus one new helper module (`src/text.py`). Every new database write is tolerant: until the operator runs the new SQL, a missing column or table is logged once per run and skipped, never costing a reel. No new format yet: reels stay English with the `ai` visuals.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, supabase-py (PostgREST), google-api-python-client (YouTube Data v3 and YouTube Analytics v2), FFmpeg.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md), sections 9.2, 9.9, 10, 11.6 (timeouts), 13, 14 (stage 0), 8.6.

## Global Constraints

- No new Python dependency; nothing in `requirements.txt` changes.
- Unit tests never reach a live service: the `tests/conftest.py` guards stay, and new code is tested with fakes.
- Rule 14: misconfiguration fails loud; anything at runtime fails soft. Bookkeeping (attempts, metrics, read-back, format) never fails a reel or the analytics job.
- Never print, log or commit a secret; error text bound for Telegram goes through `production._redact`.
- Conventional commits (`type(scope): summary`), one coherent change each, **no AI attribution of any kind**.
- CI on `ubuntu-24.04` with Python 3.12 is the proof (rule 15); run the full suite locally before each commit.
- Telegram text follows the existing plain style (an emoji, then a plain sentence).

## Review Focus

1. **The new SQL has not been run yet** when Stage 0 ships: every write naming `posts.format`, `posts.youtube_readback`, `post_metrics` or `reel_attempts` must degrade to a one-time warning per run. Test: Task 4, `test_insert_post_retries_without_format_when_the_column_is_missing` and `test_start_attempt_returns_none_when_the_table_is_missing`.
2. **An Analytics query that returns no rows** (a removed video, zero views, a video too new for reporting): stored as zeros and nulls, never raised. Test: Task 7, `test_video_metrics_with_no_rows_stores_zeros`.
3. **Sentence one with an abbreviation or a decimal** ("The U.S. Fed cut rates by 0.25 points today."): one sentence, and the opening check passes it. Test: Task 1 and Task 2.
4. **A hung FFmpeg call:** it times out with a clear error, the reel fails soft, the idea goes back to the digest. Test: Task 3, `test_a_render_that_times_out_fails_with_a_clear_error`.
5. **The read-back fails right after a successful upload** (quota, network): the upload stands and is recorded. Test: Task 6, `test_read_back_failure_never_fails_the_publish`.

---

### Task 1: One sentence splitter

**Files:**
- Create: `src/text.py`
- Modify: `src/scriptwriter.py:518-525` (`_sentences`), `src/scriptwriter.py:726` (`_SENTENCE_END_RE`), `src/voice.py:51-53,171-175`, `src/subtitles.py:285,322`
- Test: `tests/test_text.py`

**Interfaces:**
- Produces: `text.SENTENCE_END_RE: re.Pattern` (a sentence end plus the whitespace after it), `text.split_sentences(text: str) -> list[str]`, `text.ends_clause(word: str) -> bool` (word ends in `. ! ? … । : ;` and is not an abbreviation or a single initial).

- [ ] **Step 1: Write the failing tests** in `tests/test_text.py`:

```python
from src.text import ends_clause, split_sentences


def test_abbreviations_do_not_end_a_sentence():
    assert split_sentences("A U.S. court ruled today. Markets fell.") == [
        "A U.S. court ruled today.", "Markets fell."]
    assert split_sentences("Dr. Rao and J. Smith spoke. Then it rained.") == [
        "Dr. Rao and J. Smith spoke.", "Then it rained."]


def test_an_ellipsis_before_lowercase_continues_the_sentence():
    assert split_sentences("India's biggest IPO ever... and it flopped. Here's why.") == [
        "India's biggest IPO ever... and it flopped.", "Here's why."]


def test_decimals_short_answers_and_the_hindi_full_stop():
    assert split_sentences("Rates fell 0.25 points. Did it work? No. यह बड़ा है। Why?") == [
        "Rates fell 0.25 points.", "Did it work?", "No.", "यह बड़ा है।", "Why?"]


def test_a_tag_stays_with_the_sentence_it_introduces():
    assert split_sentences("One fact. [pause] Here's why it matters.") == [
        "One fact.", "[pause] Here's why it matters."]


def test_ends_clause():
    assert ends_clause("today.") and ends_clause("matters:") and ends_clause("है।")
    assert not ends_clause("U.S.") and not ends_clause("Dr.") and not ends_clause("J.")
```

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_text.py -q`. Expected: FAIL, `ModuleNotFoundError: No module named 'src.text'`.

- [ ] **Step 3: Implement `src/text.py`.** `SENTENCE_END_RE` is today's `[.!?…](?:[\"')\]]*)\s+` widened to `।` and narrowed by fixed-width negative lookbehinds for `U.S`, `U.K`, `U.N`, `E.U`, `U.S.A`, `Dr`, `Mr`, `Mrs`, `Ms`, `St`, `vs`, `Jr`, `Sr`, `Inc`, `Ltd` and a single capital initial (`(?<!\b[A-Z])`), plus `(?![a-z])` after the whitespace so a lowercase continuation is not a new sentence. "No" is deliberately not an abbreviation. `split_sentences` keeps today's `_sentences` behaviour (strip, drop empties).

- [ ] **Step 4: Wire it in.** `scriptwriter._SENTENCE_END_RE = text.SENTENCE_END_RE`; `scriptwriter._sentences` returns `text.split_sentences(body)`; `voice._split_sentences` returns `text.split_sentences(text)` (delete `voice._SENTENCE_RE`); `subtitles._caption_groups` uses `text.ends_clause(w[2].strip())` (delete `subtitles._SENTENCE_END`).

- [ ] **Step 5: Run the new and the existing tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_text.py tests/test_scriptwriter.py tests/test_voice.py tests/test_subtitles.py -q`. Expected: all pass (`test_split_sentences` in `test_voice.py` still holds).

- [ ] **Step 6: Commit.** `git add src/text.py src/scriptwriter.py src/voice.py src/subtitles.py tests/test_text.py` then `git commit -m "fix(text): one sentence splitter that keeps U.S., decimals and ... whole"`.

### Task 2: The opening check on every script

**Files:**
- Modify: `src/scriptwriter.py` (`_opens_with_a_hook` at 832-840, `write_script` at 843-923)
- Test: `tests/test_scriptwriter.py`

**Interfaces:**
- Consumes: `text.split_sentences` (Task 1); `scriptwriter._added_facts(data, source_text)`, `_visible_words`, `llm.generate`, `_parse_llm_json` (existing).
- Produces: `scriptwriter.opening_problem(body: str) -> str | None` (a reason, or None when the opening is fine); `scriptwriter._fix_opening(body: str, problem: str, source_text: str) -> str`. `_opens_with_a_hook(body)` becomes `opening_problem(body) is None`.

- [ ] **Step 1: Write the failing tests** in `tests/test_scriptwriter.py`:

```python
def test_opening_problem_flags_wind_ups_dates_and_short_openers():
    assert "wind-up" in scriptwriter.opening_problem("So, India just banned an app used by students.")
    assert "date" in scriptwriter.opening_problem("On November 18, Voyager 1 reaches one light-day.")
    assert "five words" in scriptwriter.opening_problem("Big news. India banned it today.")
    assert scriptwriter.opening_problem("India just banned the app millions of students use daily.") is None


def test_hedges_are_not_wind_ups():
    assert scriptwriter.opening_problem("Apparently, India's new rule ends free UPI for big shops.") is None


def test_an_abbreviation_in_sentence_one_is_not_a_short_opener():
    assert scriptwriter.opening_problem("The U.S. Fed cut rates by 0.25 points today.") is None


def test_a_wind_up_is_cut_when_the_rewrite_fails(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", _raiser(RuntimeError("down")))
    fixed = scriptwriter._fix_opening("So, India banned the app students use daily. More here.",
                                      "opens on the wind-up 'so'", "India banned the app")
    assert fixed.startswith("India banned the app students use daily.")


def test_a_rewrite_that_adds_a_number_is_refused(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k:
                        '{"first_sentence": "India banned 3 apps used by 40 crore people."}')
    fixed = scriptwriter._fix_opening("So, India banned the app students use daily. More here.",
                                      "opens on the wind-up 'so'", "India banned the app")
    assert "40" not in fixed and fixed.startswith("India banned the app")
```

(`_raiser` as in `tests/test_production.py`: a function that raises the given exception.)

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_scriptwriter.py -q -k "opening or wind_up or rewrite_that_adds"`. Expected: FAIL, `AttributeError: ... has no attribute 'opening_problem'`.

- [ ] **Step 3: Implement `opening_problem` and `_fix_opening`.** Values from the spec (9.2): wind-ups `so`, `okay`, `ok`, `alright`, `imagine`, `did you know`, `here's`, `picture this`, `ever wondered`, `let's`, `guess what`; never wind-ups: `apparently`, `reportedly`, `allegedly`. Date or day first: the first word (after an optional `On`/`In`/`By`) is a month name or abbreviation, a weekday, `yesterday`, `today` or `tonight`. Keep today's checks (a leading tag; a dangling `because`/`and`/`but`/`which`/`or`; fewer than five spoken words in sentence one). `_fix_opening`: one `llm.generate(..., json=True, max_tokens=1024)` asking for `{"first_sentence": ...}` that fixes the stated problem without adding a fact; accept it only if the new body has no `opening_problem` and `_added_facts({"script_body": new_first}, source_text)` is empty; else, for a wind-up problem, cut the leading wind-up word and its comma when at least five words remain and capitalise the next word; else return the body unchanged and log a warning.

- [ ] **Step 4: Call it in `write_script`** right after the first `_enforce_length(body, idea_id)`: `problem = opening_problem(body)`; if set, `body = _fix_opening(body, problem, source)` where `source` is the body plus the idea's title, hook and angle. Replace the body of `_opens_with_a_hook` with `return opening_problem(body) is None`.

- [ ] **Step 5: Run the script tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_scriptwriter.py tests/test_claude.py -q`. Expected: all pass.

- [ ] **Step 6: Commit.** `git commit -m "feat(scriptwriter): check every opening; cut wind-ups, keep hedges"` with `src/scriptwriter.py tests/test_scriptwriter.py`.

### Task 3: A timeout on every FFmpeg call

**Files:**
- Modify: `src/assembly.py:173-180` (`probe_duration`), `src/assembly.py:599-609` (`assemble`), `src/visuals.py:400-406` (`_image_to_kenburns_clip`), `src/subtitles.py:556` (`_burn`)
- Test: `tests/test_ffmpeg_timeouts.py`

**Interfaces:**
- Produces: `assembly.RENDER_TIMEOUT_SECONDS = 600`, `assembly.PROBE_TIMEOUT_SECONDS = 60`; every `subprocess.run` in `src/` passes `timeout=`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ffmpeg_timeouts.py`:

```python
import ast
import pathlib
import subprocess

import pytest

from src import assembly


def test_every_subprocess_run_in_src_has_a_timeout():
    missing = []
    for path in pathlib.Path("src").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run" and getattr(node.func.value, "id", "") == "subprocess"
                    and not any(k.arg == "timeout" for k in node.keywords)):
                missing.append(f"{path}:{node.lineno}")
    assert not missing, missing


def test_a_render_that_times_out_fails_with_a_clear_error(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"x")
    clip = tmp_path / "c.mp4"; clip.write_bytes(b"x")
    monkeypatch.setattr(assembly, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(assembly, "_measure_levels", lambda *a: {})
    monkeypatch.setattr(assembly, "_pick_music", lambda a: None)
    monkeypatch.setattr(assembly, "_sfx_enabled", lambda: False)

    def _hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(assembly.subprocess, "run", _hang)
    with pytest.raises(RuntimeError, match="timed out"):
        assembly.assemble(str(audio), [str(clip)], str(tmp_path / "out.mp4"))
```

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_timeouts.py -q`. Expected: FAIL, the first test lists the four calls without a timeout; the second raises `TimeoutExpired`, not `RuntimeError`.

- [ ] **Step 3: Add the timeouts.** `probe_duration`: `PROBE_TIMEOUT_SECONDS`. Both renders in `assemble` and `_burn`: `RENDER_TIMEOUT_SECONDS`. Ken Burns: 120. In `assemble`, a `TimeoutExpired` on the polished render is treated like a failed polished render (retry plain); a second one raises `RuntimeError("assembly: ffmpeg timed out after 600 s")`. `_burn` and Ken Burns raise `RuntimeError` naming the timeout.

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_timeouts.py tests/test_assembly.py tests/test_visuals.py tests/test_subtitles.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "fix(assembly): time out every FFmpeg call instead of waiting for the job's kill"`.

### Task 4: Tolerant database writes for the new records

**Files:**
- Modify: `src/db.py` (after `insert_post` at 222-237; new helpers)
- Test: `tests/test_db_records.py`

**Interfaces:**
- Produces:
  - `db.insert_post(script_id: int, platform: str, external_id: str, url: str, status: str, voice: str | None = None, format: dict | None = None) -> int`
  - `db.set_post_readback(post_id: int, readback: dict) -> None`
  - `db.start_attempt(idea_id: int) -> int | None`
  - `db.finish_attempt(attempt_id: int | None, *, outcome: str, stage: str, reason: str | None = None, script_id: int | None = None, spend_usd: float | None = None, downgrades: list[str] | None = None) -> None`
  - `db.posts_needing_metrics(min_age_days: int = 9, window_days: int = 7) -> list[dict]`
  - `db.upsert_post_metrics(post_id: int, window_days: int, metrics: dict) -> None`
  - `db._missing_schema(e: Exception) -> bool`: true for PostgREST codes `PGRST204`, `PGRST205`, `42P01`, `42703` or a message mentioning "schema cache".
- None of the four new functions raises; each missing column or table is warned once per process.

- [ ] **Step 1: Write the failing tests** in `tests/test_db_records.py`, with a fake client whose `insert`/`update`/`upsert`/`select` record calls and can raise `postgrest.exceptions.APIError({"code": "PGRST204", "message": "Could not find the 'format' column of 'posts' in the schema cache"})`:
  - `test_insert_post_writes_the_format`: the inserted row carries `format == {"version": 1, "language": "en"}`.
  - `test_insert_post_retries_without_format_when_the_column_is_missing`: first insert raises PGRST204, the second row has no `format` key and the id comes back.
  - `test_start_attempt_returns_none_when_the_table_is_missing`: PGRST205 → `None`; `finish_attempt(None, outcome="failed", stage="voice")` does nothing.
  - `test_finish_attempt_never_raises`: any exception from the client is swallowed.
  - `test_posts_needing_metrics_skips_posts_already_measured_and_young_posts`: posts at 3 and 12 days old, the 12-day one already in `post_metrics` → `[]`; a 12-day post without a row → returned.
  - `test_upsert_post_metrics_uses_post_and_window_as_the_key`: `upsert(..., on_conflict="post_id,window_days")`.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_db_records.py -q`. Expected: FAIL on the missing functions and the unknown `format` argument.

- [ ] **Step 3: Implement** the functions above in `src/db.py`, following `insert_post` and the `claude_spend` helpers: timestamps as timezone-aware UTC ISO strings; `posts_needing_metrics` reads published, not removed posts with `published_at` at least `min_age_days` old and filters out ids that already have a `post_metrics` row for `window_days`.

- [ ] **Step 4: Run the db tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_db_records.py tests/test_db_top_performers.py tests/test_db_transport.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(db): format, read-back, attempts and metrics records that survive missing SQL"`.

### Task 5: Production records the format and every attempt, and says "Published" per reel

**Files:**
- Modify: `src/visuals.py:454-478` (`fetch_broll`), `src/production.py` (`produce_one` 172-272, `run_production` 403-448, `make_on_demand` 602-609)
- Test: `tests/test_production.py`, `tests/test_visuals.py`

**Interfaces:**
- Consumes: Task 4's `db.start_attempt`, `db.finish_attempt`; `db.insert_post(format=...)` is reached through `publish` (Task 6).
- Produces:
  - `visuals.fetch_broll(keywords, target_seconds, out_dir, setting=None, meta: dict | None = None) -> list[str]`, which sets `meta["source"]` (`"photos"`, `"ai"` or `"video"`, the path that produced the clips) and `meta["clips"]`.
  - `production.FORMAT_VERSION = 1` (Stage 1 raises it to 2).
  - `production._format(language: str, visual_meta: dict) -> dict` returning `{"version", "language", "visuals", "video_shots": 0, "shots", "structure": None}`.
  - `production._downgrades(voice_meta: dict, visual_meta: dict) -> list[str]`: `"fallback-voice"` when the engine is not `gemini`; `"stock-video"` when the source is `video` while `VISUAL_SOURCE` is `ai` or `photos`.
  - `metadata["format"]` and `metadata["audio_language"]` (`"en"`) handed to `publish_youtube.publish`.

- [ ] **Step 1: Write the failing tests:**
  - `tests/test_visuals.py::test_fetch_broll_reports_the_source_it_used`: the image path fails, stock video succeeds → `meta == {"source": "video", "clips": n}`.
  - `tests/test_production.py::test_format_stamp_reaches_publish`: `publish` receives `m["format"]["version"] == 1`, `m["format"]["language"] == "en"`, `m["format"]["visuals"] == "ai"`, `m["audio_language"] == "en"`.
  - `test_a_failed_attempt_is_recorded_with_its_stage`: `assemble` raises → `finish_attempt` called once with `outcome="failed", stage="assembly"`.
  - `test_a_blocked_attempt_is_recorded`: `_wire_happy(factcheck_ok=False)` → `outcome="blocked", stage="factcheck"`.
  - `test_bookkeeping_failure_never_costs_a_reel`: `db.start_attempt` raises → `produce_one` still returns the video.
  - `test_published_is_sent_as_each_reel_goes_live`: two approved ideas → `_notify` receives a "✅ Published" line after the first `produce_one` returns and before the second starts; `make_on_demand` sends no second copy.
  - Update `_wire_happy`: the `fetch_broll` stub takes `meta=None` and fills `{"source": "ai", "clips": 1}`; stub `db.start_attempt` to return 1 and `db.finish_attempt` to record calls.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_production.py tests/test_visuals.py -q`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `produce_one`: after the idempotency return, `attempt = db.start_attempt(idea_id)` inside a try (any error means `None`); a local `stage` advances through `script`, `factcheck`, `voice`, `visuals`, `assembly`, `subtitles`, `upload`; on success `finish_attempt(outcome="published", stage="upload", script_id=..., downgrades=...)`; `FactCheckFailed` → `blocked`; any other exception → `failed` with `f"{type(e).__name__}: {e}"`, then re-raise. In `run_production`, `_notify(f"✅ Published: {url}")` right after each success, and the out-of-time branch records `start_attempt` plus `finish_attempt(outcome="out-of-time", stage="queue")` for each idea it releases. Remove the per-reel loop from `make_on_demand` and keep its two summary lines.

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_production.py tests/test_visuals.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(production): stamp each post's format, record every attempt, announce each reel as it goes live"`.

### Task 6: The upload declares audio by what was voiced, and reads back what YouTube recorded

**Files:**
- Modify: `src/publish_youtube.py` (`_build_body` 116-145, `publish` 189-236; new `_reader_client`, `_read_back`)
- Test: `tests/test_publish_youtube.py`

**Interfaces:**
- Consumes: `metadata["audio_language"]`, `metadata["format"]` (Task 5); `db.insert_post(format=...)`, `db.set_post_readback` (Task 4).
- Produces: `publish_youtube._read_back(video_id: str) -> dict | None` returning `{"containsSyntheticMedia": bool | None, "defaultLanguage": str | None, "defaultAudioLanguage": str | None}`; `None` on any error.

- [ ] **Step 1: Write the failing tests:**
  - `test_audio_language_follows_the_narration`: `_build_body({"title": "t", "audio_language": "hi"})["snippet"]` has `defaultLanguage == "en"` and `defaultAudioLanguage == "hi"`; without the key both are `"en"`; `YOUTUBE_LANGUAGE` is no longer read.
  - `test_publish_passes_the_format_and_stores_the_read_back`: a fake upload returns id `V1`; `_read_back` is stubbed to `{"containsSyntheticMedia": None, ...}` → `db.insert_post` got `format=...`, `db.set_post_readback` got the dict, and no alert is sent (absent is not false).
  - `test_an_explicit_false_flag_alerts_once`: two publishes whose read-back says `False` → one Telegram alert.
  - `test_read_back_failure_never_fails_the_publish`: `_read_back` raises inside → `publish` still returns `("V1", url)`.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_publish_youtube.py -q`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** `_reader_client()` builds `youtube` v3 with the `youtube.readonly` scope (the upload client holds only `youtube.upload`); `_read_back` calls `videos.list(part="status,snippet", id=video_id)`. In `publish`, after `insert_post` succeeds, store the read-back best-effort; alert once per process (module-level flag) only when `containsSyntheticMedia is False` and `AI_DISCLOSURE` is on.

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_publish_youtube.py tests/test_production.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(publish): audio language from the narration; store what YouTube recorded"`.

### Task 7: Retention, audience and traffic per Short from the YouTube Analytics API

**Files:**
- Modify: `src/analytics.py` (new `_analytics_client`, `_video_metrics`, `collect_metrics`; `__main__`)
- Test: `tests/test_analytics.py`

**Interfaces:**
- Consumes: `db.posts_needing_metrics`, `db.upsert_post_metrics` (Task 4).
- Produces:
  - `analytics._video_metrics(yta, video_id: str, start: date, end: date) -> dict` with keys `views`, `engaged_views`, `avg_view_seconds`, `avg_view_pct`, `subscribers_gained`, `india_share`, `countries` (code → views, top 10), `traffic` (source → views), `retention` (list of `[elapsedVideoTimeRatio, audienceWatchRatio]`, or `None` if that query fails).
  - `analytics.collect_metrics(min_age_days: int = 9, limit: int = 120) -> int` (posts measured).

- [ ] **Step 1: Write the failing tests** with a fake `yta` whose `reports().query(**kw).execute()` answers by `kw.get("dimensions")`:
  - `test_video_metrics_parses_totals_countries_traffic_and_retention`: totals row `[100, 40, 20, 71.5, 2]`, countries `[["IN", 60], ["US", 40]]` → `views == 100`, `engaged_views == 40`, `avg_view_pct == 71.5`, `india_share == 0.6`, `countries == {"IN": 60, "US": 40}`; every query carried `filters == "video==V1"` and the start and end dates.
  - `test_video_metrics_with_no_rows_stores_zeros`: every query returns no `rows` → `views == 0`, `india_share is None`, `countries == {}`, `traffic == {}`, `retention == []`.
  - `test_collect_metrics_measures_each_post_once_and_survives_an_error`: two posts; the first's query raises `HttpError` → the second is still upserted with `window_days == 7`; the return value is 1.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_analytics.py -q`. Expected: FAIL on the missing functions.

- [ ] **Step 3: Implement.** `_analytics_client()` builds `youtubeAnalytics` v2 from the same refresh token with `scopes=None` (the token's own grants: verified 2026-11-12 after the API was enabled on project `composed-maxim-498517-f0`). Queries, all with `ids="channel==MINE"`, `filters=f"video=={video_id}"`, `startDate` the publish date and `endDate` six days later: totals (`views,engagedViews,averageViewDuration,averageViewPercentage,subscribersGained`), `dimensions="country"` (`views`, `sort="-views"`, `maxResults=10`), `dimensions="insightTrafficSourceType"` (`views`), `dimensions="elapsedVideoTimeRatio"` (`audienceWatchRatio`). `collect_metrics` takes at most `limit` posts a run, so the first run backfills the old Shorts as the baseline over about a day and stays well inside the API quota. Run it from `__main__` after `collect_stats()`, wrapped so a failure never loses the view snapshots.

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_analytics.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(analytics): retention, India share and traffic per Short from the Analytics API"`.

### Task 8: The bot reads the leading number of `/makeshort`

**Files:**
- Modify: `telegram-bot/api/telegram.py:324-325`
- Test: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write the failing test:** `test_dispatch_makeshort_reads_the_leading_number`: `bot.dispatch("makeshort", "2 isro docking")` dispatches with `ideas == 2`; `"x"` still defaults to 5.

- [ ] **Step 2: Run it to see it fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_telegram_bot.py -q`. Expected: FAIL, `ideas == 5`.

- [ ] **Step 3: Implement:** `m = re.match(r"\s*(\d+)", arg)`; `n = max(1, min(8, int(m.group(1)))) if m else 5`.

- [ ] **Step 4: Run the bot tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "fix(bot): /makeshort 2 isro docking makes 2 ideas, not 5"`. The deploy (`vercel deploy --prod` from `telegram-bot/`, account `shaan-alpha`) waits for the operator's go-ahead.

### Task 9: The SQL, the docs, and the full suite

**Files:**
- Modify: `docs/03-setup-guide.md` (after the `claude_spend` block, line 248), `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Add the Stage 0 SQL to docs/03:** the `posts.format` and `posts.youtube_readback` columns and the `post_metrics` and `reel_attempts` tables, exactly as in the spec's section 13, with RLS enabled, and a line that the code runs without them.

- [ ] **Step 2: Run the full suite.** Run: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`. Expected: everything passes; the count is 741 plus the new tests, with 5 skipped.

- [ ] **Step 3: Update STATUS.md** (a log entry, the module table's voice/publish/analytics rows, Next actions: run the SQL, deploy the bot) **and CHANGELOG.md** (`[Unreleased]`, a "Stage 0" block).

- [ ] **Step 4: Commit.** `git commit -m "docs(status): stage 0 shipped; the SQL it needs"`.

- [ ] **Step 5: With the operator's go-ahead:** push the branch, open the pull request, wait for CI's `tests` run, merge; then the operator runs the SQL and the bot is deployed.
