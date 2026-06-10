# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.2.0 (**PUBLIC** — AI visuals + analytics + SEO; 115 tests pass)
**Last updated:** 2026-06-09
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
| Pipeline logic (modules) | 🟡 `db.py` + `llm.py` done + tested; other modules still stubs |
| Local `.venv` | ✅ pytest + supabase + google-genai + groq + edge-tts (suite green) |
| FFmpeg (system dep) | ✅ Installed locally — winget `Gyan.FFmpeg` 8.1.1 (assembly module) |

## Module progress (Phase 1)

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (Claude Routine + fallback) | ✅ Routine prompt drafted; **`ideation_fallback.py` done** — Gemini→Groq, sourced+validated; 9 tests (incl. live) |
| 2 | Approval (Telegram) | ✅ Done — digest + Approve/Reject/**Pass** buttons + cap; 12 tests (live gated) |
| 3 | Scriptwriter (Gemini/Groq) | ✅ Done — Template N via `llm.py`; compliance enforced; 8 unit tests |
| 4 | Voice | ✅ Done — **Kokoro (humanized) → edge-tts fallback**; 8 tests (incl. live Kokoro) |
| 5 | Visuals (Pexels/Pixabay) | ✅ Done — LLM keywords + CC0 portrait B-roll; 11 tests (incl. live) |
| 6 | Assembly (FFmpeg) | ✅ Done — 1080×1920 H.264 reel; 7 tests (incl. live full render) |
| 7 | Subtitles (faster-whisper) | ✅ Done — word-by-word ASS burn; 9 tests (incl. live whisper+burn) |
| 9 | Publish (YouTube) | ✅ Done — videos.insert + `containsSyntheticMedia` flag; 8 tests (live gated) |
| 10 | Orchestrator (`production.py`) | ✅ Done — wires the full chain, idempotent + fail-soft; 8 tests |
| — | `config.py` / `db.py` / `llm.py` | config ✅ · **db ✅** · **llm ✅ (Gemini→Groq failover, 5 unit tests)** |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

- ✅ **All credentials collected + verified.** ✅ **All pipeline code built + tested** (85 pass).

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
