"""Tests for the visuals module (Module 5).

Unit tests mock the HTTP layer (search + download), so they need no key/network — they verify
keyword extraction, portrait-file selection, coverage logic, idempotent caching, and the
Pexels→Pixabay fallback (rule 7, rule 11). A final live test does a real Pexels search +
download and skips when offline / unkeyed.
"""
from __future__ import annotations

import os

import pytest

from src import visuals

SCRIPT = (
    "India's ISRO just launched a reusable rocket. According to the space agency, "
    "reusability could slash launch costs and open the market to startups. That matters "
    "because cheaper launches mean more Indian satellites and jobs."
)


# --- keywords --------------------------------------------------------------------------

def test_keywords_via_llm(monkeypatch):
    monkeypatch.setattr(visuals.llm, "generate",
                        lambda *a, **k: '{"keywords": ["ISRO rocket", "satellite", "launch pad"]}')
    assert visuals.extract_keywords(SCRIPT, n=3) == ["ISRO rocket", "satellite", "launch pad"]


def test_keywords_heuristic_fallback(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(visuals.llm, "generate", _boom)
    kws = visuals.extract_keywords(SCRIPT, n=5)
    assert 1 <= len(kws) <= 5
    assert all(w not in visuals._STOPWORDS for w in kws)
    assert kws == [w.lower() for w in kws]  # lowercased content words


def test_keywords_empty_script():
    assert visuals.extract_keywords("  ") == []


# --- portrait selection ----------------------------------------------------------------

def test_pick_portrait_file_prefers_1080_wide():
    video = {"video_files": [
        {"file_type": "video/mp4", "width": 540, "height": 960, "link": "sd"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "hd"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "landscape"},
    ]}
    assert visuals._pick_portrait_file(video) == "hd"


def test_pick_portrait_file_none_when_no_portrait():
    video = {"video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "x"}]}
    assert visuals._pick_portrait_file(video) is None


# --- fetch_broll -----------------------------------------------------------------------

def _fake_download(monkeypatch):
    calls = []

    def _dl(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"\x00" * 2048)
    monkeypatch.setattr(visuals, "_download", _dl)
    return calls


def test_fetch_broll_covers_target_and_stops(monkeypatch, tmp_path):
    cands = [{"url": f"http://x/{i}.mp4", "duration": 8.0} for i in range(5)]
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: cands)
    calls = _fake_download(monkeypatch)
    paths = visuals.fetch_broll(["a"], target_seconds=15, out_dir=str(tmp_path))
    assert len(paths) == 2 and len(calls) == 2  # 8+8 >= 15, min 2 clips
    assert all(os.path.exists(p) for p in paths)


def test_fetch_broll_idempotent_cache(monkeypatch, tmp_path):
    cands = [{"url": f"http://x/{i}.mp4", "duration": 8.0} for i in range(3)]
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: cands)
    calls = _fake_download(monkeypatch)
    visuals.fetch_broll(["a"], target_seconds=15, out_dir=str(tmp_path))
    n_first = len(calls)
    visuals.fetch_broll(["a"], target_seconds=15, out_dir=str(tmp_path))  # rerun
    assert len(calls) == n_first  # cached files not re-downloaded


def test_fetch_broll_pixabay_fallback(monkeypatch):
    monkeypatch.setattr(visuals, "_pexels_search", lambda kw: [])
    pix = [{"url": "http://pix/1.mp4", "duration": 8.0}]
    monkeypatch.setattr(visuals, "_pixabay_search", lambda kw: pix)
    assert visuals._gather_candidates(["a"]) == pix


def test_fetch_broll_no_results_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: [])
    with pytest.raises(RuntimeError, match="no B-roll found"):
        visuals.fetch_broll(["a"], 15, str(tmp_path))


def test_fetch_broll_no_keywords_raises(tmp_path):
    with pytest.raises(ValueError, match="no keywords"):
        visuals.fetch_broll([], 15, str(tmp_path))


def test_live_pexels_fetch(tmp_path):
    """Real Pexels search + download — skips if offline / no key."""
    try:
        paths = visuals.fetch_broll(["nature", "city skyline"], target_seconds=10, out_dir=str(tmp_path))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Pexels unreachable / unkeyed: {e}")
    assert len(paths) >= 1
    assert all(os.path.exists(p) and os.path.getsize(p) > 10_000 for p in paths)
