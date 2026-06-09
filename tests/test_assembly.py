"""Tests for the assembly module (Module 6).

Unit tests cover argv construction and clip-cycling with no FFmpeg needed. A final live test
renders a real reel end-to-end (edge-tts narration + a Pexels clip + FFmpeg) and skips if any
piece is unavailable (offline / no FFmpeg).
"""
from __future__ import annotations

import os
import subprocess

import pytest

from src import assembly


# --- argv / planning (no ffmpeg) -------------------------------------------------------

def test_ordered_clips_cycles_to_cover_duration():
    clips = ["a.mp4", "b.mp4"]
    # ceil(18/6)+1 = 4 slices, cycled across the 2 clips
    assert assembly._ordered_clips(clips, 18.0) == ["a.mp4", "b.mp4", "a.mp4", "b.mp4"]


def test_ordered_clips_min_one_slice():
    assert assembly._ordered_clips(["a.mp4"], 1.0) == ["a.mp4", "a.mp4"]  # ceil(1/6)+1 = 2


def test_build_cmd_structure(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    cmd = assembly._build_cmd(["c0.mp4", "c1.mp4"], "narr.mp3", 9.0, "out.mp4")
    # two video inputs + one audio input
    assert cmd.count("-i") == 3
    assert "2:a" in cmd  # narration mapped directly when no music
    assert cmd[cmd.index("narr.mp3") - 1] == "-i"
    # audio is the last input → mapped as stream index 2
    assert "-map" in cmd and "2:a" in cmd
    assert "[v]" in cmd
    # trimmed to the narration duration and H.264 / yuv420p for compatibility
    assert "-t" in cmd and "9.000" in cmd
    assert "libx264" in cmd and "yuv420p" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=0" in fc
    assert f"scale={assembly._W}:{assembly._H}" in fc


def test_build_cmd_mixes_music_when_present(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    cmd = assembly._build_cmd(["c0.mp4"], "narr.mp3", 9.0, "out.mp4", music_path="bed.mp3")
    assert "-stream_loop" in cmd and "bed.mp3" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2:duration=first" in fc
    assert "[aout]" in cmd  # mixed audio is mapped


def test_pick_music_none_when_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))  # empty dir
    assert assembly._pick_music("narr.mp3") is None


def test_pick_music_deterministic(monkeypatch, tmp_path):
    for name in ("a.mp3", "b.mp3", "c.mp3"):
        (tmp_path / name).write_bytes(b"x")
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    p1 = assembly._pick_music("/some/narration.mp3")
    p2 = assembly._pick_music("/some/narration.mp3")
    assert p1 == p2 and os.path.basename(p1) in {"a.mp3", "b.mp3", "c.mp3"}


def test_pick_music_disabled(monkeypatch, tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_MUSIC", "false")
    assert assembly._pick_music("narr.mp3") is None


# --- input validation (no ffmpeg) ------------------------------------------------------

def test_missing_audio_raises(tmp_path):
    with pytest.raises(ValueError, match="narration not found"):
        assembly.assemble(str(tmp_path / "nope.mp3"), ["x.mp4"], str(tmp_path / "o.mp4"))


def test_no_clips_raises(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="no clip_paths"):
        assembly.assemble(str(audio), [], str(tmp_path / "o.mp4"))


def test_missing_clip_raises(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="clip.* missing"):
        assembly.assemble(str(audio), [str(tmp_path / "ghost.mp4")], str(tmp_path / "o.mp4"))


# --- live end-to-end render ------------------------------------------------------------

def test_live_full_reel(tmp_path):
    """Real edge-tts → Pexels → FFmpeg render. Skips if any dependency is unavailable."""
    from src import visuals, voice

    try:
        ffprobe = assembly._ffprobe()  # forces a clear skip if FFmpeg isn't installed
        audio, dur = voice.synthesize(
            "Reusable rockets could cut India's launch costs. Here is why it matters.",
            str(tmp_path),
        )
        clips = visuals.fetch_broll(["rocket launch", "night sky"], target_seconds=dur,
                                    out_dir=str(tmp_path))
        out = assembly.assemble(audio, clips, str(tmp_path / "reel.mp4"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"live render unavailable (offline / no FFmpeg): {e}")

    assert os.path.exists(out) and os.path.getsize(out) > 50_000
    # verify 1080x1920 video stream + an audio stream, length ~ narration
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration", "-of", "default=nw=1", out],
        capture_output=True, text=True,
    ).stdout
    assert "width=1080" in probe and "height=1920" in probe
    assert "codec_type=audio" in probe
    out_dur = assembly.probe_duration(out)
    assert abs(out_dur - dur) < 1.5
