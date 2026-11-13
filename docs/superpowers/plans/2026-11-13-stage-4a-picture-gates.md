# Stage 4a: the picture gates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nothing an `ai_video` reel shows, and no finished reel of any format, reaches YouTube
without an automatic look: stills with stray lettering, too dark or letterboxed are redrawn once;
broken clips become stills; a broken reel is not uploaded.

**Architecture:** A new module, `src/gates.py`, does the looking (Tesseract, Pillow, FFmpeg) and
returns plain lists of problems. `ai_video` calls it from its two stage-3b seams (`_picture`,
`_check_clip`) and acts on the answer (a redraw, a still); `production` calls it on the burned reel
before the upload. The planner also stops the commonest cause of lettering at its source: a code
check on nouns that invite it (screens above all), quoted back in its one retry.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), Pillow (already a dependency), FFmpeg/ffprobe,
Tesseract 5 as a binary (`tesseract-ocr` on CI), pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-ai-video-reels-design.md`, sections 6.5 and 11.6
(this plan is the gates part of stage 4; the text on screen and the sound are stage 4b).

## Global Constraints

- FFmpeg and Tesseract only; no new Python dependency (Pillow and numpy are already pinned).
- Every subprocess call has a timeout (11.6; true of every call today).
- Tesseract is called as a binary; if it is missing, the text check is skipped with one warning.
- A gate never costs a reel on its own failure to run (rule 14): a check that cannot run is
  skipped with a warning. Only a reel that cannot even be probed is refused.
- The design's thresholds, kept: still text = a word of 3+ letters read at confidence >= 70;
  clips at least 4.5 s, no frozen stretch over 1.5 s; reel within 0.2 s of the narration, audio
  present, no black stretch over 1.0 s, no frozen stretch over 2.0 s.
- No AI attribution anywhere (CLAUDE.md rule 3). Conventional commits.

## Calibration (measured 2026-11-13, before this plan; the evidence for its rulings)

On the six paid Kling clips of idea 561 (re-downloaded, $0) and 32 klein stills drawn for the
purpose (8 planner-like prompts x 2 style lines x 2 seeds, free tier), with Tesseract 5.4 `--psm 11`:

- **The design's rule alone misses FLUX's lettering.** FLUX writes gibberish, and Tesseract's
  confidence falls on non-words: the render's caption "TBEREOROIN" read as "EREORGC" at 46, a
  dark "Welcome" at 11. Real words read at 92-96. Clean stills produce noise words up to 59.
- **Reading a 2x copy as well catches more:** the caption read 90 at 2x, the fake code 73.
  The rule "1x or 2x >= 70" caught 4 of the 5 lettered frames, with 1 false alarm in 33 clean
  ones (a chip read as "Ait" at 83, 2x) — a false alarm costs one free redraw.
- **Screens are the source:** every laptop prompt drew lettering (4 of 4); no other prompt did.
  Hence the planner's noun check (Task 3).
- **Exposure:** one still of seven was letterboxed and dark (middle-half mean 36); every clean
  frame was 83 or brighter. Bars: top and bottom sixteenths both mean < 16 and stddev < 6 — only
  that still.
- **Clips:** all six pass `blackdetect` (0.5 s) and `freezedetect` (-60 dB, 1.0 s).
- **The style line is not the cause:** "cinematic ... film still" against a plainer line made no
  difference to lettering or bars on 32 stills, so it stays.

## Review Focus

1. **Tesseract hangs or crashes on one still** → that still's text check is skipped with a
   warning; the shot keeps its still and the reel goes on (Task 1 test).
2. **The redraw itself fails to draw** (a Workers AI 429 after the first draw) → the first still
   is kept; the shot never loses its picture to the gate (Task 2 test).
3. **A freeze that runs to the clip's end** (freezedetect logs a start and no end) → counted to
   the end, so a clip that stops moving halfway fails (Task 4 real-FFmpeg test).
4. **The reel check's FFmpeg pass times out** → the reel ships with a warning; only an unreadable
   reel is refused (Task 5 test).
5. **Tesseract's TSV carries bytes cp1252 cannot decode** (the Windows console crash seen today
   while calibrating) → decoded as UTF-8 with replacement, never an exception (Task 1 test).

---

### Task 1: `src/gates.py` — the still check

**Files:**
- Create: `src/gates.py`
- Create: `tests/test_gates.py`
- Modify: `.env.example` (one optional line, `TESSERACT_BINARY=`)

**Interfaces:**
- Produces: `gates.still_problems(path: str) -> list[str]` — empty when the still passes; else one
  entry per failed check, each starting with its kind: `"text: 'BER' 90, 'IWLE' 68"`,
  `"dark: 41 < 60"`, `"letterbox bars"`, `"unreadable: <error>"`. Every OCR hit is in the text
  entry (design: "every hit is logged").
- Produces: `gates._ocr_words(path: str) -> list[tuple[str, float]] | None` — words of 3+ ASCII
  letters with their confidence, read from the file and from a grayscale 2x LANCZOS copy
  (`--psm 11`, TSV, `timeout=60`, stdout decoded `utf-8`/`replace`); `None` when no binary.
- Produces: `gates._tesseract() -> str | None` — `TESSERACT_BINARY`, then PATH, then
  `C:\Program Files\Tesseract-OCR\tesseract.exe`; `None` warns once per process.
- Constants: `TEXT_CONFIDENCE = 70`, `TEXT_LETTERS = 3`, `DARK_BELOW = 60`, `BAR_MEAN = 16`,
  `BAR_STDDEV = 6`.

- [ ] **Step 1: Write the failing tests** in `tests/test_gates.py`:
  - `test_a_word_read_at_70_is_text`: fake `subprocess.run` returning a TSV with `TBEREOROIN`
    at 90 and `ani` at 59 → `still_problems` has one entry starting `"text:"` naming TBEREOROIN.
  - `test_noise_under_70_is_not_text`: TSV words at 59 and 68, plus a 2-letter word at 95 → [].
  - `test_the_2x_copy_is_read_too`: the fake returns nothing for the original and a 90 word for
    the `.png` copy → a text problem (the calibration's caption case).
  - `test_no_tesseract_skips_the_text_check_once`: `_tesseract` → None; two stills → `[]` for
    both and exactly one warning in `caplog`.
  - `test_a_tesseract_timeout_skips_the_text_check`: the fake raises `TimeoutExpired` → [].
  - `test_tsv_bytes_cp1252_cannot_read_are_replaced`: TSV bytes with `b"\x9d"` in a word → no
    exception.
  - `test_a_dark_middle_is_dark`: a Pillow image, grey 200 frame with a 30 middle half → `dark`.
  - `test_letterbox_bars_are_found`: rows 0..h/4 and 3h/4..h black, middle bright → `letterbox`.
  - `test_a_dark_backdrop_is_not_bars`: bottom band mean 23, top 52 (clip 4's numbers) → [].
  - `test_an_unreadable_still_is_a_problem`: a file of junk bytes → `["unreadable: ..."]`.
  - `test_real_tesseract_reads_lettering` (skipped when `_tesseract()` is None): Pillow draws
    "WELCOME HOME" (`ImageFont.load_default(size=90)`) on grey → a text problem; a smooth
    gradient → [].
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_gates.py -q` — Expected:
  collection error / failures (no module).
- [ ] **Step 3: Implement** `src/gates.py` with the interfaces above. Brightness and bars from
  Pillow `ImageStat` on the `L` image: middle half = `(w/4, h/4, 3w/4, 3h/4)`; bands = top and
  bottom `h // 16` rows.
- [ ] **Step 4: Run** the same command — Expected: all pass (the real test passes with
  `TESSERACT_BINARY` pointing at a Tesseract, skips without).
- [ ] **Step 5: Commit** `feat(gates): a still check for lettering, darkness and letterbox bars`.

### Task 2: one redraw for a still that fails its check

**Files:** Modify `src/ai_video.py` (`_check_still` removed; `_picture`), `tests/test_ai_video.py`.

**Interfaces:**
- Consumes: `gates.still_problems(path) -> list[str]` (Task 1).
- `_picture(req, shot, i) -> Picture | None` keeps its contract. A drawn still with problems is
  redrawn once at `still_{i:02d}_redraw.jpg` with seed `visuals._image_seed(f"{variant}:redraw", i)`
  (deterministic, rule 12). The redraw is used unless it has more failed checks than the first
  (fewer problems wins; a tie goes to the redraw). A redraw that fails to draw keeps the first
  still. Each failure is logged at WARNING with the shot index and the problems.
- `Picture.animatable` follows the still that is used (`klein` only).

- [ ] **Step 1: Failing tests** (fake `visuals.ai_still` and `gates.still_problems`):
  `test_a_still_with_lettering_is_redrawn_with_a_new_seed`,
  `test_a_redraw_that_fails_too_is_used_and_logged`,
  `test_the_first_still_is_kept_when_the_redraw_is_worse`,
  `test_a_redraw_that_cannot_draw_keeps_the_first_still` (Review Focus 2),
  `test_a_clean_still_is_drawn_once`. Existing `_pictures` tests get a passing gate (fixture
  patching `gates.still_problems` to `lambda p: []` in `_draws`).
- [ ] **Step 2: Run** `pytest tests/test_ai_video.py -q -k "still or picture"` — Expected: fail.
- [ ] **Step 3: Implement** in `_picture`.
- [ ] **Step 4: Run** `pytest tests/test_ai_video.py -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(ai_video): a still that fails its check is redrawn once`.

### Task 3: the planner refuses nouns that draw lettering

**Files:** Modify `src/ai_video.py` (`_planner_prompt`, `plan_shots`), `tests/test_ai_video.py`.

**Interfaces:**
- `_LETTERING`: one compiled, case-insensitive, word-bounded regex for: sign / signs / signboard /
  signage, poster, billboard, banner, placard, plaque, nameplate, headline, caption, subtitle,
  title, text, lettering, letters, words, writing, inscription, graffiti, newspaper, magazine,
  book / notebook, document, label, menu, ticket, receipt, calendar, chart, graph, spreadsheet,
  logo, banknote / currency note, number plate / licence plate / license plate, screen /
  touchscreen, monitor, laptop, computer, tablet, phone / smartphone, television / tv, display,
  dashboard, scoreboard, whiteboard, blackboard, chalkboard, keyboard — singular or plural.
- `_lettering_in(shots: list[dict]) -> list[str]` → e.g. `["laptop (shot 3)", "screen (shot 3)"]`
  from the `still` and `motion` texts, in shot order, each noun once per shot.
- `plan_shots` keeps its signature and its two attempts. A plan with a lettering noun gets the
  retry with the nouns quoted back (with any names, in one note). After the retry, the last plan
  that named no one is used even if it still has a lettering noun (logged; the still gate is then
  the backstop): the noun check never sends a reel to the fallback plan that would have bought
  clips before it.
- The prompt's noun list (rule in "still") names the same devices: "sign, poster, headline,
  screen, laptop, phone, computer, television, keyboard, newspaper, book, chart, label, banner,
  document".

- [ ] **Step 1: Failing tests:** `test_a_laptop_in_a_still_is_sent_back_once`,
  `test_lettering_nouns_are_found_in_any_case_and_plural` ("Laptops", "TV", "touchscreen";
  not "headphones", "design", "photograph", "monitoring"),
  `test_a_plan_still_naming_a_screen_after_the_retry_is_used`,
  `test_a_retry_that_names_someone_falls_back_to_the_plan_without_names`.
- [ ] **Step 2: Run** `pytest tests/test_ai_video.py -q -k "plan or lettering"` — Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_ai_video.py -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(ai_video): the shot planner is sent back for nouns that draw lettering`.

### Task 4: the clip check

**Files:** Modify `src/gates.py`, `src/ai_video.py` (`_check_clip`), `tests/test_gates.py`,
`tests/test_ai_video.py` (`_watch` fakes the gate's probe and stretches).

**Interfaces:**
- `gates.Media` (frozen dataclass): `duration: float`, `video: bool`, `audio: bool`.
- `gates._probe(path) -> Media` — one `ffprobe -show_entries format=duration:stream=codec_type
  -of json` call, `timeout=assembly.PROBE_TIMEOUT_SECONDS`; raises on an unreadable file.
- `gates._stretches(path, black_min, frozen_min, duration) -> tuple[list[float], list[float]]` —
  one `ffmpeg -vf blackdetect=d={black_min}:pix_th=0.10,freezedetect=n=-60dB:d={frozen_min}
  -an -f null -` pass (`timeout=120`), the durations of the black and frozen stretches; a
  `freeze_start` with no `freeze_end` lasts to `duration` (Review Focus 3).
- `gates.clip_problems(path, seconds) -> list[str]` — unreadable, no video stream, shorter than
  `max(4.5, seconds)` (4.5 is the design's floor; covering its shot is 3b's rule), a black
  stretch of 0.5 s or more, a frozen stretch of 1.5 s or more. A stretch pass that cannot run is
  skipped with a warning (the clip is paid for).
- `ai_video._check_clip(path, seconds) -> bool` keeps its signature: `not clip_problems(...)`,
  logging the problems with the clip's file name.

- [ ] **Step 1: Failing tests:** in `test_gates.py`, with fakes: `test_a_clip_shorter_than_4_5_s`,
  `test_a_clip_shorter_than_its_shot`, `test_a_clip_without_video`, `test_a_black_stretch`,
  `test_a_frozen_stretch`, `test_a_stretch_pass_that_fails_is_skipped`; with real FFmpeg
  (skipped without it, as `test_live_caption_burn` is): a 5 s `testsrc2` clip → [], 5 s with
  1 s of `color=black` in the middle → a black problem, 5 s whose last 2.5 s is one frame held
  (`tpad=stop_mode=clone`) → a frozen problem.
- [ ] **Step 2: Run** `pytest tests/test_gates.py -q` — Expected: the new tests fail.
- [ ] **Step 3: Implement**; update `_watch` to fake `gates._probe` (from its `probe`
  argument) and `gates._stretches` (no stretches).
- [ ] **Step 4: Run** `pytest tests/test_gates.py tests/test_ai_video.py -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(gates): a clip check for length, black and frozen stretches`.

### Task 5: the reel check before every upload

**Files:** Modify `src/gates.py`, `src/production.py`, `tests/test_gates.py`,
`tests/test_production.py`, `tests/test_assembly.py` (`test_live_full_reel`).

**Interfaces:**
- `gates.reel_problems(path, narration_seconds) -> list[str]` — unreadable (refused), no audio
  stream, no video stream, duration off the narration by more than 0.2 s, a black stretch over
  1.0 s, a frozen stretch over 2.0 s. A stretch pass that cannot run is skipped with a warning.
- `production.ReelCheckFailed(RuntimeError)`. In `_produce_chain`, after the subtitle burn and
  the metadata, before `progress["stage"] = "upload"`: `progress["stage"] = "check"`; problems →
  `raise ReelCheckFailed("; ".join(problems))`. The existing failure path then records the
  attempt as failed at stage `check` with the reason, sends the idea back to the digest, and
  alerts with the reel's spend. Every format is checked.

- [ ] **Step 1: Failing tests:** `test_gates.py`: `test_a_reel_off_its_narration`,
  `test_a_reel_without_audio`, `test_a_reel_with_a_long_black_stretch`,
  `test_a_reel_whose_check_times_out_ships` (Review Focus 4), `test_an_unreadable_reel_is_refused`;
  `test_production.py`: `test_a_reel_that_fails_its_check_is_not_uploaded` (no `publish` call,
  attempt `failed` at stage `check` with the reason, idea back to `pending`, the alert sent);
  the shared chain fakes get a passing `gates.reel_problems`. `test_live_full_reel` asserts
  `gates.reel_problems(out, dur) == []` on its real render (CI proves the old format passes).
- [ ] **Step 2: Run** `pytest tests/test_gates.py tests/test_production.py -q` — Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite, `pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(production): a reel that fails its check is not uploaded`.

### Task 6: Tesseract on CI, the gates on real media, the docs

**Files:** Modify `.github/workflows/tests.yml`, `make-short.yml`, `production.yml` (apt step:
`tesseract-ocr` added, cache key `apt-ubuntu-24.04-ffmpeg-espeak-ng-tesseract-v2`, step names);
`docs/04-free-tools-reference.md` (Tesseract), `docs/superpowers/specs/2026-11-10-ai-video-reels-design.md`
(11.6: the 2x reading, the calibration numbers, the noun check; 6.5: the noun list),
`STATUS.md`, `CHANGELOG.md`, `docs/superpowers/2026-11-10-ai-video-reels-handoff.md`, `CLAUDE.md`
(the test count).

- [ ] **Step 1:** Run the gates on real media with a local Tesseract: `still_problems` on the
  38 calibration frames (Expected: the calibration's 4 caught, 1 false alarm), `clip_problems` on
  the six paid clips (Expected: all pass), `reel_problems` on the four test renders (Expected:
  all pass). Record the numbers in STATUS.
- [ ] **Step 2:** The workflow and doc edits above.
- [ ] **Step 3: Run** the full suite, `pytest -q` — Expected: all pass; and once with every
  `.env` name blanked — Expected: only the known NICHE artifact.
- [ ] **Step 4: Commit** `ci: Tesseract joins the cached apt packages` and
  `docs(status): stage 4a, the picture gates`.
