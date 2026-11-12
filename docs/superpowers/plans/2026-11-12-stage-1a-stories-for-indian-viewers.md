# Stage 1a: Stories for Indian Viewers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ideas are chosen for Indian viewers: a deeper story pool with ages and India-stake searches, two free demand signals, the India rubric in both ideation prompts, the category stored and the topic mix enforced in code, de-duplication before research, and the India selection rules.

**Architecture:** `src/news.py` grows the pool; a new `src/demand.py` reads Wikipedia's India list and comparable channels' upload feeds; `src/ideation_fallback.py` carries the rubric, the demand lines, the stored category, the mix and the earlier de-duplication. Stage 1 of the design is split: this is 1a (design Part C); 1b (Part D, script and packaging) follows on the same branch.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), pytest, requests, stdlib XML, Google News RSS, the Wikimedia REST API, YouTube channel RSS feeds.

**Spec:** [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](../specs/2026-11-10-ai-video-reels-design.md), section 8 (all of it) and section 13 (the `ideas` columns).

## Global Constraints

- No new Python dependency.
- Every new fetch is best-effort: a feed, an API or a parse failing costs that signal, never ideation (rule 11).
- Unit tests never reach the network: feeds and APIs are tested on saved or hand-built responses.
- The ideas insert is the run's backbone: a write naming a new column (`ideas.demand`, `ideas.rank_score`) retries without it when the column is missing (the Stage 0 pattern, `db._missing_schema`).
- Wikimedia is called with a generic User-Agent and no contact details (privacy), at most about 8 requests a run.
- Conventional commits, no AI attribution; full suite green before each commit.

## Review Focus

1. **Every demand source down at once** (Wikimedia 5xx, a channel feed 404, no network): ideation runs exactly as today with no demand lines. Test: Task 2, `test_demand_lines_survive_every_source_failing`.
2. **The mix cannot be met** (all candidates are `india-politics`): the digest still gets ideas, best first, rather than none. Test: Task 4, `test_the_mix_never_empties_a_digest`.
3. **A category the picker invents** ("Geopolitics"): stored as a known category, never a free string. Test: Task 3, `test_an_unknown_category_is_mapped_to_a_known_one`.
4. **A story the de-duplication would wrongly drop** (shares only "vs" or template words with an old one): kept. Test: Task 5, `test_vs_and_template_words_do_not_make_a_repeat`.
5. **The new `ideas` columns missing** when this ships: ideas are still inserted. Test: Task 3, `test_ideas_insert_retries_without_the_new_columns`.

---

### Task 1: A deeper pool, with ages and India-stake searches

**Files:**
- Modify: `src/news.py` (`fetch_stories`, `_parse_stories`; new `search_india_stakes`, `_is_game_help`)
- Modify: `src/ideation_fallback.py:745` (`NEWS_POOL_SIZE` default)
- Test: `tests/test_news.py`

**Interfaces:**
- Produces: stories gain `age_hours: float | None` (from `pubDate`); `news.search_india_stakes(per_query: int = 3) -> list[dict]` (stories tagged `"via": "india-search"`, de-duplicated by URL); `news._is_game_help(title: str) -> bool`.

- [ ] **Step 1: Write the failing tests:**
  - `test_game_help_items_are_dropped`: `_is_game_help("Quordle hints and answers for November 12")` and `_is_game_help("NYT Connections hints today")` are true; `_is_game_help("India's rail connections to Nepal to triple")` is false; `fetch_stories` on a fake feed containing one game item returns the others only.
  - `test_each_story_carries_its_age`: a `pubDate` 5 hours before a fixed "now" gives `age_hours == 5.0` (±0.01); a missing or unparsable `pubDate` gives `None`.
  - `test_india_stake_searches_use_the_configured_queries`: `NEWS_INDIA_QUERIES="Indian students,UPI"` → `search_stories` called with each query and window `2d`; results de-duplicated by URL and tagged `via == "india-search"`.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_news.py -q -p no:cacheprovider`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** Game help: a title with a game word (wordle, quordle, connections, strands, crossword) and a help word (hint, hints, answer, answers, clue, clues), or the phrases "hints and answers" / "answers today". Age: `email.utils.parsedate_to_datetime` against `datetime.now(timezone.utc)`. Default queries (spec 8.2): "Indian-origin", "Indian students", "for Indian users", "India vs China", "price hike India", "new rule India". `search_stories` gains an optional `window` argument (default the existing `NEWS_SEARCH_WINDOW`). In ideation, `NEWS_POOL_SIZE` defaults to `"60"`, and the pool is the feed stories followed by the India-stake stories, de-duplicated by URL.

- [ ] **Step 4: Run the tests.** Run: `.venv\Scripts\python.exe -m pytest tests/test_news.py tests/test_ideation_fallback.py -q -p no:cacheprovider`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(news): a 60-story pool with ages and India-stake searches; puzzle items dropped"`.

### Task 2: Demand signals (`src/demand.py`)

**Files:**
- Create: `src/demand.py`
- Test: `tests/test_demand.py`

**Interfaces:**
- Produces:
  - `demand.wikipedia_india_spikes(days: int = 8, top: int = 15, min_views: int = 5000) -> list[dict]` → `[{"title": str, "views": int, "ratio": float}]`, best ratio first.
  - `demand.channel_spikes(channel_ids: list[str] | None = None, max_age_hours: float = 72, min_ratio: float = 2.0) -> list[dict]` → `[{"channel": str, "title": str, "views": int, "ratio": float}]`.
  - `demand.demand_lines() -> list[str]`: both signals as short prompt lines; `[]` when neither works. Never raises.

- [ ] **Step 1: Write the failing tests** on hand-built responses (a fake `requests.get` keyed by URL):
  - `test_wikipedia_spikes_rank_by_views_over_the_prior_week`: an article at 50,000 views yesterday with a prior-week median of 5,000 ranks above one at 80,000 every day (ratio 10 vs 1); `Main_Page`, `Special:` and `-` pages are dropped; a day missing from the API counts as 0 views, not an error; the 8 requested URLs are the per-country endpoint `top-per-country/IN/all-access/YYYY/MM/DD` for the 8 days ending yesterday.
  - `test_channel_spikes_compare_each_short_with_its_channel`: a feed of 3 Shorts at 100, 120 and 900 views per hour gives one spike (the 900 one, ratio about 7.5 over the channel's median); a non-Shorts entry and one older than 72 hours are ignored.
  - `test_demand_lines_survive_every_source_failing`: every request raises → `demand_lines() == []`.
  - `test_wikimedia_requests_carry_no_contact_details`: the User-Agent has no "@" and no URL.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_demand.py -q -p no:cacheprovider`. Expected: FAIL, no module `src.demand`.

- [ ] **Step 3: Implement.** Wikimedia's per-country list returns `items[0].articles[]` with `article` and `views_ceil`; verify the field names once with a live fetch while implementing (free, about 8 requests) and code to what comes back. Channel feeds: `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`; each `entry` has `title`, `link` (a Short's link contains `/shorts/`), `published` and `media:group/media:community/media:statistics@views`; a Short's pace is views over hours since publishing, its channel's norm the median pace of that feed's Shorts. `DEMAND_CHANNELS` (comma list) defaults to the twelve channels the India research sampled: `UCGdPm5Aq081vVD7ih9jZf6Q, UCglXlpWjIi95auM3umWWLdw, UCzwCEE_PchiBULMnAJqhGVg, UCwAdQUuPT6laN-AQR17fe1g, UCw5hEVOTfz_AfzsNFWyNlNg, UCsDTy8jvHcwMvSZf_JGi-FA, UCmTM_hPCeckqN3cPWtYZZcg, UCXUJJNoP1QupwsYIWFXmsZg, UCVOTBwF0vnSxMRIbfSE_K_g, UCRzYN32xtBf3Yxsx5BvJWJw, UCOhHO2ICt0ti9KAh-QHvttQ, UCKZozRVHRYsYHGEyNKuhhdA`. Lines read like `India on Wikipedia yesterday: "Sunita Williams", 526,400 views, 12x its usual` and `Indian Shorts now: "<title>" (<channel>), 7x that channel's usual pace`; at most 8 of each.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(demand): Wikipedia's India list and comparable channels' Shorts as demand signals"`.

### Task 3: The rubric, the demand lines and the stored category

**Files:**
- Modify: `src/ideation_fallback.py` (`_STAGE1_PROMPT` 666-694, `_PROMPT` 79-142, `_select_stories` 697-729, `_produce_ideas` 732-818, `_to_rows` 39-41, `_ROW_KEYS` 36)
- Modify: `src/db.py` (`insert_ideas` 96-100)
- Test: `tests/test_ideation_fallback.py`, `tests/test_db_records.py`

**Interfaces:**
- Consumes: `demand.demand_lines()` (Task 2); the stories' `age_hours` (Task 1).
- Produces: `ideation_fallback.CATEGORIES = ("india-politics", "india", "money", "world", "science", "space", "tech", "health", "sport", "culture")`; `ideation_fallback._category(raw: str) -> str` (a known category; unknown values map by keyword, else `"world"`); each idea's `niche` holds its category; rows carry `rank_score` (the `share_score` that ordered it) and `demand` (the demand lines that the picker said it matched, a list).

- [ ] **Step 1: Write the failing tests:**
  - `test_both_prompts_name_the_viewer_and_the_rubric`: both prompt templates contain "Indians aged about 18-34", "a named Indian or Indian-origin person" and "routine launches"; neither contains "at least half".
  - `test_the_winners_block_is_off_until_winners_since`: without `WINNERS_SINCE` the prompt passed to the picker holds no published titles and no "LOW PERFORMERS" line (`db.top_performing_titles` is not called).
  - `test_headlines_show_their_age`: a story with `age_hours == 5` appears as `- (5h) <title>` in the picker's prompt.
  - `test_an_unknown_category_is_mapped_to_a_known_one`: `_category("Geopolitics") == "world"`, `_category("Science & Space") == "space"`, `_category("India politics") == "india-politics"`, `_category("") == "world"`.
  - `test_each_idea_stores_its_category_and_rank`: `_to_rows` on an idea with `niche="tech"`, `share_score=0.8` gives `niche == "tech"` and `rank_score == 0.8`.
  - `test_ideas_insert_retries_without_the_new_columns` (in `tests/test_db_records.py`): a PGRST204 on the first insert → a second insert without `rank_score` and `demand` succeeds.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv\Scripts\python.exe -m pytest tests/test_ideation_fallback.py tests/test_db_records.py -q -p no:cacheprovider`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** Prompt text from spec 8.1 and 8.4, written in the prompts' existing style and without quotable example phrases: the viewer; closer to the viewer ranks higher (named Indian or Indian-origin person; personal stake in money, visas, safety, exams, jobs, prices; India beside another country; a dated event this week; the factual angle on what India is already watching; the unfamiliar term in the news, explained); lower (routine launches, macro policy, the Budget as a subject, GST, tariffs, institutional news, distant events with no Indian angle, abstract science); the old category spread line is replaced by the fixed category list; a `DEMAND SIGNALS` block with `demand.demand_lines()` ("a story that shows in two of the three signals ranks higher"); story ages ("over 48 hours old ranks lower unless it carries a new development"). The picker returns `category` from `CATEGORIES` and, per story, `demand` (the signal lines it matches). The winners block is built only when `WINNERS_SINCE` is set, from posts since that date and at least 72 hours old, with no avoid list (`db.top_performing_titles` gains an optional `since` argument). Stage 2's ideas take `niche` from their story's category through `_category`. `db.insert_ideas` retries without `rank_score` and `demand` on a missing-column error.

- [ ] **Step 4: Run the tests.** Expected: all pass, the existing ideation tests included.

- [ ] **Step 5: Commit.** `git commit -m "feat(ideation): pick for Indian viewers, with demand signals; store each idea's category"`.

### Task 4: The mix, enforced at the final pick

**Files:**
- Modify: `src/ideation_fallback.py` (`seed_ideas` 903-945, `generate_ideas` 843-855; new `_enforce_mix`)
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Consumes: `CATEGORIES`, the ideas' `niche` (Task 3); `scriptwriter.tone_for(idea: dict, body: str = "") -> str`.
- Produces: `ideation_fallback._enforce_mix(ranked: list[dict], n: int) -> list[dict]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_mix_caps_politics_categories_and_somber_stories`: ranked ideas `[india-politics, india-politics, tech, tech, tech, world]` (all calm), `n=4` → `[india-politics, tech, tech, world]`; two somber ideas in the top four → only the higher-ranked one kept.
  - `test_the_mix_never_empties_a_digest`: six `india-politics` ideas, `n=3` → three ideas, best first (the caps relax rather than empty the digest).
  - `test_seed_ideas_applies_the_mix`: `seed_ideas` inserts what `_enforce_mix` returns.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL, no `_enforce_mix`.

- [ ] **Step 3: Implement** the caps from spec 8.4: at most one `india-politics`, at most two of any one category, at most one somber story. Fill in rank order; if the caps leave fewer than `n`, fill the rest from the skipped ideas in rank order, so caps shape a digest and never empty it.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(ideation): enforce the topic mix in code at the final pick"`.

### Task 5: De-duplication before research; follow-ups; expired, not banned

**Files:**
- Modify: `src/ideation_fallback.py` (`_STOPWORDS` 50-54, `_produce_ideas`, `_repeats_recent_story` 880-900)
- Modify: `src/db.py` (`IDEA_STATUSES` 33, `recent_ideas` 176-185)
- Modify: `src/production.py` (`_pass_untapped` 386-400)
- Test: `tests/test_ideation_fallback.py`, `tests/test_production.py`

**Interfaces:**
- Produces: picked stories that repeat a recent idea are dropped before `_research_stories` runs; a story the picker marks `"followup": true` repeats an old one only when it shares no source; untapped ideas end `expired`; `db.recent_ideas` leaves `expired` ideas out.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_repeat_is_dropped_before_any_research`: `_select_stories` returns two stories, one repeating a recent idea → `_research_stories` is called with one story.
  - `test_vs_and_template_words_do_not_make_a_repeat`: "SpaceX vs Blue Origin: the race heats up" is not a repeat of "Korea vs Japan: the race heats up in Seoul".
  - `test_a_followup_with_new_sources_is_allowed`: same distinctive words, `followup` true, no shared source → not a repeat; with a shared source → a repeat.
  - `test_untapped_ideas_expire` (in `tests/test_production.py`): `_pass_untapped` sets `expired` from `pending`.
  - `test_expired_ideas_are_not_recent`: `db.recent_ideas` filters `status != expired`.

- [ ] **Step 2: Run them to see them fail.** Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** Add `vs`, `v`, `versus` and the hook template's stock words (`race`, `heats`, `showdown`, `clash`, `battle`, `shock`, `shocking`) to `_STOPWORDS`. Before research, compare each picked story's one-line description (as `{"title": story, "hook": ""}`) with `_recent_ideas()`. Add `expired` to `IDEA_STATUSES` and filter it out in `recent_ideas`. `_pass_untapped` writes `expired`.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(ideation): de-duplicate before research; allow sourced follow-ups; expire untapped ideas"`.

### Task 6: Rules that bind selection in India

**Files:**
- Modify: `src/ideation_fallback.py` (`_PROMPT` framing rules; `_validate_and_clean` 606-694 or the pick)
- Test: `tests/test_ideation_fallback.py`

**Interfaces:**
- Produces: `ideation_fallback._in_election_silence(idea: dict, today: date | None = None) -> bool`, reading `ELECTION_SILENCE` as `State:YYYY-MM-DD,...`.

- [ ] **Step 1: Write the failing tests:**
  - `test_election_matter_is_dropped_inside_the_silence`: `ELECTION_SILENCE="Bihar:2026-11-14"`, today 2026-11-13, an idea "Bihar election: what the exit polls missed" → dropped; the same on 2026-11-16 → kept; a Bihar flood story → kept (no election word).
  - `test_the_prompt_carries_the_india_rules`: `_PROMPT` asks that an allegation name the court record or official order it rests on, and that a live conflict be explained through terms and mechanisms only.

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL.

- [ ] **Step 3: Implement** from spec 8.7: the silence window is the 48 hours before the polling date's end (the date and the day before); election words are election, poll, polls, polling, vote, voting, campaign, candidate, exit poll.

- [ ] **Step 4: Run the tests.** Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -m "feat(ideation): India's selection rules: named records, conflict terms, election silence"`.

### Task 7: The SQL, the docs, the full suite

**Files:**
- Modify: `docs/03-setup-guide.md` (the Stage 0 SQL block), `.env.example`, `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Add to the docs/03 SQL:** `alter table ideas add column if not exists demand jsonb;` and `alter table ideas add column if not exists rank_score numeric;`, and note that `ideas.status` gains `expired` and `ideas.niche` now holds the category.
- [ ] **Step 2: Add to `.env.example`:** `NEWS_INDIA_QUERIES`, `DEMAND_CHANNELS`, `ELECTION_SILENCE`, `WINNERS_SINCE`, and the new `NEWS_POOL_SIZE` default, each with one line on its meaning.
- [ ] **Step 3: Run the full suite twice:** normally, and with every `.env` key blanked (as CI sees it). Expected: all pass both times (bar `test_get_falls_back_to_default`, which only fails under blanking).
- [ ] **Step 4: Update STATUS.md and CHANGELOG.md, commit.** `git commit -m "docs(status): stage 1a, stories for Indian viewers"`.
