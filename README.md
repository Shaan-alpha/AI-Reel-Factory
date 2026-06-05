# 🎬 AI Reel Factory — **But It Matters**

**Channel:** *But It Matters* — daily impact news/info explainers (India + world).

A near-zero-cost autonomous system that generates ideas, writes scripts, narrates, assembles
captioned vertical video, and publishes faceless reels — requiring **one human action per
day**: approving 4–5 ideas via a Telegram "Morning Digest."

> **Primary goal:** Reliably publish **4–5 automated, captioned YouTube Shorts per day.**
> Consistency beats sophistication. Don't chase perfection early.

---

## 🧭 Start here

1. **[CLAUDE.md](CLAUDE.md)** — operating rules for any agent working in this repo. **Read first.**
2. **[STATUS.md](STATUS.md)** — live build state (what's done, what's next, blockers).
3. The docs, in order:

| # | Doc | What it's for |
|---|-----|---------------|
| 1 | [docs/01-design-spec.md](docs/01-design-spec.md) | Architecture & decisions (the "why") |
| 2 | [docs/02-implementation-plan.md](docs/02-implementation-plan.md) | Phase-1 MVP build, step by step |
| 3 | [docs/03-setup-guide.md](docs/03-setup-guide.md) | Accounts + API keys to create **before** coding |
| 4 | [docs/04-free-tools-reference.md](docs/04-free-tools-reference.md) | Every free tool, its limits, links |
| 5 | [docs/05-content-system.md](docs/05-content-system.md) | Templates + the hook database |
| 6 | [docs/06-roadmap.md](docs/06-roadmap.md) | The 5 phases from MVP to multi-niche scale |
| 7 | [docs/07-architecture-diagram.md](docs/07-architecture-diagram.md) | Visual system + data flow |
| 8 | [docs/08-news-niche-playbook.md](docs/08-news-niche-playbook.md) | **Niche compliance — non-negotiable** |

---

## ⚡ TL;DR — the stack

| Layer | Tool | Cost |
|-------|------|------|
| **Ideation (trend research)** | **Claude Code (Pro) via Anthropic Routine** | Pro sub |
| Ideation fallback | Gemini / Groq | Free |
| Orchestration | GitHub Actions (cron) + Routines | Free |
| Database/state | Supabase Postgres | Free |
| Approval UI | Telegram Bot | Free |
| Scripts | Gemini API (Groq failover) | Free |
| Narration | edge-tts (Kokoro fallback) | Free |
| Visuals | Pexels + Pixabay APIs | Free |
| Video assembly | FFmpeg | Free |
| Captions (MVP) | faster-whisper (word-by-word) | Free |
| Publishing | YouTube Data API v3 | Free |

**Cost target:** **$0/month** beyond the existing Claude Pro subscription.

---

## ✅ Current status (summary — see [STATUS.md](STATUS.md) for live detail)

- [x] Design spec written & approved
- [x] Documentation package imported into this repo
- [x] Project rules written ([CLAUDE.md](CLAUDE.md))
- [x] Niche locked: daily impact news/info explainers (India + world), soft/positive lean
- [x] Channel name locked: **But It Matters** · YouTube handle **@butitmatters** secured
- [x] Most API keys collected (Gemini · Groq · Supabase · Telegram · Pexels) — YouTube + Claude token pending
- [ ] Accounts & API keys finished → [docs/03-setup-guide.md](docs/03-setup-guide.md) · see [STATUS.md](STATUS.md)
- [ ] Phase-1 MVP build → [docs/02-implementation-plan.md](docs/02-implementation-plan.md)

---

## 🚀 When you're ready to build

1. Work through [docs/03-setup-guide.md](docs/03-setup-guide.md) — create accounts, run
   `claude setup-token`, collect API keys.
2. Open [docs/02-implementation-plan.md](docs/02-implementation-plan.md) and build module by module.
3. Each module is independently testable — get Module 1 working before Module 2.
