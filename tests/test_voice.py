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


# --- inline delivery tags (per-engine filtering) ----------------------------------------

def test_clean_tts_text_strips_every_tag():
    assert voice._clean_tts_text("A [sarcastic] b <sfx:whoosh> c") == "A b c"


def test_pause_markup_keeps_only_pause_tags():
    out = voice._pause_markup("Well [sarcastic] that worked. [pause long] Sure it did.")
    assert "[pause long]" in out
    assert "[sarcastic]" not in out


def test_style_text_keeps_only_style_tags():
    out = voice._style_text("Well [sarcastic] that worked. [pause long] Sure.")
    assert "[sarcastic]" in out
    assert "[pause long]" not in out


def test_invented_tags_are_stripped_not_forwarded():
    """An LLM inventing a tag must never reach an API (400) or be read aloud."""
    assert voice._pause_markup("a [explodes] b") == "a b"
    assert voice._style_text("a [explodes] b") == "a b"


@pytest.mark.parametrize("tag", ["serious", "curious", "whispers", "tired", "mischievously"])
def test_documented_expressive_tags_reach_the_engine(tag, monkeypatch):
    """Widened 2026-08-07 to Google's documented audio tags. Without these in the allow-list the
    scriptwriter can emit them and the filter silently eats them."""
    monkeypatch.setenv("MAX_STYLE_TAGS", "3")
    assert f"[{tag}]" in voice._style_text(f"Before. [{tag}] After.")


@pytest.mark.parametrize("tag", ["excited", "amazed", "giggles", "crying", "panicked",
                                 "trembling", "gasp", "shouting"])
def test_hype_and_melodrama_tags_stay_excluded(tag):
    """These ARE documented and would work — they are excluded on editorial grounds, so an
    accidental re-widening should fail here rather than ship.

    Hype ([excited]/[amazed]/[giggles]) fights the deadpan register; melodrama over real events
    ([crying]/[panicked]/[trembling]/[gasp]/[shouting]) is how a news channel drifts into the
    tragedy exploitation rule 6 excludes.
    """
    assert f"[{tag}]" not in voice._style_text(f"Before. [{tag}] After.")


def test_tag_counts_are_capped(monkeypatch):
    monkeypatch.setenv("MAX_PAUSE_TAGS", "2")
    text = "a [pause] b [pause] c [pause] d [pause] e"
    assert voice._pause_markup(text).count("[pause]") == 2


def test_has_pause_tag():
    assert voice._has_pause_tag("a [pause long] b") is True
    assert voice._has_pause_tag("a [sarcastic] b") is False


def test_tags_never_reach_edge_tts(monkeypatch, tmp_path):
    """edge-tts has no tag support, so a tag reaching it would be read aloud."""
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    seen = {}

    def _fake_edge(text, out_path, voice_name, rate):
        seen["text"] = text
        with open(out_path, "wb") as f:
            f.write(b"\x00")
        return 2.0

    monkeypatch.setattr(voice, "_synthesize_edge_tts", _fake_edge)
    voice.synthesize("Well [sarcastic] that worked. [pause long] Sure.", str(tmp_path))
    assert "[" not in seen["text"]
    assert seen["text"] == "Well that worked. Sure."


def test_tags_never_reach_kokoro(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "kokoro")
    seen = {}

    def _fake_kokoro(text, out_path):
        seen["text"] = text
        with open(out_path, "wb") as f:
            f.write(b"\x00")
        return 2.0

    monkeypatch.setattr(voice, "_synthesize_kokoro", _fake_kokoro)
    voice.synthesize("Sure. [sarcastic] Brilliant.", str(tmp_path))
    assert "[" not in seen["text"]


def test_tags_only_body_is_treated_as_empty(tmp_path):
    """Tags are stage direction, not narration — a body of only tags has nothing to say."""
    with pytest.raises(ValueError, match="empty script_body"):
        voice.synthesize("[pause] [sarcastic]", str(tmp_path))


# --- Chirp 3 HD markup + speaking rate --------------------------------------------------

def _google_ok(monkeypatch, captured, seconds: float = 0.5):
    """Patch requests.post to a 200 with a real tiny WAV, capturing the request body."""
    resp = mock.Mock()
    resp.status_code = 200
    resp.json = mock.Mock(return_value={"audioContent": _fake_wav_b64(seconds)})

    def _post(url, params=None, json=None, timeout=None):
        captured["body"] = json
        return resp

    monkeypatch.setattr(voice.requests, "post", _post)


def test_chirp_uses_markup_when_pause_tags_present(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert "markup" in cap["body"]["input"]
    assert "[pause long]" in cap["body"]["input"]["markup"]


def test_chirp_uses_plain_text_without_pause_tags(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("It worked. Somehow.", str(tmp_path))
    assert cap["body"]["input"] == {"text": "It worked. Somehow."}


def test_chirp_strips_style_tags_from_markup(monkeypatch, tmp_path):
    """Style tags are Gemini's; sending them to Chirp would have them read aloud."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("Sure. [sarcastic] [pause] Great.", str(tmp_path))
    assert "[sarcastic]" not in cap["body"]["input"]["markup"]
    assert "[pause]" in cap["body"]["input"]["markup"]


def test_non_chirp_voice_never_gets_markup(monkeypatch, tmp_path):
    """`markup` may not be used with any voice other than Chirp 3 HD."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Neural2-A")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert "text" in cap["body"]["input"]
    assert "markup" not in cap["body"]["input"]


def test_pause_markup_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    monkeypatch.setenv("ENABLE_PAUSE_MARKUP", "false")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert "text" in cap["body"]["input"]


def test_speaking_rate_clamped_and_validated(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "9")
    assert voice._speaking_rate() == 2.0
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "0.01")
    assert voice._speaking_rate() == 0.25
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "1.1")
    assert voice._speaking_rate() == pytest.approx(1.1)
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "junk")
    assert voice._speaking_rate() is None
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "")
    assert voice._speaking_rate() is None


def test_speaking_rate_included_only_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    monkeypatch.delenv("GOOGLE_TTS_SPEAKING_RATE", raising=False)
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("Hello.", str(tmp_path))
    assert "speakingRate" not in cap["body"]["audioConfig"]

    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "1.15")
    voice._synthesize_google("Hello.", str(tmp_path))
    assert cap["body"]["audioConfig"]["speakingRate"] == pytest.approx(1.15)


def test_markup_rejection_retries_as_plain_text(monkeypatch, tmp_path):
    """A markup surprise must cost us the timing, never the voice."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    calls = []
    good = mock.Mock()
    good.status_code = 200
    good.json = mock.Mock(return_value={"audioContent": _fake_wav_b64(0.5)})
    bad = mock.Mock()
    bad.status_code = 400
    bad.text = "markup not supported for this voice"

    def _post(url, params=None, json=None, timeout=None):
        calls.append(json["input"])
        return bad if "markup" in json["input"] else good

    monkeypatch.setattr(voice.requests, "post", _post)
    path, dur = voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert os.path.exists(path) and dur > 0
    assert len(calls) == 2
    assert "markup" in calls[0] and "text" in calls[1]


def test_plain_text_failure_does_not_double_post(monkeypatch, tmp_path):
    """Without markup there is nothing to retry — one attempt, then fail over (rule 13)."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    calls = []
    bad = mock.Mock()
    bad.status_code = 403
    bad.text = "blocked"

    def _post(url, params=None, json=None, timeout=None):
        calls.append(json["input"])
        return bad

    monkeypatch.setattr(voice.requests, "post", _post)
    with pytest.raises(RuntimeError, match="403"):
        voice._synthesize_google("No tags here.", str(tmp_path))
    assert len(calls) == 1


# --- Gemini Developer API TTS engine ----------------------------------------------------

def _fake_genai(monkeypatch, captured, pcm: bytes | None = None):
    """Patch google.genai.Client with a stub, capturing generate_content kwargs.

    `_synthesize_gemini` imports genai inside the function, so patching the module attribute
    is what the call actually resolves.
    """
    if pcm is None:
        pcm = b"\x00\x00" * 24000  # 1.0s of silence at 24 kHz, 16-bit mono

    inline = type("Inline", (), {"data": pcm})()
    part = type("Part", (), {"inline_data": inline})()
    content = type("Content", (), {"parts": [part]})()
    candidate = type("Candidate", (), {"content": content})()
    resp = type("Resp", (), {"candidates": [candidate]})()

    class _Models:
        def generate_content(self, **kw):
            captured.update(kw)
            return resp

    class _Client:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)


def test_gemini_tts_writes_wav_and_measures_duration(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    cap = {}
    _fake_genai(monkeypatch, cap)
    path, dur = voice._synthesize_gemini("Sure. [sarcastic] That'll work.", str(tmp_path))
    assert path.endswith(".wav") and os.path.getsize(path) > 44
    assert dur == pytest.approx(1.0, abs=0.05)
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


def test_gemini_tts_wraps_raw_pcm_so_it_is_readable(monkeypatch, tmp_path):
    """The API returns raw PCM, not a WAV container — unwrapped it is unreadable."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    _fake_genai(monkeypatch, {})
    path, _ = voice._synthesize_gemini("hi there", str(tmp_path))
    with open(path, "rb") as f:
        assert f.read(4) == b"RIFF"  # a real container, not bare samples


def test_gemini_tts_passes_style_prompt_and_keeps_style_tags(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("VOICE_STYLE_PROMPT", "Dry and deadpan.")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("Sure. [sarcastic] That'll work. [pause] Really.", str(tmp_path))
    assert "Dry and deadpan." in cap["contents"]
    assert "[sarcastic]" in cap["contents"]
    assert "[pause]" not in cap["contents"]  # pause tags belong to Chirp


def _fake_genai_failing(monkeypatch, captured, fail_models: dict[str, Exception]):
    """Like _fake_genai, but raises for the named models. Records every model attempted."""
    inline = type("Inline", (), {"data": b"\x00\x00" * 24000})()
    part = type("Part", (), {"inline_data": inline})()
    content = type("Content", (), {"parts": [part]})()
    resp = type("Resp", (), {"candidates": [type("C", (), {"content": content})()]})()

    class _Models:
        def generate_content(self, **kw):
            captured.setdefault("tried", []).append(kw["model"])
            if kw["model"] in fail_models:
                raise fail_models[kw["model"]]
            return resp

    class _Client:
        def __init__(self, api_key=None):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)


def test_gemini_tts_falls_back_to_the_stable_model_on_a_transient_error(monkeypatch, tmp_path):
    """The channel's voice (Zubenelgenubi) exists ONLY on the Gemini engine, so a preview-model
    blip must not fall straight through to Chirp and change how the channel sounds.

    Not hypothetical: gemini-3.1-flash-tts-preview returned 503 "high demand" on three probes
    across ~40 minutes on 2026-08-07.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    cap = {}
    _fake_genai_failing(monkeypatch, cap, {
        "gemini-3.1-flash-tts-preview": RuntimeError("503 UNAVAILABLE. high demand")})

    path, dur = voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["tried"] == ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    assert path.endswith(".wav") and dur == pytest.approx(1.0, abs=0.05)


def test_gemini_tts_does_not_retry_a_non_transient_error(monkeypatch, tmp_path):
    """A 400 means the REQUEST is wrong — the second model would reject it identically, so
    retrying just burns time before the engine chain can do its job."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    cap = {}
    _fake_genai_failing(monkeypatch, cap, {
        "gemini-3.1-flash-tts-preview": RuntimeError("400 INVALID_ARGUMENT")})

    with pytest.raises(RuntimeError, match="400"):
        voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["tried"] == ["gemini-3.1-flash-tts-preview"], "must not try a second model"


def test_gemini_tts_does_not_double_call_when_already_on_the_stable_model(monkeypatch, tmp_path):
    """The default IS the stable model — no free-tier request may be spent twice on it."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.delenv("GEMINI_TTS_MODEL", raising=False)
    cap = {}
    _fake_genai_failing(monkeypatch, cap, {
        "gemini-2.5-flash-preview-tts": RuntimeError("503 UNAVAILABLE")})

    with pytest.raises(RuntimeError):
        voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["tried"] == ["gemini-2.5-flash-preview-tts"]


def test_quota_errors_are_not_treated_as_transient():
    """429 shares the same daily reset across models, so re-asking wastes the reel's time."""
    assert voice._is_transient(RuntimeError("503 UNAVAILABLE")) is True
    assert voice._is_transient(RuntimeError("500 INTERNAL")) is True
    assert voice._is_transient(RuntimeError("429 RESOURCE_EXHAUSTED")) is False
    assert voice._is_transient(RuntimeError("400 INVALID_ARGUMENT")) is False


def test_gemini_tts_uses_configured_model_and_voice(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-2.5-pro-preview-tts")
    monkeypatch.setenv("GEMINI_TTS_VOICE", "Puck")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["model"] == "gemini-2.5-pro-preview-tts"
    vc = cap["config"].speech_config.voice_config.prebuilt_voice_config
    assert vc.voice_name == "Puck"


def test_gemini_tts_defaults_to_the_free_flash_model(monkeypatch, tmp_path):
    """Pro has no free tier; the default must not start spending on its own."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.delenv("GEMINI_TTS_MODEL", raising=False)
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["model"] == "gemini-2.5-flash-preview-tts"


def test_gemini_tts_requests_audio_modality(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi there", str(tmp_path))
    assert "AUDIO" in cap["config"].response_modalities


def test_gemini_tts_prefers_dedicated_key(monkeypatch, tmp_path):
    """A separate key lets TTS avoid starving grounded ideation's RPD (rule 13)."""
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    monkeypatch.setenv("GEMINI_TTS_API_KEY", "dedicated")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["api_key"] == "dedicated"


def test_gemini_tts_falls_back_to_shared_key(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    monkeypatch.delenv("GEMINI_TTS_API_KEY", raising=False)
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi there", str(tmp_path))
    assert cap["api_key"] == "shared"


def test_gemini_tts_missing_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_TTS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        voice._synthesize_gemini("hi there", str(tmp_path))


def test_gemini_tts_raises_on_empty_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    _fake_genai(monkeypatch, {}, pcm=b"")
    with pytest.raises(RuntimeError, match="empty audio"):
        voice._synthesize_gemini("hi there", str(tmp_path))


def test_gemini_tts_raises_on_unexpected_response_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")

    class _Models:
        def generate_content(self, **kw):
            return type("Resp", (), {"candidates": []})()

    class _Client:
        def __init__(self, api_key=None):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)
    with pytest.raises(RuntimeError, match="unexpected response shape"):
        voice._synthesize_gemini("hi there", str(tmp_path))


def test_gemini_absent_from_chain_when_another_engine_is_primary(monkeypatch, tmp_path):
    """Gemini is kept out of _ENGINE_ORDER, so selecting a different primary excludes it
    ENTIRELY rather than leaving it as a silent fallback. Anyone who moves off Gemini (to avoid
    a preview model, or a quota, or the style prompt) must actually get what they asked for."""
    monkeypatch.setenv("VOICE_ENGINE", "google")
    called = []
    monkeypatch.setattr(voice, "_engine_gemini", lambda *a: called.append(1) or ("x.wav", 1.0))
    monkeypatch.setattr(voice, "_engine_google", lambda *a: ("ok.wav", 2.0))
    voice.synthesize("hello there", str(tmp_path))
    assert called == []


def test_gemini_selected_heads_the_chain_and_falls_soft(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "gemini")
    order = []

    def _boom(*_a):
        order.append("gemini")
        raise RuntimeError("quota exhausted")

    monkeypatch.setattr(voice, "_engine_gemini", _boom)
    monkeypatch.setattr(voice, "_engine_google",
                        lambda *a: (order.append("google"), ("ok.wav", 2.0))[1])
    path, dur = voice.synthesize("hello there", str(tmp_path))
    assert order == ["gemini", "google"]
    assert path == "ok.wav"


def test_gemini_tts_alias_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "gemini-tts")
    order = []
    monkeypatch.setattr(voice, "_engine_gemini",
                        lambda *a: (order.append("gemini"), ("ok.wav", 2.0))[1])
    voice.synthesize("hello there", str(tmp_path))
    assert order == ["gemini"]


def test_live_gemini_tts(tmp_path):
    """Real Gemini TTS. Gated by its own flag: the Pro model has NO free tier, so this must
    never run unattended in CI."""
    if os.environ.get("GEMINI_TTS_LIVE_TEST") != "1":
        pytest.skip("set GEMINI_TTS_LIVE_TEST=1 to run (may bill on non-free models)")
    path, dur = voice._synthesize_gemini(
        "Another committee. [sarcastic] Groundbreaking. Here's why it actually matters.",
        str(tmp_path))
    assert os.path.getsize(path) > 10_000
    assert 1.0 < dur < 30.0


def test_default_engine_and_voice_are_the_chosen_ones(monkeypatch, tmp_path):
    """The voice identity was picked by ear (Zubenelgenubi, 'Casual') and the engine that carries
    it is Gemini. Pinned so neither silently drifts back to an incidental default."""
    for k in ("VOICE_ENGINE", "GEMINI_TTS_VOICE", "GEMINI_TTS_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    cap = {}
    _fake_genai(monkeypatch, cap)

    order = []
    real = voice._engine_gemini
    monkeypatch.setattr(voice, "_engine_gemini",
                        lambda t, d: (order.append("gemini"), real(t, d))[1])
    monkeypatch.setattr(voice, "_engine_google",
                        lambda *a: (order.append("google"), ("chirp.wav", 1.0))[1])

    voice.synthesize("Sure. [sarcastic] Brilliant.", str(tmp_path))
    assert order == ["gemini"], "Gemini must be the primary engine, not a fallback"
    vc = cap["config"].speech_config.voice_config.prebuilt_voice_config
    assert vc.voice_name == "Zubenelgenubi"
    assert cap["model"] == "gemini-2.5-flash-preview-tts"  # the free one


def test_chirp_is_still_the_first_fallback(monkeypatch, tmp_path):
    """Gemini TTS runs on a PREVIEW model; Chirp must catch it if that model goes away."""
    monkeypatch.delenv("VOICE_ENGINE", raising=False)
    order = []

    def _boom(*_a):
        order.append("gemini")
        raise RuntimeError("404 model not found")

    monkeypatch.setattr(voice, "_engine_gemini", _boom)
    monkeypatch.setattr(voice, "_engine_google",
                        lambda *a: (order.append("google"), ("chirp.wav", 2.0))[1])
    path, _ = voice.synthesize("hello there", str(tmp_path))
    assert order == ["gemini", "google"] and path == "chirp.wav"


# --- audit fixes: pause beats on the primary engine, byte guards -------------------------

def test_pause_tags_become_ellipses_for_gemini():
    """Pause tags are Chirp's native syntax, but Chirp is only the FALLBACK now. If they were
    merely stripped, the comic beat would vanish on the primary engine — so they degrade to an
    ellipsis, which every engine reads as a deliberate pause and none can read aloud."""
    out = voice._style_text("It happened. [pause long] Here's why it matters.")
    assert "[pause" not in out
    assert "..." in out
    assert out.startswith("It happened.")


def test_style_tags_survive_alongside_the_ellipsis():
    out = voice._style_text("Sure. [sarcastic] Brilliant. [pause] Anyway.")
    assert "[sarcastic]" in out
    assert "..." in out
    assert "[pause]" not in out


def test_chirp_still_gets_native_pause_markup():
    """Chirp's own markup is higher fidelity than an ellipsis, so it keeps the real tag."""
    out = voice._pause_markup("It happened. [pause long] Here's why.")
    assert "[pause long]" in out
    assert "..." not in out


def test_gemini_rejects_oversized_input(monkeypatch, tmp_path):
    """The API caps text and prompt at 4000 bytes each and 8000 combined. Fail before the call
    with a clear reason rather than eating an opaque 400 and burning a request."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("VOICE_STYLE_PROMPT", "x" * 4100)
    _fake_genai(monkeypatch, {})
    with pytest.raises(RuntimeError, match="too long"):
        voice._synthesize_gemini("hello there", str(tmp_path))


def test_gemini_rejects_oversized_script(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.delenv("VOICE_STYLE_PROMPT", raising=False)
    _fake_genai(monkeypatch, {})
    with pytest.raises(RuntimeError, match="too long"):
        voice._synthesize_gemini("word " * 1200, str(tmp_path))


def test_gemini_accepts_a_real_length_script(monkeypatch, tmp_path):
    """A 75-word script plus the default style prompt must sit comfortably inside the limits."""
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.delenv("VOICE_STYLE_PROMPT", raising=False)
    _fake_genai(monkeypatch, {})
    path, _ = voice._synthesize_gemini(" ".join(["word"] * 75), str(tmp_path))
    assert os.path.exists(path)
