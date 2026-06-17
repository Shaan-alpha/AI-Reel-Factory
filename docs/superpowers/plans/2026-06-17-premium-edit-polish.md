# Premium Edit Polish Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rendered Shorts look professionally edited by adding a free, FFmpeg-only "polish" layer — crossfade transitions, a cinematic color grade that unifies AI-generated shots, vignette + grain, and Ken Burns motion variety.

**Architecture:** Two existing modules change. Source-agnostic effects (transitions, grade, vignette, grain) go in `src/assembly.py`, applied to the final composited stream. Image-specific motion variety goes in `src/visuals.py`. Everything is config-toggled and **fail-soft**: `assemble()` tries the polished filtergraph first and, on any ffmpeg error, retries with today's plain graph so the daily digest never dies.

**Tech Stack:** Python 3, FFmpeg/`libavfilter` (`xfade`, `zoompan`, `eq`, `colorbalance`, `vignette`, `noise`) — all already available; `pytest`. No new dependencies.

## Global Constraints

- **No AI self-attribution** in any commit, code comment, or doc (CLAUDE.md rule 3).
- **Conventional commits**: `type(scope): summary` (rule 18).
- **$0 / free-first** — no new billed service, no new dependency (rules 2, 10).
- **Fail-soft at runtime, fail-loud only on misconfig** (rule 14): a filtergraph error must fall back to a working render, never crash the batch.
- **Idempotent** (rule 12): effects are deterministic per reel so cron retries are stable.
- **Update `STATUS.md` + `CHANGELOG.md`** at the end (rules 1, 18).
- **Env reality**: dev = Windows 11 / PowerShell; pipeline = GitHub Actions UTC. Tests must pass on both; FFmpeg-dependent tests skip gracefully when the binary is absent.
- Output stays **1080×1920 H.264 yuv420p**, trimmed to narration length.

---

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/visuals.py` | Modify | Ken Burns variety: alternate zoom-in / zoom-out by clip index |
| `src/assembly.py` | Modify | `_grade_filters()`; xfade chain + overlap-aware `_ordered_clips`; `polish` flag on `_build_cmd`; fail-soft retry in `assemble()`; new env knobs |
| `tests/test_visuals.py` | Modify | KB zoom expression differs by index |
| `tests/test_assembly.py` | Modify | Grade tokens by toggle; xfade graph + offset math; overlap-aware slice count; fail-soft fallback; update one existing test for the new default |
| `.env.example` | Modify | Document the polish knobs |
| `STATUS.md` / `CHANGELOG.md` | Modify | Record the capability |

---

## Task 1: Ken Burns motion variety (visuals)

Today every image clip zooms in identically (`src/visuals.py` `_image_to_kenburns_clip`, ~line 291). Add an `index` so even clips zoom **in** and odd clips zoom **out** — kills the monotonous feel. Deterministic per index (rule 12).

**Files:**
- Modify: `src/visuals.py` (`_image_to_kenburns_clip`, and its caller `_fetch_image_broll` ~line 321)
- Test: `tests/test_visuals.py`

**Interfaces:**
- Produces: `_image_to_kenburns_clip(image_path: str, dest: str, seconds: float, index: int = 0) -> None`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_visuals.py`:

```python
def test_kenburns_zoom_varies_by_index(monkeypatch):
    """Even index zooms in, odd index zooms out — built into the ffmpeg vf string."""
    captured = []

    def fake_run(cmd, **kw):
        captured.append(" ".join(cmd))
        class R:  # minimal CompletedProcess stand-in
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(visuals, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(visuals.subprocess, "run", fake_run)

    visuals._image_to_kenburns_clip("in.jpg", "out0.mp4", 7.0, index=0)
    visuals._image_to_kenburns_clip("in.jpg", "out1.mp4", 7.0, index=1)

    vf_in, vf_out = captured[0], captured[1]
    assert "zoom+" in vf_in            # even → zoom IN (increasing)
    assert "zoom-" in vf_out           # odd  → zoom OUT (decreasing)
    assert vf_in != vf_out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_visuals.py::test_kenburns_zoom_varies_by_index -v`
Expected: FAIL — `_image_to_kenburns_clip()` takes no `index` arg / zoom string identical.

- [ ] **Step 3: Write minimal implementation**

In `src/visuals.py`, replace `_image_to_kenburns_clip`:

```python
def _image_to_kenburns_clip(image_path: str, dest: str, seconds: float, index: int = 0) -> None:
    """Render a slow Ken Burns move over an image → 1080x1920 mp4 clip (FFmpeg).

    Motion alternates by index for variety (rule 16): even = slow zoom IN, odd = slow zoom OUT.
    Deterministic per index so cron retries are stable (rule 12)."""
    from src.assembly import _ffmpeg

    frames = int(seconds * 30)
    if index % 2 == 0:
        z = "min(zoom+0.0010,1.12)"                      # slow zoom IN
    else:
        z = "if(eq(on,0),1.12,max(zoom-0.0009,1.0))"     # slow zoom OUT (start zoomed, pull back)
    vf = (
        "scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1920:fps=30,setsar=1"
    )
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-loop", "1", "-i", image_path, "-t", f"{seconds:.2f}",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", dest],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ken burns failed ({proc.returncode}): {proc.stderr[-400:]}")
```

Then pass the index at the call site in `_fetch_image_broll`. Change:

```python
            _image_to_kenburns_clip(img, clip, _IMAGE_CLIP_SECONDS)
```
to:
```python
            _image_to_kenburns_clip(img, clip, _IMAGE_CLIP_SECONDS, index=i)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_visuals.py -v`
Expected: PASS (all visuals tests).

- [ ] **Step 5: Commit**

```bash
git add src/visuals.py tests/test_visuals.py
git commit -m "feat(visuals): alternate Ken Burns zoom in/out by index for motion variety"
```

---

## Task 2: Cinematic color grade + vignette + grain (assembly)

Add a single grade pass on the final stream — the biggest premium lever, because it unifies independently-generated Flux shots into one house look. Each effect toggles independently.

**Files:**
- Modify: `src/assembly.py` (new `_grade_filters()`; wire into the trim chain in `_build_cmd`)
- Test: `tests/test_assembly.py`

**Interfaces:**
- Produces: `_grade_filters() -> str` — comma-joined ffmpeg filter string, `""` when all grade toggles are off.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_assembly.py`:

```python
def test_grade_filters_present_by_default(monkeypatch):
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)  # defaults on
    f = assembly._grade_filters()
    assert "eq=contrast=" in f and "vignette" in f and "noise=" in f


def test_grade_filters_empty_when_all_disabled(monkeypatch):
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.setenv(k, "false")
    assert assembly._grade_filters() == ""


def test_build_cmd_includes_grade_in_filtergraph(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "false")  # isolate the concat path
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)
    cmd = assembly._build_cmd([("c0.mp4", 0.0), ("c1.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "eq=contrast=" in fc and "vignette" in fc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py::test_grade_filters_present_by_default -v`
Expected: FAIL — `_grade_filters` not defined.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`, add the helper (near `_clip_seconds`):

```python
def _grade_filters() -> str:
    """Cinematic grade applied once on the final stream — unifies varied shots into a house look.

    Each effect is independently env-gated. Returns a comma-joined ffmpeg filter string (or "")."""
    parts = []
    if config.get_bool("ENABLE_GRADE", True):
        contrast = config.get("GRADE_CONTRAST", "1.06")
        saturation = config.get("GRADE_SATURATION", "1.12")
        parts.append(f"eq=contrast={contrast}:saturation={saturation}:brightness=0.01:gamma=0.98")
        parts.append("colorbalance=rs=0.03:gs=0.01:bs=-0.03")  # slight warmth
    if config.get_bool("ENABLE_VIGNETTE", True):
        parts.append("vignette=PI/5")
    if config.get_bool("ENABLE_GRAIN", True):
        strength = config.get("GRAIN_STRENGTH", "8")
        parts.append(f"noise=alls={strength}:allf=t+u")  # subtle temporal film grain
    return ",".join(parts)
```

Then wire it into the final trim of `_build_cmd`. Replace this line:

```python
    parts.append(f"[vc]trim=0:{duration:.3f},setpts=PTS-STARTPTS[v]")
```
with:
```python
    grade = _grade_filters()
    grade_suffix = ("," + grade) if grade else ""
    parts.append(f"[vc]trim=0:{duration:.3f},setpts=PTS-STARTPTS{grade_suffix}[v]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "grade or build_cmd" -v`
Expected: PASS (grade tests pass; existing `test_build_cmd_structure` still passes because `ENABLE_XFADE` is irrelevant here and grade is additive).

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): cinematic color grade, vignette and film grain (toggle-gated)"
```

---

## Task 3: Crossfade transitions + overlap-aware slice count (assembly)

Replace hard `concat` with a chained `xfade` crossfade. For N slices each `S` seconds with overlap `X`, the i-th join uses `offset = i*(S - X)`; total timeline = `N*S - (N-1)*X`. `_ordered_clips` must produce enough slices to cover that overlapped timeline.

**Files:**
- Modify: `src/assembly.py` (`_ordered_clips` gains `overlap`; new `_xfade_enabled`/`_xfade_seconds`; xfade branch in `_build_cmd`)
- Test: `tests/test_assembly.py` (new xfade tests; **update** `test_build_cmd_structure`)

**Interfaces:**
- Consumes: `_grade_filters()` from Task 2.
- Produces: `_ordered_clips(clip_paths, duration, overlap: float = 0.0)`; `_xfade_enabled() -> bool`; `_xfade_seconds() -> float`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assembly.py`:

```python
def test_ordered_clips_overlap_adds_slices(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "6")
    # overlap=0 reproduces the old count exactly (regression guard)
    assert len(assembly._ordered_clips(["a.mp4", "b.mp4"], 18.0, overlap=0.0)) == 4
    # with overlap each slice covers less → needs at least as many slices
    assert len(assembly._ordered_clips(["a.mp4", "b.mp4"], 18.0, overlap=1.0)) >= 4


def test_build_cmd_xfade_chain_and_offsets(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "true")
    monkeypatch.setenv("XFADE_SECONDS", "0.4")
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    cmd = assembly._build_cmd(
        [("c0.mp4", 0.0), ("c1.mp4", 0.0), ("c2.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.400" in fc
    assert "concat=n=" not in fc                 # concat replaced by xfade
    assert "offset=3.100" in fc                  # i=1 → 1*(3.5-0.4)=3.1
    assert "offset=6.200" in fc                  # i=2 → 2*(3.5-0.4)=6.2
    assert "[v]" in cmd                          # final graded video still mapped


def test_build_cmd_single_slice_uses_concat_not_xfade(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "true")
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 5.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=1" in fc and "xfade" not in fc  # nothing to crossfade with one clip
```

Also **update the existing** `test_build_cmd_structure` so it exercises the plain path: add `monkeypatch.setenv("ENABLE_XFADE", "false")` as its first line (it already asserts `concat=n=2`, which is now the xfade-off behavior).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "xfade or overlap or single_slice" -v`
Expected: FAIL — `_ordered_clips()` takes no `overlap`; no xfade in filtergraph.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`:

(a) Add knob helpers near `_clip_seconds`:

```python
def _xfade_enabled() -> bool:
    return config.get_bool("ENABLE_XFADE", True)


def _xfade_seconds() -> float:
    """Crossfade overlap, clamped below half a slice so xfade offsets stay positive."""
    try:
        v = float(config.get("XFADE_SECONDS", "0.35"))
    except (TypeError, ValueError):
        v = 0.35
    return max(0.1, min(v, _clip_seconds() * 0.5))
```

(b) Make `_ordered_clips` overlap-aware. Replace its slice-count line:

```python
    slice_s = _clip_seconds()
    n = min(_MAX_SLICES, math.ceil(duration / slice_s) + 1)  # +1 slice of safety margin
```
with the signature change and overlap-aware count:

```python
def _ordered_clips(clip_paths: list[str], duration: float,
                   overlap: float = 0.0) -> list[tuple[str, float]]:
    ...docstring unchanged...
    slice_s = _clip_seconds()
    step = max(0.1, slice_s - overlap)  # effective coverage per slice after the first (xfade overlaps)
    if duration > slice_s:
        n = min(_MAX_SLICES, math.ceil((duration - slice_s) / step) + 2)
    else:
        n = 2
```

(Keep the rest of `_ordered_clips` — `durs`, `used`, stagger loop — unchanged.)

(c) Add the xfade branch in `_build_cmd`. Replace the concat + trim block:

```python
    concat_in = "".join(f"[v{k}]" for k in range(n))
    parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vc]")
    grade = _grade_filters()
    grade_suffix = ("," + grade) if grade else ""
    parts.append(f"[vc]trim=0:{duration:.3f},setpts=PTS-STARTPTS{grade_suffix}[v]")
```
with:
```python
    grade = _grade_filters()
    grade_suffix = ("," + grade) if grade else ""
    if _xfade_enabled() and n >= 2:
        xf = _xfade_seconds()
        prev = "[v0]"
        for i in range(1, n):
            offset = i * (slice_s - xf)
            dst = "[vx]" if i == n - 1 else f"[xf{i}]"
            parts.append(
                f"{prev}[v{i}]xfade=transition=fade:duration={xf:.3f}:offset={offset:.3f}{dst}")
            prev = dst
        parts.append(f"[vx]trim=0:{duration:.3f},setpts=PTS-STARTPTS{grade_suffix}[v]")
    else:
        concat_in = "".join(f"[v{k}]" for k in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vc]")
        parts.append(f"[vc]trim=0:{duration:.3f},setpts=PTS-STARTPTS{grade_suffix}[v]")
```

(Remove the now-duplicated `grade`/`grade_suffix` lines added in Task 2 so they're computed once, above the branch.)

(d) Update the `assemble()` call to `_ordered_clips` to pass the overlap so coverage accounts for xfade:

```python
    overlap = _xfade_seconds() if _xfade_enabled() else 0.0
    ordered = _ordered_clips(clip_paths, duration, overlap=overlap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -v`
Expected: PASS — all assembly unit tests, including the updated `test_build_cmd_structure` and the new xfade/overlap tests. (`test_live_full_reel` skips offline or renders the full polished reel.)

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): crossfade transitions with overlap-aware slice count"
```

---

## Task 4: Fail-soft polished render (assembly)

A polished filtergraph is more complex, so guarantee the reel survives a filter error: try polished, fall back to the plain graph (rules 11, 14).

**Files:**
- Modify: `src/assembly.py` (`_build_cmd` gains `polish: bool`; `assemble()` retries plain on failure)
- Test: `tests/test_assembly.py`

**Interfaces:**
- Consumes: `_grade_filters()`, `_xfade_enabled()`, `_xfade_seconds()` from Tasks 2–3.
- Produces: `_build_cmd(..., polish: bool = True)` — when `False`, forces no xfade and no grade.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_assembly.py`:

```python
def test_build_cmd_plain_when_polish_false(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    for k in ("ENABLE_XFADE", "ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)  # all default ON…
    cmd = assembly._build_cmd([("c0.mp4", 0.0), ("c1.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4",
                              polish=False)  # …but polish=False overrides
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade" not in fc and "eq=contrast=" not in fc
    assert "concat=n=2" in fc


def test_assemble_falls_back_to_plain_on_polish_failure(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00")
    clip = tmp_path / "c.mp4"; clip.write_bytes(b"\x00")
    out = tmp_path / "o.mp4"

    monkeypatch.setattr(assembly, "probe_duration", lambda p: 6.0)
    monkeypatch.setattr(assembly, "_pick_music", lambda p: None)

    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        fc = cmd[cmd.index("-filter_complex") + 1]
        polished = ("xfade" in fc) or ("eq=contrast=" in fc)
        class R:
            returncode = 1 if (polished and calls["n"] == 1) else 0
            stderr = "boom"
        if R.returncode == 0:
            out.write_bytes(b"\x00" * 60_000)  # simulate a produced file
        return R()

    monkeypatch.setattr(assembly.subprocess, "run", fake_run)
    result = assembly.assemble(str(audio), [str(clip)], str(out))
    assert result == str(out)
    assert calls["n"] == 2  # polished attempt failed → plain retry succeeded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -k "polish or fall_back" -v`
Expected: FAIL — `_build_cmd` has no `polish` kwarg; `assemble` doesn't retry.

- [ ] **Step 3: Write minimal implementation**

In `src/assembly.py`, change `_build_cmd`'s signature and gate the polish features on the flag:

```python
def _build_cmd(ordered, audio_path, duration, out_path, music_path=None, polish=True):
```

Inside, make the polish decisions respect the flag:

```python
    grade = _grade_filters() if polish else ""
    grade_suffix = ("," + grade) if grade else ""
    use_xfade = polish and _xfade_enabled() and n >= 2
    if use_xfade:
        xf = _xfade_seconds()
        ...xfade chain (as Task 3)...
    else:
        ...concat path (as Task 3)...
```

Then make `assemble()` fail-soft. Replace the single render block:

```python
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"assembly: ffmpeg failed ({proc.returncode}):\n{proc.stderr[-1500:]}")
```
with:
```python
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.warning("assembly: polished render failed (%d); retrying plain.\n%s",
                    proc.returncode, proc.stderr[-800:])
        ordered_plain = _ordered_clips(clip_paths, duration, overlap=0.0)
        cmd = _build_cmd(ordered_plain, audio_path, duration, out_path,
                         music_path=music, polish=False)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"assembly: ffmpeg failed ({proc.returncode}):\n{proc.stderr[-1500:]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_assembly.py -v`
Expected: PASS (all assembly tests).

- [ ] **Step 5: Commit**

```bash
git add src/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): fail-soft — fall back to plain render if polish graph errors"
```

---

## Task 5: Document knobs, update logs, and verify on a real render

Wire up docs and prove the result (rule 8 — evidence, not assertion).

**Files:**
- Modify: `.env.example`, `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Document the env knobs**

Append to `.env.example` (blank/placeholder values only — rule 5):

```
# --- Edit polish (assembly): all optional, sensible defaults, all fail-soft ---
ENABLE_XFADE=          # true (default) | false — crossfade transitions between cuts
XFADE_SECONDS=         # crossfade overlap seconds (default 0.35)
ENABLE_GRADE=          # true (default) | false — cinematic color grade
GRADE_CONTRAST=        # default 1.06
GRADE_SATURATION=      # default 1.12
ENABLE_VIGNETTE=       # true (default) | false
ENABLE_GRAIN=          # true (default) | false — subtle film grain
GRAIN_STRENGTH=        # noise alls value (default 8)
```

- [ ] **Step 2: Run the full suite (no regressions)**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS — full suite green (174+ tests; live tests skip if offline / no FFmpeg).

- [ ] **Step 3: Render a before/after verification sample**

Run this from the repo root to produce two reels from the same inputs — plain vs. polished:

```bash
.venv/Scripts/python - <<'PY'
import os
from src import voice, visuals, assembly
os.makedirs("outputs/_verify", exist_ok=True)
audio, dur = voice.synthesize(
    "India just approved its largest solar push yet. Here is why it actually matters.",
    "outputs/_verify")
clips = visuals.fetch_broll(["solar panels india", "power grid", "city skyline"],
                            target_seconds=dur, out_dir="outputs/_verify")
os.environ.update(ENABLE_XFADE="false", ENABLE_GRADE="false",
                  ENABLE_VIGNETTE="false", ENABLE_GRAIN="false")
assembly.assemble(audio, clips, "outputs/_verify/before.mp4")
for k in ("ENABLE_XFADE","ENABLE_GRADE","ENABLE_VIGNETTE","ENABLE_GRAIN"):
    os.environ.pop(k, None)
assembly.assemble(audio, clips, "outputs/_verify/after.mp4")
print("WROTE outputs/_verify/before.mp4 and after.mp4")
PY
```

Open `outputs/_verify/before.mp4` and `after.mp4` and confirm: after has smooth crossfades, a warmer/graded look, and varied motion. **This is the gate — do not proceed to merge if `after` does not look clearly better.** Delete `outputs/_verify/` afterward (rule 15: render artifacts aren't committed).

- [ ] **Step 4: Update STATUS.md and CHANGELOG.md**

In `STATUS.md`, update the Module 6 row to note the polish layer and bump the version line. In `CHANGELOG.md`, add an `Added` entry under a new version (Keep a Changelog style) describing crossfade transitions, cinematic grade, vignette/grain, Ken Burns variety, and the fail-soft fallback.

- [ ] **Step 5: Commit**

```bash
git add .env.example STATUS.md CHANGELOG.md
git commit -m "docs(polish): document edit-polish knobs; update STATUS and CHANGELOG"
```

---

## Self-review

- **Spec coverage:** transitions → Task 3 · color grade → Task 2 · vignette/grain → Task 2 · Ken Burns variety → Task 1 · fail-soft → Task 4 · config knobs → Tasks 2/3/5 · before/after verification gate → Task 5 · compliance unchanged (cosmetic, no doc change needed). All spec sections covered.
- **Placeholder scan:** none — every code step shows the actual code; commands have expected output.
- **Type consistency:** `_grade_filters()`, `_xfade_enabled()`, `_xfade_seconds()`, `_ordered_clips(..., overlap=)`, `_build_cmd(..., polish=)`, `_image_to_kenburns_clip(..., index=)` are used consistently across tasks and tests.
- **Regression guard:** Task 3 explicitly updates `test_build_cmd_structure` (which asserts `concat`) to set `ENABLE_XFADE=false`, since xfade now defaults on.
