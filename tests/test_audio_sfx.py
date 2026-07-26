"""Tests for src/audio_sfx.py."""
from __future__ import annotations

import os
import struct
import wave

from src import audio_sfx


def test_ensure_sfx_assets(tmp_path):
    sfx_dir = str(tmp_path / "sfx")
    paths = audio_sfx.ensure_sfx_assets(sfx_dir)
    assert len(paths) >= 5
    for name in ("whoosh", "pop", "ding", "boom", "click"):
        assert name in paths
        assert os.path.isfile(paths[name])
        assert os.path.getsize(paths[name]) > 100


def test_mix_sfx_events(tmp_path):
    sfx_dir = str(tmp_path / "sfx")
    out_path = str(tmp_path / "mix.wav")
    events = [
        {"time": 0.0, "name": "whoosh", "volume": 0.5},
        {"time": 0.2, "name": "pop", "volume": 0.8},
        {"time": 0.5, "name": "ding"},
    ]
    res = audio_sfx.mix_sfx_events(events, total_duration=1.0, out_path=out_path, sfx_dir=sfx_dir)
    assert res == out_path
    assert os.path.isfile(out_path)
    with wave.open(out_path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 44100
        duration = w.getnframes() / 44100.0
        assert duration >= 1.0


def _samples(path: str) -> tuple[int, ...]:
    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    return struct.unpack(f"<{len(frames) // 2}h", frames)


def test_mixed_track_is_little_endian_and_in_range(tmp_path):
    """The bulk `array` write must produce the same little-endian PCM the per-sample pack did."""
    out = str(tmp_path / "m.wav")
    audio_sfx.mix_sfx_events([{"time": 0.1, "name": "boom", "volume": 0.5}], 1.0, out,
                             sfx_dir=str(tmp_path / "sfx"))
    s = _samples(out)
    assert len(s) == int(44100 * 1.5)
    assert all(-32768 <= v <= 32767 for v in s)
    assert any(v != 0 for v in s), "the boom should have been mixed in"
    assert all(v == 0 for v in s[:4000]), "nothing should precede a t=0.1s event"


def test_generated_sfx_are_deterministic(tmp_path):
    """Seeded noise → byte-identical assets on the dev box and in CI (rule 10)."""
    a = audio_sfx.ensure_sfx_assets(str(tmp_path / "a"))
    b = audio_sfx.ensure_sfx_assets(str(tmp_path / "b"))
    for name in a:
        assert open(a[name], "rb").read() == open(b[name], "rb").read(), name


def test_mix_ignores_unknown_names_and_out_of_range_times(tmp_path):
    out = str(tmp_path / "m.wav")
    events = [
        {"time": 0.1, "name": "nope"},          # unknown effect
        {"time": -5.0, "name": "pop"},          # negative
        {"time": 99.0, "name": "pop"},          # past the end
        {"time": "abc", "name": "pop"},         # unparseable
        {"time": 0.2, "name": "POP ", "volume": 0.4},  # case/space tolerated
    ]
    audio_sfx.mix_sfx_events(events, 1.0, out, sfx_dir=str(tmp_path / "sfx"))
    assert any(v != 0 for v in _samples(out)), "the one valid event should still land"


def test_volume_scales_the_mix(tmp_path):
    loud, quiet = str(tmp_path / "l.wav"), str(tmp_path / "q.wav")
    sfx_dir = str(tmp_path / "sfx")
    audio_sfx.mix_sfx_events([{"time": 0.0, "name": "ding", "volume": 0.8}], 1.0, loud, sfx_dir)
    audio_sfx.mix_sfx_events([{"time": 0.0, "name": "ding", "volume": 0.2}], 1.0, quiet, sfx_dir)
    assert max(abs(v) for v in _samples(loud)) > max(abs(v) for v in _samples(quiet)) * 2
