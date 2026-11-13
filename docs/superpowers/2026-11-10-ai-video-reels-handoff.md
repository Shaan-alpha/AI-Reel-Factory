# Handoff: AI-video reels in Hinglish, and the reach audit

**Written:** 2026-11-10. **Update this file whenever the state below changes.**
**Read this first** if you are picking the work up in a new session. Nothing here has been built:
no file under `src/`, `tests/` or `.github/` has changed, and nothing is committed.

**Resumed on 2026-11-12** ("read the handoff, invoke skills and continue"). Progress that day:

- The audit's 88 findings were checked against the code and data by four second reviewers; their
  write-ups are in `research_notes/Channel audit 2026-11-10/verification/` (one file per pair of
  lenses). None was wrong outright; many details changed.
- The YouTube Analytics API was enabled on the OAuth client's Google Cloud project
  (`composed-maxim-498517-f0`, free). Today's refresh token then read retention and country data
  with no new consent, so decision 6c-3 needs no operator action. Lifetime audience: 39% US, 5.2%
  India.
- The design is being rewritten in place (`docs/superpowers/specs/2026-11-10-ai-video-reels-design.md`);
  the first draft is archived as `research_notes/Design review 2026-11-10/first_draft_2026-11-10.md`.
- **The voice is decided:** the operator heard test 4's lines on today's model and on both Gemini 3.8
  TTS models and chose today's (`gemini-3.1-flash-tts-preview`, Charon, test 4's prompt): "voice a is
  better than others". From 2026-11-17 it runs on Vertex. The STATUS item "ear-test 3.8 before
  2026-11-17" is closed by this.

- The voice change shipped (PR #16, merged): Vertex voices the channel; CI's `verify-tts` passed.
- The design is complete; a fresh builder read it and its two questions were answered (the operator
  chose up to **$1.10 a reel**, all video; the judging rule was corrected).
- The disclosure flag does not come back from the API on the channel's uploads (design 9.9, 18.9).
- **The Stage 0 plan is written:** `docs/superpowers/plans/2026-11-12-stage-0-safety-and-measuring.md`.
  One plan per stage, each written just before it is built.

- **Stage 0 is merged** (PR #17, 2026-11-12; CI 786 pass, 5 skipped), including the fixes from a
  fresh final review; the bot is redeployed. The operator still has to run its SQL (end of docs/03 §4). Calls made while building it, each
  with its cost if wrong (none): two old tests were updated where the behaviour moved (an "ok ..."
  fixture now opens on a subject; `make_on_demand` no longer re-sends "Published"); an India share
  of 0 for fully withheld countries was treated as a real defect, not polish; two stale docs lines
  were fixed under rule 1. **Deferred minors:** an idempotent rerun re-sends "✅ Published"; a video
  whose Analytics query always fails is retried every run; the opening rewrite's 20-word limit is
  asked for, not enforced; `reel_attempts.spend_usd` waits for stage 3, and a job kill leaves a
  NULL outcome (read it as "killed").

- **Stage 1a (stories for Indian viewers) is built** on `feat/stage-1-stories-script` (7 tasks, 811
  pass); **stage 1b (script and packaging) is built** on the same branch (8 tasks, 852 pass; plan
  `docs/superpowers/plans/2026-11-12-stage-1b-script-and-packaging.md`). The calls made while
  building 1b are listed in STATUS.md's 2026-11-12 log and the ledger. Each plan's ledger is under
  `.superpowers/sdd/<plan name>/progress.md` (git-ignored).
- **The final review of stage 1 is done** (8 important findings fixed test-first, 870 pass; see
  STATUS.md). The operator asked for push and merge once the fixes were in.
  **Deferred minors from that review:**
  - `db.expire_stale_pending_ideas` still writes `passed`, so ideas aged out after 24 h count in
    the 10-day story window (design 8.5 wants them `expired`);
  - an aggregator-only description keeps one Google News link, not two;
  - `_category` matches substrings ("Transport" maps to sport);
  - the Wikipedia signal skips a run when yesterday's list is not yet published (use the newest
    day);
  - with no network, the demand fetches can add about 6.7 minutes of timeouts;
  - the idea's stored `demand` is the model's copy, unchecked against the real lines;
  - a title cut can end on a preposition;
  - `_pass_untapped` and its log still say "passed";
  - a very long line in `news.py`;
  - 9.1's warning for six or more words copied from a prompt example is not built;
  - "Today's Wordle solution" passes the puzzle filter.

- **Stage 1 is merged** (PR #18). **Stage 2 (Hinglish) is built** on `feat/stage-2-hinglish`, behind
  `NARRATION_LANGUAGE=hinglish` (9 tasks; plan
  `docs/superpowers/plans/2026-11-12-stage-2-hinglish.md`; live checks in STATUS.md). Deferred
  from the design: the Gemini 3.8 TTS request shape (7.5), since the operator kept 3.1, which
  Vertex serves.

- **Stage 2's final review is done** (5 important findings and 5 re-graded minors fixed
  test-first, 963 pass). **Deferred minors from it:**
  - the Claude ledger settles from the top-level usage, not `usage.iterations`, so a rescued call
    is under-counted, and the Opus 5 and 4.8 prices are missing, so a rescue is over-counted;
  - a Hinglish call that times out keeps its $0.41 worst case reserved;
  - missing Hindi number words: 31-99, लाखों, करोड़ों, हज़ारों, सैकड़ों, डेढ़, ढाई and आधा;
  - दो as the verb "give" fails as a number word;
  - "-5%" loses its sign;
  - a 0.5 s sentence with 4 parts can yield an inverted block;
  - the 36 s code band and the voice's 1.30x band disagree;
  - English text with any Devanagari takes the Hindi route;
  - the Hinglish step has no deadline of its own.

- **Stage 2 is merged** (PR #19, 2026-11-13; CI 963 pass).
- **Stage 3a is built** on `feat/stage-3-ai-video` (4 tasks; plan
  `docs/superpowers/plans/2026-11-13-stage-3a-higgsfield-client-and-ledger.md`). Nothing is bought
  yet; no reel calls Higgsfield. It holds:
  - the client `src/higgsfield.py`: the key only to the API host, every message redacted, each
    answer sorted into funds, auth, refused, busy or unavailable;
  - the `ai_video_jobs` ledger in `src/db.py` (its SQL at the end of docs/03 §4);
  - the sweep and the run's spend line in `src/ai_video.py`, called at the start and end of both
    entry points;
  - a conftest guard that keeps every test off the live API;
  - `tools/verify_higgsfield.py`, the one live check, at most $0.18 and not yet run.
  `HF_API_SECRET` is gone from the local `.env` (it was empty).

- **Stage 3a's final review is done** (7 findings fixed test-first; details and the deferred minors
  in STATUS.md's 2026-11-13 log). The run's closing sweep and spend line are now one call,
  `ai_video.close_run(since)`.

- **Stage 3a is merged** (PR #20). With the operator's go-ahead the `HF_API_KEY` repository secret
  is set and the live check ran: `/estimate` now answers Kling with a per-second rate ($0.1575 a
  clip; the client was fixed), and a repeated idempotency key returns the same job (one charge).
- **Stage 3b is built** on `feat/stage-3b-ai-video-shots` (8 tasks; plan
  `docs/superpowers/plans/2026-11-13-stage-3b-ai-video-shots.md`), behind `VISUAL_SOURCE=ai_video`:
  the cut list, 24 fps rendering, the shot planner, the stills, buying and settling the clips with
  stop latches, and the production wiring. Its seams for stage 4 are `ai_video._check_still` and
  `ai_video._check_clip`.

**Next:** stage 3b's final review and fix pass, then the operator's go-ahead for push and merge
and for one test render (about $0.95, no upload). Then stage 4 (picture and sound: the gates, the
number card, the banner hold, the music level, the vignette and stings) and the relaunch (design
section 14).

## 1. What the operator wants

Decisions the operator made on 2026-11-10, in order. Treat them as fixed.

1. **Format:** every reel is a narrated AI-video reel like "test 3": stills from the pipeline's
   own FLUX, each animated into a 5-second clip by Kling 2.5 Turbo on Higgsfield, with the
   pipeline's normal edit. The AI-presenter (UGC, lip-sync) idea was tried and dropped.
2. **Money:** Higgsfield is an approved billed service. About 20 videos and $60-80 a month, up
   to about $1 per reel. **No monthly spend cap and no video-count cap in code** ("ill stop
   myself"). Costs are logged.
3. **Voice:** male and informative. Test 3 used Gemini TTS `Charon`.
4. **Language:** narration in **Hinglish**, subtitles in **English** ("loved it", after test 4).
5. **Audience:** "content for indian basically". One audience: Indian viewers.
6. **Topics:** trendier, currently impactful stories from anywhere; not necessarily political;
   technology and science welcome.
7. **No watermark and no on-screen "AI-generated" label.** The AI disclosure is one line in the
   description. The existing corner logo and the music beds stay.
8. **Reach:** refine the prompts, scripts and metadata from current research, and do a full
   audit of the pipeline and the content prompts for watchability, reach and views.
9. **Tools:** installing free tools is fine where they improve the content (Tesseract was named).
10. **Working style:** go on research and judgement; do not ask for manual checks (the operator
    declined to fetch YouTube Studio figures). Still confirm before committing, pushing,
    changing repository secrets or variables, deploying, or spending beyond the above.

## 2. Where everything is

| What | Where |
|---|---|
| The design (first draft; **predates decisions 4, 5, 7, 8, 9** and the review) | `docs/superpowers/specs/2026-11-10-ai-video-reels-design.md` |
| General reach research and prompt-craft research, with sources | `docs/superpowers/specs/2026-11-10-ai-video-reels-research.md` |
| Design review: 51 findings, 21 confirmed by a sceptic | `research_notes/Design review 2026-11-10/design_review.md` (and `.json`) |
| **India research report** (the five strands in one document, with a 12-row table of changes and their evidence grades) | `reports/Hinglish Shorts reach in India.md` |
| India research notes behind it (5 strands) | `research_notes/Hinglish Shorts reach in India/` |
| The channel's data export (87 live Shorts with views, scripts, titles; all ideas) | `research_notes/Channel audit 2026-11-10/reels.json`, `ideas.json` |
| **Audit: all 88 findings in one file** | `research_notes/Channel audit 2026-11-10/FINDINGS.md` (raw: `audit_results.json`) |
| Audit reports (8 lenses, with evidence, tables and proposed prompt text in full) | `research_notes/Channel audit 2026-11-10/reports/` |
| Higgsfield API docs extracts, prices, OpenAPI | `research_notes/Higgsfield API notes/` |
| Throwaway test scripts (`spike.py` to `spike4.py`, `voice2.py`), their logs, test 3's four paid clips and stills, both test narrations | `research_notes/Spikes 2026-11-10/` |
| The test videos the operator watched | `test-videos/` (tests 1-4, face and voice options) |
| Raw pulls (YouTube channel feeds, Wikipedia top lists, Google's safe-zone overlay) | `research_notes/Raw pulls 2026-11-10/` |

`research_notes/`, `reports/` and `test-videos/` are kept out of git by `.git/info/exclude` on this
machine. The two files under `docs/superpowers/specs/` and this handoff are untracked and meant
to be committed with the build, when the operator asks.

The session's scratch area, if it still exists, holds the originals:
`C:\Users\shaan\AppData\Local\Temp\claude\24a060a1469cf26e\cdb9aede-9167-4250-9dd5-c36fee3ce03e\scratchpad`
(`audit/reports/` there is where the auditors write; copy anything newer into `research_notes/`).

## 3. What was measured

- **Kling 2.5 Turbo Standard image-to-video** (`kling-video/v2.5-turbo/standard/image-to-video`):
  $0.179 per 5 s clip on this account, 724x1268, 24 fps, 121 frames, no audio, about 95-105 s
  for four jobs at once. Test 3: four clips, $0.72, 26.7 s reel.
- **Higgsfield API:** `Authorization: Key <HF_API_KEY>` (the console key is already `id:secret`);
  free `POST /estimate/{endpoint}` gives the real price (the pricing page's discounts do not
  apply); submit, poll `GET /requests/{id}/status`, result at `video.url`; uploads through
  `POST /files/generate-upload-url`. The key is in the local `.env` as `HF_API_KEY`; it is not
  yet a GitHub Actions secret. About $5.78 of balance was used by the four tests.
- **Hinglish narration (test 4):** mixed-script text (Devanagari for Hindi words, Latin for
  English words) through the pipeline's Gemini TTS with `Charon` read correctly; 27.0 s. English
  subtitle lines were timed per sentence from the pauses in the audio, in plain white, with no
  word-by-word highlight.
- **The channel today:** 87 live Shorts since June 2026, about 16,000 views in total, median 44
  views, best 1,256, 24 under 20 views; all in YouTube category 25. A 2026 study of new Shorts
  channels found a median of about 1,300 views at 30 days.

## 4. State of each workstream

| Workstream | State on 2026-11-10 |
|---|---|
| Format tests 1-4 | Done. The operator chose test 3's format with test 4's language. |
| Design, first draft | Written. Needs a rewrite (section 5). |
| Design review | Done: 21 confirmed issues to fix in the design (section 6). |
| General reach and prompt research | Done and saved. |
| India research | **Done.** Five notes and the report written from them (`reports/Hinglish Shorts reach in India.md`, about 6,700 words). Section 6b summarises the findings. |
| Full audit (8 lenses: data, ideation, script, voice-audio, visuals-edit, packaging, throughput, prompts) | **Done: 88 findings.** All eight reports are in `research_notes/Channel audit 2026-11-10/reports/`; every finding is listed in `FINDINGS.md` beside them (raw: `audit_results.json`). Section 6a summarises the themes. **Not yet independently verified.** |
| Build plan | Not started. |
| Build | Not started. |

Background research and audit tasks belong to the session that started them. If that session
ended, check which of the files above exist; rerun only what is missing.

## 5. What the rewritten design must contain

Beyond the first draft:

- **Hinglish narration, English subtitles.** The English script stays the fact-checked source of
  truth. After the fact-check, one model call renders it into spoken Hinglish, one sentence per
  English sentence, Hindi words in Devanagari and English words in Latin script, numerals kept
  as digits. Code checks that every number and name survives; a second, independent call checks
  that each sentence means the same. On failure, retry once, then narrate that reel in English
  with the existing word-by-word captions and tell the operator. Subtitles: English phrases per
  sentence, timed from the narration's pauses (a proportional estimate snapped to the nearest
  pause), plain white, no orphan last word. Only engines that can read Devanagari voice the
  Hinglish text. The upload declares Hindi audio with an English title and description. Store
  what was actually spoken (a `spoken_body` column on `scripts`).
- **Audience India.** Topics chosen and framed for Indian viewers. Research so far: what travels
  is a named Indian person or a direct stake for Indians, tied to a dated event; money works as
  personal utility; routine launches and the Budget as a subject are weak. Free demand signals
  worth adding: Wikipedia's daily most-viewed list for India, and the public upload feeds of top
  Hinglish channels. Google's India trends feed holds only about 90 minutes of history.
- **No on-screen AI label,** with an on-screen label available as a switch that is off. India's
  rules in force (amendment effective 2026-02-20) put labelling on platforms; the uploader
  declares. A March 2026 draft proposes a label for the whole video and had not been adopted as
  far as the research found. The declaration (`containsSyntheticMedia`) is therefore the part
  that must work, and it has never been confirmed in YouTube Studio.
- **Revenue reality:** about $0.008 per 1,000 Shorts views for Indian audiences (one source
  with a stated basis). The Higgsfield spend buys reach, not ad income.
- **The audit's findings,** once verified.
- **Optional tools** where the audit supports them, for example a text check on AI stills and clips.

## 6. The 21 confirmed review findings, in one line each

Full text, evidence and the smallest fix for each are in the design review file.

Money and reliability:
1. Reserve the ledger row before the paid submit (as `claude_spend` does); `request_id` nullable.
2. Confirm by one live call what a repeated `Idempotency-Key` returns; until then never retry a submit that may have been delivered.
3. Mark a job `canceled` only when the cancel is confirmed; sweep `submitted` and `late` rows at the start of every run.
4. A reel whose deadline passes with no clip stops all buying for the rest of the run.
5. The time limit covers the whole Higgsfield phase, not just polling; give visuals a latest-finish time; set `JOB_TIMEOUT_MINUTES` to the step's limit (85 and 55).
6. Report Higgsfield spend on failed reels and at the end of every run, with the month-to-date.

Fit with the code:
7. Visuals hands assembly exactly the planned number of clips, each at least the cut length: pace Ken Burns to the clip length, never drop a shot, slow each clip by its probed length.
8. The description's hashtag line is composed in `production._build_metadata` after the footer; hashtags no longer merge into the tags.

Compliance:
9. A code check rejects any shot prompt containing a name from the story; when the planner fails, nothing is bought.
10. One agreed monthly figure and the exact new wording for CLAUDE.md's cost target and rule 2.
11. Confirm the disclosure flag takes effect before AI video goes live.
12. Somber stories skip the structure rotation and the surprise hook.
13. The stock-photo fallback takes its search words from the keyword step, never from the still prompt.
14. More docs go stale than the draft listed: README.md, docs/02, docs/06, `templates/template-N-news-impact.md`, `routines/ideation.md`.

Content:
15. The true surprising fact is always sentence one; a structure is defined by what follows.
16. The hook judge is told the structure, may reword sentence one only, and its title must meet the title rules.
17. An "assumption" or "what happens next" beat must come from the sources, stated as a belief or a scheduled step.
18. The "why it matters" guard matches a literal phrase: keep a bridge phrase it matches or widen it with tests.
19. The somber detector flags ordinary science words (explosion, dead star, kill switch): narrow it to human harm.
20. The topic mix is enforced in code at the final pick, not only asked for in a prompt; suspend the "winning titles" block until new-format reels have data.
21. (Raised twice.) Late ledger rows are never settled without the sweep in item 3.

## 6a. What the audit found (themes; unverified)

Several auditors reached the same points independently. Numbers are from the channel's own
data unless marked otherwise. Check each against the report before building on it.

**A. Measure before judging.** Views arrive in a two-day burst and stop: 79% within 24 hours,
96% within 72. 57 of 87 Shorts ended under 100 views and none passed 1,256. The pipeline stores
one public view count a day, so nobody can tell whether viewers leave at frame 1, leave at
second 5, or are the wrong audience. Proposed: pull engaged views, average percentage viewed,
traffic source and country per Short (the YouTube Analytics API; needs
`tools/get_youtube_token.py` re-run for the `yt-analytics.readonly` scope), take view snapshots
at 1, 3, 6, 12, 24, 48 and 72 hours, and stamp each post with a format version. Twenty reels can
detect a threefold change about 75% of the time and a doubling only 31%, so fix the judging rule
first: of the first 20 new reels, 14 or more reaching 100 views at 72 hours means pick-up
improved, 4 or fewer means it got worse.

**B. Hinglish breaks English-only assumptions in at least six places.** The caption step forces
Whisper to English and aligns to the script, so it would burn invented English with no error.
Also affected: sentence splitting, the no-new-facts guard, the pace guard and word cap (they
count English words), the fallback voices (the Chirp, edge-tts and Kokoro voices as configured
cannot read Devanagari), and the upload's language (one setting serves title and audio).
Proposed: a two-text contract, each line carrying its English (fact-checked, shown as the
subtitle) and its Hinglish (spoken), with spoken-form rules for numbers, dates, names and the
Hindi full stop, and a check that the two say the same thing.

**C. The opening.** Scripts that open on a wind-up word ("So,", "Alright,", "Imagine") were
picked up (100+ views) 9 times in 41, against 21 in 46 for scripts that start on the subject;
the writer added the wind-up in 37 cases where the idea's hook was clean. Since late July,
titles of 7 words or fewer were picked up 15 times in 23 against 3 in 17 for longer ones. In
tests 3 and 4 the claim lands at about 7 seconds, after a date. One string serves as both the
YouTube title and the frame-1 banner, and is too long for the banner. The hook is first written
by the cheapest model call and then policed by a weaker model on a "shock" score.

**D. Story selection.** The headline pool cannot supply enough science, technology and space
stories; both selection prompts still describe the old channel; the "winning titles" block
steers toward Gulf conflict on noise; the scores carry no information; nothing measures
demand; a story's age is parsed and never used; de-duplication bans follow-ups for 10 days;
the operator can veto ideas but cannot point the pipeline at a story.

**E. A caution about the old data.** India-domestic stories took 22% of uploads and 3.4% of
views, and all seven Shorts over 900 views went up between 01:00 and 07:30 IST. The data cannot
say who watched or from where. The past audience may not be Indian, so these patterns may not
carry over to Hinglish reels for Indian viewers.

**F. Voice and audio.** The Developer-API TTS models end on 2026-11-17; Gemini 3.8 TTS takes a
different request and the tuning tools stop working that day. The planned style prompt asks
for a General American accent, wrong for Hinglish. The music bed measures 24-25 LU under the
voice, and the cut stings are one inaudible tick per reel. Narration starts with about 0.3 s of
silence.

**G. Picture and edit.** A fifth to a third of frames are duplicates (24 fps clips converted to
30 fps and slowed): render at 24 fps and never slow a clip. Pictures are dark and small: fix the
planner's framing rule, check exposure, drop the vignette. Cut on the clause with hard cuts.
English subtitles as clause blocks in spoken order. Automatic gates on stills, clips and the
finished reel (Tesseract for stray text; FFmpeg and numpy for black, frozen or dark frames).
One animated key number per reel. A seamless loop join. A shorter, larger banner.

**H. Packaging.** Hinglish audio would be declared as English. The disclosure flag has never
been verified, and 78 published descriptions say "stock visuals" over AI images. The sources
block is a wall of aggregator links. Category 25 is wrong for science and technology (fix it,
expect nothing). Since 2026-11-03 the API can set a thumbnail for a Short. Not worth building:
playlists, a pinned comment, interactive stickers.

**I. Throughput.** Runs are rare and small, and one in five makes nothing; the render chain
itself is fast. Nothing looks at a reel before it is public, and nine of 96 were later removed.
Attempts leave no record, so the funnel cannot be measured. A fact-check block on the hook
cannot be repaired.

**J. Prompts.** No prompt says who the viewer is. Example phrases in the prompts are being
copied into published scripts and descriptions. The "grounded draft" Claude is told to trust is
probably not grounded. Length is controlled by asking a model to count. A live bug: the
sentence splitter breaks on "U.S." and "...", so the opening guard failed on 2 of the last 9
published scripts.

## 6b. What the India research found

Five notes are in `research_notes/Hinglish Shorts reach in India/`; the report written from
them is `reports/Hinglish Shorts reach in India.md`. Much of this rests on one-day samples of
public channel pages, not on published studies; each note grades its own evidence.

**Audience and language.** YouTube's last India figure is over 650 million monthly logged-in
Shorts viewers (June 2025). No one publishes a Hinglish-versus-English comparison. On public
channel pages, Hindi sister channels of six news publishers have 1.7 to 6.6 times the
subscribers of the English ones, and in two same-brand pairs Hindi Shorts get 5 to 8 times the
median views (one counter-example). Shorts revenue for Indian audiences is about $0.008 per
1,000 views against $0.328 in the US (one source with a stated basis).

**What the leading channels do** (24 channels, 110 Shorts sampled):
- The five leaders by median views all put a person on camera. The best faceless channels sit
  a tier lower, at medians of 1.2 to 2.5 million views a Short.
- The median top Short is 60 seconds; only 9 of 110 are 30 seconds or shorter. Nothing shows
  that 25-35 seconds does better or worse.
- 82 of 110 titles are English in Latin script over Hindi narration.
- Only about 10 of the 48 best recent Shorts have running captions (Roman Hinglish or English,
  never Devanagari). Hindi audio with English subtitles is rare but has precedents.
- Speech starts within 0.1 s and runs about 3.5 words a second. Most Shorts end on the payoff line.
- What separates hits from a channel's median Shorts is the subject and the first line, not
  the format. Hits: dangers the viewer can picture, India-versus-China comparisons, school
  life, big money made concrete, this week's incident, everyday "why" physics. Median:
  institutional news, distant events, abstract science or history.
- Superlative or "first ever" openers were 23% of channels' most-viewed Shorts against 7% of
  their least-viewed; "kya aap jaante hain" appeared in none of the 94 most-viewed.
- High-median channels post 0.3 to 1.1 Shorts a day.

**Topic demand.** What travels is a named Indian person or a direct stake for Indians, tied to
a dated event (Sunita Williams's return: 526,400 Wikipedia views from India; a routine
satellite launch: 17,900). Money travels as personal utility. Weak: routine launches, the
Budget as a subject, GST, tariffs. Signals tested live: Google's India trends feed works but
holds only the 10 newest trends, about 90 minutes; Wikipedia's per-country daily top list works
(one day late); YouTube channel upload feeds work without a key and show view counts; YouTube
search suggestions work for angle and title wording; `chart=mostPopular` no longer returns the
old Trending list.

**Rules in India for AI-made content** (information, not legal advice):
- The amendment in force since 2026-02-20 puts labelling duties on platforms; the uploader's
  part is to declare AI use. No burned-in label is required of the uploader, and the draft's
  "10% of the screen" label was dropped.
- A second draft (March and April 2026) proposes a label shown for the whole video. The
  research found no sign it has been adopted but could not search the Gazette directly.
- Photoreal AI depictions of real events or people presented as real are prohibited, not
  label-able. A Delhi High Court order of 2026-11-06 took down AI videos of a politician
  although one carried an "AI GENERATED" watermark.
- The rules for "publishers of news and current affairs" probably reach a systematic,
  monetised news channel; this is unsettled, and in practice the government blocks channels.
- No Hindi or Hinglish explainer channel was found reported as demonetised or terminated in
  2025-26. Only 2 of 110 sampled Shorts carry YouTube's "Made with AI" label.

**No good evidence found:** how often Indians watch with sound off; which script Indians type
when searching YouTube; whether subtitle or title script changes reach; whether Hindi viewers
accept AI voices; whether any on-screen engagement device raises retention.

**The report's bottom line.** The story and its first sentence decide reach; length, pace,
title style and endings did not separate hits from ordinary uploads. If only three things are
built, the report names: a selection rubric with the two keyless demand feeds (Wikipedia's
India list and competitor upload feeds), the first-sentence rule, and the analytics pull, which
is the only way to check any of it. It also finds that the genre changes picture about every
two seconds against this format's five-second shots (a crude estimate from preview stills),
and that the spoken Hinglish ran 78 words for content that took 59 in English, so the English
word cap does not transfer.

## 6c. Decisions waiting for the operator

None of these blocks the rewrite; each has a default the design can state.

1. **Length.** Stay at 25-35 seconds (five clips, about $0.90), or go toward the 60 seconds the
   leading channels use? At $0.179 a clip a 60-second reel of all-video shots costs about $2.
   Default: stay at 25-35 seconds; the evidence does not favour either.
2. **Cut rhythm.** Keep five-second shots, or cut and reframe within the bought clips every
   2-3 seconds? Default: cut on clause boundaries within the clips, at no extra spend.
3. **Measuring.** Re-run `tools/get_youtube_token.py` once so the pipeline may read retention
   and viewer country. This is the single operator action the audit and the report both put
   first. Default: build the pull and leave it idle until the token has the scope.
4. **The 4-5 a day goal.** The report recommends retiring it for about 20 a month, which is
   what the operator has already said the budget allows.
5. **The existing channel or a new one.** The old Shorts' audience may not be Indian (section
   6a, E). Nothing in the research settles whether a channel with 87 low-view English Shorts
   starts behind a fresh one. Default: keep the channel.
6. **A one-off opinion from a media lawyer** on three unsettled points: whether a stock
   text-to-speech narrator counts as synthetic information, whether the news-publisher rules
   reach this channel, and whether the election silence period binds it.
7. **The disclosure flag.** Whether "Altered content" shows "Yes" in Studio has been an open
   operator item since 2026-06-09, and the operator declined to check on 2026-11-10. The
   packaging report covers what can be verified from code alone.

## 7. Next steps, in order

1. ~~Collect the remaining research notes and audit reports; copy them into `research_notes/`.~~ Done 2026-11-10.
2. ~~Write the India research report from the five notes.~~ Done 2026-11-10.
3. **Next, once the operator says to continue:** check the audit's main claims against the code
   and data before relying on them. The 88 findings came from single auditors; the design
   review showed that a sceptic's second look changes details even when the finding holds.
4. Rewrite the design once, with sections 5, 6, 6a, 6b and 6c and the verified audit findings
   folded in. The 2026-11-17 voice deadline (section 6a, F) may need handling ahead of the rest.
5. Have the changed parts of the design reviewed.
6. Write the build plan from the design (`docs/superpowers/plans/`).
7. Build in stages, tests first, each stage verified. CI is the proof (rule 15).
8. One-time setup, with the operator's go-ahead: the `HF_API_KEY` repository secret, the new
   SQL in Supabase, the repository variables, then one real reel.
9. Update `STATUS.md`, `CHANGELOG.md`, `CLAUDE.md` and the docs the change touches (rule 1).

## 8. Rules that are easy to forget

- Never print, log or commit the Higgsfield key or anything from `.env`.
- No AI attribution in commits, pull requests, code or docs.
- Commit and push only when the operator asks.
- A fallback for every new dependency: a Higgsfield or Hinglish failure must cost a shot or the
  language of one reel, never the reel.
- No spend cap in code.
- The local `.env` has an empty `HF_API_SECRET` line and a comment saying "paste both". Both
  are wrong now (the console issues one combined key): tidy them at build time without
  printing any value. `.env.example` has no Higgsfield entry yet.
- The operator approves ideas, not finished reels, and declined to do manual checks in YouTube
  Studio. Anything that needs a human look has to be made automatic or dropped.
