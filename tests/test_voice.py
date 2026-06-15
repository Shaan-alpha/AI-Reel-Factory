"""Tests for the voice module (Module 4).

Unit tests mock the synthesis backends, so they need no network/model — they verify the
google → edge-tts → kokoro fallback chain, the Google Chirp 3 HD REST path, duration math,
deterministic naming, and errors. Live tests run real synthesis and skip if unavailable.
"""
from __future__ import annotations

import base64
import io
import os
import wave
from unittest import mock

import pytest

from src import voice


# --- helpers ---------------------------------------------------------------------------

def _edge_chunks(audio=b"\x00\x01\x02", end_ticks=55_000_000):
    def _gen(text, v, rate):
        yield {"type": "audio", "data": audio}
        yield {"type": "WordBoundary", "offset": end_ticks - 5_000_000,
               "duration": 5_000_000, "text": "word"}
    return _gen


def _fake_wav_b64(seconds: float = 0.5, rate: int = 24000) -> str:
    """A tiny silent LINEAR16 WAV, base64-encoded — mimics Google's audioContent."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return base64.b64encode(buf.getvalue()).decode("ascii")


# --- Google Chirp 3 HD path (mocked REST) ----------------------------------------------

def test_synthesize_google_writes_wav_and_measures_duration(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Achernar")

    resp = mock.Mock()
    resp.status_code = 200
    resp.json = mock.Mock(return_value={"audioContent": _fake_wav_b64(0.5)})
    with mock.patch("src.voice.requests.post", return_value=resp) as post:
        path, dur = voice._synthesize_google("Hello world.", str(tmp_path))

    assert path.endswith(".wav")
    assert os.path.exists(path)
    assert 0.45 <= dur <= 0.55
    sent = post.call_args.kwargs["json"]
    assert sent["voice"]["name"] == "en-IN-Chirp3-HD-Achernar"
    assert sent["voice"]["languageCode"] == "en-IN"
    assert sent["audioConfig"]["audioEncoding"] == "LINEAR16"
    assert post.call_args.kwargs["params"] == {"key": "test-key"}   # key in params, stripped


def test_synthesize_google_missing_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Achernar")
    with pytest.raises(RuntimeError):
        voice._synthesize_google("hi", str(tmp_path))


def test_synthesize_google_non200_raises_with_google_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Achernar")
    resp = mock.Mock()
    resp.status_code = 400
    resp.text = "API key not valid. Please pass a valid API key."
    with mock.patch("src.voice.requests.post", return_value=resp):
        with pytest.raises(RuntimeError, match="google tts HTTP 400: API key not valid"):
            voice._synthesize_google("hi", str(tmp_path))


# --- fallback chain --------------------------------------------------------------------

def test_synthesize_chain_prefers_google_then_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_ENGINE", "google")
    calls = []

    def ok_edge(text, out_dir):
        calls.append("edge")
        p = os.path.join(out_dir, "n.mp3"); open(p, "wb").close()
        return p, 1.0

    def boom_google(text, out_dir):
        calls.append("google"); raise RuntimeError("no key")

    monkeypatch.setattr(voice, "_synthesize_google", boom_google)
    monkeypatch.setattr(voice, "_engine_edge", ok_edge)
    monkeypatch.setattr(voice, "_engine_kokoro",
                        lambda t, d: (_ for _ in ()).throw(AssertionError("should not reach kokoro")))

    path, dur = voice.synthesize("Hello.", str(tmp_path))
    assert calls == ["google", "edge"]   # google tried first, edge second
    assert dur == 1.0


# --- edge-tts path (forced via VOICE_ENGINE) -------------------------------------------

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
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)  # google fails fast (no key)

    def _boom(text, v, rate):
        raise ConnectionError("socket closed")
        yield  # pragma: no cover
    monkeypatch.setattr(voice, "_stream_chunks", _boom)
    # kokoro is the last link in the chain now — make it fail too so ALL engines fail
    monkeypatch.setattr(voice, "_synthesize_kokoro",
                        lambda t, o: (_ for _ in ()).throw(RuntimeError("no model")))
    with pytest.raises(RuntimeError, match="all engines failed"):
        voice.synthesize("text", str(tmp_path))


# --- Kokoro path (mocked) --------------------------------------------------------------

def test_kokoro_engine_writes_wav(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")

    def fake_kokoro(text, out_path):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 4000)
        return 4.5
    monkeypatch.setattr(voice, "_synthesize_kokoro", fake_kokoro)
    path, dur = voice.synthesize("Reusable rockets.", str(tmp_path))
    assert path.endswith(".wav") and dur == 4.5 and os.path.exists(path)


def test_kokoro_falls_back_to_edge(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setattr(voice, "_synthesize_kokoro",
                        lambda t, o: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr(voice, "_stream_chunks", _edge_chunks())
    path, dur = voice.synthesize("fallback please", str(tmp_path))
    assert path.endswith(".mp3") and dur > 0  # edge-tts caught it


# --- dramatic pacing (mocked Kokoro samples) -------------------------------------------

class _FakeKokoro:
    """Returns 0.1s of audio (2400 samples @ 24kHz) per create() call."""
    sr = 24000

    def create(self, text, voice, speed, lang):
        import numpy as np
        return np.ones(2400, dtype="float32"), self.sr


def test_split_sentences():
    assert voice._split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert voice._split_sentences("Just one") == ["Just one"]
    assert voice._split_sentences("  ") == []


def test_kokoro_pacing_inserts_silence_gaps(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")
    monkeypatch.delenv("ENABLE_DRAMATIC_PACING", raising=False)  # default on
    monkeypatch.setattr(voice, "_kokoro", lambda: _FakeKokoro())
    # 3 sentences → 0.3s speech + one 0.18s gap + one 0.5s payoff beat = 0.98s
    path, dur = voice.synthesize("A cat. A dog. A bird.", str(tmp_path))
    assert path.endswith(".wav")
    assert dur == pytest.approx(0.98, abs=0.01)


def test_kokoro_pacing_disabled_is_one_shot(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")
    monkeypatch.setenv("ENABLE_DRAMATIC_PACING", "0")
    monkeypatch.setattr(voice, "_kokoro", lambda: _FakeKokoro())
    # pacing off → single create() on the whole text → just 0.1s, no gaps
    _path, dur = voice.synthesize("A cat. A dog. A bird.", str(tmp_path))
    assert dur == pytest.approx(0.1, abs=0.01)


# --- live ------------------------------------------------------------------------------

def test_live_kokoro(monkeypatch, tmp_path):
    """Real Kokoro synthesis — skips if the model isn't available / can't download."""
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")
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
