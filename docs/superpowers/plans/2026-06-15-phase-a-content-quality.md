# Phase A — Content-Quality Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace robotic American TTS with near-human Google Chirp 3 HD (free at our volume, graceful fallback), de-hype the script/ideation prompts toward honest-curiosity + a human "why it matters" beat, and upgrade captions to active-word karaoke in a real font — all behind config toggles with fallbacks.

**Architecture:** Three independent changes to existing modules, each fail-soft (rule 11/14) and idempotent (rule 12). Voice becomes an ordered fallback **chain** (`google → edge-tts en-IN → kokoro`) so the pipeline never breaks even before the Google API key exists. Prompt changes are string edits with testable seams. Captions gain an ASS karaoke (`\kf`) builder + a bundled OFL font.

**Tech Stack:** Python 3, `requests` (existing), Google Cloud TTS v1 REST (`text:synthesize`, API key), `faster-whisper` (existing word timings), FFmpeg/libass (existing), `pytest`.

**Project rules that bind this plan:** Conventional commits, **no AI self-attribution** in any commit/code/doc (CLAUDE.md rule 3); update STATUS.md + CHANGELOG at the end (rule 1); pin any new dep (none added here); fail-loud on misconfig only for *required* secrets, soft on runtime (rule 14).

---

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/voice.py` | Modify | Add `_synthesize_google` (REST); refactor `synthesize()` into an ordered fallback chain; new knobs. |
| `tools/list_google_voices.py` | Create | One-off helper: list `en-IN` Chirp 3 HD voice names so the operator can set `GOOGLE_TTS_VOICE`. |
| `tests/test_voice.py` | Modify | Tests for the Google path (mocked `requests`) + the chain ordering/fallback. |
| `src/scriptwriter.py` | Modify | De-hype `_PROMPT_N` + `_PUNCHUP_PROMPT`; add required human "why it matters" beat; `ENABLE_HUMAN_ANGLE`. |
| `src/ideation_fallback.py` | Modify | De-hype `_PROMPT`; topic framing toward honest impact, not max-drama. |
| `tests/test_scriptwriter.py` | Modify | Assert new directives present / hype directives absent; compliance still enforced. |
| `tests/test_ideation_fallback.py` | Modify | Assert ideation prompt de-hyped; validation unchanged. |
| `src/subtitles.py` | Modify | New `Karaoke` ASS style + `\kf` per-word builder; `fontsdir`; knobs. |
| `assets/fonts/Montserrat-Bold.ttf` | Create | Bundled OFL caption font (committed; CI has no Montserrat). |
| `assets/fonts/.gitignore` | Create | Exception so the TTF is committed (mirrors `assets/music/`). |
| `tests/test_subtitles.py` | Modify | Tests for karaoke `\kf` line build + font/colour from config. |
| `.env.example` | Modify | Document new env vars. |
| `.github/workflows/make-short.yml` + `production.yml` | Modify | Forward new repo vars/secret. |

---

## Task 1: Voice — Google Chirp 3 HD engine + fallback chain

**Files:**
- Modify: `src/voice.py`
- Create: `tools/list_google_voices.py`
- Test: `tests/test_voice.py`

### Design notes (read first)
- **Auth:** Google Cloud TTS v1 REST `POST https://texttospeech.googleapis.com/v1/text:synthesize?key=<API_KEY>`. Body: `{"input":{"text":...},"voice":{"languageCode":"en-IN","name":"<voice>"},"audioConfig":{"audioEncoding":"LINEAR16"}}`. Response: `{"audioContent":"<base64 WAV>"}`. We request **LINEAR16** so the bytes are a real WAV and we measure duration with the stdlib `wave` module (exact, no ffprobe) — same approach as the Kokoro path.
- **Graceful skip:** if `GOOGLE_TTS_API_KEY` or `GOOGLE_TTS_VOICE` is unset/empty, `_synthesize_google` raises immediately so the chain falls to **edge-tts `en-IN-NeerjaNeural`** (already an upgrade over Kokoro int8). Nothing breaks before the operator finishes Google setup.
- **Chain:** `synthesize()` tries engines in order `[VOICE_ENGINE] + remaining` from `["google","edge","kokoro"]`, returning the first success; raises only if all fail (rule 14).

- [ ] **Step 1: Write the failing test for the Google REST synth**

Add to `tests/test_voice.py`:

```python
import base64
import io
import wave
from unittest import mock


def _fake_wav_b64(seconds: float = 0.5, rate: int = 24000) -> str:
    """A tiny silent LINEAR16 WAV, base64-encoded — mimics Google's audioContent."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_synthesize_google_writes_wav_and_measures_duration(tmp_path, monkeypatch):
    from src import voice

    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Achernar")

    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
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


def test_synthesize_google_missing_key_raises(tmp_path, monkeypatch):
    from src import voice
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_TTS_VOICE", "en-IN-Chirp3-HD-Achernar")
    with pytest.raises(RuntimeError):
        voice._synthesize_google("hi", str(tmp_path))
```

Ensure `import os`, `import pytest`, and `import requests` are present at the top of the test file (add if missing).

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_voice.py::test_synthesize_google_writes_wav_and_measures_duration -v`
Expected: FAIL with `AttributeError: module 'src.voice' has no attribute '_synthesize_google'`.

- [ ] **Step 3: Implement `_synthesize_google` in `src/voice.py`**

Add near the other engine functions (after `_synthesize_kokoro`). Also add `import base64` and `import requests` to the imports at the top if not present (the module already imports `requests` lazily inside `_download`; add a top-level `import requests` and `import base64`).

```python
_GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


def _synthesize_google(text: str, out_dir: str) -> tuple[str, float]:
    """Synthesize via Google Cloud TTS Chirp 3 HD (REST + API key). Returns (wav_path, seconds).

    Requests LINEAR16 so the bytes are a real WAV we can measure with stdlib `wave`.
    Raises (→ caller falls back) if the key/voice is unset or the API errors."""
    import wave

    api_key = config.get("GOOGLE_TTS_API_KEY", "")
    voice_name = config.get("GOOGLE_TTS_VOICE", "")
    if not api_key or not voice_name:
        raise RuntimeError("google tts: GOOGLE_TTS_API_KEY / GOOGLE_TTS_VOICE not set")

    lang = config.get("GOOGLE_TTS_LANGUAGE", "en-IN")
    body = {
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice_name},
        "audioConfig": {"audioEncoding": "LINEAR16"},
    }
    r = requests.post(f"{_GOOGLE_TTS_URL}?key={api_key}", json=body, timeout=60)
    r.raise_for_status()
    b64 = (r.json() or {}).get("audioContent")
    if not b64:
        raise RuntimeError("google tts: empty audioContent")

    out_path = os.path.join(out_dir, _audio_filename(text, ".wav"))
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    with wave.open(out_path, "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return out_path, duration
```

- [ ] **Step 4: Run both Step-1 tests to verify they pass**

Run: `python -m pytest tests/test_voice.py -k google -v`
Expected: PASS (both `..._writes_wav...` and `..._missing_key_raises`).

- [ ] **Step 5: Write the failing test for the fallback chain**

Add to `tests/test_voice.py`:

```python
def test_synthesize_chain_prefers_google_then_falls_back(tmp_path, monkeypatch):
    from src import voice
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
    monkeypatch.setattr(voice, "_engine_kokoro", lambda t, d: (_ for _ in ()).throw(AssertionError("should not reach")))

    path, dur = voice.synthesize("Hello.", str(tmp_path))
    assert calls == ["google", "edge"]   # google tried first, edge second
    assert dur == 1.0
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python -m pytest tests/test_voice.py::test_synthesize_chain_prefers_google_then_falls_back -v`
Expected: FAIL (no `_engine_edge` / chain not implemented).

- [ ] **Step 7: Refactor `synthesize()` into a chain in `src/voice.py`**

Replace the existing `synthesize()` body (the `engine == "kokoro"` / edge block) with thin per-engine wrappers + an ordered loop. Add the wrappers above `synthesize()`:

```python
_ENGINE_ORDER = ("google", "edge", "kokoro")


def _engine_google(text: str, out_dir: str) -> tuple[str, float]:
    path, dur = _synthesize_google(text, out_dir)
    _log_done(path, dur, "google:chirp3hd")
    return path, dur


def _engine_edge(text: str, out_dir: str) -> tuple[str, float]:
    out_path = os.path.join(out_dir, _audio_filename(text, ".mp3"))
    dur = _synthesize_edge_tts(text, out_path, _VOICE, _RATE)
    _log_done(out_path, dur, f"edge-tts:{_VOICE}")
    return out_path, dur


def _engine_kokoro(text: str, out_dir: str) -> tuple[str, float]:
    out_path = os.path.join(out_dir, _audio_filename(text, ".wav"))
    dur = _synthesize_kokoro(text, out_path)
    _log_done(out_path, dur, "kokoro")
    return out_path, dur


_ENGINES = {"google": _engine_google, "edge": _engine_edge, "kokoro": _engine_kokoro}
```

Then the new `synthesize()`:

```python
def synthesize(script_body: str, out_dir: str) -> tuple[str, float]:
    """Return (audio_path, duration_seconds) via an ordered fallback chain (rule 11):
    google (Chirp 3 HD) → edge-tts en-IN → kokoro. VOICE_ENGINE picks the primary; the rest
    follow. Raises only if EVERY engine fails (rule 14: orchestrator skips that one reel)."""
    text = (script_body or "").strip()
    if not text:
        raise ValueError("voice.synthesize: empty script_body.")
    os.makedirs(out_dir, exist_ok=True)

    primary = str(config.get("VOICE_ENGINE", "google")).lower()
    order = [primary] + [e for e in _ENGINE_ORDER if e != primary]
    errors: list[str] = []
    for name in order:
        fn = _ENGINES.get(name)
        if fn is None:
            continue
        try:
            return fn(text, out_dir)
        except Exception as e:  # noqa: BLE001 — try the next engine (rule 11)
            log.warning("voice: engine %s failed (%s); trying next", name, e)
            errors.append(f"{name}: {e}")
    raise RuntimeError("voice.synthesize: all engines failed — " + " | ".join(errors))
```

Keep `_synthesize_kokoro`, `_synthesize_edge_tts`, `_stream_chunks`, `_log_done`, and the module constants unchanged.

- [ ] **Step 8: Run the whole voice suite**

Run: `python -m pytest tests/test_voice.py -v`
Expected: PASS for new tests. If a pre-existing test asserted the old `engine == "kokoro"` default, update it to set `VOICE_ENGINE=kokoro` explicitly or to assert the new chain — fix those inline so the file is green.

- [ ] **Step 9: Create the voice-list helper `tools/list_google_voices.py`**

```python
"""List en-IN Chirp 3 HD voices so the operator can choose GOOGLE_TTS_VOICE.

Run: GOOGLE_TTS_API_KEY=... python tools/list_google_voices.py
(ASCII-safe output for the Windows console.)"""
import os
import sys

import requests

KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
if not KEY:
    print("set GOOGLE_TTS_API_KEY first"); sys.exit(1)

r = requests.get(
    "https://texttospeech.googleapis.com/v1/voices",
    params={"key": KEY, "languageCode": "en-IN"}, timeout=30,
)
r.raise_for_status()
voices = [v["name"] for v in r.json().get("voices", []) if "Chirp3" in v.get("name", "")]
print("en-IN Chirp 3 HD voices:")
for name in sorted(voices):
    print(" -", name)
if not voices:
    print(" (none returned - check the API is enabled / key is valid)")
```

- [ ] **Step 10: Commit**

```bash
git add src/voice.py tools/list_google_voices.py tests/test_voice.py
git commit -m "feat(voice): add Google Chirp 3 HD engine + ordered fallback chain"
```

### Operator step (one-time, out of band — does not block the code)
Create a Google Cloud project → enable **Cloud Text-to-Speech API** → create an **API key restricted to that API** → **set a hard $5 budget cap + email alert** (Billing → Budgets). Run `tools/list_google_voices.py`, pick a voice, then set repo secret `GOOGLE_TTS_API_KEY` and repo var `GOOGLE_TTS_VOICE`. Until then the chain auto-uses edge-tts `en-IN-NeerjaNeural`.

---

## Task 2: De-hype scripts + ideation, add the human "why it matters" beat

**Files:**
- Modify: `src/scriptwriter.py` (`_PROMPT_N`, `_PUNCHUP_PROMPT`), `src/ideation_fallback.py` (`_PROMPT`)
- Test: `tests/test_scriptwriter.py`, `tests/test_ideation_fallback.py`

### Design notes
Keep the JSON contract, the accuracy hard-line, source/disclosure/#Shorts enforcement, retention-loop ending, word-count target. **Change only the framing directives**: honest curiosity + promise↔payoff alignment, and a required analytical "why it matters" human beat. Add `ENABLE_HUMAN_ANGLE` (default true) — when false, behaviour is today's minus the hype (safe escape hatch).

- [ ] **Step 1: Write failing tests asserting the new framing**

Add to `tests/test_scriptwriter.py`:

```python
def test_prompt_is_dehyped_and_demands_human_angle():
    from src import scriptwriter
    idea = {"id": 1, "title": "T", "hook": "H", "angle": "A", "sources": ["https://x.com"]}
    prompt = scriptwriter._build_prompt(idea, "N")
    low = prompt.lower()
    # de-hyped: no max-intensity / over-promise directives
    assert "max" not in low.replace("maximum-intensity", "")  # the literal hype words are gone
    assert "over-promise" not in low
    # honest curiosity + payoff alignment + human analysis required
    assert "why it matters" in low
    assert "payoff" in low or "deliver" in low
    assert "accurate" in low or "accuracy" in low
```

Add to `tests/test_ideation_fallback.py`:

```python
def test_ideation_prompt_dehyped():
    from src import ideation_fallback
    prompt = ideation_fallback._PROMPT.lower()
    assert "max hype" not in prompt
    assert "why it matters" in prompt
    assert "scroll" in prompt  # still cares about a strong honest hook
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_scriptwriter.py::test_prompt_is_dehyped_and_demands_human_angle tests/test_ideation_fallback.py::test_ideation_prompt_dehyped -v`
Expected: FAIL (current prompts contain "MAX HYPE", "maximum-intensity", "over-promise").

- [ ] **Step 3: Rewrite `_PROMPT_N` framing in `src/scriptwriter.py`**

Replace the opening persona paragraph and the "WHAT WINS ON THIS CHANNEL" paragraph with honest-curiosity framing (keep every other section — facts, accuracy, JSON contract — intact):

```python
_PROMPT_N = """You are the scriptwriter for "But It Matters" — fast, punchy YouTube Shorts that \
make people stop scrolling with HONEST curiosity, then reward them with a genuinely useful \
"why it matters" insight. Your voice is natural and conversational with real edge — a sharp \
friend explaining why something actually matters. Energetic and gripping, never a stiff \
news-anchor. The hook is strong but TRUE: the title and opening must sit honestly on what the \
video actually delivers (a click-then-bounce from an over-promise gets the channel suppressed).

IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES:
{sources}

WHAT WINS ON THIS CHANNEL: a curiosity gap the video actually CLOSES. Lead with the single most \
interesting TRUE fact or tension, then pay it off with real analysis. Stories with stakes, \
money/power, conflict, and human consequence travel — but the drama must come from the REAL \
story, framed honestly, not from a bait title the body can't cash. Promise == payoff.

Write a ~110-130 word (<=45s) narration that FLOWS naturally when spoken out loud:
1. HOOK (first 3s — most important line): an honest, scroll-stopping opener — the most surprising \
TRUE fact, a real stakes question, or a genuine curiosity loop you WILL close at the end. No \
"in this video", no throat-clearing, no over-promise.
2. WHAT HAPPENED: 1-2 real facts in your own words, citing the source out loud ("according to ...").
3. WHY IT MATTERS (the core — this is the value): your genuine analytical take on why this is a \
bigger deal than it looks — the consequence, the pattern, what it changes for India / the world. \
This human perspective is what makes the reel original (and keeps the channel monetizable).
4. PAYOFF: close the loop you opened — the answer / what it really means.
5. CTA + SEAMLESS LOOP: one punchy true line that loops back into the hook for clean auto-replay \
("follow before the next one", "comment what you'd do").

WRITE FOR THE EAR: short punchy sentences (<15 words), contractions, natural rhythm. Sound like a \
real person who finds this genuinely interesting. No hateful or personal attacks; punch at \
situations, not people.

ACCURACY (THE ONE HARD LINE): VERIFY the development actually happened (use the sources + web \
search). State ONLY facts you can support. NEVER invent product names, version numbers, figures, \
dates, quotes, or events, and never say "according to <company>" unless it's real. If the premise \
doesn't check out, write the most interesting ACCURATE version instead.

ALSO produce, for the feed + discoverability:
- "title": a clear, curiosity-driven YouTube title (<=70 chars) that is TRUE to the video. A \
curiosity gap, a real number, or honest stakes — front-load the most interesting real word. It \
must NOT promise anything the narration doesn't deliver. Examples of the honest-but-gripping \
energy: "India's new gas rule quietly changes your kitchen bill", "Why Venezuela just out-priced \
Iraq on oil".
- "caption": the YouTube description. FIRST LINE is a second honest curiosity hook (shown in-feed). \
Then a keyword-rich line for SEO, then the source link(s).
- "tags": 8-12 specific search keywords/phrases people would actually type (topic, people/orgs, \
category, close synonyms), most important FIRST. No '#'.

Return ONLY a JSON object, no markdown fences:
{{"title": "the honest, gripping title", "script_body": "the spoken narration", "caption": "hook \
line first, then keyword-rich SEO description including the source link(s)", "hashtags": \
["#keyword", "#Shorts"], "tags": ["search keyword", "another phrase"]}}
"""
```

- [ ] **Step 4: De-hype `_PUNCHUP_PROMPT` in `src/scriptwriter.py`**

Change STEP 2's rewrite trigger and rules to forbid mismatch. Replace the STEP 2 block and the "may over-promise" clause:

```python
# in _PUNCHUP_PROMPT, STEP 2:
STEP 2 — Rewrite for maximum HONEST pull (only when the score is below 7, i.e. genuinely flat):
- TITLE: a clear curiosity gap or real stakes, front-loading the most interesting TRUE word. It \
must stay honest to the narration — never promise something the body doesn't deliver.
- OPENING: replace the first 1-2 sentences with a stronger TRUE hook — the most surprising fact \
already in the script, or a real question the viewer needs answered. Keep the rest of the narration.
```

(Lower the default rewrite threshold: in `_punch_up_hook`, `config.get("HOOK_MIN_SCORE", "8")` → default `"7"`, so it only rewrites genuinely weak hooks.)

- [ ] **Step 5: De-hype ideation `_PROMPT` in `src/ideation_fallback.py`**

Replace the "SCROLL APPEAL" paragraph (the one prioritising conflict/drama/"max") with honest-impact framing, keeping the trending/winners blocks, accuracy, framing-safety, and JSON contract:

```python
# replaces the "SCROLL APPEAL (this is what separated...)" paragraph:
HONEST SCROLL APPEAL: pick stories a smart person finds genuinely surprising or consequential — \
real stakes, money & power, conflict with real consequences, science/space, big human impact. The \
hook must be a TRUE curiosity gap the explainer can actually close (a bait topic the facts can't \
support gets suppressed). Set est_score by how strong an HONEST hook + a real "why it matters" \
angle the story supports — not by how dramatic a title you could slap on it.
```

Also change the per-idea line "a PUNCHY, curiosity-driven title ... NOT a dry 'X explained'" to add "— honest to the story, no over-promise" and keep the rest.

- [ ] **Step 6: Add the `ENABLE_HUMAN_ANGLE` escape hatch**

In `scriptwriter.write_script`, after building the prompt, gate the human-angle emphasis (default on). Minimal approach — append a one-line nudge only when enabled, so the knob is testable:

```python
def _build_prompt(idea: dict, template: str) -> str:
    ...  # existing body
    prompt = _PROMPT_N.format(...)
    if config.get_bool("ENABLE_HUMAN_ANGLE", True):
        prompt += ("\n\nEMPHASIS: the \"why it matters\" analysis is the point of the video — make "
                   "it a genuine, specific human take, not a generic restatement.")
    return prompt
```

- [ ] **Step 7: Run the prompt + compliance tests**

Run: `python -m pytest tests/test_scriptwriter.py tests/test_ideation_fallback.py -v`
Expected: PASS — new framing tests green AND all existing compliance tests (sources/disclosure/#Shorts enforced, word-count, JSON parse) still green. Fix any existing test that hard-matched old hype wording.

- [ ] **Step 8: Commit**

```bash
git add src/scriptwriter.py src/ideation_fallback.py tests/test_scriptwriter.py tests/test_ideation_fallback.py
git commit -m "feat(content): de-hype script/ideation prompts; require honest why-it-matters angle"
```

---

## Task 3: Karaoke captions + Montserrat font

**Files:**
- Create: `assets/fonts/Montserrat-Bold.ttf`, `assets/fonts/.gitignore`
- Modify: `src/subtitles.py`
- Test: `tests/test_subtitles.py`

### Design notes
Build true ASS karaoke: one `Dialogue` per phrase using `{\kf<cs>}` per word, with the **Karaoke** style's `SecondaryColour` = base white and `PrimaryColour` = highlight (so each word fills to the highlight colour exactly as spoken). Per-word `\kf` centiseconds = from this word's start to the next word's start (covers gaps, stays in sync). Font becomes `CAPTION_FONT` (default `Montserrat`), bundled and passed to libass via `fontsdir`.

- [ ] **Step 1: Fetch + commit the OFL font**

Run (PowerShell):

```powershell
New-Item -ItemType Directory -Force assets/fonts | Out-Null
Invoke-WebRequest -Uri "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf" -OutFile "assets/fonts/Montserrat-Bold.ttf"
Set-Content -Path "assets/fonts/.gitignore" -Value "!*.ttf`n!.gitignore" -Encoding utf8
```

Verify the file is a real TTF (non-trivial size):

Run: `python -c "import os;print(os.path.getsize('assets/fonts/Montserrat-Bold.ttf'))"`
Expected: a number > 100000 (≈200 KB). If it's tiny/HTML, the URL redirected — re-fetch from `https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Bold.ttf`.

- [ ] **Step 2: Write the failing test for the karaoke line builder**

Add to `tests/test_subtitles.py`:

```python
def test_karaoke_line_has_kf_tags_and_words():
    from src import subtitles
    words = [(0.0, 0.40, "Oil"), (0.40, 0.90, "export"), (0.90, 1.50, "wars")]
    line = subtitles._karaoke_line(words)
    assert line.count("\\kf") == 3            # one fill tag per word
    assert "Oil" in line and "export" in line and "wars" in line
    # first word fill ~ next_start - start = 0.40s = 40cs
    assert "\\kf40" in line


def test_build_ass_uses_configured_font(monkeypatch):
    from src import subtitles
    monkeypatch.setenv("CAPTION_FONT", "Montserrat")
    words = [(0.0, 0.4, "Hi"), (0.4, 0.8, "there")]
    ass = subtitles._build_ass(words)
    assert "Montserrat" in ass
    assert "Karaoke" in ass            # the karaoke style exists
    assert "{\\kf" in ass              # events use karaoke fill
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_subtitles.py -k "karaoke or configured_font" -v`
Expected: FAIL (`_karaoke_line` undefined; old ASS has no Karaoke style).

- [ ] **Step 4: Implement the karaoke builder in `src/subtitles.py`**

Add the helper and a Karaoke style; rewrite `_build_ass` to emit karaoke phrases. Add near `_build_events`:

```python
def _cs(seconds: float) -> int:
    """Seconds → centiseconds, clamped non-negative (ASS \\kf unit)."""
    return max(0, int(round(seconds * 100)))


def _karaoke_line(words: list[tuple[float, float, str]]) -> str:
    """Build the ASS karaoke text for one phrase: {\\kf<cs>}word per token.

    Each word's fill runs from its start to the NEXT word's start (covers inter-word gaps),
    so the highlight stays synced to speech; the last word uses its own spoken length."""
    parts = []
    for i, (start, end, raw) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else end
        dur_cs = _cs(max(nxt - start, end - start)) if i + 1 < len(words) else _cs(end - start)
        word = _ass_escape(_clean_caption_word(raw))
        if word:
            parts.append(f"{{\\kf{dur_cs}}}{word}")
    return " ".join(parts)
```

Replace `_ASS_HEADER`'s `[V4+ Styles]` block to add a Karaoke style (highlight = yellow primary, white secondary, configurable font). Replace the two `Style:` lines with:

```python
_FONT = config.get("CAPTION_FONT", "Montserrat")
_HILITE = config.get("CAPTION_HIGHLIGHT_COLOR", "&H0000FFFF")  # ASS BGR: yellow

_ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{_FONT},104,{_HILITE},&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,640,1
Style: Hook,{_FONT},94,&H0000FFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,60,60,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
```

(Note: in the Karaoke style, `PrimaryColour` is the *filled* colour — yellow highlight — and `SecondaryColour` is the *pre-fill* colour — white; ASS `\kf` sweeps Secondary→Primary as each word is spoken.)

Now rewrite the event loop in `_build_ass` to group words into phrases and emit one karaoke `Dialogue` per phrase:

```python
def _build_ass(words: list[tuple[float, float, str]], hook_text: str | None = None) -> str:
    lines = [_ASS_HEADER]

    if hook_text and config.get_bool("ENABLE_HOOK_CAPTION", True):
        banner = _hook_banner_text(hook_text)
        if banner:
            secs = float(config.get("HOOK_SECONDS", "1.8"))
            lines.append(f"Dialogue: 1,{_format_ts(0)},{_format_ts(secs)},Hook,,0,0,0,,{banner}")

    size = max(1, int(config.get("CAPTION_WORDS", "3")))   # phrase length for karaoke
    for i in range(0, len(words), size):
        chunk = [w for w in words[i : i + size] if _clean_caption_word(w[2])]
        if not chunk:
            continue
        start, end = chunk[0][0], chunk[-1][1]
        end = end if end > start else start + 0.10
        lines.append(
            f"Dialogue: 0,{_format_ts(start)},{_format_ts(end)},Karaoke,,0,0,0,,{_karaoke_line(chunk)}"
        )
    return "\n".join(lines) + "\n"
```

Keep `_build_events` (still used elsewhere/tests) or delete if unused — if you remove it, also remove its test. Default `CAPTION_WORDS` reads `3` here for readable karaoke phrases.

- [ ] **Step 5: Pass `fontsdir` to libass in `_burn`**

In `_burn`, point libass at the bundled font dir so `Montserrat` resolves in CI. Modify the `-vf` arg:

```python
fonts_dir = os.path.abspath(config.get("CAPTION_FONTS_DIR", "assets/fonts"))
vf = f"ass={os.path.basename(ass_path)}"
if os.path.isdir(fonts_dir):
    vf += f":fontsdir={fonts_dir}"
cmd = [
    _ffmpeg(), "-y",
    "-i", os.path.abspath(video_path),
    "-vf", vf,
    "-c:a", "copy",
    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    os.path.abspath(out_path),
]
```

- [ ] **Step 6: Run the subtitle suite**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: PASS (karaoke + font tests green). Fix/replace any existing test that asserted the old `Pop` style name or 2-word static events — update it to the `Karaoke` style.

- [ ] **Step 7: Commit**

```bash
git add assets/fonts/Montserrat-Bold.ttf assets/fonts/.gitignore src/subtitles.py tests/test_subtitles.py
git commit -m "feat(captions): active-word karaoke captions in Montserrat (bundled font)"
```

---

## Task 4: Wire config, docs, workflows; run full suite; update STATUS/CHANGELOG

**Files:** `.env.example`, `.github/workflows/make-short.yml`, `.github/workflows/production.yml`, `STATUS.md`, `CHANGELOG.md`, `docs/01-design-spec.md`, `docs/07-architecture-diagram.md`, `docs/04-free-tools-reference.md`

- [ ] **Step 1: Document new env in `.env.example`**

Append:

```bash
# Voice — Google Cloud TTS (Chirp 3 HD). Free at our volume; set a $5 budget cap. Falls back to edge-tts en-IN.
VOICE_ENGINE=google
GOOGLE_TTS_API_KEY=
GOOGLE_TTS_VOICE=          # run tools/list_google_voices.py and paste an en-IN Chirp3-HD name
GOOGLE_TTS_LANGUAGE=en-IN
# Content framing
ENABLE_HUMAN_ANGLE=true
# Captions
CAPTION_FONT=Montserrat
CAPTION_HIGHLIGHT_COLOR=&H0000FFFF
```

- [ ] **Step 2: Forward the knobs in both workflows**

In `.github/workflows/make-short.yml` and `production.yml`, add to the job `env:` block (mirroring how existing knobs like `IMAGE_STYLE` are passed):

```yaml
      VOICE_ENGINE: ${{ vars.VOICE_ENGINE }}
      GOOGLE_TTS_API_KEY: ${{ secrets.GOOGLE_TTS_API_KEY }}
      GOOGLE_TTS_VOICE: ${{ vars.GOOGLE_TTS_VOICE }}
      GOOGLE_TTS_LANGUAGE: ${{ vars.GOOGLE_TTS_LANGUAGE }}
      ENABLE_HUMAN_ANGLE: ${{ vars.ENABLE_HUMAN_ANGLE }}
      CAPTION_FONT: ${{ vars.CAPTION_FONT }}
      CAPTION_HIGHLIGHT_COLOR: ${{ vars.CAPTION_HIGHLIGHT_COLOR }}
```

- [ ] **Step 3: Run the FULL suite**

Run: `python -m pytest -q`
Expected: all green (was 153; new tests add to that). Investigate any failure before proceeding — do not claim done on red (rule 8).

- [ ] **Step 4: Sync the remaining cost-target docs**

Update the `$0/month` lines flagged in the spec to `≤ $5/month`: `docs/01-design-spec.md:235` and `docs/07-architecture-diagram.md:7`. Add Google Cloud TTS to `docs/04-free-tools-reference.md` (free tier 1M chars/mo Chirp 3 HD; budget-capped).

- [ ] **Step 5: Update STATUS.md + CHANGELOG.md, bump version**

Add a STATUS log entry (what changed · tests · operator follow-ups: Google key + voice). Add a CHANGELOG entry under a new `0.3.0` heading (minor: voice engine + content/caption quality). Keep STATUS version in sync (rule 18).

- [ ] **Step 6: Commit**

```bash
git add .env.example .github/workflows/ STATUS.md CHANGELOG.md docs/
git commit -m "chore(phase-a): wire config + workflows; sync docs; bump to v0.3.0"
```

---

## Self-review (done before handoff)
- **Spec coverage:** voice 3.1 → Task 1; content 3.2a → Task 2; captions 3.4 → Task 3; config/doc-sync → Task 4. (3.2b news-RSS, 3.3 visuals, 3.5 metadata, 3.6 lever are Phase B/C — intentionally out of this plan.)
- **Fallback safety:** Google failure (incl. no key/voice) → edge-tts en-IN → kokoro, proven in Task 1 Step 5.
- **No placeholders:** every code/test/command step is concrete; the one runtime unknown (exact Chirp 3 HD voice name) is resolved by `tools/list_google_voices.py`, not guessed in code.
- **Naming consistency:** `_synthesize_google`, `_engine_google/_engine_edge/_engine_kokoro`, `_ENGINES`, `_karaoke_line`, `_cs`, knobs `GOOGLE_TTS_*`, `ENABLE_HUMAN_ANGLE`, `CAPTION_FONT`, `CAPTION_HIGHLIGHT_COLOR` used identically across tasks.
