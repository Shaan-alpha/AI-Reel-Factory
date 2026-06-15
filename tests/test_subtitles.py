"""Tests for the subtitles module (Module 7).

Unit tests cover timestamp formatting, gap-filling, ASS generation, and the burn_captions
orchestration with transcription + ffmpeg mocked (no model download, no ffmpeg). A final live
test runs real faster-whisper (tiny) + a real burn and skips if anything is unavailable.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from src import subtitles


# --- timestamp + events (pure) ---------------------------------------------------------

def test_format_ts():
    assert subtitles._format_ts(0) == "0:00:00.00"
    assert subtitles._format_ts(65.5) == "0:01:05.50"
    assert subtitles._format_ts(3661.23) == "1:01:01.23"


def test_build_events_holds_until_next_word(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")  # per-word for this timing check
    words = [(0.0, 0.3, "a"), (0.5, 0.9, "b"), (1.0, 1.4, "c")]
    events = subtitles._build_events(words)
    assert events[0] == (0.0, 0.5, "a")   # held until 'b' starts
    assert events[1] == (0.5, 1.0, "b")   # held until 'c' starts
    assert events[2] == (1.0, 1.4, "c")   # last keeps its own end


def test_build_events_min_duration_when_overlap(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    words = [(1.0, 1.0, "x")]
    (start, end, _), = subtitles._build_events(words)
    assert end > start  # never zero-length


def test_build_events_groups_and_cleans(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "2")
    # whisper split "mythos-level" → "mythos", "-level"; grouped + cleaned
    words = [(0.0, 0.3, "mythos"), (0.3, 0.6, "-level"), (0.7, 1.0, "AI")]
    events = subtitles._build_events(words)
    assert events[0][2] == "mythos level"   # 2-word group, '-' cleaned off
    assert events[1][2] == "AI"


def test_build_ass_has_style(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    ass = subtitles._build_ass([(0.0, 0.3, "Hello"), (0.4, 0.8, "world")])
    assert "[V4+ Styles]" in ass and "Style: Karaoke" in ass
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert ass.count("Dialogue:") == 2
    assert "Hello" in ass and "world" in ass


def test_karaoke_line_has_kf_tags_and_words():
    words = [(0.0, 0.40, "Oil"), (0.40, 0.90, "export"), (0.90, 1.50, "wars")]
    line = subtitles._karaoke_line(words)
    assert line.count("\\kf") == 3            # one fill tag per word
    assert "Oil" in line and "export" in line and "wars" in line
    assert "\\kf40" in line                   # first word fill ~ next_start - start = 40cs


def test_build_ass_uses_configured_font(monkeypatch):
    monkeypatch.setenv("CAPTION_FONT", "Montserrat")
    words = [(0.0, 0.4, "Hi"), (0.4, 0.8, "there")]
    ass = subtitles._build_ass(words)
    assert "Montserrat" in ass
    assert "Karaoke" in ass            # the karaoke style exists
    assert "{\\kf" in ass              # events use karaoke fill


def test_ass_escape_strips_braces():
    assert subtitles._ass_escape("  {evil}\\path\n ") == "evilpath"


# --- frame-1 hook banner ---------------------------------------------------------------

def test_hook_banner_uppercases_strips_emoji_and_wraps():
    # emoji + variation selector stripped; UPPERCASE; wrapped to <=16 chars/line with \N
    out = subtitles._hook_banner_text("Oil Export Wars \U0001f6e2️")
    assert "\U0001f6e2" not in out and "OIL EXPORT" in out
    for line in out.split("\\N"):
        assert len(line) <= 16
    assert out == out.upper()


def test_hook_banner_empty_when_nothing_renderable():
    assert subtitles._hook_banner_text("\U0001f600\U0001f525") == ""  # all emoji → nothing
    assert subtitles._hook_banner_text("") == ""


def test_build_ass_includes_hook_banner_when_given(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    monkeypatch.delenv("ENABLE_HOOK_CAPTION", raising=False)  # default on
    ass = subtitles._build_ass([(0.0, 0.3, "Hello")], hook_text="Oil Export Wars")
    assert "Style: Hook" in ass
    assert ",Hook,," in ass                       # the hook Dialogue line
    assert "OIL EXPORT" in ass                     # banner text present, uppercased
    assert ass.count("Dialogue:") == 2             # 1 hook + 1 word


def test_build_ass_omits_hook_when_disabled(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    monkeypatch.setenv("ENABLE_HOOK_CAPTION", "0")
    ass = subtitles._build_ass([(0.0, 0.3, "Hello")], hook_text="Oil Export Wars")
    assert ",Hook,," not in ass and ass.count("Dialogue:") == 1


# --- burn_captions orchestration (mocked transcription + ffmpeg) -----------------------

def test_burn_captions_writes_ass_and_calls_burn(monkeypatch, tmp_path):
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00" * 100)
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00" * 100)
    out = tmp_path / "out.mp4"

    monkeypatch.setattr(subtitles, "_transcribe_words",
                        lambda p: [(0.0, 0.3, "Reusable"), (0.3, 0.7, "rockets")])
    burned = {}

    def fake_burn(video_path, ass_path, out_path):
        burned["ass"] = ass_path
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 5000)  # pretend ffmpeg wrote the captioned reel
    monkeypatch.setattr(subtitles, "_burn", fake_burn)

    result = subtitles.burn_captions(str(video), str(audio), str(out))
    assert result == str(out) and os.path.exists(result)
    assert os.path.exists(burned["ass"])
    with open(burned["ass"], encoding="utf-8") as f:
        content = f.read()
    assert "Reusable" in content and "rockets" in content


def test_burn_captions_empty_transcription_raises(monkeypatch, tmp_path):
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00")
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00")
    monkeypatch.setattr(subtitles, "_transcribe_words", lambda p: [])
    with pytest.raises(RuntimeError, match="no words"):
        subtitles.burn_captions(str(video), str(audio), str(tmp_path / "o.mp4"))


def test_burn_captions_missing_inputs_raise(tmp_path):
    with pytest.raises(ValueError, match="video not found"):
        subtitles.burn_captions(str(tmp_path / "no.mp4"), str(tmp_path / "no.mp3"),
                                str(tmp_path / "o.mp4"))


# --- live: real whisper + real burn ----------------------------------------------------

def test_live_caption_burn(monkeypatch, tmp_path):
    """Real faster-whisper (tiny) + FFmpeg burn on a real reel. Skips if unavailable."""
    monkeypatch.setenv("WHISPER_MODEL", "tiny")  # smaller/faster for CI
    from src import assembly, visuals, voice

    try:
        ffprobe = assembly._ffprobe()
        audio, dur = voice.synthesize(
            "Reusable rockets could cut India's launch costs. Here is why it matters.",
            str(tmp_path),
        )
        clips = visuals.fetch_broll(["rocket", "city skyline"], target_seconds=dur,
                                    out_dir=str(tmp_path))
        reel = assembly.assemble(audio, clips, str(tmp_path / "reel.mp4"))
        # pass a hook so libass really renders the frame-1 Hook style + Layer-1 dialogue
        out = subtitles.burn_captions(reel, audio, str(tmp_path / "captioned.mp4"),
                                      hook_text="Reusable Rocket SHOCK")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"live caption render unavailable (offline / no FFmpeg / model): {e}")

    assert os.path.exists(out) and os.path.getsize(out) > 50_000
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-of", "default=nw=1", out],
        capture_output=True, text=True,
    ).stdout
    assert "width=1080" in probe and "height=1920" in probe and "codec_type=audio" in probe
    assert abs(assembly.probe_duration(out) - dur) < 1.6
