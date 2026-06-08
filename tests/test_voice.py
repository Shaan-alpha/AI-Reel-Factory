"""Tests for the voice module (Module 4).

The unit tests mock the edge-tts stream, so they need no network — they verify file writing,
duration math from WordBoundary ticks, deterministic naming, and error wrapping (rule 7).
A final live test does a real synthesis and auto-skips when offline (edge-tts needs network).
"""
from __future__ import annotations

import os

import pytest

from src import voice


def _chunks(audio=b"\x00\x01\x02", end_ticks=55_000_000):
    """A fake edge-tts stream: one audio chunk + one WordBoundary ending at `end_ticks`."""
    def _gen(text, v, rate):
        yield {"type": "audio", "data": audio}
        yield {"type": "WordBoundary", "offset": end_ticks - 5_000_000,
               "duration": 5_000_000, "text": "word"}
    return _gen


def test_writes_file_and_measures_duration(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_stream_chunks", _chunks(end_ticks=55_000_000))
    path, duration = voice.synthesize("Hello world narration.", str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0
    assert duration == pytest.approx(5.5)  # 55_000_000 ticks / 1e7


def test_deterministic_filename(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_stream_chunks", _chunks())
    p1, _ = voice.synthesize("same text", str(tmp_path))
    p2, _ = voice.synthesize("same text", str(tmp_path))
    assert p1 == p2
    assert os.path.basename(p1).startswith("narration_") and p1.endswith(".mp3")


def test_empty_script_raises(tmp_path):
    with pytest.raises(ValueError, match="empty script_body"):
        voice.synthesize("   ", str(tmp_path))


def test_no_audio_raises_runtime(monkeypatch, tmp_path):
    def _no_audio(text, v, rate):
        yield {"type": "WordBoundary", "offset": 0, "duration": 1_000_000, "text": "x"}
    monkeypatch.setattr(voice, "_stream_chunks", _no_audio)
    with pytest.raises(RuntimeError, match="edge-tts failed"):
        voice.synthesize("text with no audio", str(tmp_path))


def test_synthesis_error_is_wrapped(monkeypatch, tmp_path):
    def _boom(text, v, rate):
        raise ConnectionError("socket closed")
        yield  # pragma: no cover — makes this a generator
    monkeypatch.setattr(voice, "_stream_chunks", _boom)
    with pytest.raises(RuntimeError, match="Kokoro fallback is Phase 2"):
        voice.synthesize("text", str(tmp_path))


def test_live_edge_tts(tmp_path):
    """Real edge-tts call — skips if offline / service unreachable."""
    try:
        path, duration = voice.synthesize(
            "This is a short narration test for But It Matters.", str(tmp_path)
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"edge-tts unreachable (offline?): {e}")
    assert os.path.exists(path) and os.path.getsize(path) > 1000
    assert 0 < duration < 60
