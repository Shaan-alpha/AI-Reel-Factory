# Telegram control bot (Vercel webhook)

The operator's Telegram control surface for the AI Reel Factory, and the part of the system that
records digest taps. Telegram calls the Vercel function `api/telegram.py` (Python, stdlib only) on
every message and every button tap; it checks the secret token and the operator's chat, then acts.
No always-on server, no polling.

The pipeline workflows run with `TELEGRAM_APPROVAL_MODE=webhook`, so a run never reads Telegram
itself: it waits while this bot writes your taps to Supabase. If the bot is down, taps are not
recorded and the run's wait ends with the ideas still pending.

## Where it runs

- **Vercel account:** `shaan-alpha`. The operator has two Vercel accounts; deploy from this one.
- **Team / project:** `shaan-alphas-projects` / `telegram-bot`, on the free Hobby plan (Vercel
  limits Hobby to non-commercial use; see [docs/04](../docs/04-free-tools-reference.md)).
- **Webhook URL:** `https://telegram-bot-gilt-omega.vercel.app/api/telegram`, the stable
  production alias.
- **Deploys:** Vercel CLI only. The project is **not connected to git**: pushing to `main` does
  not update the bot.

## Commands

| Command | What it does |
|---|---|
| `/makeshort [n]` | Starts the GitHub **make-short** workflow on `main` with n ideas (1–8; 5 when no number is given) and a 30-minute wait for your taps → you get the approval digest |
| `/today` | Shorts published today (IST) + links |
| `/stats` | Total published + today + current top performer by views |
| `/pending` | Ideas waiting for your tap (up to 10, best score first) |
| `/latest` | The last 5 published Short links |
| `/help` (or `/start`) | Command list |

Each idea in the digest has **✅ Approve**, **❌ Reject** and **⏭️ Pass** buttons. On a tap the
bot:

- changes only an idea that is still pending (a tap on a decided idea answers "Already decided");
- stops approving at `APPROVAL_CAP` approved ideas (default 3, the pipeline's per-run cap);
- keeps the buttons when it cannot reach Supabase, so you can tap again.

(The `/makeshort` reply still says "Tap ✅ Make it"; the button itself reads ✅ Approve.)

Only the chat in `TELEGRAM_CHAT_ID` is served; messages and taps from any other chat are ignored.

## One-time setup

### 1. Create a GitHub token (so `/makeshort` can start the workflow)
GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** →
Generate new token:

- **Repository access:** Only select repositories → `Shaan-alpha/AI-Reel-Factory`.
- **Repository permissions:** **Actions: Read and write**. Nothing else.
- An expiry date. Renew it before it lapses; an expired token makes `/makeshort` answer
  "Couldn't start the Action".

Use it as `GH_PAT`. Do not use a classic token: the dispatch endpoint needs the classic `repo`
scope, which grants full access to every repository the account can reach, and this token sits
in the Vercel environment next to the Supabase secret key.

### 2. Check the Vercel account
```powershell
vercel whoami        # must print shaan-alpha
```
If it prints the other account, run `vercel logout`, then `vercel login` as shaan-alpha.

### 3. Link and deploy this folder
Deploy from `telegram-bot/`, which keeps the function (stdlib only, no dependencies) away from the
pipeline's heavy `requirements.txt`:
```powershell
cd telegram-bot
vercel link --project telegram-bot --team shaan-alphas-projects --yes   # once per machine; writes the gitignored .vercel/
vercel deploy --prod
```
`vercel project inspect` confirms the link (`shaan-alphas-projects/telegram-bot`). A brand-new
setup runs `vercel link` without flags and creates the project at its prompt.

### 4. Set the Vercel environment variables (Project → Settings → Environment Variables, or `vercel env add`)
| Var | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the `@ai_reel_factory_bot` token |
| `TELEGRAM_CHAT_ID` | your chat id (same as the pipeline) |
| `WEBHOOK_SECRET` | any random string (also used in step 5) |
| `GH_PAT` | the token from step 1 |
| `GH_REPO` | `Shaan-alpha/AI-Reel-Factory` |
| `SUPABASE_URL` | your Supabase URL |
| `SUPABASE_KEY` | the `sb_secret_…` key |
| `APPROVAL_CAP` | optional; unset means 3, matching the pipeline |

The live project has the first seven, for Production and Preview. Redeploy after setting or
changing any of them (`vercel deploy --prod`): a deployment keeps the values it started with.

### 5. Point Telegram at the function (once)
Add `WEBHOOK_SECRET` (the same value) to your local `.env`, then from the repo root:
```powershell
python tools/set_telegram_webhook.py https://telegram-bot-gilt-omega.vercel.app/api/telegram
python tools/set_telegram_webhook.py --info   # confirm the url, pending_update_count and any last error
```
The tool registers the secret and limits updates to messages and button taps. The production
alias follows each production deploy, so the webhook does not need setting again. While it is
set, Telegram refuses `getUpdates`; `--delete` removes it.

Done — message the bot `/help`. A plain GET on the URL answers `reel-factory bot ok`.

## Redeploying after a change
Every change to `api/telegram.py` needs a deploy:
```powershell
vercel whoami                          # shaan-alpha
cd telegram-bot; vercel deploy --prod
```
`vercel ls telegram-bot` lists the deployments, newest first. (The 2026-09-13 redeploy found the
live bot 94 days behind `main`.)

`tests/test_telegram_bot.py` runs in the main suite. It loads this folder's `api/telegram.py` by
path, so it tests the code in the repo, not what is deployed.

## Security
- **Fails closed:** with `WEBHOOK_SECRET` or `TELEGRAM_CHAT_ID` unset, every POST is answered
  **503** and nothing runs.
- A request whose `X-Telegram-Bot-Api-Secret-Token` header does not match `WEBHOOK_SECRET` is
  rejected with **401** (constant-time comparison).
- Messages and taps from any chat other than `TELEGRAM_CHAT_ID` are ignored.
- An authenticated request always gets **200**, even when handling it failed, so Telegram never
  retry-storms; replies are best-effort.
- `GH_PAT` can write to nothing but this repository's Actions (step 1).
- The bot sends GitHub REST API version `2022-11-28`, which GitHub supports until 2028-03-10.
