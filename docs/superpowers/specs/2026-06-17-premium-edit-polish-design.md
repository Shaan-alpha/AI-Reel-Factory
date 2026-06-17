# Premium Edit Polish Layer — Design

**Date:** 2026-06-17 · **Phase:** 1 (MVP quality) · **Cost:** $0 (FFmpeg-only, CPU, runs on GitHub Actions)

## Problem

Published Shorts "feel raw / unedited." The brand is *But It Matters* — daily impact-news
explainers that need to look intentional and premium, not like a stock slideshow.

## Key finding (scope correction)

The codebase already does more than it appeared:

- [src/visuals.py](../../../src/visuals.py) `fetch_broll` has a `VISUAL_SOURCE` switch: `photos`
  (Pexels photos + Ken Burns), **`ai` (Cloudflare Workers AI / Flux + Ken Burns)**, or `video`.
- The GitHub repo variable **`VISUAL_SOURCE` is already `ai`** (set 2026-06-09); `CF_API_TOKEN` /
  `CF_ACCOUNT_ID` are present as repo secrets. Verified live: a Flux image generates in ~2.2s, free.
- Ken Burns zoom already exists (`_image_to_kenburns_clip`, [src/visuals.py:291](../../../src/visuals.py)).

**So the cloud pipeline already produces story-specific AI B-roll with motion.** A new AI-image
module would duplicate working code. The genuinely-missing layer is the **edit/polish between and
over clips**, which lives in assembly and does not exist yet.

## Goals

Add a free, FFmpeg-only "polish" layer so finished reels look professionally edited:

1. **Crossfade transitions** between cuts (today: abrupt hard `concat`).
2. **Cinematic color grade** applied once over the whole reel — the single biggest lever, because
   it unifies independently-generated Flux shots (each currently has its own color/contrast) into
   one coherent house look.
3. **Vignette + subtle film grain** for depth instead of a flat digital look.
4. **Ken Burns variety** — alternate zoom-in / zoom-out and pan direction so motion isn't monotonous.

All behind config toggles, all **fail-soft**: if the polished filtergraph errors, fall back to
today's plain render so the daily digest never dies (rules 11, 14).

## Non-goals (YAGNI — explicitly out of scope)

- New AI-image provider (Gemini / Imagen). Free Cloudflare Flux already works; "paid-ready Imagen"
  is a future flip, not now.
- Audio polish (music ducking / intro-outro stings). User de-prioritized it.
- Scene-detection, beat-sync, Telegram image preview/approval. Future phases.

## Design

Two files change. Grade/transitions are **source-agnostic** → they belong in assembly (applied to
the final stream, so AI clips, stock photos, and stock video all benefit). Ken Burns variety is
image-specific → it belongs in visuals.

### 1. Color grade + vignette + grain — `src/assembly.py`

Applied **once** on the concatenated stream (one pass = consistent look + cheap), after the
trim-to-duration step. Subtle, tunable:

```
eq=contrast=1.06:saturation=1.12:brightness=0.01:gamma=0.98,
colorbalance=rs=0.03:gs=0.01:bs=-0.03,    # slight warmth
vignette=PI/5,                            # gentle edge darkening
noise=alls=8:allf=t+u                     # subtle temporal film grain
```

Each filter is independently gated (`ENABLE_GRADE`, `ENABLE_VIGNETTE`, `ENABLE_GRAIN`) and the
numeric strengths are env-tunable so the house look can be dialed without code changes.

### 2. Crossfade transitions — `src/assembly.py`

Replace the hard `concat` with a chained `xfade` (crossfade). For N slices each `S` seconds long,
overlapping by `X` seconds (`XFADE_SECONDS`, default 0.35):

- `xfade=transition=fade:duration=X:offset=i*(S-X)` for the i-th join (i = 1..N-1).
- Total timeline = `N*S - (N-1)*X`. `_ordered_clips` recomputes the slice count so the overlapped
  timeline still over-covers the narration, then the final stream is trimmed to the exact duration.

Gated by `ENABLE_XFADE` (default on). When off, the existing `concat` path is used unchanged.

### 3. Ken Burns variety — `src/visuals.py`

`_image_to_kenburns_clip` currently always zooms in, centered. Add a deterministic `index` param:
even indices zoom **in** (1.0→1.12), odd indices zoom **out** (1.12→1.0); pan x/y drifts in an
alternating direction by index. Deterministic → reruns are stable (rule 12). Caller in
`_fetch_image_broll` passes the loop index.

### 4. Fail-soft fallback — `src/assembly.py`

`_build_cmd` gains a `polish: bool`. `assemble()` builds and runs the **polished** command first;
on a non-zero ffmpeg exit it logs and retries with `polish=False` (today's plain graph). The reel
is never lost to a filtergraph error (rules 11, 14).

## Config / env knobs (all optional, sensible defaults)

| Var | Default | Purpose |
|---|---|---|
| `ENABLE_XFADE` | `true` | Crossfade transitions between cuts |
| `XFADE_SECONDS` | `0.35` | Crossfade overlap length |
| `ENABLE_GRADE` | `true` | Cinematic color grade (eq + warmth) |
| `GRADE_CONTRAST` | `1.06` | Contrast multiplier |
| `GRADE_SATURATION` | `1.12` | Saturation multiplier |
| `ENABLE_VIGNETTE` | `true` | Edge darkening |
| `ENABLE_GRAIN` | `true` | Subtle film grain |
| `GRAIN_STRENGTH` | `8` | `noise` alls value |

Documented in `.env.example`. Workflow `.yml` forwarding is optional (defaults are on); add a
`POLISH`-related `vars.*` line only if we want a kill switch from the GitHub UI.

## Files to change

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/assembly.py` | Modify | Grade/vignette/grain pass; xfade chain + recomputed slice count; `polish` flag + fail-soft retry; new knobs |
| `src/visuals.py` | Modify | Ken Burns variety (alternating zoom/pan by index) |
| `tests/test_assembly.py` | Modify | Grade tokens present/absent by toggle; xfade graph + offset math; fail-soft falls back to plain graph; live polished render (dims/duration) |
| `tests/test_visuals.py` | Modify | KB expr differs by index (in vs out) |
| `.env.example` | Modify | Document the knobs |
| `STATUS.md` / `CHANGELOG.md` / assembly docstring | Modify | Reflect the new capability (rules 1, 18) |

## Compliance (rule 6)

No change to news-niche compliance: color grade/transitions don't alter facts, the synthetic-content
flag + description disclosure already cover the AI imagery, and CC0/stock + AI-stand-in rules are
untouched. Grade is purely cosmetic.

## Testing & verification

- **Unit:** assert each polish filter appears in the ffmpeg argv when enabled and is absent when
  toggled off; assert the xfade offset math + recomputed slice count; assert the fail-soft path
  (simulate a non-zero ffmpeg exit → second call uses the plain graph).
- **Live (gated):** a full polished render → output exists, 1080×1920, duration matches narration.
- **Verification gate (rule 8):** render a **before/after sample** reel (current vs. polished) on a
  real script so the quality jump is visible before merge. Evidence shown, not asserted.

## Risks

- **xfade chain complexity** on long reels — mitigated: current target is ~25–30s (~8–9 slices),
  and the fail-soft fallback guarantees a render even if the graph misbehaves.
- **Over-grading** looking unnatural — mitigated: subtle defaults + env-tunable strengths + the
  before/after gate.
- **Double-handling of Ken Burns clips** (visuals bakes motion; assembly re-slices them) — accepted
  for now; motion survives within each slice and xfade smooths the joins. Revisit only if it reads
  poorly in the sample.
