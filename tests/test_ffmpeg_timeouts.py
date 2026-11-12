"""Every FFmpeg call has a timeout (design 11.6; audit throughput 4).

Without one, a stalled render waited for the job's hard kill, which skips every handler: the idea
stayed 'approved' and the operator heard nothing. A timeout fails the one reel, softly.
"""
import ast
import pathlib
import subprocess

import pytest

from src import assembly


def test_every_subprocess_run_in_src_has_a_timeout():
    missing = []
    for path in pathlib.Path("src").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and getattr(node.func.value, "id", "") == "subprocess"
                    and not any(k.arg == "timeout" for k in node.keywords)):
                missing.append(f"{path}:{node.lineno}")
    assert not missing, missing


def test_a_render_that_times_out_fails_with_a_clear_error(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(assembly, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(assembly, "_measure_levels", lambda *a: {})
    monkeypatch.setattr(assembly, "_pick_music", lambda a: None)
    monkeypatch.setattr(assembly, "_sfx_enabled", lambda: False)

    def _hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(assembly.subprocess, "run", _hang)
    with pytest.raises(RuntimeError, match="timed out"):
        assembly.assemble(str(audio), [str(clip)], str(tmp_path / "out.mp4"))


def test_three_timed_out_renders_still_fit_in_one_reels_budget():
    """A hung polished render, its plain retry and the caption burn must all time out inside
    the 12 minutes a reel is started with, or the job's kill lands first (final review)."""
    assert 3 * assembly.RENDER_TIMEOUT_SECONDS <= 12 * 60
