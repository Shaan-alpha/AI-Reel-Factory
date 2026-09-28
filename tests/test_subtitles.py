"""Tests for the subtitles module (Module 7).

Unit tests cover timestamp formatting, gap-filling, ASS generation, and the burn_captions
orchestration with transcription + ffmpeg mocked (no model download, no ffmpeg). A final live
test runs real faster-whisper (tiny) + a real burn and skips if anything is unavailable.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from src import subtitles


def test_build_ass_includes_source_lowerthird(monkeypatch):
    monkeypatch.delenv("ENABLE_SOURCE_CITE", raising=False)  # default on
    ass = subtitles._build_ass([(0.0, 0.5, "hi")], source_label="thehindu.com")
    assert "Style: Source," in ass
    assert "Source: thehindu.com" in ass


def test_build_ass_no_source_when_label_missing(monkeypatch):
    ass = subtitles._build_ass([(0.0, 0.5, "hi")], source_label=None)
    assert "Source: " not in ass


# --- timestamp + events (pure) ---------------------------------------------------------

def test_format_ts():
    assert subtitles._format_ts(0) == "0:00:00.00"
    assert subtitles._format_ts(65.5) == "0:01:05.50"
    assert subtitles._format_ts(3661.23) == "1:01:01.23"


def test_build_events_holds_until_next_word(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")  # per-word for this timing check
    words = [(0.0, 0.3, "a"), (0.5, 0.9, "b"), (1.0, 1.4, "c")]
    events = subtitles._build_events(words)
    assert events[0] == (0.0, 0.5, "a")   # held until 'b' starts
    assert events[1] == (0.5, 1.0, "b")   # held until 'c' starts
    assert events[2] == (1.0, 1.4, "c")   # last keeps its own end


def test_build_events_min_duration_when_overlap(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    words = [(1.0, 1.0, "x")]
    (start, end, _), = subtitles._build_events(words)
    assert end > start  # never zero-length


def test_build_events_groups_and_cleans(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "2")
    # whisper split "mythos-level" → "mythos", "-level"; grouped + cleaned
    words = [(0.0, 0.3, "mythos"), (0.3, 0.6, "-level"), (0.7, 1.0, "AI")]
    events = subtitles._build_events(words)
    assert events[0][2] == "mythos level"   # 2-word group, '-' cleaned off
    assert events[1][2] == "AI"


def test_build_ass_has_style(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    ass = subtitles._build_ass([(0.0, 0.3, "Hello"), (0.4, 0.8, "world")])
    assert "[V4+ Styles]" in ass and "Style: Karaoke" in ass
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert ass.count("Dialogue:") == 2
    assert "Hello" in ass and "world" in ass


def test_karaoke_line_has_kf_tags_and_words():
    words = [(0.0, 0.40, "Oil"), (0.40, 0.90, "export"), (0.90, 1.50, "wars")]
    line = subtitles._karaoke_line(words)
    assert line.count("\\kf") == 3            # one fill tag per word
    assert "Oil" in line and "export" in line and "wars" in line
    assert "\\kf40" in line                   # first word fill ~ next_start - start = 40cs


def test_build_ass_uses_configured_font(monkeypatch):
    monkeypatch.setenv("CAPTION_FONT", "Montserrat")
    words = [(0.0, 0.4, "Hi"), (0.4, 0.8, "there")]
    ass = subtitles._build_ass(words)
    assert "Montserrat" in ass
    assert "Karaoke" in ass            # the karaoke style exists
    assert "{\\kf" in ass              # events use karaoke fill


# --- on-screen key-point text cards ----------------------------------------------------

def test_card_events_distributes_sparsely():
    events = subtitles._card_events(["A", "B", "C"], total_dur=12.0, start_after=2.0, card_dur=1.8)
    assert len(events) == 3
    for (s, e, t), p in zip(events, ["A", "B", "C"]):
        assert 2.0 <= s < e <= 12.0
        assert e - s <= 1.81
        assert t == p
    assert events[0][0] < events[1][0] < events[2][0]   # ascending, non-overlapping order


def test_card_events_empty_when_no_points_or_no_time():
    assert subtitles._card_events([], 10.0, 2.0, 1.8) == []
    assert subtitles._card_events(["A"], 2.0, 2.0, 1.8) == []   # no span after the hook window


def test_build_ass_includes_text_cards(monkeypatch):
    monkeypatch.delenv("ENABLE_TEXT_CARDS", raising=False)  # default on
    words = [(0.0, 0.4, "Reusable"), (0.4, 0.9, "rockets"), (5.0, 5.4, "cut"), (5.4, 6.0, "costs")]
    ass = subtitles._build_ass(words, key_points=["First in Asia", "30% cheaper"], total_dur=6.0)
    assert "Style: Card" in ass
    assert "FIRST IN ASIA" in ass            # card text uppercased
    assert ass.count(",Card,,") == 2          # two card dialogues


def test_build_ass_omits_cards_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_TEXT_CARDS", "0")
    ass = subtitles._build_ass([(0.0, 0.4, "Hi")], key_points=["First in Asia"], total_dur=5.0)
    assert ",Card,," not in ass


def test_ass_escape_strips_braces():
    assert subtitles._ass_escape("  {evil}\\path\n ") == "evilpath"


# --- frame-1 hook banner ---------------------------------------------------------------

def test_hook_banner_uppercases_strips_emoji_and_wraps():
    # emoji + variation selector stripped; UPPERCASE; wrapped to <=16 chars/line with \N
    out = subtitles._hook_banner_text("Oil Export Wars \U0001f6e2️")
    assert "\U0001f6e2" not in out and "OIL EXPORT" in out
    for line in out.split("\\N"):
        assert len(line) <= 16
    assert out == out.upper()


def test_hook_banner_empty_when_nothing_renderable():
    assert subtitles._hook_banner_text("\U0001f600\U0001f525") == ""  # all emoji → nothing
    assert subtitles._hook_banner_text("") == ""


def test_build_ass_includes_hook_banner_when_given(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    monkeypatch.delenv("ENABLE_HOOK_CAPTION", raising=False)  # default on
    ass = subtitles._build_ass([(0.0, 0.3, "Hello")], hook_text="Oil Export Wars")
    assert "Style: Hook" in ass
    assert ",Hook,," in ass                       # the hook Dialogue line
    assert "OIL EXPORT" in ass                     # banner text present, uppercased
    assert ass.count("Dialogue:") == 2             # 1 hook + 1 word


def test_build_ass_omits_hook_when_disabled(monkeypatch):
    monkeypatch.setenv("CAPTION_WORDS", "1")
    monkeypatch.setenv("ENABLE_HOOK_CAPTION", "0")
    ass = subtitles._build_ass([(0.0, 0.3, "Hello")], hook_text="Oil Export Wars")
    assert ",Hook,," not in ass and ass.count("Dialogue:") == 1


# --- burn_captions orchestration (mocked transcription + ffmpeg) -----------------------

def test_burn_captions_writes_ass_and_calls_burn(monkeypatch, tmp_path):
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00" * 100)
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00" * 100)
    out = tmp_path / "out.mp4"

    monkeypatch.setattr(subtitles, "_transcribe_words",
                        lambda p: [(0.0, 0.3, "Reusable"), (0.3, 0.7, "rockets")])
    burned = {}

    def fake_burn(video_path, ass_path, out_path, cards=None):
        burned["ass"] = ass_path
        burned["cards"] = cards
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 5000)  # pretend ffmpeg wrote the captioned reel
    monkeypatch.setattr(subtitles, "_burn", fake_burn)

    result = subtitles.burn_captions(str(video), str(audio), str(out))
    assert result == str(out) and os.path.exists(result)
    assert os.path.exists(burned["ass"])
    with open(burned["ass"], encoding="utf-8") as f:
        content = f.read()
    assert "Reusable" in content and "rockets" in content


def test_burn_captions_empty_transcription_raises(monkeypatch, tmp_path):
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00")
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00")
    monkeypatch.setattr(subtitles, "_transcribe_words", lambda p: [])
    with pytest.raises(RuntimeError, match="no words"):
        subtitles.burn_captions(str(video), str(audio), str(tmp_path / "o.mp4"))


def test_burn_captions_missing_inputs_raise(tmp_path):
    with pytest.raises(ValueError, match="video not found"):
        subtitles.burn_captions(str(tmp_path / "no.mp4"), str(tmp_path / "no.mp3"),
                                str(tmp_path / "o.mp4"))


# --- PIL graphic stat cards (optional, ENABLE_GRAPHIC_CARDS) ---------------------------

def test_graphic_cards_off_by_default(monkeypatch, tmp_path):
    """Default OFF: the ASS text cards already ship, so this is an opt-in look change."""
    monkeypatch.delenv("ENABLE_GRAPHIC_CARDS", raising=False)
    assert subtitles._render_graphic_cards(["Rs 2 crore"], 20.0, str(tmp_path)) == []


def test_graphic_cards_render_pngs_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_GRAPHIC_CARDS", "true")
    monkeypatch.setenv("CARD_SECONDS", "1.8")
    monkeypatch.setenv("HOOK_SECONDS", "1.8")
    cards = subtitles._render_graphic_cards(["First in Asia", "30% cheaper"], 20.0, str(tmp_path))
    assert len(cards) == 2
    for start, end, png in cards:
        assert os.path.isfile(png) and os.path.getsize(png) > 500
        assert 1.8 <= start < end <= 20.0


def test_graphic_cards_fall_back_when_render_fails(monkeypatch, tmp_path):
    """A card renderer breaking must cost us the cards, never the captions (rules 11, 14)."""
    monkeypatch.setenv("ENABLE_GRAPHIC_CARDS", "true")
    from src import graphics
    monkeypatch.setattr(graphics, "create_stat_card",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no font")))
    assert subtitles._render_graphic_cards(["boom"], 20.0, str(tmp_path)) == []


def test_ass_omits_text_cards_when_png_cards_are_used(monkeypatch, tmp_path):
    """Both treatments at once would double-draw, so exactly one must own the key points."""
    monkeypatch.setenv("ENABLE_GRAPHIC_CARDS", "true")
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00" * 100)
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(subtitles, "_transcribe_words",
                        lambda p: [(0.0, 4.0, "hi"), (4.0, 9.0, "there")])
    seen = {}

    def fake_burn(video_path, ass_path, out_path, cards=None):
        seen["cards"] = cards
        seen["ass"] = open(ass_path, encoding="utf-8").read()
        open(out_path, "wb").write(b"\x00" * 5000)
    monkeypatch.setattr(subtitles, "_burn", fake_burn)

    subtitles.burn_captions(str(video), str(audio), str(tmp_path / "o.mp4"),
                            key_points=["Rs 2 crore"])
    assert seen["cards"], "PNG cards should have been rendered"
    assert ",Card,," not in seen["ass"], "ASS must not also draw the key-point cards"


def test_burn_captions_retries_with_text_cards_when_overlay_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_GRAPHIC_CARDS", "true")
    video = tmp_path / "in.mp4"; video.write_bytes(b"\x00" * 100)
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(subtitles, "_transcribe_words",
                        lambda p: [(0.0, 4.0, "hi"), (4.0, 9.0, "there")])
    calls = []

    def flaky_burn(video_path, ass_path, out_path, cards=None):
        calls.append(cards)
        if cards:
            raise RuntimeError("overlay filtergraph failed")
        open(out_path, "wb").write(b"\x00" * 5000)
    monkeypatch.setattr(subtitles, "_burn", flaky_burn)

    out = subtitles.burn_captions(str(video), str(audio), str(tmp_path / "o.mp4"),
                                  key_points=["Rs 2 crore"])
    assert os.path.exists(out)
    assert len(calls) == 2 and calls[0] and calls[1] is None
    # the retry's ASS carries the cards back as text, so the fallback is not feature-poorer
    fallback_ass = [p for p in os.listdir(tmp_path) if p.endswith("_text.ass")]
    assert fallback_ass, "expected a text-card fallback ASS to have been written"
    assert ",Card,," in open(os.path.join(tmp_path, fallback_ass[0]), encoding="utf-8").read()


def test_burn_builds_overlay_filtergraph_for_cards(monkeypatch, tmp_path):
    ass = tmp_path / "c.ass"; ass.write_text("[Events]\n", encoding="utf-8")
    video = tmp_path / "v.mp4"; video.write_bytes(b"\x00")
    png = tmp_path / "card_0.png"; png.write_bytes(b"\x89PNG")
    captured = {}

    class _P:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(subtitles.subprocess, "run",
                        lambda cmd, **kw: (captured.update(cmd=cmd), _P())[1])
    subtitles._burn(str(video), str(ass), str(tmp_path / "o.mp4"),
                    cards=[(2.0, 3.8, str(png))])
    cmd = captured["cmd"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "-loop" in cmd and "card_0.png" in cmd  # basename: no Windows path escaping
    assert "ass=c.ass:fontsdir=." in graph
    assert "overlay=(W-w)/2:(H-h)/2:enable='between(t,2.000,3.800)'" in graph
    assert "-shortest" in cmd, "looped stills would otherwise extend the reel"


def test_burn_uses_plain_vf_when_no_cards(monkeypatch, tmp_path):
    """The shipping path must stay a simple -vf ass burn."""
    ass = tmp_path / "c.ass"; ass.write_text("[Events]\n", encoding="utf-8")
    video = tmp_path / "v.mp4"; video.write_bytes(b"\x00")
    captured = {}

    class _P:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(subtitles.subprocess, "run",
                        lambda cmd, **kw: (captured.update(cmd=cmd), _P())[1])
    subtitles._burn(str(video), str(ass), str(tmp_path / "o.mp4"))
    cmd = captured["cmd"]
    assert "-filter_complex" not in cmd and "-shortest" not in cmd
    assert cmd[cmd.index("-vf") + 1] == f"ass=c.ass:fontsdir=.,{subtitles.BT709_TAGS}"


# --- live: real whisper + real burn ----------------------------------------------------

def test_live_caption_burn(monkeypatch, tmp_path):
    """Real faster-whisper (tiny) + FFmpeg burn on a real reel. Skips if unavailable."""
    monkeypatch.setenv("WHISPER_MODEL", "tiny")  # smaller/faster for CI
    from src import assembly, visuals, voice

    try:
        ffprobe = assembly._ffprobe()
        audio, dur = voice.synthesize(
            "Reusable rockets could cut India's launch costs. Here is why it matters.",
            str(tmp_path),
        )
        clips = visuals.fetch_broll(["rocket", "city skyline"], target_seconds=dur,
                                    out_dir=str(tmp_path))
        reel = assembly.assemble(audio, clips, str(tmp_path / "reel.mp4"))
        # pass a hook so libass really renders the frame-1 Hook style + Layer-1 dialogue
        out = subtitles.burn_captions(reel, audio, str(tmp_path / "captioned.mp4"),
                                      hook_text="Reusable Rocket SHOCK",
                                      key_points=["First in Asia", "Cheaper Launches"])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"live caption render unavailable (offline / no FFmpeg / model): {e}")

    assert os.path.exists(out) and os.path.getsize(out) > 50_000
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-of", "default=nw=1", out],
        capture_output=True, text=True,
    ).stdout
    assert "width=1080" in probe and "height=1920" in probe and "codec_type=audio" in probe
    assert abs(assembly.probe_duration(out) - dur) < 1.6


def test_burned_text_strips_delivery_tags():
    """A tag that leaks into the title or a key_point would be BURNED onto the video as
    literal '[SARCASTIC]'. The scriptwriter is now told to emit tags, so this must be guarded
    at the render surface, not just hoped away in the prompt."""
    banner = subtitles._hook_banner_text("[SARCASTIC] Gas Rule Explained")
    assert "[" not in banner and "SARCASTIC" not in banner
    assert "GAS" in banner and "EXPLAINED" in banner

    card = subtitles._hook_banner_text("[dry] Rs 2 crore", max_chars=18, max_lines=2)
    assert "[" not in card and "DRY" not in card
    assert "RS 2 CRORE" in card


def test_burned_text_survives_a_tag_only_string():
    """All-tag input must yield nothing to draw rather than an empty box."""
    assert subtitles._hook_banner_text("[sarcastic]") == ""


# --- number tokens (2026-09-03) -----------------------------------------------------------
# Measured on real narration: faster-whisper emits "1,270" as the two word tokens '1' and ',270'
# (and "2.4" as '2' and '.4'). _clean_caption_word then strips the leading punctuation, so the
# burned captions read "authority 1" / "270 people died" and "and 2 4" — a news channel showing
# 270 deaths when the script says 1,270. The audio is correct; only the caption layer was wrong.

def test_merge_number_tokens_rejoins_a_thousands_separator():
    words = [(0.0, 0.4, "1"), (0.4, 0.9, ",270"), (0.9, 1.3, "people")]
    assert subtitles._merge_number_tokens(words) == [(0.0, 0.9, "1,270"), (0.9, 1.3, "people")]


def test_merge_number_tokens_rejoins_a_decimal_point():
    words = [(0.0, 0.3, "2"), (0.3, 0.7, ".4"), (0.7, 1.1, "billion")]
    assert subtitles._merge_number_tokens(words) == [(0.0, 0.7, "2.4"), (0.7, 1.1, "billion")]


def test_merge_number_tokens_leaves_sentence_punctuation_alone():
    """'likes.' does not end in a digit, so a following '.4' must not be glued onto it."""
    words = [(0.0, 0.5, "likes."), (0.5, 0.9, ".4"), (0.9, 1.2, "percent")]
    assert subtitles._merge_number_tokens(words) == words


def test_merge_number_tokens_handles_a_number_in_three_groups():
    words = [(0.0, 0.2, "1"), (0.2, 0.4, ",270"), (0.4, 0.6, ",500")]
    assert subtitles._merge_number_tokens(words) == [(0.0, 0.6, "1,270,500")]


def test_captions_keep_a_number_whole(monkeypatch):
    """End to end through the caption grouping: the burned text must never split a figure."""
    monkeypatch.setenv("CAPTION_WORDS", "3")
    words = subtitles._merge_number_tokens(
        [(0.0, 0.5, "authority."), (0.5, 0.7, "1"), (0.7, 1.0, ",270"),
         (1.0, 1.4, "people"), (1.4, 1.8, "died")])
    texts = [t for _s, _e, t in subtitles._build_events(words)]
    assert texts == ["authority 1,270 people", "died"]


# --- 2026-09-27 audit: script-aligned text, grouping, banner fitting --------------------------

def _w(*pairs):
    """[(start, end, word)] at 0.3 s a word."""
    return [(i * 0.3, i * 0.3 + 0.25, w) for i, w in enumerate(pairs)]


def test_captions_show_the_scripts_words_at_the_heard_timing():
    """10 published reels: 7.6% of burned words differed from the approved script."""
    heard = _w("The", "ministry", "signed", "a", "769", "croned", "defense", "deal", "on",
               "Monday.", "On", "officially", "it", "is", "done.")
    script = "The ministry signed a 769-crore defense deal on Monday. Unofficially, it is done."
    out = subtitles._align_to_script(heard, script)
    assert [w[2] for w in out] == script.split()
    assert out[0][0] == heard[0][0] and out[-1][1] == heard[-1][1]
    assert out[4][0] == heard[4][0] and out[4][1] == heard[5][1]  # one word over both timings


def test_a_split_percentage_is_rejoined_before_captioning():
    heard = subtitles._merge_number_tokens(_w("a", "3", "-5", "%", "drop"))
    assert [w[2] for w in heard] == ["a", "3-5%", "drop"]


def test_delivery_tags_never_reach_the_captions():
    out = subtitles._align_to_script(_w("But", "here"), "[serious] But here")
    assert [w[2] for w in out] == ["But", "here"]


def test_asr_is_kept_when_the_script_is_not_what_was_spoken():
    heard = _w("completely", "different", "narration", "here")
    assert subtitles._align_to_script(heard, "nothing alike at all today") == heard


def test_captions_never_straddle_a_sentence_end():
    """'matters When news' and 'just drama It' were burned on the 09-22 Short."""
    groups = subtitles._caption_groups(_w("it", "matters.", "When", "news", "outlets"), 3)
    assert [[w[2] for w in g] for g in groups] == [["it", "matters."], ["When", "news", "outlets"]]


def test_a_caption_never_runs_past_the_safe_width():
    """'Germany's ThyssenKrupp Marine' drew 1130 px wide on a 1080 px frame."""
    groups = subtitles._caption_groups(_w("Germany's", "ThyssenKrupp", "Marine"), 3)
    for g in groups:
        assert subtitles._caption_px(" ".join(w[2] for w in g)) <= subtitles._MAX_CAPTION_PX


def test_the_hook_banner_keeps_every_word():
    """20 of the last 40 banners were cut mid-phrase ('...CLAIM: WHY IT')."""
    title = "Trump's One Shot Iran Claim: Why It Matters"
    banner = subtitles._hook_banner_text(title)
    for word in title.upper().split():
        assert word in banner, word
    assert banner.count("\\N") <= 2


def test_a_short_hook_banner_keeps_its_full_size():
    assert "\\fs" not in subtitles._hook_banner_text("Rupee Hits Record Low")


def test_the_source_line_sits_above_the_shorts_bottom_ui():
    header = subtitles._ass_header()
    source = next(ln for ln in header.splitlines() if ln.startswith("Style: Source"))
    assert int(source.split(",")[-2]) >= 400


def test_a_long_seven_word_title_still_fits_without_an_ellipsis():
    """Local render 2026-09-27: this title needed a fourth line at the old smallest size."""
    banner = subtitles._hook_banner_text("Networks Boycott Trump: An Unprecedented Media Blackout")
    assert "BLACKOUT" in banner and "…" not in banner


def test_a_caption_is_held_across_a_short_breath():
    words = [(0.0, 0.3, "One"), (0.3, 0.6, "two."), (0.9, 1.2, "Three."), (3.0, 3.3, "four.")]
    ass = subtitles._build_ass(words)
    events = [ln for ln in ass.splitlines() if ln.startswith("Dialogue: 0,")]
    assert events[0].split(",")[2] == subtitles._format_ts(0.9)   # held to the next caption
    assert events[1].split(",")[2] == subtitles._format_ts(1.2)   # a real pause still clears


def test_a_card_appears_when_its_point_is_spoken():
    words = [(i * 0.5, i * 0.5 + 0.4, w) for i, w in
             enumerate("the house passed a bill with tariffs of 100 percent on buyers".split())]
    cards = subtitles._card_events(["100% TARIFFS"], 10.0, 1.0, 1.8, words)
    assert cards and cards[0][0] == words[6][0]   # 'tariffs' is word 6
