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

def test_ordered_clips_cycles_to_cover_duration(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "6")  # pin the cut length for a deterministic slice count
    clips = ["a.mp4", "b.mp4"]
    # ceil(18/6)+1 = 4 slices, cycled; unprobeable paths → start offset 0.0
    assert assembly._ordered_clips(clips, 18.0) == [
        ("a.mp4", 0.0), ("b.mp4", 0.0), ("a.mp4", 0.0), ("b.mp4", 0.0)]


def test_ordered_clips_min_one_slice(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "6")
    assert assembly._ordered_clips(["a.mp4"], 1.0) == [("a.mp4", 0.0), ("a.mp4", 0.0)]  # ceil(1/6)+1


def test_ordered_clips_staggers_repeated_clip(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "3")
    monkeypatch.setattr(assembly, "_safe_probe", lambda p: 12.0)  # span = 12-3 = 9
    # one clip, 12s reel → ceil(12/3)+1 = 5 slices; starts advance 0,3,6 then wrap (9%9=0, 12%9=3)
    out = assembly._ordered_clips(["a.mp4"], 12.0)
    assert [s for _p, s in out] == [0.0, 3.0, 6.0, 0.0, 3.0]


def test_ordered_clips_overlap_adds_slices(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "6")
    # overlap=0 reproduces the old count exactly (regression guard)
    assert len(assembly._ordered_clips(["a.mp4", "b.mp4"], 18.0, overlap=0.0)) == 4
    # with overlap each slice covers less → needs at least as many slices
    assert len(assembly._ordered_clips(["a.mp4", "b.mp4"], 18.0, overlap=1.0)) >= 4


def test_build_cmd_xfade_chain_and_offsets(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "true")
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")  # isolate the xfade video chain (no logo map)
    monkeypatch.setenv("XFADE_SECONDS", "0.4")
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    cmd = assembly._build_cmd(
        [("c0.mp4", 0.0), ("c1.mp4", 0.0), ("c2.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.400" in fc
    assert "concat=n=" not in fc                 # concat replaced by xfade
    assert "offset=3.100" in fc                  # i=1 → 1*(3.5-0.4)=3.1
    assert "offset=6.200" in fc                  # i=2 → 2*(3.5-0.4)=6.2
    assert "[v]" in cmd                          # final graded video still mapped


def test_build_cmd_single_slice_uses_concat_not_xfade(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "true")
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 5.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=1" in fc and "xfade" not in fc  # nothing to crossfade with one clip


def test_seamless_loop_ends_on_first_clip(monkeypatch):
    """The reprise lands on the last slice the viewer actually sees.

    This used to pass `out[-1]`, i.e. the very last entry — which the trim always discards,
    because slice_count over-covers the narration on purpose. With a 3-slice list fully inside
    a 12s reel the last entry IS the last visible one, so the intent is unchanged; the extra
    args are what let the function tell the two apart when they differ.
    """
    monkeypatch.delenv("ENABLE_SEAMLESS_LOOP", raising=False)  # default on
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    ordered = [("a.mp4", 0.0), ("b.mp4", 0.0), ("c.mp4", 3.0)]
    out = assembly._apply_seamless_loop(ordered, duration=12.0, overlap=0.0)
    assert out[-1] == ("a.mp4", 0.0)          # last visible slice reuses the opening clip
    assert out[:-1] == ordered[:-1]           # earlier slices unchanged


def test_seamless_loop_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_SEAMLESS_LOOP", "false")
    ordered = [("a.mp4", 0.0), ("b.mp4", 0.0)]
    assert assembly._apply_seamless_loop(ordered, duration=10.0, overlap=0.0) == ordered


def test_seamless_loop_single_slice_noop(monkeypatch):
    monkeypatch.delenv("ENABLE_SEAMLESS_LOOP", raising=False)
    assert assembly._apply_seamless_loop(
        [("a.mp4", 0.0)], duration=5.0, overlap=0.0) == [("a.mp4", 0.0)]


def test_clip_seconds_clamped(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "0.2")   # too fast → clamped up
    assert assembly._clip_seconds() == assembly._MIN_CLIP_SECONDS
    monkeypatch.setenv("CLIP_SECONDS", "999")   # too slow → clamped down
    assert assembly._clip_seconds() == assembly._MAX_CLIP_SECONDS


def test_build_cmd_structure(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "false")  # exercise the plain concat path
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")  # isolate base video plumbing (no logo input/map)
    cmd = assembly._build_cmd([("c0.mp4", 0.0), ("c1.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
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


def test_grade_filters_present_by_default(monkeypatch):
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)  # defaults on
    f = assembly._grade_filters()
    assert "eq=contrast=" in f and "vignette" in f and "noise=" in f


def test_grade_filters_empty_when_all_disabled(monkeypatch):
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.setenv(k, "false")
    assert assembly._grade_filters() == ""


def test_build_cmd_includes_grade_in_filtergraph(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("ENABLE_XFADE", "false")  # isolate the concat path
    for k in ("ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)
    cmd = assembly._build_cmd([("c0.mp4", 0.0), ("c1.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "eq=contrast=" in fc and "vignette" in fc


def test_build_cmd_plain_when_polish_false(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    for k in ("ENABLE_XFADE", "ENABLE_GRADE", "ENABLE_VIGNETTE", "ENABLE_GRAIN"):
        monkeypatch.delenv(k, raising=False)  # all default ON…
    cmd = assembly._build_cmd([("c0.mp4", 0.0), ("c1.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4",
                              polish=False)  # …but polish=False overrides
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade" not in fc and "eq=contrast=" not in fc
    assert "concat=n=2" in fc


def test_assemble_falls_back_to_plain_on_polish_failure(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00")
    clip = tmp_path / "c.mp4"; clip.write_bytes(b"\x00")
    out = tmp_path / "o.mp4"

    monkeypatch.setattr(assembly, "probe_duration", lambda p: 6.0)
    monkeypatch.setattr(assembly, "_pick_music", lambda p: None)

    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        fc = cmd[cmd.index("-filter_complex") + 1]
        polished = ("xfade" in fc) or ("eq=contrast=" in fc)
        class R:
            returncode = 1 if (polished and calls["n"] == 1) else 0
            stderr = "boom"
        if R.returncode == 0:
            out.write_bytes(b"\x00" * 60_000)  # simulate a produced file
        return R()

    monkeypatch.setattr(assembly.subprocess, "run", fake_run)
    result = assembly.assemble(str(audio), [str(clip)], str(out))
    assert result == str(out)
    assert calls["n"] == 2  # polished attempt failed → plain retry succeeded


def test_build_cmd_mixes_music_when_present(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4", music_path="bed.mp3")
    assert "-stream_loop" in cmd and "bed.mp3" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2:duration=first" in fc
    assert "[aout]" in cmd  # mixed audio is mapped


def test_build_cmd_ducks_music_when_polish(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.delenv("ENABLE_DUCKING", raising=False)  # default on
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4", music_path="bed.mp3")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc and "asplit" in fc
    assert "[aout]" in cmd


def test_build_cmd_plain_mix_when_polish_false(monkeypatch):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4",
                              music_path="bed.mp3", polish=False)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" not in fc      # fail-soft retry uses the simple mix
    assert "amix=inputs=2:duration=first" in fc


def test_build_cmd_overlays_logo_when_present(monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"; logo.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("BRAND_LOGO", str(logo))
    monkeypatch.delenv("ENABLE_BRAND_BUG", raising=False)
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=" in fc and "colorchannelmixer=aa=" in fc
    assert "[vout]" in cmd                       # logo-composited video is what gets mapped
    assert str(logo) in cmd                      # logo added as an input


def test_build_cmd_no_logo_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(assembly, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setenv("BRAND_LOGO", str(tmp_path / "missing.png"))  # does not exist
    cmd = assembly._build_cmd([("c0.mp4", 0.0)], "narr.mp3", 9.0, "out.mp4")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=" not in fc
    assert "[v]" in cmd and "[vout]" not in cmd  # plain video map


def test_brand_logo_disabled(monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"; logo.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setenv("BRAND_LOGO", str(logo))
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")
    assert assembly._brand_logo() is None


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


# --- SFX events + mix plumbing ---------------------------------------------------------

def _ordered(n: int) -> list[tuple[str, float]]:
    return [(f"c{i}.mp4", 0.0) for i in range(n)]


def test_sfx_events_skip_the_hook_window(monkeypatch):
    """Nothing may fire over the opening — the hook is the highest-leverage retention moment."""
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    monkeypatch.setenv("ENABLE_XFADE", "false")
    monkeypatch.setenv("SFX_EVERY_N_CUTS", "1")  # densest setting still respects the lead-in
    events = assembly._build_sfx_events(_ordered(9), 28.0)
    assert events, "expected some SFX events"
    assert min(e["time"] for e in events) >= assembly._SFX_LEAD_IN


def test_sfx_events_are_sparse_and_quiet_by_default(monkeypatch):
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    monkeypatch.setenv("ENABLE_XFADE", "false")
    for k in ("SFX_EVERY_N_CUTS", "SFX_VOLUME"):
        monkeypatch.delenv(k, raising=False)
    events = assembly._build_sfx_events(_ordered(9), 28.0)
    # every 2nd cut, not all 8 of them
    assert 2 <= len(events) <= 5
    assert all(e["volume"] == pytest.approx(0.18) for e in events)
    # never past the end of the narration
    assert all(e["time"] < 28.0 - 0.5 for e in events)


def test_sfx_event_times_land_on_the_xfade_cuts(monkeypatch):
    """SFX times must mirror _build_cmd's xfade offsets or the stings land beside the cuts."""
    monkeypatch.setenv("CLIP_SECONDS", "4.0")
    monkeypatch.setenv("XFADE_SECONDS", "0.5")
    monkeypatch.setenv("ENABLE_XFADE", "true")
    monkeypatch.setenv("SFX_EVERY_N_CUTS", "1")
    events = assembly._build_sfx_events(_ordered(6), 30.0)
    step = 4.0 - 0.5
    assert [e["time"] for e in events] == [pytest.approx(i * step) for i in range(1, 6)]


def test_sfx_volume_zero_disables_events(monkeypatch):
    monkeypatch.setenv("SFX_VOLUME", "0")
    assert assembly._build_sfx_events(_ordered(9), 28.0) == []


def test_sfx_volume_and_density_are_clamped(monkeypatch):
    monkeypatch.setenv("SFX_VOLUME", "5")
    assert assembly._sfx_volume() == 1.0
    monkeypatch.setenv("SFX_VOLUME", "not-a-number")
    assert assembly._sfx_volume() == pytest.approx(0.18)
    monkeypatch.setenv("SFX_EVERY_N_CUTS", "0")
    assert assembly._sfx_every_n_cuts() == 1


def test_build_cmd_mixes_sfx_and_limits_the_sum(tmp_path, monkeypatch):
    """`normalize=0` sums inputs, so an SFX layer needs a limiter or the narration clips."""
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")
    sfx = tmp_path / "sfx_track.wav"
    sfx.write_bytes(b"RIFFfake")
    cmd = assembly._build_cmd(_ordered(2), "narr.mp3", 9.0, "out.mp4", sfx_path=str(sfx))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[2:a]" in graph, "SFX must be added as the input after the narration"
    assert "amix=inputs=2" in graph
    assert "alimiter=limit=0.95" in graph
    assert cmd[cmd.index("-map") + 1] == "[v]"


def test_build_cmd_sfx_plus_music_keeps_input_indices_straight(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")
    monkeypatch.setenv("ENABLE_DUCKING", "false")  # exercise the flat 3-way mix
    monkeypatch.setenv("MUSIC_VOLUME", "0.10")
    sfx = tmp_path / "sfx_track.wav"
    sfx.write_bytes(b"RIFFfake")
    cmd = assembly._build_cmd(_ordered(2), "narr.mp3", 9.0, "out.mp4",
                              sfx_path=str(sfx), music_path="bed.mp3")
    graph = cmd[cmd.index("-filter_complex") + 1]
    # inputs: 0,1 clips · 2 narration · 3 sfx · 4 music
    assert "[4:a]volume=0.10[abg]" in graph
    assert "[2:a][3:a][abg]amix=inputs=3" in graph
    assert "alimiter" in graph


def test_build_cmd_without_sfx_is_unchanged(monkeypatch):
    """No SFX → no limiter and no extra input: the path that ships today must not shift."""
    monkeypatch.setenv("ENABLE_BRAND_BUG", "false")
    cmd = assembly._build_cmd(_ordered(2), "narr.mp3", 9.0, "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "alimiter" not in graph
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "2:a"


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


# --- cut-rhythm contract (shared with visuals) ------------------------------------------

def test_slice_count_matches_what_ordered_clips_actually_builds(monkeypatch):
    """`slice_count` is the SINGLE source of truth for how many cuts a reel needs.

    visuals sizes its image generation from it, so if it ever disagrees with the slicer the
    reel silently goes back to recycling B-roll — the exact drift this function exists to stop.
    """
    monkeypatch.delenv("CLIP_SECONDS", raising=False)
    clips = [f"/tmp/c{i}.mp4" for i in range(40)]
    monkeypatch.setattr(assembly, "_safe_probe", lambda c: 7.0)
    for duration in (12.0, 18.0, 25.0, 30.0, 35.0, 48.0):
        assert assembly.slice_count(duration) == len(
            assembly._ordered_clips(clips, duration,
                                    overlap=assembly._xfade_seconds()
                                    if assembly._xfade_enabled() else 0.0)
        ), f"slice_count disagrees with _ordered_clips at {duration}s"


def test_slice_count_accounts_for_crossfade_overlap(monkeypatch):
    """Crossfades shrink each slice's effective coverage, so a faded reel needs MORE slices."""
    monkeypatch.setattr(assembly, "_xfade_enabled", lambda: False)
    hard = assembly.slice_count(30.0)
    monkeypatch.setattr(assembly, "_xfade_enabled", lambda: True)
    monkeypatch.setattr(assembly, "_xfade_seconds", lambda: 0.5)
    assert assembly.slice_count(30.0) >= hard


# --- the loop reprise must land inside the trimmed reel ------------------------------------

def test_seamless_loop_reprise_is_actually_visible(monkeypatch):
    """ENABLE_SEAMLESS_LOOP replaced the LAST slice, which the trim always cuts away.

    slice_count over-covers the narration on purpose, so the final slice starts at or past the
    trim point: measured across 23/25/28/30s narrations the reprise was on screen for 0.00s.
    The feature has never once done anything. It must replace the last slice that is still
    VISIBLE after the trim.
    """
    monkeypatch.setenv("CLIP_SECONDS", "3.5")
    monkeypatch.setenv("ENABLE_SEAMLESS_LOOP", "true")
    duration = 28.0
    clips = [f"c{i}.mp4" for i in range(12)]
    overlap = assembly._xfade_seconds() if assembly._xfade_enabled() else 0.0
    ordered = assembly._apply_seamless_loop(
        assembly._ordered_clips(clips, duration, overlap=overlap), duration, overlap)

    step = 3.5 - overlap
    visible = [i for i in range(len(ordered)) if i * step < duration]
    assert visible, "sanity: some slice must be visible"
    last_visible = visible[-1]
    assert ordered[last_visible][0] == ordered[0][0], (
        "the last VISIBLE slice must reprise the opening shot")


def test_seamless_loop_off_leaves_the_order_alone(monkeypatch):
    monkeypatch.setenv("ENABLE_SEAMLESS_LOOP", "false")
    ordered = [("a.mp4", 0.0), ("b.mp4", 0.0), ("c.mp4", 0.0)]
    assert assembly._apply_seamless_loop(list(ordered), 10.0, 0.0) == ordered


def test_music_only_mix_is_limited(monkeypatch, tmp_path):
    """`normalize=0` sums without headroom, so any mix can clip — including music-only.

    The limiter was gated on `has_sfx`, and SFX_DIR="" meant SFX never rendered at all, so in
    production the ONLY mix ever built (narration + music bed) went out unlimited.
    """
    music = tmp_path / "bed.mp3"
    music.write_bytes(b"x")
    cmd = assembly._build_cmd([("a.mp4", 0.0), ("b.mp4", 0.0)], "n.wav", 20.0,
                              str(tmp_path / "o.mp4"), music_path=str(music), sfx_path=None)
    fg = " ".join(cmd)
    assert "amix" in fg, "sanity: a music bed means a mix happened"
    assert "alimiter" in fg, "a summed mix must be limited, with or without SFX"


def test_narration_only_render_is_not_limited(monkeypatch, tmp_path):
    """No mix, no summing, nothing to limit — don't touch a clean voice track."""
    cmd = assembly._build_cmd([("a.mp4", 0.0), ("b.mp4", 0.0)], "n.wav", 20.0,
                              str(tmp_path / "o.mp4"), music_path=None, sfx_path=None)
    assert "alimiter" not in " ".join(cmd)
