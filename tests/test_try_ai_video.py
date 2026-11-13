"""tools/try_ai_video.py, offline. The tool spends real money the times it runs, so its flow is
tested first: it refuses without --yes-spend or without the ledger table (before any paid step),
and otherwise renders through the same calls a reel makes, at 24 fps, uploading nothing."""
from __future__ import annotations

import importlib.util
import os

import pytest

from src import ai_video, assembly, db, hinglish, publish_youtube, subtitles, voice

_TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools",
                     "try_ai_video.py")


def _tool():
    spec = importlib.util.spec_from_file_location("try_ai_video", _TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _no_upload(monkeypatch):
    monkeypatch.setattr(publish_youtube, "publish",
                        lambda *a, **k: pytest.fail("the test render never uploads"))


def test_it_refuses_to_spend_without_yes_spend(monkeypatch, capsys):
    monkeypatch.setenv("HF_API_KEY", "abc123:def456")
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: pytest.fail("not asked"))
    assert _tool().main([]) == 2
    assert "--yes-spend" in capsys.readouterr().out


def test_it_refuses_without_the_ledger_table(monkeypatch, capsys):
    """No table, nothing can be bought: stop before the Hinglish and the voice cost anything."""
    monkeypatch.setenv("HF_API_KEY", "abc123:def456")

    def missing():
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setattr(db, "ai_video_spend_this_month", missing)
    monkeypatch.setattr(hinglish, "to_hinglish", lambda *a: pytest.fail("nothing is spent"))
    assert _tool().main(["--yes-spend"]) == 2
    assert "docs/03" in capsys.readouterr().out


def _fake_render(monkeypatch, tool) -> dict:
    """Every paid or slow step of the tool replaced; returns what each was handed."""
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 1.5)
    monkeypatch.setattr(tool, "_pick", lambda script_id: (
        {"id": 70, "idea_id": 7, "body": "Prices rose. Here is why.", "title": "Prices rose"},
        {"id": 7, "title": "Prices rose in India", "hook": "h", "angle": "a",
         "sources": ["https://example.com/a"]}))
    lines = [{"en": "Prices rose.", "hi": "दाम बढ़े।", "said": "दाम बढ़े।"}]
    monkeypatch.setattr(hinglish, "to_hinglish", lambda body, title, tone: (
        {"said": "दाम बढ़े।", "lines": lines}, ""))
    monkeypatch.setattr(voice, "synthesize", lambda text, out_dir, meta=None, tone=None,
                        expected_seconds=None: (meta.update(voice="gemini:x") or
                                                (os.path.join(out_dir, "a.wav"), 9.0)))
    monkeypatch.setattr(subtitles, "preflight", lambda *a, **k: True)
    monkeypatch.setattr(subtitles, "pauses", lambda audio: [])
    seen = {}

    def make_shots(req):
        seen["req"] = req
        return ai_video.Shots(files=["s0.mp4", "s1.mp4"], kinds=["video", "still"],
                              cuts=assembly.cut_list(9.0, []), planned_video=2,
                              spend_usd=0.1575, problems=[])

    monkeypatch.setattr(ai_video, "make_shots", make_shots)
    monkeypatch.setattr(ai_video, "reel_line", lambda shots: "🎞️ AI video: 1 of 2 shots")
    monkeypatch.setattr(ai_video, "close_run", lambda since: "🎞️ AI video this run: 1 clip")

    def assemble(audio, clips, out, cuts=None, fps=30):
        seen["assemble"] = (clips, fps)
        return out

    def burn(raw, audio, out, lines, hook_text=None, source_label=None, fps=30):
        seen["burn"] = fps
        with open(out, "wb") as f:
            f.write(b"mp4")
        return out

    monkeypatch.setattr(assembly, "assemble", assemble)
    monkeypatch.setattr(subtitles, "burn_hinglish", burn)
    return seen


def test_a_render_goes_to_a_file_at_24_fps(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HF_API_KEY", "abc123:def456")
    tool = _tool()
    seen = _fake_render(monkeypatch, tool)
    out = tmp_path / "try.mp4"
    assert tool.main(["--yes-spend", "--out", str(out)]) == 0
    assert out.read_bytes() == b"mp4"
    assert seen["assemble"] == (["s0.mp4", "s1.mp4"], 24) and seen["burn"] == 24
    assert seen["req"].idea_id == 7 and seen["req"].setting == "India"
    printed = capsys.readouterr().out
    assert "1 of 2 shots" in printed and "abc123" not in printed


def test_a_windows_console_cannot_crash_a_paid_render(monkeypatch, tmp_path):
    """2026-11-13: the first real render bought its six clips, then died printing "🎞️" to a
    Windows console (cp1252) before it wrote the reel."""
    import io
    import sys

    monkeypatch.setenv("HF_API_KEY", "abc123:def456")
    tool = _tool()
    _fake_render(monkeypatch, tool)
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    out = tmp_path / "try.mp4"
    assert tool.main(["--yes-spend", "--out", str(out)]) == 0
    assert out.exists()
