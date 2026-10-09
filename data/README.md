# data/

> **Dormant (checked 2026-10-09).** No Routine has ever written to `daily-ideas.json`: it has held
> `{"ideas": []}` since it was created on 2026-06-09. Every idea comes from the generator in
> `src/ideation_fallback.py` (Google News and Trends headlines; Groq picks the stories, Gemini on
> Vertex researches them with grounded search and writes the ideas). See the warning at the top
> of [../routines/ideation.md](../routines/ideation.md) before enabling a Routine.

**`daily-ideas.json`** — the hand-off file for an **optional Claude Routine** (Claude Code + web
research, see [../routines/ideation.md](../routines/ideation.md)). Claude never runs inside the
pipeline (rule 4), so a Routine would overwrite this file with researched ideas, then commit and
push it.

The live pipeline does not depend on it. Only the on-demand run (`make-short` →
`ideation_fallback.seed_ideas()`) reads it: it takes up to the number of ideas asked for, skips
titles already in Supabase and stories pitched in the last `IDEA_DEDUP_DAYS` (10), and falls back
to the generator when the file is empty, absent or holds nothing fresh, which today is every run.
Nothing here is secret: the DB insert happens in GitHub Actions (which holds the Supabase key),
never in the Routine.

Schema, as `load_routine_ideas()` reads it:

```json
{"ideas": [
  {"niche": "impact-news", "title": "...", "hook": "...", "angle": "...",
   "est_score": 0.0, "sources": ["https://...", "https://..."]}
]}
```

- `title`, `hook` and `angle` are required; an idea missing one is dropped.
- `sources`: at least `MIN_SOURCES` (2) http(s) URLs that do not answer 404/410.
- `est_score` is clamped to 0–1 (default 0.5); an optional `share_score` (default: `est_score`)
  ranks the ideas.
- `niche` is replaced by the `NICHE` setting (default `impact-news`); at most 20 ideas are kept.
- The file has no date and nothing checks its age, so an unpicked idea can be offered days later;
  only the title and story checks above filter it.
