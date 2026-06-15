"""Unit tests for the scriptwriter (Module 3).

These mock llm.generate and db.insert_script, so they need no API keys, no network, and no
live DB — they verify the prompt assembly, JSON parsing, and (critically) the monetization-gate
enforcement: source links, AI-disclosure line, and #Shorts are added even when the LLM omits
them (rule 7: tested in isolation; docs/08 §1-3).
"""
from __future__ import annotations

import json

import pytest

from src import scriptwriter

IDEA = {
    "id": 42,
    "title": "ISRO's reusable rocket, explained - why it matters",
    "hook": "India just test-fired a rocket that lands itself.",
    "angle": "Reusability could cut India's launch costs and open the market to startups.",
    "sources": ["https://example.com/isro", "https://example.org/space"],
}


def _patch(monkeypatch, reply: str):
    """Make both LLM paths return `reply` and capture the db.insert_script call."""
    captured = {}
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded", lambda *a, **k: reply)  # primary
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: reply)            # fallback

    def fake_insert(idea_id, template, body, caption, hashtags, title=None):
        captured.update(idea_id=idea_id, template=template, body=body,
                        caption=caption, hashtags=hashtags, title=title)
        return 7

    monkeypatch.setattr(scriptwriter.db, "insert_script", fake_insert)
    return captured


def test_grounded_failure_falls_back_to_ungrounded(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no grounding")
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded", _boom)
    reply = json.dumps({"script_body": "ok body " * 20,
                        "caption": "cap https://example.com/isro https://example.org/space",
                        "hashtags": ["#Shorts"]})
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: reply)
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a: 7)
    out = scriptwriter.write_script(IDEA)
    assert out["script_id"] == 7 and out["script_body"].strip()


def test_happy_path_persists_and_returns(monkeypatch):
    reply = json.dumps({
        "script_body": "A clear 140-word analysis of why reusability matters. " * 3,
        "caption": "ISRO reusable rocket explained. https://example.com/isro https://example.org/space",
        "hashtags": ["#ISRO", "#Shorts"],
    })
    captured = _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    assert out["script_id"] == 7
    assert captured["idea_id"] == 42 and captured["template"] == "N"
    assert "ai-generated" in out["caption"].lower()  # disclosure enforced


def test_persists_published_title_for_learning_loop(monkeypatch):
    """The punchy published title is stored on the script so analytics can learn what wins."""
    reply = json.dumps({
        "title": "Oil Export WARS \U0001f6e2️",
        "script_body": "A clear 140-word analysis of why this matters. " * 3,
        "caption": "hook line. https://example.com/isro https://example.org/space",
        "hashtags": ["#Shorts"],
    })
    captured = _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    assert out["title"] == "Oil Export WARS \U0001f6e2️"
    assert captured["title"] == "Oil Export WARS \U0001f6e2️"  # passed through to db.insert_script


def test_enforces_disclosure_sources_and_shorts_when_llm_omits_them(monkeypatch):
    reply = json.dumps({
        "script_body": "Body that is long enough to pass the soft word check. " * 4,
        "caption": "A caption with no sources and no disclosure.",
        "hashtags": ["#space"],  # no #Shorts
    })
    scriptwriter_captured = _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    # #Shorts appended
    assert any(h.lower() == "#shorts" for h in out["hashtags"])
    # both source URLs present
    assert "https://example.com/isro" in out["caption"]
    assert "https://example.org/space" in out["caption"]
    # disclosure present
    assert scriptwriter.DISCLOSURE_LINE in out["caption"]


def test_does_not_duplicate_existing_compliance(monkeypatch):
    reply = json.dumps({
        "script_body": "Long enough body text to clear the lower word bound here. " * 4,
        "caption": ("Great explainer. https://example.com/isro https://example.org/space "
                    + scriptwriter.DISCLOSURE_LINE),
        "hashtags": ["#Shorts"],
    })
    _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    assert out["caption"].lower().count("ai-generated") == 1  # disclosure not duplicated
    assert out["hashtags"].count("#Shorts") == 1


def test_parses_json_wrapped_in_markdown_fence(monkeypatch):
    inner = json.dumps({
        "script_body": "Fenced JSON body that is sufficiently long to pass checks. " * 4,
        "caption": "cap https://example.com/isro https://example.org/space",
        "hashtags": ["#Shorts"],
    })
    _patch(monkeypatch, f"```json\n{inner}\n```")
    out = scriptwriter.write_script(IDEA)
    assert out["script_id"] == 7


def test_raises_on_empty_script_body(monkeypatch):
    _patch(monkeypatch, json.dumps({"script_body": "  ", "caption": "x", "hashtags": []}))
    with pytest.raises(ValueError, match="empty script_body"):
        scriptwriter.write_script(IDEA)


def test_raises_on_unparseable_reply(monkeypatch):
    _patch(monkeypatch, "the model refused and returned prose with no json")
    with pytest.raises(ValueError, match="no JSON object"):
        scriptwriter.write_script(IDEA)


def test_unsupported_template_raises(monkeypatch):
    _patch(monkeypatch, "{}")
    with pytest.raises(ValueError, match="unsupported template"):
        scriptwriter.write_script(IDEA, template="D")


def test_missing_idea_id_raises(monkeypatch):
    _patch(monkeypatch, "{}")
    with pytest.raises(ValueError, match="no 'id'"):
        scriptwriter.write_script({"title": "x"})


# --- scroll-stop hook judge (_punch_up_hook) -------------------------------------------

_LONG_BODY = "word " * 120  # ~120 words → inside the sane-rewrite band


def test_punch_up_keeps_original_when_hook_already_strong(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"hook_score": 9, "title": "NEW", "script_body": _LONG_BODY}))
    title, body = scriptwriter._punch_up_hook("Original Title", "the original body text")
    assert title == "Original Title" and body == "the original body text"  # strong → untouched


def test_punch_up_rewrites_weak_hook(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"hook_score": 3, "title": "PUNCHIER", "script_body": _LONG_BODY}))
    title, body = scriptwriter._punch_up_hook("Meh Title", "weak body")
    assert title == "PUNCHIER" and body.strip() == _LONG_BODY.strip()


def test_punch_up_rejects_too_short_rewrite(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"hook_score": 2, "title": "X", "script_body": "too short"}))
    title, body = scriptwriter._punch_up_hook("Keep", "keep this body")
    assert title == "Keep" and body == "keep this body"  # bad word count → original kept


def test_punch_up_fail_soft_on_llm_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(scriptwriter.llm, "generate", _boom)
    title, body = scriptwriter._punch_up_hook("Title", "body")
    assert title == "Title" and body == "body"  # never raises; returns original


def test_hook_judge_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_HOOK_JUDGE", "0")
    # generate would raise if the judge ran; reply only feeds the script JSON path via _patch
    reply = json.dumps({"title": "T", "script_body": "ok body " * 20,
                        "caption": "cap https://example.com/isro https://example.org/space",
                        "hashtags": ["#Shorts"]})
    captured = _patch(monkeypatch, reply)
    called = {"n": 0}
    real_generate = scriptwriter.llm.generate

    def counting(*a, **k):
        called["n"] += 1
        return real_generate(*a, **k)
    monkeypatch.setattr(scriptwriter.llm, "generate", counting)
    scriptwriter.write_script(IDEA)
    assert called["n"] == 0  # judge disabled → no extra generate call (grounded path supplies JSON)


# --- de-hyped framing (honest curiosity + human angle) ---------------------------------

def test_prompt_is_dehyped_and_demands_human_angle():
    prompt = scriptwriter._build_prompt(IDEA, "N").lower()
    # the old max-hype directives are gone
    for hype in ("maximum-intensity", "max hype", "max intensity", "over-promise"):
        assert hype not in prompt
    # honest curiosity + payoff alignment + required human analysis
    assert "honest" in prompt
    assert "why it matters" in prompt
    assert "accuracy" in prompt or "accurate" in prompt
    assert "payoff" in prompt or "deliver" in prompt


def test_human_angle_emphasis_toggles_off(monkeypatch):
    monkeypatch.setenv("ENABLE_HUMAN_ANGLE", "0")
    prompt = scriptwriter._build_prompt(IDEA, "N").lower()
    assert "emphasis:" not in prompt   # the extra nudge is omitted when disabled


def test_returns_key_points_for_text_cards(monkeypatch):
    reply = json.dumps({
        "title": "T",
        "script_body": "A clear analysis of why this genuinely matters to people. " * 4,
        "caption": "hook. https://example.com/isro https://example.org/space",
        "hashtags": ["#Shorts"],
        "key_points": ["Rs 2 lakh crore", "First in Asia", "  ", "30% cheaper", "a", "b", "c"],
    })
    _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    # blanks dropped, capped at 5, order preserved
    assert out["key_points"] == ["Rs 2 lakh crore", "First in Asia", "30% cheaper", "a", "b"]


def test_key_points_default_empty_when_absent(monkeypatch):
    reply = json.dumps({"title": "T", "script_body": "ok body " * 20,
                        "caption": "cap https://example.com/isro https://example.org/space",
                        "hashtags": ["#Shorts"]})
    _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    assert out["key_points"] == []
