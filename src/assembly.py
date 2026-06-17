"""Module 6 — Assembly (FFmpeg).

Contract:
    what it does : composes B-roll + narration into a 1080x1920 reel (no captions yet).
    input        : audio_path, clip_paths, output path.
    output       : path to assembled .mp4 (H.264, <=60s, 9:16).
    depends on   : the FFmpeg binary (system dep; install: `winget install Gyan.FFmpeg`).

Pipeline: probe narration length → normalize each clip (scale-to-fill + center-crop to
1080x1920, ~CLIP_SECONDS slice) → concat → trim to narration length → mux narration → H.264 mp4.
Cuts land every ~CLIP_SECONDS (default 3.5s — fast pattern-interrupts drive Shorts retention,
and shorter single-clip use is *more* copyright-safe, docs/08 §3). When a clip repeats, its
start offset advances so the repeat shows a different segment (variety on fast cuts). The reel
is a render artifact: assembly writes it, publish uploads it, then it's deleted (rule 15).

Polish layer (all toggle-gated, all fail-soft): crossfade transitions (xfade), a cinematic
color grade + vignette + film grain applied once over the final stream (unifies independently-
generated AI shots into one house look), and a quiet music bed. If the polished filtergraph
errors, assemble() retries the plain graph so a reel is never lost (rules 11, 14). Ken Burns
motion lives upstream in visuals.py (image sources).

Binary resolution (rule 14: fail loud on misconfig): FFMPEG_BINARY env → PATH → a Windows
winget fallback. On GitHub Actions (UTC) FFmpeg is installed onto PATH in the workflow.
"""
from __future__ import annotations

import glob
import hashlib
import logging
import math
import os
import shutil
import subprocess

from src import config

log = logging.getLogger(__name__)

_W, _H = 1080, 1920     # 9:16 Short
_FPS = 30
_DEFAULT_CLIP_SECONDS = 3.5   # default cut length — fast pattern-interrupts for Shorts retention
_MIN_CLIP_SECONDS = 1.5       # below this it gets seizure-fast / under-covers long reels
_MAX_CLIP_SECONDS = 8.0       # docs/08 §3 copyright ceiling for one continuous clip
_MAX_SLICES = 60        # filter-graph safety cap (covers a 60s reel down to ~1.5s cuts)
_MUSIC_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".aac")


def _clip_seconds() -> float:
    """Seconds per clip cut, env-tunable via CLIP_SECONDS, clamped to a sane range."""
    try:
        v = float(config.get("CLIP_SECONDS", str(_DEFAULT_CLIP_SECONDS)))
    except (TypeError, ValueError):
        v = _DEFAULT_CLIP_SECONDS
    return max(_MIN_CLIP_SECONDS, min(_MAX_CLIP_SECONDS, v))


def _xfade_enabled() -> bool:
    return config.get_bool("ENABLE_XFADE", True)


def _ducking_enabled() -> bool:
    return config.get_bool("ENABLE_DUCKING", True)


def _xfade_seconds() -> float:
    """Crossfade overlap, clamped below half a slice so xfade offsets stay positive."""
    try:
        v = float(config.get("XFADE_SECONDS", "0.35"))
    except (TypeError, ValueError):
        v = 0.35
    return max(0.1, min(v, _clip_seconds() * 0.5))


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


def _pick_music(audio_path: str) -> str | None:
    """Pick a royalty-free track from MUSIC_DIR (default assets/music) to bed under narration.

    Returns None if the dir is missing/empty (BGM is optional). Deterministic per reel (hashes
    the narration path) so reruns reuse the same track, but different reels vary."""
    if not config.get_bool("ENABLE_MUSIC", True):
        return None
    music_dir = config.get("MUSIC_DIR", "assets/music")
    if not os.path.isdir(music_dir):
        return None
    tracks = sorted(f for f in os.listdir(music_dir) if f.lower().endswith(_MUSIC_EXTS))
    if not tracks:
        return None
    idx = int(hashlib.sha1(audio_path.encode("utf-8")).hexdigest(), 16) % len(tracks)
    return os.path.join(music_dir, tracks[idx])


def _resolve_binary(name: str, env_key: str) -> str:
    """Find an FFmpeg tool: env override → PATH → Windows winget package. Fail loud if absent."""
    cand = config.get(env_key) or shutil.which(name) or shutil.which(name + ".exe")
    if cand:
        return cand
    pattern = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
        "Gyan.FFmpeg*", "**", name + ".exe",
    )
    hits = glob.glob(pattern, recursive=True)
    if hits:
        return hits[0]
    raise RuntimeError(
        f"{name} not found. Install FFmpeg (`winget install Gyan.FFmpeg`) or set {env_key}."
    )


def _ffmpeg() -> str:
    return _resolve_binary("ffmpeg", "FFMPEG_BINARY")


def _ffprobe() -> str:
    return _resolve_binary("ffprobe", "FFPROBE_BINARY")


def probe_duration(path: str) -> float:
    """Return media duration in seconds via ffprobe."""
    out = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _safe_probe(path: str) -> float:
    """Clip duration in seconds, or 0.0 if it can't be probed (→ no stagger for that clip)."""
    try:
        return probe_duration(path)
    except Exception:  # noqa: BLE001 — a missing/odd clip just gets a zero start offset
        return 0.0


def _ordered_clips(clip_paths: list[str], duration: float,
                   overlap: float = 0.0) -> list[tuple[str, float]]:
    """Cycle clips into enough slices to over-cover the narration. Returns [(path, start_offset)].

    When a clip repeats (few clips, many fast cuts), its start advances by one slice each time
    and wraps within the clip's length — so a repeat shows a DIFFERENT segment, not the same
    opening frames twice. Clips that can't be probed get start 0.0 (safe fallback).

    `overlap` (xfade seconds) shrinks each slice's effective coverage to slice_s - overlap, so
    crossfaded reels still over-cover the narration. overlap=0 reproduces the hard-cut count."""
    slice_s = _clip_seconds()
    step = max(0.1, slice_s - overlap)  # effective coverage per slice after the first
    if duration > slice_s:
        n = min(_MAX_SLICES, math.ceil((duration - slice_s) / step) + 2)
    else:
        n = 2
    durs = [_safe_probe(c) for c in clip_paths]
    used: dict[int, int] = {}
    ordered: list[tuple[str, float]] = []
    for i in range(n):
        idx = i % len(clip_paths)
        repeat = used.get(idx, 0)
        used[idx] = repeat + 1
        span = durs[idx] - slice_s
        start = round((repeat * slice_s) % span, 3) if span > 0.05 else 0.0
        ordered.append((clip_paths[idx], start))
    return ordered


def _build_cmd(ordered: list[tuple[str, float]], audio_path: str, duration: float, out_path: str,
               music_path: str | None = None, polish: bool = True) -> list[str]:
    """Construct the ffmpeg argv: normalize → concat/xfade → grade → trim → mux narration.

    `ordered` is [(clip_path, start_offset)] from _ordered_clips; each slice is trimmed at its
    own start so repeated clips show different segments. `polish=False` forces the plain graph
    (no xfade, no grade) — used by the fail-soft retry in assemble() (rules 11, 14)."""
    slice_s = _clip_seconds()
    n = len(ordered)
    parts = []
    for k, (_clip, start) in enumerate(ordered):
        parts.append(
            f"[{k}:v]trim={start:.3f}:{start + slice_s:.3f},setpts=PTS-STARTPTS,"
            f"scale={_W}:{_H}:force_original_aspect_ratio=increase,"
            f"crop={_W}:{_H},setsar=1,fps={_FPS}[v{k}]"
        )
    grade = _grade_filters() if polish else ""
    grade_suffix = ("," + grade) if grade else ""
    if polish and _xfade_enabled() and n >= 2:
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

    cmd = [_ffmpeg(), "-y"]
    for clip, _start in ordered:
        cmd += ["-i", clip]
    cmd += ["-i", audio_path]  # narration = input n

    if music_path:
        # music looped under the narration. With polish on, sidechain-DUCK it so it dips while the
        # voice speaks and swells between sentences (clearer speech = retention); the fail-soft retry
        # (polish=False) uses today's flat mix. MUSIC_VOLUME sets the base bed level.
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

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[v]", "-map", audio_map,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-r", str(_FPS), "-movflags", "+faststart",
        out_path,
    ]
    return cmd


def assemble(audio_path: str, clip_paths: list[str], out_path: str) -> str:
    """Build the 1080x1920 reel and return its path. Subtitles are burned in next (Module 7)."""
    if not os.path.exists(audio_path):
        raise ValueError(f"assembly: narration not found: {audio_path}")
    if not clip_paths:
        raise ValueError("assembly: no clip_paths provided.")
    missing = [c for c in clip_paths if not os.path.exists(c)]
    if missing:
        raise ValueError(f"assembly: clip(s) missing: {missing}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    duration = probe_duration(audio_path)
    overlap = _xfade_seconds() if _xfade_enabled() else 0.0
    ordered = _ordered_clips(clip_paths, duration, overlap=overlap)
    music = _pick_music(os.path.abspath(audio_path))
    cmd = _build_cmd(ordered, audio_path, duration, out_path, music_path=music)

    log.info("assembly: rendering %s (%.1fs, %d slices from %d clips, music=%s)",
             out_path, duration, len(ordered), len(clip_paths), os.path.basename(music) if music else "none")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fail-soft (rules 11, 14): a polished filtergraph error must never lose the reel.
        log.warning("assembly: polished render failed (%d); retrying plain.\n%s",
                    proc.returncode, proc.stderr[-800:])
        ordered_plain = _ordered_clips(clip_paths, duration, overlap=0.0)
        cmd = _build_cmd(ordered_plain, audio_path, duration, out_path,
                         music_path=music, polish=False)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"assembly: ffmpeg failed ({proc.returncode}):\n{proc.stderr[-1500:]}")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("assembly: ffmpeg reported success but produced no output file.")
    return out_path
