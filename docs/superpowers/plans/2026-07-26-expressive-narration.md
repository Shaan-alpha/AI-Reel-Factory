# Expressive Narration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the narration actually *sound* dry-sarcastic by giving each TTS engine the control signals it natively understands, instead of sending plain text to all of them.

**Architecture:** The scriptwriter emits two families of inline bracket tags. `voice.py` filters them per-engine through one shared allow-list helper: pause tags become Chirp 3 HD `markup`, style tags pass through to a new Gemini Developer API TTS engine, and everything is stripped for edge-tts/Kokoro. The new engine joins the head of the existing fallback chain only when explicitly selected.

**Tech Stack:** Python 3.13, `google-genai==2.8.0` (already pinned), Google Cloud TTS v1 REST, `requests`, stdlib `wave`, pytest.

## Global Constraints

- **Spec:** [docs/superpowers/specs/2026-07-26-expressive-narration-design.md](../specs/2026-07-26-expressive-narration-design.md)
- **No self-attribution in any commit** (CLAUDE.md rule 3) — no `Co-Authored-By`, no AI credit.
- **Conventional commits**, logically grouped (rule 18).
- **Ships inert:** `VOICE_ENGINE` default stays `google`. With that default the Gemini engine must not appear in the chain at all.
- **No new dependency.** `google-genai==2.8.0` already exposes `SpeechConfig` / `VoiceConfig` / `PrebuiltVoiceConfig` / `GenerateContentConfig.speech_config` (verified 2026-07-26).
- **Fail-soft (rules 11, 14):** any engine failure logs and advances the chain; only *all* engines failing raises.
- **Billed path discipline (rule 13):** one attempt on Gemini TTS, no retry loops.
- **No DB schema change. No change to `production.py`, `publish_youtube.py`, `subtitles.py`, `db.py`.**
- Every task ends green on `python -m pytest -q` (baseline: **242 passed, 2 skipped**).

---

### Task 1: Per-engine tag filtering in `voice.py`

Today `synthesize()` strips every tag at line 250 *before* dispatching, so no tag can ever reach an engine. This task moves filtering into the engines and adds the allow-lists.

**Files:**
- Modify: `src/voice.py:232-269`
- Test: `tests/test_voice.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `_filter_tags(text: str, keep: tuple[str, ...], limit: int) -> str`; `_clean_tts_text(text: str) -> str`; `_pause_markup(text: str) -> str`; `_style_text(text: str) -> str`; `_has_pause_tag(text: str) -> bool`; constants `_PAUSE_TAGS`, `_STYLE_TAGS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_voice.py — append
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


def test_tag_counts_are_capped(monkeypatch):
    monkeypatch.setenv("MAX_PAUSE_TAGS", "2")
    text = "a [pause] b [pause] c [pause] d [pause] e"
    assert voice._pause_markup(text).count("[pause]") == 2


def test_has_pause_tag():
    assert voice._has_pause_tag("a [pause long] b") is True
    assert voice._has_pause_tag("a [sarcastic] b") is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_voice.py -k "tag or markup or style_text" -v`
Expected: FAIL — `AttributeError: module 'src.voice' has no attribute '_pause_markup'`

- [ ] **Step 3: Implement**

Replace `src/voice.py:232-238` (the `_TAG_RE` / `_clean_tts_text` block) with:

```python
# Inline bracket tags the scriptwriter may emit, in two families consumed by different engines:
#   pause tags -> Chirp 3 HD's `markup` input field
#   style tags -> Gemini TTS inline audio tags
# Everything outside these allow-lists is stripped. An invented tag must never reach an API
# (it 400s the request) nor the synthesiser (it gets read aloud).
_PAUSE_TAGS = ("pause short", "pause", "pause long")
_STYLE_TAGS = ("sarcastic", "deadpan", "dry", "amused", "flat", "sighs", "laughs", "beat")

_TAG_RE = re.compile(r"\[([^\]]{1,24})\]|<[^>]{1,60}>")


def _tag_limit(key: str, default: int) -> int:
    try:
        return max(0, int(config.get(key, str(default))))
    except (TypeError, ValueError):
        return default


def _filter_tags(text: str, keep: tuple[str, ...], limit: int) -> str:
    """Keep at most `limit` allow-listed bracket tags; strip every other tag.

    The cap is enforced HERE rather than trusted to the prompt: a prompt asks, a guard is what
    makes it true. Over-tagging a 25-30s Short reads as sluggish."""
    kept = 0

    def _sub(m: re.Match) -> str:
        nonlocal kept
        inner = m.group(1)
        if inner is not None:
            token = inner.strip().lower()
            if token in keep and kept < limit:
                kept += 1
                return f"[{token}]"
        return ""

    return re.sub(r"\s+", " ", _TAG_RE.sub(_sub, text)).strip()


def _clean_tts_text(text: str) -> str:
    """Strip every tag — for engines with no tag support (edge-tts, Kokoro)."""
    return _filter_tags(text, (), 0)


def _pause_markup(text: str) -> str:
    """Chirp 3 HD `markup`: keep pause tags, drop style tags."""
    return _filter_tags(text, _PAUSE_TAGS, _tag_limit("MAX_PAUSE_TAGS", 3))


def _style_text(text: str) -> str:
    """Gemini TTS input: keep style tags, drop pause tags."""
    return _filter_tags(text, _STYLE_TAGS, _tag_limit("MAX_STYLE_TAGS", 3))


def _has_pause_tag(text: str) -> bool:
    return bool(re.search(r"\[(?:pause short|pause long|pause)\]", text))
```

- [ ] **Step 4: Move filtering out of `synthesize()` into the engines**

In `synthesize()` replace line 250-252 with:

```python
    raw = (script_body or "").strip()
    if not _clean_tts_text(raw):  # tags alone are not narration
        raise ValueError("voice.synthesize: empty script_body.")
```

and change the dispatch call from `fn(text, out_dir)` to `fn(raw, out_dir)`.

Then make `_engine_edge` and `_engine_kokoro` filter for themselves:

```python
def _engine_edge(text: str, out_dir: str) -> tuple[str, float]:
    clean = _clean_tts_text(text)
    out_path = os.path.join(out_dir, _audio_filename(clean, ".mp3"))
    dur = _synthesize_edge_tts(clean, out_path, _VOICE, _RATE)
    _log_done(out_path, dur, f"edge-tts:{_VOICE}")
    return out_path, dur


def _engine_kokoro(text: str, out_dir: str) -> tuple[str, float]:
    clean = _clean_tts_text(text)
    out_path = os.path.join(out_dir, _audio_filename(clean, ".wav"))
    dur = _synthesize_kokoro(clean, out_path)
    _log_done(out_path, dur, "kokoro")
    return out_path, dur
```

- [ ] **Step 5: Add a regression test that tags never reach tag-blind engines**

```python
def test_tags_never_reach_edge_tts(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    monkeypatch.setattr(voice, "_synthesize_edge_tts",
                        lambda text, out, v, r: seen.setdefault("text", text) and 1.0 or 1.0)
    monkeypatch.setattr(voice, "_engine_google", lambda *a: (_ for _ in ()).throw(RuntimeError("skip")))
    voice.synthesize("Well [sarcastic] that worked. [pause long] Sure.", str(tmp_path))
    assert "[" not in seen["text"]
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — 242 baseline plus the new tests, 2 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "feat(voice): per-engine inline tag filtering

Tag stripping moves out of synthesize() into each engine so tags can reach the
engines that understand them. Two allow-listed families -- pause tags for Chirp
markup, style tags for Gemini TTS -- with counts capped in code rather than
trusted to the prompt. Everything else is stripped so an invented tag can never
400 an API or be read aloud."
```

---

### Task 2: Chirp 3 HD markup + speaking rate

**Files:**
- Modify: `src/voice.py:146-179` (`_synthesize_google`)
- Test: `tests/test_voice.py`

**Interfaces:**
- Consumes: `_pause_markup`, `_clean_tts_text`, `_has_pause_tag` (Task 1).
- Produces: `_speaking_rate() -> float | None`; `_is_chirp_voice(name: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def _google_ok(monkeypatch, captured):
    class _R:
        status_code = 200
        @staticmethod
        def json():
            import base64, io, wave
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                w.writeframes(b"\x00\x00" * 24000)
            return {"audioContent": base64.b64encode(buf.getvalue()).decode()}
    def _post(url, params=None, json=None, timeout=None):
        captured.update(body=json)
        return _R()
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


def test_non_chirp_voice_never_gets_markup(monkeypatch, tmp_path):
    """`markup` may not be used with any voice other than Chirp 3 HD."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Neural2-A")
    cap = {}
    _google_ok(monkeypatch, cap)
    voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert "text" in cap["body"]["input"]


def test_speaking_rate_clamped(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "9")
    assert voice._speaking_rate() == 2.0
    monkeypatch.setenv("GOOGLE_TTS_SPEAKING_RATE", "junk")
    assert voice._speaking_rate() is None


def test_markup_rejection_retries_as_plain_text(monkeypatch, tmp_path):
    """A markup surprise must not cost us the good voice."""
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Kore")
    calls = []
    import base64, io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)
    good = base64.b64encode(buf.getvalue()).decode()

    class _Bad:
        status_code = 400
        text = "markup not supported"
    class _Good:
        status_code = 200
        @staticmethod
        def json(): return {"audioContent": good}

    def _post(url, params=None, json=None, timeout=None):
        calls.append(json["input"])
        return _Bad() if "markup" in json["input"] else _Good()
    monkeypatch.setattr(voice.requests, "post", _post)

    voice._synthesize_google("It worked. [pause long] Somehow.", str(tmp_path))
    assert len(calls) == 2 and "markup" in calls[0] and "text" in calls[1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_voice.py -k "chirp or markup or speaking_rate" -v`
Expected: FAIL — `AttributeError: module 'src.voice' has no attribute '_speaking_rate'`

- [ ] **Step 3: Implement**

Add above `_synthesize_google`:

```python
def _is_chirp_voice(name: str) -> bool:
    """`markup` is Chirp 3 HD-only; sending it with any other voice is an API error."""
    return "chirp3-hd" in (name or "").lower()


def _speaking_rate() -> float | None:
    """audioConfig.speakingRate, clamped to the documented [0.25, 2.0]. None = leave unset."""
    raw = (config.get("GOOGLE_TTS_SPEAKING_RATE", "") or "").strip()
    if not raw:
        return None
    try:
        return max(0.25, min(float(raw), 2.0))
    except (TypeError, ValueError):
        log.warning("voice: GOOGLE_TTS_SPEAKING_RATE=%r is not a number; ignoring", raw)
        return None
```

Inside `_synthesize_google`, replace the `body = {...}` / `r = requests.post(...)` block with:

```python
    clean = _clean_tts_text(text)
    markup = _pause_markup(text) if config.get_bool("ENABLE_PAUSE_MARKUP", True) else ""
    use_markup = _is_chirp_voice(voice_name) and _has_pause_tag(markup)

    audio_cfg: dict = {"audioEncoding": "LINEAR16"}
    rate = _speaking_rate()
    if rate is not None:
        audio_cfg["speakingRate"] = rate

    def _post(payload_input: dict):
        return requests.post(
            _GOOGLE_TTS_URL, params={"key": api_key},
            json={"input": payload_input,
                  "voice": {"languageCode": lang, "name": voice_name},
                  "audioConfig": audio_cfg},
            timeout=60,
        )

    r = _post({"markup": markup} if use_markup else {"text": clean})
    if r.status_code != 200 and use_markup:
        # Fail-soft: a markup surprise must never cost us the good voice (rules 11, 14).
        log.warning("voice: Chirp rejected markup (%d); retrying as plain text.", r.status_code)
        r = _post({"text": clean})
    if r.status_code != 200:
        raise RuntimeError(f"google tts HTTP {r.status_code}: {r.text[:500]}")
```

Then change the filename line to use `clean`:

```python
    out_path = os.path.join(out_dir, _audio_filename(clean, ".wav"))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_voice.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "feat(voice): Chirp 3 HD pause markup and speaking rate

Sends input.markup instead of input.text when the voice is Chirp 3 HD and a
pause tag survived filtering -- markup is rejected on any other voice, so the
check is required, not defensive. Adds a clamped GOOGLE_TTS_SPEAKING_RATE.

A markup rejection retries once as plain text before failing over, so an
unexpected syntax error costs us the timing, never the voice."
```

---

### Task 3: Gemini Developer API TTS engine

**Files:**
- Modify: `src/voice.py` (add `_synthesize_gemini` + `_engine_gemini` + alias)
- Test: `tests/test_voice.py`

**Interfaces:**
- Consumes: `_style_text` (Task 1), `_audio_filename`, `_log_done`.
- Produces: `_synthesize_gemini(text: str, out_dir: str) -> tuple[str, float]`; `_engine_gemini(text, out_dir) -> tuple[str, float]`.

**Note:** `_ENGINE_ORDER` is deliberately **not** changed. The existing dispatch builds `[primary] + [e for e in _ENGINE_ORDER if e != primary]`, so leaving `gemini` out of that tuple means it is prepended only when explicitly selected and is absent entirely under the default `VOICE_ENGINE=google`. That is exactly the "ships inert" requirement.

- [ ] **Step 1: Write the failing tests**

```python
class _FakePart:
    def __init__(self, data): self.inline_data = type("D", (), {"data": data})()

class _FakeResp:
    def __init__(self, data):
        part = _FakePart(data)
        content = type("C", (), {"parts": [part]})()
        self.candidates = [type("Cd", (), {"content": content})()]


def _fake_genai(monkeypatch, captured, pcm=b"\x00\x00" * 24000):
    class _Models:
        def generate_content(self, **kw):
            captured.update(kw)
            return _FakeResp(pcm)
    class _Client:
        def __init__(self, api_key=None): captured["api_key"] = api_key
        models = _Models()
    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)


def test_gemini_tts_writes_wav_and_measures_duration(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    cap = {}
    _fake_genai(monkeypatch, cap)
    path, dur = voice._synthesize_gemini("Sure. [sarcastic] That'll work.", str(tmp_path))
    assert path.endswith(".wav") and os.path.getsize(path) > 44
    assert dur == pytest.approx(1.0, abs=0.05)  # 24000 frames @ 24 kHz
    import wave
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1


def test_gemini_tts_passes_style_prompt_and_keeps_style_tags(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    monkeypatch.setenv("VOICE_STYLE_PROMPT", "Dry and deadpan.")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("Sure. [sarcastic] That'll work. [pause] Really.", str(tmp_path))
    assert "Dry and deadpan." in cap["contents"]
    assert "[sarcastic]" in cap["contents"]
    assert "[pause]" not in cap["contents"]  # pause tags belong to Chirp


def test_gemini_tts_prefers_dedicated_key(monkeypatch, tmp_path):
    """A separate key lets TTS avoid starving grounded ideation's RPD (rule 13)."""
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    monkeypatch.setenv("GEMINI_TTS_API_KEY", "dedicated")
    cap = {}
    _fake_genai(monkeypatch, cap)
    voice._synthesize_gemini("hi", str(tmp_path))
    assert cap["api_key"] == "dedicated"


def test_gemini_tts_raises_on_empty_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    _fake_genai(monkeypatch, {}, pcm=b"")
    with pytest.raises(RuntimeError, match="empty audio"):
        voice._synthesize_gemini("hi", str(tmp_path))


def test_gemini_absent_from_chain_by_default(monkeypatch, tmp_path):
    """Ships inert: the default VOICE_ENGINE must not reach the new engine at all."""
    monkeypatch.delenv("VOICE_ENGINE", raising=False)
    called = []
    monkeypatch.setattr(voice, "_engine_gemini", lambda *a: called.append(1) or ("x", 1.0))
    monkeypatch.setattr(voice, "_engine_google", lambda *a: ("ok.wav", 2.0))
    voice.synthesize("hello there", str(tmp_path))
    assert called == []


def test_gemini_selected_heads_the_chain_and_falls_soft(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_ENGINE", "gemini")
    order = []
    monkeypatch.setattr(voice, "_engine_gemini",
                        lambda *a: order.append("gemini") or (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(voice, "_engine_google", lambda *a: order.append("google") or ("ok.wav", 2.0))
    path, dur = voice.synthesize("hello there", str(tmp_path))
    assert order == ["gemini", "google"] and path == "ok.wav"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_voice.py -k gemini -v`
Expected: FAIL — `AttributeError: module 'src.voice' has no attribute '_synthesize_gemini'`

- [ ] **Step 3: Implement**

Add after `_synthesize_google`:

```python
_DEFAULT_STYLE_PROMPT = ("Deliver with dry, deadpan sarcasm - amused, never zany. "
                         "Keep it conversational and quick. Land the final line straight.")


def _synthesize_gemini(text: str, out_dir: str) -> tuple[str, float]:
    """Synthesize via the Gemini Developer API TTS models. Returns (wav_path, seconds).

    Uses the already-pinned google-genai SDK and the existing GEMINI_API_KEY, so this adds no
    dependency and no new credential. Style comes from VOICE_STYLE_PROMPT plus the inline style
    tags the scriptwriter emits - both are features of this API, unlike Chirp.

    GEMINI_TTS_API_KEY (optional) isolates TTS onto a second free key so it cannot starve the
    grounded ideation/scriptwriting that only Gemini can do (rule 13).

    The response is RAW PCM (24 kHz, 16-bit mono), not a WAV container - it must be wrapped or
    nothing downstream can read it."""
    import wave

    from google import genai
    from google.genai import types

    key = (config.get("GEMINI_TTS_API_KEY") or config.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("gemini tts: GEMINI_TTS_API_KEY / GEMINI_API_KEY not set")

    spoken = _style_text(text)
    style = config.get("VOICE_STYLE_PROMPT", _DEFAULT_STYLE_PROMPT)
    model = config.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    voice_name = config.get("GEMINI_TTS_VOICE", "Kore")

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=f"{style}\n\n{spoken}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    try:
        pcm = resp.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError) as e:
        raise RuntimeError(f"gemini tts: unexpected response shape ({e})") from e
    if not pcm:
        raise RuntimeError("gemini tts: empty audio")

    out_path = os.path.join(out_dir, _audio_filename(spoken, ".wav"))
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_GEMINI_TTS_RATE)
        w.writeframes(pcm)
    with wave.open(out_path, "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return out_path, duration
```

Add near `_GOOGLE_TTS_URL`:

```python
# Gemini Developer API TTS returns raw PCM at this rate (16-bit mono, no container).
_GEMINI_TTS_RATE = 24000
```

Add beside the other engines, and extend the aliases:

```python
def _engine_gemini(text: str, out_dir: str) -> tuple[str, float]:
    path, dur = _synthesize_gemini(text, out_dir)
    _log_done(path, dur, f"gemini:{config.get('GEMINI_TTS_MODEL', 'gemini-2.5-flash-preview-tts')}")
    return path, dur
```

```python
_ENGINE_ALIASES = {"edge-tts": "edge", "chirp": "google", "google-tts": "google",
                   "gemini-tts": "gemini"}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_voice.py -v`
Expected: PASS

- [ ] **Step 5: Add the gated live test**

```python
def test_live_gemini_tts(tmp_path):
    """Real Gemini TTS. Gated by its own flag: the Pro model has NO free tier, so this must
    never run unattended in CI."""
    if os.environ.get("GEMINI_TTS_LIVE_TEST") != "1":
        pytest.skip("set GEMINI_TTS_LIVE_TEST=1 to run (may bill on non-free models)")
    path, dur = voice._synthesize_gemini(
        "Another committee. [sarcastic] Groundbreaking. Here's why it actually matters.",
        str(tmp_path))
    assert os.path.getsize(path) > 10_000 and 1.0 < dur < 30.0
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, with the new live test skipped.

- [ ] **Step 7: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "feat(voice): Gemini Developer API TTS engine

Adds a promptable TTS engine that honours both a style prompt and the inline
style tags the scriptwriter emits -- the capability Chirp lacks. Uses the
already-pinned google-genai SDK and the existing GEMINI_API_KEY, so no new
dependency and no new credential.

The response is raw 24 kHz PCM rather than a WAV container and is wrapped
before use; skipping that yields a file ffprobe cannot read.

Deliberately left out of _ENGINE_ORDER: the chain builds [primary] + the rest,
so gemini is prepended only when explicitly selected and is absent under the
default VOICE_ENGINE=google. Optional GEMINI_TTS_API_KEY isolates TTS from the
grounded-ideation quota."
```

---

### Task 4: Scriptwriter emits tags, and word counting ignores them

The word cap runs in three places (`src/scriptwriter.py:194`, `:276`, `:280`) plus `_truncate_to_words`. `[pause long]` would count as two words and corrupt the 25–30s length enforcement.

**Files:**
- Modify: `src/scriptwriter.py:34-95` (`_PROMPT_N`), `:194`, `:201-209`, `:275-281`
- Test: `tests/test_scriptwriter.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (tags are plain text here).
- Produces: `_visible_words(body: str) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_visible_words_ignores_tags():
    assert scriptwriter._visible_words("a [pause long] b [sarcastic] c") == ["a", "b", "c"]


def test_word_cap_counts_only_spoken_words(monkeypatch):
    """Tags must not eat the 25-30s word budget."""
    body = " ".join(["word"] * 70) + " [pause long] [sarcastic]"
    assert len(scriptwriter._visible_words(body)) == 70


def test_truncate_preserves_tags_and_cuts_on_a_sentence():
    body = "One two three. [pause] Four five six. Seven eight nine."
    out = scriptwriter._truncate_to_words(body, 6)
    assert out.endswith(".")
    assert "[pause]" in out
    assert "Seven" not in out


def test_prompt_teaches_pause_and_style_tags():
    prompt = scriptwriter._build_prompt(IDEA, "N")
    assert "[pause]" in prompt and "[sarcastic]" in prompt
    assert "..." in prompt  # ellipses guidance for engines without tag support
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_scriptwriter.py -k "visible or truncate or tags" -v`
Expected: FAIL — `AttributeError: module 'src.scriptwriter' has no attribute '_visible_words'`

- [ ] **Step 3: Implement the counting helpers**

Add above `_truncate_to_words`:

```python
_TAG_TOKEN_RE = re.compile(r"^\[[^\]]*\]$")


def _visible_words(body: str) -> list[str]:
    """Words the narrator actually SAYS — inline delivery tags are direction, not narration,
    so counting them would silently shrink the 25-30s script budget."""
    return [w for w in body.split() if not _TAG_TOKEN_RE.match(w)]
```

Replace `_truncate_to_words` with a tag-aware version:

```python
def _truncate_to_words(body: str, max_words: int) -> str:
    """Hard length backstop: cut to the last full sentence at or under max_words (so we never
    end mid-thought). Inline tags are carried through and do not count toward the cap."""
    tokens = body.split()
    if len(_visible_words(body)) <= max_words:
        return body
    kept, spoken = [], 0
    for tok in tokens:
        if not _TAG_TOKEN_RE.match(tok):
            if spoken >= max_words:
                break
            spoken += 1
        kept.append(tok)
    truncated = " ".join(kept)
    ends = list(re.finditer(r"[.!?]", truncated))
    return (truncated[: ends[-1].end()] if ends else truncated).strip()
```

- [ ] **Step 4: Point the three call sites at `_visible_words`**

`src/scriptwriter.py:194`:

```python
    if new_body and 40 <= len(_visible_words(new_body)) <= max_words:
```

`src/scriptwriter.py:276-281`:

```python
    if len(_visible_words(body)) > max_words:
        log.warning("scriptwriter: idea %s script %d words > %d cap; truncating to a sentence.",
                    idea_id, len(_visible_words(body)), max_words)
        body = _truncate_to_words(body, max_words)
    if len(_visible_words(body)) < 50:
        log.warning("scriptwriter: idea %s script is short (%d words)",
                    idea_id, len(_visible_words(body)))
```

- [ ] **Step 5: Add the delivery-direction block to `_PROMPT_N`**

Insert immediately before the `ACCURACY (THE ONE HARD LINE)` paragraph:

```
DELIVERY DIRECTION (this is how it will be READ ALOUD):
Write for the ear first. Short punchy sentences, contractions, natural rhythm. Use "..." for a \
deliberate beat or hesitation - it changes the timing on every voice engine.
Then add AT MOST 3 delivery tags total, only where they genuinely land:
- [pause] or [pause long] for a comic beat before a punchline or the "why it matters" turn.
- [sarcastic], [deadpan] or [dry] immediately before the line whose TONE flips.
Tags are stage direction, never narration - never write a tag the sentence already says out \
loud, and never open the script with one. Fewer is better: a tag on every line reads as noise.
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/scriptwriter.py tests/test_scriptwriter.py
git commit -m "feat(scriptwriter): emit sparse delivery tags, count only spoken words

The prompt now asks for at most three inline delivery tags -- pause beats and
tone flips -- plus ellipses, which change timing on every engine including the
ones with no tag support.

Word counting moves to _visible_words so tags cannot eat the 25-30s budget:
'[pause long]' would otherwise have counted as two words at all three cap sites
and silently shortened the script. Truncation carries tags through and still
cuts on a sentence boundary."
```

---

### Task 5: `tools/compare_voices.py` A/B helper

The Pro model has no free tier, so the Flash-vs-Pro choice should be made by ear, not asserted.

**Files:**
- Create: `tools/compare_voices.py`

**Interfaces:**
- Consumes: `voice._synthesize_google`, `voice._synthesize_gemini` (Tasks 2, 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the tool**

```python
"""Render one script through each voice engine so the operator can pick by ear.

Run: python tools/compare_voices.py [out_dir]
Needs GOOGLE_TTS_API_KEY + GOOGLE_TTS_VOICE for Chirp, GEMINI_API_KEY for Gemini.

NOTE: gemini-2.5-pro-preview-tts has NO free tier (~$1.27/month at 3 Shorts/day). The Flash
model is free. This renders both so the difference is audible before you commit to either.
(ASCII-safe output for the Windows console.)"""
import os
import sys

try:  # load local .env on the dev machine (CI sets env directly)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import voice

SCRIPT = ("Another committee has been formed. [sarcastic] Groundbreaking. "
          "[pause long] Here's why it actually matters: the rules change in April, "
          "and your electricity bill is the one that moves.")

OUT = sys.argv[1] if len(sys.argv) > 1 else "voice_ab"
os.makedirs(OUT, exist_ok=True)

CANDIDATES = [
    ("chirp", None),
    ("gemini-flash", "gemini-2.5-flash-preview-tts"),
    ("gemini-pro", "gemini-2.5-pro-preview-tts"),
]

for label, model in CANDIDATES:
    target = os.path.join(OUT, label)
    os.makedirs(target, exist_ok=True)
    try:
        if model is None:
            path, dur = voice._synthesize_google(SCRIPT, target)
        else:
            os.environ["GEMINI_TTS_MODEL"] = model
            path, dur = voice._synthesize_gemini(SCRIPT, target)
        print("OK   %-13s %5.1fs  %s" % (label, dur, path))
    except Exception as e:  # noqa: BLE001 — report and continue to the next candidate
        print("FAIL %-13s %s" % (label, str(e)[:160]))

print("\nListen to each, then set VOICE_ENGINE and GEMINI_TTS_MODEL accordingly.")
```

- [ ] **Step 2: Verify it runs and reports per-engine status**

Run: `python tools/compare_voices.py "$TMP/voice_ab"`
Expected: three lines, each `OK` or `FAIL` with a readable reason. It must not traceback when a key is missing — a missing key is a `FAIL` line.

- [ ] **Step 3: Commit**

```bash
git add tools/compare_voices.py
git commit -m "chore(tools): add compare_voices A/B helper

Renders one script through Chirp, Gemini Flash and Gemini Pro so the model
choice is settled by ear. Pro has no free tier, so hearing the difference
before enabling it matters. Mirrors tools/list_google_voices.py."
```

---

### Task 6: Wire the knobs into `.env.example` and both workflows

**Files:**
- Modify: `.env.example`, `.github/workflows/make-short.yml`, `.github/workflows/production.yml`

**Interfaces:**
- Consumes: every config key read in Tasks 1–3.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add to `.env.example` under the Voice section**

```
VOICE_STYLE_PROMPT=                 # style instruction for the Gemini TTS engine; default is
                                    # dry deadpan sarcasm. Only this engine honours it.
GEMINI_TTS_MODEL=                   # default gemini-2.5-flash-preview-tts (FREE tier).
                                    # gemini-2.5-pro-preview-tts has NO free tier: ~$1.27/mo
                                    # at 3 Shorts/day. Compare with tools/compare_voices.py.
GEMINI_TTS_VOICE=                   # default Kore (bare name; NOT the en-IN-Chirp3-HD- form)
GEMINI_TTS_API_KEY=                 # optional 2nd free key so TTS cannot starve the grounded
                                    # ideation RPD; falls back to GEMINI_API_KEY
GOOGLE_TTS_SPEAKING_RATE=           # 0.25-2.0 (unset = engine default); >1.0 suits Shorts
ENABLE_PAUSE_MARKUP=                # true (default) | false - send [pause] tags as Chirp markup
MAX_PAUSE_TAGS=                     # cap on pause tags per script (default 3)
MAX_STYLE_TAGS=                     # cap on style tags per script (default 3)
```

- [ ] **Step 2: Add the same block to BOTH workflows**

Append to the `env:` block in `.github/workflows/make-short.yml` and `.github/workflows/production.yml`:

```yaml
          VOICE_STYLE_PROMPT: ${{ vars.VOICE_STYLE_PROMPT }}         # Gemini TTS style instruction
          GEMINI_TTS_MODEL: ${{ vars.GEMINI_TTS_MODEL || 'gemini-2.5-flash-preview-tts' }}  # free tier
          GEMINI_TTS_VOICE: ${{ vars.GEMINI_TTS_VOICE || 'Kore' }}   # bare name, not the Chirp form
          GEMINI_TTS_API_KEY: ${{ secrets.GEMINI_TTS_API_KEY }}      # optional; isolates TTS quota
          GOOGLE_TTS_SPEAKING_RATE: ${{ vars.GOOGLE_TTS_SPEAKING_RATE }}  # 0.25-2.0, unset = default
          ENABLE_PAUSE_MARKUP: ${{ vars.ENABLE_PAUSE_MARKUP || 'true' }}  # [pause] -> Chirp markup
          MAX_PAUSE_TAGS: ${{ vars.MAX_PAUSE_TAGS || '3' }}
          MAX_STYLE_TAGS: ${{ vars.MAX_STYLE_TAGS || '3' }}
```

- [ ] **Step 3: Verify both workflows still parse**

Run:
```bash
python -c "import yaml,sys;[yaml.safe_load(open(p,encoding='utf-8')) for p in ['.github/workflows/make-short.yml','.github/workflows/production.yml']];print('both workflows parse OK')"
```
Expected: `both workflows parse OK`

- [ ] **Step 4: Confirm the default path is unchanged**

Run: `python -m pytest -q`
Expected: PASS — 242 baseline plus all tests added in Tasks 1–4, 2 skipped (Gemini live test skipped).

- [ ] **Step 5: Commit**

```bash
git add .env.example .github/workflows/make-short.yml .github/workflows/production.yml
git commit -m "chore(config): wire expressive-narration knobs into env and workflows

Documents and forwards VOICE_STYLE_PROMPT, GEMINI_TTS_MODEL/VOICE/API_KEY,
GOOGLE_TTS_SPEAKING_RATE, ENABLE_PAUSE_MARKUP and the tag caps.

Defaults keep the feature inert: VOICE_ENGINE stays google, so the Gemini
engine is absent from the chain and the free Flash model is the default if it
is ever selected."
```

---

### Task 7: Update STATUS.md and CHANGELOG.md

**Files:**
- Modify: `STATUS.md`, `CHANGELOG.md`

- [ ] **Step 1: Run the suite and record the REAL number**

Run: `python -m pytest -q 2>&1 | tail -3`
Copy the actual `N passed, M skipped` line — do not estimate it (rule 8; the previous log entry claimed 212 when the true figure was 215).

- [ ] **Step 2: Add a STATUS.md log entry** under a new `### 2026-07-26 — Expressive narration` heading, covering: the per-engine tag design, that Chirp gets `[pause]` markup while Gemini gets style tags, that the Gemini engine is free on the Flash model and ~$1.27/month on Pro at 3 Shorts/day, that it ships inert behind `VOICE_ENGINE`, and the operator follow-ups (run `tools/compare_voices.py`; check free-tier TTS rate limits in AI Studio; set `DAILY_REEL_CAP`/`APPROVAL_CAP` to 3).

- [ ] **Step 3: Add a CHANGELOG.md `### Added` entry** under `[Unreleased]` with the same substance in Keep-a-Changelog style.

- [ ] **Step 4: Commit**

```bash
git add STATUS.md CHANGELOG.md
git commit -m "docs: log expressive narration"
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| Layer 1 — writing craft | 4 (prompt block, ellipses) |
| Layer 2 — inline tags, allow-lists, caps in code | 1, 2, 4 |
| Layer 3 — Gemini TTS engine, PCM→WAV, dedicated key | 3 |
| Layer 4 — speaking rate | 2 |
| Contract impact — word cap fix | 4 |
| Error handling — markup retry, fail-soft, one billed attempt | 2, 3 |
| Testing — unit, gated live, A/B tool | 1–3, 5 |
| Rollout — inert, config wired | 3 (chain), 6 |

No gaps.

**Placeholder scan:** none — every step has runnable code or an exact command.

**Type consistency:** `_filter_tags` / `_clean_tts_text` / `_pause_markup` / `_style_text` / `_has_pause_tag` (Task 1) are used with those exact names in Tasks 2–3; `_visible_words` (Task 4) is used at all three cap sites; `_synthesize_gemini` and `_synthesize_google` keep the shared `(text, out_dir) -> (path, duration)` contract and are called that way in Task 5.

**Deliberate non-change:** `_ENGINE_ORDER` stays `("google", "edge", "kokoro")`. Adding `gemini` to it would put the new engine in the fallback chain under the default config, breaking the "ships inert" requirement.
