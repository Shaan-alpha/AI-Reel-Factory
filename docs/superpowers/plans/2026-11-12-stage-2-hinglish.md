# Stage 2: Hinglish Narration, English Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behind `NARRATION_LANGUAGE=hinglish`, every fact-checked English script is rendered line by line as spoken Hinglish, checked in code and by a second model, voiced only by Hindi-capable voices, trimmed, and captioned with English subtitles timed from the narration's pauses; any failure narrates the reel in English as today.

**Architecture:** A new `src/hinglish.py` owns the two-text lines: rendering (Claude, then Gemini, then Groq), the code checks, the meaning check and number-to-words. `src/voice.py` gains a Hindi route chosen by script, a length band, and the trim. `src/subtitles.py` gains a Hinglish burn that needs no speech recognition. `src/production.py` wires them, with English as the fallback at every step. `src/llm.py` gains a provider-pinned call, plus structured output and the refusal fallback for Claude.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, the Anthropic SDK 1.12.1 (`output_config.format`, beta `fallbacks`), google-genai, FFmpeg `silencedetect`/`atrim`.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md), section 7 (Part B), section 12 (settings), section 13 (`scripts.spoken`), section 14 (stage 2 row).

## Global Constraints

- Everything new is behind `NARRATION_LANGUAGE=hinglish`; with the default `english`, a reel is byte-for-byte today's path.
- "A Hinglish failure never costs the reel" (7.6): every failure ends in English narration, today's captions, audio language `en`, and one Telegram line.
- No new Python dependency; no new billed service. Claude spend goes through the `claude_spend` ledger with purpose `hinglish`.
- Edge-tts and Kokoro never receive Devanagari (7.5).
- A write naming `scripts.spoken` retries without it when the column is missing (the stage 0 pattern).
- Conventional commits, no AI attribution; the suite green normally and with `.env` blanked.

## Review Focus

1. **Text that only partly renders** (the model returns 5 lines for 6 sentences, or the same `i` twice): the code check fails it and the retry gets the failure list. Test: Task 2, `test_a_missing_or_repeated_line_fails`.
2. **A number written in Hindi words** ("दो दिन") or turned into a different digit: fails, since the number guard cannot see Hindi words. Test: Task 2, `test_hindi_number_words_and_changed_digits_fail`.
3. **A Hindi voice that silently reads English only** (edge-tts style), or reads twice as long: the length band moves to the next engine, and with none left the reel is English. Test: Task 6, `test_a_render_outside_the_length_band_moves_on`.
4. **Pauses that do not line up with sentence ends** (a breath inside a sentence, no pause at a real end): the global assignment still orders the ends, and a sentence never gets zero time. Test: Task 7, `test_sentence_ends_follow_test_4s_hand_placed_ends`, `test_assignment_survives_too_few_pauses`.
5. **The renderer's `parts` that do not match the sentence** (an English word not in the sentence, a number dropped): the whole English sentence shows instead. Test: Task 7, `test_bad_parts_fall_back_to_the_whole_sentence`.

---

### Task 1: Provider-pinned calls; Claude with a schema and the refusal fallback

**Files:**
- Modify: `src/llm.py` (`generate_claude` 823-899, `_claude_create` 785-800; new `generate_with`)
- Test: `tests/test_llm.py`, `tests/test_claude.py`

**Interfaces:**
- Produces: `llm.generate_with(provider: str, prompt: str, *, json: bool = False, max_tokens: int = 1024) -> str`, with `provider` "gemini" or "groq" (one provider, the usual retry, raises on failure); `llm.generate_claude(prompt, *, purpose="script", schema: dict | None = None, fallbacks: bool = False) -> str`.

- [ ] **Step 1: Write the failing tests:**
  - `test_generate_with_uses_only_the_named_provider`: with `_gen_gemini` raising and `_gen_groq` returning "ok", `generate_with("groq", ...)` is "ok" and `generate_with("gemini", ...)` raises; an unknown provider raises ValueError.
  - `test_claude_schema_is_sent_as_structured_output`: the create call gets `output_config == {"effort": "low", "format": {"type": "json_schema", "schema": S}}`.
  - `test_claude_fallbacks_use_the_beta_server_side_fallback`: with `fallbacks=True` the call goes through the beta path with `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`.
  - `test_a_fallback_call_reserves_at_the_highest_price`: the reserved worst case uses `_ANTHROPIC_PRICE_FALLBACK`, and the settled cost uses the price of `resp.model`.
  - `test_a_refusal_raises`: `stop_reason == "refusal"` raises RuntimeError, as other unfinished replies do.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_llm.py tests/test_claude.py -q -p no:cacheprovider`. Expected: the five FAIL.

- [ ] **Step 3: Implement.** `generate_with` reuses `_call_with_retry` with `_gen_gemini` or `_gen_groq`. In `generate_claude`, `schema` merges `{"format": {"type": "json_schema", "schema": schema}}` into `output_config`. `fallbacks=True` calls `_anthropic_client().beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")` (claude-api skill: Claude Opus 5.5 refusal handling). With `fallbacks=True`, the worst case is priced at `_ANTHROPIC_PRICE_FALLBACK`, since another model may answer, and the settled cost at `resp.model`'s price. The script call is unchanged.

- [ ] **Step 4: Run the tests.** Expected: all pass, `tests/test_claude.py` whole.

- [ ] **Step 5: Commit.** `git commit -m "feat(llm): a provider-pinned call; Claude with structured output and the refusal fallback"`.

### Task 2: The code checks and number-to-words

**Files:**
- Create: `src/hinglish.py`
- Test: `tests/test_hinglish.py`

**Interfaces:**
- Produces: `hinglish.english_lines(body: str) -> list[str]` (the fact-checked script's sentences, delivery tags removed, via `text.split_sentences`); `hinglish.check(en_lines: list[str], lines: list[dict]) -> list[str]` (failure messages, empty when it passes; `lines` are `{"i": int, "hi": str, "parts": [...]}`); `hinglish.say_numbers(text: str) -> str`; `hinglish.spoken_seconds(said: str) -> float` (words / 2.9).

- [ ] **Step 1: Write the failing tests** on test 4's six pairs (research_notes/Spikes 2026-11-10/code/spike4.py `UNITS`, with digits restored in `hi`):
  - `test_test_4s_lines_pass`.
  - `test_a_missing_or_repeated_line_fails`: 5 lines for 6, a duplicated `i`, an `i` of 7.
  - `test_hindi_number_words_and_changed_digits_fail`: "दो दिन" fails (एक passes); "25.9" turned into "26.9" fails; an extra "3" fails.
  - `test_a_name_must_stay_in_latin`: "Voyager" written in Devanagari fails.
  - `test_scripts_are_checked`: no Devanagari fails; a Cyrillic or emoji character fails; ZWJ and ZWNJ pass.
  - `test_the_spoken_length_must_fit`: 40 said words (13.8 s) fails against `HINGLISH_MIN_SECONDS` 24; test 4's `said` passes.
  - `test_say_numbers`:
    - "1977" → "nineteen seventy-seven", "2005" → "two thousand five", "2026" → "twenty twenty-six";
    - "25.9 billion" → "twenty-five point nine billion";
    - "40%" → "forty percent";
    - "₹500" → "five hundred rupees", "$2 billion" → "two billion dollars";
    - "18th" → "eighteenth", "1,250" → "one thousand two hundred fifty", "1,25,000" → "one lakh twenty-five thousand";
    - "1500 crore" → "one thousand five hundred crore" (a year only from 1800 to 2099, and never before a scale or unit word).

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL (no module).

- [ ] **Step 3: Implement** from design 7.3.
  - **Numbers.** A number token is digits with `,` `.` `%`, a currency symbol or an ordinal suffix. The Hindi number words are दो तीन चार पाँच पांच छह छः सात आठ नौ दस … नब्बे सौ हज़ार हजार लाख करोड़ करोड अरब; एक is exempt.
  - **Names.** A name is a capitalised word that does not start its sentence. "I" and the month after a number are still names.
  - **Allowed characters.** Devanagari U+0900-U+097F, Latin, digits, spaces, `.,;:!?'"()-–—…।`, `₹$€£%`, ZWJ and ZWNJ.
  - **Number words.** Cardinals are written by a small function in the module (no dependency). Indian grouping (`\d{1,2}(,\d{2})+,\d{3}`) reads in lakh and crore; other numbers read in thousand, million and billion.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(hinglish): the line checks and spoken numbers"`.

### Task 3: Rendering

**Files:**
- Modify: `src/hinglish.py`
- Test: `tests/test_hinglish.py`

**Interfaces:**
- Consumes: `llm.generate_claude(..., schema=, fallbacks=True)`, `llm.generate_with`.
- Produces: `hinglish.render(en_lines: list[str], title: str, tone: str, failures: list[str] | None = None) -> tuple[list[dict], str]` (the lines and the renderer: "claude", "gemini" or "groq"; raises RuntimeError when no renderer answers with parseable lines).

- [ ] **Step 1: Write the failing tests:**
  - `test_claude_renders_with_the_schema_and_purpose`: one Claude call with `purpose="hinglish"`, a schema requiring `lines[].i/hi/parts[].hi/en`, and `fallbacks=True`. The prompt carries the numbered English lines, the title, the tone and the rules: Devanagari for Hindi, Latin for English and names, digits kept, no Hindi number words, sentence one at most 12 words with the subject inside the first four, `।` endings. The English lines are not echoed back in the output schema.
  - `test_gemini_then_groq_render_when_claude_cannot`: `ClaudeUnavailable` → `generate_with("gemini")`; that raising → `generate_with("groq")`; the renderer is reported.
  - `test_a_retry_carries_the_failures`: `failures=["line 2: number 25.9 missing"]` appears in the prompt.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.2. The prompt describes the rules, not phrases to copy (design 9.1's rule applies here too). The reply is parsed with `llm.parse_json_object`.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(hinglish): rendering, Claude first"`.

### Task 4: The meaning check

**Files:**
- Modify: `src/hinglish.py`
- Test: `tests/test_hinglish.py`

**Interfaces:**
- Produces: `hinglish.meaning_check(en_lines: list[str], lines: list[dict], renderer: str) -> tuple[list[str], str]` (failures and the checker's provider).

- [ ] **Step 1: Write the failing tests:**
  - `test_the_checker_is_never_the_renderer`: claude → gemini, gemini → groq, groq → gemini.
  - `test_a_line_judged_different_fails`: `{"lines": [{"i": 2, "same": false, "why": "..."}]}` → one failure naming line 2.
  - `test_a_checker_that_cannot_run_fails_when_strict`: `HINGLISH_STRICT` unset or true means a failure; false means a pass with a log line.
  - `test_every_verdict_is_logged`.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.4. Each line is judged: does `hi` say the same as `en`, with nothing added, dropped, or changed in strength?

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(hinglish): a second model checks the meaning"`.

### Task 5: One call from script to spoken lines; stored on the script row

**Files:**
- Modify: `src/hinglish.py`, `src/db.py` (new `set_script_spoken`), `docs/03-setup-guide.md` (SQL)
- Test: `tests/test_hinglish.py`, `tests/test_db_records.py`

**Interfaces:**
- Produces: `hinglish.to_hinglish(body: str, title: str, tone: str) -> tuple[dict | None, str]`. It returns the spoken record and a reason. The record is `{"language": "hi", "lines": [{"en", "hi", "said", "parts"}], "said": str, "renderer", "checker"}`; on failure it is None with the reason. `db.set_script_spoken(script_id: int, spoken: dict) -> None` (tolerant).

- [ ] **Step 1: Write the failing tests:**
  - `test_to_hinglish_passes_and_speaks_numbers`: `said` joins the lines' `said`, which turn digits into words.
  - `test_one_failed_check_is_retried_with_its_failures`.
  - `test_two_failed_checks_end_hinglish`: returns `(None, reason)`.
  - `test_a_failed_meaning_check_is_retried_once`.
  - `test_set_script_spoken_survives_a_missing_column` (test_db_records).

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.3-7.4. A render failure, a check failure and a meaning failure share one retry. Add `alter table scripts add column if not exists spoken jsonb;` to the stage 2 block in docs/03 §4.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(hinglish): script to checked spoken lines, stored on the script row"`.

### Task 6: The Hindi voice route, the length band, the trim

**Files:**
- Modify: `src/voice.py`
- Test: `tests/test_voice.py`

**Interfaces:**
- Produces: `voice.synthesize(script_body, out_dir, meta=None, tone=None, expected_seconds: float | None = None)`. Text containing Devanagari takes the Hindi route: Gemini with `HINGLISH_STYLE_PROMPT`, then Chirp `GOOGLE_TTS_VOICE_HI` (default `hi-IN-Chirp3-HD-Charon`, language `hi-IN`). The Hindi route never uses edge-tts or Kokoro. Each output must be within 0.75-1.30 × `expected_seconds` and is then trimmed (`voice.trim_silence(path) -> float`). Meta gains `"route": "hi"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_devanagari_never_reaches_edge_or_kokoro`.
  - `test_the_hindi_route_uses_charon_style_and_the_hindi_chirp_voice`.
  - `test_a_render_outside_the_length_band_moves_on`: 0.67 and 1.56 × expected move on; 1.01 is kept.
  - `test_trim_silence_cuts_head_and_tail`: an FFmpeg-made tone with 1 s of silence at each end comes out within 0.15 s of the tone.
  - `test_the_somber_hinglish_prompt_keeps_the_accent_direction`.
  - `test_the_retiring_developer_api_models_are_skipped_after_the_shutdown`: on and after 2026-11-17 they are never asked, Vertex or not.
  - `test_english_text_takes_todays_chain`: unchanged.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.5.
  - `HINGLISH_STYLE_PROMPT` is test 4's prompt word for word (spike4.py `STYLE`). The somber version is calm and unhurried, with the same accent direction.
  - No inline tags in Hinglish text.
  - The trim uses FFmpeg `silenceremove` at the start and the end, keeping a 0.05 s margin.
  - `GOOGLE_TTS_VOICE` defaults to `en-IN-Chirp3-HD-Charon` and `GEMINI_TTS_VOICE` to `Charon` in code. The workflows keep `Zubenelgenubi` as their fallback until the relaunch sets the variables (design 15), so the live English voice does not change at merge.
  - Before enabling the Hindi Chirp link, run one live render of test 4's line 3 through `_synthesize_google` with the Hindi voice (Cloud TTS, about $0.01). Ledger the measured length against the band; if it fails, the link stays out and the route is Gemini only.

- [ ] **Step 4: Run the tests.** Expected: all pass, `tests/test_voice.py` whole.

- [ ] **Step 5: Commit.** `git commit -m "feat(voice): the Hindi route, a length band and the trim"`.

### Task 7: English subtitles timed from the narration

**Files:**
- Modify: `src/subtitles.py`
- Create: `tests/fixtures/hinglish_test4.json` (test 4's pauses from `silencedetect`, its duration, its six pairs and its hand-placed ends, `hf_spike4_sentence_ends.json`)
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Produces:
  - `subtitles.pauses(audio_path: str) -> list[tuple[float, float]]` (`silencedetect=noise=-38dB:d=0.12`);
  - `subtitles.sentence_ends(pauses, weights: list[int], duration: float) -> list[float]` (the global assignment);
  - `subtitles.burn_hinglish(video_path, audio_path, out_path, lines: list[dict], hook_text=None, source_label=None) -> str`.

- [ ] **Step 1: Write the failing tests:**
  - `test_sentence_ends_follow_test_4s_hand_placed_ends`: from the fixture's pauses and the lines' spoken characters, every inner end lands within 0.35 s of the hand-placed one.
  - `test_assignment_survives_too_few_pauses`: 2 pauses for 6 sentences still gives 5 increasing ends, none giving a sentence under 0.5 s.
  - `test_parts_become_blocks_in_spoken_order`.
  - `test_bad_parts_fall_back_to_the_whole_sentence`: an `en` part with a word not in the sentence, or a dropped number, shows the whole sentence in one or two blocks.
  - `test_blocks_are_plain_white_two_lines_at_most_and_never_one_word_alone`.
  - `test_burn_hinglish_needs_no_speech_recognition`: `_transcribe_words` must not be called.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.7.
  - **Assignment:** a dynamic program over the pauses, in order. It minimises the sum of |a sentence's cumulative share of spoken characters − its cumulative share of time|, with each end at a pause's start.
  - **Parts:** each boundary falls at the parts' share of characters, snapped to a pause within 0.3 s.
  - **Style:** a "Sub" ASS style, white, about 86 px, bottom-aligned at the karaoke's margin, MarginR 150 (the action rail), clear of the Source line.
  - **Wrapping:** wrap with `_caption_px`; a block over two lines splits in time.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(subtitles): English subtitles timed from the narration's pauses"`.

### Task 8: Wire it into the reel, English as the fallback

**Files:**
- Modify: `src/production.py` (`_produce_chain` 345-386, `_downgrades`, `_format`), `.env.example`, `.github/workflows/make-short.yml`, `.github/workflows/production.yml`
- Test: `tests/test_production.py`

**Interfaces:**
- Consumes: Tasks 5, 6 and 7.
- Produces: with `NARRATION_LANGUAGE=hinglish`:
  - the stage "hinglish" runs after the gate;
  - Hinglish voiced means audio language `hi`, format language `hi`, the Hinglish burn, and `spoken` stored;
  - any failure means English narration, today's burn, `en`, the downgrade `english-narration`, and one `_notify` line.

- [ ] **Step 1: Write the failing tests:**
  - `test_english_is_unchanged_by_default`: no hinglish call.
  - `test_a_hinglish_reel_is_voiced_captioned_and_uploaded_as_hindi`.
  - `test_a_hinglish_render_failure_narrates_in_english_and_says_so`.
  - `test_no_hindi_voice_narrates_in_english`.
  - `test_the_spoken_record_is_stored`, including `{"language": "en"}` on the English fallback.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 7.6 and 12. Pass `NARRATION_LANGUAGE`, `HINGLISH_STRICT`, `HINGLISH_MIN_SECONDS`, `HINGLISH_MAX_SECONDS` and `GOOGLE_TTS_VOICE_HI` through both workflows, and document them in `.env.example`.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(production): Hinglish reels behind NARRATION_LANGUAGE, English as the fallback"`.

### Task 9: A live check, the docs, the suite, the final review

- [ ] **Step 1: One live Hinglish run, locally, with no upload.** Render test 3's English script lines through `to_hinglish` (Claude, about $0.03), voice them (Vertex, cents), and burn the subtitles on a still. Record the renderer, the checker, the measured length and the band, then look at the frame grabs.
- [ ] **Step 2: Docs:** STATUS.md (including PR #18's merge), CHANGELOG, docs/05 (the two-text lines), docs/03 (the SQL), docs/08 if the AI-voice rules change, and the handoff.
- [ ] **Step 3: Full suite twice** (normally, and with `.env` blanked). Expected: all pass, bar the known `NICHE` artifact under blanking.
- [ ] **Step 4: The final review of stage 2,** then the fix pass, then ask the operator before pushing.
