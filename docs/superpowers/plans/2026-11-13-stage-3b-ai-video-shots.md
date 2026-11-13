# Stage 3b: The Shots, the Cut List and the Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An AI-video reel end to end, behind `VISUAL_SOURCE=ai_video`. The narration's pauses give a cut list. A shot planner writes a still and a motion prompt per shot. FLUX draws the stills. Kling animates as many as the per-reel budget buys, every job reserved in the ledger first. Assembly cuts the clips at 24 fps on the pauses, and the operator sees every dollar.

**Architecture:**
- `src/assembly.py` gains the cut list, one pure function that fixes the shots and every cut, and a renderer for it at 24 fps with hard cuts.
- `src/ai_video.py` (from 3a) gains one reel's shots: sizing, the planner, the pictures, buying, waiting, settling and the run's stop latches. It returns a typed `Shots`.
- `src/production.py` calls `ai_video.make_shots` for this source and falls back to today's `ai` path when not one picture exists. It hands the cut list to assembly and reports the spend.
- Stage 4 (the gates, the key-number card, the banner hold, the source line, the music level, the vignette and stings) follows this plan; the seams for its still and clip gates are named here.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, FFmpeg (system), `requests`, Supabase PostgREST.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md): 6.1-6.5, 6.7 (last rule), 6.8, 6.9, 11.1, 11.2, 12, 14. Stage 3a's plan: [2026-11-13-stage-3a-higgsfield-client-and-ledger.md](2026-11-13-stage-3a-higgsfield-client-and-ledger.md).

**Measured on 2026-11-13 (live check; STATUS log and docs/04):**
- `/estimate` answers Kling with a rate: $0.0315 per video second at 720p, so **$0.1575 a 5 s clip**. At the default $1.10 that is `k = 6`.
- It needs an `image_url` in the body, but any URL will do.
- Two submits with one `Idempotency-Key` returned **the same `request_id`**, so a submit with no answer may be repeated with the same key and body.
- Jobs were `in_progress` a second or two after the submit, so a cancel at the deadline will rarely find a job still queued.

## Global Constraints

- **Off by default.** Everything new runs only with `VISUAL_SOURCE=ai_video`; with today's `ai`, nothing on the live channel changes.
- **No cap.** No new Python dependency, and no monthly or count cap in code (operator, 2026-11-10). `AI_VIDEO_BUDGET_USD` (default `1.10`) only sizes how many clips one reel may buy: `k = floor(budget / quote)`.
- **No test spends money.** No test reaches Higgsfield (the conftest guard), Cloudflare, a model or the database.
- **Reserve first:** a row is reserved before its still is uploaded or its job submitted, and a failed reserve buys nothing more for that reel. Only a `klein` still is ever animated.
- **Repeats.** A submit is repeated only with the same key and body. A refusal is never repeated, except a 429 whose `Retry-After` fits the phase deadline.
- **Failures cost shots, never the reel.** Per shot: Kling, then Ken Burns over the same still. Per reel: `ai_video`, then today's `ai`, then stock video.
- **No secrets in messages.** The key, either half of it and any URL's query string never reach a log line or a Telegram message (`higgsfield.redact`, `production._redact`).
- **24 fps, never slowed.** Kling clips are never slowed or frame-rate converted: `ai_video` reels are cut, rendered and burned at **24 fps**. Every other source stays at 30 fps exactly as today.
- **Settings defaults** (design 12): `AI_VIDEO_MODEL` = `kling-video/v2.5-turbo/standard/image-to-video`, `AI_VIDEO_BUDGET_USD` = `1.10`, `AI_VIDEO_TIMEOUT_SECONDS` = `300`, `AI_VIDEO_GRACE_SECONDS` = `120`, `AI_VIDEO_TAIL_SECONDS` = `240`, `AI_VIDEO_CUTS` = `pauses`, `AI_VIDEO_STYLE` = `cinematic 3D animated film still, stylized shapes, rich saturated color, bright clear lighting`, `REEL_BUDGET_MINUTES` = `14`.
- **House rules.** Conventional commits, no AI attribution. The suite is green normally and with every `.env` name blanked (bar the known NICHE artifact).

## Review Focus

1. **A tail that is nearly nothing:** a narration whose last pause sits just before its end must not end on a flash of a shot. Expected: no shot under 1.5 s, none over 5.0 s. Test: Task 1, `test_no_shot_is_a_flash_or_too_long`.
2. **An ambiguous submit, then a refusal:** a submit times out and its repeat is refused. The first may have been charged, so the row stays `reserved` at its quote, never `refused` at 0 (3a's I-6). Test: Task 5, `test_a_refusal_after_an_unanswered_submit_keeps_the_quote`.
3. **A clip shorter than its shot:** a downloaded clip that cannot cover its shot's screen time would shift every later cut off its pause. Expected: that shot becomes a still and the reel keeps its length. Test: Task 6, `test_a_clip_too_short_for_its_shot_becomes_a_still`.
4. **Three reels, no key (or no table):** expected one Telegram alert per kind for the run, and every reel still ships, on stills. Test: Task 7, `test_one_alert_per_kind_per_run`.
5. **A slow queue:** the first reel's phase passes with no clip finished. Expected: nothing more is bought for the rest of the run, and the second reel buys nothing. Test: Task 7, `test_a_reel_with_no_clip_stops_buying_for_the_run`.

---

### Task 1: The cut list

**Files:**
- Modify: `src/assembly.py`
- Test: `tests/test_assembly.py`

**Interfaces:**
- Produces:
  - `Segment` (frozen dataclass): `shot: int` (from 0), `start: float`, `end: float` (reel seconds), `offset: float` (seconds into that shot's own clip or Ken Burns still), and `zoom: float` (1.0, or `REFRAME_ZOOM` after a reframe).
  - Constants `SHOT_MIN = 3.0`, `SHOT_MAX = 5.0`, `TAIL_MIN = 1.5`, `REFRAME_OVER = 3.6`, `REFRAME_SNAP = 0.6`, `REFRAME_ZOOM = 1.15`.
  - `cut_list(duration: float, pauses: list[tuple[float, float]], mode: str = "pauses") -> list[Segment]`: ValueError when `duration <= 0`.
  - `shot_lengths(cuts: list[Segment]) -> list[float]`: one per shot, in order.

- [ ] **Step 1: Write the failing tests.** The fixture is `tests/fixtures/hinglish_test4.json`, trimmed as `voice.trim_silence` would trim it: drop the leading pause `[0.0, 0.285]`, shift every other pause by -0.285, and set `duration = 27.04 - 0.285`.
  - `test_cut_list_on_test_4`:
    - 6 shots, boundaries `[0, 4.906, 9.906, 13.052, 17.706, 22.706, 26.755]` (±0.002);
    - 11 segments that tile `[0, duration]` with no gap or overlap;
    - the reframed shots are 1, 2, 4, 5 and 6 (not shot 3, 3.15 s long);
    - every second part has `zoom == 1.15` and `offset == its start - its shot's start`.
  - `test_clip_mode_is_one_segment_per_shot`: `mode="clip"` → 6 segments, every `zoom == 1.0` and `offset == 0`.
  - `test_no_shot_is_a_flash_or_too_long`: `duration=25.3`, no pauses → every shot is in `[1.5, 5.0]` and the last one is 1.5 s. Also `duration=21.2` with one pause at `[20.0, 20.1]`.
  - `test_short_narrations`: `duration=4.0` → one shot (reframed once at 2.0); `duration=2.0` → one shot, one segment; `duration=0` → ValueError.
  - `test_a_reframe_snaps_to_a_pause_near_the_middle`: one 5.0 s shot with a pause centred 0.4 s from its middle cuts there; a pause 0.9 s away is ignored and the cut is at the middle.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_assembly.py -q -p no:cacheprovider -k "cut_list or clip_mode or flash or short_narrations or reframe"`. Expected: FAIL (no `cut_list`).

- [ ] **Step 3: Implement** from design 11.2. The algorithm:
  - Cut points are the pause middles `(s + e) / 2` strictly inside `(0.05, duration - 0.05)`.
  - From `t = 0`, while `duration - t > SHOT_MAX`:
    - the window is `[t + SHOT_MIN, t + hi]`, where `hi = SHOT_MAX`, but `duration - t - TAIL_MIN` when the rest is under `SHOT_MAX + TAIL_MIN`;
    - the shot ends at the latest cut point in the window, else at `t + hi`.
  - The rest is the last shot.
  - In `pauses` mode, each shot longer than `REFRAME_OVER` is cut once: at the cut point nearest its middle when one lies within `REFRAME_SNAP`, else at the middle.
  - Times are rounded to 3 decimals.

- [ ] **Step 4: Run the tests.** Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat(assembly): the cut list, shots first on the narration's pauses"`.

### Task 2: A cut list rendered at 24 fps

**Files:**
- Modify: `src/assembly.py`, `src/visuals.py` (`_image_to_kenburns_clip`), `src/subtitles.py` (`_burn`, `burn_captions`, `burn_hinglish`)
- Test: `tests/test_assembly.py`, `tests/test_visuals.py`, `tests/test_subtitles.py`

**Interfaces:**
- Consumes: `Segment`, `cut_list`, `shot_lengths` (Task 1).
- Produces:
  - `assemble(audio_path, clip_paths, out_path, cuts: list[Segment] | None = None, fps: int = 30) -> str`. With `cuts`, `clip_paths[i]` is shot `i`'s file, and the call raises ValueError when the counts differ.
  - `x264_args(final: bool = False, fps: int = 30) -> list[str]`: the final GOP is `fps // 2`.
  - `visuals._image_to_kenburns_clip(image_path, dest, seconds, index=0, fps=30)`.
  - `burn_captions(..., fps: int = 30)`, `burn_hinglish(..., fps: int = 30)`, `_burn(..., fps=30)`.

- [ ] **Step 1: Write the failing tests.**
  - `test_a_cut_list_render_is_hard_cuts_at_24_fps`: build `_build_cmd` for test 4's cut list. Expected:
    - no `xfade` in the graph; one input per segment;
    - each segment trims `[offset, offset + length]`;
    - reframed segments scale by 1.15 and crop to 1080x1920; every segment has `fps=24`;
    - the output has `-r 24`; the stings file is not added.
  - `test_the_final_gop_is_half_the_frame_rate`: `x264_args(final=True, fps=24)` has `-g 12`; the default is still `-g 15`.
  - `test_kenburns_paces_to_its_length_at_24_fps`: `_image_to_kenburns_clip(..., 4.2, fps=24)` asks zoompan for `d=101` frames at `fps=24` and outputs `-r 24`. The zoom per frame is scaled by 30/24, so a shot moves as far per second as today.
  - `test_burns_keep_the_reels_frame_rate`: `burn_hinglish(..., fps=24)` reaches `_burn` and its encode has `-g 12`.
  - `test_a_cut_list_reel_keeps_every_frame` (real FFmpeg, skipped without it):
    - inputs: two 5.04 s 24 fps `testsrc2` clips and a 9.0 s sine narration;
    - `assemble(..., cuts=cut_list(9.0, []), fps=24)` gives a reel of 24/1 fps, 9.0 ± 0.1 s and 216 ± 2 frames.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement.**
  - With `cuts`, `_build_cmd` makes one input per segment. Its graph per segment:
    - `trim={offset}:{offset+len},setpts=PTS-STARTPTS`;
    - today's scale-to-fill and crop; for `zoom > 1`, `scale=iw*{zoom}:ih*{zoom},crop=1080:1920`;
    - `setsar=1,fps={fps}`.
  - Then concat, the grade, the logo and the audio exactly as today. There is no xfade, no seamless loop, no SFX, and output `-r {fps}`.
  - The plain retry keeps the cut list (without the grade and the logo).
  - Without `cuts`, nothing changes.

- [ ] **Step 4: Run the tests,** then the whole `tests/test_assembly.py`, `test_visuals.py` and `test_subtitles.py`. Expected: PASS, nothing else changed.

- [ ] **Step 5: Commit.** `git commit -m "feat(assembly): render a cut list with hard cuts at 24 fps, never slowed"`.

### Task 3: The shot planner

**Files:**
- Modify: `src/ai_video.py`
- Test: `tests/test_ai_video.py`

**Interfaces:**
- Produces:
  - `ReelRequest` (frozen dataclass): what production hands over, fixed here for every later task. Fields:
    - `idea_id: int`, `script_body: str`, `title: str`, `tone: str | None`, `setting: str | None`;
    - `story: str` (the idea's hook and angle, plus its title unless title-cased);
    - `audio_path: str`, `duration: float`, `pauses: list[tuple[float, float]]`, `work_dir: str`;
    - `deadline: float | None`, a `time.monotonic()` value: the latest-finish time from production, or None;
    - `can_buy: bool = True`, False when the subtitle preflight failed.
  - `plan_shots(req: ReelRequest, durations: list[float]) -> tuple[list[dict], bool]`. It returns `m` shots in order, each `{"still", "motion", "search"}`, the still already ending in the style line. The flag says whether clips may be bought from this plan.
  - `NEGATIVE = "text, subtitles, captions, watermark, logo, distortion, warping, flicker, fast motion, scene change, people"`.

- [ ] **Step 1: Write the failing tests** with `llm.generate` replaced (it returns JSON text):
  - `test_a_good_plan_is_used`:
    - 6 durations in, 6 shots out, flag True;
    - every still ends with `Style: cinematic 3D animated film still, stylized shapes, rich saturated color, bright clear lighting. Mood: <the plan's mood>.`;
    - the prompt sent states `m`, each shot's seconds, the tone and the setting.
  - `test_ai_video_style_overrides_the_look`.
  - `test_a_name_from_the_story_rejects_the_plan`:
    - the script names "Sunita Williams" and "NASA"; the first plan's still says "Sunita Williams floating";
    - a second call is made, quoting `Sunita`, `Williams`; its clean plan is used and the flag is True;
    - "India", "Delhi", "Earth", "The" and "Indian" never count as names.
  - `test_a_second_failure_buys_nothing`: both plans name a person. Expected:
    - `m` shots built from `visuals.extract_keywords` and `visuals._img_prompt`, one fixed motion line;
    - flag False.
  - `test_a_broken_reply_buys_nothing`: the wrong shot count twice, or `llm.generate` raising → the same fallback, flag False.
  - `test_search_words_never_come_from_the_still`: a shot without `search` gets the script's heuristic keyword for its position (`visuals._keywords_heuristic`).

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 6.5.
  - The call: one `llm.generate(prompt, json=True, max_tokens=4096)` asking for `{"mood": "...", "shots": [{"still", "motion", "search"}]}`.
  - The prompt states every rule in 6.5 (still prose, framing for the banner and subtitles, no lettering nouns, the motion rules, the content rules), and that shot 1 shows the opening claim and the last shot the payoff.
  - The name check (`_story_names(texts) -> set[str]`): the capitalised tokens of `req.script_body` (tags removed) and `req.story`.
    - A token counts when it is capitalised in mid-sentence, or sits in a run of two or more capitalised tokens.
    - Possessive `'s` is dropped; function words and `_PLACES` are removed.
  - A shot fails when any name appears in its still or motion as a whole word, matched case-sensitively.
  - `_PLACES` (builder's list, design 20):
    - the countries as English news writes them (US, USA, UK, UAE included), every Indian state and union territory as tokens ("Uttar", "Pradesh");
    - about 30 large Indian cities and 30 world capitals or big cities, with their demonyms;
    - months, weekdays, and the Sun, Moon, Earth and planets.
  - Caps: a still at most 1,800 characters with the style line, a motion at most 500.

- [ ] **Step 4: Run the tests.** Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): the shot planner, with no name from the story in a prompt"`.

### Task 4: A picture for every shot

**Files:**
- Modify: `src/visuals.py`, `src/ai_video.py`
- Test: `tests/test_visuals.py`, `tests/test_ai_video.py`

**Interfaces:**
- Consumes: `ReelRequest`, the plan (Task 3), `_image_to_kenburns_clip(..., fps)` (Task 2).
- Produces:
  - `visuals.ai_still(prompt: str, dest: str, seed: int) -> str | None`: FLUX.2 klein at 768x1344 with the seed, then FLUX.1 schnell. It returns `"klein"` or `"schnell"` (which model drew it), or None.
  - `visuals.stock_photo(query: str, dest: str, variant: str, index: int) -> bool`: the Pexels half of `_fetch_image`, unchanged in behaviour.
  - `ai_video.Picture` (frozen dataclass): `path: str`, `animatable: bool` (True only for klein).
  - `ai_video.NoShots(RuntimeError)`.
  - `ai_video._pictures(req, plan) -> list[Picture]`: one per shot, in parallel (`visuals._visual_workers()`). Seeds come from `visuals._image_seed(f"idea_{req.idea_id}", i)`. It raises `NoShots` when no shot has a picture.
  - `ai_video._still_clip(picture: Picture, dest: str, seconds: float, index: int) -> str`: Ken Burns at 24 fps for `seconds + 0.1`.
  - The seam for stage 4's still gate: `_pictures` calls `_check_still(path) -> bool`, which returns True in 3b.

- [ ] **Step 1: Write the failing tests:**
  - `test_ai_still_names_the_model_that_drew_it`: klein ok → `"klein"`; klein fails and schnell ok → `"schnell"`; no credentials → None.
  - `test_only_a_klein_still_is_animatable`.
  - `test_a_shot_without_ai_falls_back_to_its_search_words`: the Pexels query is the planner's `search`, never the still prompt.
  - `test_a_shot_with_nothing_borrows_its_neighbour`: shot 3 gets shot 2's picture (shot 0 gets shot 1's), not animatable.
  - `test_no_picture_at_all_is_no_shots`: `NoShots`.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.** `_fetch_image` uses `stock_photo` for its Pexels half, so the `ai` path keeps its behaviour and its tests.
- [ ] **Step 4: Run the tests,** and the whole of `tests/test_visuals.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): a klein still for every shot, with the existing fallbacks"`.

### Task 5: Buying the clips

**Files:**
- Modify: `src/ai_video.py`
- Test: `tests/test_ai_video.py`

**Interfaces:**
- Consumes: `higgsfield` (3a), `db.reserve_ai_video_job`, `db.update_ai_video_job`, `db.ai_video_jobs_for_idea` (3a), `Picture` (Task 4).
- Produces:
  - `Job` (dataclass): `shot`, `row_id`, `key`, `request_id: str | None`, `status`, `cost: float`, `submitted_at: float | None`, `ambiguous: bool`, `clip: str | None`.
  - `video_shots(m: int, k: int) -> list[int]`: the first `min(m, k)` of the order shot 0, the last shot, then the rest from the start, returned sorted.
  - `_buy(req, positions: list[int], pictures, plan, price: float, phase_end: float) -> list[Job]`.
  - The run's latch: `_latch: set[str]` (kinds `funds`, `auth`, `ledger`, `slow`), cleared by `begin_run()` (Task 7). `_stop_buying() -> bool`.
  - The time seams, which tests replace with a fake clock: `_clock = time.monotonic`, `_sleep = time.sleep`.

- [ ] **Step 1: Write the failing tests** with a fake `higgsfield` and ledger that record call order:
  - `test_video_positions`: `(6, 6) → [0..5]`; `(7, 6) → [0, 1, 2, 3, 4, 6]`; `(6, 2) → [0, 5]`; `(1, 6) → [0]`; `(6, 0) → []`.
  - `test_a_row_is_reserved_before_anything_is_sent`: per job the order is reserve → upload → submit.
    - The submit carries the row's key and the body `{"prompt", "image_url", "duration": 5, "negative_prompt": NEGATIVE}`.
    - The row gets `request_id` and `submitted`.
  - `test_a_failed_reserve_buys_nothing_more`.
  - `test_an_unanswered_submit_is_repeated_with_the_same_key_and_body`:
    - two `unavailable`, then an answer → one job, the same key and the identical body three times, the still uploaded once;
    - never answered by the phase end → the row stays `reserved` at its quote, and the shot is a still.
  - `test_a_refusal_after_an_unanswered_submit_keeps_the_quote` (Review Focus 2).
  - `test_refusals_cost_nothing`: a first-attempt 422 → `refused`, cost 0, and the next position is still bought.
  - `test_funds_and_auth_stop_buying_for_the_run`: a 403 at shot 2 → `refused` at 0, latch `funds`, no further reserve this reel, and `_stop_buying()` True.
  - `test_busy_waits_out_retry_after_inside_the_phase`:
    - 429 with `Retry-After: 7` and 60 s left → wait 7, resubmit with the same key;
    - `Retry-After: 90` with 60 s left → `refused` at 0.
  - `test_a_still_that_cannot_animate_is_not_bought`: a schnell picture at a video position reserves nothing.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** from design 6.2 step 7 and 6.4.
  - A failed upload means no job exists: the row becomes `refused` at 0.
  - A ledger write that fails after a submit leaves the row `reserved` at its quote, while the job is still used in memory.
  - Waits between repeats: 2, 4, 8, then 10 s. Each wait is cut short by `phase_end`.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): buy each clip after reserving its row; repeat only with the same key"`.

### Task 6: Waiting, settling and the clips

**Files:**
- Modify: `src/ai_video.py`, `src/higgsfield.py` (`download` gains `timeout`)
- Test: `tests/test_ai_video.py`, `tests/test_higgsfield.py`

**Interfaces:**
- Consumes: `Job`, `_clock`, `_sleep`, `_latch` (Task 5).
- Produces:
  - `_settle_jobs(jobs, phase_end: float, grace_end: float, lengths: list[float], out_dir: str) -> None`. It fills each `Job.clip` with a usable clip path or leaves it None, and writes every outcome to the ledger.
  - `higgsfield.download(url, dest, timeout: float | None = None)`.
  - The seam for stage 4's clip gate: `_check_clip(path, seconds) -> bool`. In 3b it means only "probed length at least `seconds`".

- [ ] **Step 1: Write the failing tests** with a fake clock, fake status answers and a fake `assembly.probe_duration`:
  - `test_jobs_are_polled_until_they_finish`: polls at 2, 3, 4.5, 6.75, then 10 s (±0.5 s jitter).
    - `completed` → the row gets `completed`, `seconds`, `result_url` and `settled_at`, and the clip is downloaded without the key.
    - `failed` or `nsfw` → cost 0; that shot is a still.
  - `test_a_status_error_is_retried_next_tick`.
  - `test_at_the_deadline_a_queued_job_is_cancelled`:
    - a confirmed cancel, or a re-read `canceled` → `canceled` at 0;
    - an unconfirmed one is waited out like a running job.
  - `test_a_running_job_gets_the_grace_period`:
    - finished inside `grace_end` → used;
    - still running → `late` at its quote, and the shot is a still.
  - `test_a_clip_too_short_for_its_shot_becomes_a_still` (Review Focus 3): probed 3.9 s for a 4.6 s shot → no clip; the row stays `completed`.
  - `test_a_failed_download_leaves_the_row_completed`.
  - `test_download_timeout_is_passed_through` (`test_higgsfield.py`).

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** from design 6.2 steps 8-10.
  - Clips are downloaded as soon as their job completes, each with `timeout=min(180, seconds to grace_end)`.
  - `seconds` is measured from the submit.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): wait, settle and download each clip inside the phase deadline"`.

### Task 7: One reel's shots, and the run's latches

**Files:**
- Modify: `src/ai_video.py`
- Test: `tests/test_ai_video.py`

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces:
  - `Shots` (dataclass), one entry per shot in order:
    - `files: list[str]`, `kinds: list[str]` (`video` or `still`), `cuts: list[assembly.Segment]`;
    - `planned_video: int`, `spend_usd: float`, `problems: list[str]`, and the property `video -> int`.
  - `begin_run() -> None`: clears the latches and the alert kinds already sent.
  - `make_shots(req: ReelRequest) -> Shots`. It raises `NoShots` only when no shot has a picture.
  - `reel_line(shots: Shots) -> str`: `🎞️ AI video: 5 of 6 shots, $0.90 ($14.30 this month)`; without the month when the ledger cannot be read.

- [ ] **Step 1: Write the failing tests** (fakes for every module below `ai_video`):
  - `test_a_reel_end_to_end`, test 4's narration:
    - 6 shots, 6 bought at $0.1575, `spend_usd == 0.945`, all `video`;
    - `files[i]` is the clip; the cut list is Task 1's.
  - `test_nothing_is_bought_without_the_means`: no key; a latch already set; `can_buy=False`; a planner failure; a failed ledger read; a quote that fails or is not positive; under 150 s left before `phase_end`.
    - Each gives an all-still reel (Ken Burns at 24 fps on the same cut list) with `spend_usd == 0` and no reserve.
  - `test_paid_clips_are_reused`: this idea's ledger has `completed` rows at shots 0 and 5 with URLs, and two more paid rows.
    - Those two shots are downloaded, not bought, and they count against `k`: only `k - 4` new clips are bought.
  - `test_the_phase_and_grace_times`:
    - `phase_end = min(quote time + AI_VIDEO_TIMEOUT_SECONDS, req.deadline)`;
    - `grace_end = min(phase_end + AI_VIDEO_GRACE_SECONDS, req.deadline)`.
  - `test_one_alert_per_kind_per_run` (Review Focus 4): three reels with no key → one problem in total, and `begin_run()` lets the next run say it again.
  - `test_a_reel_with_no_clip_stops_buying_for_the_run` (Review Focus 5).
  - `test_reel_line`.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** from design 6.2 (steps 1-11), 6.4 and 6.8:
  1. `cuts = assembly.cut_list(req.duration, req.pauses, mode=AI_VIDEO_CUTS)`, plus their lengths.
  2. `plan_shots`, then `_pictures`.
  3. The buying gate.
  4. The quote: `higgsfield.estimate(model, {"prompt": plan[0]["motion"], "image_url": "https://example.com/still.png", "duration": 5, "negative_prompt": NEGATIVE})`.
  5. Reuse; `_buy`; `_settle_jobs`.
  6. `_still_clip` for every shot without a clip.
  - The latches: `funds`, `auth` and `ledger` are set by Task 5's refusals and the ledger read. `slow` is set when a reel submitted jobs and none finished by `grace_end`.
  - `spend_usd` sums this attempt's rows at their settled cost; reused clips add nothing.

- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ai_video): one reel's shots, with stop latches that last the run"`.

### Task 8: Production wiring, settings and docs

**Files:**
- Modify:
  - code: `src/production.py`, `src/subtitles.py` (`preflight`), `src/visuals.py` (`fetch_broll(source=)`), `src/db.py` (age-out);
  - settings: `.env.example`, `.github/workflows/make-short.yml`, `.github/workflows/production.yml`;
  - docs: `STATUS.md`, `CHANGELOG.md`, the handoff.
- Test: `tests/test_production.py`, `tests/test_subtitles.py`, `tests/test_db_records.py`

**Interfaces:**
- Consumes: `ReelRequest`, `make_shots`, `Shots`, `reel_line`, `begin_run`, `NoShots` (Task 7); `assemble(cuts=, fps=)`, the burns' `fps` (Task 2).
- Produces:
  - `subtitles.preflight(audio_path: str, out_dir: str, *, lines: list[dict] | None = None, hook_text: str | None = None, source_label: str | None = None) -> bool`. It is True when a one-second blank 1080x1920 clip takes the reel's subtitle burn.
    - For an English narration it first transcribes, which is the step that broke in October.
    - `burn_captions` then reuses those words: a cache keyed by the audio's path, size and mtime.
  - `visuals.fetch_broll(..., source: str | None = None)`: `source` overrides `VISUAL_SOURCE`.
  - `db.ideas_with_paid_clips(days: int = 6) -> set[int]`: never raises (empty on failure). `expire_stale_pending_ideas` skips those ideas.
  - `production.produce_one(idea, work_root, report: dict | None = None)`: `report` receives `ai_video` (the reel's line) and `spend_usd`.

- [ ] **Step 1: Write the failing tests:**
  - `test_ai_video_reels_use_the_shots` (`VISUAL_SOURCE=ai_video`):
    - `make_shots` gets a `ReelRequest` with the narration's pauses, and a `deadline` of `seconds left - AI_VIDEO_TAIL_SECONDS`;
    - `assemble` gets `cuts=shots.cuts, fps=24`; the burn gets `fps=24`;
    - the format stamp says `visuals: ai_video` with `video_shots` and `shots`;
    - the attempt row gets `spend_usd`, and `report["ai_video"]` is the reel's line.
  - `test_no_shots_falls_back_to_the_ai_path`: `NoShots` → `fetch_broll(source="ai")`, `assemble` without cuts at 30 fps, and the downgrade `ai-path`.
  - `test_fewer_video_shots_than_planned_is_a_downgrade`: `still-shots`.
  - `test_the_disclosure_follows_what_was_shown`: after the fallback, the caption's video line becomes the images line.
  - `test_a_failed_preflight_buys_nothing`: `can_buy=False` reaches `make_shots`.
  - `test_published_and_failed_lines_carry_the_spend`:
    - `✅ Published: <url>` is followed by the reel's line;
    - a failed reel with $0.47 of Higgsfield spend says so in its alert.
  - `test_both_entry_points_begin_the_run`: `begin_run` comes before the opening sweep.
  - `test_preflight` (`test_subtitles.py`, real FFmpeg, skipped without it): a Hinglish ASS burns onto a blank second and returns True; a missing font file still burns, as libass falls back.
  - `test_paid_clips_keep_their_idea_alive` (`test_db_records.py`).
  - `test_settings_defaults`:
    - `_reel_seconds()` is 840 by default;
    - both workflows set `JOB_TIMEOUT_MINUTES` to their Python step's `timeout-minutes` (85 and 55);
    - both pass every `AI_VIDEO_*` setting.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 6.1, 6.4, 6.7 (last rule), 6.8 and 9.9.
  - `begin_run()` runs before the opening sweep in `run` and `make_on_demand`.
  - In `_produce_chain`, when `VISUAL_SOURCE=ai_video`:
    - after the voice: `pauses = subtitles.pauses(audio)`, then the preflight, then `make_shots`;
    - each of its `problems` goes to `_notify`.
  - `_notify_failure` gains the spend when it is above 0.
  - `.env.example` and both workflows get every `AI_VIDEO_*` setting from `vars` with design 12's defaults. `JOB_TIMEOUT_MINUTES` becomes 85 and 55, with the comment saying why (design 6.4). The `VISUAL_SOURCE` comment names `ai_video`.

- [ ] **Step 4: Run the tests,** then the full suite twice (normal, and with every `.env` name blanked). Expected: all green, bar the known NICHE artifact in the blanked run.

- [ ] **Step 5: Docs** (rule 1):
  - STATUS: the 2026-11-13 log and Next actions;
  - CHANGELOG `[Unreleased]`;
  - the handoff: what 3b holds, and that stage 4 is next.

- [ ] **Step 6: Commit.** `git commit -m "feat(production): AI-video reels behind VISUAL_SOURCE=ai_video"`.

- [ ] **Step 7: The final review of stage 3b and its fix pass.** Then ask the operator for:
  - push and merge;
  - one test render with no upload: `tools/try_ai_video.py`, run locally, takes one stored script through narration, `make_shots`, `assemble` and `burn_hinglish` into `test-videos/`. It spends about $0.95 (six clips), and the operator watches the result.
