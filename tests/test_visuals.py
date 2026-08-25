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
    monkeypatch.setenv("VISUAL_SOURCE", "video")
    cands = [{"url": f"http://x/{i}.mp4", "duration": 8.0} for i in range(5)]
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: cands)
    calls = _fake_download(monkeypatch)
    paths = visuals.fetch_broll(["a"], target_seconds=15, out_dir=str(tmp_path))
    assert len(paths) == 2 and len(calls) == 2  # 8+8 >= 15, min 2 clips
    assert all(os.path.exists(p) for p in paths)


def test_fetch_broll_idempotent_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("VISUAL_SOURCE", "video")
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
    monkeypatch.setenv("VISUAL_SOURCE", "video")
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: [])
    with pytest.raises(RuntimeError, match="no B-roll found"):
        visuals.fetch_broll(["a"], 15, str(tmp_path))


# --- image-based visuals (photos / AI) -------------------------------------------------

def test_fetch_broll_photos_makes_kenburns_clips(monkeypatch, tmp_path):
    monkeypatch.delenv("VISUAL_SOURCE", raising=False)  # default = photos

    def fake_fetch_image(kw, dest, seed, source):
        with open(dest, "wb") as f:
            f.write(b"\xff" * 2048)
        return True
    monkeypatch.setattr(visuals, "_fetch_image", fake_fetch_image)

    def fake_kb(img, dest, seconds, index=0):
        with open(dest, "wb") as f:
            f.write(b"\x00" * 4096)
    monkeypatch.setattr(visuals, "_image_to_kenburns_clip", fake_kb)

    from src import assembly

    paths = visuals.fetch_broll(["courtroom", "rocket"], target_seconds=18, out_dir=str(tmp_path))
    # One image per cut the assembler will make — NOT the old local `ceil(18/6)+1` guess, which
    # under-produced against a ~3.5s cut rhythm and left the slicer replaying earlier shots.
    assert len(paths) == assembly.slice_count(18)
    assert all(p.endswith(".mp4") and os.path.exists(p) for p in paths)


def test_fetch_broll_photos_fall_back_to_video(monkeypatch, tmp_path):
    monkeypatch.delenv("VISUAL_SOURCE", raising=False)  # photos default
    monkeypatch.setattr(visuals, "_fetch_image", lambda *a, **k: False)  # no images at all
    cands = [{"url": "http://x/0.mp4", "duration": 8.0}, {"url": "http://x/1.mp4", "duration": 8.0}]
    monkeypatch.setattr(visuals, "_gather_candidates", lambda kws: cands)
    _fake_download(monkeypatch)
    paths = visuals.fetch_broll(["a"], target_seconds=12, out_dir=str(tmp_path))
    assert paths and all(p.endswith(".mp4") for p in paths)  # fell back to stock video


def test_kenburns_zoom_varies_by_index(monkeypatch):
    """Even index zooms in, odd index zooms out — built into the ffmpeg vf string."""
    from src import assembly

    captured = []

    def fake_run(cmd, **kw):
        captured.append(" ".join(cmd))
        class R:  # minimal CompletedProcess stand-in
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(visuals.subprocess, "run", fake_run)

    visuals._image_to_kenburns_clip("in.jpg", "out0.mp4", 7.0, index=0)
    visuals._image_to_kenburns_clip("in.jpg", "out1.mp4", 7.0, index=1)

    vf_in, vf_out = captured[0], captured[1]
    assert "zoom+" in vf_in            # even → zoom IN (increasing)
    assert "zoom-" in vf_out           # odd  → zoom OUT (decreasing)
    assert vf_in != vf_out


def test_cloudflare_image_no_creds_returns_false(monkeypatch):
    monkeypatch.delenv("CF_API_TOKEN", raising=False)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    assert visuals._cloudflare_image("x", "/tmp/none.jpg") is False


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


# --- B-roll must cover every cut, not recycle ---------------------------------------------

def _stub_image_pipeline(monkeypatch):
    def fake_fetch_image(kw, dest, seed, source):
        with open(dest, "wb") as f:
            f.write(b"\xff" * 2048)
        return True

    def fake_kb(img, dest, seconds, index=0):
        with open(dest, "wb") as f:
            f.write(b"\x00" * 4096)
    monkeypatch.setattr(visuals, "_fetch_image", fake_fetch_image)
    monkeypatch.setattr(visuals, "_image_to_kenburns_clip", fake_kb)


@pytest.mark.parametrize("target", [18.0, 25.0, 30.0, 35.0])
def test_image_broll_covers_every_slice_the_assembler_will_cut(monkeypatch, tmp_path, target):
    """The regression: visuals sized on a hardcoded 6s cut while assembly cuts at CLIP_SECONDS.

    Measured on the live channel 2026-08-25 — a 30s reel wanted 10 slices but got 6 images, so
    4 of them replayed earlier shots. On Ken Burns clips the slicer's usual anti-repeat trick
    (advance the start offset) cannot help: every offset of a pan over ONE still is that same
    still, so the repeat is plainly visible. Gemini's audit of the newest Short named exactly
    that loop as the swipe-away point. Enough distinct images is the only fix.
    """
    from src import assembly

    monkeypatch.delenv("VISUAL_SOURCE", raising=False)  # default = photos
    _stub_image_pipeline(monkeypatch)

    paths = visuals.fetch_broll(["courtroom", "rocket"], target_seconds=target,
                                out_dir=str(tmp_path))
    needed = assembly.slice_count(target)
    assert len(paths) >= min(needed, visuals._MAX_IMG_CLIPS), (
        f"{target}s reel cuts {needed} slices but only {len(paths)} distinct images were made "
        f"— {needed - len(paths)} slices would replay earlier footage"
    )
    assert len(set(paths)) == len(paths), "duplicate clip paths"


def test_image_broll_still_respects_the_api_call_cap(monkeypatch, tmp_path):
    """Coverage must not become an unbounded image-generation bill (rule 13)."""
    _stub_image_pipeline(monkeypatch)
    monkeypatch.delenv("VISUAL_SOURCE", raising=False)
    paths = visuals.fetch_broll(["a", "b"], target_seconds=600.0, out_dir=str(tmp_path))
    assert len(paths) <= visuals._MAX_IMG_CLIPS
