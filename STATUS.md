# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.17.0 (**PUBLIC**) · _Full audit: the gate that switched itself off_ (fact-check fail-open now alerts + can hold its own quota; stale-idea age-out; per-reel photo variety; 17 stacked `[Unreleased]` blocks turned into a real version history; **460 pass, 5 skipped** — measured 2026-09-03)
  ↳ the 0.5.0 label was a STATUS-only number: the last git tag was `v0.2.0`. `v0.17.0` is tagged.
**Last updated:** 2026-09-03
**Voice:** Gemini TTS `gemini-3.1-flash-tts-preview` · **Zubenelgenubi** ("Casual") · both picked by ear · free tier
  ↳ falls back to `gemini-2.5-flash-preview-tts` (same voice) on a 503 — the preference order IS the fallback order
**Editorial policy:** **truth over neutrality** — verdicts allowed; `factcheck.verify()` blocks **fabrication**, waives imprecision (`FACTCHECK_SEVERITY`)
**Brand:** But It Matters · YouTube handle **@butitmatters** · Telegram bot **@ai_reel_factory_bot**

---

## Snapshot

| Area | State |
|------|-------|
| Design / docs | ✅ Complete — 8 docs in [docs/](docs/) |
| Project rules | ✅ Written — [CLAUDE.md](CLAUDE.md) |
| Repo scaffolding (src/, routines/, templates/, tests/, workflows) | ✅ Done — stubs + contracts |
| `config.py` | ✅ Functional + tested (4/4 pass) |
| Script templates (N, D, A, C) | ✅ Written |
| Routine prompt (`routines/ideation.md`) | ✅ First draft |
| Accounts & API keys | ✅ **ALL collected + verified** — Gemini · Groq · Supabase(secret) · Telegram · Pexels · Claude token · YouTube |
| Supabase database | ✅ 5 tables + RLS + secret-key writes confirmed |
| YouTube OAuth | ✅ Verified (upload+readonly); token bound to the correct **@butitmatters** channel |
| YouTube handle `@butitmatters` | ✅ Secured (IG/TikTok not checked — Phase 3) |
| YouTube channel *title* | ✅ Renamed to **But It Matters** (matches handle + CHANNEL_NAME) |
| Pipeline logic (modules) | ✅ **All modules implemented + tested** — see the table below (this row said "still stubs" until 2026-09-03, contradicting it) |
| Local `.venv` | ✅ pytest + supabase + google-genai + groq + edge-tts (suite green) |
| FFmpeg (system dep) | ✅ Installed locally — winget `Gyan.FFmpeg` 8.1.1 (assembly module) |

## Module progress (Phase 1)

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (Claude Routine + fallback) | ✅ Routine prompt drafted; **`ideation_fallback.py` done** — Gemini→Groq, sourced+validated; 9 tests (incl. live) |
| 2 | Approval (Telegram) | ✅ Done — digest + Approve/Reject/**Pass** buttons + cap; 12 tests (live gated) |
| 3 | Scriptwriter (Gemini/Groq) | ✅ Done — Template N; honest framing + why-it-matters + **key-point cards**; compliance enforced; **25-30s length enforced** (punch-up no longer lengthens + hard word cap); 20 tests |
| 4 | Voice | ✅ Done — **Google Chirp 3 HD → edge-tts (en-IN) → Kokoro** chain + **opt-in Gemini TTS** head (promptable, free Flash model) and **per-engine delivery tags** (`[pause]`→Chirp markup, `[sarcastic]`→Gemini); 47 tests (incl. gated live) |
| 5 | Visuals (Pexels/Pixabay) | ✅ Done — LLM keywords + CC0 portrait B-roll; 11 tests (incl. live) · *Phase B: story-specific* |
| 6 | Assembly (FFmpeg) | ✅ Done — 1080×1920 H.264 reel + **premium polish** (crossfade transitions, cinematic grade, vignette/grain) + **retention v2** (music ducking, brand-logo bug, loop-friendly endings), all toggle-gated + fail-soft; 29 tests (incl. live full render) |
| 7 | Subtitles (faster-whisper) | ✅ Done — **karaoke + frame-1 hook + key-point cards** (Montserrat) + **source lower-third**; 22 tests (incl. live burn) |
| 9 | Publish (YouTube) | ✅ Done — videos.insert + `containsSyntheticMedia` flag; 8 tests (live gated) |
| 10 | Orchestrator (`production.py`) | ✅ Done — wires the full chain, idempotent + fail-soft; 8 tests |
| — | `config.py` / `db.py` / `llm.py` | config ✅ · **db ✅** · **llm ✅ (Gemini→Groq failover, 5 unit tests)** |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

- ✅ **All credentials collected + verified.** ✅ **All pipeline code built + tested** (**460 pass, 5 skipped** — 2026-09-03).

### Operating model: ON-DEMAND (chosen 2026-06-09)
Instead of (or before) scheduled crons, the primary trigger is the **`make-short` workflow**
(`.github/workflows/make-short.yml`, `workflow_dispatch`). Click **Run workflow** (GitHub web/
mobile) → it generates `ideas` fresh ideas → Telegram digest with Make-it/Pass/Reject → waits
`wait_min` for your taps → produces the approved → replies with the YouTube link. PC can be off.
Entry: `python -m src.production make` (`make_on_demand`). You control frequency by how often
you click. The scheduled cron path (`production.yml`) remains available but optional.

### Go-live checklist (Phase-1 DoD — these are deploy steps, no new modules)
1. ✅ **End-to-end dry run done (2026-06-09):** seeded one approved idea → `run_production`
   produced + uploaded a real **unlisted** Short → https://www.youtube.com/shorts/mT4k_iuAZ5s
   (41s, captioned; description carries the analysis, both source links, the AI-disclosure
   line, `#Shorts`; DB `posts` recorded; idea→`produced`; local files cleaned). **The full
   real chain incl. `videos.insert` now works.**
   ⚠️ **Verify in YouTube Studio:** the "Altered content" disclosure on that video. We send
   `status.containsSyntheticMedia=true` on insert, but the readonly API returns it as `None`
   and our token lacks the `youtube` (write) scope to re-confirm — so confirm it shows "Yes"
   in Studio. (The description disclosure line is present regardless.) Test artifacts to clean:
   delete that unlisted video in Studio; DB has test idea 13 / post 12.
2. ✅ **GitHub Actions secrets set (2026-06-09):** 10 secrets mirrored to
   `Shaan-alpha/AI-Reel-Factory` via `gh secret set` (values piped via stdin, never printed).
   `CLAUDE_CODE_OAUTH_TOKEN` deliberately excluded (rule 4). `PIXABAY_API_KEY` not set (optional
   backup, empty locally) — workflow reference resolves to empty, Pixabay fallback just no-ops.
3. **Create the ideation runner:** an **Anthropic Routine** from `routines/ideation.md`
   (recommended) so ideas land in `ideas` each morning; the `ideation_fallback` covers misses.
4. **Enable the crons:** uncomment `schedule:` in `.github/workflows/production.yml` (UTC,
   staggered). CI already installs FFmpeg; faster-whisper pulls its model on first run.
5. **First unattended day:** approve 4-5 via the Telegram digest → confirm 4-5 captioned Shorts
   go live with the AI-disclosure label. → then tag **v0.1.0** (Phase-1 MVP done).
6. (Phase 3) Check `@butitmatters` on Instagram + TikTok before cross-posting.

## Open decisions

- **Ideation runner:** Anthropic Routines vs Oracle VM cron (lean Routines).

## Blockers

- _None._

---

## Log

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
