"""Tests for the production orchestrator (Module 10).

Every pipeline module is mocked — no real renders, uploads, or network. These verify the
chain wiring, idempotency, fail-soft batching, the daily cap, and the dry-queue bootstrap.
"""
from __future__ import annotations

import pytest

from src import production


def test_source_domain_derivation():
    assert production._source_domain(["https://www.thehindu.com/news/x"]) == "thehindu.com"
    assert production._source_domain(["pib.gov.in/PressRelease"]) == "pib.gov.in"
    assert production._source_domain([]) is None


IDEA = {"id": 7, "title": "ISRO rocket, explained", "hook": "h", "angle": "a",
        "sources": ["https://x.example"]}
SCRIPT = {"script_id": 70, "script_body": "body words " * 20,
          "caption": "cap https://x.example\n#Shorts", "hashtags": ["#ISRO", "#Shorts"]}


def _wire_happy(monkeypatch, existing_post=None, factcheck_ok=True):
    """Mock the whole chain so produce_one runs without side effects."""
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: SCRIPT)
    # MUST be mocked: factcheck.verify() calls grounded Gemini. Left real, the suite makes live
    # network calls and burns the shared 20/day grounded quota (rule 13) — and passes for the
    # wrong reason, because a 429 takes the fail-open path.
    monkeypatch.setattr(production.factcheck, "verify",
                        lambda body, sources=None, title="": {
                            "ok": factcheck_ok,
                            "unsupported": [] if factcheck_ok else ["the 40% figure is invented"],
                            "checked": 3, "reason": "pass" if factcheck_ok else "fail"})
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
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s: None)  # no live Supabase

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
    meta = production._build_metadata(idea, script, include_channel_tags=False)
    assert meta["title"] == "SEO Title"
    # hashtags(#-stripped) + tags, case-insensitively de-duped, order preserved
    assert meta["tags"] == ["ISRO", "Shorts", "space mission", "rocket"]

    # With channel tags included
    meta_full = production._build_metadata(idea, script, include_channel_tags=True)
    assert "But It Matters" in meta_full["tags"]


def test_build_metadata_falls_back_to_idea_title():
    meta = production._build_metadata({"title": "Idea T"}, {"caption": "d", "hashtags": []}, include_channel_tags=False)
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
                        lambda limit=None, only_ids=None: {
                            "published": [{"idea_id": 1, "url": "https://yt/x"}], "failed": []})
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
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    production.make_on_demand()  # uses the 2 queued ideas, no generation


def test_make_on_demand_nothing_approved(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n: 3)
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    production.make_on_demand()
    assert any("Nothing approved" in n for n in notes)


# --- fact-check gate --------------------------------------------------------------------

def test_factcheck_failure_blocks_the_reel_before_any_render(monkeypatch, tmp_path):
    """The gate sits before voice/visuals/render so a bad script costs one LLM call, not a
    full render and upload."""
    produced = _wire_happy(monkeypatch, factcheck_ok=False)
    rendered = []
    monkeypatch.setattr(production.voice, "synthesize",
                        lambda body, d: rendered.append("voice") or ("a.mp3", 30.0))

    with pytest.raises(production.FactCheckFailed, match="40%"):
        production.produce_one(IDEA, str(tmp_path))

    assert rendered == [], "nothing may render after a failed fact check"
    assert (7, "rejected") in produced, "the idea must drop out of the queue, not retry forever"


def test_factcheck_pass_lets_the_reel_through(monkeypatch, tmp_path):
    produced = _wire_happy(monkeypatch, factcheck_ok=True)
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1"
    assert (7, "produced") in produced


def test_factcheck_failure_is_soft_for_the_batch(monkeypatch):
    """One blocked reel must not take the day's other Shorts with it (rule 14)."""
    ideas = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)

    def _produce(idea, root):
        if idea["id"] == 2:
            raise production.FactCheckFailed("idea 2 failed fact check: invented figure")
        return f"V{idea['id']}", f"https://youtu.be/V{idea['id']}"

    monkeypatch.setattr(production, "produce_one", _produce)
    out = production.run_production()
    assert [p["idea_id"] for p in out["published"]] == [1, 3]
    assert len(out["failed"]) == 1
    assert "FactCheckFailed" in out["failed"][0]["error"]


def test_factcheck_failure_alerts_the_operator(monkeypatch):
    """A silently dropped reel is worse than a loud one — the operator must learn WHY."""
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 9, "title": "t"}])
    alerts = []
    monkeypatch.setattr(production, "_notify_failure",
                        lambda idea, e: alerts.append(f"{type(e).__name__}: {e}"))
    monkeypatch.setattr(production, "produce_one",
                        lambda i, r: (_ for _ in ()).throw(
                            production.FactCheckFailed("idea 9 failed fact check: bad date")))
    production.run_production()
    assert len(alerts) == 1
    assert "FactCheckFailed" in alerts[0] and "bad date" in alerts[0]


# --- the approval boundary: a run may only produce what THIS run offered -------------------

def test_run_production_only_produces_ideas_offered_in_this_run(monkeypatch):
    """`only_ids` scopes the batch to the ideas this run put in front of the operator.

    Without it, run_production drained every row still sitting at status='approved' — including
    ones left over from an earlier run that failed. Live receipt (2026-09-01): run 32920283763
    logged `idea 223 failed`; two days later run 33108008045 sent 2 ideas to the digest, reported
    `3 approved after webhook wait`, and published 223 with no fresh tap.
    """
    stale, fresh = {"id": 223, "title": "left over from a failed run"}, {"id": 226, "title": "offered now"}
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [stale, fresh])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)
    seen = []
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root: seen.append(idea["id"]) or ("V", "u"))

    production.run_production(only_ids=[226])
    assert seen == [226], "a stale approved idea must not be produced without a fresh approval"


def test_run_production_without_only_ids_still_drains_the_queue(monkeypatch):
    """The scheduled cron path has no 'this run's digest' — it legitimately drains the queue."""
    monkeypatch.setattr(production.db, "get_approved_ideas",
                        lambda: [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)
    seen = []
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root: seen.append(idea["id"]) or ("V", "u"))
    production.run_production()
    assert seen == [1, 2]


def test_a_failed_reel_is_released_from_the_approved_queue(monkeypatch):
    """A reel that dies mid-chain must not stay 'approved'.

    Staying approved is what let it be produced later with no tap, and it also permanently
    consumed a slot of APPROVAL_CAP (approval._apply_callback counts every approved row), so
    three stuck ideas made every future tap answer "capped".
    """
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 5, "title": "x"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root: (_ for _ in ()).throw(RuntimeError("voice died")))
    statuses = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s: statuses.append((i, s)))

    production.run_production()
    assert (5, "pending") in statuses, (
        "a transiently failed idea must go back to the digest for a fresh decision, not linger approved")


def test_a_factcheck_failure_stays_rejected_and_is_not_re_offered(monkeypatch):
    """produce_one already rejected it — a content verdict must not be reset to pending."""
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 6, "title": "y"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e: None)
    monkeypatch.setattr(production, "produce_one", lambda idea, root: (_ for _ in ()).throw(
        production.FactCheckFailed("idea 6 failed fact check: invented statistic")))
    statuses = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s: statuses.append((i, s)))

    production.run_production()
    assert (6, "pending") not in statuses


def test_make_on_demand_scopes_production_to_the_ideas_it_offered(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 11}, {"id": 12}])
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 1)
    monkeypatch.setattr(production, "_notify", lambda t: None)
    captured = {}

    def _fake_run(limit=None, only_ids=None):
        captured["only_ids"] = only_ids
        return {"published": [], "failed": []}
    monkeypatch.setattr(production, "run_production", _fake_run)

    production.make_on_demand()
    assert sorted(captured["only_ids"]) == [11, 12]
