# Setup Guide — Accounts & API Keys

Everything needed to reproduce the running system: accounts, keys, the Google Cloud setup and
the Telegram bot. Collect every secret into a local `.env` (copied from `.env.example`; never
commit it). At the end you copy the secrets into **GitHub → Settings → Secrets** so the workflows
can run headless.

> ⏱️ Budget ~1–2 hours. Instagram/TikTok items are **Phase 3** — skip for the MVP.

---

## Local machine (first)

- **Python 3.12**, which is what CI runs. Install with `pip install -r requirements-dev.txt`
  (every package pinned, plus pytest). Run the suite as CI does: `python -m pytest -q -rs`.
- **FFmpeg** on PATH, with libass (it burns the captions; the winget and apt builds both have it).
  Windows: `winget install Gyan.FFmpeg` (the code also finds the winget install when it is not on
  PATH). Linux: `apt-get install ffmpeg`. Or point `FFMPEG_BINARY` / `FFPROBE_BINARY` at the
  binaries.
- **espeak-ng**, Linux only (Kokoro's phonemizer): `apt-get install espeak-ng`.
- The first run downloads the Kokoro model (~120 MB, `~/.cache/kokoro`) and the faster-whisper
  `base` model (Hugging Face cache).
- The **Google Cloud CLI** (`gcloud`) for the Vertex login (§2b), and the **Vercel CLI**
  (`npm i -g vercel`) for the bot (§5b).

CI uses GitHub's `ubuntu-24.04` runner with Python 3.12 and apt's `ffmpeg` and `espeak-ng`.

---

## 1. Claude — the scriptwriter (Anthropic API, $4/month) · optional

Since 2026-10-22 Claude writes every reel's final script. Gemini still does the web research: its
grounded draft is Claude's fact base, and the fact-check gate re-checks Claude's script. Claude
cannot search, so the code also checks that every number and name in Claude's script is already
in the draft or the idea; if not, the draft ships. Without a key, or without a grounded draft,
the pipeline runs as it did before this section existed.

1. console.anthropic.com → **API keys** → create a key. Save it as `ANTHROPIC_API_KEY` in `.env`
   and as a GitHub Actions secret of the same name.
2. Create the `claude_spend` table (the SQL in §4). Each Claude call first reserves its worst
   case there, the month's total is read with that reservation in it, and the call is not sent
   if the total passes `ANTHROPIC_MONTHLY_BUDGET_USD` (default 4). The row is then settled to
   the real cost; a call that dies without an answer stays counted at its worst case. Without
   the table no Claude call is made, because the spend cannot be checked. A missing table, a
   bad key or setting, or a spent month is reported to Telegram once a run.
3. Optional, recommended: set a monthly spend limit on the key's workspace in the Console as a
   second stop that does not depend on this code.

Model and effort are `ANTHROPIC_MODEL` (default `claude-opus-5-5`) and `ANTHROPIC_EFFORT`
(default `low`); measured costs are in `.env.example`. `ENABLE_CLAUDE_SCRIPT=false` switches it off.

ToS (rule 4): the Claude **subscription** runs **only** through official Claude Code / Routines.
Never put `CLAUDE_CODE_OAUTH_TOKEN` into Python, the Agent SDK or a workflow; no code or workflow
reads it, and the local `.env` no longer holds it. The paid API key above is the only way code
reaches Claude. An Anthropic Routine (`routines/ideation.md`) remains optional and has never run
in production; update its prompt before enabling one, since it predates the truth-first policy.

---

## 2. Google AI Studio — Gemini Developer API key ★ required

1. Go to https://aistudio.google.com/ → sign in with Google.
2. **Get API key** → create a key. (On 2026-09-04 AI Studio refused to mint one for a project in
   the organisation that holds `but-it-matters-tts`, so create it in a project outside it.)
3. Save as `GEMINI_API_KEY`.

- **Role:** the first link of the voice chain (Gemini TTS, voice Zubenelgenubi, free tier), and a
  required setting: `config.py` stops without it. With `GEMINI_USE_VERTEX` off (the code default)
  it also serves text and grounding, but free grounded search is closed to new projects
  (2026-09-04), so production runs text and grounding on Vertex (§2b).
- **Limits:** the free tier is metered per model, with small daily caps (measured: 20 grounded
  requests/day on `gemini-2.5-flash`; a TTS 429 on 2026-10-09).
- **2026-11-17:** the Developer API shuts down both TTS models in use
  (`gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`). The replacements,
  `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`, are on the free tier and wait on the
  operator's ear test (STATUS.md).

---

## 2b. Google Cloud — Vertex AI (billed, keyless) ★ required

Production serves all Gemini text, grounding and the fact-check gate through Vertex AI (both
pipeline workflows set `GEMINI_USE_VERTEX=true`), and voices the channel narrator there when the
Developer API fails. It replaced the Developer API's 20 grounded requests/day, which ran out and
left the fact-check gate unable to run.

- **Cost:** tokens are billed on every call (a fact-check costs about $0.003-0.004). Grounding is
  free up to 5,000 search queries/month across Gemini 3 models, then $14 per 1,000.
- **Budget:** a ₹450/month budget on the billing account ("AI Reel Factory cap") alerts at 50, 90
  and 100% of spend and covers every project on that account. It alerts; it does not stop spend.
  Rule 2's cap is ≤ $5/month.
- **Models:** nothing to set. The workflow defaults are `gemini-3.8-flash` for text,
  `gemini-3.5-flash-lite,gemini-3.5-flash` for grounding and ideation research, and
  `gemini-3.5-flash,gemini-3.5-flash-lite` for the fact-check gate. Vertex retires
  `gemini-2.5-flash`, `-2.5-flash-lite` and `-2.5-pro` on 2026-10-20; no default uses them.

**The live setup** (project `but-it-matters-tts`, number `892249248253`):

- APIs enabled: Vertex AI (`aiplatform`), IAM Credentials and STS (for the keyless login), and
  Cloud Text-to-Speech (§6d).
- Service account `reel-factory-ci@but-it-matters-tts.iam.gserviceaccount.com`, holding
  `roles/aiplatform.user` on the project.
- Workload Identity pool `github` with OIDC provider `github-oidc` (issuer
  `https://token.actions.githubusercontent.com`, condition
  `assertion.repository_owner=='Shaan-alpha'`). The service account grants
  `roles/iam.workloadIdentityUser` to this repository only.
- No key is stored anywhere. The organisation blocks service-account key creation, and new API
  keys could not be minted in it (2026-09-04). Each workflow that calls Vertex has
  `permissions: id-token: write` and runs `google-github-actions/auth@v3` with the provider path
  and the service account.

These commands reproduce that configuration (read back from the live project on 2026-10-09):

```bash
P=but-it-matters-tts
SA=reel-factory-ci@$P.iam.gserviceaccount.com
gcloud services enable aiplatform.googleapis.com iamcredentials.googleapis.com sts.googleapis.com --project=$P
gcloud iam service-accounts create reel-factory-ci --project=$P
gcloud projects add-iam-policy-binding $P --member="serviceAccount:$SA" --role="roles/aiplatform.user"
gcloud iam workload-identity-pools create github --location=global --project=$P
gcloud iam workload-identity-pools providers create-oidc github-oidc \
  --location=global --workload-identity-pool=github --project=$P \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner=='Shaan-alpha'"
gcloud iam service-accounts add-iam-policy-binding $SA --project=$P \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/892249248253/locations/global/workloadIdentityPools/github/attribute.repository/Shaan-alpha/AI-Reel-Factory"
```

A fork in another project uses its own project ID and number above, and must also edit the
provider path, service account and project in the four workflows that authenticate:
`make-short.yml`, `production.yml`, `verify-tts.yml` and `verify-vertex.yml`. The two pipeline
workflows read `GCP_PROJECT` from a repo variable (default `but-it-matters-tts`); the two verify
workflows hard-code it.

**Locally** there is no key either; use Application Default Credentials:

```powershell
gcloud auth application-default login
```

Then set `GEMINI_USE_VERTEX=true` (the code default is false), `GCP_PROJECT=but-it-matters-tts`
and `GCP_LOCATION=global` in `.env`, and run `python tools/verify_vertex.py`. It checks the
credentials first, then makes one grounded call and prints the citations. In CI, run the
**verify-vertex** workflow after any change to the pool, the provider, the service account or the
auth step.

---

## 3. Groq — failover LLM (free) ★ required

1. Go to https://console.groq.com/ → sign up.
2. **API Keys** → create key.
3. Save as `GROQ_API_KEY`.

- Model `openai/gpt-oss-120b` (`GROQ_MODEL`), run with `reasoning_effort` low. It picks the
  stories in ideation, goes first for the no-web tasks (hook punch-up, tighten pass, visual
  keywords) and is the failover for ungrounded Gemini calls. Grounded calls have no Groq fallback.
- Free tier on this key: 1,000 requests/day and 8,000 tokens/minute for that model (Groq's
  rate-limit headers, 2026-10-09).

---

## 4. Supabase — database (free) ★ required

1. Go to https://supabase.com/ → new project (region near you).
2. Save the **Project URL** → `SUPABASE_URL` and the server-side **secret key** (`sb_secret_…`)
   → `SUPABASE_KEY`. Never the publishable key: every table has RLS on, and only the secret key
   bypasses it.
3. Open **SQL Editor** and run the schema below.
- Free tier: 500 MB DB; a project pauses after 7 idle days (the daily `analytics` workflow's
  writes keep it awake). No video is ever stored here (rule 15).

```sql
-- Run this in Supabase SQL Editor

create table ideas (
  id bigint generated always as identity primary key,
  created_at timestamptz default now(),
  niche text,
  title text,
  hook text,
  angle text,
  est_score numeric,
  sources text[],                         -- source URLs (news niche: >= MIN_SOURCES, default 2)
  status text default 'pending'           -- pending | approved | rejected | passed | produced | blocked
);

create table scripts (
  id bigint generated always as identity primary key,
  idea_id bigint references ideas(id),
  template text,
  body text,
  caption text,
  hashtags text[],
  title text,         -- the punchy PUBLISHED title; lets analytics learn winning title styles
  factcheck jsonb     -- the fact-check gate's verdict
);

create table posts (
  id bigint generated always as identity primary key,
  script_id bigint references scripts(id),
  platform text,                          -- youtube | instagram | tiktok
  external_id text,
  url text,
  status text,                            -- published | removed (gone from the platform)
  published_at timestamptz,
  voice text                              -- which engine/model spoke, e.g. gemini:<model>@dev
);

create table analytics (
  id bigint generated always as identity primary key,
  post_id bigint references posts(id),
  pulled_at timestamptz default now(),
  views int, retention numeric, likes int,   -- views, likes and comments are filled;
  comments int, shares int, saves int        -- the public Data API has no retention
);

create table hook_performance (            -- unused today
  id bigint generated always as identity primary key,
  hook_text text,
  niche text,
  uses int default 0,
  avg_retention numeric,
  avg_views numeric
);

create table claude_spend (                -- one row per Claude call; holds the monthly budget
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  model text not null,
  purpose text not null,                   -- script
  input_tokens int not null,
  output_tokens int not null,              -- includes thinking tokens
  cost_usd numeric(10, 6) not null,
  settled boolean not null default true    -- false: a worst-case reservation for a call that
);                                         -- died mid-flight (a timeout); it stays counted
create index claude_spend_created_at on claude_spend (created_at);

-- RLS on every table, with no policies: the publishable key gets nothing, and the
-- server-side sb_secret_ key bypasses RLS.
alter table ideas            enable row level security;
alter table scripts          enable row level security;
alter table posts            enable row level security;
alter table analytics        enable row level security;
alter table hook_performance enable row level security;
alter table claude_spend     enable row level security;

-- A project created before 2026-09-27 adds the two newer columns with the migration
-- `record_factcheck_verdict_and_voice` (applied to the live project):
--   alter table public.scripts add column if not exists factcheck jsonb;
--   alter table public.posts   add column if not exists voice text;
```

---

## 5. Telegram Bot — approval UI (free) ★ required

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts (the live bot is
   `@ai_reel_factory_bot`).
2. Save the token → `TELEGRAM_BOT_TOKEN`.
3. Message your new bot once, then get your chat ID:
   visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`. Do this before
   §5b sets the webhook: Telegram refuses `getUpdates` while a webhook is set.
4. Save → `TELEGRAM_CHAT_ID`.

## 5b. Telegram control bot on Vercel ★ required

The pipeline workflows run with `TELEGRAM_APPROVAL_MODE=webhook`: the bot is what writes your
digest taps (✅ Approve / ❌ Reject / ⏭️ Pass) to Supabase, and `/makeshort` in the bot starts a
run. Without the bot, taps are never recorded.

Follow [telegram-bot/README.md](../telegram-bot/README.md): a fine-grained GitHub token
(`GH_PAT`), the Vercel project and its environment variables, and the webhook. The live bot is the
Vercel project `telegram-bot` in team `shaan-alphas-projects` (account shaan-alpha; the operator
has two Vercel accounts, so check `vercel whoami` before deploying). Put the same `WEBHOOK_SECRET`
in your local `.env` so `tools/set_telegram_webhook.py` can register it.

---

## 6. Pexels API — stock B-roll (free) ★ required

1. Go to https://www.pexels.com/api/ → sign up → get key.
2. Save as `PEXELS_API_KEY`.
- Pexels License, **not CC0**: free for commercial use, no attribution, but identifiable people
  may not appear in a bad light, so queries keep faces out of frame. Free: 200 requests/hour,
  20,000/month.
- Role: the photo fallback for each AI shot, and stock video.

## 6b. Pixabay API — backup B-roll (free) ★ recommended

1. Go to https://pixabay.com/api/docs/ → sign up → get key.
2. Save as `PIXABAY_API_KEY` (optional: without it the stock-video search uses Pexels alone).
- Pixabay Content License, **not CC0**: free for commercial use, no attribution, no misleading use
  of recognisable people. Free: 100 requests per 60 s per key.

## 6c. Cloudflare Workers AI — AI-generated B-roll (free tier) ★ recommended

Production runs on **AI imagery** (`VISUAL_SOURCE=ai`, set as a repo variable): story-specific
illustrative images + Ken Burns motion. Any image that fails becomes a Pexels photo, and stock
video takes over if no image works. The code and workflow default is `photos` (Pexels stills), so
a fresh fork without the variable uses stock until you set it.

1. Create a Cloudflare account → **Workers & Pages** → note your **Account ID**.
2. **My Profile → API Tokens → Create Token** with the **Workers AI** permission.
3. Save as `CF_API_TOKEN` and `CF_ACCOUNT_ID`. Model default:
   `@cf/black-forest-labs/flux-2-klein-4b` (native 768x1344, per-shot seeds; override via
   `CF_IMAGE_MODEL`), with `flux-1-schnell` as the fallback. Free tier: 10,000 neurons/day.

## 6d. Google Cloud Text-to-Speech — Chirp 3 HD (billed, first voice fallback) ★ recommended

The channel voice is Gemini TTS (`gemini-3.1-flash-tts-preview`, Zubenelgenubi): the §2 key first,
then the same voice on Vertex (§2b), with no extra setup. Chirp 3 HD is the next link, reading as
the same narrator (`en-IN-Chirp3-HD-Zubenelgenubi`). Billed service: 1M characters/month free,
then $30 per 1M; the budget in §2b covers it.

1. In `but-it-matters-tts`, enable the **Cloud Text-to-Speech API** and create an **API key**
   restricted to that API. Save as `GOOGLE_TTS_API_KEY`. (The live key was created with the project
   on 2026-06-15; see §2b on new keys in this organisation.)
2. Set the repo variable `GOOGLE_TTS_VOICE=en-IN-Chirp3-HD-Zubenelgenubi` (and the same in
   `.env`). It has no default: without it Chirp is skipped. Keep the narrator's voice;
   `python tools/list_google_voices.py` lists the en-IN Chirp 3 HD voices.

Without a key or voice the chain moves on to edge-tts (`en-IN-PrabhatNeural`), then Kokoro
(`am_michael`): male voices all the way down.

---

## 7. faster-whisper — subtitles (free, local) ★ required (MVP)

- No account needed. Installed by `requirements.txt`. It times each spoken word (`WHISPER_MODEL`,
  default `base`; FFmpeg decodes the audio); the caption text comes from the approved script. The
  model downloads on first run.

---

## 8. YouTube Data API v3 — publishing (free) ★ required

1. https://console.cloud.google.com/ → create/reuse a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **OAuth consent screen** → External, add your email as a test user, and under **Data Access**
   add the three scopes `tools/get_youtube_token.py` asks for:
   `https://www.googleapis.com/auth/youtube.upload`,
   `https://www.googleapis.com/auth/youtube.readonly` and
   `https://www.googleapis.com/auth/yt-analytics.readonly`.
   Publish the app (**In production**): in Testing mode refresh tokens can expire in ~7 days.
4. **Credentials → Create → OAuth client ID → Desktop app** → download it as
   `client_secret.json` in the repo root (the name is gitignored).
5. Run `python tools/get_youtube_token.py` from the repo root (or pass the file's path), log in
   with the Google account that owns the channel, and copy the printed `YOUTUBE_CLIENT_ID`,
   `YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REFRESH_TOKEN`.
6. Run `python tools/verify_youtube.py`: it mints an access token and prints the channel the token
   is bound to. Confirm it is **But It Matters** (@butitmatters).

- Publishing needs `youtube.upload`; the daily analytics read needs `youtube.readonly`. The live
  token has those two; `yt-analytics.readonly` arrives with the next re-authorisation, and nothing
  reads it yet.
- ~100 uploads/day on the free quota.

---

## 9. GitHub — orchestration (free) ★ required

1. The live repo, `Shaan-alpha/AI-Reel-Factory`, is **public**, which gives unlimited Actions
   minutes. A private repo gets 2,000 minutes/month on the Free plan, and one run can take up to
   90 minutes.
2. **Settings → Secrets and variables → Actions → New repository secret.** The 15 in force:
   `GEMINI_API_KEY`, `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `CF_API_TOKEN`, `CF_ACCOUNT_ID`,
   `GOOGLE_TTS_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`,
   `ANTHROPIC_API_KEY` (§1, added 2026-10-22).
   Nothing for Vertex: it is keyless (§2b). The workflows also read `GEMINI_TTS_API_KEY`,
   `FACTCHECK_API_KEY` and `GH_MODELS_KEY`; none is set or needed (on Vertex the fact-check key
   is ignored, and GitHub Models is retired).
3. **Variables** tab. The repository variables in force:

   | Variable | Value | Why |
   |----------|-------|-----|
   | `FACTCHECK_STRICT` | `true` | Hold the reel when the fact-checker cannot run (workflow default `false`) |
   | `VISUAL_SOURCE` | `ai` | Cloudflare AI images (workflow default `photos`) |
   | `YOUTUBE_PRIVACY` | `public` | Same as the workflow default; `unlisted` for safe first runs |
   | `GOOGLE_TTS_VOICE` | `en-IN-Chirp3-HD-Zubenelgenubi` | No default; without it the Chirp fallback is skipped |

   Everything else uses the defaults written into `make-short.yml` and `production.yml`.
4. The workflows (all on `ubuntu-24.04` with Python 3.12; times are UTC, rule 15):
   - `make-short`: the pipeline, **on demand only**. Run it from the Actions tab (inputs `ideas`,
     default 3, and `wait_min`, default 20) or send `/makeshort [n]` to the bot (n from 1 to 8,
     5 without a number; it always asks for a 30-minute wait). Its schedule was removed on
     2026-09-29.
   - `production`: manual only, on purpose.
   - `analytics`: daily view snapshots; its writes also keep Supabase awake, and it re-enables the
     scheduled workflows that GitHub turns off after 60 days without a commit.
   - `tests`: on push, pull request and daily.
   - `verify-tts`, `verify-vertex`: manual diagnostics (below).

---

## 10. Instagram + TikTok — Phase 3 only (skip for MVP)

- **Instagram:** Business/Creator account + Facebook Page + Meta Developer App with
  `instagram_business_content_publish`, then **Meta App Review** (days–weeks). Start early.
- **TikTok:** Content Posting API **Direct Post** needs a full app audit (2–6 weeks);
  until audited, posts are private-only → draft/semi-auto.

---

## ✅ Local `.env`

Copy `.env.example` to `.env` and fill in the secrets from the sections above, plus
`WEBHOOK_SECRET` (§5b). Every other setting has a working default, explained line by line in
`.env.example`. To run the Vertex path locally, add the three settings from §2b. Check that every
required secret is present with `python -m src.config`.

Only the blank `.env.example` is committed; `.env` stays local (rule 5).

---

## Diagnostics (nothing is published)

Each makes a few small requests; the Vertex ones are billed per token like any other call.

| Check | What it proves | Run |
|-------|----------------|-----|
| `verify-tts` workflow | The channel voice renders on the Developer API and on Vertex (keyless), and the Chirp key lists its en-IN voices | Actions → verify-tts → Run workflow |
| `verify-vertex` workflow | CI reaches Vertex grounded search with no stored credential, on the grounding and the fact-check models | Actions → verify-vertex → Run workflow |
| `tools/verify_vertex.py` | The same from your machine (ADC) | `python tools/verify_vertex.py` |
| `tools/verify_gemini_tts.py` | The voice step of verify-tts, locally | `python tools/verify_gemini_tts.py` |
| `tools/verify_youtube.py` | The refresh token works and is bound to the right channel | `python tools/verify_youtube.py` |
| `tools/set_telegram_webhook.py --info` | Where the webhook points, and Telegram's last delivery error | `python tools/set_telegram_webhook.py --info` |
