# Stage 4b: the text on screen and the sound — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The reel's words sit where Shorts viewers can read them and stay for as long as they
matter (the title for the opening claim, the source with it, one key number when it is said), and
the sound loses the clicks and gains its music bed, as design Part F measured.

**Architecture:** Three settings change their defaults (vignette, cut stings, the music level)
and the key-point cards give way to one key number. `subtitles._build_ass` gains the first
sentence's end (both burns know it: the English one from the aligned words, the Hinglish one from
the sentence times it already computes) and the key number's moment, and places the banner, the
source line, the subtitles and the number inside the safe area. The writer names the key number;
code keeps it only when it is copied exactly from the narration.

**Tech Stack:** Python 3.12/3.13, ASS subtitles burned by libass through FFmpeg, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-ai-video-reels-design.md`, sections 11.3, 11.4, 11.5
and 12 (settings); 7.7 for the Hinglish subtitles; 9.1-9.4 for the writer.

## Global Constraints

- Shorts safe area on 1080x1920 (research, Google's vertical overlay): keep clear the top 288 px,
  the bottom 672 px, the right 192 px and the left 48 px; the safe box is x 48-888, y 288-1248.
- Defaults (design 12): `ENABLE_VIGNETTE=false`, `ENABLE_SFX=false`, `ENABLE_TEXT_CARDS=false`,
  `MUSIC_LU_BELOW_VOICE=4`, in the code and in both production workflows' fallbacks.
- The banner holds until the first sentence ends: at least 1.8 s (`HOOK_SECONDS`), at most 4.0 s
  (new `HOOK_MAX_SECONDS`).
- The source line ("Source: <publisher>") shows with the first sentence and moves out of y 1480.
- One key number a reel, copied exactly from the English narration, large in the upper middle
  with a short scale-in, while the narration says it.
- No AI attribution (rule 3). Conventional commits. Nothing here touches what is bought.

## Review Focus

1. **A first sentence longer than 4.0 s** (the test renders' opening claims ended at 6.6-7.3 s)
   → the banner leaves at 4.0 s, the source line stays to the sentence's end (Task 2 test).
2. **A key number the narration says twice, or inside a longer number** ("2" in "2,000") → the
   card marks its first whole occurrence, never a digit inside another number (Task 4 test).
3. **A key number the writer gets wrong** (absent from the narration, no digit, a repair that
   rewrote it away) → no card, never a wrong one (Task 3 and Task 4 tests).
4. **No aligned words** (the English burn's word timing failed and fell back) or a Hinglish
   reel whose blocks do not carry the number → no card and the banner keeps its 1.8 s
   minimum (Task 2 and Task 4 tests).
5. **A long title** that the banner fits on three rows at a smaller size → the source line sits
   below the banner's real height, not over it (Task 2 test).

---

### Task 1: the sound and the look (defaults)

**Files:** `src/assembly.py` (`ENABLE_VIGNETTE`, `ENABLE_SFX`, `MUSIC_LU_BELOW_VOICE` defaults),
`src/subtitles.py` (`ENABLE_TEXT_CARDS` default, both uses), `.github/workflows/make-short.yml`
and `production.yml` (fallbacks `'false'`, `'false'`, `'4'`), `.env.example`, the tests that pin
the old defaults (`tests/test_assembly.py`, `tests/test_subtitles.py`).

- [ ] **Step 1: Failing tests:** `test_the_vignette_is_off_by_default`,
  `test_cut_stings_are_off_by_default`, `test_the_music_bed_sits_4_lu_under_the_voice`
  (`levels["bed"] == target - 4 - bed` with the setting unset), `test_key_point_cards_are_off_by_default`
  (`_build_ass` with key points and no setting has no `Card` event). Each also checks that the
  setting set to the old value brings the old behaviour back.
- [ ] **Step 2: Run** `pytest tests/test_assembly.py tests/test_subtitles.py -q` — Expected: the
  four fail.
- [ ] **Step 3: Implement** the defaults; update the tests that asserted the old defaults to set
  the setting explicitly (behaviour kept, not deleted, design 17).
- [ ] **Step 4: Run** the full suite — Expected: pass.
- [ ] **Step 5: Commit** `feat(assembly): no vignette, no cut stings, the music bed 4 LU under the voice`.

### Task 2: the banner, the source line and the subtitles in the safe area

**Files:** `src/subtitles.py`, `src/assembly.py` (`BRAND_LOGO_HEIGHT` default 96), `.env.example`
(`HOOK_MAX_SECONDS`, the logo and source defaults), `tests/test_subtitles.py`.

**Interfaces:**
- `_build_ass(words, hook_text=None, key_points=None, total_dur=None, source_label=None,
  first_end: float | None = None, number: tuple[float, float, str] | None = None) -> str`.
- `_banner_seconds(first_end: float | None) -> float` — `min(HOOK_MAX_SECONDS 4.0,
  max(HOOK_SECONDS 1.8, first_end or 0))`.
- The source line: shown `0 -> max(HOOK_SECONDS, first_end)` (`SOURCE_CITE_SECONDS` when
  `first_end` is None), top-anchored (alignment 8) under the banner: its `MarginV` is 300 plus the
  banner's rows times its font size times 1.25 plus 16 (300 when there is no banner).
- Styles: `Karaoke` and `Sub` margins L 48, R 192, V 672 (the safe box's bottom at y 1248).
- `_first_sentence_end(words, script_text) -> float | None` — the aligned word that ends
  `text.split_sentences(script_text)[0]` (counted in words); None without words.
- `burn_captions` computes `first_end` from its aligned words; `burn_hinglish` uses
  `sentence_ends(...)[0]`, which `subtitle_blocks` already computes (expose it, do not recompute
  differently).

- [ ] **Step 1: Failing tests:** `test_the_banner_holds_for_the_first_sentence` (first_end 3.1 →
  banner 0-3.1), `test_the_banner_holds_between_1_8_and_4_0` (1.2 → 1.8; 6.9 → 4.0),
  `test_the_source_line_shows_with_the_first_sentence` (6.9 → source 0-6.9 while the banner ends
  at 4.0; Review Focus 1), `test_the_source_line_sits_under_the_banner` (a 3-row banner at a
  smaller size → `MarginV` from its real rows and size; Review Focus 5),
  `test_subtitles_sit_inside_the_safe_box` (both styles' margins), `test_no_words_keeps_the_1_8_s_banner`
  (Review Focus 4), `test_first_sentence_end_from_aligned_words`, and in the Hinglish burn
  `test_hinglish_banner_ends_with_line_one`.
- [ ] **Step 2: Run** `pytest tests/test_subtitles.py -q` — Expected: the new tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite — Expected: pass.
- [ ] **Step 5: Commit** `feat(subtitles): the banner and the source line stay for the first sentence, inside the safe area`.

### Task 3: the writer names the key number

**Files:** `src/scriptwriter.py` (the writer's prompt and its parse; the repair keeps it only if
still in the body), `tests/test_scriptwriter.py`.

**Interfaces:**
- The prompt's field list gains: `- "key_number": the one number that carries the story (a
  count, an amount, a percentage, a date or a year), copied exactly as it is written in
  script_body, with its unit when the unit is written next to it ("286 days", "Rs 2,000 crore",
  "40%"); an empty string when the story has none.` The JSON example gains `"key_number": "..."`.
- `_key_number(data: dict, body: str) -> str` — the writer's value, stripped, kept only when it
  has a digit and occurs in `body` as a whole phrase (not inside a longer number: "2" in
  "2,000" does not count); else "". The script dict carries `key_number`.
- After a repair that rewrites the body, `key_number` is re-checked against the new body.

- [ ] **Step 1: Failing tests:** `test_the_key_number_is_kept_when_copied_exactly`,
  `test_a_key_number_not_in_the_narration_is_dropped`, `test_a_key_number_without_a_digit_is_dropped`,
  `test_a_digit_inside_a_longer_number_does_not_count` (Review Focus 2/3),
  `test_a_repair_that_drops_the_number_drops_the_card`, and the prompt names the field.
- [ ] **Step 2: Run** `pytest tests/test_scriptwriter.py -q` — Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_scriptwriter.py tests/test_production.py -q` — Expected: pass.
- [ ] **Step 5: Commit** `feat(scriptwriter): the writer names the reel's key number`.

### Task 4: the key-number card

**Files:** `src/subtitles.py`, `src/production.py` (passes `key_number=script.get("key_number")`
to both burns), `tests/test_subtitles.py`, `tests/test_production.py`.

**Interfaces:**
- Style `Number`: the caption font, 150 px, white with a black outline 8, alignment 8 (top
  centre), margins L 48, R 192, V 700 (the upper middle, under the banner and the source line).
- `_number_moment_words(key_number, words) -> tuple[float, float] | None` — the first run of
  aligned words whose normalized text equals the number's tokens (digits compared without
  commas); None when not said.
- `_number_moment_blocks(key_number, blocks) -> tuple[float, float] | None` — the first English
  block whose text contains the number as a whole phrase.
- The event: shown from the moment it is said for `max(1.5, spoken + 0.5)` s, at most 2.5 s, never
  past the reel's end; text `{\fscx70\fscy70\t(0,180,\fscx100\fscy100)}` + the number in capitals.
- `burn_captions(..., key_number: str | None = None)`, `burn_hinglish(..., key_number=None)`.

- [ ] **Step 1: Failing tests:** `test_the_number_shows_when_it_is_said` (English words),
  `test_the_number_shows_with_its_block` (Hinglish), `test_the_number_scales_in`,
  `test_a_number_never_said_has_no_card`, `test_the_card_stays_inside_the_reel`,
  `test_a_number_said_twice_marks_the_first` (Review Focus 2), `test_no_words_no_card`
  (Review Focus 4), and in production `test_the_key_number_reaches_both_burns`.
- [ ] **Step 2: Run** `pytest tests/test_subtitles.py tests/test_production.py -q` — Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite — Expected: pass.
- [ ] **Step 5: Commit** `feat(subtitles): one key number, large, when the narration says it`.

### Task 5: a look at the result, and the docs

**Files:** `tools/try_ai_video.py` (`--key-number`, so an older script can show the card),
`tests/test_try_ai_video.py`, `STATUS.md`, `CHANGELOG.md`, the design (11.3-11.5: where things now
sit), the handoff, `CLAUDE.md`, `.env.example`.

- [ ] **Step 1:** Failing test for `--key-number` reaching the burn; implement; run.
- [ ] **Step 2:** One test render of script 441 reusing its six paid clips ($0 of Higgsfield; the
  Hinglish rendering costs cents of Claude), with `--key-number`. Look at frames at 0.5 s, 3 s,
  the number's moment and the end; measure the bed against the voice (`ebur128` on the mix and on
  the narration). Expected: the banner held to line 1's end, the source line under it, the
  subtitles inside the safe box, the number large and scaled in, no vignette, no clicks, the bed
  audibly present. Send the render to the operator.
- [ ] **Step 3:** The docs; the full suite; the suite with `.env` blanked (only the NICHE artifact).
- [ ] **Step 4: Commit** `feat(try_ai_video): --key-number` and `docs(status): stage 4b`.
