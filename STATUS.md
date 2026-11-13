# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP, live (goal: 4–5 captioned YouTube Shorts/day; about 0.7/day so far, ~81 public Shorts)
**Version:** 0.19.0 (2026-11-14, the AI-video format built; tagged when `feat/relaunch-prep` is
merged, with the operator's go-ahead). Before it, 0.18.0 (2026-09-04) + **untagged on `main`**: the 2026-09-13 fixes, the 2026-09-27/28 audit (PR #12), the 2026-09-29 follow-ups, the 2026-10-09 audit, the 2026-10-22 Claude scriptwriter (PR #13) and the apt cache + job clock (PR #14) (CHANGELOG `[Unreleased]`) · CI **741 pass, 5 skipped** (run 39793591290 on `main`; the 5 are opt-in live tests)
**2026-10-09:** production was **down 2026-10-01 → 10-09** (PyAV 19 broke captions). Fixed: the first run on the new code published 2 Shorts (`rJjqfdltLvg`, `KbWEI-G61dA`). The Vercel bot was **redeployed** the same day (`dpl_ExGu8QdF735Bk9kkQDJi353ZAWeK`, account shaan-alpha). See the log entry below.
**In progress, the new format:** AI-video shots, Hinglish narration with English subtitles, for Indian viewers. Research and a full reach audit done (2026-11-10); the audit checked and the design rewritten (2026-11-12); **stage 0 merged** (PR #17); **stage 1 (1a stories, 1b script and packaging) merged** (PR #18, 2026-11-12, CI 870 pass); **stage 2 (Hinglish) merged** (PR #19, 2026-11-13, CI 963 pass), behind `NARRATION_LANGUAGE`; **stage 3 (AI video) merged** (PRs #20, #21), behind `VISUAL_SOURCE=ai_video`; the test renders' fixes merged (PR #22, CI 1125 pass); **stage 4a (the picture gates) merged** (PR #23, 2026-11-14, CI 1171 pass); **stage 4b (the text on screen and the sound) merged** (PR #24, 2026-11-14, CI 1213 pass). Every build stage is merged; next is the relaunch, on `feat/relaunch-prep`. **Start at [docs/superpowers/2026-11-10-ai-video-reels-handoff.md](docs/superpowers/2026-11-10-ai-video-reels-handoff.md).** Everything below still describes what is live.
**Last updated:** 2026-11-13 · **Fact-check:** `FACTCHECK_STRICT=true`, **2 samples**, a repair pass, on `gemini-3.5-flash` → `3.5-flash-lite` (Vertex)
**Voice:** Gemini TTS `gemini-3.1-flash-tts-preview` · **Zubenelgenubi** ("Casual") · style prompt ON (operator, 2026-09-27) in labelled sections
  ↳ same-voice chain (since 2026-11-12): **Vertex 3.1 → Vertex 2.5 GA**, then Chirp → edge-tts → Kokoro (all male) · somber read for tragedies · whoosh removed
  ↳ the Developer API is no longer asked for 3.1 or the 2.5 preview (it shuts both down 2026-11-17); the operator kept 3.1 over both 3.8 models by ear on 2026-11-12
**Models:** script writer **`claude-opus-5-5`** (Anthropic API, effort low, $4/month cap, since 2026-10-22) · Vertex: text `gemini-3.8-flash` · grounding `gemini-3.5-flash-lite` → `3.5-flash` · fact-check `gemini-3.5-flash` → `3.5-flash-lite` · ideation research `gemini-3.5-flash-lite` → `3.5-flash` (prose). Groq `openai/gpt-oss-120b` picks stories and is the text failover. Nothing on Vertex uses `gemini-2.5-flash`, which Vertex retires 2026-10-20
**Trigger:** **on demand only** (`/makeshort` or the workflow button); the scheduled digests were removed 2026-09-29 (operator); nothing is produced without a tap
**Editorial policy:** **truth over neutrality** — verdicts allowed; `factcheck.verify()` blocks **fabrication**, waives imprecision (`FACTCHECK_SEVERITY`)
**Brand:** But It Matters · YouTube handle **@butitmatters** · Telegram bot **@ai_reel_factory_bot**

---

## Snapshot

| Area | State |
|------|-------|
| Production | ✅ Live, **on demand only**: about 81 public Shorts on **@butitmatters**, about 0.7 a day against the 4–5 goal. Down 2026-10-01 → 10-09 (PyAV 19), back since |
| Pipeline code ([src/](src/)) | ✅ Every module implemented and tested (table below); CI **741 pass, 5 skipped** |
| Design / docs | ✅ 8 docs in [docs/](docs/) · rules in [CLAUDE.md](CLAUDE.md) |
| GitHub Actions | `make-short` (the pipeline), `production` (manual-only), `tests` (push, PR, daily), `analytics` (daily), `verify-tts` / `verify-vertex` (manual); all on `ubuntu-24.04`, Python 3.12. 15 secrets, Pixabay and `ANTHROPIC_API_KEY` (2026-10-22) included (`CLAUDE_CODE_OAUTH_TOKEN` deliberately absent, rule 4). Repo variables: `FACTCHECK_STRICT=true`, `VISUAL_SOURCE=ai`, `YOUTUBE_PRIVACY=public`, `GOOGLE_TTS_VOICE` |
| Telegram bot ([telegram-bot/](telegram-bot/)) | ✅ Vercel project `telegram-bot`, team `shaan-alphas-projects`, account **shaan-alpha** (the operator has two Vercel accounts; deploy from this one). CLI-deployed, not git-connected: every bot change needs `vercel deploy --prod` from `telegram-bot/`. Last deploy 2026-10-09 |
| Google Cloud `but-it-matters-tts` (billed) | Vertex AI (keyless: Workload Identity Federation in CI, ADC locally) + Cloud Text-to-Speech (Chirp). ₹450/month budget with 50/90/100% alerts (alerts only, not a hard stop) |
| Supabase (free) | ✅ `ideas` · `scripts` · `posts` · `analytics` · `claude_spend` (the Anthropic budget ledger, 2026-10-22) (+ `hook_performance`, unused); RLS on; server-side `sb_secret_` key |
| Anthropic API (billed) | Claude writes the final script; $4/month cap enforced in code by `claude_spend`. No Console spend limit set yet |
| YouTube | ✅ **@butitmatters**, titled **But It Matters**. Token scopes `youtube.upload` + `youtube.readonly`; `yt-analytics.readonly` needs a re-auth |
| Script templates | Template N is the only one wired (embedded in `scriptwriter.py`); D, A, C are written but unused |
| Claude Routine ([routines/ideation.md](routines/ideation.md)) | Optional and **dormant**: it has never run in production, and `data/daily-ideas.json` is empty |
| Local dev | Windows 11; `.venv` on Python 3.13 (CI uses 3.12); FFmpeg 8.1.1 (winget `Gyan.FFmpeg`) |

## Module progress (Phase 1)

Numbers are the modules' own (docs/01 §5 and the module docstrings); rows follow the pipeline order.

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (`ideation_fallback.py`, `news.py`, `trends.py`) | ✅ The live engine (the file name predates it): Google News RSS (India front page + World, Business, Technology, Science; 24 stories) and Google Trends (IN) → Groq picks N distinct stories → Gemini researches them in prose with grounded search on Vertex (`IDEATION_MODEL`), each idea keeping its own story's citations → JSON ideas on `gemini-3.8-flash` (Groq failover). ≥ 2 live source links per idea (`MIN_SOURCES`), Google News search top-up, 10-day story dedup. A Claude Routine file would be read first; it is empty |
| 2 | Approval (`approval.py` + the Vercel bot) | ✅ Digest with ✅ Approve / ⏭️ Pass / ❌ Reject; the bot writes each tap to Supabase (webhook mode); at most 3 approvals a run (`APPROVAL_CAP`); deaths and serious harm flagged "Sensitive" |
| 3 | Scriptwriter (`scriptwriter.py`) | ✅ Template N: a grounded Gemini draft (`gemini-3.5-flash-lite` → `3.5-flash`), then **Claude** (`claude-opus-5-5`, effort low, ~$0.037) writes the final script from it, capped at $4/month by the `claude_spend` ledger (since 2026-10-22); without Claude the draft ships; ungrounded `gemini-3.8-flash` (Groq failover) last; a why-it-matters take; ≤ 80 words (LLM tighten pass, then a whole-sentence cut); hook punch-up except on somber stories; titles ≤ 70 chars; key-point cards; somber tone for deaths and serious harm |
| 11 | Fact-check gate (`factcheck.py`) | ✅ Every script, before voicing: `gemini-3.5-flash` → `3.5-flash-lite` on Vertex, grounded; 2 samples (either can block); blocks fabrication, waives imprecision (`FACTCHECK_SEVERITY=critical`); one repair pass; strict mode holds the reel if the checker cannot run. A blocked idea gets status `blocked` |
| 4 | Voice (`voice.py`) | ✅ Gemini TTS `gemini-3.1-flash-tts-preview`, voice Zubenelgenubi, labelled style prompt. Same voice: Vertex 3.1 → Vertex 2.5 GA (since 2026-11-12; the Developer API is used only where Vertex is not set up); then Chirp 3 HD `en-IN-Chirp3-HD-Zubenelgenubi` → edge-tts `en-IN-PrabhatNeural` → Kokoro `am_michael` (one male narrator throughout). Telegram alert when a reel leaves the channel voice; `posts.voice` records the engine |
| 5 | Visuals (`visuals.py`) | ✅ `VISUAL_SOURCE=ai`: Cloudflare FLUX.2 klein (768×1344, per-shot seeds, 4 shots at a time) → FLUX.1 schnell → a Pexels photo, each with Ken Burns motion; stock video (Pexels → Pixabay) if the image path fails. Stock is under the Pexels/Pixabay licences, not CC0 |
| 6 | Assembly (`assembly.py`, `audio_sfx.py`, `graphics.py`) | ✅ FFmpeg 1080×1920 H.264: crossfades, grade, vignette (grain off), one of four AI-generated music beds (Google Lyria 2, disclosed) with ducking, a click every 2nd cut, -14 LUFS, logo bug, seamless loop, CRF 20 / 8 Mbps cap, BT.709 |
| 7 | Captions (`subtitles.py`) | ✅ faster-whisper `base` times the words (audio decoded by FFmpeg; PyAV pinned to 18.1.0 and off this path); the text comes from the approved script; karaoke in 3-word groups, frame-1 hook, key-point cards, "Source: <publisher>" lower-third, Montserrat |
| 9 | Publish (`publish_youtube.py`) | ✅ `videos.insert` with `containsSyntheticMedia=true` + the disclosure line; public; token pre-flight before the digest; resumable upload with retries; idempotent (checks `posts`) |
| 10 | Analytics (`analytics.py`) | ✅ Daily `analytics.yml`: view snapshots; removed or taken-down Shorts reported on Telegram, then marked `removed`; winners and low performers feed ideation; keeps the scheduled workflows enabled |
| — | Orchestrator (`production.py`) | ✅ `python -m src.production make` (make-short): token pre-flight → leftover approvals released, stale pending ideas aged out → ideation → digest → wait for taps → each approved idea through the chain → "✅ Published <link>". Idempotent, fail-soft; a crash, timeout or cancellation reaches Telegram |
| — | `config.py` / `db.py` / `llm.py` | ✅ config fails loud on a missing secret; db: Supabase over HTTP/1.1 with a retrying transport; llm: Gemini (Vertex in CI) ↔ Groq failover, 120 s timeout |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

- **New format:** AI-video shots, Hinglish narration, English subtitles, Indian viewers. The
  audit is checked and the design rewritten (2026-11-12,
  [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](docs/superpowers/specs/2026-11-10-ai-video-reels-design.md));
  **stage 0 is merged** (PR #17, see the 2026-11-12 log); **stage 1 is merged** (PR #18, after a
  fresh final review and its fixes); **stage 2 (Hinglish) is merged** (PR #19, behind
  `NARRATION_LANGUAGE`). Stage 3 (AI video) came in two plans: **3a (the Higgsfield client,
  the ledger, the sweep) is merged** (PR #20) and **3b (the shots, the cut list, the wiring) is
  merged** (PR #21), behind `VISUAL_SOURCE=ai_video` (see the 2026-11-13 log). The test renders
  are done and their fixes merged (PR #22). Stage 4 comes in two plans: **4a, the picture gates,
  is merged** (PR #23; see the 2026-11-13 log); **4b** (the key-number card, the banner hold, the
  source line and logo, the music level, the vignette and the stings) **is merged** (PR #24;
  see the 2026-11-14 log). Next is the relaunch (design 14-15): `FORMAT_VERSION` 2 and the
  design's docs pass, then, with the operator's go-ahead, the repository variables and one real
  reel end to end. State and decisions are in
  [docs/superpowers/2026-11-10-ai-video-reels-handoff.md](docs/superpowers/2026-11-10-ai-video-reels-handoff.md).
- ~~**Operator, for stages 0-3:** run the new SQL at the end of docs/03 §4~~ Done 2026-11-13 at the
  operator's request, through the Supabase CLI (`supabase db query --linked`): every table and
  column exists, RLS is on, the pipeline's key reads them, and the advisors show nothing above
  info level.
- ~~**Operator, before the relaunch:** the `HF_API_KEY` secret and the live check~~ Both done
  2026-11-13 with the operator's go-ahead (design 15 steps 2-3; result in docs/04 and the log).
- ⚠️ **Operator** (details in the 2026-10-09 and 2026-09-27/28 log entries):
  - ~~before 2026-11-17: ear-test the 3.8 TTS models~~ Done 2026-11-12: the operator kept
    `gemini-3.1-flash-tts-preview` (Charon, Hinglish) over both 3.8 models, and the voice moved
    to Vertex the same day;
  - settle the two source questions under Open decisions;
  - unlist or delete the two public Shorts that never passed the gate, `xRUo6GxYwYo` and
    `NKPb-InUoJU` (the pipeline's YouTube token cannot edit videos);
  - review the other public Shorts the auditors flagged: `hYhYKlAWQv4` (idea 211, a claim the
    checker called contradicted shipped as "minor"), `9Nkp1i1GQl8` (idea 301), `d3kJpc0QCWg`
    (the claim the gate blocked on idea 314), and `bMc2Kq_7-wg` (2026-09-12, Houthi: its
    description cites unrelated stories and the screen says "Source: voanews.com");
  - in Studio: delete the 10 unlisted test uploads from 2026-06-09, and first confirm on
    `mT4k_iuAZ5s` or any recent Short that "Altered content" shows "Yes" (we send
    `containsSyntheticMedia=true`, but our scopes cannot read it back; open since 2026-06-09);
  - note the 9 Shorts found gone from YouTube on 2026-09-28: they were never reported (the
    alert had no Telegram secrets until 2026-10-09), and their IDs are in the 2026-10-09 log;
  - ~~re-run `tools/get_youtube_token.py`~~ Not needed: the YouTube Analytics API was only
    disabled on the OAuth client's project; enabled 2026-11-12, today's token reads retention.
- **Code, when there is time** (the 2026-10-09 log's "Not done here"): a hashed lock file for
  CI; a scheduled model-liveness canary; the lower findings listed there. (The 3.8 TTS
  migration is not needed: the operator kept 3.1, now on Vertex.)

### Operating model: on demand only (since 2026-09-29)
Start a run with `/makeshort [N]` in the Telegram bot (N ideas, 1–8, default 5; it waits 30 min)
or the `make-short` workflow's **Run workflow** button (`ideas` default 3, `wait_min` default 20).
The run (`python -m src.production make` on GitHub Actions, `ubuntu-24.04`, a 90-minute job, one
run at a time) checks the YouTube token, releases leftover approvals, ages out pending ideas older
than 24 h, tops the queue up to N ideas and sends the digest. Taps (✅ Approve / ⏭️ Pass /
❌ Reject, at most 3 approvals) reach Supabase through the Vercel bot. Each approved idea then
runs script → fact-check → voice → visuals → assembly → captions → YouTube, and Telegram gets
"✅ Published <link>". A crash, timeout or cancellation sends a Telegram alert. The PC can be
off. Two scheduled digests ran on 2026-09-28 and were removed the next day (GitHub started them
6.5–7 h late); `production.yml`, the old cron path, is manual-only.

### Go-live checklist (Phase-1 DoD) — closed
1. ✅ **End-to-end dry run (2026-06-09):** a real unlisted Short, `mT4k_iuAZ5s`; its test rows
   were removed from Supabase the same day. The Studio checks left are under Next actions.
2. ✅ **GitHub Actions secrets:** 14 set, Pixabay included; `CLAUDE_CODE_OAUTH_TOKEN`
   deliberately excluded (rule 4). Vertex AI needs none (keyless Workload Identity Federation).
3. ⏭️ **Claude Routine for ideation:** superseded. Ideation runs inside the pipeline (Gemini on
   Vertex + Groq); the Routine is optional and has never run.
4. ⏭️ **Enable the crons:** superseded by the on-demand decision of 2026-09-29;
   `production.yml`'s schedule stays commented out on purpose.
5. ✅ **v0.1.0** tagged 2026-06-09 (first cloud Shorts published). A 4–5-Short day has not
   happened yet: about 0.7 a day, at most 3 approvals a run (see Open decisions).
6. (Phase 3) Check `@butitmatters` on Instagram + TikTok before cross-posting.

## Open decisions

- **Cadence vs the goal:** about 0.7 Shorts a day against 4–5, with at most 3 approvals a run.
  Run more often, or restate the goal and the Phase-1 exit criteria for on-demand runs?
- **Sources:** should model-written source URLs count toward `MIN_SOURCES` (invented TOI / The
  Hindu links pass the liveness probe)? Does one outlet twice, or the subject's own site (idea
  475 cited three imf.org pages), count as two independent sources?
- **Ideation runner:** superseded. Ideation runs inside the pipeline (Gemini on Vertex + Groq)
  on every on-demand run. The Claude Routine stays optional and dormant; re-enabling it would
  first need `routines/ideation.md` brought up to the truth-first policy.

## Blockers

- _None._

---

## Log

### 2026-11-14 — The relaunch's preparation (on `feat/relaunch-prep`)

Stage 4b was **merged as PR #24** (merge b3f8aa1; CI 1213 pass). Every build stage is merged.
Before the relaunch's switches (design 14-15):
- **format version 2:** `production.FORMAT_VERSION` was still 1, while the judging rule (design
  10.2) counts posts stamped version 2, so it would have counted nothing. Every reel is stamped 2
  from this merge; the rule's Hinglish and video-share filters keep English reels out;
- **the docs pass** (design 16): CLAUDE.md (the goal of about 20 reels a month, design 18.4's
  default and the operator's own figure; the cost target with Higgsfield; rule 2's Higgsfield
  text; rules 11 and 13), README, docs/01-08 (docs/03 gains a Higgsfield section and the
  relaunch's variables; docs/08 the AI-shot and India rules), the template and the routine;
- **design 15, step 5, corrected:** `GOOGLE_TTS_VOICE` is the English fallback
  (`en-IN-Chirp3-HD-Charon`); the Hindi voice is `GOOGLE_TTS_VOICE_HI`'s default, as section 12
  and the code say;
- **v0.19.0** in the changelog, to be tagged at the merge.

**The relaunch, each step waiting for the operator** (docs/03 §9): the repository variables
`NARRATION_LANGUAGE=hinglish`, `VISUAL_SOURCE=ai_video`, `GEMINI_TTS_VOICE=Charon`,
`GOOGLE_TTS_VOICE=en-IN-Chirp3-HD-Charon` and `WINNERS_SINCE`; then one real reel end to end,
watched (public; about $1 of Higgsfield). Optional (design 15, step 6): YouTube Studio's automatic
dubbing set to "Publish manually" for the first 20 reels. Not built yet, and not needed until
the twentieth new reel is 72 hours old: the judging rule's Telegram verdict.

### 2026-11-14 — Stage 4b: the text on screen and the sound (merged as PR #24)

Plan `docs/superpowers/plans/2026-11-14-stage-4b-text-and-sound.md`, 5 tasks, test-first, built
inline. Design Part F's remaining items:
- **the sound:** no cut stings (`ENABLE_SFX=false`) and the music bed 4 LU under the voice, not 11
  (`MUSIC_LU_BELOW_VOICE=4`), in the code and in both workflows' fallbacks;
- **the look:** no vignette (`ENABLE_VIGNETTE=false`); the key-point cards are off
  (`ENABLE_TEXT_CARDS=false`): one key number replaces them;
- **the banner** (the title) holds until the first sentence ends, between 1.8 s and 4.0 s
  (`HOOK_MAX_SECONDS`): the English burn finds the end in its aligned words, the Hinglish burn
  in the same sentence times its subtitles use;
- **the source line** ("Source: <publisher>") shows with the first sentence, top-anchored under
  the banner's real height; at y 1480 the Shorts interface covered it;
- **the subtitles** sit inside Google's vertical safe box (x 48-888, bottom at y 1248); the logo
  is 96 px tall (was 150);
- **one key number:** the writer names it (`key_number`); code keeps it only when it is copied
  exactly from the narration, as a whole phrase ("2" never counts inside "2,000"), and checks it
  again after a fact-check repair. It shows large in the upper middle (150 px, a 0.18 s
  scale-in from 70%) from the moment it is said, for 1.5-2.5 s;
- `tools/try_ai_video.py --key-number` lets an older script show the card.

**The render** (script 441, the six paid clips reused: $0.00 of Higgsfield; Claude cents):
- banner to 4.0 s, the source line to the end of line 1 (past 5 s), subtitles inside the safe
  box, the smaller logo; the reel check passed;
- the log shows `sfx=no` and the bed's gain at +4.9 dB, 7 dB above what 11 LU gave; the
  quietest 5% of the mix rose from -21.9 to -19.7 LUFS while the median held (-14.7, -14.5);
- the number card, burned over the render as a sample (script 441 has no number): it scales in
  from 70% at 8.02 s, is full size by 8.4 s, and reads clearly over a busy picture;
- the still check worked inside a reel: shot 5's still measured just under 60 and was redrawn;
  the redraw was worse (fake lettering, darker, letterbox bars), so the first was kept;
- the fake caption and the laptop of code are still in the clips bought in render 1, before
  the gate: reused clips are shown as they are.

**Found by the render and fixed test-first:** the planner's prompt told it why the frame's top
and bottom stay calm ("a title and subtitles sit there"), and it wrote that into its stills
("room for the title and subtitles", "free of text"). The 4a lettering check therefore refused
nearly every plan, and FLUX may draw what it reads (render 1's fake caption sat exactly where
subtitles go). The reason is gone, the planner is told never to name text even to exclude it,
the retry says the same, and "display" left the word list (a live false alarm: "on display").
Three live plans afterwards: one clean at once, one fixed by its retry (a real "notebook"), one
flagged only for "display". Also: the darkness message shows the measured value ("59.6 < 60").

**Final review** (a fresh reviewer over `3f3c65c..e24097d`): no critical finding; the plan's five
review-focus cases hold. Fixed test-first:
- **the card could show over another number:** its moment was matched on digits alone, so "40%"
  showed while "40 districts" was said, and "14" at "1.4 billion". Figures are compared as written;
- **a key number could lose its unit or sign:** "2,000" passed for "Rs 2,000 crore" (off by ten
  million), "5" for "$5 billion", and a typographic minus was stripped by the font. A number next
  to a unit, a magnitude word, a currency or a minus is refused, and a card the renderer would
  change is not drawn;
- **a long number jumped from one row to two during its scale-in:** rows are broken in code (at
  most two of 12 characters) and libass's wrapping is off;
- **capitals changed units:** "5 m" (metres) read "5 M"; only words of 3+ letters are capitalised;
- **the fact-check checked cards no one sees** and not the key number that is shown; it now sees
  what is on screen.

**Decided (review finding 4): merging changes today's English reels at once.** They lose the
vignette, the stings and the key-point cards; their bed comes up 7 LU; the logo is smaller; the
banner holds for the first sentence; the source line moves under it; the karaoke moves 42 px left
and 32 px up into the safe box; and a key number appears when the writer names one. Design 12 makes
these global defaults, and the judging rule is not touched: its baseline is a fixed count (18 of
the 40 Shorts since 2026-07-27) and its cohort needs Hinglish, format version 2 and video shots, so
English reels made before the relaunch count in neither.

**For the relaunch** (found while checking that): `production.FORMAT_VERSION` is still 1, while the
judging rule counts posts stamped version 2, so it must become 2 with the relaunch; and the
rule's Telegram verdict (design 10.2) is not built yet.

**Deferred minors:** the source line has no upper bound (a one-sentence script keeps it up the
whole reel); PNG cards still start at `HOOK_SECONDS`; a shadowed variable in `_build_ass`'s card
loop; cards and a two-row number can overlap when cards are switched on; the writer is still asked
for key points; any phrase with a digit counts as a key number ("G20"); "display" left the
lettering list entirely; no test for a number said inside the first sentence or for the
first-sentence end on the ASR fallback.

Suite: **1213 passed, 5 skipped**; with every `.env` name blanked, the known NICHE artifact only.
**Merged as PR #24** (merge b3f8aa1, 2026-11-14) with the operator's go-ahead; CI 1213 passed.
Next: the relaunch.

### 2026-11-13 — Stage 4a: the picture gates (merged as PR #23 on 2026-11-14)

The test renders' fixes were **merged as PR #22** first (merge b6e6216, CI 1125 pass), with the
operator's go-ahead. Stage 4 is split like stage 3: **4a, the gates** (this entry; plan
`docs/superpowers/plans/2026-11-13-stage-4a-picture-gates.md`, 6 tasks, test-first, built
inline) and 4b, the text on screen and the sound.

**Calibrated before the plan, at $0:** the six paid clips of idea 561, re-downloaded from the
ledger, and 32 klein stills drawn for the purpose (8 planner-like prompts, 2 style lines, 2 seeds,
free tier), read by Tesseract 5.4:
- the design's rule (a word of 3+ letters at confidence 70+) missed FLUX's lettering: FLUX writes
  gibberish, and Tesseract reads it at low confidence (the render's "TBEREOROIN" caption at 46, a
  dark "Welcome" at 11; real words at 92-96; clean stills' noise at up to 59). Reading a
  grayscale 2x copy too lifted the caption to 90;
- **screens are the source:** every laptop prompt drew lettering (4 of 4), no other prompt did;
- one still of seven was letterboxed and dark (middle half 36); every clean frame was 83+;
- the style line ("cinematic ... film still") made no difference to captions or bars, so it
  stays;
- a vision model as the checker could not be compared: Gemini's Developer API answered 503, then
  429, on all 38 frames locally. It stays a follow-up.

**What a reel now does:**
- **each still is checked** (`gates.still_problems`, new module `src/gates.py`): a word of 3+
  letters at confidence 70+ read from the still or its 2x copy, a middle half darker than 60, or
  letterbox bars means one redraw with a new seed. The redraw is used unless it fails more
  checks; a redraw that cannot be drawn keeps the first. Every hit is logged;
- **the shot planner is sent back** for words that draw lettering or a screen (laptop, screen,
  phone, sign, chart and more), in the same one retry as the name check. It never costs a reel
  its clips: after the retry, the last plan that names no one is used;
- **each bought clip is checked** (`gates.clip_problems`): a readable video at least 4.5 s long
  that covers its shot, no black stretch of 0.5 s or more, no frozen stretch of 1.5 s or more (a
  freeze to the end counts). A failed clip becomes a still;
- **every finished reel, of any format, is checked before the upload** (`gates.reel_problems`):
  within 0.2 s of its narration, video and audio present, no black stretch of 1.0 s or more, no
  frozen stretch of 2.0 s or more. A failing reel is not uploaded: its attempt fails at stage
  `check` with the reason, and its idea goes back to the digest with an alert. Black and frozen
  stretches refuse only an AI-video reel that has its shots; in today's formats they are logged
  (see the final review). A check that cannot run is skipped with a warning; only a reel that
  cannot be probed is refused;
- **CI installs `tesseract-ocr`** with the cached apt packages (new key
  `apt-ubuntu-24.04-ffmpeg-espeak-ng-tesseract-v2`, so each workflow's first run refills it).
  Without a binary the text check is skipped with one warning.

**On real media** (Tesseract from the official installer, unpacked into a scratch folder: the
machine-wide install stopped at Windows' admin prompt): the stills, 4 of 5 lettered frames
caught and 1 of 33 clean ones flagged (a chip read as "Ait", a free redraw); the frame missed is
the dark laptop screen the noun check now keeps out. The six paid clips pass the clip check. The
four test renders, and the suite's real render of today's format (Kokoro, Pexels, FFmpeg), pass
the reel check.

**Final review** (a fresh reviewer over `b6e6216..1e7f6ef`): no critical finding; the five
review-focus cases hold. Three important findings, each fixed test-first:
- **the reel check could refuse a sound reel of today's format.** A Ken Burns move ends 4.0-4.4 s
  into its 7 s clip; after a failed image fetch a clip is replayed from 3.5 s, about 3 s with no
  motion, and a held Hinglish sentence does not break the freeze. Black and frozen stretches now
  refuse only an AI-video reel with its shots (there every clip passed its own check); elsewhere
  they are logged;
- **a Tesseract that runs but fails** (missing language data: exit 1, a bare header) made the
  text check a silent no-op; it now raises, and the skip is logged;
- **the 4.5 s clip floor broke the neighbour cover** (review I-3 of 3b): a still's Ken Burns clip
  is its shot plus 0.1 s, so cover is a length-only check again.

**Deferred minors:** a redraw tie goes to a schnell redraw over a klein first still; the redraw
comparison ignores the problems' kinds; the planner keeps the last name-free plan rather than the
one with fewer lettering words; the lettering list is broad (`tablet`, `title`, `sign`) and lacks
Indian-English `hoarding`, `mobile`, `cheque`; the reel's length is the container's, not the video
stream's; gate timeouts are not tied to the reel's deadline; gates calls assembly's private binary
helpers.

Tesseract is now installed on the dev machine too (`winget install UB-Mannheim.TesseractOCR`,
5.4.0, with the operator's admin approval), so the real-Tesseract test runs locally.
Suite: **1171 passed, 5 skipped**. **Merged as PR #23** (merge 3f3c65c, 2026-11-14) with the
operator's go-ahead; CI 1171 passed, 5 skipped (only the opt-in live tests), so the real-Tesseract
test (apt's 5.3.4) and the real-FFmpeg tests (apt's 6.1) ran and passed on Ubuntu. Next: 4b.

### 2026-11-13 — The first AI-video test renders (approved, nothing uploaded)

With the operator's go-ahead (`tools/try_ai_video.py`, script 441, idea 561, "Nvidia's Jensen
Huang and a Suspected Chinese Spy?"):

- **Bought:** 6 Kling clips at $0.1575, **$0.945**, every row `completed` in `ai_video_jobs`. Kling
  delivered what was measured on 11-10: 724x1268, 24 fps, 121 frames, 5.04 s.
- **The reel:** 31.9 s English narration, 8 shots (6 clips and 2 Ken Burns stills), 15 segments, a
  new picture about every 2.1 s; 1080x1920 at 24 fps, 767 frames, as rendered.
- **The tool crashed after buying,** printing the reel's line ("🎞️") to a cp1252 console, before
  it wrote the reel. The reel was finished from the paid files, at no new cost. Fixed and tested:
  the tool now writes UTF-8.
- **The Hinglish failed twice,** so the reel was narrated in English, as designed. The real
  renderings showed three causes, each fixed test-first:
  - the name check read "U.S." as two names, "U" and "S", so "US" failed and the retry message
    was unusable; an abbreviation is now one name, dots optional;
  - it matched names case-sensitively, so "NVIDIA" failed; it now checks the script, not the
    capitals;
  - told only about line 1, a retry sent back line 1 alone; it now asks for every line.
  - Not a bug: attempt 1 really did drop "A U.S. intelligence memo reportedly says", and the check
    was right to refuse it.
- **What the pictures need** (stage 4 next):
  - FLUX drew fake lettering into the first still ("TBEREOROIN"), the case the still gate
    (Tesseract, then a redraw) exists for;
  - the planner drew a laptop screen of fake code although its rules forbid screens.
  - The other shots were clean (a map, a chip, a question mark), and the 1.15x punch-in reads as a
    new picture.
- **Three more renders,** reusing the six paid clips at $0.00 (the reuse path worked live; Claude
  cost cents a render):
  - the second found Gemini answering the meaning check with 503 "high demand", and strict mode
    sent a rendering that had passed every code check to English. The meaning check now fails over
    to another provider independent of the renderer (Claude's lines: Gemini, then Groq);
  - the third found a contradiction in design 7.2: Hinglish line 1 had at most 12 words, and
    nothing could be dropped, yet 31 of the 40 newest English first sentences run over 12 words
    (median 17). The renderer cut a clause to comply. Saying all of it now comes first, and
    design 7.2 says so;
  - **the fourth is the target format:** Hinglish (Charon) passed every code check on its first
    attempt; Groq passed all 5 lines after Gemini's 503; 32.5 s, 5 of 7 shots video, English
    clause subtitles. It is in `test-videos/ai_video_try_441_hinglish.mp4`, sent to the operator.
- **Spent on the renders:** Higgsfield $0.945; Claude about $0.14 (eight Hinglish renderings, two
  of them diagnostic), inside its own budget. Suite after the fixes: **1125 passed, 5 skipped.**
- **Worth deciding:** a shorter English first sentence (12-15 words) would serve reach and the
  Hinglish line 1 alike. It changes design 9.2's opening rule, so it waits for the operator.

### 2026-11-13 — Stage 3b: AI-video reels behind VISUAL_SOURCE=ai_video (merged as PR #21)

Stage 3a was merged as PR #20. Stage 3b was built inline on `feat/stage-3b-ai-video-shots` from
its plan, `docs/superpowers/plans/2026-11-13-stage-3b-ai-video-shots.md` (8 tasks, each test-first;
the calls made are in the plan's ledger). With `VISUAL_SOURCE=ai_video` a reel now:

- **cuts on its narration** (`assembly.cut_list`): shots of 3-5 s ending on pauses, each longer one
  reframed once inside its clip (1.15x punch-in); on test 4's narration, 6 shots and a new picture
  every 2.4 s, as the design simulated;
- **plans its pictures** (`ai_video.plan_shots`): one model call, a still and a motion prompt per
  shot, the look added by code; a prompt naming anyone from the story is retried once, then the
  reel uses a fallback plan and buys nothing;
- **buys clips** (`ai_video.make_shots`): a klein still per shot; the quote (`/estimate`, $0.1575),
  then up to `floor(AI_VIDEO_BUDGET_USD / quote)` clips (6), shot 1 first, then the last; each row
  reserved before its still is uploaded; a submit with no answer repeated with the same key (the
  live check showed one job, one charge); refusals at $0, but a refusal after an unanswered submit
  keeps the quote; polling to a 300 s phase, 120 s more for running jobs, then `late`; a clip too
  short for its shot becomes a still; paid clips under 7 days old are reused;
- **stops buying for the run** on an empty balance, a refused key, a missing ledger table, or a
  reel that got no clip in time, each told once a run;
- **is rendered at 24 fps** with hard cuts and frame-exact trims (a real FFmpeg test: 216 frames
  for 9.0 s), stills as Ken Burns moves paced to their shot, and the caption burn at 24 fps;
- **is wired in production**: the subtitle burn is tried on a blank second before anything is
  bought; the latest finish (job time left minus 240 s) caps the phase; "Published" gains
  "🎞️ AI video: 5 of 6 shots, $0.79 ($… this month)"; a failure alert gains the spend; the attempt
  row gets the spend and the downgrades `ai-path` and `still-shots`; a reel that cannot have its
  shots takes today's `ai` path; the description says images when no clip was shown.

Also: paid clips keep their idea from the 24-hour age-out for 6 days; `REEL_BUDGET_MINUTES` is 14;
`JOB_TIMEOUT_MINUTES` is the Python step's limit (85 and 55), so the job clock can never run late.
Not in 3b (stage 4 next): the still, clip and reel gates (seams `_check_still`, `_check_clip`),
the key-number card, the banner hold, the source line and logo, the music level, the vignette and
the stings.

**Final review** (a fresh reviewer over `c3bf7c7..b2caf28`): no critical finding; the money
invariants hold (no job without a ledger row, no double charge, no charged job recorded at $0).
Four important findings and four minors re-graded by their effect, all fixed test-first:

- **Silent latches:** an empty balance found at a submit, or a missing table found at a reserve,
  stopped the buying with no Telegram message. Each is now told, once a run.
- **A hung Higgsfield:** with every status and cancel call hanging, the phase ran 225 s past
  its deadline, into the job's kill. A polling tick now stops at its end or when the service
  stops answering, cancels stop at the grace's end, an upload's timeout is what is left of the
  phase, and a download has a deadline over the whole file, not only a per-read timeout.
- **One still's failed render** threw the reel's paid clips away and lost its spend report. A
  render is retried once, then the shot shows the nearest shot's file that covers it; a reel
  that still cannot have its shots reports what it spent.
- **A submit blackout** (Higgsfield never answering) tripped no latch, so each reel of a run
  spent its whole phase on one shot. It now stops the run's buying.
- `Retry-After: 0` resubmitted in a tight loop (now at least a second); a stock-photo search
  could name someone from the story (now replaced); a rejected shot plan was silent (now told).

Also checked live, read-only: PostgREST accepts the age-out's `not.in` filter. **Deferred
minors:** paid clips are not reused while buying is stopped; clips that all fail their check trip
no latch (the Published line shows "0 of 6 shots, $0.95"); `AI_VIDEO_BUDGET_USD=inf` sends every
reel to the `ai` path; an `OSError` after a reserve escapes to the `ai` path with the row at its
quote; late shots' stills render inside the 240 s tail.

Suite: **1116 passed, 5 skipped**; with every `.env` name blanked, the known NICHE artifact only.

**Merged as PR #21** (merge 27b2f43; CI green on both pushes) with the operator's go-ahead, with
`tools/try_ai_video.py`: one test render through a reel's steps into `test-videos/`, never
uploaded, about $0.95 of clips. It refuses without `--yes-spend`, and without the
`ai_video_jobs` table before anything is spent. The operator agreed to run the SQL (docs/03 §4)
so the render can buy clips; checked after the merge, the table was still missing. At the
operator's request it was then run through the Supabase CLI, already logged in (`supabase db query
--linked -f`, docs/03 lines 255-323, linked from a scratch folder so the repo gained no files):
- all three tables (RLS on) and all seven columns exist;
- the pipeline's key has the same grants as on `claude_spend` and reads all three;
- the advisors show 15 notes, all info level: no policies on server-only tables (intended), two
  unindexed foreign keys on `reel_attempts` (a few dozen rows a month), and one new, still unused
  index.

### 2026-11-13 — Stage 3a: the Higgsfield client, the ledger and the sweep (merged as PR #20)

Stage 2 was merged as PR #19 (CI 963 pass). Stage 3a was built on `feat/stage-3-ai-video` from
its plan, `docs/superpowers/plans/2026-11-13-stage-3a-higgsfield-client-and-ledger.md`. This is
the plumbing that touches money. No reel buys anything yet: stage 3b wires the shots.

- **`src/higgsfield.py`**, the only code that talks to Higgsfield:
  - estimate, upload, submit, status, cancel and download, through one transport;
  - the key goes only to `api.higgsfield.ai`, never to the presigned upload or the clip download;
  - every message is redacted (the key, each half of it, any URL's query string), with no raw
    exception chained behind it;
  - each answer is sorted into funds (403), auth (401), refused (other 4xx), busy (429, with
    `Retry-After`) or unavailable (5xx, a timeout, no `request_id`);
  - a cancel counts only when Higgsfield confirms it.
- **The `ai_video_jobs` ledger** (`src/db.py`; SQL at the end of docs/03 §4):
  - a row is reserved, at the quote and with a fresh idempotency key, before a job is bought;
  - a missing table raises `LedgerUnavailable`, never an empty list that would read as "nothing
    bought".
- **The sweep** (`src/ai_video.py`), at the start of both entry points and after the last reel:
  - `submitted` and `late` jobs under 7 days old are settled;
  - a completed job keeps its cost and gains its URL; failed, nsfw or canceled cost 0;
  - it is fail-soft, and runs only with `HF_API_KEY` set.
- **The run's spend line** on Telegram, read from the ledger: clips, dollars, paid and not used,
  and the month to date. It is a report, not a cap.
- **A conftest guard:** no test can reach Higgsfield.
- **`tools/verify_higgsfield.py`**, the live check of design 15 step 3:
  - two submits with one key, then an immediate cancel, at most $0.18;
  - it is tested offline and has **not been run**: it waits for the operator.
- **Settings:** `HF_API_KEY` is in `.env.example` and in both workflows as a secret reference;
  until the secret exists it renders empty and nothing runs. The empty `HF_API_SECRET` line and
  its "paste both" comment were removed from the local `.env`, with no value printed.
- **docs/04** records Higgsfield and its licence basis (Terms §4.4: no claim on outputs, commercial
  use unrestricted; §5.5: disclose AI output, keep its provenance marks).

**Final review** (a fresh reviewer over `42e1beb..24b8f20`): no critical finding, 6 important and 9
minor; two minors re-graded important. All 7 are fixed test-first, in four commits:

- **The key in an error** (I-1): the detail was cut to 300 characters before redaction, so a key
  straddling the cut left a prefix of its secret half. It is now redacted, then cut.
- **"Paid, not used"** (I-2): the closing sweep turned a late clip that had since finished into
  `completed`, which reads as used. `ai_video.close_run` now reads the unused clips before the
  sweep, then sends the line.
- **An expired key** (I-3): a 403 marked `no-store` is a disabled or expired key (Higgsfield's
  header docs), so it counts as `auth`, not "out of funds".
- **An outage** (I-4): the sweep stopped only at a refused key; it now stops at the first failure of
  Higgsfield itself (auth, funds, busy, unavailable), so an outage costs one timeout, not 30 s per
  row twice a run. A row's own failure (404, a failed write) still leaves just that row (I-5's test).
- **The live tool** (M-1): a failed second submit left the first job running and unrecorded; it is
  now still cancelled or waited for, and its id is recorded first.
- **A malformed key** (M-2): a key holding a space or control character is refused before any header
  is built, since `requests` would quote it, escaped, where the redactor cannot find it.

**Ruled out of 3a:** I-6 (a refusal after an ambiguous submit may follow a charged job) is a 3b rule:
a row stays `reserved` at its quote after any ambiguous attempt. Whether a repeated key returns the
same `request_id`, and whether a cancel is free, only the live check can answer.

**Deferred minors:** an upload or download error carries 300 characters of the storage host's body
(an S3 error names its access key id); a truthy but malformed `request_id` is stored and refused on
every sweep; a `completed` status without `video.url` is settled with a null URL; a missing column
reads as a missing table; no spend line when a run crashes (the next month total has it); authed
calls follow redirects; `_FILE_TIMEOUT` is per read, not a total, so 3b's phase deadline cannot
rely on it (carried to 3b).

Suite after the fixes: **1028 passed, 5 skipped**.

**Operator go-ahead, the same day:** push and merge (PR #20), the `HF_API_KEY` repository secret
(piped from the local `.env`, never printed), and the live check (design 15, steps 2-3):

- **The first run bought nothing.** `/estimate` now answers Kling with a rate, not a total: "720p:
  $0.0315 per video second. Total price = selected rate × output duration". The client read only
  `usd`, so every reel would have refused to buy. It now takes the 720p rate (else the highest
  listed) times the job's `duration`: **$0.1575 a clip**, against $0.179 quoted on 11-10. The
  estimate needs an `image_url` in its body, but any URL will do.
- **The second run:** two submits with one idempotency key returned **the same `request_id`**: a
  repeat is one job and one charge, so 3b may retry a submit that got no answer.
- The job was `in_progress` a second or two after the submit, so the immediate cancel was refused
  (HTTP 400). The clip finished and downloaded without the key (1.66 MB). **Spent: one clip,
  $0.1575.** Whether cancelling a queued job is free stays unmeasured: jobs barely queue here.

### 2026-11-12 — The voice moves to Vertex now; the audit checked; the design rewritten

**Voice (live once merged).** The Developer API shuts down `gemini-3.1-flash-tts-preview` and
`gemini-2.5-flash-preview-tts` on 2026-11-17. The operator heard test 4's Hinglish lines in Charon
on 3.1 and on both 3.8 models (`test-videos/voice_A/B/C_*.mp3`) and chose 3.1 ("voice a is better
than others"), then asked for the change "now". So wherever Vertex is set up (both production
workflows), those two models are no longer asked of the Developer API: the channel voice comes from
Vertex 3.1, then Vertex's 2.5 GA model, then Chirp (`voice._DEV_TTS_RETIRING`). Billed on Vertex at
cents a reel, inside the Google Cloud cap. `tools/verify_gemini_tts.py` skips the Developer API for
those models. The live voice stays Zubenelgenubi until the new format launches with Charon.

**YouTube Analytics.** The first query failed with `accessNotConfigured`: the API was disabled on
the OAuth client's Google Cloud project (`composed-maxim-498517-f0`). Enabled (free); today's
refresh token then read retention and country with no new consent. Lifetime baseline: 16,048 views,
44% engaged, 71% of each Short watched on average; **39% of views from the US, 5.2% from India**;
86% from the Shorts feed. The old audience was not Indian.

**The audit, checked.** Four second reviewers checked all 88 findings against the code and data
(`research_notes/Channel audit 2026-11-10/verification/`): none was wrong outright, many details
changed (for example, the fallback voices fail silently on Hinglish; the judging rule's false-alarm
rate is about 5%, not 2%; titles of 7 words or fewer mattered even when the banner fitted).

**The design, rewritten** on the checked audit, the India research and the review's 21 confirmed
findings: [docs/superpowers/specs/2026-11-10-ai-video-reels-design.md](docs/superpowers/specs/2026-11-10-ai-video-reels-design.md).
A fresh builder read it; the operator then chose **up to $1.10 a reel** so a typical reel is video
throughout (6 clips). The disclosure flag does not come back from the API (design 9.9, 18.9).

**Stage 0 built** (branch `feat/stage-0-safety-measuring`,
[plan](docs/superpowers/plans/2026-11-12-stage-0-safety-and-measuring.md)), English reels unchanged
in look and sound:
- one sentence splitter (`src/text.py`) for the scriptwriter, voice and subtitles: "U.S.",
  decimals and "..." no longer end a sentence; the Hindi full stop does;
- the opening check on every script (wind-ups rewritten once or cut; hedges kept);
- a timeout on every FFmpeg call;
- each post stamped with its format (`posts.format`), one `reel_attempts` row per attempt with the
  stage it ended at, "✅ Published" sent as each reel goes live (from both entry points);
- the upload declares audio by what was voiced and stores YouTube's read-back;
- the analytics job pulls each Short's first week from the Analytics API (engaged views, average
  percentage viewed, India share, traffic, the retention curve), backfilling the old Shorts as the
  baseline; checked live on one Short;
- the bot reads the leading number of `/makeshort`.
A fresh final review found 5 issues worth fixing (the wind-up cut could garble an opening; a sentence ending on "U.S." merged with the next; 75 old posts lacked a publish date for the metrics; the render timeout outlasted a reel's budget; the punch-up skipped the opening check), plus an India share of 0 for withheld countries; all fixed test-first. 786 pass, 5 skipped (CI run 43196062166 on the PR). **Merged as PR #17** and the bot
redeployed the same day (`dpl_ABnQptCFzrEPdKBxQtXm3satobmb`, account shaan-alpha). **Waiting for
the operator:** the SQL at the end of docs/03 §4 (the code runs without it, skipping those records).

**Stage 1a built (stories for Indian viewers)** on branch `feat/stage-1-stories-script`
([plan](docs/superpowers/plans/2026-11-12-stage-1a-stories-for-indian-viewers.md)): a 60-story pool with each
story's age and Google News searches for an Indian stake (puzzle items dropped); two free demand
signals in `src/demand.py`, Wikipedia's India list (yesterday's views over the article's own week,
checked live: Jensen Huang 42x, Nvidia 13.6x) and comparable Hindi channels' Shorts pacing ahead of
their norm; both ideation prompts name the Indian viewer and the rubric, with no science quota;
each idea stores its category (`ideas.niche`), the score that ranked it and the signals it matched;
the topic mix is enforced in code (one india-politics idea, two per category, one somber story);
de-duplication runs before research, ignores "vs" and template words, and lets a sourced
follow-up through; untapped ideas end `expired`, not banned; election matter is dropped inside an
`ELECTION_SILENCE` window. The winners block is off until `WINNERS_SINCE` is set. 811 pass,
5 skipped. SQL for it is at the end of docs/03 §4 (two `ideas` columns; the code runs without them).

**Stage 1b built (script and packaging)** on the same branch
([plan](docs/superpowers/plans/2026-11-12-stage-1b-script-and-packaging.md)):
- the writer's brief: a plain explainer for Indian viewers (the sarcastic voice retired),
  sentence one with the Indian stake, a payoff that says what changes for a person in India, no
  phrases to copy; the English narrator prompt is test 3's, with a neutral Indian English accent;
- three structures (what happened, the number, the belief), chosen by a hash of the idea id,
  somber stories always the first, stored on the script row;
- one title of at most 7 words and 44 characters (also the banner): one model shortening, then a
  word cut; a reply without a title uses the idea's under the same limits;
- length in seconds (27 s target, 33 s cap, 2.2 words a second): optional sentences the writer
  marks go first, never sentence one or the payoff it marks (both copied as text and found by
  their words), which also places
  the `[serious]` tag; the tighten rewrite and the hook judge are off (code and both workflows);
- the repair may fix the title, the re-check sees it, and every model rewrite (repair, opening,
  hook judge) is refused if it adds a number or a name;
- the gate thinks at the model's default (32,768 output tokens after the review; roughly two cents
  a reel), an
  unsourced forecast for India blocks like unsupported blame, and the draft's and the gate's
  citation counts are stored (`scripts.grounding`); Claude hears "the draft searched" only when
  it has citations;
- the description: publisher names with their links, the disclosure line by visual source (an
  AI-video line added), a one-line footer, at most three hashtags ending `#ButItMatters`, no
  `#Shorts`; tags: the writer's six plus the brand; category 28 for science, space and tech.
852 pass, 5 skipped; with every `.env` key blanked, 841 pass and only the known `NICHE` artifact
fails. SQL: two `scripts` columns at the end of docs/03 §4 (the code runs without them).

**Stage 2 built (Hinglish narration, English subtitles)** on `feat/stage-2-hinglish`, behind
`NARRATION_LANGUAGE=hinglish` ([plan](docs/superpowers/plans/2026-11-12-stage-2-hinglish.md)); with the
default `english` nothing changes:
- `src/hinglish.py`:
  - the fact-checked English script becomes numbered two-text lines, rendered by Claude
    (structured output, the refusal fallback on, purpose `hinglish` in the spend ledger), then
    Gemini, then Groq;
  - code checks the lines: count, numbers kept as digits and no Hindi number word, names in Latin,
    scripts, and a spoken length of 24-36 s at 2.9 words a second;
  - a model from another provider checks the meaning;
  - one retry, then English;
  - code reads the digits out as English words for the voice.
- `src/voice.py`: Devanagari text goes only to Gemini (test 4's style prompt) and Chirp's Hindi Charon,
  never edge-tts or Kokoro. Each render is trimmed and must last 0.75-1.30 times the English
  script's length. The Developer API's retiring models are never asked from 2026-11-17. The code's
  voices are now Charon; the workflows keep Zubenelgenubi until the relaunch.
- `src/subtitles.py`: no speech recognition on Hinglish reels. Sentence ends are assigned to the
  narration's pauses all together (on test 4: within 0.02 s of the hand-placed ends). The
  renderer's parts become blocks in spoken order, else the whole sentence; white, at most two rows.
- `src/production.py`: the stage `hinglish`, audio language `hi`, `scripts.spoken`; any failure
  narrates in English, records `english-narration` and tells the operator.
- **Live checks:**
  - Chirp's Hindi Charon read test 4's narration in 23.56 s against an expected 26.82 s (ratio
    0.88), so it joined the chain.
  - One end-to-end run with no upload: Claude's first rendering used "दो" for "two", and the check
    and retry fixed it. Gemini passed the meaning. The voice took 27.86 s (ratio 1.04), and there
    were 12 subtitle blocks. About $0.10.
- **SQL:** `scripts.spoken` (end of docs/03 §4).
- **Final review of stage 2** by a fresh reviewer found no critical issue and 5 important ones,
  all fixed test-first:
  - the voice tests would have turned the daily CI red on 2026-11-17 by the date alone;
  - subtitle parts could drop words ("did not ban" shown as "ban");
  - a blank Hinglish line passed the checks;
  - line numbers given as text blanked the meaning check;
  - rupee figures with compound scales were garbled.
  Five minor ones were fixed too:
  - "Rs", "5G", "10x", "21वीं", decades and times read wrongly;
  - "°" and "+" were refused;
  - a verdict of "true" as text failed;
  - a sentence end with no pause drifted 2.5 s;
  - a pause-reading timeout could lose the reel.

  963 pass, 5 skipped; with `.env` blanked only the `NICHE` artifact fails. Deferred minors are
  in the handoff.

**Final review of stage 1 (1a and 1b)** by a fresh reviewer: no critical issue, 8 important, all
fixed test-first:
- an unsourced forecast for India no longer slips through the "could not confirm" waiver (rule 6
  updated);
- the gate's budget at default thinking is 32,768 tokens, and an unreadable reply is asked again
  at minimal thinking. Measured on two real scripts (441, 436): about 2,800-3,100 thinking tokens,
  finish STOP, both verdicts parsed; roughly two cents a reel;
- the writer copies its payoff and optional sentences as text, found by their words: it counts
  sentences its own way, so indices landed on the wrong sentence;
- the repair keeps a payoff (or marks its rewritten one) and may fix the description and cards,
  which the re-check, the stored caption and the upload then use;
- a follow-up returns only after a published story;
- "India" no longer makes two stories one;
- the election window covers polling day and the two days before, in Indian dates;
- top-up ideas get their story's category.
870 pass, 5 skipped; with `.env` blanked only the `NICHE` artifact fails. The repository variables
`ENABLE_HOOK_JUDGE`, `ENABLE_SCRIPT_TIGHTEN`, `SCRIPT_MAX_WORDS` and `VOICE_STYLE_PROMPT` are not
set, so the new defaults apply. Deferred minors are listed in the handoff.

### 2026-11-10 — A new format chosen; design, research and a reach audit in progress (no code changed)

The operator compared four test videos and chose the direction for every reel from now on.
Nothing under `src/`, `tests/` or `.github/` has changed and nothing is committed. The full
state, file map and next steps are in
[docs/superpowers/2026-11-10-ai-video-reels-handoff.md](docs/superpowers/2026-11-10-ai-video-reels-handoff.md).

**Decided by the operator**

- Visuals: the pipeline's FLUX stills, each animated into a 5-second clip by Kling 2.5 Turbo on
  **Higgsfield** (a new, approved billed service). About $1 a reel, about 20 reels a month,
  $60-80 a month at most. **No spend cap in code**; costs are to be logged.
- Narration in **Hinglish**, an informative male voice (Gemini TTS `Charon` in the tests);
  subtitles stay in English. Audience: Indian viewers.
- Topics: trending, high-impact stories from anywhere, not mainly politics.
- No watermark and no on-screen AI label; the disclosure line stays in the description. The
  corner logo and music beds stay.
- A full audit of the pipeline and its prompts for watchability and reach.

**Measured**

- Kling 2.5 Turbo Standard image-to-video: $0.179 per 5 s clip, about 100 s to generate. A
  four-clip, 26.7 s test reel cost $0.72. Lip-synced presenter tests cost about $2.50 each and
  were dropped. The four tests used about $5.78 of Higgsfield balance.
- The channel: 87 live Shorts, about 16,000 views in total, **median 44 views**, best 1,256.

**Written so far**

- Design, first draft: `docs/superpowers/specs/2026-11-10-ai-video-reels-design.md` (it
  predates the Hinglish and India decisions and is to be rewritten).
- Research with sources: `docs/superpowers/specs/2026-11-10-ai-video-reels-research.md`.
- A design review confirmed 21 issues to fix before building; they are listed in the handoff.
- India research: five notes and one report, `reports/Hinglish Shorts reach in India.md`.
- A full audit in eight lenses (data, ideation, script, voice and audio, visuals and edit,
  packaging, throughput, prompts): 88 findings, all in
  `research_notes/Channel audit 2026-11-10/FINDINGS.md`, with the eight reports beside it.
  The findings have not been independently verified.
- Raw notes, the channel data export, test scripts and the test videos are under
  `research_notes/`, `reports/` and `test-videos/`, kept out of git on this machine.

**What the research and audit say, in short** (detail and evidence grades in the handoff):

- The story and its first sentence decide reach. Length, pace and title tricks did not
  separate leading Hinglish channels' hits from their ordinary Shorts.
- The pipeline cannot see why viewers leave: it stores one public view count a day. Reading
  retention and viewer country needs the `yt-analytics.readonly` scope (the existing operator
  item: re-run `tools/get_youtube_token.py`).
- Hinglish narration breaks the caption step as built (it would burn invented English with no
  error) and five other English-only assumptions, including the fallback voices and the
  language declared to YouTube.
- Scripts that opened on a wind-up word were picked up 9 times in 41 against 21 in 46 for
  scripts that start on the subject; the scriptwriter was adding the wind-up.
- The headline pool cannot supply enough science and technology stories, and the "winning
  titles" feedback would steer the new format back to the old one.
- India's rules in force since 2026-02-20 put AI labelling on platforms; the uploader declares.
  No burned-in label is required. A draft that would require one had not been adopted as far
  as the research found.
- The 2026-11-17 voice deadline now also matters for the new format: Gemini 3.8 TTS takes a
  different request, and the backup voices as configured cannot read Hinglish.

**Next (when the operator says to continue):** check the audit's main claims, rewrite the
design once, write the build plan, then build in stages. **Blockers:** none. The one-time setup
(the `HF_API_KEY` secret, new SQL in Supabase, repository variables) waits for the build and
the operator's go-ahead. Decisions waiting for the operator are listed in the handoff, section 6c.

### 2026-10-22 — A crawling Ubuntu mirror held `/makeshort 1` in apt for 16 minutes

Operator: `/makeshort 1` had run 12 minutes with nothing on Telegram. Run 39785910849.

**Found**
- The run never reached Python. `apt-get update` was fine (5.8 MB in 1 s), but the 104 packages
  for `ffmpeg espeak-ng` (99.2 MB) came from `azure.archive.ubuntu.com` at ~60 KB/s: 63 of 104
  after 16 minutes (`libflite1`, 13.6 MB, took 3.5 min). The step normally takes 20–35 s. GitHub
  reported no incident. Cancelled at 16 min, before any Supabase write or digest; the
  workflow's own "run stopped" message went to Telegram.
- **A latent kill risk behind it.** `production._seconds_left()` assumed 5 minutes of setup
  (`JOB_SETUP_MINUTES`) and started its clock at import. Had apt finished at ~30 min, the
  guard would have believed it had ~25 minutes more than it did and could start a reel that the
  90-minute kill cuts mid-chain: the idea stranded at `approved`, or a kill between upload and
  `insert_post` that a rerun publishes twice.

**Done** (PR #14, merged as `c388ebc`; CI **741 pass, 5 skipped** on the branch, the PR and `main`)
- The job's first step writes `JOB_STARTED_AT` (epoch seconds) to `$GITHUB_ENV` in
  `make-short.yml` and `production.yml`; `_seconds_left()` counts from it, and falls back to
  `JOB_SETUP_MINUTES` without it. Test watched failing first (85 min claimed, 60 real).
- The .debs are cached (`~/apt-archives`, key `apt-ubuntu-24.04-ffmpeg-espeak-ng-v1`) in
  `make-short`, `production` and `tests`: update the index, copy the cached .debs into apt's
  archive, `--download-only` (fetches only what changed), copy back, install. The order also
  survives an image that deletes .debs after `update` or after `dpkg`. `tests` runs daily on
  `main`, which keeps the shared cache from its 7-day expiry.

**Proven on runners**
- Branch, cold (run 39789743167): install **760 s**, the mirror still crawling; cache saved, 94.5 MB.
- Branch, warm (run 39792458582), the same hour: restored, install **15 s**, "Need to get 0 B/99.2 MB".
- `main`: the merge's push run (39793591290) found no cache and saved it at 14:13:51; by then the
  mirror had recovered (99 MB in ~5 s). The run status API showed it "queued" minutes after it
  had finished, which briefly made that cache look unexplained; the run's own log settles it.
- The re-run of the Short (make-short 39793617178) started before that save, so it was cold too
  (install 25 s on the recovered mirror). Its env carried `JOB_STARTED_AT: 1792678322` (14:12:02
  UTC, the job's start). Its post-step save warned "another job may be creating this cache":
  harmless, `main` already had the entry.

**The Short, and the first live Claude script** (idea 548, https://www.youtube.com/shorts/YAIDWDKgN_A)
- Setup 54 s · ideation to digest 30 s · operator's tap 12.4 min · grounded draft + Claude 18 s
  (`claude-opus-5-5`, low: **$0.0393**, $0.22 of $4.00 this month) · fact-check 7 s · voice 15 s
  (first link, Developer-API 3.1) · visuals 83 s (12 AI clips) · render + captions 76 s · upload
  2.5 s. **Tap to live: 3 min 24 s.** Nothing in the pipeline itself is a bottleneck.
- The gate passed (6 claims) and waived 2 issues, both samples agreeing: the script says "a
  missile strike" on King Fahd International Airport, but authorities have not said missile or
  drone (four drones were intercepted over the Eastern Province that night). Imprecision under
  the 2026-08-07 policy, so it shipped; flagged to the operator.
- `gemini-3.8-flash` 400s once per run on MINIMAL thinking, then uses LOW (`llm._generate_content`).
  By design (keyed on the error, not a version table); costs ~1 s. Left as is.

**Limits**
- A run that finds no cache while the mirror crawls is still slow; the daily `tests` run keeps
  the cache inside its 7-day expiry, so that should now be rare.
- Bump the key's `-v1` if the runner image moves off 24.04 or the package set changes.

### 2026-10-22 — Claude writes every script (Anthropic API, $4/month cap)

Operator: remove the Claude OAuth token, use an Anthropic API key, and have Claude work on every
reel with at most $4 a month of Anthropic spend.

**Done**
- `CLAUDE_CODE_OAUTH_TOKEN` is gone from the local `.env`; `ANTHROPIC_API_KEY` replaces it (the
  key starts `sk-ant-usr`, an unfamiliar prefix, and the API accepts it: `models.list` and real
  calls work). The old token stays valid until revoked from the operator's Claude account.
- **Flow** (`scriptwriter._generate_script_json`): Gemini's grounded write is now a draft. Claude
  rewrites it into the final script with the draft as its only fact base ("add no facts"), and
  the fact-check gate then checks Claude's script as before. Fallbacks: no Claude → the grounded
  draft ships; no draft → Claude writes from the idea alone; neither → ungrounded Gemini → Groq.
  The hook punch-up, the tighten pass and the gate are unchanged.
- **Budget** (`llm.generate_claude`): a new Supabase table, `claude_spend` (created on the live
  project through the Supabase CLI; SQL in docs/03 §4). Reserve, check, call, settle: the call's
  worst case (max_tokens 8k/12k/16k by effort) is inserted first, the month's sum is read with it
  included, and over `ANTHROPIC_MONTHLY_BUDGET_USD` (4) the reservation is dropped and nothing is
  sent. After the reply the row is settled to the real cost. A timeout or lost connection keeps
  the worst case (it may have been billed); an error status releases it (it was not). The SDK's
  retries are off, since they retried timeouts; 429/5xx get one retry of our own. An unusable
  ledger refuses the call. Prices are a table in `llm.py`; an unknown model is costed at the top
  tier. Server-side refusal fallbacks are deliberately off: a refusal falls back to the grounded
  draft, and another model's price would escape the guard.
- **Audit** (code-review skill, then each finding checked, test first): Claude could add a fact
  from memory that the gate waives as "couldn't confirm", so `scriptwriter._added_facts` now drops
  a Claude script with any number (digits or spelled) or proper name absent from the draft and the
  idea, and the draft ships; tested on Claude's three real rewrites, which pass. No grounded
  draft, no Claude call. Repeating Claude problems (no key, bad `ANTHROPIC_EFFORT`, unusable
  ledger, spent month, a 401/403/400/404) reach Telegram once a run (`production._report_claude`)
  instead of being logged and forgotten; `write_script` returns `writer` and `claude_issue`.
  Not changed: the model is read at import, as Gemini's and Groq's are; the concurrency finding
  is covered by the reservation (both workflows already share the `reel-pipeline` group).
- **edge-tts hang, pre-existing** (systematic debugging): the full local suite never finished.
  `test_live_edge_tts` hung because Microsoft answers edge-tts 7.2.8 with a 403, and edge-tts's
  `stream_sync()` waits forever when its stream raises (still so in 7.3.1). In production that
  would hang a reel reaching the third voice link until the job's limit, never trying Kokoro.
  `voice._stream_chunks` now runs the stream itself with a 120 s ceiling so the error surfaces;
  `edge-tts==7.3.1` (2026-10-13) synthesizes again (measured: 30 audio chunks in 1.5 s).
  **The daily `tests` workflow has been dead since 2026-10-14**: all 8 scheduled runs were
  cancelled at the job's 25-minute limit, the log going silent after the 82% mark, where
  `test_live_edge_tts` sits. No `make-short` run since 2026-10-13, so production never hit it.
- **Tests:** locally **739 pass, 5 skipped** (the 5 opt-in live tests) in 102 s; 50 new across
  `tests/test_claude.py`, `test_production.py` and `test_voice.py`. CI: 740 pass, 5 skipped.
- **Measured** on the real Template N prompt (~2,870 input tokens): Opus 5.5 at low effort
  $0.037 (14 s), at medium $0.066 (25 s); Sonnet 5.5 at low $0.011 (5 s, but 91 words, over the
  80-word cap). Default: `claude-opus-5-5`, effort `low`, so $4 is about 108 scripts a month
  against today's ~21. The live end-to-end call through the new code cost $0.032 and was written
  to the ledger, and a live run of `scriptwriter._claude_write` after the audit fixes ($0.032)
  reserved, settled and passed the fact check. Spend so far: $0.177 (five rows, ids 1-5).
- `anthropic==1.12.1` pinned (2.0.0 shipped the day before; 1.12.1 is two weeks old). The
  `ANTHROPIC_API_KEY` Actions secret is set (15 secrets); both workflows pass it plus
  `ANTHROPIC_MODEL` / `ANTHROPIC_EFFORT` / `ANTHROPIC_MONTHLY_BUDGET_USD` / `ENABLE_CLAUDE_SCRIPT`
  (repo variables, all optional). conftest blocks the Anthropic client in unit tests.
- Docs: CLAUDE.md rules 2, 4, 11, 13; docs/03 §1 and §4; docs/04; `.env.example`.

**Not done / open**
- Merged as PR #13 (operator: commit, push and merge). CI on the PR: **740 pass, 5 skipped**,
  a 6 min 22 s job (run 39756475459), where the daily runs had been dying at 25 minutes.
- Cost caps, decided by the operator the same day: **separate**. Google keeps ≤ $5/month and
  Claude has its own ≤ $4/month, so metered spend can reach about $9 (CLAUDE.md rule 2).
- No Console spend limit is set on the Anthropic workspace; docs/03 §1 recommends one as a
  second stop that does not depend on this code.

### 2026-10-09 — Production down since 10-01, a full audit, and the 10-20 / 11-17 deprecations

Asked for "a full audit, deep checks, fixes, zero-cost upgrades, and model/API deprecations".
Made on branch `fix/audit-2026-10-09`, then committed one change at a time and pushed to `main`
(operator: "commit and push"). **The bot fixes need a Vercel redeploy** before they are live.
Suite with live keys: **688 pass, 5 skipped** (was 645 + 5; every skip is an opt-in live test).

**Shipped and verified (2026-10-09).** CI on the push: 688 pass on ubuntu-24.04 with PyAV 18.1.0,
and the live caption test ran instead of skipping. `verify-tts` passed (the channel voice on both
the Developer API and Vertex; Chirp listed with the key in a header); `verify-vertex` passed
(real citations on 3.5-flash-lite and 3.5-flash). **The first run on the new code** (`/makeshort
3`, run 37884778710) researched 6 stories with citations for all 6 and offered 3 ideas with named
outlets; the operator approved 2 and rejected the weakly sourced one. Both published, the first
Shorts since 09-28: `rJjqfdltLvg` (Indian pilot honoured by Israel) and `KbWEI-G61dA` (US
sanctions on Mumbai firms). Images took 62-67 s a reel (198-238 s before); the second reel's
Developer-API TTS hit its daily quota (429) and was voiced on Vertex in the same voice.
Two follow-ups, each pushed: a unit test had sent a real "post row could not be saved" alert to
the operator's chat (a guard in `tests/conftest.py` now refuses Telegram in unit tests); and the
tighten pass ran out of its 1,024-token budget on both providers (reasoning counts against it),
so the pilot reel shipped at 42 s. It is 4,096 now (repair fallback too), verified live: idea
488's script tightened 80 -> 72 words with the payoff kept. CI: **689 pass, 5 skipped**.

**How it was audited.** 15 subsystem auditors and 3 live probes (models, dependencies, live
state) ran as a multi-agent workflow. The account's session limit stopped it after 16 of 134
agents: every auditor and two probes finished, but the research agents, the adversarial verifiers
and the upgrade panel did not. So 147 findings arrived **unverified**. Each one fixed below was
checked in the code first, most with a failing test or a live probe. Agent transcripts are under
`~/.claude/projects/c--Users-shaan-Desktop-AI-Reel-Factory/<session>/subagents/workflows/wf_51e4270a-2c0/`.

**Production has been down since 2026-10-01 (critical).**
- CI's `pip install` resolved **PyAV 19.0.x** (unpinned; faster-whisper pulls it in, released
  2026-09-29). faster-whisper 1.2.1 calls `av.open(..., metadata_errors="ignore")`, which PyAV 19
  rejects, so every reel died at captions (idea 475). The last published reel (idea 397,
  2026-09-28) ran on PyAV 18.1.0; the local `.venv` has 17.1.0, so nothing looked wrong locally.
  No Short has shipped for 11 days.
- The daily `tests` run stayed green from 09-30: the live caption test turned every exception
  into a skip, so the break showed only as 10 skips instead of 9.
- **Fixed twice over:** `av==18.1.0` is pinned, and `subtitles` now decodes the narration with
  the FFmpeg binary and hands faster-whisper an array, so PyAV's `av.open` is no longer on our
  path at all. Proven on Python 3.12: with PyAV 19.0.1 the old path fails with the production
  error and the new one transcribes (start times within 0.044 s of the old path on average).
  The whisper model now loads from the local cache before asking the Hugging Face Hub.

**Fixed and verified (each with tests; live where marked):**
- **Crashes and lost work.** A dropped Supabase connection (HTTP/2 GOAWAY) crashed run
  36804231283 mid-wait. Supabase now uses its own HTTP client: HTTP/1.1 and a retrying transport
  that resends reads, updates and deletes, and an insert only when nothing was sent (live DB round
  trip passes through it). The approval wait survives a failed poll. A crash, a kill at the time
  limit or a cancellation now reaches Telegram (the pipeline reports its own crash; a workflow
  step covers kills and cancels, without a second message). The step is timed out inside the
  job so the alert can run.
- **A live Short is never reported as failed.** After the upload, a failed `produced` write used
  to fail the reel and put its idea back in the digest (a second tap would upload it twice). It is
  logged and announced instead; a release only moves ideas still at `approved`; a lost post row is
  announced on Telegram with the URL.
- **Gemini calls had no timeout** (the SDK default is none): 120 s now (`LLM_TIMEOUT_SECONDS`).
  Connection errors are retried by exception class, and a status code no longer matches inside a
  number such as "1,500".
- **Fact-check gate (rule 6 as written):** a checker reply with a preamble object, a wrapped
  verdict or "FAIL - fabricated" used to PASS with 0 claims checked; now it is re-asked and, under
  strict, held. A "minor" finding the checker itself calls contradicted now blocks (idea 211
  shipped one). The "could not confirm" waiver no longer reaches an invented quote, ruling, law or
  blame; a statistic the checker merely could not confirm stays waived, as before. A sample
  whose findings arrive unwrapped is no longer dropped when two samples are merged. The repair
  prompt is told today's date.
- **Tone.** Death and harm stories read as sarcastic when worded "kill", "killing", "deadliest",
  a crash or an attack. The detector covers those (bank strikes and market crashes keep the channel
  voice), also reads the finished script, and the hook punch-up is skipped for somber stories.
- **Disclosure.** The AI line was skipped whenever "AI-generated" appeared anywhere in the
  description; it now checks for the exact line and sits in its own paragraph.
- **Ideation after 2026-10-20 (high).** Measured by the auditor with 10 live probes: on the 3.x
  models a JSON ideation reply gets no citations, but a prose reply does. Stories are now
  researched in prose (`_research_stories`) and the JSON is written from those notes, each idea
  taking its own story's citations. `IDEATION_MODEL` defaults to
  `gemini-3.5-flash-lite,gemini-3.5-flash`. ✓live: 2 ideas, each with its own publishers (CBS
  News + The Guardian; SecurityWeek + 2 more), none borrowed from the other story.
- **Google News:** one retry after 5 s on 5xx / 429 / a dropped connection (10-01 had 503 on every
  feed). Curly apostrophes no longer split search words ("Russia s"); a search that finds nothing
  is retried with the 5 most distinctive words; model-written URLs no longer stop the search early.
- **Visuals:** the `flux-1-schnell` fallback sent a `seed` its schema rejects (HTTP 400 on every
  call), so it never worked. Shots are generated 4 at a time (11 images took 198-238 s one by
  one). The rupee is in the prompt only when money is in the shot.
- **YouTube:** a token pre-flight before the digest (a refused token stops the run before taps
  or a render; a network blip only logs). Upload retries cover TLS, httplib2 and http.client errors.
  Descriptions lose `<` `>` and fit 5,000 bytes; tags lose `<` `>` `,`.
- **Analytics:** the removed-Shorts alert had no Telegram secrets in `analytics.yml`, so it never
  sent, and rows were marked before sending. It now sends first and marks after; takedowns
  (`uploadStatus` rejected) count as removed. **Never reported, 9 removed Shorts:** `9iBRAKdrRtM`,
  `G5aIs_tQMXE`, `LB1HXE4ASmA`, `Y36jpSV4U9I`, `_X-zuJHmS9w`, `floqwtYfhPw`, `j6Ds0GjERiA`,
  `mpCx2fwc2Fc`, `z1JpC2YCEzo`. google-auth pin aligned (2.58.1).
- **CI:** every workflow pinned to `ubuntu-24.04` (`ubuntu-latest` moves to 26.04 from 2026-10-19,
  taking apt FFmpeg from 6.1.1 to 8.0.1). `pytest -rs`. Live tests skip only when a prerequisite
  is missing and re-raise in CI (`CI=true`); the live render tests voice with Kokoro, so CI no
  longer spends the channel voice's TTS quota. `analytics` re-enables both scheduled workflows
  daily: GitHub disables them after 60 days without a commit (next ~2026-11-28), and analytics'
  writes keep the free Supabase project awake. `production.yml` uses the webhook approval mode.
- **Security:** alerts to Telegram are scrubbed of secret values and `?key=` params; the Chirp
  key moved from the URL to a header (✓live: HTTP 200, the voice is listed); the bot compares
  the webhook secret in constant time; `.gitignore` covers `gha-creds-*.json`; Pillow 12.2.0 ->
  12.3.0 (13 CVEs; graphics tests pass on 3.12).
- **Bot** (needs a redeploy): titles escaped in `/pending` and `/stats` (an `&` made Telegram
  refuse the reply); a tap whose database write fails keeps its buttons and says "tap again";
  `link_preview_options` replaces the removed `disable_web_page_preview`.

**Deprecations and limits (probed 2026-10-09, official pages):**
- Vertex retires `gemini-2.5-flash` (and 2.5-flash-lite, 2.5-pro) on **2026-10-20**: handled above.
  `gemini-3.6-flash` retires 2026-11-19 (only `.env.example` named it; corrected).
  `gemini-3.8-flash`, the text model, has "a shorter availability period" with no date yet.
- **Developer API shuts down `gemini-3.1-flash-tts-preview` and `gemini-2.5-flash-preview-tts` on
  2026-11-17** — the channel voice's first and third links. Replacements `gemini-3.8-flash-tts` and
  `gemini-3.8-flash-lite-tts` are live (free tier; Vertex serves both too). Not switched: the voice
  is the operator's choice by ear, and the auditor reports the 3.8 request schema may differ
  (unverified). Until then the chain survives on billed Vertex 3.1, then Vertex 2.5 GA. The 3.8 TTS
  paid price doubles on 2027-01-01.
- Groq `openai/gpt-oss-120b` is active (no Llama chat model remains on Groq). Cloudflare lists
  flux-2-klein-4b and flux-1-schnell with no deprecation. Chirp `en-IN-Chirp3-HD-Zubenelgenubi`
  is listed. GitHub REST `2022-11-28` (the bot's dispatch) ends 2028-03-10.

**Not done here (needs the operator, or verification first):**
- the 2026-11-17 TTS migration (ear test); the bot redeploy;
- counting only fetched sources toward `MIN_SOURCES`: tried, then reverted. It breaks the
  2026-09-03 decision to keep model-written URLs, which the tests encode;
- docs: CLAUDE.md still describes a Claude Routine as live ideation and Gemini as free (production
  bills Vertex per token); docs/01-07 still name Chirp as the primary voice;
- a hashed lock file for CI (the structural fix for K1-style drift: 48 packages differ between CI
  and the local `.venv`), and a scheduled model-liveness canary (Vertex `count_tokens` is free;
  `models.get` is NOT a liveness check: it answered OK for retired ids);
- lower findings left for a later pass: repair rewrites only the narration (title, cards and
  summary stay stale); `/stats` counts removed Shorts; 2 of 11 AI images never reach the screen.

### 2026-09-29 — Scheduled digests off; leftovers, dedup and a post-merge review

The first day on the merged audit. The operator reported "my ideas are generating itself": the two
scheduled digests had started 6.5 and 7 hours late (15:35 and **01:32 IST**), and the night one
re-sent the afternoon's three ideas, two of them the same UPI story. Operator: **on demand only**.
Each change below is its own commit; **642 pass, 5 skipped**; pushed to `main`, CI green.

- **Schedule removed** from `make-short.yml` (pushed before the next slot). `/makeshort` and the
  workflow button are the triggers again.
- **New music beds** (operator: "non-copyright bg music"): four calm, neutral instrumentals
  generated with Google Lyria 2 on the Vertex project replace the four Dark/Dramatic Audio Library
  tracks. Original, so nothing for Content ID to match; nine candidates cost $0.66 once. Picked by
  measurement (least bass per style, no vocals, even intros), looped to 62.5 s with an
  equal-power crossfade (a linear one dipped 2-4.5 dB at the seam). In the production mix all four
  land at -14.5 LUFS, TP -2.1 dBTP. The description now discloses AI-generated music.
  `tools/generate_music_beds.py` records the prompts and seeds and spends nothing without `--yes`.
- **`/makeshort N` offers N ideas** (operator): the audit's floor of 3 (`DIGEST_MIN_IDEAS`) now
  defaults to 1, so `/makeshort 1` is one idea. Ideas still pending from an earlier run (a failed
  reel, a leftover approval) count toward N.
- **An untapped digest idea is passed**, not re-offered: left pending, the three ideas became the
  next digest and, filling it, kept fresh ideation from running. The three live rows (432-434)
  were set to `passed` by hand, so the next `/makeshort` brings fresh stories.
- **Leftover approvals** (a late tap, or a job killed mid-chain) go back to the digest at the
  start of a run instead of holding one of the bot's three approval slots for good; leftover
  pending ideas are topped up with fresh ones.
- **Story dedup** folds plurals and drops filler: the two UPI ideas shared five words at 0.38
  overlap, under 0.4. Over 60 days of real ideas this adds exactly that match (and loses one pair
  that matched only on "just").
- **A job time budget:** the wait is shortened so a reel still fits, and no reel starts with
  under 12 minutes before the job's limit (`JOB_TIMEOUT_MINUTES`, set in the workflows).
- **`gemini-3.8-flash` refuses MINIMAL thinking** in two wordings; only Vertex's was caught, so
  on the Developer API every text call went to Groq (seen live in a test run). Both are caught
  now, and the refusal is remembered per model. Verified live.
- **Retirement wording:** a 410, "has been retired" or "deprecated" also moves a grounded chain on,
  so 2026-10-20 does not depend on Vertex saying exactly "404 not found".
- **The unit suite reached live services:** the local `.env` and CI give it real Supabase keys, so
  un-stubbed tests wrote to the live `ideas` table, and the repair pass made live Gemini and Groq
  calls. A `conftest.py` now blocks both outside the opt-in live tests (241 s -> 90 s).
- **Fact-check:** the title is labelled as ours and opinion lines are ruled out of both buckets
  (script 314 live: 3/3 pass vs 2/3 with the old prompt; no measured gain claimed for that part).
- **Stock licences are not CC0** (both pages checked): Pexels forbids identifiable people "in a
  bad light", Pixabay misleading use of "recognisable people". The keyword prompt now keeps faces
  out; CLAUDE.md, docs/04 and docs/08 name the real licences.
- **Smaller fixes:** the punched-up title is capped at 70 too; `est_score` is no longer shown as a
  star rating (Spearman 0.13 against views); `parse_json` skips a preamble bracket; a routine file
  with nothing fresh falls back to the generator; stale quota, framing and default notes corrected.
- **Grounding spend, measured:** 7 search queries per reel (1 write + 3 per gate sample), about 14
  with a repair. Six repaired reels a day plus ideation is about 3,000 a month, inside Gemini 3's
  5,000 free on Vertex.
- **The first reel on the new code** (idea 397, Starship, `pe-LTPYxEEU`) ran clean: tightened
  95 -> 72 words, gate passed, the channel voice on the Developer API, published in 6 minutes.

### 2026-09-28 — The audit's decisions, carried out one change at a time

Operator: "do all changes, remove the whoosh sound, style prompt for sound is good rather than off,
change the retiring model to newer as suggested, do all changes one by one." Every change below is
its own commit, each gated on a green suite; **614 pass, 5 skipped**. Live verification on Vertex
and a full local render of a current story (the 2026-09-28 bank strike) through `produce_one`.

- **Whoosh removed**; the click stays at its old, sparser slots. **Style prompt kept on.**
- **Off the retiring model, measured first.** Text `gemini-3.8-flash`; grounding
  `gemini-3.5-flash-lite`; the fact-check `gemini-3.5-flash`. **Ideation stays on
  `gemini-2.5-flash` until 2026-10-20**: on the real ideation prompt 2.5 returned 15 and 18
  citations while 3.5-flash-lite, 3.5-flash and 3.8-flash all searched but returned **zero**
  citation chunks, and those citations are an idea's sources. The retirement 404 moves it on.
- **The plain style-prompt layout caused the intermittent TTS 400s.** Same text on 3.1-preview:
  plain failed 4/4, labelled sections 4/4 OK (idea 292's failure). Every model now gets the
  labelled layout; same prompt, reads slightly less briskly (A/B sample 12).
- **Fact-check:** two samples by default (the Modi-Xi claim was waived on one run and blocked on
  the next); a repair pass that rewrites only the blocked claims and re-runs the gate (live, it
  fixed the Modi-Xi claim and passed); "could not confirm" findings waived in code; verdicts
  stored in `scripts.factcheck`; gate blocks marked `blocked`, not `rejected`.
- **DB migration** `record_factcheck_verdict_and_voice` (additive, nullable, applied live):
  `scripts.factcheck` jsonb, `posts.voice` text.
- **Scripts:** a somber tone for deaths/serious harm (script and voice), the ideation angle not
  copied, titles held to 70 (an 84-character title overflowed the banner), today's date in the
  prompts (a grounded answer dated September news to June).
- **Ideation:** a wider pool (World/Business/Technology/Science sections), 3 ideas a run,
  in-batch story dedup, a 3-day recency window on the source search, a sensitive-story flag in
  the digest.
- **Visuals:** illustrative style per docs/08 on FLUX.2 klein (native 768x1344, ~103 neurons),
  per-shot seeds and compositions, place-true keywords, the story's country as the setting
  (dollar bills illustrated an Indian bank story).
- **Captions and video:** captions held through breaths, cards on the beat of their words, the
  logo below the Shorts icons, film grain off, a real publisher as the on-screen source.
- **Ops:** two scheduled digests a day, a 90-minute job timeout, removed Shorts detected and
  reported once, the cron path no longer polls Telegram in webhook mode, the daily test run
  leaves the live database alone, the bot fails closed, verify-tts checks every voice backend.
- **Growth:** recent, varied, correctly titled winners (plus low performers to avoid), the real
  YouTube title backfilled, the India tag only on India stories, the footer says 30 seconds.
- **Deps and CI:** google-genai 2.25.0, google-auth 2.58.1, groq 1.7.0 (suite and live calls
  verified on both versions first); checkout/setup-python v7, cache v6.
- **Two bugs of mine caught before shipping:** a status update that never executed (live DB
  test) and a removal alert that would have repeated daily (found while reading the code).
- **Shipped.** PR #12 merged to `main` (`3ac1ac0`) after its `tests` run passed (614 pass,
  5 skipped), with `verify-vertex` and `verify-tts` passing on the branch. The Vercel bot was
  redeployed (`telegram-k2wvf1c1q`, aliased to `telegram-bot-gilt-omega.vercel.app`): GET 200,
  an unsigned POST 401 (configured and authenticating, not the fail-closed 503), webhook with no
  errors. The two scheduled digests are live from this merge. The local `.venv` is on the new pins
  and passes the suite.

### 2026-09-27 — Full audit: why the sound changed, a model retiring in 3 weeks, and 60+ findings

Asked for "a full deep audit — sound is very different too from before — check everything and
every possible upgrade". Nine subsystem auditors (voice, mix, scripts/LLM, ideation, fact-check,
visuals, captions/video, ops, growth) plus live probes and a local end-to-end render. All fixes
are on branch **`fix/audit-2026-09-27`** (worktree `../AI-Reel-Factory-fix`), **uncommitted**,
**565 pass, 5 skipped** (was 489 + 5).

**Why the sound changed — measured, not guessed.** Audio of 10 published Shorts (06-11..09-22):
- **2026-09-01, commit 55544f1** (`config.get` treats an empty env var as absent) silently turned
  on two things in production that had never run there: the Gemini **style prompt** ("brisk
  clip… very little warmth"; the same script reads in 21.9 s with it, 26.2 s without) and the
  procedural **SFX stings** (whoosh/click every 2nd cut; `SFX_DIR=""` had crashed them since
  07-26). Loudness range went from 1.6–3.4 LU to 4.5–5.8 LU. From 07-27 to 09-01 every reel was
  narrated with NO direction at all — that is the "before" sound.
- **3 of ~13 reels since 09-01 left the channel voice for Chirp** (ideas 292, 303, 304): a 400,
  503s on both Developer-API models, and an httpx "Server disconnected" that matched no
  transient marker. Nothing recorded which engine spoke.
- **Loudness was never set**: published reels measured -16.8 to -22.7 LUFS (YouTube plays at -14
  and never turns quiet uploads up), and the music ducking pumped 9–11 dB inside each second.

**Critical, time-bound:** Google's Vertex model-versions page lists **`gemini-2.5-flash` for
retirement on 2026-10-20** (replacement `gemini-3.5-flash-lite`). It grounds ideation, the
scriptwriter and the fact-check gate; with `FACTCHECK_STRICT=true` every reel would be held.

**Fixed on the branch (each with tests; live-verified where marked ✓live):**
- `llm`: `GEMINI_GROUNDED_MODEL` is an ordered chain (default `gemini-2.5-flash,gemini-3.5-flash-lite`)
  that falls through only on a 404 "model gone" ✓live; MINIMAL thinking is retried at LOW
  (`gemini-3.8-flash` 400s on MINIMAL) ✓live; one shared JSON repair (`parse_json`) for scare
  quotes, trailing text and bare arrays — the scriptwriter wrote both 09-22 scripts ungrounded
  over a quote mark; Groq retries an empty `json_validate_failed` once with double the budget.
- `voice`: same-voice attempt chain (Vertex serves 3.1 and GA 2.5-flash-tts with Zubenelgenubi;
  ~$0.5/month expected, knob `GEMINI_TTS_VERTEX_FALLBACK`) ✓live — the local render hit a real
  429 on the Developer API and was voiced by Vertex 3.1, same voice; any error advances (a 429
  is per model, the 292 400 was intermittent); request timeout; mime-aware audio (3.8 answers a
  full RIFF WAV); per-model prompt layout (**3.8 reads an unlabelled style prompt aloud**,
  measured: 47.5 s) plus a read-aloud guard; `VOICE_STYLE_PROMPT=off`; `synthesize(meta=)` and
  a Telegram alert whenever a reel leaves the channel voice.
- `assembly`: every reel leveled to **-14 LUFS** from its own measurements (voice to a -20
  reference, light 3:1 compression, bed 11 LU under, 48 kHz limiter) — local renders land at
  -14.3..-14.7 for every engine (was -17.9..-19.9) ✓live; de-pumped ducking (3.5 dB swing);
  bed starts at a per-reel offset with a fade-in; `MUSIC_VOLUME` validated; 48 kHz output.
  Video: capped-CRF encodes (final CRF 20 / 8 Mbps, intermediates CRF 17 / 20 Mbps) and real
  BT.709 tags. **An uncapped CRF 18 measured 44 Mbps** on the film grain — the cap is required.
- `scriptwriter`: the word cap is stated in the prompt (it never was; drafts ran 82–128 words);
  an LLM tighten pass before truncation (live: 101→72, 91→72) ✓live; truncation drops whole
  sentences, CTA first, never mid-sentence (script 267 shipped mid-sentence); the hook punch-up
  may not delete the "why it matters" turn (it did, live, on idea 312); markdown stripped; ONE
  Sources block from fetched sources only (every recent description had two, 12 of 53
  model-written links were dead); disclosure says "narration and images" when `VISUAL_SOURCE=ai`.
- `factcheck`: the checker is told today's date ✓live (it then correctly blocked idea 308's
  10-day-old "headed to the President's desk"); key-point cards and the description summary are
  checked too; opt-in `FACTCHECK_SAMPLES` (block if any of N samples blocks) — measured
  non-determinism: the same script passed 2 of 5 runs.
- `ideation`: redirects resolve from Google's one-hop `Location` (idea 315 kept two raw
  vertexaisearch links); a grounded citation whose slug names another story is dropped
  (Iran-UAE idea 301 cited three UCC articles); **story-level dedup** over the last 10 days by
  shared source or distinctive words (blocked idea 314 came back 47 min later as 315 and
  shipped) — replayed on the real table it flags 227/228 and 314/315 ✓live.
- `subtitles`: caption TEXT comes from the approved script, whisper only times it (7.6% of
  burned words were wrong: '3 5 %', '769 croned', 'On officially'); groups close at sentence
  ends and at a measured 840 px width; the hook banner shrinks to fit instead of dropping words
  (20 of 40 were cut); the Source line moved above the Shorts bottom UI.
- ops: `concurrency: reel-pipeline` on both pipeline workflows (overlapping runs could
  double-publish); digest taps only move a still-pending idea (polling path + bot code); the
  approval wait is scoped to this run's ideas and ends at the cap; YouTube upload retries
  transient errors; `defaultLanguage/defaultAudioLanguage=en` (one English reel was tagged
  Hindi); Cloudflare's error body is logged; `tests.yml` gets `permissions: contents: read`.
- **Bug caught by the live DB test before it shipped:** the new conditional
  `db.set_idea_status` skipped `execute()` on the unconditional path. Fixed, with a live test.

**Operator decisions (not changed in code):**
1. **Narration style** — listen to the A/B pack (scratchpad `ab_pack/`): August (no direction)
   vs now (style prompt) vs `gemini-3.8-flash-tts` (not labelled preview; needs the labelled
   prompt, which the branch provides). Set `VOICE_STYLE_PROMPT=off` for the August sound.
2. **SFX** — the auditor recommends OFF (`ENABLE_SFX=false`): 3 of 4 stings land on words, the
   whoosh is mostly hiss after the 24 kHz output; it was never signed off.
3. **Grounded successor** — the chain moves to `gemini-3.5-flash-lite` on 10-20 by itself; the
   gate could move now to `gemini-3.5-flash` (caught the 314 error in 1 sample; ~$0.003/check).
4. **Fact-check samples** — `FACTCHECK_SAMPLES=2` halves the chance a contradiction slips through.
5. **Visual style** — the Flux prompt asks for "photorealistic documentary news b-roll", which
   docs/08 reads as against its rule that AI images stay abstract; upgrade path flux-2-klein-4b.
6. **Cadence** — 0.72 Shorts/day vs a 4–5 goal; every run is hand-triggered with IDEAS=1-2.
7. Two public Shorts never passed the gate: `xRUo6GxYwYo` (idea 285, US-Iran tanker) and
   `NKPb-InUoJU` (idea 291, Modi-Xi). Re-checking now
   blocks both.
8. Redeploy the Vercel bot for the stale-tap guard (CLI-deployed, not git-connected).


### 2026-09-13 — Strict fact-check is ON: no reel ships unverified

- **Operator decision:** repo variable `FACTCHECK_STRICT=true`, read by both `make-short.yml`
  and `production.yml`. When the gate cannot run (outage, or a reply unreadable even after the
  repair and the re-ask), the reel is **blocked** instead of published unverified. Why: idea 291
  shipped unverified with a claim the gate blocks every time. On Vertex, the quota exhaustion
  that fail-open was built to survive is gone.
- **Bug fixed before switching it on.** Strict mode took the same path as a real verdict:
  `produce_one` marked the idea `rejected` for good, and the alert said "failed fact check" about
  a story nobody had checked. It now raises `FactCheckUnavailable`, which is not a
  `FactCheckFailed`, so `_release_failed_idea` puts the idea back to `pending`. The alert
  explains it was held back, not judged. A contract test runs the real `factcheck.verify` in
  strict mode, so if the reason string drifts the test fails instead of ideas being rejected.
- Tests: **489 pass, 5 skipped**.

### 2026-09-13 — Every idea cited every story, and the gate fell open on a quote mark

Run 34703685567 (2026-09-12) produced ideas 291 (Modi-Xi) and 292 (Houthis). Both shipped with the
**same 15 grounded citations**, which also covered a Nagpur bank robbery and a California murder.
Idea 291 also shipped **UNVERIFIED** (`checker-failed: Expecting ',' delimiter`).

- **Why the citations smeared.** It was reproduced live on Vertex and replayed offline from the
  captured reply. The first support segment starts at offset 0, which the API omits, so the SDK
  returns `start_index=None`. `int(None)` raised, and one `except` around the whole loop threw
  away every span. With every citation "loose", each one was attached to every idea. Two more
  bugs were underneath:
  - offsets are UTF-8 **bytes** (measured: `byte_match=True`, `char_match=False` once ₹ and — are
    in the text) and relative to their `part_index`;
  - a support that straddled two ideas was credited to both.

  Fixed in `llm._text_parts`/`_support_span` and `ideation_fallback._citations_by_idea`. Each
  support goes to the one idea whose own words it covers most. A spanless citation is kept only
  in a one-idea reply.
- **Why the gate fell open.** The checker put raw `"` inside a finding, `json.loads` died, and a
  parse error takes the same fail-open path as a quota outage. The actual reply is gone: it was
  never logged, and six live re-runs did not reproduce it. But the error signature is exactly
  that of an unescaped quote, and a synthetic reply of that shape reproduces the production error
  verbatim on the old code. Now:
  - the prompt asks for single quotes;
  - `_escape_stray_quotes` repairs the JSON (a no-op on all 6 real valid replies, exact on every
    broken variant);
  - an unreadable reply is asked for **once** more;
  - the unreadable raw reply is logged.
- **What the gate would have said.** Re-run on script 258 it **blocks 6/6**: Modi and Xi did not
  just hold their "first bilateral talks in five years". They met in Kazan (Oct 2024) and Tianjin
  (Aug 2025). The idea's first "source" was a 2024-10-23 VOA article about Kazan.
- **Telegram digest.** Each idea listed every source as its own full-URL line (17 of them, up to
  884 characters each), with a link-preview card. Sources now fit on one line: three publisher
  names as links, `+N more`, previews off. Tapping a button used to re-send the plain text as
  HTML, which lost every link and 400'd on `&` or `<`. It now re-sends the original entities,
  shifted by UTF-16 length. Both halves were verified against the live Bot API: one labelled
  preview message was sent to the operator chat.
- **Blast radius.** Only the 2026-09-12 batch. Every batch since the Vertex switch was checked,
  and none of the others share sources, because the bug fires only when the reply starts with `{`
  instead of a code fence.
- **Verified live after the fix:** a fresh grounded ideation on Vertex gave each of 6 ideas its
  own story's sources. The fact-check still blocks script 258. Tests: **486 pass, 5 skipped**.
- **Shipped:** pushed to `main` (5 commits, `tests` workflow green on `a24bddf`). The Vercel bot
  was redeployed to production (`telegram-k6us6ouk7`, aliased to the webhook's
  `telegram-bot-gilt-omega.vercel.app`, health check OK). That deploy also carried the
  2026-09-03 bot fixes (approval cap 3, `/latest` nulls-last), which had never been deployed:
  the previous deploy was 94 days old. The project is CLI-deployed, not git-connected.
- **Still open (needs the operator):**
  - decide what to do about `NKPb-InUoJU` (false claim, public) and both Shorts' descriptions;
  - ~~consider `FACTCHECK_STRICT=true`~~ — **done**: the operator chose it, and the repo variable
    is `true` (see the strict-mode entry above).

### 2026-09-04 — Vertex AI removes the grounded-search ceiling entirely

Yesterday's audit found the fact-check gate silently failing open once the shared 20/day grounded
budget ran out. A second free API key turned out not to fix it (grounded search is closed to new
projects). Google Cloud does.

- **Vertex AI serves the same Gemini models with 1,500 grounded requests/day free** on 2.5,
  against ~21/day of demand — 71× headroom, ₹0. It also still serves `gemini-2.5-flash`, which
  the Developer API 404s for new projects. Verified end to end through the real pipeline code:
  citations returned, and `factcheck.verify` reaching a real verdict instead of failing open.
- **Auth is keyless.** The org enforces `iam.disableServiceAccountKeyCreation` and disallows API
  keys (AI Studio refuses to mint one for an org project), so ADC locally and Workload Identity
  Federation in CI. Nothing is stored: `permissions: id-token: write` + `auth@v3` exchange
  GitHub's OIDC token for a short-lived Google one.
- **Cloud objects created** (all in `but-it-matters-tts`, which was already billed for TTS):
  service account `reel-factory-ci` with `roles/aiplatform.user`; WIF pool `github`; OIDC
  provider `github-oidc`, restricted to `assertion.repository_owner=='Shaan-alpha'` and bound to
  this repo only. A ₹450/month budget with 50/90/100% alerts now guards the billing account.
- **Dead ends, recorded so nobody re-walks them:** gcloud-minted API keys are rejected by the
  Gemini API unless `--api-target=generativelanguage.googleapis.com` is set, and are blocked
  outright on org projects; the billing account is at its 5-project cap; Custom Search JSON API
  is closed to new customers and shuts down 2027-01-01.
- `GEMINI_USE_VERTEX` defaults to **false** in code (a fresh clone still works with just an API
  key) and **true** in both pipeline workflows. `tools/verify_vertex.py` and the `verify-vertex`
  workflow prove the path before a real run depends on it.
- Tests: **469 pass, 5 skipped**.

### 2026-09-04 — A second free key cannot give the fact-check gate its own quota

Setting up 0.17.0's `FACTCHECK_API_KEY` with a real second key turned up a hard limit:
**free grounded search is closed to new Google Cloud projects.** Probed both keys across five
models — on the new key `gemini-2.5-flash` 404s ("no longer available to new users") while every
other model 429s with an empty violation list (no allowance); on the original key
`gemini-2.5-flash` 429s with `quotaValue: 20`, i.e. a real budget merely spent.

- **So the gate cannot be isolated for free.** The 20/day on the original project is the whole
  grounded budget the pipeline gets. `FACTCHECK_API_KEY` stays wired for a PAID key or a future
  free tier, but it is not a fix available today.
- **Worse, a wrong key was actively harmful:** it fails on every call, so the gate fail-opened on
  every reel. `factcheck._ask_checker` now falls back to `GEMINI_API_KEY` on a misconfigured key
  (404/403/invalid) and NOT on a 429 — a spent dedicated key means isolation is working.
- **What actually protects the gate today** is the other two levers from the audit, both live:
  the fail-open Telegram alert (you now hear about every unverified reel) and
  `ENABLE_GROUNDED_SCRIPT=false`, which hands the scriptwriter's grounded call to the gate and
  cuts a 3-reel run from 7 grounded calls to 4.
- Tests: **465 pass, 5 skipped.** `tools/verify_factcheck_key.py` reports this situation directly.

### 2026-09-03 — Full audit, start to end

Read every module, both cron paths, the Vercel bot, the docs, the workflows and the live
database. **460 pass, 5 skipped** (was 440 + 5). Findings, worst first:

- **The accuracy gate switched itself off on busy days, silently.** Ideation (1/run), the
  scriptwriter (1/reel) and `factcheck.verify` (1/reel) share ONE 20/day free grounded budget on
  `gemini-2.5-flash`. A 3-reel run spends 7, so a third run exhausts it — reproduced live
  (`429 … limit: 20`). With `FACTCHECK_STRICT=false` (default) the gate then returns `ok=True`,
  and `produce_one` read only `ok` — so an unverified reel shipped looking exactly like a verified
  one. Now `factcheck.gate_ran()` separates a verdict from an outage, `produce_one` Telegram-alerts
  on a fail-open, `FACTCHECK_API_KEY` can give the gate its own free key, and
  `ENABLE_GROUNDED_SCRIPT=false` reclaims the scriptwriter's call for it.
- **CLAUDE.md — the file every agent must read first — said "No pipeline code yet."** It was
  written before the build and never updated; 76 Shorts and 5,100 lines of pipeline later it was
  still the first thing a cold agent read. STATUS also contradicted itself (Snapshot said "other
  modules still stubs" while the table below marked all ✅) and carried two stale test counts.
- **Versioning had collapsed:** 17 stacked `[Unreleased]` blocks, STATUS claiming 0.5.0, last real
  tag `v0.2.0` (2026-06-10). Blocks are now dated from git and versioned from their own
  subsections; **`v0.17.0` is tagged**. No retroactive tags — those releases were never cut.
- **The Telegram bot's `APPROVAL_CAP` defaulted to 5 vs the pipeline's 3**, which would strand
  approved-but-unproducible ideas at 'approved' forever and answer "capped" to later taps.
- **Nothing aged out stale pending ideas**, so a two-day-old story could headline today's digest.
- Smaller: two reels in a batch could draw identical photos; source blocks were an unreadable
  wall; three GitHub Actions were on the deprecated Node 20; `production.yml` had no job timeout;
  `analytics.yml` installed Kokoro + Whisper for one API call; three settings were read by nothing.

**Verified healthy, not changed:** secrets hygiene (`.env`, `client_secret*.json` gitignored AND
untracked); all deps pinned and importable; assets committed; DB clean (0 stuck approved/pending,
76 posts / 123 ideas); publish idempotent and correct about the irreversible-upload case.

**Known and deliberately not fixed:** citations are Google News article links (249-884 chars) —
the modern `AU_yqL…` id is opaque, so the publisher URL cannot be recovered; grounded publisher
URLs are already preferred when quota allows. `_GEMINI_TTS_RATE` stays hardcoded at 24000 (matches
the API's declared mime type today, re-check if a TTS model changes).

### 2026-09-03 — The digest was starving on invented citations (and the captions were wrong)

**Reported:** the job run failed, asking for >1 idea only produced one, and the TTS "might not be
accurate". The first two were **one bug**; the third was real but not in the voice.

- **Root cause (failures 1 + 2).** `llm._gen_gemini_grounded` returned only `resp.text` and
  discarded `grounding_metadata` — `grounding_metadata` appeared **nowhere** in the codebase — so
  the ideation prompt asked the *model* for source URLs. Models invent them
  (`articleshow/115000000.cms`, `world-asia-68700000`); `_url_is_dead` 404'd them; every idea fell
  under `MIN_SOURCES` and was dropped. ≥1 survivor → a digest of one. 0 survivors → `RuntimeError:
  no fresh ideas to seed` → exit 1. Both faces of the same defect.
- **Fix.** Cite what we actually fetch: grounded citations via
  `llm.generate_grounded_with_sources()` (per-idea via `grounding_supports` spans), the news feed's
  own `<link>`/`<source>` via `news.fetch_stories()`, and `news.search_stories()` — the free,
  key-less Google News RSS *search* — for anything still short, preferring distinct publishers.
  Homepages are rejected; only FETCHED sources count toward the minimum.
- **Verified live** with the grounded quota fully exhausted (HTTP 429, `limit: 20`, the worst case
  and the one that killed the run): **3 ideas, 2 real distinct-publisher sources each.**
- **Root cause (failure 3) — the captions, not the voice.** TTS output matches the script 98%
  (only `recognise`/`recognize`) and the PCM rate matches its declared mime type. But
  faster-whisper splits `1,270` into `1` + `,270`, `_clean_caption_word` stripped the comma, and
  the reel burned **"authority 1" / "270 people died"** and **"and 2 4"**. Fixed in
  `subtitles._merge_number_tokens()` and confirmed against the real narration.
- **Resilience.** A thin grounded pass now tops up instead of shipping one idea, and ideation
  coming up dry sends a Telegram message and exits 0 rather than a red ✗ (rule 14).
- **Tests: 440 pass, 5 skipped** (was 405 + 5). The ideation suite is fully offline again (0.7s).
- **Not changed:** the voice engine, model and Zubenelgenubi voice are untouched — they were fine.

### 2026-09-01 — Audit complete (batch 3): the coverage gaps the cut-short fan-out left
**404 pass, 5 skipped.** Every module in `src/` is now read or scanned, plus `telegram-bot/`
and all five workflows. Clean on review: `analytics.py` (deleted videos are handled),
`news.py`, `trends.py`, `graphics.py`, `subtitles.py`.

- ✅ **The narrator still changed gender two links down.** STATUS 2026-08-25 recorded "keep one
  narrator down the whole voice fallback chain" but changed only link 2 of 4. Actual chain:
  Gemini **Zubenelgenubi (male)** → Chirp **Zubenelgenubi (male)** → edge-tts
  **en-IN-NeerjaNeural (FEMALE)** → Kokoro **af_heart (FEMALE)**. A double outage still swapped
  who was presenting the news. Now `en-IN-PrabhatNeural` (the male en-IN edge voice, confirmed
  against the live voice list) and `am_michael`; new `_kokoro_voice()` makes the rule testable.
- ✅ **The stock-video path still recycled shots** — the 2026-08-25 `slice_count` fix was wired
  into the IMAGE path only. Video credited each clip with `_SLICE_SECONDS` (8.0s) while assembly
  cuts at ~3.5s: measured **4 clips downloaded for 10 cuts**, so 6 of 10 shots replayed. It is
  the branch that runs when Flux fails, i.e. exactly when things are already going wrong.
- ✅ **`ENABLE_SEAMLESS_LOOP` had never once done anything.** It replaced the LAST slice, but
  `slice_count` over-covers on purpose and the render is trimmed to the narration, so the
  reprise started at or past the trim point. Measured across 23/25/28/30s narrations: **visible
  for 0.00s every time.** Now targets the last *visible* slice.
- ✅ **The audio limiter was gated on SFX.** With `SFX_DIR=""` breaking SFX on 100% of runs, the
  only mix production ever built — narration + music bed, summed with `normalize=0` (no
  headroom) — went out **unlimited**. Now gated on "did we mix at all".
- ✅ **`GROQ_MODEL` was settable by no workflow.** Both Groq breakages were the model, and both
  needed a commit to swap. Now a repo variable.
- ✅ **fact-check now logs the raw checker reply on a block.** There was zero observability into
  what the checker returned, so a model that mis-sorted a finding was indistinguishable from
  `_findings()` harvesting one of the undocumented `critical`/`unsupported` keys — different
  causes, different fixes, and three August reels died with no way to tell them apart.
- ✅ `.env.example`: `NICHE_LEAN` marked removed (dead in code since 2026-07-27); `VOICE` and the
  one-narrator rule documented for the first time.
- ⚠️ **Deliberately NOT changed: fact-check's blocking logic.** `verify()` still harvests the
  undocumented `critical`/`unsupported` keys and still lets grading override the model's own
  `verdict` — it only ever *widens* what blocks. Loosening a safety gate without being able to
  measure the result live is the wrong trade, and the source-liveness fix already removes what
  triggered 2 of the 3 real blocks. Revisit once the raw-reply logs show real data.

### 2026-09-01 — Fixed (batch 2): the reason nobody noticed, plus six reliability holes
**396 pass, 5 skipped** (batch 1 left it at 383 + 4). Still uncommitted — working tree only.

- ✅ **CI now runs the suite** — new `.github/workflows/tests.yml` (push · PR · daily 05:00 UTC ·
  manual). **The schedule is the point:** both Groq breakages were upstream drift, not code
  changes, so a push-only trigger would have missed them. This is the single fix that would have
  caught two of batch 1's four bugs.
  - ⚠️ **`test_live_real_llm_ideation` was the one live test that ran by DEFAULT**, and it is the
    most expensive in the suite — `run_fallback_ideation()` spends several grounded Gemini calls
    against the 20/day cap that production shares. Every casual `pytest` was competing with the
    day's reels for their provider. Now gated behind `IDEATION_LIVE_TEST=1`, matching the four
    other live tests. CI therefore spends **zero** Gemini requests; verified by simulation —
    382 passed, 5 skipped, every skip a deliberate opt-in, and 30s faster.
- ✅ **`posts.published_at` is stamped at insert** (`db.insert_post`). The column has no DB
  default and nothing ever set it, so the bot's `/today` always answered "0 Shorts" and `/latest`
  ordered by an all-NULL column. Bot queries now also use `.nullslast`, so the 75 legacy NULL
  rows can't outrank real ones (Postgres sorts NULLs FIRST on DESC).
  **Not backfilled** — that is 75 production writes and the operator's call.
- ✅ **The word cap no longer amputates the payoff.** `_truncate_to_words` reserves the
  "why it matters" sentence and trims the setup to fit around it; new shared `_payoff_start()`
  keeps the cap and the tag floor agreeing on where the payoff is. Idea 224's log — `104 words >
  80 cap; truncating` immediately followed by `has NO 'why it matters' turn` — was cause and
  effect. Untouched when there is no bridge, or when the payoff alone would blow the cap.
- ✅ **Transient upstream errors get one retry** (`_call_with_retry`). 429/503/500/504 retry once,
  honouring Google's own `retryDelay` when it names one, capped by `LLM_RETRY_MAX_WAIT` (90s) so a
  daily-cap 429 naming an hour fails over instead of stalling. A 400 is a verdict — no retry.
  Run 32920283763 had Gemini 503, an explicit `retryDelay: 46s` nobody read, and ~40 minutes of
  unused job budget; it failed over to the (then-broken) Groq leg and died.
- ✅ **`generate_grounded` retries too** — it has NO second provider, and its failure is silent:
  `factcheck.verify` fails OPEN under the default `FACTCHECK_STRICT=false`, so a 503 there doesn't
  block a reel, it publishes one with the accuracy gate quietly absent.
- ✅ **A failed post-insert no longer costs a duplicate video.** `publish()` swallows and loudly
  logs an `insert_post` failure instead of propagating it. The upload is irreversible; the row is
  not — and both idempotency guards key off that row, so letting it raise meant the idea returned
  to the queue and the next run re-uploaded the same reel. **This one was made worse by batch 1's
  `_release_failed_idea`** (which returns failed ideas to `pending`), so it needed fixing here.
- ✅ **GitHub Models is retired by GitHub** — verified live: catalog *and* inference both return
  HTTP 410 `github_models_retirement_brownout`. Left in the tree (opt-in, off, fails over
  cleanly) but now documented as dead in `llm.py` and `.env.example`. **Rule 11's third link does
  not exist — the live chain is Gemini ↔ Groq only.**

**Still open — needs the operator, not code:**
- ✅ **`PIXABAY_API_KEY` set (2026-09-01)** — operator supplied a key; stored in the local
  `.env` (gitignored) and as a GitHub Actions secret, never committed (rule 5). Verified live
  against both endpoints: images 200/500 hits, and `_pixabay_search` returns 3 clips per
  keyword. **Rule 11's visual chain is now closed end to end**: Flux → Pexels video → Pixabay.
- **No GCP budget cap** (rule 2 unmet since 2026-08-25): billing is on with `texttospeech`
  enabled and `billingbudgets.googleapis.com` is not. Deliberately not touched — creating budgets
  on a billing account is the operator's call. (Note a GCP budget is an *alert*, not a hard stop.)
- **The 75 already-published Shorts still carry dead citations.** Batch 1 stops new ones; it does
  not rewrite existing descriptions.

### 2026-09-01 — Fixed: all four audit blockers, each pinned by a test watched failing first
**383 pass, 4 skipped** (was 366 + 4; 17 new tests). No code was committed — working tree only.

- ✅ **`config.get()` treats a present-but-empty env var as absent.** One line, three subsystems
  back. Verified under the exact CI env shape (`SFX_DIR=""`, `VOICE_STYLE_PROMPT=""`,
  `IMAGE_STYLE=""`, `CAPTION_FONT_FILE=""`): style prompt resolves to its real 480 chars,
  `ensure_sfx_assets()` generates 5 wavs instead of raising, `"no text, no watermark"` is back in
  the Flux prompt, Montserrat path restored.
- ✅ **`_gen_groq` sends `reasoning_effort` (default `low`).** Reproduced the production failure
  against the exact call — `visuals.extract_keywords` at `max_tokens=200` — then fixed it:
  `400 json_validate_failed` → valid JSON in 52 reasoning tokens. The old "live" test was
  replaced with one that sends the **real** prompt at its **real** budget; it fails on the
  unfixed code with the production error.
- ✅ **`run_production(only_ids=…)` scopes a batch to the ideas that run offered**, and
  `_release_failed_idea` returns a transiently-failed idea to `pending` (a `FactCheckFailed`
  stays `rejected`). Stale approved rows can no longer ship unapproved or eat `APPROVAL_CAP`.
- ✅ **`_url_is_dead()` probes every source before the digest**; `MIN_SOURCES` now counts live
  links. Verified against the real fabricated URLs: drops the TOI/DW/HT 404s, keeps the live
  Al Jazeera article, keeps bot-blocked NDTV and paywalled Bloomberg, keeps an unresolvable host.
  **Honest limits:** it catches hard 404/410 only — The Hindu's `article12345678.ece` placeholder
  answers 200 (soft-404) and still gets through, and fail-soft means a DNS blip keeps a URL.
- ⚠️ **Not fixed, deliberately** (each is its own change): no CI workflow runs pytest;
  `posts.published_at` NULL on all 75 rows; the 80-word cap truncates from the end, where the
  "why it matters" turn lives; missing `PIXABAY_API_KEY`; GitHub Models retired (410); no Gemini
  429 retry; non-atomic publish→status; no GCP budget cap.
- 🔎 **Not repaired by any of this: the 75 already-published Shorts still carry dead citations.**
  The fix stops new ones. Cleaning up the existing descriptions is a separate decision.

### 2026-09-01 — Audit: 91 of 167 published citations are dead links, and one config bug broke three subsystems
Operator report: reels failing, failed reels re-producing without approval, "voice TTS not coming".
All three reproduced. **366 pass, 4 skipped** — the suite is green against every defect below,
which is itself the top finding.

- 🔴 **Ideation fabricates source URLs; 23 published Shorts cite nothing but dead links.**
  `_clean_sources` ([ideation_fallback.py:131](src/ideation_fallback.py#L131)) validates only that a
  string starts with `http` — that is the whole of what STATUS has been calling "sourced+validated".
  Live-checked all 167 source URLs on the 75 produced ideas: **91 hard 404, 45 blocked/paywalled,
  25 OK.** 58 of 75 reels have ≥1 dead citation; **23 of 75 have no live citation at all**. Several
  are placeholder ids (`articleshow/12345678.cms`, `article12345678.ece`); others are real articles
  about a different story (idea 226, published, cites an RSS-chief piece for a Modi–Putin script).
  This is the monetization gate (docs/08 §1) failing silently on a public channel, and it is the
  **upstream cause of most fact-check kills** — the checker was right to object.
- 🔴 **Unapproved re-production — confirmed with a receipt.** `run_production` drains
  `db.get_approved_ideas()`, unscoped to the current run; only `FactCheckFailed` sets `rejected`, so
  any other failure leaves the idea `approved` forever. `ideas` has **no `approved_at` column**, so
  the system structurally cannot tell "approved 5 min ago" from "stuck 3 days". Run 32920283763
  (08-26) logged `idea 223 failed`; run 33108008045 (08-27) logged `sent 2 ideas to the digest` then
  `3 approved after webhook wait` and published 223 → `floqwtYfhPw`, now *Video unavailable*.
  Knock-ons: stale `approved` rows permanently consume `APPROVAL_CAP` (3 stuck = every future tap
  returns "capped"), and stale `pending` rows are reported as `already queued (Routine)` next run.
- 🔴 **`config.get()` lets a set-but-empty env var shadow its default** —
  [config.py:72](src/config.py#L72) is `os.environ.get(key, DEFAULTS.get(key, default))`, and
  `FOO: ${{ vars.FOO }}` with no repo variable exports `FOO=`. `get_bool`/`require` are safe; only
  `get()` is affected. **One bug, three live symptoms:**
  · `VOICE_STYLE_PROMPT=""` → [voice.py:305](src/voice.py#L305) sends the Gemini TTS request with
    **no delivery direction at all** since 7393ef5 (2026-07-27). `tools/compare_voices.py` runs
    locally where the default applies, so the voice was tuned by ear on a render production has
    never made. **This is the operator's "voice TTS not coming".**
  · `SFX_DIR=""` → `os.makedirs("")` → the `SFX track generation failed ([Errno 2] …: '')` line in
    **100% of runs**; `ENABLE_SFX`/`SFX_VOLUME`/`SFX_EVERY_N_CUTS` are dead knobs.
  · `IMAGE_STYLE=""` → [visuals.py:225](src/visuals.py#L225) strips `"…no text, no watermark"` from
    every Flux prompt. **This retires the 2026-08-25 "no clean fix found" entry**: the negative
    styling was never ignored by the model, it was never sent — which is also why that A/B was
    inconclusive.
- ✅ **Narration is NOT missing.** Pulled the audio of every reachable published Short and
  transcribed it: all three carry clear, intelligible narration (mean −17…−21 dB, full transcripts
  recovered). The defect is character, not presence — see `VOICE_STYLE_PROMPT` above.
- 🔴 **The Groq fallback is still dead — a 404 was traded for a 400.** `openai/gpt-oss-120b` is a
  reasoning model and Groq bills its trace against `max_tokens`. Reproduced against the exact
  production call: `visuals.extract_keywords` at `max_tokens=200` returns
  `400 json_validate_failed / failed_generation: ''`; adding `reasoning_effort="low"` returns valid
  JSON in 52 reasoning tokens. Every `llm.generate` caller passes `json=True`, so rule 11's chain is
  **one deep** — a Gemini 429 (20 req/day/model) is a hard stop. That is what killed idea 223.
  The live test that "pinned" the fix uses a toy prompt at `max_tokens=256`, which fits inside the
  trace — and **no CI workflow runs pytest**, so it never executes anyway.
- 🟠 **Fact-check over-blocks, but less than it first appeared.** Severity grading is pure prompt
  prose; [factcheck.py:212](src/factcheck.py#L212) harvests undocumented `critical`/`unsupported`
  keys into the blocking bucket and line 229 discards the model's own `verdict`, so the code only
  ever *widens* what blocks. It fired 3 times in 13 runs. **Correction to the first read:** the
  "script from 2024" block was *not* the checker's training cutoff — the string `2024` was in its
  prompt, inside an ideation-supplied Reuters date-slug. Fix the sources, not the date prompt.
- 🟠 **The word cap eats the payoff.** `_truncate_to_words` cuts from the end, and the
  "why it matters" check runs after it — idea 224 logs `104 words > 80 cap; truncating` immediately
  followed by `has NO 'why it matters' turn`. Not the only cause (most warnings have no truncation
  line), but a real one, on the exact turn that carries the originality signal.
- 🟠 **`posts.published_at` is NULL on all 75 rows** — `db.insert_post` never sets it. The bot's
  `/today` therefore always reports 0 Shorts, and `/latest` orders by an all-NULL column.
- 🟡 Also: `PIXABAY_API_KEY` secret does not exist, so the Pexels→Pixabay fallback is dead (rule 11);
  GitHub Models (the designated third provider) is retired by GitHub and returns HTTP 410;
  no Gemini 429 retry despite an explicit `retryDelay`, inside a 60-minute job; publish→
  `set_idea_status("produced")` is non-atomic; `TELEGRAM_APPROVAL_MODE` is empty in production.yml
  (→ polling, which Telegram refuses while the webhook is registered — latent, cron is off);
  still no GCP budget cap (rule 2 unmet).


### 2026-08-25 — Audit: the analytics feedback loop was learning from 3 videos out of 72
Health check of a channel that has been live and unattended for ~3 weeks. **366 pass, 4 skipped.**
- ✅ **Re-verified, still correct:** suite green; grounded search still 429s with an *empty*
  quota-violation list on every 3.x model while `gemini-2.5-flash` answers, so the grounding pin
  stays; `gemini-3.1-flash-tts-preview` + Zubenelgenubi still exist and are still the newest TTS.
- 🔴 **Fixed — `db.top_performing_titles` ranked snapshots, not videos.** `analytics` is a time
  series (3,454 rows for 72 posts), so the top-24 window was filled by one breakout Short's own
  daily history: it returned **3** winners when ideation asked for 6, and decayed further every
  day. Now collapses to one row per post (newest snapshot) before ranking, with a window that
  scales with the post count. **Live: 3 → 6 winners.** +5 tests.
- 🟠 **No GCP budget cap exists** — billing is enabled on `composed-maxim-498517-f0` with
  `texttospeech` on, but `billingbudgets.googleapis.com` is not even enabled, so rule 2's "set a
  hard budget cap so it can never overrun" is unmet. (A GCP budget is an *alert*, not a hard stop.)
- ✅ **Fixed — the voice-fallback chain changed the narrator's gender.** Primary is Gemini TTS
  **Zubenelgenubi (male)** but `GOOGLE_TTS_VOICE` was `en-IN-Chirp3-HD-Kore` (**female**), so a
  double Gemini 503 silently swapped the channel's narrator. Now `en-IN-Chirp3-HD-Zubenelgenubi`
  in the repo variable, local `.env`, and documented in `.env.example`.
- ✅ **Fixed — 40% of a reel's shots were recycled.** `visuals` sized B-roll on a hardcoded 6.0s
  cut while `assembly` cuts at `CLIP_SECONDS` (~3.5s): a 30s reel wanted 11 slices, got 6 images,
  and replayed 5. The slicer's anti-repeat trick (advance the start offset) can't help on a Ken
  Burns pan over a single still. `assembly.slice_count()` is now public and the one source of
  truth. **Repeats per reel: 18s 3→0 · 25s 3→0 · 30s 5→0 · 35s 5→0.**
- 🟠 **`VISUAL_SOURCE=ai` is set at repo level**, so production runs Cloudflare Flux images, not
  the `photos` default the code assumes. Gemini's read of a real flop found garbled in-image text
  and a wrong flag on the White House — Flux artifacts, shipped to the channel.
- 📉 **Throughput is ~1.2 reels/day against a 4–5/day target** (46 produced across the last 80
  ideas; crons still commented out in `production.yml`, so cadence is gated on manual clicks).
- 🔴 **Fixed — the Groq fallback had been dead.** `llama-3.3-70b-versatile` was retired by Groq and
  404s, so rule 11's chain had no second link: once Gemini hit its **20 req/day per model** free
  cap, `llm.generate` failed outright. Every Groq test mocks `_gen_groq`, so 366 green tests
  coexisted with a broken fallback. Now **`openai/gpt-oss-120b`** (handles plain *and*
  `json_object`, both of which the pipeline needs), pinned by a live test. Verified in the real
  failure mode: Gemini 429ing, Groq answering.
- ⚠️ **Free Gemini is 20 requests/day per model** — worth remembering before raising cadence: one
  reel spends several LLM calls, so the ungrounded path leans on Groq sooner than expected.
- 🔬 **New capability found: Gemini reads YouTube URLs directly**, so the channel can now critique
  its own published Shorts on the existing free key (see the log entry's winner-vs-flop compare).
- 🟡 **Flux text artifacts: no clean fix found.** `flux-1-schnell` accepts only `prompt`/`steps`/
  `seed` — there is **no `negative_prompt`**, so "no text, no watermark" is just a positive token
  the model is free to ignore. A 3-way prompt A/B (current · text-words removed · tight-framing)
  was **inconclusive at the sample size the free quota allowed**. Unresolved; the real options are
  `VISUAL_SOURCE=photos` (free, clean, more generic) or a Workers AI model with a negative prompt.

### 2026-08-07 — Voice model chosen by ear: `gemini-3.1-flash-tts-preview` is now the default
Operator A/B'd all three renders from `tools/compare_voices.py` on an identical script and ranked
**3.1-flash > 2.5-flash > Chirp**. **352 pass, 4 skipped.**
- **`GEMINI_TTS_MODEL` now defaults to `gemini-3.1-flash-tts-preview`** in code and both workflows.
  Free on input and output; voice stays **Zubenelgenubi**.
- **Why promoting a *preview* model is safe here:** the operator's preference order is exactly the
  order the engine already degrades in. A 503 drops to `gemini-2.5-flash-preview-tts` **with the
  same voice** — the second-favourite sound, never a surprise — and only then to Chirp. That is
  the in-engine fallback added earlier today; it stops being a nicety and becomes load-bearing.
- ⚠️ **It is genuinely flaky:** 503 "high demand" on **3 of 4** attempts on 2026-08-07. Expect some
  reels to be voiced by 2.5-flash. Both are free, so this costs nothing but consistency.
- **`gemini-2.5-pro-preview-tts` 429s** on this key — no free tier and no billing quota. It stays
  the only paid option (~$1.27/mo at 3/day) and is not used.
- Verified end to end with nothing set: resolves to 3.1 + Zubenelgenubi and renders (8.44s).
  A test now pins that the fallback is a *different* model from the primary — otherwise a 503
  would just re-ask the same unavailable model and burn two of a 10/day budget.

### 2026-08-07 — Delivery-tag floor: ~40% of reels were shipping with no direction on the read
Operator observed the latest video "already had sarcastic and curious voice". **Checked the DB
instead of agreeing** — half right, and the other half was the useful part. **349 pass, 4 skipped.**
- **`[sarcastic]` was real** (present in scripts 159/157/156, with `[dry]`/`[deadpan]`/`[pause]`).
  **`[curious]` was not, and could not have been** — it wasn't allow-listed until earlier today, so
  `voice._style_text` stripped it before the engine. The curiosity was the style prompt plus the
  writer's conversational openers ("Alright, so in Jharkhand…") — curiosity in the WORDS, not a
  delivery instruction. So the widened tags don't add a missing quality, they let the writer
  **place** it deliberately.
- 🔴 **The real gap: 2 of the last 5 scripts (158, 154) carried NO delivery tags at all.** The
  prompt said "AT MOST 3 … fewer is better", which permits zero — on a channel whose whole premise
  is the delivery.
- **Fix — `_ensure_delivery_tag` + prompt now requires ≥1.** Guarantees `[serious]` on the "why it
  matters" turn: that line is both the emotional turn and the originality signal carrying the
  monetization gate (docs/08 §1), and it is the line most damaged by being read in the same dry
  register as the joke before it. A prompt asks; a guard makes it true (same reasoning as
  `MAX_STYLE_TAGS`). Toggle **`ENABLE_TAG_FLOOR`**, wired into both workflows.
- **Fail-soft by design:** if the payoff sentence can't be located confidently the script is left
  **unchanged** — a tag in the wrong sentence is worse than no tag. **Replayed over the last 10
  real scripts: 8 already-tagged untouched, 1 fixed (tag landed exactly on the bridge), 1 left
  alone.** Zero regressions.
- `voice.has_style_tag()` is now public so the scriptwriter asks **this** module rather than
  keeping its own copy of the allow-list — two lists drifting is exactly how `[curious]` came to
  be emitted-but-silently-stripped.
- **Separate finding, now visible:** script 158 has no "why it matters" bridge **at all** — a
  content gap, not a tag gap, and it shipped because nothing checked. `write_script` now logs a
  loud warning when the turn is missing: a script without it is a bare **summary**, which is what
  YouTube's inauthentic-content policy demotes and what the monetization gate turns on (docs/08 §1).
  **Warns, does not block** — accuracy already has a hard gate, and stacking a second blocking gate
  on a *soft* quality judgement would cost reels for something a human should eyeball (rule 14),
  especially right after deliberately loosening the other one.

### 2026-08-07 — Expressive range widened; the Gemini voice now survives a preview blip
Follow-through on the model audit below. **341 pass, 4 skipped.**
- **Tag vocabulary 7 → 12**, taken from Google's *documented* audio-tag list (not invented) —
  `[serious]`, `[curious]`, `[whispers]`, `[tired]`, `[mischievously]` join the existing set.
  **Both** TTS models accept audio tags, so this lands on the engine already in production; it is
  not gated on adopting the new model. Scriptwriter prompt teaches each tag's purpose; 3-tag cap
  unchanged, because the channel's failure mode is a narrator who announces the joke.
- **Excluded on purpose, now pinned by tests:** `[excited]`/`[amazed]`/`[giggles]` (hype vs the
  deadpan register) and `[crying]`/`[panicked]`/`[trembling]`/`[gasp]`/`[shouting]` (melodrama
  over real events → the tragedy-exploitation line in rule 6). All documented; all would work.
- 🐞 **A 503 used to cost the channel its voice.** `Zubenelgenubi` exists only on the Gemini
  engine, so a blip fell through to Chirp and silently changed how that reel sounded. Now retries
  once on the stable free model with the same voice before leaving the engine. 429 is explicitly
  NOT transient — same daily reset across models, so retrying just burns the reel's time.
- ⚠️ **`gemini-3.1-flash-tts-preview` is not usable as a primary right now** — 503 "high demand"
  on **3 of 3** attempts across ~40 minutes. Verified it DOES render when it answers (12.29s WAV
  through the real `voice.py` path). Safe to set `GEMINI_TTS_MODEL` to it: a 503 degrades to
  today's sound, not to Chirp. ⚙️ Operator: `python tools/compare_voices.py` and judge by ear.

### 2026-08-07 — Model audit: Gemini 3.6 Flash for scripts, grounding pinned to 2.5
Asked "what new tech can upgrade content/video quality". **Measured this account's real quota
rather than trusting listicles** — the useful answer was mostly "the model lineup moved under us".
**324 pass, 4 skipped.**
- ✅ **Ungrounded text → `gemini-3.6-flash`** (was 2.5-flash). Free quota is metered **per model**:
  3.6-flash, 3.5-flash, 3.5/3.1-flash-lite and 3-flash-preview all answered fine **while
  2.5-flash was returning `limit: 20`**. Better scripts *and* a second daily budget that stops
  competing with grounding.
- 🔴 **Grounding is NOT free on any 3.x model** — `google_search` 429s on all of them with an
  **empty quota-violation list** (no allowance), while 2.5-flash 429s with an explicit
  `limit: 20` (a real budget, just spent). New **`GEMINI_GROUNDED_MODEL`** knob pins it there.
- 🐞 **Footgun fixed:** grounding used to default to `GEMINI_MODEL`, and `.env.example` told the
  operator to *"bump it if RPD gets tight"* — that would have silently killed grounded ideation,
  the grounded scriptwriter **and** the fact-check gate in one edit.
- 🐞 **`thinking_budget=0` is rejected by Gemini 3.x** (400, verified live); replaced by
  `thinking_level=MINIMAL`. The Groq failover was **swallowing** the 400, so every Gemini call
  would have quietly become a Groq call while still looking healthy. Now picked per generation
  (`llm._thinking_cfg`) with a test.
- ❌ **Not viable at ≤$5/mo — measured, not assumed** (all 429 with no free allowance on this key):
  **Veo video gen** (docs list free tier as "Not available"; $0.03–0.40/sec ⇒ **$80–1000/mo** at
  3×30s/day), **image gen** (Nano Banana 2 / `gemini-3.1-flash-image`), **Lyria music gen**.
  Stock B-roll + the existing CC0 music beds stay.
- ⚙️ **Operator lever, free, not yet flipped:** `gemini-3.1-flash-tts-preview` (launched
  2026-04-15) is reachable on this key — **200+ inline audio tags** vs the 7 in `voice._STYLE_TAGS`.
  It 503'd ("high demand", transient — not a quota error) when probed. Set
  `GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview` to A/B it; the engine chain already falls back.

### 2026-08-07 — Fact-check gate retuned: it stops fabrication, not imprecision
🔴 **Operator report: the gate was failing most content ideas over "very minute differences".**
Root-caused and fixed. **322 pass, 4 skipped** (was 313, 5).
- **Why it over-blocked.** The gate was all-or-nothing (*any* item in `unsupported` → reel dead,
  idea `rejected`) sitting on top of a prompt that actively invited nitpicking: it listed "the real
  figure, date or name differs" and "overstates its scale or certainty" as failures, and declared
  **"absence of evidence is failure, not a pass"** — so a true story that one grounded search pass
  happened not to surface was killed. **A gate that stops everything protects nothing; it just
  stops the channel.**
- **Fix — severity grading.** The checker now sorts findings into two buckets and only the first
  blocks. **Blocking:** the event/ruling didn't happen · a named party blamed for something they
  didn't do · an invented quote/law/product/report/statistic · a number off by an order of
  magnitude, the wrong direction, or >~25% · a blame claim **no** source supports. **Minor
  (logged, reel ships):** rounding · a figure sources count differently · a date off by a few days ·
  wording/emphasis/over-confidence · a claim nothing contradicts but this pass couldn't confirm ·
  sources disagreeing with each other.
- **Two rules do most of the work**, both from the operator's own reasoning: **contradiction blocks,
  non-confirmation does not** ("I couldn't find it" ≠ "it's false"), and **two sources disagreeing
  is not proof the script is wrong** — both can be wrong, both can be right, or they measure
  different things. Only the *weight* of evidence blocks.
- **This loosens precision, NOT the anti-fabrication spine.** Rule 6's trade — the sharper the
  verdict, the more certain its facts — is about invented facts and misplaced blame. Those still
  block, and the live fabrication test still blocks.
- **Grading outranks the verdict word in both directions now:** "pass" + a blocking finding still
  blocks; "fail" + only nitpicks now ships. A `fail` naming *nothing* still blocks (nothing to grade).
- 🐞 **Fail-open found by a new test:** a checker returning one finding as a bare object
  (`"blocking": {...}` instead of a list) had it **silently dropped** — a real fabrication would
  have shipped. Bare strings and bare objects are both wrapped now.
- **New knob `FACTCHECK_SEVERITY`** (`critical` default | `any` = old block-on-everything), wired
  into `.env.example` **and both workflows**. `production.produce_one` logs waived issues per reel —
  ⚙️ **if that count climbs, the scriptwriter is drifting; fix it there, not by re-tightening the gate.**
- CLAUDE.md rule 6, [docs/08](docs/08-news-niche-playbook.md) §5 and CHANGELOG updated to match (rule 1).

### 2026-08-05 — Stale test count corrected in both docs
🔴 **README and STATUS disagreed with reality and with each other.** Ran the full suite:
**313 passed, 5 skipped** (209s). README claimed 199, STATUS claimed 311. Both corrected
(rule 1). No code changed — this is a docs-only fix. Found while sourcing a figure for a
public post, which is the cheap way to find it; the expensive way is publishing it.

### 2026-07-27 — Policy change: truth over neutrality, enforced by a fact-check gate
**Operator decision.** The "soft-positive" lean and the "strictly neutral / never take political
sides" rule are both **retired**. The channel may now reach a verdict and name who is
responsible. Higher demonetization risk accepted knowingly. **311 pass, 4 skipped.**
- **What was removed:** `NICHE_LEAN="soft-positive"` (read by nothing — a dead label) and the
  neutrality clause in the ideation + scriptwriter prompts. Politics, government action and court
  rulings are fully in scope.
- **What replaced it — a real gate, not a prompt request.** New **[`src/factcheck.py`](src/factcheck.py)**:
  an **independent, adversarial** grounded pass over the FINISHED script, run **before any render**
  (cheapest place to abort). Unsupported claim → reel **blocked**, idea marked `rejected` so it
  can't retry-loop. **"Cannot verify" counts as unsupported.** It is told to ignore tone entirely:
  a harsh verdict the evidence supports passes; a mild claim it can't source does not.
  Deliberately separate from the scriptwriter, which was grounding its own output — a model
  marking its own homework.
- **Trust the claim list over the verdict word:** a checker that lists problems then says "pass"
  is exactly the failure this gate exists to catch, so the list wins.
- ⚠️ **Quota reality, measured today:** the free `gemini-2.5-flash` bucket is **20 requests/day
  and was already exhausted** during this work. Grounded ideation, the grounded scriptwriter AND
  the fact check all draw from it (~8+/day at 3 Shorts). If it runs dry the gate **cannot run** —
  default is ship-unverified-and-log-loudly; **`FACTCHECK_STRICT=true`** blocks instead. Choose
  which risk you prefer.
- 🐞 **Found while wiring:** `tests/test_production.py` had started making **real network calls**
  and passing for the wrong reason (a 429 took the fail-open path). Now mocked — suite time for
  that file went 4.69s → 0.57s.
- **CLAUDE.md rule 6 and [docs/08](docs/08-news-niche-playbook.md) §5 rewritten to match** — the
  code contradicted the written contract, and rule 1 says fix the docs.
- **Sensitivity filter untouched:** communal/religious incitement, inflaming violence,
  rumour-as-fact, deepfakes, graphic tragedy exploitation, medical/financial advice as fact all
  remain excluded. This widened what may be *said*, not what may be *targeted*.

### 2026-07-27 — Voice chosen by ear: Gemini TTS + Zubenelgenubi is now the channel voice
- **Operator A/B'd 5 renders and picked `Zubenelgenubi` ("Casual")** over Kore/Schedar/Algenib/
  Charon. That voice only exists on the Gemini engine, so **`VOICE_ENGINE` now defaults to
  `gemini`** and `GEMINI_TTS_VOICE` to `Zubenelgenubi` — in code and in both workflows. The
  previous default `Kore` is documented as **"Firm"**, which is not the same thing as dry.
- **Style prompt rewritten** to Google's documented structure (audio profile → director's notes on
  pace/inflection → paralinguistic detail). Their guidance is explicit that naming an emotion
  underperforms describing what it *sounds* like, so the prompt is now mostly **restraint** — the
  failure mode for this channel is a narrator who announces the joke.
- **`tools/tune_voice.py`** renders one script across the voices whose documented characteristics
  suit deadpan, budget-aware (paces for 3 RPM, refuses to exceed 5 calls against the 10 RPD free
  tier, retries a transient 500 once so a blip doesn't cost a voice slot).
- **Still $0** — `gemini-2.5-flash-preview-tts` is free on input and output. Chirp 3 HD remains the
  first fallback, which matters because the Gemini TTS models are all **preview**; there's a test
  pinning that fallback.
- ⚠️ **Free tier is 10 requests/day.** At 3 Shorts/day that's 3, but clicking make-short 4+ times in
  one day will exhaust it — TTS then falls back to Chirp automatically (degraded voice, not a
  failure). **282 pass, 3 skipped.**

### 2026-07-27 — Expressive narration: sarcasm you can actually hear
Implements [the expressive-narration spec](docs/superpowers/specs/2026-07-26-expressive-narration-design.md).
**280 pass, 3 skipped.** Ships **inert** — `VOICE_ENGINE` stays `google`, so nothing changes until
the operator flips it.
- **Root cause of the no-op sanitiser:** `synthesize()` stripped every tag *before* dispatching, so
  no tag could ever reach an engine — and emotion tags aren't a Chirp feature anyway. The operator's
  instinct was right but aimed at the wrong engine: **inline audio tags are a documented Gemini
  Developer API feature**, and Chirp separately supports `[pause]` via its `markup` input field.
- **Tag handling is now per-engine** (`voice._filter_tags` + two allow-lists), because the control
  signals aren't portable: `[pause]`→Chirp `markup`, `[sarcastic]`→Gemini, both stripped for
  edge-tts/Kokoro. Caps enforced **in code** (`MAX_PAUSE_TAGS`/`MAX_STYLE_TAGS`, default 3) — a
  prompt asks, a guard is what makes it true. Invented tags are stripped, never forwarded.
- **New `gemini` engine** on the existing `GEMINI_API_KEY` + already-pinned `google-genai` — **no
  new dependency, no new credential.** Default `gemini-2.5-flash-preview-tts` is **free on input
  and output**; `gemini-2.5-pro-preview-tts` has **no free tier** (~**$1.27/mo at 3 Shorts/day**,
  25% of the cap). Deliberately **absent from `_ENGINE_ORDER`**: the chain is `[primary] + the rest`,
  so it's prepended only when selected and never enters the fallback path on its own.
- **Gemini TTS returns raw 24 kHz PCM, not WAV** — wrapped before use, or ffprobe/whisper can't
  read it.
- **Chirp:** `input.markup` when the voice is Chirp *and* a pause tag survived; `GOOGLE_TTS_SPEAKING_RATE`
  clamped to [0.25, 2.0]; a markup rejection **retries once as plain text** so a syntax surprise
  costs the timing, never the voice.
- **Length-guard bug fixed:** `[pause long]` contains a space, so whitespace splitting yielded
  `[pause` + `long]` and counted **both as spoken words** at all three cap sites — silently
  shrinking the 25–30s budget. `_visible_words` now matches tags against the whole string.
- **`tools/compare_voices.py`** renders Chirp / Flash / Pro side by side — the Flash-vs-Pro call is
  a judgement about how the sarcasm lands, so it's made by ear, not asserted.
- ⚙️ **Operator follow-ups:** (1) run `python tools/compare_voices.py`, then set `VOICE_ENGINE=gemini`
  (+ `GEMINI_TTS_MODEL` if Pro wins); (2) check the **free-tier TTS rate limits in the AI Studio
  dashboard** — unpublished in the docs, and grounded ideation has blown Gemini RPD before, so set
  `GEMINI_TTS_API_KEY` to a second key if the pools are shared (rule 13); (3) set `DAILY_REEL_CAP`
  and `APPROVAL_CAP` to **3** to match the new volume (both still default to 5).

### 2026-07-26 — Audit of the Content-Engine overhaul: 3 blockers fixed, SFX retuned, cards wired
Full audit of the same-day overhaul (below). Everything green: **242 pass, 2 skipped**.
- **🔴 GitHub Models was dead code** — wrong host (`models.inference.ai.azure.com` is the retired
  Azure preview; correct is `https://models.github.ai/inference/chat/completions`) and a bare
  `gpt-4o-mini` where the API requires a **publisher prefix** (`openai/gpt-4o-mini`). Verified
  against GitHub's REST docs. Also: the token needs scope **`models: read`** (in Actions,
  `permissions: models: read`). Corrected the log claim below — **Anthropic is not in the GitHub
  Models catalog**, so this was never a route to Claude (and never a rule-4 question).
- **🔴 Renamed every knob to `GH_*`** (`GH_MODELS_KEY`/`ENABLE_GH_MODELS`/`PREFER_GH_MODELS`/
  `GH_MODEL`): GitHub **rejects secret and variable names starting with `GITHUB_`**, so the
  original names could never have been created as Actions secrets.
- **🔴 Dropped `GH_PAT` from the credential chain** (rule 5). That is the Telegram bot's Actions
  read+write PAT and this repo's Actions hold the YouTube/Supabase/Telegram secrets — it must
  never be sent to a third-party inference endpoint. Now `GH_MODELS_KEY` → `GITHUB_TOKEN` only.
- **GitHub Models is now OPT-IN** (`ENABLE_GH_MODELS`/`PREFER_GH_MODELS`), not "on whenever a
  token exists". An unconfigured provider silently in the chain burns a doomed round-trip per call
  and *delays the Groq failover* on exactly the Gemini-RPD outages it exists to survive (rules 11/13).
- **🔴 `pillow` was missing from `requirements.txt`** while `graphics.py` imported it — green
  locally, `ImportError` in CI. Pinned `pillow==12.2.0` (rule 10).
- **SFX retuned — it would have sounded cheap and clipped the voice.** Was: a sting on *every*
  cut (~9 per reel) at volume 0.5–0.6, plus a whoosh at **t=0 over the hook**. Now: every **2nd**
  cut, volume **0.18**, and a **1.5s lead-in** so nothing competes with the hook. Measured live:
  4 events across 28s at 6.3/12.6/18.9/25.2s.
- **Added a limiter after the mix.** `amix ... normalize=0` sums without headroom. **Proven with
  real FFmpeg:** narration 0.95 + SFX 0.30 summed → peak **+0.0003 dB (hard-clipped)**; with
  `alimiter=limit=0.95:level=0` → **−0.445 dB, no clipping**. Narration is not attenuated.
- **Scriptwriter JSON example fixed**: the caption template contained **raw newlines** inside a
  JSON string (invalid JSON) and taught the model to emit the same. Now escaped `\\n`, plus an
  explicit instruction. `_parse_llm_json`'s `strict=False` was masking this on the grounded path.
- **`graphics.py` was dead code** — nothing imported it, yet the log claimed shipped stat cards.
  Now wired into `subtitles.py` behind **`ENABLE_GRAPHIC_CARDS` (default OFF)**: shares
  `_card_events` with the ASS path (one timing rule, no double-draw), overlays each PNG via
  `-loop 1` + `enable='between(t,…)'` + `-shortest`, and **falls back to a full-featured ASS
  text-card burn** on any failure. **Verified with a real 1080×1920 render** — card visible in
  its window, absent outside it, duration unchanged.
- **`audio_sfx` hardening**: seeded RNG **per generator** so assets are byte-identical across
  runs (a shared module-level `Random` made output depend on call order — caught by a new test);
  bulk `array` PCM write (measured **0.42s → 0.19s**, byte-identical); per-effect decode cache;
  bad/out-of-range events skipped instead of raising. Dropped dead `_SFX_NAMES` + `extra_events`.
- **Every new knob wired** into `.env.example` **and both workflows** — `ENABLE_SFX`, `SFX_VOLUME`,
  `SFX_EVERY_N_CUTS`, `SFX_DIR`, `ENABLE_GRAPHIC_CARDS`, `ENABLE_CHANNEL_TAGS`, `CAPTION_FONT_FILE`,
  and the four `GH_*` keys. `ENABLE_SFX` defaults true, so it previously would have shipped on the
  next cloud run **with no repo-variable kill switch**.
- **+27 tests (215 → 242).** ⚠️ Note `_clean_tts_text` strips `[sarcastic]`/`<sfx:…>` tags that
  **nothing in the pipeline emits** — it is purely defensive, not an active feature.

### 2026-07-26 — Content Creation Engine Overhaul & GitHub Models Integration
> ⚠️ Superseded in part by the audit entry above — read it first. The GitHub Models endpoint,
> model naming, env-var names and Claude-availability claim below were all wrong; SFX levels and
> the "PIL stat card overlays" feature were not production-ready as written.
- **Witty Roasting Scriptwriter (`src/scriptwriter.py`)**: Upgraded `_PROMPT_N` to adopt a Daily Show / Phil DeFranco edutainment roasting style. Enforced disorienting opening hooks (0–2s), sarcastic witty commentary, retention bridges ("Here's why it actually matters..."), and seamless loop-back endings.
- **Expressive Voice Sanitizer (`src/voice.py`)**: Added `_clean_tts_text()` to strip embedded emotion tags (`[sarcastic]`, `[sigh]`) and SFX markers (`<sfx:...>`) before TTS synthesis, preserving natural dramatic sentence pacing.
- **Procedural SFX Audio Generator (`src/audio_sfx.py` [NEW])**: Added wave synthesis generators for 5 core sound effects (`whoosh`, `pop`, `ding`, `boom`, `click`) and audio track mixing.
- **Multi-Track Audio & Video Assembly (`src/assembly.py`)**: Updated `src/assembly.py` to automatically mix SFX transition sweeps (`whoosh`, `click`) at clip cut boundaries along with narration and ducked background music.
- **Free GitHub Models API Integration (`src/llm.py`)**: Added support for GitHub Models API using a GitHub token — see the audit entry for the corrected endpoint, model naming, and env vars.
- **PIL Graphic Stat Cards (`src/graphics.py` [NEW])**: Added `src/graphics.py` for rendering high-contrast RGBA stat cards with rounded corners, drop shadows, and Montserrat typography.
- **+4 new tests.**

### 2026-06-29 — Ideation diversity & virality (two-stage, news-anchored)
- **Root-caused the "similar + not viral/trendy" complaint** with live evidence: ideation made the
  whole batch in ONE LLM call (mode-collapse → near-duplicate ideas); dedup was exact-title only; the
  **Google Trends feed was returning junk** ("weather", "june 2026 calendar", "wimbledon",
  "germany vs paraguay") that the prompt told the model to *prefer*; and a grounding outage (Gemini
  RPD) silently dropped ideation to stale training knowledge.
- **Fix — Approach A (news-anchored two-stage):**
  - `trends.py`: best-effort **noise filter** (weather/calendar/festival-date/`X vs Y`/scorecard/
    lottery) + demoted trends from "prefer" to a supplementary flavour signal. The **news feed is the
    primary anchor** (verified live: 12 real, current, diverse stories).
  - `ideation_fallback.py`: **Stage 1** (`_select_stories`, Groq via `prefer_groq`) clusters real
    headlines into N **distinct** share-worthy stories → **Stage 2** (existing grounded→ungrounded)
    expands one idea per story. Diversity is now structural, not hoped-for. Freshness no longer depends
    on grounding succeeding.
  - **`share_score`** virality field (0–1, "would someone share this?"); on-demand ranking is
    share-first, est-second (`_rank_key`). It's ranking-only — **projected out before DB insert**
    (`_to_rows`), so **no DB schema change**.
  - **Token-overlap dedup backstop** (Jaccard ≥ 0.6) catches same-story near-duplicates.
  - Prompts rewritten (both stages): one-idea-per-story, spread categories, share test + curiosity-gap
    — **all rule-6 hard guards intact** (no fabrication, neutral framing, ≥2 real sources).
- **+13 tests; 204 pass** (gated live tests deselected). No workflow changes. Branch
  `feat/ideation-diversity-virality`. Spec/plan in `docs/superpowers/{specs,plans}/2026-06-29-*`.
- **Follow-up (same day): score calibration.** Stage 2 now ranks ideas relative to each other and
  spreads `share_score`/`est_score` across 0–1 (was saturating at 1.0 → flat ranking). Verified live
  (0.95 → 0.55 spread). +1 test (205 pass).

### 2026-06-16 — Chirp key FIXED (corrupted secret) + 25-30s sarcastic tone
- **Voice root cause corrected**: the cloud `API_KEY_INVALID` was a **corrupted secret**, NOT an IP
  restriction (operator's key has Application restrictions = None, confirmed by screenshot). Cause:
  Windows PowerShell 5.1 mangled the piped value (`$key | gh secret set`) with UTF-16/BOM. Re-set via
  `gh secret set --body` (clean argv); new **`verify-tts` workflow** confirmed from CI:
  `OK: key works (30 en-IN Chirp 3 HD voices)`. So Chirp 3 HD fires on the next run — no operator action.
- **Length → 25-30s**, **tone → sarcastic but serious & humorous** (operator directive): `scriptwriter`
  persona + structure rewritten (~65-75 words, dry wit, facts straight, no-harassment guard kept);
  `ideation` sized to 25-30s. Word guard now ~50-90.
- **Music**: still none. Bensound blocks direct download (403, won't circumvent); Pixabay tracks got
  Content-ID-claimed; CC0 file URLs aren't reliably auto-fetchable here. Claim-safe fix = **YouTube
  Audio Library** (manual, ~3 min → drop files in `assets/music/`).
- **174 pass, 2 skipped.**

### 2026-06-16 — First live short-form run (idea 88): news works; 2 fixes shipped
- **Ran make-short on the new code** → https://www.youtube.com/shorts/sO25uMROuFw. **News topics
  now work** (`news: 38 headlines`); published OK; cards/karaoke/short-form structure all fired.
- **Grounded LLM truncation FIXED** (`llm.py`): `_gen_gemini_grounded` wasn't disabling
  gemini-2.5-flash "thinking", which ate `max_output_tokens` and truncated the grounded script
  mid-sentence → forced the Groq fallback → an 11-word **6.4s** reel (under the 12-20s floor).
  Set `thinking_budget=0` (mirrors `_gen_gemini`). Plus a **HARD 30-50 word / 12-20s floor** in the
  scriptwriter prompt so no fallback ships a one-liner.
- **Chirp 3 HD — root cause CONFIRMED** (the new error logging worked): CI returned
  `"reason": "API_KEY_INVALID"` while the SAME key returns 200 locally → the key has an
  **Application/IP restriction** (Google reports an IP-blocked key as "invalid"). Re-set the secret
  via `--body` (exact 39-char key) to rule out corruption. ⚠️ **Operator: remove the key's
  Application restriction** — Console → Credentials → key → **Application restrictions = None**
  (keep API restriction = Cloud TTS). GitHub Actions IPs are dynamic; any IP/referrer rule blocks them.
- **173 pass, 3 skipped** (one live-LLM test skipped on a Gemini 503).

### 2026-06-15 — Short-form pivot (12-20s on-point bites) + cloud voice/news hotfix
- **Format → 12-20 SECOND Shorts** (operator directive): `scriptwriter` now writes a tight ~30-45
  word bite — HOOK → THE NEWS → one honest "why it matters" clause → 2-3 word CTA (was ~110-130
  words / 45s). `ideation` proposes TRENDING, single-development stories sized to land in 12-20s.
  The reel auto-shortens to the narration, so the whole Short follows. Kept ONE why-it-matters
  clause so it stays original (monetization gate, rule 6) — not a bare summary. `key_points`
  trimmed to 2-3; word guard now ~30-45.
- **Cloud hotfix** (from inspecting the last live run, idea 85 → published but voice/news fell back):
  Chirp 3 HD 400'd in CI and fell back to edge-tts. Diagnosed: NOT length (908 B), NOT content
  (re-sends 200), NOT key whitespace — the cloud key differs; **prime suspect a key application/IP
  restriction**. `_synthesize_google` now surfaces Google's real error body (was an opaque "400
  Client Error") + strips/encodes the key. `news.fetch_headlines` no longer breaks when the
  `NEWS_RSS_URL` repo var is empty (it became an invalid URL). Secret re-set cleanly.
- ⚠️ **Operator action:** Google Cloud → Credentials → the API key → **Application restrictions =
  None** (keep API restriction = Cloud Text-to-Speech only); GitHub Actions IPs are dynamic. Then
  re-run a make-short — logs now print Google's exact reason if Chirp still fails.
- **174 tests pass.**

### 2026-06-15 — Content-quality overhaul Phase B (story-specific visuals + curated topics) + Chirp 3 HD LIVE
- **On-screen key-point cards** (`scriptwriter.py` → `subtitles.py` → `production.py`): the
  scriptwriter emits 3-5 ultra-short `key_points`; subtitles burns them as SPARSE bold mid-frame
  cards (new `Card` ASS style, distributed across the reel after the hook window). Layers
  story-specific TEXT over the generic stock B-roll — the core fix for the "AI-slop" look. Knobs
  `ENABLE_TEXT_CARDS`/`CARD_SECONDS`. Verified with a real karaoke+cards burn (live test green).
- **Curated news topics** (`src/news.py` → ideation): ideation is now seeded by real Google News
  RSS headlines (India locale, no key) IN ADDITION to trends — ideas track actual current stories,
  not just trending search noise. Best-effort (rule 11); override via `NEWS_RSS_URL`.
- **Chirp 3 HD LIVE** (operator added the key): verified `en-IN-Chirp3-HD-Kore` synthesizes via the
  real chain (5.8s WAV). Set local `.env` + **GitHub secret `GOOGLE_TTS_API_KEY` + var
  `GOOGLE_TTS_VOICE`** so cloud runs use it. 30 en-IN Chirp3-HD voices available — A/B by changing
  the var (`tools/list_google_voices.py`, which now loads `.env`).
- **171 pass, 2 skipped.** New knobs wired into both workflows + `.env.example`. Branch
  `feat/phase-b-visuals-topics`. **Phase C remains** (metadata trims, optional Telegram hot-take
  lever, optional data-viz/maps). Spec: `docs/superpowers/specs/2026-06-15-content-quality-overhaul-design.md`.

### 2026-06-15 — Content-quality overhaul Phase A (voice + honest scripts + karaoke captions)
- **Voice → Google Chirp 3 HD** (`voice.py`): near-human en-IN narration via Google Cloud TTS v1
  REST + API key. `synthesize()` is now an ordered fallback **chain** google → edge-tts (en-IN
  Neerja) → Kokoro, resolved at call time (rule 11). Helper `tools/list_google_voices.py`. Free
  within 1M chars/mo (≈ our whole volume), so the $5/mo cap is headroom.
- **De-hyped content** (`scriptwriter.py`, `ideation_fallback.py`): replaced the "max hype"
  clickbait framing with honest curiosity + promise↔payoff alignment + a required "why it matters"
  human take (`ENABLE_HUMAN_ANGLE`) — a quality fix AND the anti-"AI-slop" monetization signal
  (2026 Inauthentic-Content policy). Accuracy hard-line unchanged; `HOOK_MIN_SCORE` default 8 → 7.
- **Karaoke captions** (`subtitles.py`): active-word highlight (ASS `\kf`) in a bundled OFL
  Montserrat font (`assets/fonts/`, libass `fontsdir`). Knobs `CAPTION_FONT`/`CAPTION_HIGHLIGHT_COLOR`;
  `CAPTION_WORDS` default 2 → 3. Verified with a real karaoke burn (live test green).
- **Budget $0 → ≤ $5/mo** (CLAUDE.md rule 2 + README + docs/01/04/07 synced). Both workflows wired
  with the new env (`VOICE_ENGINE`, `GOOGLE_TTS_*`, `ENABLE_HUMAN_ANGLE`, `CAPTION_FONT`, …).
  **161 pass, 2 skipped** (gated live upload/LLM). Branch `feat/phase-a-content-quality`.
- **Operator follow-ups:** (1) create a Google Cloud project → enable Cloud TTS → make a
  TTS-restricted API key → **set a $5 budget cap + alert**; (2) `python tools/list_google_voices.py`,
  pick a voice; set repo secret `GOOGLE_TTS_API_KEY` + var `GOOGLE_TTS_VOICE`. Until then the chain
  auto-uses edge-tts en-IN (already better than the old Kokoro int8 `af_heart`). Spec:
  `docs/superpowers/specs/2026-06-15-content-quality-overhaul-design.md`. **Phase B/C remain**
  (story-specific visuals, curated news-RSS topics, metadata trims, optional Telegram hot-take lever).

### 2026-06-11 — Webhook callback support + getUpdates 409 conflict fixes
- **Webhook callback query handling**: processed inline button callback queries (`a:`, `r:`, `p:`) in Vercel Telegram bot with HTML parse_mode enabled, so Telegram handles bold/italic formatting of the edited messages correctly.
- **Webhook mode in production**: added `TELEGRAM_APPROVAL_MODE` support to prevent the production orchestrator (`make_on_demand` and `run`) from calling `getUpdates` (which raises 409 Conflict if webhook is active) and instead poll Supabase for decisions.
- **Allowed updates fix**: updated `tools/set_telegram_webhook.py` to register both `message` and `callback_query` updates with Telegram.
- **CI / Workflows configuration**: forwarded `TELEGRAM_APPROVAL_MODE: ${{ vars.TELEGRAM_APPROVAL_MODE }}` in the production workflow and set it to `webhook` in the make-short workflow. All 153 tests passed locally.

### 2026-06-11 — Channel branding: description footer + (manual) channel About/keywords
- **Description footer** (`production._with_footer`): every Short's description now ends with a
  brand + subscribe-CTA + 3 brand hashtags block (`#ButItMatters #NewsShorts #WhyItMatters`).
  Complements — never duplicates — the scriptwriter caption (hook/sources/AI-disclosure) and
  publish's `#Shorts`; total stays under YouTube's 15-hashtag cap. Idempotent + length-capped
  (≤4900 chars). Toggle `ENABLE_DESC_FOOTER`; override copy via `DESCRIPTION_FOOTER` (both wired
  into the workflows). **17 production tests pass.**
- **Operator (manual, no code):** set the channel **About** description + hidden **keywords**
  (drafted in chat) in YouTube Studio — copy lives in the conversation, not a repo file.

### 2026-06-11 — Telegram control bot LIVE on Vercel ✅
- Deployed `telegram-bot/` to Vercel (project **telegram-bot**, team shaan-alphas-projects) via the
  CLI from the isolated dir (stdlib-only, no heavy deps). Webhook registered + the operator's 7 env
  vars set; secret-token gate verified (a POST without `WEBHOOK_SECRET` → 401). **Confirmed working
  end-to-end** — `/help`, `/stats`, `/today` reply in Telegram.
  - Webhook: `https://telegram-bot-gilt-omega.vercel.app/api/telegram`
  - Redeploy after code/env change: `vercel deploy --prod --yes --cwd telegram-bot`
  - Re-register webhook: `python tools/set_telegram_webhook.py <url>/api/telegram`
- Fixed a Windows-console crash in `set_telegram_webhook.py` (non-ASCII `→`/emoji in print → cp1252
  UnicodeEncodeError) — the webhook had already registered; output is now ASCII-safe.

### 2026-06-10 — Telegram control bot (Vercel webhook) — code done, deploy pending
- **New instant command surface** (operator chose webhook over polling): `telegram-bot/api/telegram.py`,
  a **stdlib-only Vercel serverless function** (zero deps; isolated in its own dir so Vercel doesn't
  install the pipeline's heavy `requirements.txt`). Commands: **`/makeshort [n]`** (dispatches the
  make-short Action via the GitHub API), **`/today`** (Shorts published today, IST), **`/stats`**
  (totals + today + top performer), **`/pending`** (ideas awaiting approval), **`/latest`**, **`/help`**.
- **Security:** rejects requests without the `X-Telegram-Bot-Api-Secret-Token` (WEBHOOK_SECRET) and
  ignores any chat ≠ `TELEGRAM_CHAT_ID`; always 200s so Telegram never retry-storms.
- Helper `tools/set_telegram_webhook.py` registers the webhook + secret. Setup guide in
  `telegram-bot/README.md`; new env documented in `.env.example` (`WEBHOOK_SECRET`/`GH_PAT`/`GH_REPO`).
  **8 bot tests pass** (parse/dispatch/clamp/IST-date/auth gate); suite green.
- ⏳ **Operator to finish deploy:** (1) create a GitHub fine-grained PAT (Actions: read+write);
  (2) deploy `telegram-bot/` to Vercel (Root Directory = `telegram-bot`); (3) set the 7 Vercel env
  vars; (4) run `set_telegram_webhook.py <vercel-url>/api/telegram`. Then `/help` the bot.

### 2026-06-10 — Gemini RPD blown → route no-web tasks to Groq (reserve Gemini for grounding)
- **Quota finding:** Gemini 2.5 Flash free **RPD hit 30/20 (over limit)** — text calls now 429.
  The Gemini→Groq failover (rule 11) keeps the pipeline alive, but grounded web research is
  Gemini-only, so accuracy degrades to ungrounded while exhausted. The new hook judge added load.
- **Fix (operator: don't make output worse):** added `llm.generate(prefer_groq=True)` — tries
  **Groq first**, Gemini second. Routed the two **no-web** tasks there: **hook punch-up**
  (`scriptwriter`) and **B-roll keyword extraction** (`visuals`). The accuracy-critical **grounded
  research stays on Gemini**, so quality where it matters is unchanged; Gemini's scarce RPD is now
  reserved for it (rule 13). Failover still intact (Groq→Gemini if Groq fails).
- **Upgraded the Groq-routed prompts** for llama-3.3-70b: stronger hook-doctor instructions
  (explicit score→rewrite steps, strict no-fact-change rule, JSON-only) and richer keyword
  translation (added oil/energy + sport stand-ins, story-beat ordering, strike abstract words).
  **Verified live on Groq** (valid JSON, scored a strong hook 9 and correctly left it). **139 pass.**
- ⚙️ Optional extra relief (no code): set repo var `GEMINI_MODEL` to a higher-free-RPD model
  (e.g. `gemini-2.0-flash`) — verify current limits first.

### 2026-06-10 — Learning loop LIT with real analytics
- Ran `analytics.collect_stats()` against the live channel → **6 real snapshots** recorded
  (views/likes/comments) for the published Shorts. `db.top_performing_titles()` now returns real
  winners ranked by views: "Venezuela vs Iraq Oil Export…" 994, "Argentina FC vs Iceland…" 956,
  "Delhi Air…" 24, "Kerala's New CM…" 7, gas/monsoon 3 each → **ideation now biases toward the
  oil/sports/conflict winners**. Old posts feed back the *idea* title (predate `scripts.title`);
  new reels will feed back the punchy *published* title (winning STYLE). ⚙️ Enable `analytics.yml`
  daily cron (uncomment `schedule:`) to keep this fresh automatically.

### 2026-06-10 — Dramatic voice pacing (Kokoro sentence-wise + payoff beat)
- **`voice.py`:** Kokoro narration is now synthesized **sentence-by-sentence** and rejoined with
  controlled silence — **tighter `PAUSE_BETWEEN` (0.18s)** mid-script and a **longer
  `PAUSE_BEFORE_PAYOFF` (0.5s)** beat before the final line. Exact + in-memory (Kokoro returns
  raw samples; no ffmpeg). Single-sentence scripts and any paced-synth error fall back to one-shot;
  edge-tts fallback stays one-shot. Toggle `ENABLE_DRAMATIC_PACING`.
- **Measured live:** per-sentence speech = 7.45s; one-shot Kokoro already adds ~0.87s of uniform
  pauses (8.32s total). Our version **redistributes** that (snappier mid-script + a clear beat
  before the payoff) for ~the same length — drama without burning the <60s budget. Knobs wired
  into both workflows. **137 pass, 2 skipped.**

### 2026-06-10 — Hook quality: seamless loop ending + LLM scroll-stop judge
- **Seamless loop ending (`template-N`):** the CTA now loops back into the hook so an auto-replay
  flows from the last line into the first — Shorts replays inflate watch-time/views for free.
- **Scroll-stop hook judge (`scriptwriter._punch_up_hook`):** before spending a render, a cheap
  Gemini/Groq pass rates the opening hook 1-10 and, only if weak (< `HOOK_MIN_SCORE`, default 8),
  rewrites the **title + opening** for more punch. **Hard accuracy guard:** the prompt forbids
  adding/changing any fact, the sources/caption are untouched, and it's **fail-soft** (any error,
  a strong score, or an out-of-range rewrite keeps the original). Toggle `ENABLE_HOOK_JUDGE`.
  **Verified live:** "India New Natural Gas Policy Explained" → "Your Cooking Fuel is About to
  Change Forever (and Save You Money!)" with all facts preserved (score 7 → rewritten).
- Knobs wired into both workflows: `ENABLE_HOOK_JUDGE`. **133 pass, 3 skipped.**

### 2026-06-10 — Free visual upgrades: frame-1 hook banner + faster staggered cuts
- **Frame-1 hook banner (`subtitles.py`):** the punchy title is now burned as a bold YELLOW
  top-of-frame banner for the first `HOOK_SECONDS` (1.8s). The first frame IS the in-feed
  thumbnail, so this is the biggest free CTR lever. Banner text is emoji-stripped (so libass
  never shows tofu), UPPERCASED, and word-wrapped (≤16 chars/line, ≤3 lines); word captions
  stay at the bottom (no overlap). `production` passes `script.title` as the hook; toggle via
  `ENABLE_HOOK_CAPTION`. **Verified with a real render** — extracted frame 1 showed
  "OIL EXPORT WARS" over on-topic refinery B-roll.
- **Faster, staggered cuts (`assembly.py`):** cut length is now `CLIP_SECONDS` (default **3.5s**,
  was a fixed 6s) — fast pattern-interrupts lift Shorts retention, and shorter single-clip use is
  *more* copyright-safe (docs/08 §3). When a clip repeats (few clips, many cuts), its start offset
  advances one slice and wraps, so the repeat shows a DIFFERENT segment, not the same opening
  twice. Clamped to [1.5, 8.0]s; filtergraph cap raised to 60 slices. Live full-reel render passes.
- New repo-variable knobs wired into both workflows: `ENABLE_HOOK_CAPTION`, `HOOK_SECONDS`,
  `CLIP_SECONDS`. **129 pass, 2 skipped.** (Suggested next free wins, not yet built: LLM
  "scroll-stop" hook judge before render; 2-3 hook variants; loop-back ending; dramatic voice pacing.)

### 2026-06-10 — Virality retune from first real analytics (operator: max hype)
- **Analyzed first real traffic.** Matched the YouTube dashboard to the DB: the published title is
  the scriptwriter's, not the idea title. Winners were **conflict/curiosity** framed — "Oil Export
  Wars" (1,032 views, from idea "Venezuela vs Iraq Oil Export Differences Explained") and "Messi's
  Nightmare Debut" (961) — vs dry explainers that flopped ("Kerala's New CM" 8, PNG gas rule 3).
  Two signals: **title framing** (drama > explainer) and **topic pull** (global/emotional > local/wonky).
- **Closed a real learning-loop gap:** `scripts` had no `title` column, so the winning *published*
  titles were never stored — the loop could only learn dry idea topics. Added `scripts.title`
  (migration `add_title_to_scripts`), persist it in `scriptwriter`/`db.insert_script`, and
  `db.top_performing_titles()` now returns the published title + views (`"title" — N views`).
- **Retuned generators (operator chose MAX HYPE):** scriptwriter title formulas (power-words,
  curiosity gap, conflict, ALL-CAPS, "watch till the end"); caption first line = curiosity hook;
  spoken hook opens a loop paid off at the end. Ideation now picks topics by **scroll appeal** and
  seeds punchy titles, not "X explained". **The one hard line kept: accuracy** — hype the framing,
  never fabricate a fact (a strike kills reach). **123 pass, 2 skipped** (incl. live DB cycle).
- ⚠️ **Operator-owned risk:** max-hype/mismatch framing raises clickbait-suppression risk; accuracy
  guard is the demonetization backstop. **Action to light up the loop:** run `analytics.yml`
  (currently 0 snapshots) so winning titles actually feed back into ideation.

### 2026-06-10 — Deep audit: fixes + grounded scriptwriter + clean-slate data
- **Audited the whole system.** Fixed: (1) duplicate-publish gap → idea-level idempotency before
  scripting (`db.get_published_post_for_idea`); (2) pinned `requirements.txt` (rule 10);
  (3) `config.get_bool` so `AI_DISCLOSURE=1` can't silently disable disclosure; (4) CHANGELOG/
  version → **v0.2.0** (tagged); (5) CI caches Kokoro+whisper+pip (~260 MB/run saved).
- **Accuracy hardened (public-channel risk):** scriptwriter is now **web-grounded** — it verifies
  the premise via search and won't repeat a fabricated one, falling back to ungrounded JSON mode.
  Verified live (142-word script, web-verified title).
- **Wiped all test data** from Supabase (analytics/posts/scripts/ideas → 0) so the analytics
  learning loop starts clean from real PUBLIC videos only. **Operator: delete the unlisted test
  Shorts in YouTube Studio** (esp. the fabricated "Claude Fable 5" one).
- **116 tests pass.** Open (low/optional): `make_on_demand` re-sends undecided pending on repeat
  triggers; image clips are encoded twice (visuals→assembly).

### 2026-06-10 — Analytics learning loop + polish/tuning knobs
- **Analytics (`src/analytics.py`):** `collect_stats()` pulls each published Short's public
  views/likes/comments (YouTube `videos.list`, readonly) into the `analytics` table;
  `db.top_performing_titles()` joins analytics→posts→scripts→ideas to rank winners, which
  **ideation now injects into its prompt** to make fresh variants of what works. `analytics.yml`
  wired to run it (manual; daily cron ready to uncomment). Verified live (9 snapshots, join works).
- **Polish:** AI-image prompt has a stronger cinematic default, tunable via `IMAGE_STYLE`;
  captions now **group ~`CAPTION_WORDS` words (default 2)** and strip stray punctuation (fixes
  fragments like "-level"). Exposed `IMAGE_STYLE`/`CAPTION_WORDS`/`KOKORO_SPEED`/`MUSIC_VOLUME`
  as repo-variable knobs in the workflows — look/feel tunable with zero code. **115 tests pass.**
- ⚙️ **Tuning knobs (repo Variables):** `IMAGE_STYLE` (AI look), `CAPTION_WORDS` (1=karaoke,
  2-3=readable), `KOKORO_SPEED` (e.g. 0.95 slower/natural), `MUSIC_VOLUME` (0.10 default),
  `KOKORO_VOICE`, `VISUAL_SOURCE`, `YOUTUBE_PRIVACY`.

### 2026-06-10 — Channel went PUBLIC + SEO (titles + tags) + Cloudflare AI visuals live
- **`YOUTUBE_PRIVACY=public`** — Shorts now publish publicly.
- **Cloudflare AI images working in CI** (after removing the token's IP filter; verified 200).
  `VISUAL_SOURCE=ai` → true on-topic Flux images + Ken Burns; auto-falls back to Pexels photos.
- **SEO discoverability:** scriptwriter now also outputs an optimized **`title`** (click-worthy,
  <=80 chars) and **`tags`** (10-15 search keywords). `production._build_metadata` prefers the SEO
  title and merges hashtags+tags (de-duped); `publish._cap_tags` keeps tags within YouTube's
  ~500-char budget. **111 tests pass.**

### 2026-06-10 — Video assessment → fixes: anti-hallucination + photo/AI visuals
- **Assessed a generated Short** (frames + whisper transcript). Findings: (1) 🔴 CRITICAL —
  fabricated news: it invented a fake "Claude Fable 5" Anthropic launch ("according to
  Anthropic…"); (2) clips off-topic (Gundam statue / Nashville skyline for an AI story);
  (3) minor caption split ("-level"). Assessed video then deleted per operator.
- **Anti-hallucination guardrails** added to ideation + scriptwriter prompts (only REAL,
  source-supported facts; never invent products/versions/quotes/attribution).
- **Visuals upgrade — photos + Ken Burns (default) + optional AI:** free AI image gen is now
  paywalled (Pollinations 402 queue-gate, Gemini image 429). So `visuals.fetch_broll` now has
  `VISUAL_SOURCE`: **`photos`** (default — Pexels stock PHOTOS, far more abundant/on-topic than
  video, rendered with a Ken Burns slow-zoom to 1080×1920), **`ai`** (Cloudflare Workers AI Flux —
  free tier, needs `CF_API_TOKEN`+`CF_ACCOUNT_ID`), or **`video`** (old stock-video). Image sources
  fall back to stock video on failure (rule 11). Verified live (on-topic courtroom/parliament/
  rocket Ken Burns clips). Workflows pass the new env. **108 tests pass.**
- ⚙️ **To enable true AI images:** make a free Cloudflare account → Workers AI → create an API
  token + grab the account id → add repo secrets `CF_API_TOKEN`/`CF_ACCOUNT_ID` and repo var
  `VISUAL_SOURCE=ai`.

### 2026-06-09 — Upgrades from deep research: trending topics + disclosure trim
- Deep-research workflow hit a session limit, but direct verified searches answered all 4 asks.
- **Trending (new `src/trends.py`):** pulls live Google-Trends-India RSS (no key/quota) and seeds
  the ideation prompt → timely, current ideas instead of generic evergreen. Best-effort (rule 11).
- **Topic policy — operator override:** user chose to INCLUDE politics/government/court topics
  (against the original soft/positive playbook). Loosened the ideation filter to allow them
  **only with strictly neutral, well-sourced framing**; kept the hard guards (communal/religious
  incitement, violence, unverified rumors-as-fact, deepfakes, tragedy exploitation, med/financial
  advice). ⚠️ Higher demonetization/strike risk acknowledged by operator.
- **AI disclosure — kept minimal (researched):** removing it risks forced labels + YPP suspension
  and does NOT improve reach, so we keep the synthetic-content FLAG and trimmed the description line
  to a discreet "AI-generated narration; stock visuals."
- **Voice → Kokoro (humanized):** `voice.py` now defaults to **Kokoro** (open-weight, Apache-2.0,
  CPU via kokoro-onnx int8 — far more natural) with **edge-tts fallback** (rule 11). int8 model
  (~120 MB) auto-downloads once; voice/speed via `KOKORO_VOICE`(`af_heart`)/`KOKORO_SPEED`; engine
  via `VOICE_ENGINE`. CI installs **espeak-ng**. Verified live locally (4.5s natural WAV).
- **Background music:** `assembly.py` mixes a quiet looped track from `assets/music/` under the
  narration (FFmpeg `amix`, ~12%). **Operator must drop 1–3 royalty-free tracks in `assets/music/`**
  (see its README); empty → skipped. Verified the mix renders in real FFmpeg.
- All four upgrade asks delivered. **105 tests pass.**
- **Operator follow-ups (same day):** added 5 CC0 cinematic/suspense beds to `assets/music/`
  (gitignore exception so they're committed); BGM default lowered to **0.10** (narration stays
  clear). **Narration tone switched to sarcastic/witty/roasting** (scriptwriter Template N) —
  facts stay accurate; hard limits keep it punching at situations/irony, not personal attacks
  (harassment = demonetization), per operator request.

### 2026-06-09 — 🎉 FIRST CLOUD SHORTS PUBLISHED — Phase-1 MVP live (v0.1.0)
- Ran the **entire system in the cloud, PC off**: make-short workflow → grounded/fallback
  ideation → Telegram digest → user approved 2 / passed 1 → script → voice → visuals → assemble
  → subtitles → upload. Two unlisted Shorts published, `2 published, 0 failed`:
  - idea 22 (Gaganyaan): https://www.youtube.com/shorts/ACXOPuT1Lac
  - idea 23 (AI drug discovery): https://www.youtube.com/shorts/zJv9-rvNw20
- **Hardened against three real LLM-output failures found in cloud runs** (local tests missed them):
  1. raw control chars in grounded JSON → `json.loads(strict=False)`;
  2. malformed/truncated grounded JSON → grounded parse now falls back to ungrounded JSON-mode;
  3. **gemini-2.5-flash thinking** consuming `max_output_tokens` → truncated scriptwriter JSON →
     disabled thinking (`thinking_budget=0`) + raised scriptwriter budget to 2048.
- **`production.yml` retry pattern proven:** with ideas already `approved`, `run()` skips seeding/
  digest and just produces them — used to retry ideas 22/23 after the scriptwriter fix.
- **Tagged v0.1.0** — Phase-1 MVP complete and operating in production.

### 2026-06-09 — Web-researched ideas IN-CLOUD via Gemini grounding (routine retired)
- **Resolved the routine-delivery dead end.** The cloud Anthropic Routine can't feed the
  pipeline: its git token is read-only (can't push) AND custom MCP connectors (Supabase) don't
  attach to routines — only directory connectors (Vercel/Gmail/Drive) do. Giving it a GitHub
  write token was rejected as a security hole (this repo's Actions hold upload/DB/Telegram
  secrets → a leaked write token = secret exfiltration).
- **Pivot that meets the goal (full cloud, PC off, researched ideas):** added
  `llm.generate_grounded()` — Gemini with **Google Search grounding** (live web research, real
  sources). `ideation_fallback._produce_ideas()` now researches the web first and falls back to
  ungrounded Gemini→Groq. This runs inside the make-short GitHub Action — **no routine, no PC, no
  embedded credential, no security tradeoff.**
- **Verified live:** produced 5 current, well-sourced ideas (isro.gov.in, thehindu.com,
  npci.org.in, mnre.gov.in, roche.com). **Suite: 100 passed, 2 skipped.**
- **Disabled** the cloud routine `trig_01APQkpZG1i14A5HJm8AsVDc` (kept for reference; re-enableable
  only if a writable delivery ever exists). The `data/daily-ideas.json` file-bridge stays as a
  still-supported secondary path (e.g. if you ever push ideas there from a writable context).
- ⭐ **Goal met: end-to-end cloud automation with web-researched ideas, machine never on.**

### 2026-06-09 — Anthropic Routine created; delivery blocked (read-only git token)
- Created routine **Daily ideation — But It Matters** (`trig_01APQkpZG1i14A5HJm8AsVDc`),
  daily 08:00 IST (cron `30 2 * * *`), Sonnet 4.6, repo Shaan-alpha/AI-Reel-Factory, WebSearch
  enabled. **It researches well** — a test run produced 17 sourced, sensitivity-filtered ideas.
- **BLOCKER:** the routine's CCR GitHub token is **read-only** → `git push` returns 403; the
  sandbox commit (`1e55f45`) is discarded with the sandbox. So the file-bridge (commit
  `data/daily-ideas.json`) **cannot work from a cloud routine** — not a prompt issue, an infra limit.
- **Open decision — how the routine delivers ideas:** (a) add a **Supabase MCP connector** at
  claude.ai so the routine inserts ideas straight into the DB (then `make_on_demand` prefers
  existing pending), or (b) keep the **Gemini/Groq fallback** for ideas and treat the routine as
  deferred. The bridge code (`seed_ideas`/`load_routine_ideas` + `data/`) stays either way —
  it's still used by the fallback and would work if a writable delivery is added later.
- **Not blocked:** the on-demand make-short button works today via the Gemini/Groq fallback.

### 2026-06-09 — On-demand "Make a Short" (cloud button + Telegram confirm)
- New operating model per user choice: trigger Shorts on demand, machine-off, with a Telegram
  confirm step. Added `.github/workflows/make-short.yml` (`workflow_dispatch`, inputs `ideas` /
  `wait_min`) → `python -m src.production make`.
- `production.make_on_demand(num_ideas, wait_minutes)`: generates fresh ideas → `_notify` →
  `send_digest` → `process_responses` (waits for taps) → `run_production` → Telegram-replies each
  published link. Added `ideation_fallback.generate_ideas(n)` (on-demand, no pending-guard, keeps
  the highest-scored n) + a `_notify` helper + `python -m src.production make` CLI mode.
- Tests: +2 ideation (`generate_ideas` no-guard / none-valid) +2 production (make flow / nothing
  approved). **Suite: 90 passed, 3 skipped.** ⚠️ Minor: `send_digest` resends all pending, so
  repeated triggers before deciding can re-show old ideas (decide or they pile up) — fine for v1.
- **Not yet pushed** — `make-short.yml` must reach the default branch for the Run-workflow button
  to appear in GitHub Actions.

### 2026-06-09 — GitHub Actions secrets mirrored (go-live step 2 ✅)
- Set 10 Actions secrets on `Shaan-alpha/AI-Reel-Factory` (GEMINI/GROQ/SUPABASE_URL+KEY/
  TELEGRAM_BOT_TOKEN+CHAT_ID/PEXELS/YOUTUBE_CLIENT_ID+SECRET+REFRESH_TOKEN) via `gh secret set`,
  values piped through stdin (never on argv, never printed). `CLAUDE_CODE_OAUTH_TOKEN` excluded
  by design (rule 4); `PIXABAY_API_KEY` left unset (optional). Verified via `gh secret list`.
- Remaining go-live: ideation Routine, enable crons, first unattended day → tag v0.1.0.

### 2026-06-09 — Add Telegram "Pass" button; clean dry-run test rows
- User confirmed the unlisted Short is live (title/description/disclosure all correct in Studio).
- Added a third digest button **⏭️ Pass** (`p:{id}`) → new idea status **`passed`** (soft skip:
  not posted, distinct from a hard `rejected`; drops out of the pending queue). Wired through
  `db.IDEA_STATUSES`, `approval._keyboard`/`_apply_callback`/`_DECISION_TEXT` + tests. **86 passed.**
- Cleaned the dry-run test rows from Supabase (post 12 / script 12 / idea 13) → DB back to empty.
  (The unlisted test video remains on the channel for the user to delete in Studio if desired.)

### 2026-06-09 — First real end-to-end run (unlisted upload) ✅
- Seeded one approved idea (id 13) and ran `production.run_production(limit=1)` with
  `YOUTUBE_PRIVACY=unlisted`. Full real chain executed: script (Gemini/Groq) → 40.6s narration
  (edge-tts) → Pexels B-roll → FFmpeg render → faster-whisper(base) 91 word-events burned →
  `videos.insert`. **Live:** https://www.youtube.com/shorts/mT4k_iuAZ5s — verified unlisted,
  `uploadStatus=processed`, 41s, description has analysis + both sources + disclosure line +
  `#Shorts`, tags set. `posts` row 12 recorded; idea 13 → `produced`; work dir cleaned (rule 15).
- **Open item:** `containsSyntheticMedia` was sent on insert but reads back `None` via the
  readonly API; token lacks the `youtube` write scope to re-confirm. → verify the "Altered
  content" flag in YouTube Studio (description disclosure line is present regardless).
- This exercises the one path not previously run live (a real upload). MVP is functionally proven.

### 2026-06-09 — Orchestrator: production.py wired — MVP CODE-COMPLETE
- Implemented [src/production.py](src/production.py): `run()` validates config →
  `ensure_ideas_and_digest()` (fallback ideation + digest if the queue is dry) → best-effort
  `approval.process_responses()` drain → `run_production()`. `produce_one(idea)` runs the full
  chain (script → voice → visuals → assemble → subtitle → publish), marks the idea `produced`,
  and `rmtree`s the work dir in a `finally` (rule 15).
- **Idempotent** (rule 12): `find_post` short-circuits an already-published script; produced
  ideas drop out of `get_approved_ideas`. **Fail-soft** (rule 14): a per-reel exception is
  logged, Telegram-alerted (best-effort, rule 13), and skipped — the batch continues. Daily
  cap via `DAILY_REEL_CAP` (default 5).
- Added [tests/test_production.py](tests/test_production.py): 8 cases (full chain, idempotency,
  fail-soft batching, cap, dry-queue bootstrap, run() smoke) — all modules mocked, no real
  uploads. **Suite: 85 passed, 3 skipped (gated live).**
- ⭐ **Every module of the Phase-1 pipeline is built and tested.** What remains is go-live only
  (secrets mirror, Routine, enable crons, first real run) — see the Go-live checklist above.

### 2026-06-09 — Module: approval.py implemented + tested — all 10 modules done
- Implemented [src/approval.py](src/approval.py) on the **Telegram Bot HTTP API via requests**
  (no async framework): `send_digest()` posts one message per pending idea (HTML, source links
  for sanity-check) with inline ✅/❌ buttons; `process_responses()` long-polls `getUpdates`,
  applies taps to `ideas`, and stops when all decided or after `max_seconds`. Soft cap via
  `APPROVAL_CAP` (default 5). Security: callbacks from any chat ≠ `TELEGRAM_CHAT_ID` are ignored.
- Verified the `_api` plumbing live with `getMe` (bot `@ai_reel_factory_bot`) — no message sent.
  `requirements.txt`: dropped `python-telegram-bot` (HTTP API used directly).
- Added [tests/test_approval.py](tests/test_approval.py): 10 mocked cases (format, keyboard,
  digest, cap enforcement, callback handling, foreign-chat ignore) + 1 **gated** live digest
  (`TELEGRAM_LIVE_TEST=1`). **Suite: 78 passed, 2 skipped (both gated live).**
- ⭐ Every module is built & tested. Only the `production.py` orchestrator + the GitHub Actions
  cron remain to reach the Phase-1 MVP.

### 2026-06-09 — Module: ideation_fallback.py implemented + tested (live)
- Implemented [src/ideation_fallback.py](src/ideation_fallback.py): `run_fallback_ideation()`
  mirrors `routines/ideation.md`'s JSON contract via `llm.generate` (Gemini→Groq), then
  validates/cleans: requires title+hook+angle, ≥`MIN_SOURCES` real http(s) URLs (drops the
  rest), dedupes by title, clamps `est_score`∈[0,1], caps at 20, inserts as `pending`.
  Idempotent (rule 12): no-op if pending ideas already exist. Thin-digest guard: raises rather
  than ship <5 ideas. Honest caveat documented: no live web-search on the free path, so the
  human approval is the source-quality net.
- Added [tests/test_ideation_fallback.py](tests/test_ideation_fallback.py): 8 mocked cases +
  1 **live** (real llm; DB mocked). Live run hit a Gemini 503 → **failed over to Groq** → 18
  valid sourced ideas — the rule-11 fallback proven under a real upstream outage. **Suite: 68 passed.**

### 2026-06-09 — Module: publish_youtube.py — all 9 pipeline modules done
- Implemented [src/publish_youtube.py](src/publish_youtube.py): `publish(video_path, metadata,
  script_id)` → resumable `videos.insert` via the .env refresh token, records `(video_id, url)`
  to `posts`, then deletes the local .mp4 (rule 15). Idempotent: `db.find_post` short-circuits
  a re-upload on cron retry (rule 12).
- **AI disclosure wired the official way:** sets `status.containsSyntheticMedia=true` (the
  Data-API "altered/synthetic content" flag, available since 2024-10) when `AI_DISCLOSURE=true`,
  plus the description disclosure line from the scriptwriter (docs/08 §2). Forces `#Shorts`,
  caps title at 100 chars, strips `#` from tags, `selfDeclaredMadeForKids=false`. Privacy/
  category env-overridable (`YOUTUBE_PRIVACY` default `public`, `YOUTUBE_CATEGORY_ID` `25`).
- Added [tests/test_publish_youtube.py](tests/test_publish_youtube.py): 7 mocked cases (body/
  disclosure/#Shorts/title, idempotency, record→delete, validation) + 1 **gated** live PRIVATE
  upload (runs only with `YOUTUBE_LIVE_UPLOAD_TEST=1`). **Suite: 59 passed, 1 skipped.**
- Quota note: `videos.insert` ≈ 1600 units; default 10k/day → ~6 uploads, fits 4-5 Shorts/day.
- ⭐ Every pipeline module (ideation-fallback + approval + orchestrator aside) is built & tested.
  Remaining for MVP: `approval.py` (Telegram digest), `ideation_fallback.py`, and wiring
  `production.py` + the GitHub Actions cron.

### 2026-06-09 — Module: subtitles.py — FULL CAPTIONED REEL END-TO-END
- Implemented [src/subtitles.py](src/subtitles.py): `burn_captions(video_path, audio_path,
  out_path)` runs **faster-whisper** (CPU int8, env `WHISPER_MODEL`=`base`) for word-level
  timestamps, builds a karaoke **.ass** (one word at a time, each held until the next starts
  → no blank frames), and burns it with FFmpeg (`ass=` filter). Style: 112px bold white, thick
  black outline, lower-third — readable on a phone (retention driver, ★ MVP).
- Burn runs with `cwd` set to the subtitle's dir so the filter arg is a bare filename — dodges
  Windows drive-colon/backslash escaping in libass. Reuses assembly's FFmpeg resolver.
- Added [tests/test_subtitles.py](tests/test_subtitles.py): 8 unit cases (ts formatting,
  gap-fill, ASS build, escape, orchestration with mocked whisper+ffmpeg, error paths) + 1
  **live** test — real faster-whisper(tiny) + burn on a real reel. **Suite: 52 passed.**
- ⭐ The entire production pipeline now runs: idea → script → narration → B-roll → 1080×1920
  video → **burned-in word-synced captions**. Only publishing remains for a shippable Short.

### 2026-06-09 — Module: assembly.py — FIRST FULL REEL RENDERS END-TO-END
- Implemented [src/assembly.py](src/assembly.py): `assemble(audio_path, clip_paths, out_path)`
  calls the **FFmpeg binary** directly (subprocess) — normalizes each clip (scale-to-fill +
  center-crop to 1080×1920, ~6s slice), concats, trims to the narration length (via `ffprobe`),
  and muxes the narration → H.264/yuv420p/AAC `.mp4`, `+faststart`. Clips are cycled to
  over-cover the audio; cuts land ~every 6s (retention + copyright, docs/08 §3).
- Binary resolution: `FFMPEG_BINARY`/`FFPROBE_BINARY` env → PATH → Windows winget fallback;
  fails loud if absent (rule 14). **Installed FFmpeg 8.1.1** locally (`winget install Gyan.FFmpeg`).
- **MVP scope** (rule 16): no Ken Burns / music bed yet — deferred until the core is proven;
  easy follow-ups. `requirements.txt`: dropped `ffmpeg-python` (binary called directly).
- Added [tests/test_assembly.py](tests/test_assembly.py): 6 unit cases (argv build, clip cycling,
  input validation) + 1 **live end-to-end** test — edge-tts → Pexels → FFmpeg renders a real
  1080×1920 reel with audio, length within 1.5s of narration. **Suite: 43 passed.**
- ⭐ The text→audio→visuals→video chain is now complete: an approved idea produces a real,
  watchable (un-captioned) Short. Next: burn in karaoke captions (`subtitles.py`).

### 2026-06-09 — Module: visuals.py implemented + tested (live)
- Implemented [src/visuals.py](src/visuals.py): `extract_keywords(script_body, n)` (LLM with a
  frequency-heuristic fallback, rule 11) + `fetch_broll(keywords, target_seconds, out_dir)` →
  CC0 vertical clips from **Pexels** (→ **Pixabay** backup). Picks portrait mp4 closest to
  1080w, interleaves across keywords for variety, downloads until ~target coverage (8s/clip,
  matching assembly cuts), content-hashed filenames for idempotent caching (rule 12).
- **Verified the Pexels video endpoint** is `https://api.pexels.com/videos/search` (no `/v1`),
  auth via bare `Authorization` header; live search returns true 1080×1920 portrait clips.
- Added [tests/test_visuals.py](tests/test_visuals.py) — 10 mocked cases (keywords LLM+heuristic,
  portrait selection, coverage/stop, idempotent cache, Pixabay fallback, error paths) + 1 **live**
  Pexels search+download (skips offline). **Suite: 36 passed.**

### 2026-06-09 — Module: voice.py implemented + tested (live)
- Implemented [src/voice.py](src/voice.py): `synthesize(script_body, out_dir) → (audio_path,
  duration_s)` via **edge-tts** (free, no key). Uses `stream_sync()` to write the MP3 and
  measure duration from boundary events in one pass — no extra audio-probe dep. Deterministic
  filename `narration_<sha1>.mp3` (idempotent reruns, rule 12). Voice/rate env-overridable
  (`VOICE`=`en-IN-NeerjaNeural`, `VOICE_RATE`). edge-tts wrapped so Kokoro slots in (Phase 2).
- **edge-tts 7.2.8 gotcha:** default boundary is `SentenceBoundary`, not `WordBoundary` (the
  older docs). Duration now reads either type. Found via a real stream-type probe.
- Added [tests/test_voice.py](tests/test_voice.py) — 5 mocked cases (write, duration math,
  deterministic name, empty/no-audio/error wrapping) + 1 **live** edge-tts synth (skips
  offline). Confirmed a real ~4s en-IN MP3 renders. **Suite: 25 passed.**

### 2026-06-09 — Module: scriptwriter.py implemented + tested
- Implemented [src/scriptwriter.py](src/scriptwriter.py): `write_script(idea, template='N')`
  builds the Template-N prompt, calls `llm.generate(json=True)`, parses the JSON (tolerant of
  markdown fences), and persists via `db.insert_script`. Returns `{script_id, script_body,
  caption, hashtags}`.
- **Monetization-gate enforcement in code, not trusted to the LLM** (docs/08 §1-3): source
  links + the AI-disclosure line are guaranteed in the caption, and `#Shorts` in the hashtags —
  added only if missing (no duplication). Soft word-count warning (~130-150) per rule 14.
- Only Template N is wired (rule 9 / YAGNI); D/A/C raise a loud `ValueError`.
- Added [tests/test_scriptwriter.py](tests/test_scriptwriter.py) — 8 cases mocking `llm` + `db`
  (no keys/network/DB): happy path, compliance enforcement, no-duplication, fenced JSON,
  empty-body / unparseable / unsupported-template / missing-id errors. **Suite: 19 passed.**

### 2026-06-09 — Module: llm.py implemented + tested; SDK + venv fixes
- Implemented [src/llm.py](src/llm.py): `generate(prompt, *, json, max_tokens)` with a
  **Gemini → Groq** failover chain (rule 11) — logs + fails over on error/quota/empty, raises
  only when *every* provider fails. JSON mode for both; models overridable via `GEMINI_MODEL`/
  `GROQ_MODEL` env. Defaults: `gemini-2.5-flash`, `llama-3.3-70b-versatile`.
- Added [tests/test_llm.py](tests/test_llm.py) — 5 cases mocking both providers (no keys/network)
  to prove the failover, empty-response handling, all-fail RuntimeError, and json/max_tokens
  threading. **Suite: 11 passed** (4 config + 6 db live + 5 llm).
- **SDK fix:** `requirements.txt` `google-generativeai` → **`google-genai`** (the old SDK was
  deprecated/EOL late 2025; verified the current `from google import genai` API via Context7).
- **Env:** created local `.venv` (first one) and installed pytest + supabase + google-genai +
  groq so the suite collects and runs green from a clean checkout. (Lock file deferred until
  the heavier video deps install — `pip freeze` now would be a partial/misleading lock.)

### 2026-06-06 — YouTube channel binding confirmed
- First OAuth pass was bound to the wrong (main) channel + then revoked. Re-ran cleanly:
  added `youtube.readonly` scope, regenerated the token selecting the **@butitmatters**
  channel, no post-revoke. `tools/verify_youtube.py` reads the bound channel and confirms it.
- Bound channel title is `Why It Matters??`; user confirmed it's the project channel and set
  the canonical brand to **But It Matters** (matches the handle + repo). Cosmetic to-do:
  rename the YT channel title to "But It Matters".

### 2026-06-05 — All credentials complete (YouTube OAuth verified)
- Generated YouTube OAuth creds (Desktop-app client + published consent screen) and added
  `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` to `.env`.
- Added [tools/verify_youtube.py](tools/verify_youtube.py); confirmed the refresh token mints
  a live access token. **Every API key is now collected and verified** — the full pipeline
  (incl. `publish_youtube.py`) is unblocked.

### 2026-06-05 — Module: db.py implemented + tested
- Implemented [src/db.py](src/db.py) on supabase-py 2.31.0: `get_client()` (cached, secret
  key), `insert_ideas`, `get_pending_ideas`, `set_idea_status`, `get_approved_ideas`,
  `insert_script`, `insert_post`, `find_post` (idempotency helper, rule 12). Added a
  `produced` idea status so cron retries skip shipped reels.
- Added [tests/test_db_integration.py](tests/test_db_integration.py): full idea→post cycle
  against the live DB, auto-skips without creds. **Suite: 6 passed.**
- User swapped `SUPABASE_KEY` to the `sb_secret_…` key — RLS-protected writes confirmed working.

### 2026-06-05 — Supabase database provisioned
- Created all 5 tables (`ideas`, `scripts`, `posts`, `analytics`, `hook_performance`) on the
  `ai-reel-factory` project (Postgres 17, Seoul) via the Supabase MCP, matching the
  [docs/03](docs/03-setup-guide.md) §4 schema (FKs + identity PKs + array/timestamp defaults).
- **RLS enabled** on every table (no policies → public/anon key denied; the server-side
  `sb_secret_…` key bypasses RLS). Cleared an advisor WARN by revoking public EXECUTE on the
  pre-existing `rls_auto_enable()` event-trigger (auto-RLS behavior unaffected).
- Smoke-tested insert → read (defaults applied) → delete. Security advisor now clean
  (only expected INFO `rls_enabled_no_policy`).
- User completed `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` in `.env` (for the Routine).
- **Remaining:** swap `SUPABASE_KEY` to the `sb_secret_…` key (MCP only exposes publishable keys).

### 2026-06-05 — Branding + setup underway
- Channel handle `@newsence` was taken → rebranded to **But It Matters** (`@butitmatters`,
  secured on YouTube). Renamed across all repo files.
- Collected keys into `.env` (gitignored): Gemini, Groq, Supabase (publishable — swap to
  secret), Telegram bot `@ai_reel_factory_bot` (+ chat id, in `.env`), Pexels. Verified
  Gemini + Pexels return HTTP 200.
- Added [tools/get_youtube_token.py](tools/get_youtube_token.py) to generate the YouTube
  refresh token (one-time OAuth), with step-by-step setup notes.
- Repo home decision: use the **public** `Shaan-alpha/AI-Reel-Factory` repo (unlimited
  Actions minutes). Secret-scanned tracked files before pushing — clean.

### 2026-06-05 — Phase-1 scaffolding
- Created the repo skeleton from [docs/02-implementation-plan.md](docs/02-implementation-plan.md) §0:
  `src/` (10 module stubs + functional `config.py`), `routines/ideation.md` (first-draft
  Routine prompt), `templates/` (N, D, A, C), `tests/`, `.github/workflows/` (skeletons,
  manual-trigger), `requirements.txt`, `.env.example`, `.gitattributes`.
- Module stubs carry their typed input→output contract + `NotImplementedError` (no pipeline
  logic yet, per scope). Build them in order, in isolation (rule 7).
- `config.py` is real (fail-loud, rule 14) and covered by `tests/test_config.py` — **4/4 pass**.
- Workflows default to `workflow_dispatch`; cron stays commented out until modules work.

### 2026-06-05 — Foundation set up
- Imported the 8-doc design package into [docs/](docs/) from the `AI Idea` source folder.
- Wrote [CLAUDE.md](CLAUDE.md): 18 operating rules (docs-as-memory, free-first, no
  self-attribution, ToS boundary, news compliance, runtime reliability, versioning).
- Added this STATUS.md, [README.md](README.md), and [CHANGELOG.md](CHANGELOG.md).
- No pipeline code yet — foundation only by design.
