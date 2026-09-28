# data/

> **Dormant (checked 2026-09-27).** No Routine writes this file any more; it holds
> `{"ideas": []}`, so every idea comes from the Gemini/Groq generator in
> `src/ideation_fallback.py`. See the warning at the top of
> [../routines/ideation.md](../routines/ideation.md) before re-enabling a Routine.

**`daily-ideas.json`** — the idea bridge between the daily **Anthropic Routine** and the
pipeline. The Routine (Claude + web research, see [../routines/ideation.md](../routines/ideation.md))
overwrites this file each morning with 15–20 researched ideas, then commits + pushes.

The on-demand **make-short** workflow reads it via `ideation_fallback.seed_ideas()`:
it prefers these Routine ideas, de-dupes against ideas already in Supabase, and falls back
to the Gemini/Groq generator when this file is empty/absent or holds nothing fresh. Nothing here is secret —
the actual DB insert happens in GitHub Actions (which holds the Supabase key), never in the
Routine.

Schema:

```json
{"ideas": [
  {"niche": "impact-news", "title": "...", "hook": "...", "angle": "...",
   "est_score": 0.0, "sources": ["https://...", "https://..."]}
]}
```
