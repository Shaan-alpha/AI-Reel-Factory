"""Module 6 — Assembly (FFmpeg).

Contract:
    what it does : composes B-roll + narration into a 1080x1920 reel (no captions yet).
    input        : audio_path, clip_paths, output path.
    output       : path to assembled .mp4 (H.264, <=60s, 9:16).
    depends on   : the FFmpeg binary (system dep; install: `winget install Gyan.FFmpeg`).

Pipeline: probe narration length → normalize each clip (scale-to-fill + center-crop to
1080x1920, ~6s slice) → concat → trim to narration length → mux narration → H.264 mp4.
Cuts land every ~6s (retention + copyright safety, docs/08 §3). The reel is a render
artifact: assembly writes it, publish uploads it, then it's deleted (rule 15).

MVP scope (rule 16: reliable + watchable beats cinematic): no Ken Burns / music bed yet —
those are easy follow-ups once the core renders consistently.

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
_SLICE = 6.0            # seconds per clip cut (within the 5-8s target)
_MAX_SLICES = 40        # safety cap on filter-graph size
_MUSIC_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".aac")


def _pick_music(audio_path: str) -> str | None:
    """Pick a royalty-free track from MUSIC_DIR (default assets/music) to bed under narration.

    Returns None if the dir is missing/empty (BGM is optional). Deterministic per reel (hashes
    the narration path) so reruns reuse the same track, but different reels vary."""
    if str(config.get("ENABLE_MUSIC", "true")).lower() != "true":
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


def _ordered_clips(clip_paths: list[str], duration: float) -> list[str]:
    """Cycle the available clips into enough ~6s slices to over-cover the narration."""
    n = min(_MAX_SLICES, math.ceil(duration / _SLICE) + 1)  # +1 slice of safety margin
    return [clip_paths[i % len(clip_paths)] for i in range(n)]


def _build_cmd(ordered: list[str], audio_path: str, duration: float, out_path: str,
               music_path: str | None = None) -> list[str]:
    """Construct the ffmpeg argv: normalize → concat → trim → mux narration (+ optional music bed)."""
    n = len(ordered)
    parts = []
    for k in range(n):
        parts.append(
            f"[{k}:v]trim=0:{_SLICE},setpts=PTS-STARTPTS,"
            f"scale={_W}:{_H}:force_original_aspect_ratio=increase,"
            f"crop={_W}:{_H},setsar=1,fps={_FPS}[v{k}]"
        )
    concat_in = "".join(f"[v{k}]" for k in range(n))
    parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vc]")
    parts.append(f"[vc]trim=0:{duration:.3f},setpts=PTS-STARTPTS[v]")

    cmd = [_ffmpeg(), "-y"]
    for clip in ordered:
        cmd += ["-i", clip]
    cmd += ["-i", audio_path]  # narration = input n

    if music_path:
        # music looped to cover narration, mixed quietly under it (faint bed, docs/08 §7)
        vol = config.get("MUSIC_VOLUME", "0.12")
        cmd += ["-stream_loop", "-1", "-i", music_path]  # music = input n+1
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
    ordered = _ordered_clips(clip_paths, duration)
    music = _pick_music(os.path.abspath(audio_path))
    cmd = _build_cmd(ordered, audio_path, duration, out_path, music_path=music)

    log.info("assembly: rendering %s (%.1fs, %d slices from %d clips, music=%s)",
             out_path, duration, len(ordered), len(clip_paths), os.path.basename(music) if music else "none")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"assembly: ffmpeg failed ({proc.returncode}):\n{proc.stderr[-1500:]}")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("assembly: ffmpeg reported success but produced no output file.")
    return out_path
