# Stage 3a: The Higgsfield Client, the Ledger and the Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The parts of the AI-video stage that touch money: one module that talks to Higgsfield, a ledger row reserved before any job is bought, a sweep that settles jobs earlier runs left open, a guard that keeps tests off the live API, and a live check tool. No reel buys anything yet; stage 3b wires the shots.

**Architecture:**
- `src/higgsfield.py` (new) is the only code that talks to Higgsfield. It uses raw REST with `requests`, sends the key only to `api.higgsfield.ai`, and redacts every message.
- `src/db.py` gains the `ai_video_jobs` ledger.
- `src/ai_video.py` (new) starts with `sweep()` and the month's spend line.
- `tools/verify_higgsfield.py` is written here and run only with the operator's go-ahead.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, `requests` (already pinned), Supabase PostgREST.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md): 6.6 (the client), 6.7 (the ledger and sweep), 6.2 step 7 (reserve first, retries), 13 (`ai_video_jobs`), 15 (one-time setup), 17 (the conftest guard).

**API facts** (`research_notes/Higgsfield API notes/`, and the working calls in `research_notes/Spikes 2026-11-10/code/spike.py` and `spike3.py`):
- Base `https://api.higgsfield.ai`; header `Authorization: Key <HF_API_KEY>` (the console key, already `id:secret`).
- `POST /estimate/{endpoint}` with the job's arguments → `{"usd": …}` (free).
- `POST /files/generate-upload-url {"content_type"}` → `upload_url`, optional `upload_headers`, `public_url`. Then PUT the file to `upload_url` with those headers only.
- `POST /{endpoint}` with an `Idempotency-Key` header → `request_id`, `status`. The same key returns the original request.
- `GET /requests/{id}/status` → `status` in queued, in_progress, completed, failed, nsfw, canceled. A completed job carries `video.url`.
- `POST /requests/{id}/cancel` → 202 when canceled; 400 once the job has started.
- Errors (`concepts_errors.md`):
  - 400 invalid; 401 credentials; 403 insufficient balance; 404 not found; 409 still running; 422 validation or a reused key with other parameters; 423 model blocked.
  - 429 queue full (`Retry-After`); 500 and 503 retry with backoff.
  - "After an ambiguous timeout, network failure, or 5xx, repeat the same generation request with the same idempotency key."
  - Failed and nsfw jobs are not charged.
  - There is no balance endpoint, so one `request_id` for two submits is the evidence of one charge (charges are per request).
- The endpoint is `kling-video/v2.5-turbo/standard/image-to-video`. Its body is `prompt`, `image_url`, `duration: 5`, `negative_prompt`.

**Not in 3a** (stage 3b, with the shots): the phase deadline, retries and `Retry-After` waits; the stop latches and their alerts; reuse; the "Published" and "Reel failed" spend text; the idea age-out exemption for paid clips (6.7, last rule).

## Global Constraints

- No new Python dependency; no money spent by any test; the live tool runs only with the operator's go-ahead (design 15).
- `HF_API_KEY` is optional (`config.REQUIRED` unchanged); the key, each half of it, and any URL's query string never appear in a log line, an exception or a Telegram message.
- Every request has a timeout. A request that was refused is never retried; a submit with no answer is retried only with the same key and body.
- Ledger writes and reads raise on failure; callers decide (stage 3b: a failed ledger read means nothing is bought). The sweep is fail-soft.
- Conventional commits, no AI attribution; the suite green normally and with `.env` blanked.

## Review Focus

1. **The key in an error:** a 401 whose body echoes the header, or a `requests` exception quoting the URL. Every raised message is redacted. Test: Task 1, `test_no_message_carries_the_key_or_a_query_string`.
2. **The presigned upload:** an `Authorization` header sent to the storage host breaks the upload and leaks the key. Test: Task 1, `test_the_key_goes_only_to_the_api_host`.
3. **A 429 with `Retry-After`:** must come back to the caller as "busy, retry after N s", not as a refusal or an outage. Test: Task 1, `test_errors_are_classified`.
4. **A missing `ai_video_jobs` table:** a read raises a clear `LedgerUnavailable`, never returns an empty list that reads as "nothing bought". Test: Task 2, `test_a_missing_ledger_table_is_unavailable_not_empty`.
5. **A sweep that meets a broken status call:** that row is left for the next sweep and the others are still settled. Test: Task 3, `test_the_sweep_settles_what_it_can`.

---

### Task 1: The Higgsfield client

**Files:**
- Create: `src/higgsfield.py`
- Test: `tests/test_higgsfield.py`

**Interfaces:**
- Produces:
  - `HiggsfieldError(Exception)` with `kind` (funds | auth | refused | busy | unavailable), `status` and `retry_after`.
  - The calls: `estimate(endpoint, args) -> float`, `upload(path, content_type) -> str` (the public URL), `submit(endpoint, args, key) -> dict`, `status(request_id) -> dict`, `cancel(request_id) -> bool`, `download(url, dest) -> str`.
  - `redact(text) -> str`.
  - `KLING = "kling-video/v2.5-turbo/standard/image-to-video"`, `TERMINAL`.

- [ ] **Step 1: Write the failing tests** with a fake transport. Every call goes through `requests.request`, which the tests monkeypatch; there is no network.
  - `test_estimate_reads_the_quote`.
  - `test_upload_puts_the_file_and_returns_the_public_url`.
  - `test_submit_sends_the_idempotency_key`: the same key and body twice give the same request.
  - `test_status_and_cancel`: cancel is True only on 202. It is False on 400, 404, 5xx or a timeout, and never raises.
  - `test_errors_are_classified`:
    - 403 → funds; 401 → auth.
    - 400, 404, 409, 422 and 423 → refused.
    - 429 with `Retry-After: 7` → busy with `retry_after == 7`.
    - 500, 503, a timeout, a dropped connection, and a 2xx submit without a `request_id` → unavailable.
  - `test_the_key_goes_only_to_the_api_host`: the upload PUT and the download carry no `Authorization`.
  - `test_no_message_carries_the_key_or_a_query_string`: with key `abc123:def456`, an error body echoing it and a URL with `?X-Amz-Signature=…`, the raised message contains none of `abc123:def456`, `abc123`, `def456`, `X-Amz-Signature`.
  - `test_no_key_is_auth`: an unset `HF_API_KEY` raises auth before any request.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_higgsfield.py -q -p no:cacheprovider`. Expected: FAIL (no module).

- [ ] **Step 3: Implement** from design 6.6 and the API facts. Timeouts: 30 s for calls, 180 s for upload and download. The redactor removes the whole key, each half split at the first `:`, and everything after `?` in any URL.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(higgsfield): a client that keeps its key to itself"`.

### Task 2: The ledger

**Files:**
- Modify: `src/db.py`, `docs/03-setup-guide.md` (SQL, design 13)
- Test: `tests/test_db_records.py`

**Interfaces:**
- Produces:
  - `db.LedgerUnavailable(RuntimeError)`.
  - `db.reserve_ai_video_job(idea_id, shot, endpoint, cost_usd) -> dict` (`id` and a fresh UUID `idempotency_key`; status `reserved`).
  - `db.update_ai_video_job(row_id, **fields) -> None`.
  - `db.ai_video_jobs_for_idea(idea_id, days=7) -> list[dict]`.
  - `db.open_ai_video_jobs(days=7) -> list[dict]` (submitted or late).
  - `db.ai_video_jobs_since(since: datetime) -> list[dict]`: this run's rows, for the spend line.
  - `db.ai_video_spend_this_month() -> float`: UTC month, as `claude_spend_this_month`.
  - `created_at` is stamped by `reserve`, as `reserve_claude_spend` does.

- [ ] **Step 1: Write the failing tests:**
  - `test_reserve_stamps_a_fresh_key_and_status`.
  - `test_update_writes_the_fields`.
  - `test_reads_filter_by_idea_age_and_status`.
  - `test_the_months_spend_sums_cost`.
  - `test_a_missing_ledger_table_is_unavailable_not_empty`: PGRST205 → `LedgerUnavailable` from every read and from `reserve`.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 6.7 and 13; add the `ai_video_jobs` SQL (table and two indexes) to docs/03 §4.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(db): the ai_video_jobs ledger, reserved before anything is bought"`.

### Task 3: The sweep and the spend line

**Files:**
- Create: `src/ai_video.py`
- Modify: `src/production.py` (the sweep at the start of both entry points and after the last reel; the run's spend line)
- Test: `tests/test_ai_video.py`, `tests/test_production.py`

**Interfaces:**
- Produces:
  - `ai_video.sweep() -> dict`: `settled`, `left` and `errors` counts. It is fail-soft and never raises.
  - `ai_video.spend_line(since: datetime) -> str | None`: the run's line for Telegram, read from the ledger (6.8). It gives clips bought, dollars, clips paid for and not used (`late`, `reserved` or `submitted` at a cost), and the month-to-date. It is None when this run reserved nothing or the ledger cannot be read.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_sweep_settles_what_it_can`:
    - a submitted row that is now completed gets its URL and `settled_at`;
    - a failed or nsfw row gets cost 0;
    - a row whose status call raises is left as it was and counted under `errors`.
  - `test_a_reserved_row_is_not_read`: it has no request id.
  - `test_no_key_or_no_table_means_no_sweep`: both return without raising.
  - `test_spend_line`.
  - `test_runs_sweep_before_and_after` (test_production): `make_on_demand` and `run` call the sweep first and after the last reel.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 6.7 and 6.8. The sweep only runs when `HF_API_KEY` is set.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): the ledger sweep and the month's spend line"`.

### Task 4: The guard, the live tool, the settings, the docs

**Files:**
- Modify: `tests/conftest.py`, `.env.example`, `.github/workflows/make-short.yml`, `.github/workflows/production.yml`, STATUS.md, CHANGELOG.md, `docs/04-free-tools-reference.md` (Higgsfield and its terms), the handoff
- Create: `tools/verify_higgsfield.py`

- [ ] **Step 1: Write the failing test** `test_tests_never_reach_higgsfield`: inside a test, `higgsfield.submit` raises the guard's error.
- [ ] **Step 2: Run it to see it fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The conftest guard works as the Telegram guard does: `higgsfield._send` refuses a real network call (an unpatched `requests.request`) in every test.
  - `tools/verify_higgsfield.py` follows design 15 step 3, on one job:
    - one estimate and one still uploaded;
    - two submits with one idempotency key: is the request_id the same?
    - an immediate cancel, then a status read: canceled at no cost?
    - if the job had already started, it waits, downloads the clip without the key, and reports it: $0.18 at most.
    - The result goes into docs/04. The tool refuses to run without `--yes-spend`, and prints only redacted URLs.
  - `HF_API_KEY` goes in `.env.example` and in both workflows as a secret reference (`${{ secrets.HF_API_KEY }}`).
  - `HF_API_SECRET` is dropped (6.6): the empty `HF_API_SECRET=` line and the "paste both" comment go from the local `.env`, by a script that prints no value.
  - Docs, and the suite twice.
- [ ] **Step 4: Run the tests.** Expected: all pass; the full suite green normally and with `.env` blanked (bar the known NICHE artifact).
- [ ] **Step 5: Commit.** `git commit -m "chore(higgsfield): a test guard, the live check tool, settings and docs"`.
- [ ] **Step 6: The final review of stage 3a,** its fix pass, then ask the operator: push and merge, run the live tool ($0.18), and add the `HF_API_KEY` secret (design 15 steps 2-3).
