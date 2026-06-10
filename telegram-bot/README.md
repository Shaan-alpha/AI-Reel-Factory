# Telegram control bot (Vercel webhook)

An instant, free Telegram command surface for the AI Reel Factory. Telegram calls the Vercel
function `api/telegram.py` on every message; it authenticates the operator's chat + a secret
token and runs the command. No always-on server, no polling.

## Commands
| Command | What it does |
|---|---|
| `/makeshort [n]` | Starts the GitHub **make-short** Action (n ideas, default 5) → you get the approval digest |
| `/today` | Shorts published today (IST) + links |
| `/stats` | Total published + today + current top performer by views |
| `/pending` | Ideas waiting for your approval |
| `/latest` | The last few published Short links |
| `/help` | Command list |

Only the chat in `TELEGRAM_CHAT_ID` is served; everything else is ignored.

## One-time setup

### 1. Create a GitHub token (so `/makeshort` can start the Action)
GitHub → Settings → Developer settings → **Fine-grained token** scoped to `Shaan-alpha/AI-Reel-Factory`
with **Actions: Read and write**. Copy it (used as `GH_PAT`). *(A classic token with the `workflow`
scope also works.)*

### 2. Deploy this folder to Vercel
- Import the repo in Vercel and set **Root Directory = `telegram-bot`** (keeps it isolated from the
  pipeline's heavy `requirements.txt` — this function is stdlib-only, zero deps).
- Or from a terminal: `cd telegram-bot && npx vercel --prod`.

### 3. Set the Vercel environment variables (Project → Settings → Environment Variables)
| Var | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the `@ai_reel_factory_bot` token |
| `TELEGRAM_CHAT_ID` | your chat id (same as the pipeline) |
| `WEBHOOK_SECRET` | any random string (also used in step 4) |
| `GH_PAT` | the token from step 1 |
| `GH_REPO` | `Shaan-alpha/AI-Reel-Factory` |
| `SUPABASE_URL` | your Supabase URL |
| `SUPABASE_KEY` | the `sb_secret_…` key |

Redeploy after setting them.

### 4. Point Telegram at the function
Add `WEBHOOK_SECRET` (the same value) to your local `.env`, then:
```powershell
python tools/set_telegram_webhook.py https://<your-project>.vercel.app/api/telegram
python tools/set_telegram_webhook.py --info   # confirm url + pending_update_count
```

Done — message the bot `/help`.

## Security
- Requests without the matching `X-Telegram-Bot-Api-Secret-Token` header are rejected (401).
- Messages from any chat other than `TELEGRAM_CHAT_ID` are ignored.
- The function always returns 200 to Telegram so it never retry-storms; replies are best-effort.
