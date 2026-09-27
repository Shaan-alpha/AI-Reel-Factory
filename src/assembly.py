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
import re
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


# Colour tags go on the FRAMES: ffmpeg 8 writes the frame properties and ignores
# -color_primaries/-color_trc codec options (measured 2026-09-27: they came out 'unknown').
BT709_TAGS = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def x264_args(final: bool = False) -> list[str]:
    """libx264 settings for every video encode, so all three generations agree.

    Every frame is encoded three times (Ken Burns clip, this render, the caption burn), and at
    the default CRF 23 three generations measured PSNR-Y 43.0 dB against 46.3 after one. Lower
    CRF alone is not safe here: the temporal film grain is incompressible noise, and CRF 18 on
    it measured 44 Mbps (a 183 MB file for 33 s, against 3.8 Mbps before). So the CRF is
    CAPPED: the final encode at YouTube's 1080p30 upload guideline of 8 Mbps (measured about
    5.3 Mbps on grainy footage), the intermediates at 20 Mbps. The final encode also uses
    YouTube's recommended closed GOP of half the frame rate."""
    if final:
        crf, cap = config.get("X264_CRF_FINAL", "20"), config.get("X264_MAXRATE_FINAL", "8M")
    else:
        crf, cap = config.get("X264_CRF", "17"), config.get("X264_MAXRATE", "20M")
    bufsize = f"{2 * int(''.join(c for c in cap if c.isdigit()) or 8)}M"
    args = ["-c:v", "libx264", "-preset", config.get("X264_PRESET", "veryfast"),
            "-crf", crf, "-maxrate", cap, "-bufsize", bufsize, "-pix_fmt", "yuv420p"]
    if final:
        args += ["-profile:v", "high", "-g", str(_FPS // 2), "-bf", "2"]
    return args


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
    # Off by default since 2026-09-27: temporal grain is incompressible noise. It pushed an
    # uncapped CRF 18 encode to 44 Mbps, now eats the 8 Mbps cap, and YouTube's own re-encode
    # smears it anyway. ENABLE_GRAIN=true brings it back.
    if config.get_bool("ENABLE_GRAIN", False):
        strength = config.get("GRAIN_STRENGTH", "8")
        parts.append(f"noise=alls={strength}:allf=t+u")  # subtle temporal film grain
    return ",".join(parts)


def _brand_logo() -> str | None:
    """Path to the brand-bug logo if enabled and the file exists, else None (fail-soft)."""
    if not config.get_bool("ENABLE_BRAND_BUG", True):
        return None
    path = config.get("BRAND_LOGO", "assets/brand/logo.png")
    return path if path and os.path.isfile(path) else None


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


def _slice_count(duration: float, overlap: float) -> int:
    """How many slices cover `duration` at the configured cut rhythm. The +2 over-covers."""
    slice_s = _clip_seconds()
    if duration <= slice_s:
        return 2
    step = max(0.1, slice_s - overlap)  # effective coverage per slice after the first
    return min(_MAX_SLICES, math.ceil((duration - slice_s) / step) + 2)


def slice_count(duration: float) -> int:
    """Cuts this module will make for `duration` seconds of narration, transitions included.

    PUBLIC because `visuals` must generate at least this many distinct shots. It used to size
    its B-roll off its own hardcoded 6.0s guess while this module cut at `CLIP_SECONDS` (~3.5s),
    so a 30s reel asked for 10 slices, got 6 images, and replayed 4 of them. `_ordered_clips`
    normally softens a repeat by advancing the start offset — but a Ken Burns clip is a pan over
    ONE still, so every offset of it is the same picture and the repeat is plainly visible.
    Two modules deriving the same number from different constants is the drift this closes:
    ask the module that does the cutting (rule 7).
    """
    return _slice_count(duration, _xfade_seconds() if _xfade_enabled() else 0.0)


def _ordered_clips(clip_paths: list[str], duration: float,
                   overlap: float = 0.0) -> list[tuple[str, float]]:
    """Cycle clips into enough slices to over-cover the narration. Returns [(path, start_offset)].

    When a clip repeats (few clips, many fast cuts), its start advances by one slice each time
    and wraps within the clip's length — so a repeat shows a DIFFERENT segment, not the same
    opening frames twice. Clips that can't be probed get start 0.0 (safe fallback).

    `overlap` (xfade seconds) shrinks each slice's effective coverage to slice_s - overlap, so
    crossfaded reels still over-cover the narration. overlap=0 reproduces the hard-cut count."""
    slice_s = _clip_seconds()
    n = _slice_count(duration, overlap)
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


def _apply_seamless_loop(ordered: list[tuple[str, float]], duration: float,
                         overlap: float) -> list[tuple[str, float]]:
    """Make the last VISIBLE slice reuse the opening clip so the ending rhymes with the start
    (loop-friendly replays). No-op when disabled or there's only one slice.

    It must be the last visible slice, not simply the last one. `slice_count` deliberately
    over-covers the narration, and the render is then trimmed to the narration length — so the
    final entry starts at or beyond the trim point and never reaches the screen. Measured across
    23/25/28/30s narrations at CLIP_SECONDS=3.5, the reprise was on screen for 0.00s every time:
    the feature was inert from the day it shipped.
    """
    if not (config.get_bool("ENABLE_SEAMLESS_LOOP", True) and len(ordered) >= 2):
        return ordered
    step = max(0.01, _clip_seconds() - overlap)
    # Last index whose slice actually STARTS before the trim point (start = i * step, strictly
    # less than duration). No clamping up to 1: _slice_count returns 2 even for a duration of
    # one slice or less, so index 1 exists but begins at or after the trim — forcing the reprise
    # onto it would put it back on a slice nobody sees, which is the defect this function fixes.
    last_visible = min(len(ordered) - 1, math.ceil(duration / step) - 1)
    if last_visible < 1:
        return ordered  # only the opening slice survives the trim; nothing to rhyme with
    return (ordered[:last_visible] + [(ordered[0][0], 0.0)]
            + ordered[last_visible + 1:])


def _sfx_enabled() -> bool:
    return config.get_bool("ENABLE_SFX", True)


def _sfx_volume() -> float:
    """SFX level, clamped to [0, 1]. Deliberately LOW: `amix ... normalize=0` sums its inputs
    without headroom, so a loud marker on top of a near-full-scale narration peak clips."""
    try:
        v = float(config.get("SFX_VOLUME", "0.18"))
    except (TypeError, ValueError):
        v = 0.18
    return max(0.0, min(v, 1.0))


def _sfx_every_n_cuts() -> int:
    """Mark every Nth cut, not every cut. A transition sting on all ~9 cuts of a 28s reel reads
    as cheap; sparse markers punctuate instead of nagging."""
    try:
        n = int(config.get("SFX_EVERY_N_CUTS", "2"))
    except (TypeError, ValueError):
        n = 2
    return max(1, n)


# Keep the opening clean: the first frames carry the hook, the single highest-leverage
# retention moment — a whoosh over it competes with the line that has to land.
_SFX_LEAD_IN = 1.5


def _build_sfx_events(ordered: list[tuple[str, float]], duration: float) -> list[dict]:
    """SFX events on a sparse subset of the clip cuts. Times mirror `_build_cmd`'s xfade offsets
    (i * (slice - xfade)) so a sting lands ON the cut, not beside it."""
    vol = _sfx_volume()
    if vol <= 0.0:
        return []
    slice_s = _clip_seconds()
    xf = _xfade_seconds() if _xfade_enabled() else 0.0
    step = max(0.1, slice_s - xf)
    every = _sfx_every_n_cuts()

    events: list[dict] = []
    for i in range(1, len(ordered)):
        if i % every:
            continue
        t = round(i * step, 2)
        if t < _SFX_LEAD_IN or t >= duration - 0.5:
            continue
        # Clicks only (operator, 2026-09-27): the whoosh that alternated with them is gone. It
        # landed on words, and after the 24 kHz narration path it was mostly hiss. The click
        # keeps its old slots, so the stings are now half as frequent.
        if not (i // every) % 2:
            continue
        events.append({"time": t, "name": "click", "volume": vol})
    return events


# --- Audio levels (2026-09-27 audit) -------------------------------------------------------
# Nothing used to set the loudness. Published Shorts measured -16.8 to -22.7 LUFS integrated,
# 6-7 dB under YouTube's -14 LUFS reference, and YouTube turns loud uploads down but never turns
# quiet ones up, so every reel played quieter than the Shorts around it. The narration engines
# also land 6 LU apart (Chirp -15, Gemini 2.5 about -21), so the mix changed with the engine.
#
# The fix levels each reel from its own measurements, three quick ebur128 reads of small files,
# no extra render: the voice is brought to the reference level the ducking was tuned at, lightly
# compressed, then raised to TARGET_LUFS; the bed is set MUSIC_LU_BELOW_VOICE under it; a
# 48 kHz limiter holds true peak near -1.5 dBTP after AAC. Validated on a production-identical
# render (Gemini and edge narration x two beds): -14.9 LUFS, TP -1.4, LRA 2.4-2.5 in 4 of 4.
# Every measurement is fail-soft: one that fails leaves that stage at today's fixed levels.
_REF_LUFS = -20.0
# Light broadcast compression on the voice, at the reference level: -21 dBFS threshold, 3:1.
_VOICE_COMP = "acompressor=threshold=0.089:ratio=3:knee=2.8:attack=15:release=150"
# De-pumped ducking. The old sidechaincompress (threshold 0.03, ratio 8, attack 20, release 300)
# swung the bed 9-11 dB inside every second of speech and brought it back up in each pause.
# Holding the key (the voice plus copies 120 and 240 ms late) with a gentler, slower compressor
# measured a 3.5 dB swing and 0.8 dB per-50 ms steps.
_HOLD_KEY = ("[vkey]asplit=3[k0][k1][k2];[k1]adelay=120:all=1[k1d];[k2]adelay=240:all=1[k2d];"
             "[k0][k1d][k2d]amix=inputs=3:normalize=0:duration=first[key]")
_DUCK = "sidechaincompress=threshold=0.02:ratio=2.5:knee=8:attack=80:release=1200"
# -3 dBFS sample ceiling at 48 kHz: the margin AAC's inter-sample overs need to stay under -1
# dBTP. At -2.5 a bed with a clipped master (Duty Calls, +1.0 dBTP) still measured -0.9 dBTP.
_FINAL_LIMIT = "aresample=48000,alimiter=limit=0.7079:level=0:attack=5:release=50:latency=1"
# Without ducking (the plain retry) the bed sits this much lower, so speech still clears it.
_PLAIN_BED_DROP_DB = -10.0
_LOUDNESS_RE = re.compile(r"I:\s+(-?\d+(?:\.\d+)?) LUFS")


def _float_setting(key: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(config.get(key, str(default)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(v, hi))


def _music_volume() -> float:
    """MUSIC_VOLUME as a number. It used to go into the filter graph as raw text, so a malformed
    repo variable failed the polished render AND the plain retry, after TTS and visuals had been
    paid for."""
    return _float_setting("MUSIC_VOLUME", 0.10, 0.0, 1.0)


def _loudness(path: str, af: str = "", start: float = 0.0,
              seconds: float | None = None) -> float | None:
    """Integrated loudness (LUFS) of `path` after filter `af`, or None if it cannot be read."""
    cmd = [_ffmpeg(), "-hide_banner", "-nostats"]
    if start > 0:
        cmd += ["-ss", f"{start:.2f}"]
    if seconds:
        cmd += ["-t", f"{seconds:.2f}"]
    cmd += ["-i", path, "-vn", "-af", (af + "," if af else "") + "ebur128=framelog=quiet",
            "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:  # noqa: BLE001 — a measurement is optional (rule 14)
        return None
    if proc.returncode != 0:
        return None
    err = proc.stderr or ""
    m = _LOUDNESS_RE.search(err[err.rfind("Summary:"):] if "Summary:" in err else err)
    if not m:
        return None
    value = float(m.group(1))
    return value if value > -70.0 else None  # -70 is ebur128's floor: silence, not a level


def _music_start(music_path: str, audio_path: str, duration: float) -> float:
    """Where in the bed this reel starts. Every reel used to open on the same bar of its track."""
    if not config.get_bool("ENABLE_MUSIC_OFFSET", True):
        return 0.0
    track = _safe_probe(music_path)
    room = int(track - duration - 5)
    if room < 5:
        return 0.0
    return float(int(hashlib.sha1(("start:" + audio_path).encode("utf-8")).hexdigest(), 16) % room)


def _measure_levels(audio_path: str, music_path: str | None, duration: float) -> dict:
    """Gains for this reel's mix, from its own measurements. {} = today's fixed levels."""
    if not config.get_bool("ENABLE_LOUDNORM", True):
        return {}
    raw = _loudness(audio_path)
    if raw is None:
        log.warning("assembly: could not measure the narration; mixing at fixed levels")
        return {}
    target = _float_setting("TARGET_LUFS", -14.0, -24.0, -9.0)
    pre = _REF_LUFS - raw
    compress = config.get_bool("ENABLE_VOICE_COMPRESS", True)
    at_ref = _REF_LUFS
    if compress:
        at_ref = _loudness(audio_path, af=f"volume={pre:.2f}dB,{_VOICE_COMP}")
        if at_ref is None:
            compress, at_ref = False, _REF_LUFS
    levels = {"voice_pre": pre, "voice_post": target - at_ref, "compress": compress,
              # SFX were sized against the raw narration; they follow its total gain.
              "sfx": target - raw}
    if music_path:
        start = _music_start(music_path, audio_path, duration)
        levels["music_start"] = start
        bed = _loudness(music_path, start=start, seconds=duration)
        if bed is not None:
            below = _float_setting("MUSIC_LU_BELOW_VOICE", 11.0, 3.0, 30.0)
            levels["bed"] = target - below - bed
    return levels


def _audio_parts(n: int, sfx_idx: int | None, music_idx: int | None, polish: bool,
                 levels: dict) -> list[str]:
    """Filter-graph lines for the audio: narration (input n), optional SFX and bed -> [aout].

    `duration=first` on the amix keys the mix to the narration, so the reel ends with the voice;
    `normalize=0` keeps the voice at unity instead of halving it."""
    parts: list[str] = []
    duck = polish and music_idx is not None and _ducking_enabled()
    # The ducking key is the voice at the REFERENCE level, so the duck behaves the same whichever
    # engine spoke; the voice itself then goes on to its target level.
    head = f"[{n}:a]volume={levels.get('voice_pre', 0.0):.2f}dB"
    if duck:
        parts.append(f"{head},asplit=2[vref][vkey]")
        parts.append(_HOLD_KEY)
    else:
        parts.append(f"{head}[vref]")
    comp = f"{_VOICE_COMP}," if levels.get("compress") else ""
    parts.append(f"[vref]{comp}volume={levels.get('voice_post', 0.0):.2f}dB[voice]")
    inputs = ["[voice]"]
    if sfx_idx is not None:
        parts.append(f"[{sfx_idx}:a]volume={levels.get('sfx', 0.0):.2f}dB[sfx]")
        inputs.append("[sfx]")
    if music_idx is not None:
        bed = levels.get("bed")
        gain = f"volume={bed:.2f}dB" if bed is not None else f"volume={_music_volume():.3f}"
        if duck:
            parts.append(f"[{music_idx}:a]{gain},afade=t=in:d=0.3[bg]")
            parts.append(f"[bg][key]{_DUCK}[bed]")
        else:
            drop = f",volume={_PLAIN_BED_DROP_DB:.1f}dB" if bed is not None else ""
            parts.append(f"[{music_idx}:a]{gain}{drop}[bed]")
        inputs.append("[bed]")
    if len(inputs) > 1:
        parts.append(f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=first"
                     f":dropout_transition=3:normalize=0[amixed]")
        last = "[amixed]"
    else:
        last = "[voice]"
    parts.append(f"{last}{_FINAL_LIMIT}[aout]")
    return parts


def _build_cmd(ordered: list[tuple[str, float]], audio_path: str, duration: float, out_path: str,
               music_path: str | None = None, sfx_path: str | None = None,
               polish: bool = True, levels: dict | None = None) -> list[str]:
    """Construct the ffmpeg argv: normalize → concat/xfade → grade → trim → mux narration + SFX + music.

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
    # BT709_TAGS rides on the trim that makes [v]; the logo overlay inherits it from [v].
    grade_suffix = (("," + grade) if grade else "") + "," + BT709_TAGS
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

    # Audio inputs, in a FIXED order after the clips: narration (n) → SFX → music → logo.
    # Every render now ends in the same limiter, narration-only included: the voice is gained
    # to the target, so there is always something for it to hold (see _audio_parts).
    has_sfx = bool(sfx_path and os.path.isfile(sfx_path))
    curr_idx = n
    sfx_idx = music_idx = None
    if has_sfx:
        cmd += ["-i", sfx_path]
        curr_idx += 1
        sfx_idx = curr_idx
    if music_path:
        start = float((levels or {}).get("music_start", 0.0))
        if start > 0:
            cmd += ["-ss", f"{start:.2f}"]
        cmd += ["-stream_loop", "-1", "-i", music_path]
        curr_idx += 1
        music_idx = curr_idx
    parts += _audio_parts(n, sfx_idx, music_idx, polish, levels or {})
    audio_map = "[aout]"

    # Brand-bug overlay: composite the logo (added as the LAST input so it never shifts the
    # voice/music indices) small + semi-transparent in the top-right. Fail-soft + polish-gated.
    video_label = "[v]"
    logo_path = _brand_logo() if polish else None
    if logo_path:
        logo_idx = curr_idx + 1
        cmd += ["-loop", "1", "-i", logo_path]
        h = config.get("BRAND_LOGO_HEIGHT", "150")
        op = config.get("BRAND_LOGO_OPACITY", "0.55")
        m = config.get("BRAND_LOGO_MARGIN", "44")
        # Below the Shorts player's top-right icons (search, camera, menu), which covered the
        # logo at y=44. The side margin stays.
        top = config.get("BRAND_LOGO_TOP", "240")
        parts.append(f"[{logo_idx}:v]scale=-1:{h},format=rgba,colorchannelmixer=aa={op}[lg]")
        parts.append(f"[v][lg]overlay=W-w-{m}:{top}[vout]")
        video_label = "[vout]"

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", video_label, "-map", audio_map,
        "-t", f"{duration:.3f}",
        *x264_args(),
        # 48 kHz: the mix used to inherit the TTS's 24 kHz, which cut the bed off at 12 kHz.
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1",
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
    ordered = _apply_seamless_loop(
        _ordered_clips(clip_paths, duration, overlap=overlap), duration, overlap)
    music = _pick_music(os.path.abspath(audio_path))
    sfx_path = None
    if _sfx_enabled():
        try:
            from src import audio_sfx
            events = _build_sfx_events(ordered, duration)
            if events:
                sfx_path = os.path.join(os.path.dirname(os.path.abspath(out_path)), "sfx_track.wav")
                audio_sfx.mix_sfx_events(events, duration, sfx_path)
        except Exception as e:  # noqa: BLE001 — SFX is best-effort (rule 11/14)
            log.warning("assembly: SFX track generation failed (%s); proceeding without SFX", e)
            sfx_path = None

    levels = _measure_levels(audio_path, music, duration)
    cmd = _build_cmd(ordered, audio_path, duration, out_path, music_path=music, sfx_path=sfx_path,
                     levels=levels)

    log.info("assembly: rendering %s (%.1fs, %d slices from %d clips, music=%s, sfx=%s, "
             "voice gain %+.1f dB, bed %s)",
             out_path, duration, len(ordered), len(clip_paths),
             os.path.basename(music) if music else "none", "yes" if sfx_path else "no",
             levels.get("voice_pre", 0.0) + levels.get("voice_post", 0.0),
             f"{levels['bed']:+.1f} dB" if "bed" in levels else "fixed")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fail-soft (rules 11, 14): a polished filtergraph error must never lose the reel.
        log.warning("assembly: polished render failed (%d); retrying plain.\n%s",
                    proc.returncode, proc.stderr[-800:])
        ordered_plain = _ordered_clips(clip_paths, duration, overlap=0.0)
        cmd = _build_cmd(ordered_plain, audio_path, duration, out_path,
                         music_path=music, polish=False, levels=levels)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"assembly: ffmpeg failed ({proc.returncode}):\n{proc.stderr[-1500:]}")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("assembly: ffmpeg reported success but produced no output file.")
    return out_path
