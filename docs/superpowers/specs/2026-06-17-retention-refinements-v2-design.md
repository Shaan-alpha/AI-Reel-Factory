# Retention Refinements v2 — Design

**Date:** 2026-06-17 · **Phase:** 1 (MVP quality) · **Cost:** $0 (FFmpeg/prompt-only, runs on GitHub Actions)

## Problem

Shorts can retain better. Four targeted refinements, all evidence-backed from the codebase:

1. Reels overshoot the intended length (a **38s reel** was observed vs the 25–30s target) — and on
   Shorts, completion rate is dominated by length.
2. The music bed is a flat 10% under the narration, not ducked — speech could be crisper.
3. No persistent brand presence or on-screen source citation.
4. Replays aren't encouraged — the ending doesn't visually rhyme with the opening.

## Goals & locked decisions

| Refinement | Decision |
|---|---|
| Length | Fix the stale punch-up prompt + tighten guards + a final hard word cap |
| Audio | **Sidechain ducking only** — no whoosh SFX (user choice) |
| Brand bug | **Logo PNG** the user provides; fail-soft skip until present |
| Source cite | Derived **domain** from the idea's first source URL (e.g. "SOURCE: pib.gov.in") |
| Loop | "Loop-friendly" (end clip reuses the opening clip), not frame-perfect |

All toggle-gated, all fail-soft (a failure degrades to today's behaviour, never kills the batch —
rules 11, 14). $0, no new dependency.

## Root cause of the length bug

The scriptwriter prompt correctly targets 25–30s / 65–75 words
([scriptwriter.py:36,56](../../../src/scriptwriter.py)), but the **punch-up pass that runs after it
still carries long-form instructions**:

- [scriptwriter.py:165](../../../src/scriptwriter.py): *"Keep the narration roughly the same length
  (~110-130 words)"* — stale from the long-form era.
- [scriptwriter.py:202](../../../src/scriptwriter.py): the acceptance guard allows **80–220 words**.

So a tight 65–75 word script gets punched up toward 100+ words → 35–40s reels.

## Design

### 1. Length enforcement — `src/scriptwriter.py`

- **Punch-up prompt:** replace "~110-130 words" with "keep it a 25–30s / ~65–75 word bite; you may
  sharpen wording but **never lengthen** it."
- **Acceptance guard** (the `80 <= len <= 220` check): accept the punch-up only when it stays within
  the cap (`<= SCRIPT_MAX_WORDS`, plus a small floor so it isn't gutted); otherwise **keep the
  original tight script** (the punch-up is a sharpener, not a lengthener).
- **Final hard guard:** after all steps, if the body exceeds `SCRIPT_MAX_WORDS` (default 80),
  truncate to the last full sentence at or under the cap and log a WARNING. Deterministic.
- **Config:** `SCRIPT_MAX_WORDS` (default `80`).

### 2. Audio ducking — `src/assembly.py`

Replace the flat `volume + amix` audio branch (`_build_cmd`, the `music_path` block) with sidechain
ducking so the music dips under speech and recovers between sentences:

```
[<voice>]asplit=2[v1][vkey];
[<music>]volume={MUSIC_VOLUME}[m];
[m][vkey]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[ducked];
[v1][ducked]amix=inputs=2:duration=first:normalize=0[aout]
```

- Gated `ENABLE_DUCKING` (default on) and **folded into the existing `polish` flag**: when
  `polish=False` (the fail-soft retry), the audio branch uses today's simple `volume + amix`.
- `MUSIC_VOLUME` default may rise slightly (it ducks when needed) — kept env-tunable.

### 3. Brand bug + source lower-third

**Logo bug — `src/assembly.py`.** If `BRAND_LOGO` (default `assets/brand/logo.png`) exists, add it
as an extra ffmpeg input and `overlay` it small + semi-transparent in a corner, persistent over the
whole reel. **Fail-soft: if the file is absent, skip the overlay entirely** (so the feature ships
now and activates when the user drops the logo in). Gated `ENABLE_BRAND_BUG` (default on). New
`assets/brand/` folder + a `.gitignore` exception for the logo (mirrors `assets/music/`).

**Source lower-third — `src/subtitles.py` + `src/production.py`.** [production.py:115](../../../src/production.py)
already has the `idea` dict in scope. Derive a clean label from `idea["sources"][0]` (strip scheme,
`www.`, and path → bare domain), and pass `source_label` to `burn_captions`. `_build_ass` adds one
ASS lower-third event ("SOURCE: <domain>", uppercased, emoji-stripped via the existing
`_NON_RENDERABLE` filter) shown for the first ~`SOURCE_CITE_SECONDS` (default 3.0s). Gated
`ENABLE_SOURCE_CITE` (default on); no label → no event. Strengthens news-compliance (rule 6: cite
sources).

### 4. Seamless loop — `src/assembly.py`

`ENABLE_SEAMLESS_LOOP` (default on): in `_ordered_clips`, force the **final slice's clip source to
equal the first slice's clip source** so the ending visually rhymes with the opening, smoothing
replays. Loop-friendly, not frame-perfect (frame-perfect would fight the narration-driven captions).
No-op when there's only one slice/clip.

## Config / env knobs

| Var | Default | Purpose |
|---|---|---|
| `SCRIPT_MAX_WORDS` | `80` | Hard word cap; over → truncate to last full sentence |
| `ENABLE_DUCKING` | `true` | Sidechain-duck music under narration |
| `ENABLE_BRAND_BUG` | `true` | Corner logo overlay (skips if file absent) |
| `BRAND_LOGO` | `assets/brand/logo.png` | Logo path |
| `ENABLE_SOURCE_CITE` | `true` | First-~3s "SOURCE: domain" lower-third |
| `SOURCE_CITE_SECONDS` | `3.0` | How long the citation shows |
| `ENABLE_SEAMLESS_LOOP` | `true` | End clip reuses the opening clip |

Documented in `.env.example`. Workflow `.yml` forwarding optional (defaults on).

## Files to change

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/scriptwriter.py` | Modify | Punch-up prompt fix; tighter guard; final word-cap truncation; `SCRIPT_MAX_WORDS` |
| `src/assembly.py` | Modify | Sidechain ducking (polish-gated); logo overlay (fail-soft); seamless-loop ordering |
| `src/subtitles.py` | Modify | `source_label` → ASS lower-third event |
| `src/production.py` | Modify | Derive source domain; pass `source_label` to `burn_captions` |
| `assets/brand/` + `.gitignore` | Create | Logo folder + commit exception |
| `tests/test_scriptwriter.py` / `test_assembly.py` / `test_subtitles.py` | Modify | TDD coverage for each change |
| `.env.example` / `STATUS.md` / `CHANGELOG.md` | Modify | Document + log |

## Compliance (rule 6)

The source lower-third **adds** an on-screen citation, reinforcing the "cite sources" requirement.
Length, ducking, logo, and loop are cosmetic/structural — no effect on accuracy, disclosure, or the
synthetic-content flag.

## Testing & verification

- **Unit (TDD):** punch-up no longer lengthens + over-cap body truncates to a sentence boundary;
  ducking graph contains `sidechaincompress` when enabled and simple `amix` when `polish=False`;
  logo overlay present only when the file exists; source label derives the bare domain; ASS contains
  the lower-third event; seamless-loop makes slice[-1] source == slice[0] source.
- **Live (gated):** a full render — audio probes show music present + voice intact; a frame shows
  the logo (if a test PNG is supplied) and the lower-third; reel duration tracks the (now shorter)
  narration.
- **End-to-end gate (rule 8):** one `make-short` run; confirm reel length is back in 25–30s and the
  logs are clean.

## Out of scope (YAGNI)

Whoosh/transition SFX (declined), caption word-pop animation, emoji-capable caption font,
script-level retention scaffolding (open-loop enforcement) — all deferred to a later pass.

## Risks

- **Sidechain params** too aggressive → pumping. Mitigated: conservative defaults + env-tunable +
  the simple-mix fallback.
- **Over-truncation** of a script mid-thought. Mitigated: truncate only at sentence boundaries; the
  prompt/guard fixes mean truncation rarely triggers.
- **On-screen clutter** (captions + cards + hook + bug + cite). Mitigated: bug is faint, cite is
  brief (~3s) and low; both individually toggleable.
