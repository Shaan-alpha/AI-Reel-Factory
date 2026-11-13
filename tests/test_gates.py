"""The automatic picture checks (design 11.6): stills, clips and the finished reel."""
import logging
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from src import gates

W, H = 768, 1344
HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv(*words: tuple[str, float]) -> bytes:
    rows = [f"5\t1\t1\t1\t1\t{i}\t10\t10\t80\t30\t{conf}\t{text}\n"
            for i, (text, conf) in enumerate(words, 1)]
    return (HEADER + "1\t1\t0\t0\t0\t0\t0\t0\t768\t1344\t-1\t\n" + "".join(rows)).encode("utf-8")


def _still(tmp_path, name="still.jpg", fill=200, middle=None, bars=False) -> str:
    """A plain grey still; `middle` paints the middle half, `bars` blacks out the top and
    bottom quarters (letterbox)."""
    img = Image.new("L", (W, H), fill)
    draw = ImageDraw.Draw(img)
    if middle is not None:
        draw.rectangle((W // 4, H // 4, 3 * W // 4, 3 * H // 4), fill=middle)
    if bars:
        draw.rectangle((0, 0, W, H // 4), fill=0)
        draw.rectangle((0, 3 * H // 4, W, H), fill=0)
    path = tmp_path / name
    img.convert("RGB").save(path, quality=92)
    return str(path)


def _ocr(monkeypatch, original: bytes | None = None, doubled: bytes | None = None,
         raises=None) -> list:
    """Tesseract replaced: `original` is what it reads from the still itself, `doubled` from the
    2x copy (a TSV with no words when not given). Returns the commands it was given."""
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if raises:
            raise raises
        out = doubled if "ocr2x" in cmd[1] else original
        return SimpleNamespace(stdout=_tsv() if out is None else out, stderr=b"", returncode=0)

    monkeypatch.setattr(gates, "_tesseract", lambda: "tesseract")
    monkeypatch.setattr(gates.subprocess, "run", run)
    return calls


# --- Stills -----------------------------------------------------------------------------------

def test_a_word_read_at_70_is_text(monkeypatch, tmp_path):
    calls = _ocr(monkeypatch, original=_tsv(("TBEREOROIN", 90.2), ("ani", 59.0)))
    problems = gates.still_problems(_still(tmp_path))
    assert len(problems) == 1 and problems[0].startswith("text:")
    assert "TBEREOROIN" in problems[0] and "ani" not in problems[0]
    cmd, kwargs = calls[0]
    assert cmd[2:] == ["stdout", "--psm", "11", "tsv"] and kwargs["timeout"] == 60


def test_noise_under_70_is_not_text(monkeypatch, tmp_path):
    _ocr(monkeypatch, original=_tsv(("bel", 59.0), ("are", 68.0), ("OK", 95.0), ("A1", 99.0)))
    assert gates.still_problems(_still(tmp_path)) == []


def test_the_2x_copy_is_read_too(monkeypatch, tmp_path):
    """The render's caption read 46 from the still and 90 from a 2x copy (calibration)."""
    calls = _ocr(monkeypatch, original=_tsv(("EREORGC", 46.0)), doubled=_tsv(("BER", 90.0)))
    problems = gates.still_problems(_still(tmp_path))
    assert problems and problems[0].startswith("text:") and "BER" in problems[0]
    assert len(calls) == 2 and calls[1][0][1].endswith(".png")


def test_no_tesseract_skips_the_text_check_once(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(gates, "_tesseract", lambda: None)
    monkeypatch.setattr(gates, "_warned_no_tesseract", False)
    with caplog.at_level(logging.WARNING, logger="src.gates"):
        assert gates.still_problems(_still(tmp_path, "a.jpg")) == []
        assert gates.still_problems(_still(tmp_path, "b.jpg")) == []
    assert len([r for r in caplog.records if "Tesseract" in r.getMessage()]) == 1


def test_a_tesseract_that_fails_warns_instead_of_passing_the_still(monkeypatch, tmp_path,
                                                                   caplog):
    """Review 4a I-2: without its language data Tesseract exits 1 with a bare TSV header, which
    read as a clean still and said nothing."""
    def run(cmd, **kwargs):
        return SimpleNamespace(stdout=HEADER.encode(), returncode=1,
                               stderr=b"Error opening data file eng.traineddata")

    monkeypatch.setattr(gates, "_tesseract", lambda: "tesseract")
    monkeypatch.setattr(gates.subprocess, "run", run)
    with caplog.at_level(logging.WARNING, logger="src.gates"):
        assert gates.still_problems(_still(tmp_path)) == []
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "exited 1" in said and "eng.traineddata" in said


def test_a_tesseract_with_no_tsv_warns(monkeypatch, tmp_path, caplog):
    _ocr(monkeypatch, original=b"", doubled=b"")
    with caplog.at_level(logging.WARNING, logger="src.gates"):
        assert gates.still_problems(_still(tmp_path)) == []
    assert any("no TSV" in r.getMessage() for r in caplog.records)


def test_a_tesseract_timeout_skips_the_text_check(monkeypatch, tmp_path):
    """Review Focus 1: a hung Tesseract costs the still nothing but its text check."""
    _ocr(monkeypatch, raises=subprocess.TimeoutExpired(["tesseract"], 60))
    assert gates.still_problems(_still(tmp_path)) == []


def test_tsv_bytes_cp1252_cannot_read_are_replaced(monkeypatch, tmp_path):
    """Review Focus 5: Tesseract writes UTF-8; a Windows console decoding it crashed."""
    raw = _tsv(("WELCOME", 95.0)).replace(b"WELCOME", b"WEL\x9dCOME")
    _ocr(monkeypatch, original=raw)
    problems = gates.still_problems(_still(tmp_path))
    assert problems and problems[0].startswith("text:")


def test_a_dark_middle_is_dark(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    assert gates.still_problems(_still(tmp_path, middle=30)) == ["dark: 30.0 < 60"]


def test_letterbox_bars_are_found(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    assert gates.still_problems(_still(tmp_path, bars=True)) == ["letterbox bars"]


def test_a_dark_backdrop_is_not_bars(monkeypatch, tmp_path):
    """Clip 4's chip on a dark backdrop: top band 52, bottom 23, a bright subject."""
    _ocr(monkeypatch)
    img = Image.new("L", (W, H), 52)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, H // 2, W, H), fill=23)
    draw.rectangle((W // 4, H // 4, 3 * W // 4, 3 * H // 4), fill=150)
    path = tmp_path / "backdrop.jpg"
    img.convert("RGB").save(path, quality=92)
    assert gates.still_problems(str(path)) == []


def test_an_unreadable_still_is_a_problem(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    problems = gates.still_problems(str(path))
    assert len(problems) == 1 and problems[0].startswith("unreadable:")


def test_real_tesseract_reads_lettering(tmp_path):
    """The binary itself, when there is one (CI installs tesseract-ocr): plain lettering is
    text, a smooth gradient is not."""
    if gates._tesseract() is None:
        pytest.skip("no Tesseract binary")
    img = Image.new("L", (W, H), 170)
    ImageDraw.Draw(img).text((60, 600), "WELCOME HOME", fill=20,
                             font=ImageFont.load_default(size=90))
    lettered = tmp_path / "lettered.jpg"
    img.convert("RGB").save(lettered, quality=92)
    problems = gates.still_problems(str(lettered))
    assert problems and problems[0].startswith("text:") and "WELCOME" in problems[0]

    gradient = Image.linear_gradient("L").resize((W, H)).point(lambda v: 90 + v // 2)
    smooth = tmp_path / "smooth.jpg"
    gradient.convert("RGB").save(smooth, quality=92)
    assert gates.still_problems(str(smooth)) == []


# --- Clips --------------------------------------------------------------------------------------

def _media(monkeypatch, duration=5.04, video=True, audio=False, black=(), frozen=(), fails=None):
    """The gate's probe and its one FFmpeg detection pass, replaced."""
    def probe(path):
        if isinstance(fails, Exception):
            raise fails
        return gates.Media(duration, video, audio)

    def stretches(path, black_min, frozen_min, total):
        if fails == "stretches":
            raise subprocess.TimeoutExpired(["ffmpeg"], 120)
        return list(black), list(frozen)

    monkeypatch.setattr(gates, "_probe", probe)
    monkeypatch.setattr(gates, "_stretches", stretches)


def test_a_clip_that_covers_its_shot_passes(monkeypatch):
    _media(monkeypatch)
    assert gates.clip_problems("clip.mp4", 5.0) == []


def test_a_clip_shorter_than_4_5_s(monkeypatch):
    _media(monkeypatch, duration=4.2)
    assert gates.clip_problems("clip.mp4", 3.0) == ["short: 4.20 s < 4.50 s"]


def test_a_clip_shorter_than_its_shot(monkeypatch):
    _media(monkeypatch, duration=4.9)
    assert gates.clip_problems("clip.mp4", 5.0) == ["short: 4.90 s < 5.00 s"]


def test_a_clip_without_video(monkeypatch):
    _media(monkeypatch, video=False, audio=True)
    assert gates.clip_problems("clip.mp4", 5.0) == ["no video stream"]


def test_an_unreadable_clip(monkeypatch):
    _media(monkeypatch, fails=subprocess.CalledProcessError(1, ["ffprobe"]))
    (problem,) = gates.clip_problems("clip.mp4", 5.0)
    assert problem.startswith("unreadable:")


def test_a_black_stretch(monkeypatch):
    _media(monkeypatch, black=[0.8])
    assert gates.clip_problems("clip.mp4", 5.0) == ["black: 0.8 s"]


def test_a_frozen_stretch(monkeypatch):
    _media(monkeypatch, frozen=[1.6])
    assert gates.clip_problems("clip.mp4", 5.0) == ["frozen: 1.6 s"]


def test_a_stretch_pass_that_fails_is_skipped(monkeypatch, caplog):
    """The clip is paid for: a detection pass that cannot run does not throw it away."""
    _media(monkeypatch, fails="stretches")
    with caplog.at_level(logging.WARNING, logger="src.gates"):
        assert gates.clip_problems("clip.mp4", 5.0) == []
    assert any("could not" in r.getMessage() for r in caplog.records)


def _ffmpeg_or_skip() -> str:
    from src import assembly
    try:
        return assembly._ffmpeg()
    except RuntimeError as e:
        pytest.skip(f"no FFmpeg: {e}")


def _render(tmp_path, name: str, *graph: str) -> str:
    """A small 24 fps test clip from lavfi sources, concatenated in order."""
    ffmpeg = _ffmpeg_or_skip()
    cmd = [ffmpeg, "-v", "error", "-y"]
    for source in graph:
        cmd += ["-f", "lavfi", "-i", source]
    n = len(graph)
    cmd += ["-filter_complex", "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24",
            str(tmp_path / name)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return str(tmp_path / name)


SIZE = "s=320x568:r=24"


def test_real_ffmpeg_a_moving_clip_passes(tmp_path):
    clip = _render(tmp_path, "moving.mp4", f"testsrc2={SIZE}:d=5")
    assert gates.clip_problems(clip, 5.0) == []


def test_real_ffmpeg_finds_a_black_second(tmp_path):
    clip = _render(tmp_path, "black.mp4", f"testsrc2={SIZE}:d=2", f"color=c=black:{SIZE}:d=1",
                   f"testsrc2={SIZE}:d=2")
    problems = gates.clip_problems(clip, 5.0)
    assert len(problems) == 1 and problems[0].startswith("black: 1.0")


def test_real_ffmpeg_a_freeze_to_the_end_counts(tmp_path):
    """Review Focus 3: freezedetect logs a start and no end when the clip ends frozen."""
    clip = _render(tmp_path, "frozen.mp4",
                   f"testsrc2={SIZE}:d=2.5,tpad=stop_mode=clone:stop_duration=2.5")
    problems = gates.clip_problems(clip, 5.0)
    assert len(problems) == 1 and problems[0].startswith("frozen: ")
    assert 2.0 <= float(problems[0].split()[1]) <= 2.6


# --- The finished reel ----------------------------------------------------------------------------

def test_a_reel_that_matches_its_narration_passes(monkeypatch):
    asked = []
    monkeypatch.setattr(gates, "_probe", lambda path: gates.Media(32.52, True, True))
    monkeypatch.setattr(gates, "_stretches",
                        lambda path, black_min, frozen_min, total: asked.append(
                            (black_min, frozen_min, total)) or ([], []))
    assert gates.reel_problems("reel.mp4", 32.5) == []
    assert asked == [(1.0, 2.0, 32.52)]  # the design's reel thresholds


def test_a_reel_off_its_narration(monkeypatch):
    _media(monkeypatch, duration=32.9, audio=True)
    assert gates.reel_problems("reel.mp4", 32.5) == ["length: 32.90 s for 32.50 s of narration"]


def test_a_reel_without_audio(monkeypatch):
    _media(monkeypatch, duration=32.5, audio=False)
    assert gates.reel_problems("reel.mp4", 32.5) == ["no audio stream"]


def test_a_reel_without_video(monkeypatch):
    _media(monkeypatch, duration=32.5, video=False, audio=True)
    assert gates.reel_problems("reel.mp4", 32.5) == ["no video stream"]


def test_a_reel_with_a_long_black_stretch(monkeypatch):
    _media(monkeypatch, duration=32.5, audio=True, black=[1.4], frozen=[2.2])
    assert gates.reel_problems("reel.mp4", 32.5) == ["black: 1.4 s", "frozen: 2.2 s"]


def test_a_reel_whose_check_times_out_ships(monkeypatch):
    """Review Focus 4: a check that cannot run never costs a reel."""
    _media(monkeypatch, duration=32.5, audio=True, fails="stretches")
    assert gates.reel_problems("reel.mp4", 32.5) == []


def test_an_unreadable_reel_is_refused(monkeypatch):
    _media(monkeypatch, fails=subprocess.TimeoutExpired(["ffprobe"], 60))
    (problem,) = gates.reel_problems("reel.mp4", 32.5)
    assert problem.startswith("unreadable:")


def test_real_ffmpeg_a_reel_with_sound_passes(tmp_path):
    ffmpeg = _ffmpeg_or_skip()
    reel = tmp_path / "reel.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2={SIZE}:d=5",
                    "-f", "lavfi", "-i", "sine=f=440:d=5", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-c:a", "aac", "-shortest", str(reel)],
                   check=True, capture_output=True, timeout=120)
    assert gates.reel_problems(str(reel), 5.0) == []
    assert gates.reel_problems(str(reel), 4.0)[0].startswith("length: 5.0")


def test_the_darkness_message_shows_the_measured_value(monkeypatch, tmp_path):
    """The 4b render logged "dark: 60 < 60" for a still measured just under 60."""
    _ocr(monkeypatch)
    (problem,) = gates.still_problems(_still(tmp_path, middle=59))
    assert problem.startswith("dark: 59.") and problem.endswith("< 60")
