# CLAUDE.md — AI Reel Factory ("But It Matters")

> **Read this first, every session.** It is the operating contract for any agent
> (cold or warm) working in this repo. Rules here **override** default behavior.

## What this project is

A near-zero-cost **autonomous content system** that publishes **4–5 captioned
YouTube Shorts per day**, requiring exactly **one human action daily**: approving
4–5 ideas via a Telegram "Morning Digest."

- **Channel:** *But It Matters* — daily impact news/info explainers (India + world), soft/positive lean.
- **Primary goal:** Reliably ship 4–5 captioned Shorts/day. **Consistency beats sophistication.**
- **Cost target:** **$0/month** beyond the existing Claude Pro subscription.

## Onboarding (do this before working)

1. Read [STATUS.md](STATUS.md) — the live state of the build (what's done, what's next, blockers).
2. Read the docs **in order** (they are the source of truth):

   | # | Doc | Purpose |
   |---|-----|---------|
   | 1 | [docs/01-design-spec.md](docs/01-design-spec.md) | Architecture & decisions (the "why") |
   | 2 | [docs/02-implementation-plan.md](docs/02-implementation-plan.md) | Phase-1 MVP build, step by step |
   | 3 | [docs/03-setup-guide.md](docs/03-setup-guide.md) | Accounts + API keys to create first |
   | 4 | [docs/04-free-tools-reference.md](docs/04-free-tools-reference.md) | Every free tool, limits, links |
   | 5 | [docs/05-content-system.md](docs/05-content-system.md) | Templates + hook database |
   | 6 | [docs/06-roadmap.md](docs/06-roadmap.md) | The 5 phases, MVP → multi-niche scale |
   | 7 | [docs/07-architecture-diagram.md](docs/07-architecture-diagram.md) | Visual system + data flow |
   | 8 | [docs/08-news-niche-playbook.md](docs/08-news-niche-playbook.md) | **Niche compliance — non-negotiable** |

---

## The Rules

### A. Prime directives (always)

1. **Docs are living memory.** Before you finish any task, update [STATUS.md](STATUS.md)
   (what changed · what's next · blockers) and any doc your change affects. A cold agent —
   or future-you — must be able to resume from the markdown alone. If reality and the docs
   disagree, fix the docs.
2. **Free-first, best-possible.** Default to free tools. You **may** lean on the existing
   **Claude Pro** and **Google Gemini Pro** subscriptions when they meaningfully improve
   quality — but **never introduce a new paid or billed service/API**. If a step appears to
   need paid infrastructure, **stop and flag it** instead of signing anything up.
3. **Never self-attribute.** No `Co-Authored-By`, no "Generated with Claude Code," no AI
   credit anywhere — commits, PRs, code comments, or docs. *(This overrides default git
   behavior. Applies to this repo.)*

### B. Non-negotiable guardrails

4. **ToS boundary.** Claude ideation runs **only** via official Claude Code / Anthropic
   Routines. **Never** pipe `CLAUDE_CODE_OAUTH_TOKEN` into custom Python or the Agent SDK —
   that is a Terms-of-Service violation. The free fallback uses the Gemini/Groq *developer*
   APIs, never Claude.
5. **Secrets hygiene.** Never commit real keys. Only `.env.example` (blank values) is
   committed. Real values live in a local `.env` (gitignored) and GitHub Actions secrets.
6. **News-niche compliance is the monetization gate** (see [docs/08](docs/08-news-niche-playbook.md)):
   - **Originality** — every reel adds analysis ("why it matters"), never a bare summary.
   - **AI disclosure** — set YouTube's synthetic-content flag + a description disclosure line.
   - **Copyright** — CC0 B-roll only (no broadcaster/agency footage); cut every 5–8s; own words + cite.
   - **Accuracy** — ≥2 independent sources per claim; neutral framing; sensitivity filter applied.

### C. How to build

7. **Module-by-module.** Each module has one purpose and a typed input→output contract. Get
   it working and tested **in isolation** before wiring the next. Modules communicate only
   through typed data (Supabase rows / function returns) — never shared globals.
8. **Verify before claiming done.** Run the check; show the evidence. Never assert "works"
   or "fixed" without proof. If tests fail or a step was skipped, say so plainly.
9. **Stay in the current phase (YAGNI).** Don't build Phase 2+ features early. A phase's exit
   criteria are the gate to the next one.
10. **Reproducible environment.** Pin dependency versions in `requirements.txt`. Document
    system deps (e.g. FFmpeg). A cold agent should be able to set up from the docs alone.

### D. Runtime reliability (this is a headless, free-tier, cron-driven system)

11. **Fallbacks are mandatory — the digest never dies.** Every external dependency has a
    fallback chain: ideation **Claude → Gemini → Groq**, voice **edge-tts → Kokoro**, visuals
    **Pexels → Pixabay**. A single upstream failure must never kill the daily run.
12. **Idempotent, safe reruns.** Cron can and will retry. Check Supabase state before acting —
    never double-publish, double-insert, or re-spend quota. Every step is safe to run twice.
13. **Quota & cost awareness.** Respect free-tier ceilings (YouTube ~100 uploads/day, Gemini
    ~1,500 req/day, Groq per-model limits, Supabase 500 MB DB). Log usage; alert via Telegram
    on a hard failure.
14. **Fail loud on misconfig, soft on runtime.** A missing required secret/env var = hard stop
    with a clear message (`config.py` fails loudly). One reel failing inside the daily batch =
    log it, skip it, keep the rest going.
15. **Environment reality.** Dev machine is **Windows 11 / PowerShell**. The pipeline runs on
    **GitHub Actions in UTC** — convert local times accordingly. **Asset policy:** render
    locally → upload → **delete the local file**. Never store video in Supabase.

### E. Product principles (from the design spec)

16. **Consistency > perfection.** Hooks > visuals · retention > followers · consistency >
    cinematic quality · use **templates**, not pure randomness · **keep the human approval
    layer** (AI still produces occasional cringe).

### F. Tooling

17. **Use Context7 for library/API docs.** When working with any library, framework, SDK, API,
    CLI, or cloud service, fetch current docs via Context7 MCP before relying on memory — your
    training data may lag recent changes.

### G. Git & versioning

18. **Versioning discipline.**
    - **Conventional commits:** `type(scope): summary` — e.g. `feat(voice): add edge-tts module`,
      `fix(publish): handle quota error`, `docs(status): log module 4 done`. Types: `feat`,
      `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.
    - **Logically-grouped commits** — one coherent change each; no giant catch-all dumps.
    - **`CHANGELOG.md`** is kept current ([Keep a Changelog] style).
    - **Tag phase milestones:** `v0.1.0` = Phase-1 MVP done, `v0.2.0` = Phase 2, etc.
    - Keep [STATUS.md](STATUS.md) and the version in sync.
    - **Never force-push** shared history. Commit/push only when asked.
    - **No self-attribution in any commit or PR** (see rule 3).

[Keep a Changelog]: https://keepachangelog.com/

---

## Current status

- **Phase:** 1 (MVP) — **foundation only so far** (docs + rules). No pipeline code yet.
- Always check [STATUS.md](STATUS.md) for the authoritative, up-to-date state.
