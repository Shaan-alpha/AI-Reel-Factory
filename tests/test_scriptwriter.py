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
    """Make llm.generate return `reply` and capture the db.insert_script call."""
    captured = {}
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: reply)

    def fake_insert(idea_id, template, body, caption, hashtags):
        captured.update(idea_id=idea_id, template=template, body=body,
                        caption=caption, hashtags=hashtags)
        return 7

    monkeypatch.setattr(scriptwriter.db, "insert_script", fake_insert)
    return captured


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
    assert out["caption"].lower().count("narration is ai-generated") == 1
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
