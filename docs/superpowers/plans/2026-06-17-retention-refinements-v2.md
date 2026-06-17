# Retention Refinements v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise Shorts retention via four refinements — fix the length-overshoot bug, sidechain-duck music under the voice, add a fail-soft brand-logo bug + a brief source-citation lower-third, and make reels loop-friendly.

**Architecture:** Source-agnostic A/V effects (ducking, logo overlay, loop ordering) live in `src/assembly.py`; the on-screen source citation lives in `src/subtitles.py` fed by `src/production.py`; the length fix lives in `src/scriptwriter.py`. Everything is toggle-gated and fail-soft: assembly's effects fold into the existing `polish` flag so the fail-soft retry degrades to today's plain render, and the logo/citation skip silently when their inputs are absent.

**Tech Stack:** Python 3, FFmpeg (`sidechaincompress`, `overlay`, `colorchannelmixer`), libass (ASS styling), `pytest`. No new runtime dependency.

## Global Constraints

- **No AI self-attribution** in any commit, code comment, or doc (rule 3).
- **Conventional commits** `type(scope): summary` (rule 18).
- **$0 / free-first**, no new billed service, no new runtime dependency (rules 2, 10).
- **Fail-soft at runtime** (rules 11, 14): any new filter/overlay failure must degrade gracefully, never crash the batch.
- **Idempotent / deterministic** (rule 12): effects don't use randomness; reruns are stable.
- **News compliance** (rule 6): the source citation *adds* on-screen sourcing; nothing weakens disclosure/accuracy.
- **Update `STATUS.md` + `CHANGELOG.md`** at the end (rules 1, 18).
- Output stays **1080×1920 H.264 yuv420p**, trimmed to narration length.
- `assets/brand/logo.png` already exists (committed); `BRAND_LOGO` defaults to it.

---

## File structure

| File | Modify | Responsibility |
|---|---|---|
| `src/scriptwriter.py` | Punch-up prompt length fix; tighter guard; `_truncate_to_words` + `SCRIPT_MAX_WORDS` enforcement |
| `src/assembly.py` | Sidechain ducking; brand-logo overlay (fail-soft); seamless-loop ordering helper |
| `src/subtitles.py` | `source_label` → ASS lower-third event + a `Source` style |
| `src/production.py` | Derive source domain from the idea; pass `source_label` to `burn_captions` |
| `tests/test_scriptwriter.py` / `test_assembly.py` / `test_subtitles.py` | TDD coverage |
| `.env.example` / `STATUS.md` / `CHANGELOG.md` | Document + log |

---

## Task 1: Length enforcement (scriptwriter)

Fixes the 38s-reel bug: the punch-up pass carries stale long-form length instructions and a loose guard.

**Files:**
- Modify: `src/scriptwriter.py` (`_PUNCHUP_PROMPT` ~line 165; `_punch_up_hook` guard line 202; new `_truncate_to_words`; `write_script` ~line 272)
- Test: `tests/test_scriptwriter.py`

**Interfaces:**
- Produces: `_truncate_to_words(body: str, max_words: int) -> str`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scriptwriter.py`:

```python
def test_truncate_to_words_cuts_at_sentence_boundary():
    from src import scriptwriter
    body = "One two three. Four five six seven. Eight nine ten eleven twelve."
    out = scriptwriter._truncate_to_words(body, 7)
    assert out == "One two three. Four five six seven."   # last full sentence within 7 words


def test_truncate_to_words_noop_when_within_cap():
    from src import scriptwriter
    body = "Short enough already."
    assert scriptwriter._truncate_to_words(body, 50) == body


def test_punchup_prompt_targets_short_form():
    from src import scriptwriter
    assert "110-130" not in scriptwriter._PUNCHUP_PROMPT      # stale long-form gone
    assert "never lengthen" in scriptwriter._PUNCHUP_PROMPT.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_scriptwriter.py -k "truncate or punchup_prompt" -v`
Expected: FAIL — `_truncate_to_words` undefined; prompt still says "110-130".

- [ ] **Step 3: Write minimal implementation**

In `src/scriptwriter.py`, add the helper (near the other private helpers, e.g. above `_ensure_sources`):

```python
def _truncate_to_words(body: str, max_words: int) -> str:
    """Hard length backstop: if the body exceeds max_words, cut to the last full sentence
    at or under the cap (so we never end mid-thought). Deterministic."""
    words = body.split()
    if len(words) <= max_words:
        return body
    truncated = " ".join(words[:max_words])
    ends = list(re.finditer(r"[.!?]", truncated))
    return (truncated[: ends[-1].end()] if ends else truncated).strip()
```

Ensure `import re` is present at the top of the file (add it if missing).

Fix the stale length line in `_PUNCHUP_PROMPT` — replace:

```
Every factual statement must stay exactly as true as the original. You may ONLY re-word, re-order, \
and intensify the DELIVERY. Keep the narration roughly the same length (~110-130 words) and keep \
the closing CTA / loop-back line.
```
with:
```
Every factual statement must stay exactly as true as the original. You may ONLY re-word, re-order, \
and intensify the DELIVERY. Keep it a tight 25-30 SECOND bite (~65-75 words) — sharpen wording but \
NEVER lengthen it — and keep the closing CTA / loop-back line.
```

Tighten the acceptance guard in `_punch_up_hook` (line 202) — replace:

```python
    if new_body and 80 <= len(new_body.split()) <= 220:  # sane rewrite only
```
with:
```python
    max_words = int(config.get("SCRIPT_MAX_WORDS", "80"))
    if new_body and 40 <= len(new_body.split()) <= max_words:  # accept only if it stayed short
```

Apply the hard backstop in `write_script` — replace the word-count warning block (lines ~272-274):

```python
    words = len(body.split())
    if not 50 <= words <= 90:  # ~65-75 target (25-30s); warn on a miss, don't block (rule 14)
        log.warning("scriptwriter: idea %s script is %d words (target ~65-75 / 25-30s)", idea_id, words)
```
with:
```python
    max_words = int(config.get("SCRIPT_MAX_WORDS", "80"))
    if len(body.split()) > max_words:
        log.warning("scriptwriter: idea %s script %d words > %d cap; truncating to a sentence.",
                    idea_id, len(body.split()), max_words)
        body = _truncate_to_words(body, max_words)
    if len(body.split()) < 50:
        log.warning("scriptwriter: idea %s script is short (%d words)", idea_id, len(body.split()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_scriptwriter.py -v`
Expected: PASS (all scriptwriter tests).

- [ ] **Step 5: Commit**

```bash
git add src/scriptwriter.py tests/test_scriptwriter.py
git commit -m "fix(scriptwriter): enforce 25-30s length — punch-up no longer lengthens + hard word cap"
```

---

## Task 2: Sidechain audio ducking (assembly)

Music dips under the voice and swells between sentences. Folded into the `polish` flag.

**Files:**
- Modify: `src/assembly.py` (the `music_path` block in `_build_cmd`; new `_ducking_enabled`)
- Test: `tests/test_assembly.py`

**Interfaces:**
- Consumes: `_build_cmd(..., polish: bool = True)` (existing).
- Produces: `_ducking_enabled() -> bool`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assembly.py`:

```python
def test_build_cmd_ducks_music_when_polish(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.delenv("ENABLE_DUCKING", raising=False)  # default on
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4", music_path="bed.mp3")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc and "asplit" in fc
    assert "[aout]" in cmd


def test_build_cmd_plain_mix_when_polish_false(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4",
                              music_path="bed.mp3", polish=False)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" not in fc      # fail-soft retry uses the simple mix
    assert "amix=inputs=2:duration=first" in fc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "ducks_music or plain_mix" -v`
Expected: FAIL — no `sidechaincompress` in the graph.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`, add the toggle helper near `_xfade_enabled`:

```python
def _ducking_enabled() -> bool:
    return config.get_bool("ENABLE_DUCKING", True)
```

Replace the music branch in `_build_cmd` — the current block:

```python
    if music_path:
        # music looped to cover narration, mixed quietly UNDER it so speech stays clear.
        # Narration stays at full volume; music sits low (env MUSIC_VOLUME, default 0.10).
        vol = config.get("MUSIC_VOLUME", "0.10")
        cmd += ["-stream_loop", "-1", "-i", music_path]  # music = input n+1
        parts.append(f"[{n + 1}:a]volume={vol}[abg]")
        parts.append(f"[{n}:a][abg]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]")
        audio_map = "[aout]"
    else:
        audio_map = f"{n}:a"
```
with:
```python
    if music_path:
        # music looped under the narration. With polish on, sidechain-DUCK it so it dips while
        # the voice speaks and swells between sentences (clearer speech = retention); the fail-soft
        # retry (polish=False) uses today's flat mix. MUSIC_VOLUME sets the base bed level.
        vol = config.get("MUSIC_VOLUME", "0.12")
        cmd += ["-stream_loop", "-1", "-i", music_path]  # music = input n+1
        if polish and _ducking_enabled():
            parts.append(f"[{n}:a]asplit=2[vmix][vkey]")
            parts.append(f"[{n + 1}:a]volume={vol}[bg]")
            parts.append("[bg][vkey]sidechaincompress=threshold=0.03:ratio=8:"
                         "attack=20:release=300[duck]")
            parts.append("[vmix][duck]amix=inputs=2:duration=first:dropout_transition=3:"
                         "normalize=0[aout]")
        else:
            parts.append(f"[{n + 1}:a]volume={vol}[abg]")
            parts.append(f"[{n}:a][abg]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]")
        audio_map = "[aout]"
    else:
        audio_map = f"{n}:a"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "music or mix or build_cmd" -v`
Expected: PASS (new ducking tests + existing `test_build_cmd_mixes_music_when_present`, which still finds `amix=inputs=2:duration=first` because the ducking path also ends in that amix).

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): sidechain-duck music under narration (polish-gated, fail-soft)"
```

---

## Task 3: Brand-logo bug overlay (assembly)

Overlay the committed circular logo small + semi-transparent in the top-right, persistent. Fail-soft: skip if the file is missing or `ENABLE_BRAND_BUG` is off; dropped on the polish retry.

**Files:**
- Modify: `src/assembly.py` (input building + final video map in `_build_cmd`; new `_brand_logo`)
- Test: `tests/test_assembly.py`

**Interfaces:**
- Produces: `_brand_logo() -> str | None` (path if the file exists and the toggle is on, else None).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assembly.py`:

```python
def test_build_cmd_overlays_logo_when_present(monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"; logo.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("BRAND_LOGO", str(logo))
    monkeypatch.delenv("ENABLE_BRAND_BUG", raising=False)
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=" in fc and "colorchannelmixer=aa=" in fc
    assert "[vout]" in cmd                       # logo-composited video is what gets mapped
    assert str(logo) in cmd                      # logo added as an input


def test_build_cmd_no_logo_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("BRAND_LOGO", str(tmp_path / "missing.png"))  # does not exist
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=" not in fc
    assert "[v]" in cmd and "[vout]" not in cmd  # plain video map


def test_brand_logo_disabled(monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"; logo.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setenv("BRAND_LOGO", str(logo))
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")
    assert assembly._brand_logo() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "logo" -v`
Expected: FAIL — `_brand_logo` undefined; no overlay in graph.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`, add near `_pick_music`:

```python
def _brand_logo() -> str | None:
    """Path to the brand-bug logo if enabled and the file exists, else None (fail-soft)."""
    if not config.get_bool("ENABLE_BRAND_BUG", True):
        return None
    path = config.get("BRAND_LOGO", "assets/brand/logo.png")
    return path if path and os.path.isfile(path) else None
```

In `_build_cmd`, the final filtergraph currently ends by producing `[v]` and maps it. After the
existing `[v]`-producing line (the grade/trim line), insert the optional logo overlay and switch the
video map. Find where the command maps video:

```python
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[v]", "-map", audio_map,
```

Change the logo handling and video map. First, add the logo as the **last** input (after voice/music
so existing indices don't shift) — add this right before the `cmd += ["-filter_complex", ...]` block:

```python
    video_label = "[v]"
    logo_path = _brand_logo() if polish else None
    if logo_path:
        logo_idx = n + 1 + (1 if music_path else 0)   # inputs: clips 0..n-1, voice n, [music], logo
        cmd += ["-loop", "1", "-i", logo_path]
        h = config.get("BRAND_LOGO_HEIGHT", "150")
        op = config.get("BRAND_LOGO_OPACITY", "0.55")
        m = config.get("BRAND_LOGO_MARGIN", "44")
        parts.append(f"[{logo_idx}:v]scale=-1:{h},format=rgba,colorchannelmixer=aa={op}[lg]")
        parts.append(f"[v][lg]overlay=W-w-{m}:{m}[vout]")
        video_label = "[vout]"
```
Then change the map line to use `video_label`:
```python
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", video_label, "-map", audio_map,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "logo or build_cmd or structure" -v`
Expected: PASS. (`test_build_cmd_structure` still passes — no `BRAND_LOGO` set there, so no overlay and the map stays `[v]`.)

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): brand-logo bug overlay (top-right, semi-transparent, fail-soft)"
```

---

## Task 4: Seamless-loop ordering (assembly)

End the reel on the opening clip so replays don't jar. Pure helper so it's unit-testable and leaves `_ordered_clips` untouched.

**Files:**
- Modify: `src/assembly.py` (new `_apply_seamless_loop`; call it in `assemble`)
- Test: `tests/test_assembly.py`

**Interfaces:**
- Produces: `_apply_seamless_loop(ordered: list[tuple[str, float]]) -> list[tuple[str, float]]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assembly.py`:

```python
def test_seamless_loop_ends_on_first_clip(monkeypatch):
    monkeypatch.delenv("ENABLE_SEAMLESS_LOOP", raising=False)  # default on
    ordered = [("a.mp4", 0.0), ("b.mp4", 0.0), ("c.mp4", 3.0)]
    out = assembly._apply_seamless_loop(ordered)
    assert out[-1] == ("a.mp4", 0.0)          # last slice reuses the opening clip
    assert out[:-1] == ordered[:-1]           # earlier slices unchanged


def test_seamless_loop_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_SEAMLESS_LOOP", "false")
    ordered = [("a.mp4", 0.0), ("b.mp4", 0.0)]
    assert assembly._apply_seamless_loop(ordered) == ordered


def test_seamless_loop_single_slice_noop(monkeypatch):
    monkeypatch.delenv("ENABLE_SEAMLESS_LOOP", raising=False)
    assert assembly._apply_seamless_loop([("a.mp4", 0.0)]) == [("a.mp4", 0.0)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "seamless" -v`
Expected: FAIL — `_apply_seamless_loop` undefined.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`, add near `_ordered_clips`:

```python
def _apply_seamless_loop(ordered: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Make the final slice reuse the opening clip so the ending visually rhymes with the start
    (loop-friendly replays). No-op when disabled or there's only one slice."""
    if config.get_bool("ENABLE_SEAMLESS_LOOP", True) and len(ordered) >= 2:
        return ordered[:-1] + [(ordered[0][0], 0.0)]
    return ordered
```

Wire it into `assemble` — change:

```python
    overlap = _xfade_seconds() if _xfade_enabled() else 0.0
    ordered = _ordered_clips(clip_paths, duration, overlap=overlap)
```
to:
```python
    overlap = _xfade_seconds() if _xfade_enabled() else 0.0
    ordered = _apply_seamless_loop(_ordered_clips(clip_paths, duration, overlap=overlap))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -v`
Expected: PASS (all assembly tests, incl. the live render).

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): loop-friendly ending — final clip reuses the opening shot"
```

---

## Task 5: Source-citation lower-third (subtitles + production)

A brief "Source: domain" line, derived from the idea's first source URL, burned for the first ~3s.

**Files:**
- Modify: `src/subtitles.py` (`_ass_header` Source style; `_build_ass` + `burn_captions` gain `source_label`)
- Modify: `src/production.py` (derive domain; pass `source_label`)
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `burn_captions(..., source_label: str | None = None)`; `_build_ass(..., source_label: str | None = None)`; `production._source_domain(sources: list[str] | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_subtitles.py`:

```python
def test_build_ass_includes_source_lowerthird(monkeypatch):
    from src import subtitles
    monkeypatch.delenv("ENABLE_SOURCE_CITE", raising=False)  # default on
    ass = subtitles._build_ass([(0.0, 0.5, "hi")], source_label="thehindu.com")
    assert "Style: Source," in ass
    assert "Source: thehindu.com" in ass


def test_build_ass_no_source_when_label_missing(monkeypatch):
    from src import subtitles
    ass = subtitles._build_ass([(0.0, 0.5, "hi")], source_label=None)
    assert "Source: " not in ass


def test_source_domain_derivation():
    from src import production
    assert production._source_domain(["https://www.thehindu.com/news/x"]) == "thehindu.com"
    assert production._source_domain(["pib.gov.in/PressRelease"]) == "pib.gov.in"
    assert production._source_domain([]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_subtitles.py -k "source" tests/test_production.py -k "source_domain" -v`
Expected: FAIL — `source_label` kwarg/`_source_domain` undefined.

- [ ] **Step 3: Write minimal implementation**

In `src/subtitles.py` `_ass_header`, add a `Source` style line after the `Card` style line:

```
Style: Card,{font},90,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,40,40,0,1
Style: Source,{font},46,&H20FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,2,40,40,120,1
```

Change `_build_ass`'s signature and add the event. Replace:

```python
def _build_ass(words: list[tuple[float, float, str]], hook_text: str | None = None,
               key_points: list[str] | None = None, total_dur: float | None = None) -> str:
    """Render the full .ass subtitle file: active-word karaoke captions + an optional frame-1
    hook banner + optional sparse on-screen key-point cards."""
    lines = [_ass_header()]
```
with:
```python
def _build_ass(words: list[tuple[float, float, str]], hook_text: str | None = None,
               key_points: list[str] | None = None, total_dur: float | None = None,
               source_label: str | None = None) -> str:
    """Render the full .ass subtitle file: active-word karaoke captions + an optional frame-1
    hook banner + optional sparse on-screen key-point cards + an optional source lower-third."""
    lines = [_ass_header()]

    # Brief source citation (bottom, faint) — credibility + news-compliance (rule 6: cite sources).
    if source_label and config.get_bool("ENABLE_SOURCE_CITE", True):
        secs = float(config.get("SOURCE_CITE_SECONDS", "3.0"))
        label = _ass_escape(_NON_RENDERABLE.sub("", f"Source: {source_label}"))
        lines.append(f"Dialogue: 1,{_format_ts(0)},{_format_ts(secs)},Source,,0,0,0,,{label}")
```

Change `burn_captions` to accept and forward `source_label`. Replace its signature:

```python
def burn_captions(video_path: str, audio_path: str, out_path: str,
                  hook_text: str | None = None, key_points: list[str] | None = None) -> str:
```
with:
```python
def burn_captions(video_path: str, audio_path: str, out_path: str,
                  hook_text: str | None = None, key_points: list[str] | None = None,
                  source_label: str | None = None) -> str:
```
and the `_build_ass` call inside it:
```python
        f.write(_build_ass(words, hook_text, key_points, total_dur))
```
with:
```python
        f.write(_build_ass(words, hook_text, key_points, total_dur, source_label))
```

In `src/production.py`, add the domain helper near the top-level helpers (e.g. above `produce_reel`/the produce function), and the `urlparse` import:

```python
from urllib.parse import urlparse


def _source_domain(sources: list[str] | None) -> str | None:
    """Bare domain of the first source URL (for an on-screen citation), or None."""
    for s in sources or []:
        host = urlparse(s if "://" in str(s) else "http://" + str(s)).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    return None
```

Pass it at the `burn_captions` call (the line that currently ends `key_points=script.get("key_points"))`):

```python
        final = subtitles.burn_captions(raw, audio, os.path.join(work, "reel_final.mp4"),
                                        hook_text=hook, key_points=script.get("key_points"),
                                        source_label=_source_domain(idea.get("sources")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_subtitles.py tests/test_production.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/subtitles.py src/production.py tests/test_subtitles.py
git commit -m "feat(subtitles): brief source-citation lower-third from the idea's first source"
```

---

## Task 6: Document knobs, update logs, end-to-end verify

**Files:**
- Modify: `.env.example`, `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Document the env knobs**

Append to `.env.example` under the existing "Edit polish (assembly)" block:

```
# --- Retention refinements v2 ---
SCRIPT_MAX_WORDS=       # hard cap; over -> truncate to last full sentence (default 80)
ENABLE_DUCKING=         # true (default) | false — sidechain-duck music under the voice
ENABLE_BRAND_BUG=       # true (default) | false — corner logo overlay (skips if file absent)
BRAND_LOGO=             # logo path (default assets/brand/logo.png)
BRAND_LOGO_HEIGHT=      # overlay height px (default 150)
BRAND_LOGO_OPACITY=     # 0..1 (default 0.55)
BRAND_LOGO_MARGIN=      # corner margin px (default 44)
ENABLE_SOURCE_CITE=     # true (default) | false — first-~3s "Source: domain" lower-third
SOURCE_CITE_SECONDS=    # how long the citation shows (default 3.0)
ENABLE_SEAMLESS_LOOP=   # true (default) | false — end clip reuses the opening shot
```

- [ ] **Step 2: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS — full suite green (live tests skip if offline / no FFmpeg).

- [ ] **Step 3: End-to-end verification render**

Run a local render and confirm the refinements land:

```bash
.venv/Scripts/python - <<'PY'
import os
os.environ["VISUAL_SOURCE"] = "ai"
from src import voice, visuals, assembly, subtitles
os.makedirs("outputs/_verify2", exist_ok=True)
audio, dur = voice.synthesize(
    "India just cleared its biggest rooftop-solar subsidy yet. Here is why it actually matters.",
    "outputs/_verify2")
clips = visuals.fetch_broll(["solar rooftop india", "power grid", "rupee money"],
                            target_seconds=dur, out_dir="outputs/_verify2")
raw = assembly.assemble(audio, clips, "outputs/_verify2/raw.mp4")
final = subtitles.burn_captions(raw, audio, "outputs/_verify2/final.mp4",
                                hook_text="India's solar bet", source_label="pib.gov.in")
print("duration:", round(assembly.probe_duration(final), 1), "s")
print("WROTE", final)
PY
```
Extract a first-second frame (`ffmpeg -ss 1.5 -i outputs/_verify2/final.mp4 -frames:v 1 outputs/_verify2/frame.png`) and confirm the **logo bug** (top-right) and **"Source: pib.gov.in"** lower-third are visible. **Gate (rule 8):** do not proceed if they're missing. Delete `outputs/_verify2/` afterward (rule 15).

- [ ] **Step 4: Update STATUS.md and CHANGELOG.md**

Bump `STATUS.md` version to `0.4.3` with a one-line summary; update the Module 3/6/7 rows to note length enforcement, ducking + logo bug + loop, and the source lower-third. Add a `## [0.4.3]` CHANGELOG entry (Keep a Changelog) describing all four refinements + the new knobs.

- [ ] **Step 5: Commit**

```bash
git add .env.example STATUS.md CHANGELOG.md
git commit -m "docs(retention): document v2 knobs; update STATUS and CHANGELOG"
```

---

## Self-review

- **Spec coverage:** length fix → Task 1 · ducking → Task 2 · brand bug → Task 3 · seamless loop → Task 4 · source lower-third → Task 5 · config knobs → Tasks 1/2/3/5/6 · end-to-end gate → Task 6 · compliance (source cite) → Task 5. All spec sections covered.
- **Placeholder scan:** none — every code step shows the actual code; commands have expected output.
- **Type consistency:** `_truncate_to_words`, `_ducking_enabled`, `_brand_logo`, `_apply_seamless_loop`, `_source_domain`, and the `source_label` kwarg on `_build_ass`/`burn_captions` are used consistently across tasks and tests.
- **Input-index safety (Task 2 + 3):** the logo is always added as the **last** ffmpeg input, so it never shifts the voice (`n`) or music (`n+1`) indices the ducking graph relies on.
- **Regression note:** ducking still ends in `amix=inputs=2:duration=first`, so the existing `test_build_cmd_mixes_music_when_present` keeps passing; the seamless-loop helper is separate from `_ordered_clips`, so its tests are untouched.
