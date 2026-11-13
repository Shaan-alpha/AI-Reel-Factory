# AI-video reels in Hinglish for Indian viewers

**Date:** 2026-11-12. Rewrite of the first draft of 2026-11-10, which is archived beside its review
in `research_notes/Design review 2026-11-10/first_draft_2026-11-10.md`.
**Status:** Second draft, complete and read by a fresh builder (2026-11-12). Its two questions are
answered here: the per-reel budget (the operator chose $1.10, 2.1) and the judging rule (10.2).
**Evidence:** [2026-11-10-ai-video-reels-research.md](2026-11-10-ai-video-reels-research.md) (reach and
prompt craft, with sources); `reports/Hinglish Shorts reach in India.md` (the India report);
`research_notes/Channel audit 2026-11-10/` (88 audit findings, and `verification/` with a second
reviewer's check of each against the code and data); `research_notes/Design review 2026-11-10/`
(51 review findings on the first draft, 21 confirmed); tests 1-4 in `test-videos/`.
**Scope:** new modules `src/higgsfield.py`, `src/ai_video.py`, `src/hinglish.py`, `src/demand.py`,
`src/gates.py`; changes to `src/visuals.py`, `src/assembly.py`, `src/subtitles.py`, `src/voice.py`,
`src/scriptwriter.py`, `src/factcheck.py`, `src/ideation_fallback.py`, `src/news.py`,
`src/trends.py`, `src/production.py`, `src/publish_youtube.py`, `src/analytics.py`, `src/db.py`,
`src/config.py`; their tests and `tests/conftest.py`; `tools/`; the `make-short`, `production`,
`analytics`, `tests` and `verify-tts` workflows; `.env.example`; the docs in section 16.
**New tables and columns:** section 13. **New system packages:** Tesseract OCR (section 11.6).
**New Python dependencies:** none.

## 1. What this is and why

The channel has 87 live Shorts since June 2026, about 16,000 views in all, a median of 44 views a
Short and a best of 1,256. It publishes about 0.7 a day. On 2026-11-10 the operator chose a new
format after four test videos, and asked for a full audit of the pipeline for reach.

The new reel is a narrated AI-video Short for Indian viewers:

- **Pictures:** the pipeline's own FLUX stills, each animated into a 5-second clip by Kling 2.5
  Turbo on Higgsfield (test 3: four clips, $0.72).
- **Voice:** one informative male narrator, Gemini TTS `Charon`, speaking **Hinglish**: Hindi
  sentences with English words, written Hindi in Devanagari and English in Latin script (test 4).
- **Text on screen:** **English subtitles** in short blocks that follow the narration, plain white
  (test 4).
- **Stories:** current, high-impact stories from anywhere that an Indian viewer has a stake in;
  science and technology welcome; not necessarily political.

The research and the audit agree on what moves reach, in this order: **which story is picked**,
**what the first sentence says**, and **measuring** whether viewers stay, which is the only way to
check either. Format, length, pace and title style did not separate hits from ordinary uploads in
the India sample. This design therefore changes selection and the opening as much as the pictures.

## 2. Who decided what

### 2.1 The operator decided (fixed)

From 2026-11-10, in order:

1. **Format:** every reel is a narrated AI-video reel like test 3: FLUX stills animated by Kling
   2.5 Turbo on Higgsfield, with the pipeline's normal edit. Presenters, avatars and lip-sync were
   tried and dropped.
2. **Money:** Higgsfield is an approved billed service: about 20 videos and $60-80 a month, up to
   about $1 a reel. **No monthly spend cap and no video-count cap in code** ("ill stop myself").
   Costs are logged.
3. **Voice:** male and informative; test 3 used Gemini TTS `Charon`.
4. **Language:** narration in Hinglish, subtitles in English ("loved it", after test 4).
5. **Audience:** "content for indian basically". One audience: Indian viewers.
6. **Topics:** trendier, currently impactful stories from anywhere; not necessarily political;
   technology and science welcome.
7. **No watermark and no on-screen "AI-generated" label.** The disclosure is one line in the
   description plus YouTube's synthetic-content declaration. The corner logo and the music beds stay.
8. **Reach:** refine the prompts, scripts and metadata from current research, and audit the
   pipeline and the content prompts for watchability, reach and views.
9. **Tools:** free tools may be installed where they improve the content (Tesseract was named).
10. **Working style:** go on research and judgement; no requests for manual checks (the operator
    declined to fetch YouTube Studio figures). Confirm before committing, pushing, changing
    repository secrets or variables, deploying, or spending beyond the above.

From 2026-11-12:

11. **Voice model:** `gemini-3.1-flash-tts-preview` with `Charon` and test 4's prompt, chosen by ear
    over both Gemini 3.8 TTS models ("voice a is better than others"), moved to Vertex at once
    ahead of the Developer API's 2026-11-17 shutdown ("change it now").
12. **Per-reel spend:** up to **$1.10**, so a typical reel is video from start to finish (6 clips,
    $1.07; about $21 a month at 20 reels). Chosen over $1.00 with one or two stills a reel, and over
    up to $1.50 for every reel.

### 2.2 Calls made in this design (the operator should check these)

Each is the builder's default; the section named gives the reason.

1. Scripts are plain, informative explainers: no sarcasm or roast (9.1). Test 3 and 4 read this way.
2. The English script stays the single fact-checked source; the Hinglish is a checked rendering of
   it, made after the fact-check (7.1).
3. Numbers are written as digits in the rendering and spoken as English words by code, so the number
   the fact-check passed is the number said (7.3).
4. Names stay in Latin script in the Hinglish (7.3).
5. A reel whose Hinglish fails its checks is narrated in English with today's word-by-word
   captions, never dropped (7.6).
6. The hook-judge rewrite is off for the new format; its rules move into the writer's prompt (9.2).
7. The "winning titles" block in ideation is off until 20 new-format reels have 72-hour data (8.4).
8. The topic mix is enforced in code at the final pick, with no science quota (8.4).
9. The reel is rendered at 24 fps and no clip is ever slowed; extra screen time comes from free
   stills (6.3, 11.1).
10. Cuts are hard cuts on the narration's pauses, about every 2-3 seconds, reframing inside each
    bought clip at no extra spend; the loop back to the start is a plain cut (11.2; the operator's
    open question 18.2).
11. The output goal becomes about 20 reels a month, the figure the operator's budget already sets,
    instead of 4-5 a day (18.4). CLAUDE.md changes at relaunch.
12. edge-tts and Kokoro are left out of the Hinglish voice chain; a Hinglish reel that no Hindi voice
    can read is narrated in English (7.5).
13. The title is one string of at most 7 words and 44 characters, and is also the frame-1 banner
    (9.4).
14. Subtitles are English clause blocks in the narration's spoken order (7.7).
15. The vignette and the cut stings go, and the music bed comes up (11.3, 11.4).

## 3. Goals, non-goals, anti-goals

**Goals**

1. Every reel is an AI-video reel: FLUX stills animated by Kling 2.5 Turbo Standard, for at most
   `AI_VIDEO_BUDGET_USD` (default 1.10) of Higgsfield spend.
2. Every reel is narrated in Hinglish with English subtitles, and what is spoken says what the
   fact-checked English says, number for number.
3. Ideas are chosen for Indian viewers, with demand measured from free public feeds.
4. The first sentence states the story's newest or most extreme true fact, with its subject and
   the Indian stake, and speech starts on frame 1.
5. Every Short's retention, traffic source and viewer country are recorded from the YouTube
   Analytics API, with a judging rule fixed before the first new reel.
6. No reel is lost or stalled by Higgsfield, the Hinglish step or a fallback voice. Each failure
   costs a shot or the language of one reel.
7. No shot is paid for twice, no job exists without a ledger row, and every dollar reaches Telegram.

**Non-goals**

- Presenters, avatars, lip-sync, a named narrator persona.
- Any monthly budget or video-count cap.
- Devanagari or Roman-Hinglish captions; word-by-word highlight on the Hinglish reels.
- A/B tests, the unused `hook_performance` table, playlists, pinned comments, interactive stickers.
- Text-to-video, other video models, webhooks, the Higgsfield SDK.
- A scheduled Google Trends collector (the project avoids schedules; GitHub runs them hours late).
- Letting the operator point the pipeline at a story (section 19).
- Changing how runs are triggered (on demand only).

**Anti-goals** (the build has failed if any of these happen, even if it runs)

- A reel fails, or blows the job's time limit, because Higgsfield is slow, down or out of funds.
- Money is spent twice for one shot, or spent without a ledger row, or spent without the operator
  hearing about it on Telegram.
- The narration says a number, name or claim the fact-checked English does not, or the subtitles
  show text the narration did not say.
- A reel shows a recognisable real person, a photoreal depiction of a real event, or animates a
  photo of real people.
- Reels become interchangeable: one fixed script skeleton, boilerplate descriptions.
- A hook promises what the reel does not deliver.
- The Higgsfield key, either half of it, or a signed URL appears in a log, an error, a Telegram
  message or a commit.

## 4. Constraints

- **CLAUDE.md rules** that bind this work: 2 (billing; Higgsfield is sanctioned by the operator,
  and the rule's text is rewritten at relaunch, section 16), 5 (secrets), 6 and docs/08
  (compliance), 7 (typed contracts), 8 (verify), 10 (pinned dependencies), 11 (fallback chains),
  12 (safe to run twice), 13 (cost awareness, Telegram on hard failure), 14 (loud on
  misconfiguration, soft at runtime), 15 (CI is the proof: `ubuntu-24.04`, Python 3.12).
- **Time.** A run is one GitHub Actions job: `make-short` 90 minutes (its Python step 85),
  `production` 60 (step 55). Reels run one after another. Measured on 2026-10-22: script 18 s,
  check 7 s, voice 15 s, visuals 83 s, render and captions 76 s, upload 2.5 s.
- **Higgsfield API** (live calls on 2026-11-10 unless marked "docs"; notes in
  `research_notes/Higgsfield API notes/`):
  - Base `https://api.higgsfield.ai`; header `Authorization: Key <HF_API_KEY>`, where the console's
    one key is already `id:secret`.
  - Submit `POST /{endpoint}` with a flat JSON body; the reply carries `request_id`. Status
    `GET /requests/{id}/status`: `queued`, `in_progress`, then `completed`, `failed`, `nsfw` or
    `canceled`. The video is at `video.url`; result URLs last 7 days (docs).
  - Price `POST /estimate/{endpoint}` with the same body: free, returns `usd`.
  - Upload `POST /files/generate-upload-url` with `{"content_type"}` returns `upload_url` (a
    presigned PUT), `public_url` and `upload_headers`.
  - **Idempotency (docs):** a repeated `Idempotency-Key` with the same endpoint and body "returns
    the original `request_id` without creating or charging for another generation"; the same key
    with a different body is `422`; a request refused before acceptance does not use up its key.
    The build confirms this with one live call (section 15) before the client relies on it.
  - Errors (docs): `failed` and `nsfw` are not charged; 403 is insufficient balance (prepaid, no
    balance endpoint); 429 `account_queue_full` with `Retry-After`, nothing charged; 503
    `admission_control_unavailable` is retryable; a queued request can be cancelled with
    `POST /requests/{id}/cancel`.
  - Concurrency is set per account (console only). Four jobs submitted together all finished in
    93-105 s, so at least four run at once.
- **Kling 2.5 Turbo Standard image-to-video** (`kling-video/v2.5-turbo/standard/image-to-video`):
  inputs `prompt`, `image_url`, `duration` (5 or 10), `negative_prompt`, `cfg_scale`. For a
  768x1344 still: 724x1268, 24 fps, 121 frames (5.04 s), no audio. $0.179 a 5 s clip on this
  account (the pricing page's discounts do not apply; `/estimate` is the truth).
- **Voice deadline.** On 2026-11-17 the Gemini Developer API shuts down both TTS models the voice
  chain starts with; the same models keep working on Vertex, billed (section 7.5).
- **Rules in India** (information, not legal advice; India report, last section): the uploader's
  stated duty is to declare AI use truthfully; photoreal AI depictions of real events or people
  presented as real are prohibited outright; defamation and false alarming information are crimes;
  the government blocks channels. A label on screen is not required of the uploader today.
- **Revenue reality:** about $0.008 per 1,000 Shorts views for Indian audiences against $0.328 in
  the US (one source). The Higgsfield spend buys reach, not ad income.

## 5. The new reel, end to end

| # | Step | Module | What changes | If it fails |
|---|---|---|---|---|
| 0 | Sweep the Higgsfield ledger | `ai_video` | New: settle jobs left open by earlier runs | Logged; the run goes on |
| 1 | Ideas | `ideation_fallback`, `demand`, `news`, `trends` | India rubric, demand feeds, mix in code (section 8) | Existing chain: Gemini grounded, then Groq |
| 2 | Approval | `approval` + bot | "Published" per reel; the bot's argument fix (8.6) | Unchanged |
| 3 | English script | `scriptwriter` | Viewer named, opening check, structures, one short title, length in seconds (section 9) | Existing chain: Claude, grounded draft, Gemini, Groq |
| 4 | Fact-check | `factcheck` | Default thinking; forecasts about India count as claims; grounding logged (9.7) | Unchanged: blocks or repairs |
| 5 | Hinglish rendering | `hinglish` (new) | New: two-text lines, code checks, a second model's meaning check (section 7) | Retry once, then the reel is narrated in English |
| 6 | Voice | `voice` | Charon, Hinglish style prompt, Hindi-capable fallbacks only, head and tail trim (7.5) | Next voice; no Hindi voice left means English narration |
| 7 | Pictures | `ai_video` (new), `higgsfield` (new), `visuals` | Shot plan, stills, Kling clips, ledger (section 6) | Per shot: Kling, then a still; per reel: today's `ai` path, then stock video |
| 8 | Gates | `gates` (new) | Stray text and darkness on stills, black or frozen clips, the finished reel (11.6) | A bad still is redrawn once; a bad clip becomes a still; a bad reel is not uploaded |
| 9 | Edit | `assembly` | 24 fps, hard cuts on pauses, no vignette, no stings, music level (section 11) | Existing plain-graph retry |
| 10 | Text on screen | `subtitles` | English clause blocks timed from the narration's pauses, banner held for sentence one, key number (7.7, 11.5) | Existing burn; English reels keep word captions |
| 11 | Upload | `publish_youtube`, `production` | Audio language from what was voiced, text `en`, disclosure line by source, hashtags, category, read-back (9.9) | Unchanged retries |
| 12 | Measure | `analytics` | Format stamp, one row per attempt, retention, India share and traffic per Short at 7 days (section 10) | Logged; never blocks a run |

The fact-check (step 4) still runs before any money is spent on voice or video.

## 6. Part A: AI-video shots

### 6.1 Shape

A new visual source, `VISUAL_SOURCE=ai_video`. The existing sources (`photos`, `ai`, `video`) keep
working unchanged, and `ai` is what a reel falls back to.

| Module | Responsibility |
|---|---|
| `src/higgsfield.py` (new) | The only code that talks to Higgsfield: estimate, upload, submit, status, cancel, download. Raw REST with `requests`; no SDK (it retries on its own). |
| `src/ai_video.py` (new) | One reel's shots: sizing, the shot planner, stills, buying, waiting, settling, the ledger sweep, the spend report. |
| `src/visuals.py` | `fetch_broll` delegates `ai_video` to `ai_video.make_shots` and keeps every existing path. FLUX and Ken Burns helpers are shared. |
| `src/db.py` | The `ai_video_jobs` ledger: reserve, update, read open rows, month-to-date. |
| `src/assembly.py` | Takes a cut list (section 11.2) and a frame rate, besides today's arguments. |
| `src/production.py` | Passes the script, idea, narration, its pauses and a latest-finish time to visuals; passes the cut list to assembly; reports spend. |

`ai_video.make_shots` returns typed data, not a bare list: one entry per shot in order (the file,
whether it is a Kling clip or a still, its usable seconds), the cut list for assembly, the number
of video and still shots, the Higgsfield spend for this reel, and any problem worth telling the
operator. No module reads another's globals.

### 6.2 One reel, step by step

After the narration exists, with its length `D` (probed from the trimmed file) and its pauses:

1. **Can it buy at all?** If this run has already stopped buying (6.4), or `HF_API_KEY` is unset,
   or the ledger cannot be read, the reel skips the planner and Kling and goes straight to the
   `ai` path. The operator is told once per run. **The subtitle burn is tested first:** the reel's
   subtitle file is burned onto a one-second blank clip; if that fails, nothing is bought, since the
   reel would fail at captions after paying (the October outage broke exactly that step for 8 days).
2. **Price.** Ask `/estimate` for one 5 s clip. `k = floor(AI_VIDEO_BUDGET_USD / price)` is the
   most clips this reel may buy (6 at $0.179 and the default $1.10). A failed or non-positive quote
   counts as step 1.
3. **Size.** Choose the number of shots `m` and which of them are video (6.3).
4. **Plan.** One model call writes `m` shots, each a still prompt and a motion prompt (6.5).
5. **Stills.** Generate the `m` stills with FLUX.2 klein at 768x1344 with the per-reel, per-shot
   seed, then run the still gate (11.6). Only a klein still may be animated: a FLUX.1 schnell
   still (square, unseeded) or a Pexels photo stays a still.
6. **Reuse.** Read this idea's ledger rows. A `completed` row under 7 days old at the same shot
   position is downloaded and not bought again; a reused clip may not match a rewritten line, an
   accepted trade. Clips already paid for this idea count against `k`. A failed ledger read means
   nothing is bought for this reel.
7. **Buy,** for each remaining video position in order, up to `k`:
   1. **Reserve first,** as `claude_spend` does: insert the row with status `reserved`, the quoted
      cost, and a fresh idempotency key (a UUID) before anything is sent. If the insert fails,
      buy nothing more for this reel.
   2. Upload the still; submit the Kling job with the row's key.
   3. On an answer, store the `request_id`; status `submitted`.
   4. **A submit with no answer** (timeout, dropped connection) is repeated with the same key and
      body, inside the phase deadline; Higgsfield documents that this returns the original job
      without a second charge. If it never answers, the row stays `reserved` at its quote (it may
      have been charged) and the shot becomes a still.
   5. **A refusal that is never charged** (403, 422, 429 past the deadline, any other 4xx) sets
      the row's cost to 0 and status `refused`. A 429 with a `Retry-After` inside the deadline is
      waited out and resubmitted with the same key.
8. **Wait.** Poll every job (2 s, then x1.5 up to 10 s, with jitter) until all are terminal or the
   phase deadline passes (6.4).
9. **Settle.** `completed`: status, seconds taken and result URL. `failed` or `nsfw`: cost 0. At
   the deadline a `queued` job is cancelled, and marked `canceled` at cost 0 **only** when the
   cancel reply confirms it or a re-read status says `canceled`. A job already `in_progress` is paid
   for, so it is polled for up to `AI_VIDEO_GRACE_SECONDS` (120) more, inside the latest-finish
   time, and used if it arrives; anything still unfinished is `late` at its quote and its shot
   becomes a still.
10. **Clips.** Download each finished clip and run the clip gate (11.6). A clip that fails to
    download or fails the gate leaves its row `completed` (it is never bought again) and the shot
    becomes a Ken Burns still.
11. **Whole-reel fallback.** If no clip came back, the reel uses its planned stills with Ken Burns
    on the same cut list. If the stills failed too, the existing `ai` path runs, then stock video.

### 6.3 Sizing (a pure function)

Inputs: narration seconds `D`; its pauses; `k`; the usable clip length `L = 5.0` (of 5.04). No clip
is ever slowed or frame-rate converted (11.1).

- The cut list (11.2) and the shot count `m` come from one pure function in assembly: shots first,
  each at most `L` seconds and ending on a pause, then a reframe inside each longer shot.
- There is no reprise of shot 1 at the end (11.2), so every second of screen time is a shot's own.
- The first `min(m, k)` shots in the order below are video; the rest are stills (Ken Burns over the
  planned still, free).
- **Order of video positions:** shot 1 (the opening claim), then the last shot (the payoff), then the
  rest from the start. A still never opens the reel.

Simulated on both test narrations (26.4 and 26.8 s), the rule gives **6 shots** each, so at the
default $1.10 (`k` = 6) a typical reel is video throughout for $1.07. A narration of 30-35 s comes to
about 7-8 shots, so its last one or two middle shots are stills. (The builder's check found that the
first version of the rule, segments first and paired into shots, gave 8-9 shots for the same
narrations.)

### 6.4 Time and the stop latches

- **One deadline for the whole Higgsfield phase,** from the quote to the last download:
  `AI_VIDEO_TIMEOUT_SECONDS` (default 300). Uploads, submits, retries and `Retry-After` waits all
  spend from it; a `Retry-After` longer than what is left counts as a refusal.
- **A latest-finish time from production.** Production passes visuals a number: the seconds left
  in the job minus the tail the reel still needs after visuals (`AI_VIDEO_TAIL_SECONDS`, default
  240; measured 161.5 s). The phase ends at whichever comes first.
- **The job clock.** `JOB_TIMEOUT_MINUTES` is set to the Python step's limit (85 in `make-short`,
  55 in `production`), not the job's, so `_seconds_left()` can never be later than the real kill
  (review finding: it ran about four minutes fast).
- **Worst case per reel,** every clip late: about 40 s script, check and voice, 20 s rendering
  and checking the Hinglish, 40 s plan and stills, 300 s Higgsfield phase, 160 s render, captions
  and upload, plus a repair pass: about 10 minutes. `REEL_BUDGET_MINUTES` goes from 12 to 14.
- **Stop latches,** each lasting for the rest of the run, each with one Telegram alert: a 403 (out
  of funds); a 401 or other refusal of the key; a missing ledger table; a reel whose phase
  deadline passes with no clip finished (a slow queue would otherwise charge every reel in the run
  for clips that arrive too late).

### 6.5 The shot planner

One call through `llm.generate(json=True)` (Gemini on Vertex, then Groq; no search). It gets the
English script with tags removed, the title, the tone (`somber` or not), the India setting
flag visuals already receives, `m`, and the per-shot durations. It returns `m` shots in narration
order, each `{"still": "...", "motion": "...", "search": "..."}`; `search` is a 1-3 word stock
query, used only if this shot falls back to a Pexels photo.

**Rules for every still prompt** (research part 2.1; audit visuals-edit 5):

- Descriptive prose of 60 to 100 words, not a tag list. Subject and action first, then setting,
  then light (source, direction, softness).
- One main subject, **large and centred, filling the middle half of a vertical frame**, brightly
  and evenly lit; a named shot size and angle. The top fifth and the lower third are simple and
  calm, because the banner and subtitles sit there. The planner is not told that reason: told it,
  it wrote "room for the title and subtitles" into its stills (stage 4b's render), and the image
  model draws what it reads. It is told never to name text, even to exclude it.
- Describe the wanted state, not negatives ("all surfaces are plain and unmarked"), and avoid
  nouns that invite lettering or a screen (sign, poster, headline, screen, laptop, phone,
  computer, television, keyboard, newspaper, book, chart, label, banner, document).
- End with the fixed look: `Style: cinematic 3D animated film still, stylized shapes, rich saturated
  color, bright clear lighting. Mood: <mood>.` (`AI_VIDEO_STYLE` overrides the look.)

**Rules for every motion prompt** (research part 2.2):

- One to three short sentences of motion only. One slow subject motion, at most one supporting
  motion, and what stays still. Exactly one camera instruction: static, or one slow stable move.
- Nothing that is not in the picture; constraints in the prompt ("keeps its exact shape and
  colors"). `cfg_scale` stays at its default. The fixed negative prompt is sent as test 3 did:
  `text, subtitles, captions, watermark, logo, distortion, warping, flicker, fast motion, scene change, people`.

**Content rules** (docs/08; India report; review finding 9):

- No recognisable real person or likeness: show places, objects, symbols, hands, or small figures
  seen from behind. No logos, brand marks, flags carrying text, documents, screens or interfaces.
- Nothing that imitates footage of the real event: no disaster in progress, no violence, no
  bodies, no crowd in distress. A somber story gets calm symbolic scenes and minimal motion.
- Shot 1 illustrates the opening claim; the last shot illustrates the payoff.
- **A code check** rejects the plan if any still or motion prompt contains a person's name from
  the story (any capitalised name in the script or idea that is not a place on a fixed list of
  countries, Indian states and large cities). One retry with the offending names quoted back; if
  it fails again, the plan is built from `extract_keywords` and `_img_prompt` with one generic
  motion line, and **nothing is bought** for that reel.
- **A second code check** (stage 4a, from the test renders: a laptop of fake code; calibration,
  2026-11-13: every laptop prompt drew lettering, 4 of 4, and no other prompt did) finds words
  that make the image model draw lettering or a screen (`ai_video._LETTERING_WORDS`, singular or
  plural, whole words) and quotes them back in the same one retry. It never costs a reel its
  clips: after the retry, the last plan that names no one is used, and the still check (11.6)
  is the backstop.

### 6.6 The Higgsfield client

- **Key.** `HF_API_KEY` holds the console key. It is optional in `config` (not in `REQUIRED`).
  `HF_API_SECRET` is dropped, and the local `.env`'s empty line and its "paste both" comment are
  removed without printing any value.
- **Headers only where they belong.** The `Authorization` header is attached only to requests to
  `api.higgsfield.ai`, never to the presigned upload or the result download (an S3-style presigned
  PUT also rejects a second credential).
- **Never printed.** Every error from this module passes a redactor that removes the whole key,
  each half of it, and the query string of any URL, before it is logged, raised or sent.
- **Timeouts** on every request. A status poll that fails is retried on the next tick.
- **Retries** follow 6.2 step 7: only with the same key and body, only inside the phase deadline,
  and never for a status that says the request was refused.

### 6.7 The ledger

SQL in section 13. Rules:

- No row, no purchase: the row is reserved before the submit (6.2 step 7).
- **The sweep:** at the start of every run (both entry points) and once after the last reel, every
  row under 7 days old that is `submitted` or `late` is re-read and settled: `completed` with its
  URL; cost 0 for `failed`, `nsfw` or `canceled`. A `reserved` row (its submit never answered, so it
  has no request id to read) stays counted at its quote. Status calls are free; the sweep is
  fail-soft.
- `db.ai_video_spend_this_month()` returns the month's total, for the log and Telegram only. It is
  not a cap.
- **Paid clips keep their idea alive.** An idea released after a failed attempt that left completed,
  unused clips is not aged out for 6 days (the clips' URLs last 7), so a fresh approval reuses them
  instead of the money being lost to the 24-hour age-out.

### 6.8 What the operator sees

- The "Published" line gains the reel's spend and the month-to-date:
  `AI video: 5 of 6 shots, $0.90 ($14.30 this month)`.
- The "Reel failed" alert gains the reel's Higgsfield spend when it is above zero.
- One spend line at the end of every run, from both `make_on_demand` and `run()`, read from the
  ledger: clips bought, dollars, clips paid for and not used, the month-to-date.
- One alert per run, per kind: out of funds; key missing or refused; ledger missing; a reel that
  shipped with fewer video shots than planned (with the count); a stop latch tripped.

### 6.9 Fallback chain (rule 11)

Per shot: Kling clip, then a Ken Burns move over the same klein still, then the existing still
fallbacks (FLUX.1 schnell, a Pexels photo found with the planner's `search` words, never with the
still prompt). Per reel: the `ai_video` path, then the existing `ai` path, then stock video. A
missing key, a missing table, an empty balance, a slow queue, a rejected prompt or an outage each
cost video shots, never the reel.

### 6.10 Disclosure and licence

- The description's disclosure line for this source: `AI-generated narration, video and music.`
  (The 78 published descriptions saying "stock visuals" over AI images are corrected by section
  9.9's line for the `ai` source, going forward; published descriptions are not edited.)
- `containsSyntheticMedia` stays on for every upload, and the upload's read-back (9.9) confirms that
  it landed.
- Higgsfield's terms (extract in `research_notes/Higgsfield API notes/terms_extract.txt`) are
  recorded in docs/04 as the licence basis for the clips (review finding).

## 7. Part B: Hinglish narration, English subtitles

### 7.1 The two-text contract

`NARRATION_LANGUAGE=hinglish` turns this part on; `english` (the default until relaunch) keeps
today's English narration and word-by-word captions.

The English script is written and fact-checked exactly as today. After the gate passes, it is
split into sentences, and every sentence becomes one **line** with two texts:

- `en`: the English sentence, unchanged. It is what the fact-check saw and what the subtitles show.
- `hi`: the same sentence as spoken Hinglish. It is what the narrator says.

Lines are stored in order on the script row (section 13), one Hinglish line per English sentence,
so the pairing never needs re-deriving.

### 7.2 Rendering

One model call receives the numbered English lines, the story's title, the tone, and the rules
below, and returns `{"lines": [{"i": 1, "hi": "...", "parts": [{"hi": "...", "en": "..."}]}, ...]}`
(the English line is not echoed back; code pairs by number; `parts` serve the subtitles, 7.7).

The renderer is **Claude** (`claude-opus-5-5`, effort low, structured output), through the
existing `claude_spend` ledger with purpose `hinglish`: test 4's approved Hinglish was
Claude's, and the call costs about $0.03 (about 1,500 tokens in, 1,000-1,500 out, since Devanagari
takes more tokens than English), so 20 reels a month of script plus rendering come to about $1.35
against the $4 Claude cap. If Claude is unavailable or its budget is spent, Gemini on Vertex renders,
then Groq. The refusal fallback the Claude API offers is switched on for this call.

Rules for `hi`:

- Natural spoken Hinglish of young urban Indian creators: Hindi grammar, English words where an
  urban speaker would use them, conversational rather than news-anchor Hindi.
- Hindi words in Devanagari, English words in Latin script.
- One `hi` line for each `en` line, saying the same thing: nothing added, nothing dropped, no
  softening or sharpening of a claim.
- Numbers stay as digits exactly as in the English (7.3). Names stay in Latin script exactly as in
  the English.
- Sentence one: the subject or the surprise inside the first four words; as short as saying all of
  its English allows, at most 12 words when the English is that short, never a word of its meaning
  dropped to get there; never a date, a place or a greeting first; no "kya aap jaante hain".
  (2026-11-13: a hard 12-word cap contradicted "nothing dropped". 31 of the 40 newest English first
  sentences run over 12 words, median 17, and the first test render's Hinglish cut a clause to
  comply, was refused by the checks, and fell back to English.)
- End each line with the Hindi full stop `।` or a question mark.

### 7.3 Spoken form and the code checks

Code then checks every line; any failure sends the whole rendering back once with the failures
listed, and a second failure ends Hinglish for the reel (7.6):

1. One line for every English sentence, numbered as sent, none missing or extra.
2. Every number token in `en` (digits, with `,` `.` `%` and currency symbols) appears in `hi`.
   No number appears in `hi` that is not in `en`, and `hi` carries no Hindi number word (दो, तीन,
   चार ... सौ, हज़ार, लाख, करोड़; एक is exempt, being also the article "a"), since the number guard
   cannot see those.
3. Every name in `en` (a capitalised word that does not start the sentence) appears in `hi` in
   Latin script.
4. `hi` contains Devanagari, and contains no character outside Devanagari, Latin, digits, ordinary
   punctuation, and the currency and percent signs.
5. The total spoken length fits the reel: estimated at the measured 2.9 Hinglish words a second,
   between `HINGLISH_MIN_SECONDS` (24) and `HINGLISH_MAX_SECONDS` (36). Test 4 measured 78 Hinglish
   words in 27.0 s for the content that took 59 English words in 26.7 s: the seconds match, so the
   English script's own budget (about 2.2 words a second) predicts the reel's length, and the word
   cap is set in seconds (9.5). The voiced length is what finally sizes the shots.

After the checks pass, code (not the model) turns every digit into English words for the voice:
years as pairs ("nineteen seventy-seven"), decimals with "point", grouping as written ("lakh",
"crore", "billion" stay words), `%` as "percent", `₹` and `$` as "rupees" and "dollars", ordinals
("18th" as "eighteenth"). Test 4's numbers were spoken in English words and the operator approved
it; doing it in code keeps every spoken number identical to the checked one.

### 7.4 The meaning check

A second, independent call, always from a different provider than the renderer (Gemini on Vertex
when Claude rendered; Groq `openai/gpt-oss-120b` when Gemini rendered; Gemini when Groq rendered),
sees each pair and answers per line: does `hi` say the same as `en`, with nothing added, dropped, or
changed in strength? Any "no" is a failure under 7.3's retry rule. If the checker cannot run, strict
mode (`HINGLISH_STRICT`, default on) treats it as a failure. The checks were tested only on pairs
written for the purpose, so the build logs every verdict for later review.

### 7.5 The voice

- **Text is routed by script before synthesis.** Text containing Devanagari goes only to voices that
  read Hindi. Measured on test 4's text: edge-tts `en-IN-PrabhatNeural` dropped every Hindi word and
  returned 18.1 s of English fragments **with no error**; Kokoro spoke its own language markers aloud
  ("enus") at every switch; edge-tts `hi-IN-MadhurNeural` read everything but took 38.5 s for 27 s of
  content. Today's chain would publish the first two.
- **The voice is decided:** on 2026-11-12 the operator compared three samples of test 4's lines and
  chose **A**, `gemini-3.1-flash-tts-preview` with `Charon` and test 4's own style prompt, over both
  Gemini 3.8 models ("voice a is better than others").
- **The Hinglish chain:** that model and voice through the same-voice attempts (Developer API until
  2026-11-17, then Vertex 3.1, then Vertex's 2.5 GA model), then Chirp 3 HD `hi-IN-Chirp3-HD-Charon`
  once one rendered line passes its check in the build, then English narration (7.6). edge-tts and
  Kokoro are left out of the Hinglish chain.
- **Every engine's output is checked by length in seconds,** not words a second: within 0.75 to 1.30
  times the expected length (the English script's words at 2.2 a second). The broken renders above
  measure 0.67 and 1.56; Gemini's measured 1.01. A words-a-second band separated good from broken by
  0.03-0.11 words a second, too thin to trust. Outside the band, the next engine.
- **Style prompt:** test 4's prompt, word for word, because it is what the operator chose by ear.
  The audit's proposed additions (never American, full energy on the first word) are unheard and are
  not adopted. A somber version for deaths and serious harm is derived from it (calm and unhurried,
  the same accent direction), since today's somber prompt has none. No inline delivery tags in
  Hinglish text.
- **Trim** leading and trailing silence straight after synthesis (tested: 27.04 s to 26.26 s with
  speech 10 ms in); the trimmed length sizes the shots.
- **2026-11-17:** the Developer API's two TTS models shut down; the chosen voice answers from Vertex,
  billed (cents a reel), and the dead attempts are dropped. **Gemini 3.8 TTS** (the free successor)
  takes a different request (the style in its own field, the text read verbatim); the samples were
  rendered with it on 2026-11-12 (`gemini-3.8-flash-tts` 24.4 s, `-lite-tts` 26.6 s, against test 4's
  27.0 s; `test-videos/voice_A/B/C_*.mp3`) and the operator preferred today's model. The build adds
  the 3.8 request shape to the voice engine, selectable by `GEMINI_TTS_MODEL` but outside the default
  chain, and the tuning tool learns it and Vertex, so the move is a setting when Vertex retires 3.1.
- **English fallback voices** keep one narrator too: `GOOGLE_TTS_VOICE` moves to the English Charon
  voice, and the edge-tts and Kokoro links stay male.

### 7.6 When Hinglish fails

If the rendering fails twice, the meaning check fails twice, or no Hindi-capable voice succeeds, the
reel is narrated in **English** from the fact-checked script with today's chain, captioned with
today's word-by-word captions, uploaded with audio language `en`, and the operator is told. A
Hinglish failure never costs the reel.

### 7.7 English subtitles

- **No speech recognition on Hinglish reels.** Run on test 4's narration, today's caption step burned
  English that Whisper invented (a different invention on each run), because the script matched
  under 0.6. Speech recognition stays only for English reels.
- **Sentence timing from the audio:** `silencedetect` finds the pauses in the trimmed narration, and
  the sentence ends are assigned to pauses all together (each end goes to a pause, in order, keeping
  every sentence's share of the spoken characters as close as possible to its share of the time).
  This global assignment placed 5 of 5 sentence ends on both test narrations; snapping each estimate
  to its nearest pause on its own missed 2 of 5 on the English one.
- **Clause blocks in spoken order.** Hindi word order differs from English, so splitting an English
  sentence into phrases by length put test 4's phrases up to 1.9 s early and 4.25 s late. The renderer
  therefore also returns each line as parts in spoken order, `[{"hi": ..., "en": ...}]`: the `hi`
  parts join to the line's `hi` exactly, and the `en` parts are the English sentence's own words
  regrouped to follow the Hindi. Code checks that the `en` parts use only that sentence's content
  words and carry all its numbers and names. Part boundaries fall at the share of spoken characters,
  snapped to a pause within 0.3 s. If the parts fail their check, the whole English sentence shows
  for the sentence's time, in one or two blocks.
- **Text:** plain white, no word highlight (they are a translation, not a transcript); at most two
  lines a block, no single word alone on a line.
- **Position:** inside the vertical safe zone, clear of the banner, the source line and the action
  rail.

## 8. Part C: stories for Indian viewers

The channel's own audience so far is not Indian. From the YouTube Analytics API (first pulled
2026-11-12): of 16,048 lifetime views, 39% came from the US and **5.2% from India** (840 views, an
average of 52% of each Short watched against 77% in the US); 86% of views came from the Shorts feed
and 11% from search. The old view patterns describe that audience, so selection is rebuilt from the
India research, not from the channel's history.

### 8.1 Who the viewer is

Both ideation prompts and the script prompt name the viewer: Indians aged about 18-34 watching on a
phone, at home in Hindi and English, who care about what changes their money, jobs, exams, safety,
gadgets and the country's standing.

### 8.2 The story pool

- All five Google News feeds stay (English edition: India front page, World, Business, Technology,
  Science). The pool deepens from 24 stories to about 60 (`NEWS_POOL_SIZE`, default set in code: the
  workflow does not pass the setting through). The Hindi Science feed is not added: it held 4 items.
- Puzzle and game-help items are dropped by title ("hints", "answers today", Wordle, Quordle,
  Connections, Strands): 3 of 5 Technology headlines on 2026-11-12 were of this kind.
- **Each story carries its age** (from `pubDate`, parsed today and never used). Over 48 hours old
  ranks lower unless it carries a new development.
- **Searches for Indian stakes:** a short configurable list of Google News searches
  (`NEWS_INDIA_QUERIES`, for example "Indian-origin", "Indian students", "for Indian users", "India
  vs China", "price hike India", "new rule India"), through the existing search fetcher, last 48
  hours, a few stories each.

### 8.3 Demand signals

- **Wikipedia's India list** (`src/demand.py`): the last eight daily India lists; drop the Main Page,
  special pages and search pages; score each article as yesterday's views over its own median for the
  week before, so evergreen pages do not rank. About 8 requests a run, inside the anonymous limit,
  with a generic User-Agent. One day late by design.
- **Comparable channels' upload feeds** (`src/demand.py`): the public RSS feeds of a configured list
  of Hindi explainer channels (`DEMAND_CHANNELS`, starting from the India report's sample); Shorts
  earning views an hour above their channel's own median are listed as "what Indian Shorts viewers
  are watching now".
- **Google Trends IN** stays as it is. It covers about 90 minutes, and `geo=IN,US` is refused with
  HTTP 400, so the first draft's two-country setting is dropped.
- The signals go into the picker's prompt as evidence. A story that shows in two of the three ranks
  higher. Nobody has tested whether they predict views for a small channel; the stored matches (9.8)
  let the retention data answer that.

### 8.4 The rubric and the final pick

- **Closer to the viewer ranks higher:** a named Indian or Indian-origin person; a personal stake
  (money, visas, safety, exams, jobs, prices); India beside another country; a dated event this week;
  the factual angle on what India is already watching; the unfamiliar term in the news, explained.
  **Lower:** routine launches, macro policy (the Budget as a subject, GST, tariffs), institutional
  news, distant events with no Indian angle, abstract science. India's hits are the science of
  ordinary things, not "pure" space or physics.
- **No science-majority quota.** The operator asked for "trendier, currently impactful stories from
  anywhere; not necessarily political; tech and science welcome". The first draft's "at least half
  science" and the audit's broad leave-out list are not adopted.
- **The category is stored.** The picker already assigns each story a category, and it is dropped
  before the idea row is written. It now returns one from a fixed list (`india-politics`, `india`,
  `money`, `world`, `science`, `space`, `tech`, `health`, `sport`, `culture`) and code stores it in
  the idea's existing `niche` column. It drives the mix, the YouTube category (9.9) and later analysis.
- **The mix, enforced in code at the final pick** (review finding 20): at most one `india-politics`
  idea per digest, at most two from any one category, at most one somber story. A pick that breaks a
  rule loses its lowest-ranked offender to the next eligible story.
- The "winning titles" block is suspended until 20 new-format reels have 72-hour views. When it
  returns it counts only posts since `WINNERS_SINCE` (the relaunch date) that are at least 72 hours
  old, and the "avoid" list of low performers is dropped. The old block steered toward one topic on
  noise.

### 8.5 De-duplication

- It runs before research, not after, so a duplicate costs no grounded search.
- "vs" and the hook template's stock words become stopwords: 3 to 5 of 20 replayed flags were
  unrelated stories matched on them.
- A follow-up that carries a new dated event is allowed inside the 10-day window.
- Untapped ideas end as `expired`, not `passed`, and expired stories are not banned by the window.

### 8.6 Approval

- **Each "Published" line is sent as its reel goes live,** not after the whole batch.
- **The bot's argument parsing:** today any non-numeric argument turns `/makeshort 2 isro docking`
  into a 5-idea run. The bot reads the leading number and ignores the rest. (A bot change needs a
  `vercel deploy`, which waits for the operator's go-ahead.)
- The digest's size and the three-approval cap are unchanged.

### 8.7 Rules that bind selection in India

From the India report (information, not legal advice): an allegation names the court record or
official order it rests on; in a live conflict a reel explains terms and mechanisms only; trending
terms naming a faith or a communal incident are excluded (the existing sensitivity filter); and no
election matter is chosen for a state inside the 48 hours before its polling closes
(`ELECTION_SILENCE`, a list of state and date pairs, empty by default, maintained by hand).

## 9. Part D: script and packaging

The script check (`verification/script-prompts.md`) found that only one view pattern in the old data
survives comparison within the same month and topic: **openings that start on the subject beat
wind-up openings** (Fisher p about 0.005). The other gaps (India mentions, the bridge phrase, length)
disappear inside a month, so they are treated as hypotheses for the retention data, not rules.

### 9.1 The writer's brief

- **Voice:** a clear, curious, confident explainer for the viewer of 8.1; no sarcasm, no roast, no
  jokes at anyone's expense. The truth-over-neutrality rules, the accuracy rules and the JSON reply
  stay.
- **Why it matters, concretely:** the payoff says what changes for a person in India (a price, a
  rule, a date, a risk, a job), using the sources; with no Indian stake, what changes for anyone. 36
  published payoffs checked: none said what changes for a person in India, and the prompt never
  mentions India.
- **No phrases to copy.** The prompts' quotable examples are replaced by descriptions of the move:
  the exact bridge phrase reached 13 of the last 40 scripts and the "💬" comment prompt all 40
  descriptions; the prompt demanded "isn't just X, it's Y". A code check warns when a published text
  repeats six or more consecutive words of a prompt example.
- **The payoff is marked, not matched.** The writer's JSON names the index of its "why it matters"
  sentence; the guard checks that index instead of `_WHY_IT_MATTERS_RE`'s literal phrase (review
  finding 18). Missing or out of range is a warning, as today.

### 9.2 The opening

- Sentence one states the newest or most extreme true fact, with its subject and the Indian stake in
  its first clause.
- **A code check on every script,** not only in repair: sentence one must have at least five words,
  must not start with a wind-up word (so, okay, alright, imagine, did you know, here's, picture this,
  ever wondered, let's, guess what), and must not open on a date or a day. Hedges ("apparently",
  "reportedly", "allegedly") are never wind-ups and are never cut: cutting one turns a hedged claim
  into a flat one before the fact-check. On failure the writer is asked once to rewrite sentence one
  with the reason; if that fails, a leading wind-up word is cut mechanically when what is left is a
  sentence of five words or more. The check runs before the fact-check, so the gate sees the final
  opening. Wind-ups were 9 of 41 picked up against 21 of 46 for plain openings; since October all 8
  openings were already plain (0 of 3 under Claude), so the check is a guard, not a cure.
- **One sentence splitter** for the scriptwriter, the voice and the subtitles, which no longer breaks
  on "U.S.", "U.K.", "Dr.", decimals or "..." (it split 10 of 87 published scripts wrongly at the
  start; 3 of those were splitter errors that tripped the opening guard).
- **The hook judge's rewrite is off** (`ENABLE_HOOK_JUDGE=false`): it lets a cheaper model (Groq
  first) rewrite the writer's opening and title on a "shock" score with no added-facts guard. The
  code stays; if switched back on, it gets the added-facts guard, is told the structure, and may
  reword sentence one only (review finding 16).

### 9.3 Structures

The true surprising fact is always sentence one; a structure is defined by what follows it (review
finding 15). Three, chosen by a hash of the idea id (so a digest's size cannot lock the choice) and
recorded on the script row; a somber story always takes the first:

1. **What happened:** the fact, how it happened, why it matters, what is scheduled next.
2. **The number:** the fact is a number; what it measures, what it compares with, why it matters.
3. **The belief:** the fact, then the common belief it overturns (only when a source records that
   belief), the evidence, why it matters.

A "what is next" beat must be a scheduled step the sources record, and a belief must be stated as a
belief (review finding 17). The writer may fall back to structure 1 and says so in its JSON.

### 9.4 The title, which is also the banner

- **One string, enforced in code:** English, at most 7 words and 44 characters, the searchable name
  first, stating the claim the reel delivers. At 44 characters it always fits the frame-1 banner at
  full size (three lines of 16).
- Why one string and not a separate banner: on the old data short titles were picked up more often
  even when a longer title's banner fitted (10 of 14 against 1 of 5), and since late July titles of 7
  words or fewer were picked up 15 of 23 times against 3 of 17. 42 of 87 titles could not fit the
  banner at full size. The draft's 40-55 characters kept the worst range.
- Over the limit, the writer is asked once to shorten it; then the title is cut at a word boundary
  inside the limit. The fact-check sees the final title (it already checks the title).

### 9.5 Length

- The budget is set in seconds: the English script aims at `SCRIPT_TARGET_SECONDS` (27) and may not
  pass `SCRIPT_MAX_SECONDS` (33), converted to words at 2.2 a second (about 60 and 73 words).
- The writer marks each sentence `core` or `optional`. Over budget, optional sentences are dropped
  from the end, never the payoff; the existing whole-sentence cut is the last resort. The second-model
  tighten rewrite is retired. (0 of the last 40 scripts were over 80 spoken words; the cap is a guard.)

### 9.6 Repair and every rewrite

- Every model-written rewrite (the opening fix, the repair pass) passes the added-facts guard
  (`_added_facts`), which today runs only on Claude's script.
- The repair's re-check uses the repaired title and description, not the originals, and the repair
  may fix the title too.

### 9.7 The fact-check

- The gate's model call moves from minimal thinking to the model's default.
- A forecast or consequence for India counts as a claim: it must be stated by a source or follow
  directly from sourced facts. (Causal statements already count; forecasts about India escaped.)
- Both the grounded draft and the gate log what grounding did (the number of citations, and the
  search queries when the response carries them) on the script row, so "the draft searched" is
  measured before anything is built on it. Claude's brief says the draft searched only when it has
  citations.

### 9.8 What is stored for learning

On the script row: the structure, the lines (English and spoken), which model wrote and which
rendered. On the idea row: the category, the demand signals that matched, and the score that ranked
it (today the main ranking key, `share_score`, is never stored).

### 9.9 Description, hashtags, tags, languages, category

- **Description:** line 1 restates the claim with its main keyword; line 2 is one sentence on why it
  matters; then the sources as publisher names, each with its own link (aggregator links are resolved
  to the publisher or dropped: 61% of the newest 30 descriptions' links were aggregators); then the
  disclosure line; then a one-line footer with no "every day" claim. The fixed "💬 comment below"
  prompt goes.
- **Disclosure line by source:** `ai_video`: "AI-generated narration, video and music."; `ai`:
  "AI-generated narration, images and music."; stock sources keep today's line. 78 published
  descriptions say "stock visuals" over AI images; they are not edited.
- **Hashtags:** at most three on the description's last line: up to two from the writer naming the
  story's subject or event, plus `#ButItMatters`. Generic ones are dropped by code (`shorts`,
  `youtubeshorts`, `viral`, `trending`, `fyp`, `foryou`, `explore`, `news`, `breaking`,
  `breakingnews`, `newsshorts`) and `#Shorts` is no longer added. The line is composed in
  `production._build_metadata` after the footer; hashtags are no longer merged into the tags (review
  finding 8).
- **Tags:** at most six from the writer (names and alternate spellings, Hindi spellings allowed) plus
  `But It Matters`; the other fixed channel tags go.
- **Languages, from what was actually voiced:** `defaultLanguage` `en` (title and description);
  `defaultAudioLanguage` `hi` for a Hinglish reel and `en` for an English one. Today one setting
  (`YOUTUBE_LANGUAGE`, default `en`) feeds both; a fixed `hi` would mislabel the English fallback.
- **Category** from the idea's stored category: 28 (Science & Technology) for science, space and
  technology, else 25 (News & Politics). Expect nothing from it in reach.
- **Read back after upload:** one `videos.list` (part `status,snippet`) on the new video stores what
  YouTube recorded for `containsSyntheticMedia` and the two languages. Checked on 2026-11-12 on the
  three newest uploads with the owner's read-only token: the languages come back (`en`/`en`), but
  `containsSyntheticMedia` is **absent**, although every upload sends `true` and the API's schema
  lists the field. So either the flag is not landing, or the API hides it from a read-only token;
  the API cannot tell which (review finding 11; open since 2026-06-09). The read-back stores what
  comes back and alerts only on an explicit `false`. Settling it is decision 18.9.

## 10. Part E: measuring

Views arrive in a two-day burst and stop: 79% of a Short's views within 24 hours, 92% within 48, 96%
within 72. The pipeline stores one public view count a day, so it cannot tell a viewer who leaves at
frame 1 from one who leaves at second 5, or an Indian viewer from anyone else. Twenty reels can
detect a threefold change in views about 75% of the time and a doubling only 31%.

### 10.1 What is recorded

- **The format, on every post** (`posts.format`): the narration language actually voiced, the visual
  source actually used, the number of video and still shots, the structure, and a format version
  (`2` for this design). Every comparison later depends on it.
- **Daily view snapshots,** as today. The view count at 72 hours is interpolated from the snapshots
  either side of it. (GitHub starts the daily run 5-8 hours late, so an hourly ladder of snapshots
  could not run as the audit proposed; it is not built.)
- **Retention and audience, from the YouTube Analytics API,** per Short once it is 7 days old: views,
  `engagedViews`, `averageViewDuration`, `averageViewPercentage`, subscribers gained, the share of
  views from India, the top countries, and views by traffic source. Plus a one-off baseline over the
  old Shorts (all countries, and India alone), so the first new reels have something to be compared
  with. Stored in `post_metrics` (section 13).
- **The token already works.** On 2026-11-12 the first query failed only because the YouTube
  Analytics API was not enabled on the OAuth client's Google Cloud project
  (`composed-maxim-498517-f0`); it was enabled that day (free), and today's refresh token then read
  views, engaged views, average percentage viewed and country without a new consent. No operator
  action is needed. If Google ever answers 403 for the scope, the pull logs it, stays idle, and asks
  the operator once to re-run `tools/get_youtube_token.py`.
- **One row per attempt** (`reel_attempts`): every `produce_one` call records its outcome (published,
  blocked, failed, out of time), the stage it ended at, the reason, the Higgsfield spend, and any
  downgrade (English narration, a fallback voice, still shots). Today failed attempts leave no record
  (an idea that died at captions exports as "rejected"), so the funnel cannot be measured.

### 10.2 The judging rule, fixed before the first new reel

Against the old 18 of 40 Shorts since 2026-07-27 that reached 100 views at 72 hours:

- Of the first 20 new-format reels, **15 or more** at 100+ views at 72 hours means pick-up improved;
  **3 or fewer** means it got worse; anything between is no conclusion. Each threshold is a
  difference at the 5% level from the old 18 of 40 (two-sided Fisher exact test, which allows for
  the old figure's own uncertainty: p = 0.03 and 0.025); 14 of 20 would be p = 0.10.
- **Which reels count:** posts from `WINNERS_SINCE` (the relaunch date) stamped format version 2,
  narrated in Hinglish, with at least half their shots video. Reels that fell back to English
  narration or to mostly stills are reported beside the verdict, not counted in the 20. A reel later
  removed from YouTube counts with its last snapshot at or before 72 hours, and is named.
- Any Short above 2,500 views (twice the channel's best) is a lead to study, not proof: one appears in
  29% of random draws from the old spread.
- Read the India share of views first: if most viewers are not in India, the stories are not reaching
  the audience they were chosen for, whatever the view count.
- The analytics job sends the verdict to Telegram when the twentieth new reel passes 72 hours.

## 11. Part F: picture and sound

Measured on the test renders (`verification/voice-visuals.md`).

### 11.1 Frame rate

`ai_video` reels are made at **24 fps end to end**, Kling's own rate: the assembly output, the Ken
Burns stills for this source, and the caption burn (its keyframe interval set to half the rate). No
clip is slowed or converted. Converting the clips to 30 fps made 20.0% of frames duplicates, slowing
them 30.2%, and the finished test reels carried 26-27%. Other sources stay at 30 fps.

### 11.2 The cut list

- **Hard cuts, no crossfades,** for `ai_video`.
- **Shots first, on the narration's pauses:** the same pauses the subtitles use (`silencedetect` on
  the trimmed narration). From the start of a shot, the shot ends at the latest pause that keeps it
  between 3.0 and 5.0 seconds (one clip, never slowed), or at 5.0 seconds when there is none. Today a
  cut falls on the clock, mid-sentence.
- **Then one reframe inside each longer shot:** a shot over 3.6 seconds is cut once, at the pause
  nearest its middle (or at the middle when no pause is within 0.6 s of it). The second part continues
  the clip's own time and punches in (about 1.15x, on the subject's centre), which reads as a new
  picture at no extra spend. On both test narrations this changed the picture every 2.2-2.4 seconds,
  the genre's rhythm.
- **No reprise at the end.** The loop back to frame 1 is a plain cut: the reprise and the
  reverse-play the audit proposed both replay the opening footage, and the loop jump measured 14.7
  against a median 2.0 between frames.
- One pure function in assembly makes the cut list and the shot count together, so sizing (6.3) and
  the render cannot disagree. `AI_VIDEO_CUTS=clip` gives one segment per shot instead (18.2).

### 11.3 Brightness

- **The vignette goes off** (`ENABLE_VIGNETTE=false`): with the grade it darkened the top of the
  frame by 48% and the bottom by 40%; switching it off alone recovers most of that.
- The planner's framing rule (6.5) asks for a large, centred, brightly lit subject; the still gate
  (11.6) checks exposure.

### 11.4 Sound

- The narration's head and tail are trimmed (7.5): speech started 0.29 s in, and the opening claim
  ended at 6.6-7.3 s.
- **The music bed comes up:** `MUSIC_LU_BELOW_VOICE` from 11 to 4. After the ducking's 13-14 LU, the
  bed then sits 17-18 LU under the voice instead of 24-25 (simulated on all four beds, matching the
  real mixes at -14.6 and -14.8 LUFS).
- **Cut stings go** (`ENABLE_SFX=false`): one click a reel at -19.8 dBFS, landing inside speech.
- The loudness chain stays as it is.

### 11.5 Text on screen

- **The banner** is the title (9.4), held until the first sentence ends (at least 1.8 s, at most 4.0
  s) instead of vanishing at 1.8 s, which was the biggest change between two frames in the reel.
- **The subtitles** (7.7) sit inside the vertical safe zone, clear of the banner and the action rail.
- **The source line** ("Source: <publisher>") shows with the first sentence, the claim it supports,
  and moves up from y 1480, which the Shorts interface covers, into the safe zone. The logo shrinks.
- **One key number a reel:** the writer names the script's key number; code checks that the exact
  figure is in the English script; it appears large in the upper middle, with a short scale-in, for
  the part of the narration that says it. The key-point text cards are off for the new format.
- **As built (stage 4b):** the safe box is Google's vertical overlay (x 48-888, y 288-1248). The
  subtitles' margins are 48/192/672; the banner is top-centred at y 300; the source line sits
  under the banner's real rows; the number is 150 px, top-anchored at y 760, scaling in from 70%
  over 0.18 s, shown 1.5-2.5 s from the moment it is said (the English burn finds it in its
  aligned words, the Hinglish burn in its English blocks); the logo is 96 px tall.

### 11.6 Automatic gates

Nothing looks at a reel before it is public, and the operator declined manual checks, so the checks
are automatic. FFmpeg and Tesseract only; no new Python dependency.

- **Stills:** Tesseract OCR (`--psm 11`, TSV output) on each still, read as drawn and as a
  grayscale copy at twice the size; any word of three or more letters read with confidence 70 or
  more means the still is redrawn once with a new seed. A mean brightness of the middle half under
  60 (of 255), or letterbox bars (the top and bottom sixteenths both darker than 16 and flatter
  than a standard deviation of 6), means the same. The redraw is used unless it fails more checks
  than the first; a second failure is logged. **Measured 2026-11-13** on the renders' six paid
  clips and 32 klein stills drawn for the purpose: FLUX writes gibberish, and Tesseract reads it at
  low confidence (the render's "TBEREOROIN" caption at 46 from the still, 90 from the 2x copy;
  real words at 92-96; clean stills' noise at up to 59). Read both ways, the rule caught 4 of the
  5 lettered frames, with 1 false alarm in 33 clean ones (a free redraw); the frame it missed was
  a dark laptop screen, which the planner's noun check (6.5) keeps out. One still of seven was
  letterboxed and dark (36); every clean frame measured 83 or brighter.
- **Clips:** a video stream at least 4.5 s long that covers its shot; no black stretch of 0.5 s
  or more (`blackdetect`) and no frozen stretch over 1.5 s (`freezedetect`; a freeze running to
  the end counts to the end); a failed clip becomes a still. All six paid clips passed.
- **The finished reel:** duration within 0.2 s of the narration, audio present, no black stretch over
  1.0 s and no frozen stretch over 2.0 s. A reel that fails is not uploaded; the attempt fails with
  the reason and the idea goes back to the digest. Every format is checked: the four test renders
  and the suite's real render of today's format pass. Black and frozen stretches refuse only an
  `ai_video` reel that has its shots: today's formats can hold a picture still (a Ken Burns move
  ends before its clip does, and a clip is replayed after a failed image fetch), so there they are
  logged (stage 4a's final review). A check that cannot run is skipped with a warning; only a
  reel that cannot be probed is refused for the check's own sake.
- `tesseract-ocr` joins the cached apt packages on CI (Ubuntu 24.04 ships 5.3.4) and is called as a
  binary. If it is missing, the text check is skipped with one warning.
- **Every FFmpeg call gets a timeout;** none has one today, so a stalled call waits for the job's kill.

## 12. Settings

All optional with defaults, added to `.env.example` and to both production workflows.

| Setting | Default | Meaning |
|---|---|---|
| `NARRATION_LANGUAGE` | `english` until relaunch | `hinglish` turns Part B on |
| `VISUAL_SOURCE` | repository variable, now `ai` | `ai_video` turns Part A on |
| `HF_API_KEY` | none (secret) | The Higgsfield console key |
| `AI_VIDEO_MODEL` | `kling-video/v2.5-turbo/standard/image-to-video` | Endpoint id |
| `AI_VIDEO_BUDGET_USD` | `1.10` | Most to spend on one reel; sets how many clips are bought (operator, 2026-11-12) |
| `AI_VIDEO_TIMEOUT_SECONDS` | `300` | The whole Higgsfield phase, quote to last download |
| `AI_VIDEO_GRACE_SECONDS` | `120` | Extra wait for jobs already running at the deadline |
| `AI_VIDEO_TAIL_SECONDS` | `240` | What a reel still needs after visuals |
| `AI_VIDEO_STYLE` | the look in 6.5 | The stills' style line |
| `AI_VIDEO_CUTS` | `pauses` | `clip` gives one segment per shot |
| `REEL_BUDGET_MINUTES` | `14` | Was 12 |
| `JOB_TIMEOUT_MINUTES` | `85` / `55` in the workflows | The Python step's limit; was the job's |
| `GEMINI_TTS_VOICE` | `Charon` | Was `Zubenelgenubi` |
| `GEMINI_TTS_MODEL` | `gemini-3.1-flash-tts-preview` | Chosen by the operator by ear on 2026-11-12 over both 3.8 models |
| `GOOGLE_TTS_VOICE` | `en-IN-Chirp3-HD-Charon` | The English Chirp voice (was Zubenelgenubi) |
| `GOOGLE_TTS_VOICE_HI` | `hi-IN-Chirp3-HD-Charon` | The Hindi Chirp voice, once one line passes its check |
| `HINGLISH_STRICT` | `true` | A meaning check that cannot run counts as a failure |
| `HINGLISH_MIN_SECONDS` / `HINGLISH_MAX_SECONDS` | `24` / `36` | Spoken length band |
| `SCRIPT_TARGET_SECONDS` / `SCRIPT_MAX_SECONDS` | `27` / `33` | Replace `SCRIPT_MAX_WORDS` |
| `ENABLE_HOOK_JUDGE` | `false` | Was `true` |
| `ENABLE_VIGNETTE` | `false` | Was `true` |
| `ENABLE_SFX` | `false` | Was `true` |
| `ENABLE_SEAMLESS_LOOP` | `false` for `ai_video` | Unchanged for other sources |
| `ENABLE_TEXT_CARDS` | `false` | The key number replaces the key-point cards |
| `MUSIC_LU_BELOW_VOICE` | `4` | Was 11 |
| `NEWS_POOL_SIZE` | `60` | Was 24, and now set in code |
| `NEWS_INDIA_QUERIES` | a short list (8.2) | Google News searches for Indian stakes |
| `DEMAND_CHANNELS` | the India report's sample | Comparable channels' upload feeds |
| `ELECTION_SILENCE` | empty | State and date pairs to avoid (8.7) |
| `WINNERS_SINCE` | unset, so the block is off | The relaunch date |
| `YOUTUBE_LANGUAGE` | retired | Text language is `en`; audio follows what was voiced |

## 13. Database changes

Run once in the Supabase SQL editor; every statement is safe to run twice. Added to docs/03.

```sql
-- Part A: the Higgsfield ledger. One row per job: the cost log, and the record that a shot is paid.
create table if not exists ai_video_jobs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  idea_id bigint not null references ideas (id),
  shot int not null,                        -- position in the reel, from 0
  endpoint text not null,
  idempotency_key text not null unique,
  request_id text unique,                   -- null until a submit is answered
  status text not null,                     -- reserved | submitted | completed | failed | nsfw
                                            -- | canceled | late | refused
  cost_usd numeric(10, 4) not null,         -- the quote; 0 once known not to be charged
  seconds numeric(8, 1),                    -- submit to finished
  result_url text,                          -- valid for 7 days
  settled_at timestamptz
);
create index if not exists ai_video_jobs_idea on ai_video_jobs (idea_id, shot);
create index if not exists ai_video_jobs_open on ai_video_jobs (status, created_at);
alter table ai_video_jobs enable row level security;

-- Parts B and D: what was spoken, and how the script was built.
alter table scripts add column if not exists spoken jsonb;     -- {"language": "hi"|"en",
                                                               --  "lines": [{"en","hi","said"}],
                                                               --  "renderer", "checker"}
alter table scripts add column if not exists structure text;   -- what-happened | number | belief
alter table scripts add column if not exists grounding jsonb;  -- citations, queries: draft and gate

-- Part C: selection. The category goes in the existing ideas.niche column.
alter table ideas add column if not exists demand jsonb;       -- the demand signals it matched
alter table ideas add column if not exists rank_score numeric; -- the score that ordered it

-- Part E: measuring.
alter table posts add column if not exists format jsonb;       -- {"version": 2, "language",
                                                               --  "visuals", "video_shots",
                                                               --  "shots", "structure"}
alter table posts add column if not exists youtube_readback jsonb; -- what YouTube recorded

create table if not exists post_metrics (
  id bigint generated always as identity primary key,
  post_id bigint not null references posts (id),
  pulled_at timestamptz not null default now(),
  window_days int not null,                 -- 7; the 72-hour view count comes from snapshots
  views int, engaged_views int,
  avg_view_seconds numeric, avg_view_pct numeric,
  subscribers_gained int,
  india_share numeric,                      -- share of views from IN
  countries jsonb,                          -- top countries with their views
  traffic jsonb,                            -- views by traffic source
  retention jsonb,                          -- [[elapsed ratio, audienceWatchRatio], ...]
  unique (post_id, window_days)
);
alter table post_metrics enable row level security;

create table if not exists reel_attempts (
  id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  idea_id bigint not null references ideas (id),
  script_id bigint references scripts (id),
  outcome text,                             -- published | blocked | failed | out-of-time
  stage text,                               -- script | factcheck | hinglish | voice | visuals
                                            -- | assembly | subtitles | upload
  reason text,
  spend_usd numeric(10, 4),                 -- Higgsfield spend in this attempt
  downgrades text[]                         -- english-narration | fallback-voice | still-shots
                                            -- | ai-path | stock-video
);
alter table reel_attempts enable row level security;
-- ideas.status gains the value 'expired' (no constraint to change).
```

**Without the SQL the pipeline runs as today** (rule 14, soft at runtime): no `ai_video_jobs` means
nothing is bought and the operator is told once a run; a write that names a missing column retries
once without the new fields and logs once a run; no `post_metrics` or `reel_attempts` means those
records are skipped.

## 14. Build order and rollout

Each stage is tested and merged on its own and is safe to ship before the next. Stages 2 and 3 sit
behind switches, so the format changes in one step at relaunch and the first 20 new reels are
comparable.

| Stage | Contents | Live when merged? |
|---|---|---|
| 0. Safety and measuring | The shared sentence splitter; the opening check (hedges kept); timeouts on every FFmpeg call; `posts.format`, `reel_attempts`, the Analytics pull and baseline (Part E); the upload read-back; audio language from what was voiced; "Published" sent per reel; the bot's argument fix (its deploy waits for the operator) | Yes |
| 1. Stories and script | Part C (pool, ages, India searches, demand feeds, rubric, stored category, mix, de-dup, approval) and Part D (brief, opening, structures, title, length, repair, fact-check, packaging) | Yes: English reels get the new selection and script |
| 2. Hinglish | Part B: `src/hinglish.py`, the Hindi voice chain, the trim, the English subtitles | Behind `NARRATION_LANGUAGE=hinglish` |
| 3. AI video | Part A: `src/higgsfield.py`, `src/ai_video.py`, the ledger, the sweep, the spend lines; `tools/verify_higgsfield.py` | Behind `VISUAL_SOURCE=ai_video` |
| 4. Picture and sound | Part F: 24 fps, the cut list, the gates, the number card, the loop join, music level | With stage 3 |
| Relaunch | The SQL, the secret and the variables (section 15); one real reel end to end; `WINNERS_SINCE` set | Operator go-ahead |

The voice deadline of 2026-11-17 needs no stage: the Developer API attempts fail and the same voice
answers from Vertex. Stage 2 drops the dead attempts so they stop costing a round trip.

## 15. One-time setup

Each step waits for the operator's go-ahead, as the working rules require:

1. Run the SQL in section 13 in Supabase (pasted by the operator; the build has no way to run it).
2. Add `HF_API_KEY` as a repository Actions secret, from the local `.env`, without printing it.
3. Spend one clip ($0.18) on `tools/verify_higgsfield.py`: two submits with one idempotency key
   (same `request_id`, one charge?) and a cancel of a queued job. The result goes into docs/04.
4. Deploy the bot (`vercel deploy --prod` from `telegram-bot/`, account `shaan-alpha`).
5. At relaunch, set the repository variables `NARRATION_LANGUAGE=hinglish`,
   `VISUAL_SOURCE=ai_video`, `GEMINI_TTS_VOICE=Charon` and `GOOGLE_TTS_VOICE` to the English Charon
   voice (`en-IN-Chirp3-HD-Charon`: it is the English fallback; the Hindi one,
   `hi-IN-Chirp3-HD-Charon`, is `GOOGLE_TTS_VOICE_HI`'s default, as section 12 says); set
   `WINNERS_SINCE` to that date. Before it, `production.FORMAT_VERSION` becomes 2 (10.2 counts
   version 2 posts): done on `feat/relaunch-prep`.
6. Optional, in YouTube Studio on a phone: Content > Automatic dubbing > "Publish manually" for the
   first 20 reels, so English dubs of Hinglish audio do not confuse the first measurements.
7. Keep the Higgsfield balance topped up. When it runs out, reels revert to stills and one alert is
   sent.

`VISUAL_SOURCE=ai` and `NARRATION_LANGUAGE=english` switch the new format off at once.

## 16. Docs to update

With the build (rule 1): `CLAUDE.md` (the goal, the cost target, rule 2's text, rules 11 and 13,
the current status, the voice), `STATUS.md`, `CHANGELOG.md` (release `v0.19.0`), `README.md`,
`.env.example`, `docs/01` (decisions 6 and 8 say "AI images, not generative video"), `docs/02`,
`docs/03` (the key, the SQL), `docs/04` (Higgsfield, Tesseract, the clips' licence basis), `docs/05`
(script voice, structures, the two-text lines), `docs/06`, `docs/07` (the diagram), `docs/08` (rules
for AI shots, the India rules, hashtags), `templates/template-N-news-impact.md`,
`routines/ideation.md`, and this design's handoff.

**Rule 2's new text** (review finding 10), proposed: "Higgsfield (Kling 2.5 Turbo image-to-video) is
an operator-approved billed service (2026-11-10). Each reel may spend up to $1.10 (operator,
2026-11-12): about $1.07 for a typical all-video reel, about $21 a month at 20 reels; the operator's
stated budget is $60-80 a month. There is no cap in code, by the
operator's choice: every job is reserved in `ai_video_jobs` before it is bought, and every dollar is
reported on Telegram with the month-to-date." The cost-target line in "What this project is" names
all three billed services and their figures.

## 17. Testing

- **Offline unit tests** for every new module: the Higgsfield client against a fake transport
  (submit, poll, complete, failed, nsfw, 403, 422, 429 with `Retry-After`, no answer then a repeat
  with the same key, timeout to `late`, cancel confirmed and unconfirmed, the key and its halves and a
  signed URL absent from every message); sizing against a table and against assembly's cut list; the
  planner's validation, name check and fallback; reserve-first and ledger reuse; the sweep; the
  no-key and no-table paths; the Hinglish checks (numbers, names, scripts, length) on pairs that pass
  and pairs that should fail; number-to-words; the meaning-check plumbing; subtitle timing against
  test 4's narration and its hand-placed boundaries (`hf_spike4_sentence_ends.json`); the opening
  check and the splitter on the 87 published scripts; the mix rule; the demand parsers on saved
  responses; the analytics pull on saved responses.
- **A conftest guard** blocks live Higgsfield calls in every test, as the existing guards do for the
  database, Telegram, the models and YouTube.
- **Existing tests** that assert the old voice, the sarcastic prompt, `#Shorts`, the tag list or the
  single language setting are updated with the behaviour, not deleted.
- **CI is the proof** (rule 15). Then the live checks in section 15 and one real reel, watched.

## 18. Decisions waiting for the operator

None blocks the build; each has the default stated.

1. **Length:** 25-35 seconds (default) or toward the leading channels' 60. Nothing shows either is
   better; 60 seconds of video shots costs about $2 a reel.
2. **Cut rhythm:** hard cuts on the narration's pauses, about every 2-3 seconds, inside the bought
   clips (default), or one cut per clip.
3. **Measuring:** no action needed; the API is enabled and the token works (10.1).
4. ~~**The goal**~~ **Decided 2026-11-14 (operator):** about 20 reels a month, one channel until
   its reach earns, then full power; no 4-5-a-day milestone now. CLAUDE.md says so.
5. **The channel:** keep it (default). Its 87 Shorts were watched mostly outside India.
6. **A one-off media lawyer's opinion** on a stock AI narrator as synthetic information, the
   news-publisher rules and the election silence period: recommended, not blocking.
7. **Automatic dubbing** for the first 20 reels: leave it (default) or set "Publish manually"
   (section 15, step 6).
8. ~~**The Gemini 3.8 voice.**~~ Decided 2026-11-12: today's model (sample A) over both 3.8 models.
9. **The disclosure flag** (9.9): the API does not show it on the channel's uploads. Either one look
   at any recent Short's "Altered content" setting in Studio, or a one-time re-consent giving the
   pipeline's token the full YouTube scope (`tools/get_youtube_token.py` with `youtube` added), which
   would also let the pipeline read the flag and unlist the two Shorts STATUS lists as never gated.
   Default: neither, and the description's disclosure line carries the disclosure.

## 19. Follow-ups, not in this build

1. Let the operator point the pipeline at a story (`/makeshort <topic>`).
2. A custom thumbnail per Short (`thumbnails.set` works for Shorts since 2026-11-03).
3. A scheduled Google Trends collector, if the other demand signals prove useful.
4. A reference still to anchor the look across a reel's shots.
5. A Hindi translated title alongside the English one.
6. Gemini 3's structured output with search for the grounded draft, if the grounding log shows it
   does not search.
7. A private publishing delay (`publishAt`) for a look before a reel goes public.
8. From the 2026-10-09 log: a hashed lock file made on CI; a model-liveness canary; an alert on the
   daily test run.

## 20. Left to the builder

Function and type names; how the cut list is threaded through assembly; the polling implementation;
the exact prompt wording within the rules above; the place-name list for the planner's name check;
the comparable channels' list (start from the India report's sample); exactly where the subtitles sit
inside the safe zone; the test layout.
