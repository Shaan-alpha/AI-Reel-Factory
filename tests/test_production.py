"""Tests for the production orchestrator (Module 10).

Every pipeline module is mocked — no real renders, uploads, or network. These verify the
chain wiring, idempotency, fail-soft batching, the daily cap, and the dry-queue bootstrap.
"""
from __future__ import annotations

import pytest

from src import production


IDEA = {"id": 7, "title": "ISRO rocket, explained", "hook": "h", "angle": "a",
        "sources": ["https://x.example"]}
SCRIPT = {"script_id": 70, "script_body": "body words " * 20,
          "caption": "cap https://x.example\n#Shorts", "hashtags": ["#ISRO", "#Shorts"]}


def _wire_happy(monkeypatch, existing_post=None):
    """Mock the whole chain so produce_one runs without side effects."""
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: SCRIPT)
    monkeypatch.setattr(production.db, "get_published_post_for_idea",
                        lambda idea_id, plat="youtube": existing_post)
    monkeypatch.setattr(production.voice, "synthesize", lambda body, d: ("a.mp3", 30.0))
    monkeypatch.setattr(production.visuals, "extract_keywords", lambda body: ["rocket"])
    monkeypatch.setattr(production.visuals, "fetch_broll", lambda kw, dur, d: ["c1.mp4"])
    monkeypatch.setattr(production.assembly, "assemble", lambda a, c, o: o)
    monkeypatch.setattr(production.subtitles, "burn_captions", lambda v, a, o, **k: o)
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: ("VID1", "https://www.youtube.com/shorts/VID1"))
    produced = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s: produced.append((i, s)))
    return produced


def test_produce_one_full_chain(monkeypatch, tmp_path):
    produced = _wire_happy(monkeypatch)
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1" and url.endswith("VID1")
    assert (7, "produced") in produced  # idea marked produced


def test_produce_one_passes_key_points_to_captions(monkeypatch, tmp_path):
    captured = {}
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "key_points": ["First in Asia"]})
    monkeypatch.setattr(production.subtitles, "burn_captions",
                        lambda v, a, o, **k: captured.update(k) or o)
    production.produce_one(IDEA, str(tmp_path))
    assert captured.get("key_points") == ["First in Asia"]


def test_produce_one_idempotent_skips_before_scripting(monkeypatch, tmp_path):
    produced = _wire_happy(monkeypatch, existing_post={"external_id": "OLD", "url": "u"})
    # neither scripting nor rendering should happen when the idea already shipped
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda *a, **k: pytest.fail("should not write a script when already published"))
    monkeypatch.setattr(production.voice, "synthesize",
                        lambda *a, **k: pytest.fail("should not render when already published"))
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "OLD" and (7, "produced") in produced


def test_build_metadata_appends_footer(monkeypatch):
    monkeypatch.delenv("ENABLE_DESC_FOOTER", raising=False)  # default on
    monkeypatch.delenv("DESCRIPTION_FOOTER", raising=False)
    meta = production._build_metadata(
        {"id": 1, "title": "T"},
        {"title": "Viral T", "caption": "the analysis. https://src", "hashtags": [], "tags": []})
    assert "But It Matters" in meta["description"]
    assert meta["description"].startswith("the analysis.")        # caption preserved, footer after
    assert meta["description"].count("#ButItMatters") == 1


def test_footer_toggle_off(monkeypatch):
    monkeypatch.setenv("ENABLE_DESC_FOOTER", "0")
    assert production._with_footer("just the caption") == "just the caption"


def test_footer_is_idempotent(monkeypatch):
    monkeypatch.delenv("ENABLE_DESC_FOOTER", raising=False)
    once = production._with_footer("body text")
    twice = production._with_footer(once)            # re-applying must not double the footer
    assert once == twice and twice.count("#ButItMatters") == 1


def test_footer_env_override(monkeypatch):
    monkeypatch.setenv("DESCRIPTION_FOOTER", "Follow @x")
    out = production._with_footer("caption")
    assert out == "caption\n\nFollow @x"


def test_run_production_is_fail_soft(monkeypatch):
    ideas = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)

    def fake_produce(idea, root):
        if idea["id"] == 2:
            raise RuntimeError("boom")
        return f"V{idea['id']}", f"url{idea['id']}"
    monkeypatch.setattr(production, "produce_one", fake_produce)

    summary = production.run_production()
    assert [p["idea_id"] for p in summary["published"]] == [1, 3]
    assert summary["failed"][0]["idea_id"] == 2 and "boom" in summary["failed"][0]["error"]


def test_run_production_respects_cap(monkeypatch):
    ideas = [{"id": i, "title": str(i)} for i in range(10)]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    seen = []
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root: seen.append(idea["id"]) or ("V", "u"))
    production.run_production(limit=3)
    assert seen == [0, 1, 2]


def test_run_production_no_approved(monkeypatch):
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [])
    assert production.run_production() == {"published": [], "failed": []}


def test_ensure_ideas_bootstraps_when_dry(monkeypatch):
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [])
    monkeypatch.setenv("ENABLE_FALLBACK_IDEATION", "true")
    monkeypatch.setattr(production.ideation_fallback, "run_fallback_ideation", lambda: 12)
    sent = []
    monkeypatch.setattr(production.approval, "send_digest", lambda: sent.append(True))
    assert production.ensure_ideas_and_digest() == 12 and sent == [True]


def test_ensure_ideas_noop_when_queue_has_work(monkeypatch):
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 1}])
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "run_fallback_ideation",
                        lambda: pytest.fail("should not ideate when ideas pending"))
    assert production.ensure_ideas_and_digest() == 0


def test_build_metadata_prefers_seo_title_and_merges_tags():
    idea = {"title": "fallback title"}
    script = {"title": "SEO Title", "caption": "desc",
              "hashtags": ["#ISRO", "#Shorts"], "tags": ["isro", "space mission", "rocket"]}
    meta = production._build_metadata(idea, script)
    assert meta["title"] == "SEO Title"
    # hashtags(#-stripped) + tags, case-insensitively de-duped, order preserved
    assert meta["tags"] == ["ISRO", "Shorts", "space mission", "rocket"]


def test_build_metadata_falls_back_to_idea_title():
    meta = production._build_metadata({"title": "Idea T"}, {"caption": "d", "hashtags": []})
    assert meta["title"] == "Idea T" and meta["tags"] == []


def test_run_smoke(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production, "ensure_ideas_and_digest", lambda: 0)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "run_production", lambda: {"published": [1], "failed": []})
    production.run()  # should not raise


def test_make_on_demand_flow(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])  # empty → generate
    calls = []
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n: calls.append(("gen", n)) or 3)
    monkeypatch.setattr(production.approval, "send_digest", lambda: calls.append(("digest",)))
    monkeypatch.setattr(production.approval, "process_responses",
                        lambda **k: calls.append(("drain", k)) or 1)
    monkeypatch.setattr(production, "run_production",
                        lambda: {"published": [{"idea_id": 1, "url": "https://yt/x"}], "failed": []})
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))

    summary = production.make_on_demand(num_ideas=3, wait_minutes=15)
    assert summary["published"][0]["url"] == "https://yt/x"
    # ordered: generate -> digest -> drain(900s) -> (then notify links)
    assert calls[0] == ("gen", 3) and calls[1] == ("digest",)
    assert calls[2][0] == "drain" and calls[2][1]["max_seconds"] == 900
    assert any("https://yt/x" in n for n in notes)  # link sent to Telegram


def test_make_on_demand_prefers_existing_pending(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n: pytest.fail("must not generate when ideas already queued"))
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 1)
    monkeypatch.setattr(production, "run_production", lambda: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    production.make_on_demand()  # uses the 2 queued ideas, no generation


def test_make_on_demand_nothing_approved(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n: 3)
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "run_production", lambda: {"published": [], "failed": []})
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    production.make_on_demand()
    assert any("Nothing approved" in n for n in notes)
