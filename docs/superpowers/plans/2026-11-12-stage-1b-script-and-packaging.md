# Stage 1b: Script and Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The English script becomes a plain explainer for Indian viewers with the payoff made concrete, three structures, one short title, a length set in seconds, guarded rewrites, a stricter fact-check that logs its grounding, and cleaner packaging.

**Architecture:** Almost all of it is `src/scriptwriter.py` (prompt, JSON contract, guards); `src/factcheck.py` and `src/llm.py` for the gate's thinking and the grounding log; `src/production.py` and `src/publish_youtube.py` for the description, hashtags, tags and category. Second half of the design's stage 1, on branch `feat/stage-1-stories-script` after 1a.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, google-genai (Vertex), the Anthropic API path already in `llm`.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md), section 9 (9.1, 9.3-9.9; the opening check of 9.2 shipped in stage 0) and section 13 (the `scripts` columns).

## Global Constraints

- No new Python dependency; no new billed service.
- Every new guard is fail-soft: a check that cannot run keeps the script as written and logs (rule 14); only the fact-check gate blocks.
- The added-facts guard (`_added_facts`) applies to every model-written rewrite.
- Script-row writes naming `scripts.structure` or `scripts.grounding` retry without them when the columns are missing (the stage 0 pattern).
- Prompt text describes moves; it carries no quotable example phrases (design 9.1).
- Conventional commits, no AI attribution; the full suite green normally and with `.env` blanked.

## Review Focus

1. **The writer's JSON omits the new fields** (`payoff_index`, `optional`, `structure`): every guard falls back to today's behaviour. Test: Task 4, `test_a_script_without_the_new_fields_still_ships`.
2. **A title the writer cannot shorten** (the second call fails): cut at a word boundary inside 7 words and 44 characters, never mid-word. Test: Task 3, `test_a_long_title_is_cut_at_a_word`.
3. **Over budget with no optional sentence marked:** the whole-sentence cut still keeps sentence one and the payoff. Test: Task 4, `test_over_budget_without_optional_sentences_keeps_the_payoff`.
4. **The gate at default thinking runs out of tokens:** the larger budget keeps its JSON whole. Test: Task 6, `test_the_gate_asks_for_room_to_think`.
5. **A description with only aggregator links:** at least one link is kept, never none. Test: Task 7, `test_sources_keep_one_link_when_only_aggregators_exist`.

---

### Task 1: The writer's brief

**Files:**
- Modify: `src/scriptwriter.py` (`_PROMPT_N` 46-128, `_SOMBER_NOTE` 154-159, `_build_prompt` 184-206, `_CLAUDE_DRAFT_NOTE` 247-255)
- Modify: `src/voice.py` (`_DEFAULT_STYLE_PROMPT` 110-117)
- Test: `tests/test_scriptwriter.py`, `tests/test_voice.py`

**Interfaces:**
- Produces: `_PROMPT_N` placeholders `{title}`, `{hook}`, `{angle}`, `{sources}`, `{structure}`, `{target_seconds}`, `{target_words}`, `{max_words}`; JSON fields `title`, `script_body`, `caption`, `hashtags`, `tags`, `key_points`, `payoff_index` (0-based sentence index), `optional` (list of 0-based sentence indices), `structure`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_brief_names_the_viewer_and_drops_the_roast`: `_PROMPT_N` contains "Indians aged about 18-34" and "what changes for a person in India"; it contains none of "SARCASTIC", "roast", "Here's the catch", "Wait, it gets weirder", "Comment below", "💬", "[sarcastic]", "[deadpan]".
  - `test_the_somber_note_needs_no_bridge_phrase`: `_SOMBER_NOTE` does not contain "Here's why it matters".
  - `test_the_english_style_prompt_is_informative`: `voice._DEFAULT_STYLE_PROMPT` contains "informative" and "Indian English accent" and not "unimpressed".

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_scriptwriter.py tests/test_voice.py -q -p no:cacheprovider`. Expected: the three FAIL.

- [ ] **Step 3: Rewrite the prompt** from design 9.1-9.5: the viewer (the stage 1a wording); a clear, curious, confident explainer, no sarcasm, no roast, no jokes at anyone's expense; sentence one states the newest or most extreme true fact with its subject and the Indian stake in its first clause, never a wind-up, a date or a greeting; the structure block `{structure}` (Task 2); the payoff says what changes for a person in India (a price, a rule, a date, a risk, a job) from the sources, or what changes for anyone when there is no Indian stake; length "about {target_seconds} seconds, about {target_words} words, never more than {max_words}"; the delivery tags shrink to `[pause]`, `[serious]` and `[curious]`, at most two; the title rule of Task 3; the caption: line 1 restates the claim with its main keyword, line 2 one sentence on why it matters, no links, no question to the viewer; hashtags at most two naming the story's subject or event, no `#Shorts`; tags at most six (names and alternate spellings, Hindi spellings allowed); `payoff_index`, `optional` and `structure` in the JSON. Keep the accuracy and truth-over-neutrality paragraphs. The somber note keeps its effect without the bridge phrase. `_CLAUDE_DRAFT_NOTE` gains `{searched}`: "searched the live web" only when the draft has citations (Task 6), else "a draft whose search could not be confirmed". The English style prompt becomes test 3's approved narrator prompt with "a neutral Indian English accent" in place of "a General American accent" (it voices English reels until the Hinglish relaunch).

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_scriptwriter.py tests/test_voice.py tests/test_claude.py -q -p no:cacheprovider`. Expected: all pass; update any old test that asserts the sarcastic wording, with the behaviour.

- [ ] **Step 5: Commit.** `git commit -m "feat(scriptwriter): a plain explainer for Indian viewers, with a concrete payoff"`.

### Task 2: Three structures

**Files:**
- Modify: `src/scriptwriter.py` (new `_STRUCTURES`, `structure_for`; `_build_prompt`; `write_script` return), `src/db.py` (`insert_script` 194-206)
- Test: `tests/test_scriptwriter.py`, `tests/test_db_records.py`

**Interfaces:**
- Produces: `scriptwriter.STRUCTURES = {"what-happened": str, "number": str, "belief": str}` (each a short prompt block); `scriptwriter.structure_for(idea: dict) -> str`; `write_script(...)["structure"]`; `db.insert_script(..., structure: str | None = None)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_structure_is_stable_per_idea_and_somber_takes_the_first`: the same idea id always gives the same structure; over ids 1-60 all three appear; a somber idea gives `"what-happened"`.
  - `test_the_structure_block_reaches_the_prompt`: `_build_prompt` for an idea whose structure is `"number"` contains that block's text.
  - `test_insert_script_stores_the_structure_and_survives_a_missing_column`: `structure="belief"` is in the row; a PGRST204 retries without it.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.3: the true surprising fact is always sentence one; then (1) what happened: how it happened, why it matters, what is scheduled next; (2) the number: what it measures, what it compares with, why it matters; (3) the belief: the common belief it overturns, only when a source records that belief, the evidence, why it matters. A "what is next" beat must be a scheduled step the sources record; a belief is stated as a belief. The choice is `sha1(str(idea_id))` modulo 3; somber is always `what-happened`. The writer may fall back to `what-happened` and says so in `structure`; `write_script` stores the writer's value when it is a known structure, else the chosen one.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(scriptwriter): three structures, chosen per idea and stored"`.

### Task 3: One short title

**Files:**
- Modify: `src/scriptwriter.py` (`_TITLE_MAX` 209, `_fit_title` 212-224; new `_shorten_title`)
- Test: `tests/test_scriptwriter.py`

**Interfaces:**
- Produces: `_TITLE_MAX = 44`, `_TITLE_MAX_WORDS = 7`; `scriptwriter._shorten_title(title: str, body: str) -> str` (one model call, then a word-boundary cut; always within both limits).

- [ ] **Step 1: Write the failing tests:**
  - `test_a_title_within_the_limits_is_kept`: "ISRO's new rocket can land itself" (6 words, 33 characters) is unchanged and no model call is made.
  - `test_a_long_title_is_shortened_once`: a stubbed model returns "India bans 3 apps for students" for a 12-word title → that title.
  - `test_a_long_title_is_cut_at_a_word`: the model fails → the result has at most 7 words and 44 characters and ends on a whole word.
  - `test_a_shortened_title_that_adds_a_fact_is_refused`: the model's title carries a number the body lacks → the word-boundary cut is used instead.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.4 and replace the call in `write_script`: over either limit, one `llm.generate(json=True)` asking for `{"title": ...}` within both limits with the searchable name first, accepted only within the limits and with no added fact; else cut at the last whole word that fits. The punch-up's title goes through the same function.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(scriptwriter): one title of 7 words and 44 characters, which is also the banner"`.

### Task 4: Length in seconds; the payoff by index; the hook judge off

**Files:**
- Modify: `src/scriptwriter.py` (`_max_words` 226-230, `_enforce_length` 642-656, `_payoff_start` 500-510, `_ensure_delivery_tag` 729-761, `write_script`; `ENABLE_HOOK_JUDGE` default)
- Test: `tests/test_scriptwriter.py`

**Interfaces:**
- Produces: `scriptwriter._max_words() -> int` = `round(SCRIPT_MAX_SECONDS * 2.2)` (33 s → 73) unless `SCRIPT_MAX_WORDS` is set; `_target_words()` = `round(SCRIPT_TARGET_SECONDS * 2.2)` (27 s → 59); `_drop_optional(body: str, optional: list[int], payoff: int | None, max_words: int) -> str`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_budget_is_set_in_seconds`: with no setting `_max_words() == 73` and `_target_words() == 59`; `SCRIPT_MAX_SECONDS=30` → 66; `SCRIPT_MAX_WORDS=80` still wins.
  - `test_optional_sentences_go_first_and_never_the_payoff`: an 85-word body with `optional=[2, 4]` and `payoff_index=4` loses sentence 2 only if that fits, then whole sentences from the end except 0 and 4.
  - `test_over_budget_without_optional_sentences_keeps_the_payoff`: the whole-sentence cut keeps sentence one and the payoff sentence.
  - `test_the_payoff_tag_follows_payoff_index`: `payoff_index=2` puts `[serious]` before sentence 2 even when it does not say "why it matters".
  - `test_a_script_without_the_new_fields_still_ships`: a reply with none of `payoff_index`, `optional`, `structure` goes through `write_script` as today.
  - `test_the_hook_judge_is_off_by_default`: `write_script` makes no punch-up call unless `ENABLE_HOOK_JUDGE=true`.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.5 and 9.1: the tighten rewrite is retired from the default path (`ENABLE_SCRIPT_TIGHTEN` default false); the order is optional sentences from the end, then `_truncate_to_words` keeping sentence one and the payoff. The payoff index, when present and in range, replaces `_WHY_IT_MATTERS_RE` for the delivery tag and for the "no why it matters" warning; without it the regex path is unchanged.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(scriptwriter): length in seconds, writer-marked cuts, the payoff by index; hook judge off"`.

### Task 5: Repair and every rewrite

**Files:**
- Modify: `src/scriptwriter.py` (`repair_script` 789-826, `_REPAIR_PROMPT` 770-787), `src/production.py` (repair block 217-233)
- Test: `tests/test_scriptwriter.py`, `tests/test_production.py`

**Interfaces:**
- Produces: `scriptwriter.repair_script(body: str, findings: list[str], topic: str | None = None, title: str | None = None) -> dict | None` returning `{"script_body": str, "title": str}`; production re-checks with the repaired title and stores both.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_repair_that_adds_a_fact_is_refused`: the repaired body carries a number neither the body, the findings nor the topic has → `None`.
  - `test_the_repair_may_fix_the_title`: a finding about the title → the returned title is the repaired one, held to Task 3's limits.
  - `test_the_recheck_sees_the_repaired_title` (in `tests/test_production.py`): `factcheck.verify` is called the second time with the repaired title.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.6: the repair prompt carries the title and returns both fields; the added-facts guard runs against the original body, the findings, the topic and the idea; production passes the repaired title and summary to the re-check and stores the repaired title (`db.backfill_script_title` is not enough: add `db.update_script_title`).

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(scriptwriter): the repair may fix the title, and adds no fact"`.

### Task 6: The fact-check thinks, counts forecasts, and logs grounding

**Files:**
- Modify: `src/llm.py` (`generate_grounded` 408-432, `generate_grounded_with_sources` 434-447 and the grounded workers: an optional `thinking` argument), `src/factcheck.py` (`_PROMPT` 62-111, the calls at 272/279), `src/scriptwriter.py` (`_generate_script_json` 370-410), `src/db.py` (`set_script_grounding`)
- Test: `tests/test_factcheck.py`, `tests/test_llm.py`, `tests/test_scriptwriter.py`

**Interfaces:**
- Produces: `llm.generate_grounded(..., thinking: str = "minimal")`, where `"default"` sends no thinking config; `write_script(...)["grounding"] = {"draft_citations": int, "gate_citations": int | None}`; `db.set_script_grounding(script_id: int, grounding: dict) -> None` (tolerant).

- [ ] **Step 1: Write the failing tests:**
  - `test_default_thinking_sends_no_thinking_config` (test_llm): with `thinking="default"` the config has no `thinking_config`.
  - `test_the_gate_asks_for_room_to_think` (test_factcheck): the gate's grounded call uses `thinking="default"` and `max_tokens >= 8192`.
  - `test_the_gate_counts_forecasts_about_india`: `factcheck._PROMPT` says a forecast or consequence for India counts as a claim that a source must state or that follows directly from sourced facts.
  - `test_the_draft_reports_its_citations` (test_scriptwriter): a grounded draft returned with 3 citations → `grounding["draft_citations"] == 3` and Claude's note says the draft searched; 0 citations → the note says its search could not be confirmed.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.7. The draft moves to `generate_grounded_with_sources` so its citations can be counted; production stores the grounding on the script row next to the verdict.

- [ ] **Step 4: Run the tests.** Expected: all pass, `tests/test_factcheck.py` whole.

- [ ] **Step 5: Commit.** `git commit -m "feat(factcheck): default thinking, forecasts about India as claims, grounding logged"`.

### Task 7: Description, hashtags, tags, category

**Files:**
- Modify: `src/scriptwriter.py` (`_publishable_sources` 664-683, `_ensure_sources` 686-701, `_disclosure_line` 704-707, `_ensure_shorts` 763), `src/production.py` (`_DEFAULT_FOOTER` 116-121, `_CORE_CHANNEL_TAGS` 145-149, `_build_metadata` 152-169), `src/publish_youtube.py` (`_build_body` 116-125)
- Test: `tests/test_scriptwriter.py`, `tests/test_production.py`, `tests/test_publish_youtube.py`

**Interfaces:**
- Produces: `production._hashtag_line(writer_hashtags: list[str]) -> str` (at most 3: up to 2 from the writer, then `#ButItMatters`); `metadata["category_id"]` from the idea's `niche` (`science`, `space`, `tech` → `"28"`, else `"25"`).

- [ ] **Step 1: Write the failing tests:**
  - `test_sources_are_publisher_names_with_their_links`: two publisher links and one Google News link → lines `"<Publisher>: <url>"` for the publishers only, the name from the host (`thehindu.com` → "The Hindu" when known, else the host).
  - `test_sources_keep_one_link_when_only_aggregators_exist`: only Google News links → one kept.
  - `test_the_disclosure_line_follows_the_visual_source`: `ai_video` → "AI-generated narration, video and music."; `ai` → the images line; `photos`/`video` → today's stock line.
  - `test_hashtags_are_three_at_most_on_the_last_line`: writer `["#ISRO", "#Shorts", "#viral", "#Gaganyaan", "#Space"]` → the description ends with `#ISRO #Gaganyaan #ButItMatters`, and none of them is in `tags`.
  - `test_tags_are_six_from_the_writer_plus_the_brand`: eight writer tags → the first six plus `But It Matters`; no other channel tag.
  - `test_the_footer_makes_no_every_day_claim`: `_DEFAULT_FOOTER` has no "every day" and no hashtags.
  - `test_the_category_follows_the_story`: niche `tech` → `"28"`; `india-politics` → `"25"`.
  - `test_publish_no_longer_adds_shorts`: `_build_body` leaves a description without `#Shorts` as it is.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from design 9.9: generic hashtags dropped (`shorts`, `youtubeshorts`, `viral`, `trending`, `fyp`, `foryou`, `explore`, `news`, `breaking`, `breakingnews`, `newsshorts`), and anything not letters, digits or underscores; `_ensure_shorts` and publish's `#Shorts` step removed; the footer is one line, `But It Matters: what happened, and why it matters. Subscribe @butitmatters`; `DESCRIPTION_FOOTER` still overrides it.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(packaging): a readable description, three hashtags, six tags, the right category"`.

### Task 8: The SQL, the docs, the full suite, the final review

- [ ] **Step 1: Add to the docs/03 SQL:** `alter table scripts add column if not exists structure text;` and `alter table scripts add column if not exists grounding jsonb;`.
- [ ] **Step 2: `.env.example`:** `SCRIPT_TARGET_SECONDS`, `SCRIPT_MAX_SECONDS`, the new `ENABLE_HOOK_JUDGE` and `ENABLE_SCRIPT_TIGHTEN` defaults.
- [ ] **Step 3: Full suite twice** (normally, and with `.env` blanked). Expected: all pass (bar the known `NICHE` artifact under blanking).
- [ ] **Step 4: STATUS.md, CHANGELOG.md, docs/05** (the script voice, structures, title), commit `docs(status): stage 1b, script and packaging`.
- [ ] **Step 5: The final whole-branch review of stage 1 (1a and 1b),** then the fix pass, then ask the operator before pushing.
