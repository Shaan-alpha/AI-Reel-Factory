# data/

**`daily-ideas.json`** — the idea bridge between the daily **Anthropic Routine** and the
pipeline. The Routine (Claude + web research, see [../routines/ideation.md](../routines/ideation.md))
overwrites this file each morning with 15–20 researched ideas, then commits + pushes.

The on-demand **make-short** workflow reads it via `ideation_fallback.seed_ideas()`:
it prefers these Routine ideas, de-dupes against ideas already in Supabase, and falls back
to the Gemini/Groq generator only when this file is empty/absent. Nothing here is secret —
the actual DB insert happens in GitHub Actions (which holds the Supabase key), never in the
Routine.

Schema:

```json
{"ideas": [
  {"niche": "impact-news", "title": "...", "hook": "...", "angle": "...",
   "est_score": 0.0, "sources": ["https://...", "https://..."]}
]}
```
