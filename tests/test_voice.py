"""Tests for the voice module (Module 4).

Unit tests mock the synthesis backends, so they need no network/model — they verify the
Kokoro→edge-tts engine selection + fallback, duration math, deterministic naming, and errors.
Two live tests (Kokoro and edge-tts) run real synthesis and skip if unavailable (offline / no model).
"""
from __future__ import annotations

import os

import pytest

from src import voice


# --- edge-tts path (forced via VOICE_ENGINE) -------------------------------------------

def _edge_chunks(audio=b"\x00\x01\x02", end_ticks=55_000_000):
    def _gen(text, v, rate):
        yield {"type": "audio", "data": audio}
        yield {"type": "WordBoundary", "offset": end_ticks - 5_000_000,
               "duration": 5_000_000, "text": "word"}
    return _gen


def test_edge_writes_file_and_measures_duration(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "edge-tts")
    monkeypatch.setattr(voice, "_stream_chunks", _edge_chunks(end_ticks=55_000_000))
    path, duration = voice.synthesize("Hello world narration.", str(tmp_path))
    assert path.endswith(".mp3") and os.path.getsize(path) > 0
    assert duration == pytest.approx(5.5)


def test_edge_deterministic_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "edge-tts")
    monkeypatch.setattr(voice, "_stream_chunks", _edge_chunks())
    p1, _ = voice.synthesize("same text", str(tmp_path))
    p2, _ = voice.synthesize("same text", str(tmp_path))
    assert p1 == p2 and os.path.basename(p1).startswith("narration_")


def test_empty_script_raises(tmp_path):
    with pytest.raises(ValueError, match="empty script_body"):
        voice.synthesize("   ", str(tmp_path))


def test_all_engines_fail_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "edge-tts")
    def _boom(text, v, rate):
        raise ConnectionError("socket closed")
        yield  # pragma: no cover
    monkeypatch.setattr(voice, "_stream_chunks", _boom)
    with pytest.raises(RuntimeError, match="all engines failed"):
        voice.synthesize("text", str(tmp_path))


# --- Kokoro path (mocked) --------------------------------------------------------------

def test_kokoro_is_default_and_writes_wav(monkeypatch, tmp_path):
    monkeypatch.delenv("VOICE_ENGINE", raising=False)  # default = kokoro

    def fake_kokoro(text, out_path):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 4000)
        return 4.5
    monkeypatch.setattr(voice, "_synthesize_kokoro", fake_kokoro)
    path, dur = voice.synthesize("Reusable rockets.", str(tmp_path))
    assert path.endswith(".wav") and dur == 4.5 and os.path.exists(path)


def test_kokoro_falls_back_to_edge(monkeypatch, tmp_path):
    monkeypatch.delenv("VOICE_ENGINE", raising=False)  # kokoro default
    monkeypatch.setattr(voice, "_synthesize_kokoro",
                        lambda t, o: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr(voice, "_stream_chunks", _edge_chunks())
    path, dur = voice.synthesize("fallback please", str(tmp_path))
    assert path.endswith(".mp3") and dur > 0  # edge-tts caught it


# --- live ------------------------------------------------------------------------------

def test_live_kokoro(tmp_path):
    """Real Kokoro synthesis — skips if the model isn't available / can't download."""
    try:
        path, duration = voice._kokoro() and voice.synthesize(
            "This is a Kokoro narration test for But It Matters.", str(tmp_path))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"kokoro unavailable: {e}")
    assert os.path.exists(path) and path.endswith(".wav") and 0 < duration < 60


def test_live_edge_tts(monkeypatch, tmp_path):
    """Real edge-tts synthesis — skips if offline."""
    monkeypatch.setenv("VOICE_ENGINE", "edge-tts")
    try:
        path, duration = voice.synthesize("A short edge test for But It Matters.", str(tmp_path))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"edge-tts unreachable: {e}")
    assert os.path.exists(path) and os.path.getsize(path) > 1000 and 0 < duration < 60
