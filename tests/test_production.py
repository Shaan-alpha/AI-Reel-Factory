"""Tests for the production orchestrator (Module 10).

Every pipeline module is mocked — no real renders, uploads, or network. These verify the
chain wiring, idempotency, fail-soft batching, the daily cap, and the dry-queue bootstrap.
"""
from __future__ import annotations

import os

import pytest

from src import gates, production


@pytest.fixture(autouse=True)
def _reels_pass_their_check(monkeypatch):
    """The reel check (design 11.6) probes the burned reel; these tests' reels are fakes, so
    every reel passes it unless a test says otherwise."""
    monkeypatch.setattr(gates, "reel_problems", lambda path, seconds: [], raising=False)


def test_source_domain_derivation():
    assert production._source_domain(["https://www.thehindu.com/news/x"]) == "thehindu.com"
    assert production._source_domain(["pib.gov.in/PressRelease"]) == "pib.gov.in"
    assert production._source_domain([]) is None


def _raiser(exc):
    def _fn(*_args, **_kwargs):
        raise exc

    return _fn


IDEA = {"id": 7, "title": "ISRO rocket, explained", "hook": "h", "angle": "a",
        "sources": ["https://x.example"]}
SCRIPT = {"script_id": 70, "script_body": "body words " * 20,
          "caption": "cap https://x.example\n#Shorts", "hashtags": ["#ISRO", "#Shorts"]}



def _fake_synth(body, d, meta=None, tone=None):
    """A normal render: the channel voice spoke."""
    if meta is not None:
        meta.update(engine="gemini", voice="gemini:gemini-3.1-flash-tts-preview@dev")
    return "a.mp3", 30.0

def _wire_happy(monkeypatch, existing_post=None, factcheck_ok=True):
    """Mock the whole chain so produce_one runs without side effects."""
    # A fresh copy per reel: production writes into the script dict (a repair replaces the
    # body), and the shared SCRIPT used to carry one test's repair into every later test.
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: dict(SCRIPT))
    # MUST be mocked: factcheck.verify() calls grounded Gemini. Left real, the suite makes live
    # network calls and burns the shared 20/day grounded quota (rule 13) — and passes for the
    # wrong reason, because a 429 takes the fail-open path.
    monkeypatch.setattr(production.factcheck, "verify",
                        lambda body, sources=None, title="", on_screen=None: {
                            "ok": factcheck_ok,
                            "unsupported": [] if factcheck_ok else ["the 40% figure is invented"],
                            "checked": 3, "reason": "pass" if factcheck_ok else "fail"})
    monkeypatch.setattr(production.db, "get_published_post_for_idea",
                        lambda idea_id, plat="youtube": existing_post)
    monkeypatch.setattr(production.voice, "synthesize", _fake_synth)
    monkeypatch.setattr(production.visuals, "extract_keywords", lambda body: ["rocket"])
    def _broll(kw, dur, d, setting=None, meta=None):
        if meta is not None:
            meta.update(source="ai", clips=1)
        return ["c1.mp4"]

    monkeypatch.setattr(production.visuals, "fetch_broll", _broll)
    monkeypatch.setattr(production.assembly, "assemble", lambda a, c, o: o)
    monkeypatch.setattr(production.subtitles, "burn_captions", lambda v, a, o, **k: o)
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: ("VID1", "https://www.youtube.com/shorts/VID1"))
    produced = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: produced.append((i, s)))
    monkeypatch.setattr(production.db, "set_script_factcheck", lambda *a, **k: None)
    monkeypatch.setattr(production.db, "set_script_grounding", lambda *a, **k: None)
    # The repair pass is a grounded rewrite: left real, a blocked reel made live model calls.
    monkeypatch.setattr(production.scriptwriter, "repair_script", lambda *a, **k: None)
    monkeypatch.setattr(production.db, "update_script_body", lambda *a, **k: None)
    monkeypatch.setattr(production.db, "update_script_title", lambda *a, **k: None)
    monkeypatch.setattr(production.db, "update_script_caption", lambda *a, **k: None)
    return produced


def test_produce_one_full_chain(monkeypatch, tmp_path):
    produced = _wire_happy(monkeypatch)
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1" and url.endswith("VID1")
    assert (7, "produced") in produced  # idea marked produced


def test_a_live_short_is_never_reported_as_failed(monkeypatch, tmp_path):
    """After the upload, a failed 'produced' write used to fail the reel and send its idea back
    to the digest, where a second tap would upload the same story again (rule 12)."""
    _wire_happy(monkeypatch)

    def _db_down(*a, **k):
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr(production.db, "set_idea_status", _db_down)
    notes = []
    monkeypatch.setattr(production, "_notify", notes.append)
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1"
    assert notes and "Published" in notes[0] and "Don't approve it again" in notes[0]


def test_a_claude_problem_is_reported_once_per_run(monkeypatch, tmp_path):
    """A revoked key or a spent budget repeats on every reel, and the grounded draft quietly
    ships each time: the operator hears it once, not three times, and not never."""
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production, "_claude_reported", set())
    issue = {"kind": "misconfigured", "reason": "AuthenticationError: invalid x-api-key"}
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: {
        **SCRIPT, "writer": "gemini-grounded", "claude_issue": issue})
    notes = []
    monkeypatch.setattr(production, "_notify", notes.append)
    production.produce_one(IDEA, str(tmp_path))
    production.produce_one({**IDEA, "id": 8}, str(tmp_path))
    claude_notes = [n for n in notes if "Claude" in n]
    assert len(claude_notes) == 1 and "invalid x-api-key" in claude_notes[0]


def test_a_script_claude_wrote_sends_no_claude_note(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production, "_claude_reported", set())
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "writer": "claude", "claude_issue": None})
    notes = []
    monkeypatch.setattr(production, "_notify", notes.append)
    production.produce_one(IDEA, str(tmp_path))
    assert not [n for n in notes if "Claude" in n]


def test_alerts_carry_no_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCdefGHIjkl")
    msg = production._redact("400 for url: https://api.telegram.org/bot123456:ABCdefGHIjkl/send"
                             " and https://texttospeech.googleapis.com/v1/text:synthesize?key=AIzaXYZ")
    assert "ABCdefGHIjkl" not in msg and "AIzaXYZ" not in msg and "key=***" in msg


def test_a_crash_is_reported_once(monkeypatch, tmp_path):
    marker = tmp_path / "crash-notified"
    monkeypatch.setenv("CRASH_NOTE_FILE", str(marker))
    notes = []
    monkeypatch.setattr(production, "_notify", notes.append)
    production._report_crash(RuntimeError("boom"))
    assert "crashed" in notes[0] and "RuntimeError" in notes[0]
    assert marker.exists()  # the workflow's own alert step stays quiet


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
    assert once == twice and twice.count(production._DEFAULT_FOOTER) == 1


def test_footer_env_override(monkeypatch):
    monkeypatch.setenv("DESCRIPTION_FOOTER", "Follow @x")
    out = production._with_footer("caption")
    assert out == "caption\n\nFollow @x"


def test_run_production_is_fail_soft(monkeypatch):
    ideas = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: None)  # no live Supabase

    def fake_produce(idea, root, report=None):
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
                        lambda idea, root, report=None: seen.append(idea["id"]) or ("V", "u"))
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


def test_build_metadata_prefers_seo_title_and_keeps_hashtags_out_of_tags():
    idea = {"title": "fallback title"}
    script = {"title": "SEO Title", "caption": "desc",
              "hashtags": ["#ISRO", "#Shorts"], "tags": ["isro", "space mission", "rocket"]}
    meta = production._build_metadata(idea, script, include_channel_tags=False)
    assert meta["title"] == "SEO Title"
    # the writer's tags only, order preserved; hashtags go on the description's last line
    assert meta["tags"] == ["isro", "space mission", "rocket"]

    # With channel tags included: the brand only
    meta_full = production._build_metadata(idea, script, include_channel_tags=True)
    assert meta_full["tags"] == ["isro", "space mission", "rocket", "But It Matters"]


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
                        lambda n, already_pending=0: calls.append(("gen", n)) or 3)
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
    # The link is announced by run_production as the reel goes live (stubbed here), never a
    # second time by make_on_demand: test_published_is_sent_as_each_reel_goes_live covers it.
    assert not any("https://yt/x" in n for n in notes)


def test_make_on_demand_tops_up_ideas_already_queued(monkeypatch):
    """Leftovers go in the digest WITH fresh ideas. Any pending idea used to switch ideation off,
    so the evening digest would have re-sent the morning's untapped ideas and nothing new."""
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 1}, {"id": 2}])
    calls = []
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n, already_pending=0: calls.append((n, already_pending)) or 1)
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 1)
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    production.make_on_demand()
    assert calls == [(3, 2)]
    assert any("3 idea(s) ready" in n for n in notes), notes


def test_make_on_demand_keeps_queued_ideas_when_the_top_up_comes_up_dry(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 1}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        _raiser(RuntimeError("ideation: no fresh ideas to seed")))
    sent = []
    monkeypatch.setattr(production.approval, "send_digest", lambda: sent.append(1))
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    production.make_on_demand()
    assert sent, "the queued idea must still be offered"


def test_leftover_approvals_go_back_to_the_digest(monkeypatch):
    """A late tap, or a job killed mid-chain, left an idea at 'approved' that no run produces,
    holding one of the bot's three approval slots for good."""
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 7}, {"id": 8}])
    moves = []
    monkeypatch.setattr(production.db, "set_idea_status",
                        lambda i, s, from_status=None: moves.append((i, s, from_status)) or i == 7)
    assert production._release_leftover_approvals() == 1
    assert moves == [(7, "pending", "approved"), (8, "pending", "approved")]


def test_make_on_demand_releases_leftover_approvals_before_the_age_out(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    order = []
    monkeypatch.setattr(production, "_release_leftover_approvals",
                        lambda: order.append("release") or 0)
    monkeypatch.setattr(production.db, "expire_stale_pending_ideas",
                        lambda: order.append("expire") or 0)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 9}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n, already_pending=0: 0)
    monkeypatch.setattr(production.approval, "send_digest", lambda: 1)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    production.make_on_demand(3, 1)
    assert order == ["release", "expire"], "a released idea must still be aged out if it is old"


def test_make_on_demand_nothing_approved(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n, already_pending=0: 3)
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
                        lambda body, d, meta=None, tone=None: rendered.append("voice") or ("a.mp3", 30.0))

    with pytest.raises(production.FactCheckFailed, match="40%"):
        production.produce_one(IDEA, str(tmp_path))

    assert rendered == [], "nothing may render after a failed fact check"
    assert (7, "blocked") in produced, "the idea must drop out of the queue, not retry forever"


def test_strict_mode_holds_back_an_unchecked_reel_without_rejecting_the_idea(monkeypatch, tmp_path):
    """FACTCHECK_STRICT=true (operator, 2026-09-13) blocks a reel whose check could not RUN.

    That is not a verdict on the story. Treating it as FactCheckFailed marked a good idea
    'rejected' forever over a 503 or an unreadable reply, and the alert said "failed fact check"
    about a story nobody had checked.
    """
    produced = _wire_happy(monkeypatch)
    monkeypatch.setattr(production.factcheck, "verify", lambda body, sources=None, title="", on_screen=None: {
        "ok": False, "unsupported": ["checker unavailable: 503 UNAVAILABLE"], "minor": [],
        "checked": 0, "reason": "checker-failed: 503 UNAVAILABLE"})
    rendered = []
    monkeypatch.setattr(production.voice, "synthesize",
                        lambda body, d, meta=None, tone=None: rendered.append("voice") or ("a.mp3", 30.0))

    with pytest.raises(production.FactCheckUnavailable, match="could not run"):
        production.produce_one(IDEA, str(tmp_path))

    assert rendered == [], "an unverified reel must not render or publish in strict mode"
    assert (7, "rejected") not in produced and (7, "blocked") not in produced


_REAL_VERIFY = production.factcheck.verify


def test_strict_mode_contract_with_the_real_gate(monkeypatch, tmp_path):
    """Pins the handshake the test above mocks: factcheck's strict outage result must be what
    produce_one recognises. If the reason string ever drifts, this fails instead of the idea
    silently being rejected again."""
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.factcheck, "verify", _REAL_VERIFY)
    monkeypatch.setenv("ENABLE_FACT_CHECK", "true")
    monkeypatch.setenv("FACTCHECK_STRICT", "true")
    monkeypatch.setattr(production.factcheck.llm, "generate_grounded",
                        _raiser(RuntimeError("503 UNAVAILABLE")))
    with pytest.raises(production.FactCheckUnavailable):
        production.produce_one(IDEA, str(tmp_path))


def test_an_unchecked_reel_goes_back_to_the_digest(monkeypatch):
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 8, "title": "z"}])
    alerts = []
    monkeypatch.setattr(production, "_notify_failure",
                        lambda idea, e, spend=None: alerts.append(f"{type(e).__name__}: {e}"))
    monkeypatch.setattr(production, "produce_one", lambda idea, root, report=None: (_ for _ in ()).throw(
        production.FactCheckUnavailable("idea 8 held back: the fact-check could not run")))
    statuses = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: statuses.append((i, s)))

    production.run_production()
    assert (8, "pending") in statuses
    assert "could not run" in alerts[0] and "FactCheckFailed" not in alerts[0]


def test_factcheck_pass_lets_the_reel_through(monkeypatch, tmp_path):
    produced = _wire_happy(monkeypatch, factcheck_ok=True)
    vid, url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1"
    assert (7, "produced") in produced


def test_factcheck_failure_is_soft_for_the_batch(monkeypatch):
    """One blocked reel must not take the day's other Shorts with it (rule 14)."""
    ideas = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)

    def _produce(idea, root, report=None):
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
                        lambda idea, e, spend=None: alerts.append(f"{type(e).__name__}: {e}"))
    monkeypatch.setattr(production, "produce_one",
                        lambda i, r, report=None: (_ for _ in ()).throw(
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
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)
    seen = []
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root, report=None: seen.append(idea["id"]) or ("V", "u"))

    production.run_production(only_ids=[226])
    assert seen == [226], "a stale approved idea must not be produced without a fresh approval"


def test_run_production_without_only_ids_still_drains_the_queue(monkeypatch):
    """The scheduled cron path has no 'this run's digest' — it legitimately drains the queue."""
    monkeypatch.setattr(production.db, "get_approved_ideas",
                        lambda: [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)
    seen = []
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root, report=None: seen.append(idea["id"]) or ("V", "u"))
    production.run_production()
    assert seen == [1, 2]


def test_a_failed_reel_is_released_from_the_approved_queue(monkeypatch):
    """A reel that dies mid-chain must not stay 'approved'.

    Staying approved is what let it be produced later with no tap, and it also permanently
    consumed a slot of APPROVAL_CAP (approval._apply_callback counts every approved row), so
    three stuck ideas made every future tap answer "capped".
    """
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 5, "title": "x"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)
    monkeypatch.setattr(production, "produce_one",
                        lambda idea, root, report=None: (_ for _ in ()).throw(RuntimeError("voice died")))
    statuses = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: statuses.append((i, s)))

    production.run_production()
    assert (5, "pending") in statuses, (
        "a transiently failed idea must go back to the digest for a fresh decision, not linger approved")


def test_a_factcheck_failure_stays_rejected_and_is_not_re_offered(monkeypatch):
    """produce_one already rejected it — a content verdict must not be reset to pending."""
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 6, "title": "y"}])
    monkeypatch.setattr(production, "_notify_failure", lambda idea, e, spend=None: None)
    monkeypatch.setattr(production, "produce_one", lambda idea, root, report=None: (_ for _ in ()).throw(
        production.FactCheckFailed("idea 6 failed fact check: invented statistic")))
    statuses = []
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: statuses.append((i, s)))

    production.run_production()
    assert (6, "pending") not in statuses


def test_make_on_demand_scopes_production_to_the_ideas_it_offered(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 11}, {"id": 12}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n, already_pending=0: 0)
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


# --- ideation failure is a runtime condition, not a misconfig (2026-09-03) ------------------
# Run 33755597063 died with `RuntimeError: ideation: no fresh ideas to seed` and exit 1. The
# operator's only signal was a red X in the Actions UI. Rule 14 says fail loud on MISCONFIG and
# soft on RUNTIME — "no sourced stories right now" is the latter, so it is a Telegram message.

def test_make_on_demand_alerts_and_exits_cleanly_when_ideation_fails(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        _raiser(RuntimeError("ideation: no fresh ideas to seed (source: x).")))

    def _never(*a, **k):
        raise AssertionError("must not reach the digest with nothing to propose")

    monkeypatch.setattr(production.approval, "send_digest", _never)
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))

    summary = production.make_on_demand(num_ideas=3, wait_minutes=15)

    assert summary == {"published": [], "failed": []}
    assert any("no fresh ideas to seed" in n for n in notes), notes


def test_make_on_demand_still_raises_on_a_misconfigured_run(monkeypatch):
    """A missing secret must stay a hard stop — the soft path is only for ideation coming up dry."""
    monkeypatch.setattr(production.config, "validate",
                        _raiser(production.config.ConfigError("Missing required settings: X")))
    with pytest.raises(production.config.ConfigError):
        production.make_on_demand()


# --- a silent fail-open is the worst outcome (2026-09-03 audit) ---------------------------
# factcheck.verify returns ok=True both when a reel PASSES and when the checker could not run
# (quota exhausted, Gemini down). produce_one only read `ok`, so an unverified reel published
# looking exactly like a verified one. Accuracy is the monetization gate (rule 6) — the operator
# has to be told.

def test_produce_one_alerts_when_the_fact_check_gate_could_not_run(monkeypatch):
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.factcheck, "verify",
                        lambda *a, **k: {"ok": True, "unsupported": [], "minor": [], "checked": 0,
                                         "reason": "checker-failed: 429 RESOURCE_EXHAUSTED"})
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))

    video_id, _url = production.produce_one(dict(IDEA), "/tmp/work")

    assert video_id == "VID1"            # fail-open still ships (FACTCHECK_STRICT default)
    assert notes, "the operator must be told the gate did not run"
    assert "unverified" in notes[0].lower()
    assert str(IDEA["id"]) in notes[0]


def test_produce_one_does_not_alert_on_a_normal_pass(monkeypatch):
    _wire_happy(monkeypatch)
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    production.produce_one(dict(IDEA), "/tmp/work")
    assert notes == [], "a verified reel must not cry wolf"


# --- stale ideas must not be re-offered (2026-09-03 audit) --------------------------------
# make_on_demand PREFERS whatever is already pending, and a reel that dies mid-chain is put back
# to 'pending' by _release_failed_idea. Nothing ages those out, so yesterday's news can be
# re-proposed as today's digest — on a channel whose whole premise is "today's story".

def test_make_on_demand_expires_stale_pending_before_reusing_it(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    order = []
    monkeypatch.setattr(production.db, "expire_stale_pending_ideas",
                        lambda: order.append("expire") or 2)
    monkeypatch.setattr(production.db, "get_pending_ideas",
                        lambda: order.append("read") or [{"id": 9}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n, already_pending=0: 0)
    monkeypatch.setattr(production.approval, "send_digest", lambda: 1)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    monkeypatch.setattr(production, "_wait_for_webhook_decisions", lambda **k: 0)
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)

    production.make_on_demand(3, 1)
    assert order[0] == "expire", "stale ideas must be cleared BEFORE the queue is read"


def test_produce_one_alerts_when_the_reel_leaves_the_channel_voice(monkeypatch, tmp_path):
    """Three September reels shipped in Chirp's voice with only a log line to show for it."""
    _wire_happy(monkeypatch)
    sent = []
    monkeypatch.setattr(production, "_notify", sent.append)

    def _chirp(body, d, meta=None, tone=None):
        meta.update(engine="google", voice="google")
        return "a.wav", 30.0

    monkeypatch.setattr(production.voice, "synthesize", _chirp)
    production.produce_one(IDEA, str(tmp_path))
    assert any("not the channel voice" in m for m in sent)


def test_produce_one_is_quiet_when_the_channel_voice_spoke(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    sent = []
    monkeypatch.setattr(production, "_notify", sent.append)
    production.produce_one(IDEA, str(tmp_path))
    assert not any("channel voice" in m for m in sent)


def test_the_approval_wait_ends_once_this_runs_cap_is_met(monkeypatch):
    """5 of 14 sampled runs sat out the full 30 minutes waiting on ideas nobody would tap."""
    monkeypatch.setenv("APPROVAL_CAP", "1")
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 9}, {"id": 2}])
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [{"id": 1}])
    monkeypatch.setattr(production.time, "sleep", lambda s: pytest.fail("must not keep waiting"))
    assert production._wait_for_webhook_decisions(600, offered=[1, 2]) == 1


def test_the_approval_wait_ignores_other_runs_pending_ideas(monkeypatch):
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 99}])
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [])
    monkeypatch.setattr(production.time, "sleep", lambda s: pytest.fail("must not keep waiting"))
    production._wait_for_webhook_decisions(600, offered=[1, 2])


def test_a_failed_poll_keeps_the_approval_wait_alive(monkeypatch):
    """Run 36804231283 died on one dropped connection while the operator's tap was pending."""
    import httpx

    polls = iter([httpx.RemoteProtocolError("ConnectionTerminated"), [{"id": 1}], []])

    def _pending():
        nxt = next(polls)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    slept = []
    monkeypatch.setattr(production.db, "get_pending_ideas", _pending)
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [])
    monkeypatch.setattr(production.time, "sleep", slept.append)
    production._wait_for_webhook_decisions(600, offered=[1])
    assert len(slept) == 2  # waited through the failed poll and the pending one, then finished


def _verdicts(monkeypatch, *results):
    it = iter(results)
    monkeypatch.setattr(production.factcheck, "verify", lambda *a, **k: next(it))


_BLOCK = {"ok": False, "unsupported": ["the bill was already signed"], "minor": [], "checked": 3,
          "reason": "fail"}
_OK = {"ok": True, "unsupported": [], "minor": [], "checked": 3, "reason": "pass"}


def test_a_blocked_script_is_repaired_once_and_rechecked(monkeypatch, tmp_path):
    """Idea 308's block said exactly what was true ('already signed into law'); the reel used to
    be thrown away anyway. The rewrite must pass the same gate before it is used."""
    _wire_happy(monkeypatch)
    _verdicts(monkeypatch, _BLOCK, _OK)
    saved, voiced = [], []
    monkeypatch.setattr(production.scriptwriter, "repair_script", lambda body, f, topic=None, title=None, **_:
                        {"script_body": "FIXED BODY", "title": title})
    monkeypatch.setattr(production.db, "update_script_body", lambda sid, b: saved.append(b))
    monkeypatch.setattr(production.voice, "synthesize",
                        lambda body, d, meta=None, tone=None: voiced.append(body) or _fake_synth(body, d, meta))
    production.produce_one(IDEA, str(tmp_path))
    assert saved == ["FIXED BODY"] and voiced == ["FIXED BODY"]


def test_a_repair_rechecks_the_key_number(monkeypatch, tmp_path):
    """Review Focus 3: a repair that rewrites the number away drops the card."""
    _wire_happy(monkeypatch)
    _verdicts(monkeypatch, _BLOCK, _OK)
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: {
        **SCRIPT, "script_body": "It took 286 days. " * 5, "key_number": "286 days"})
    monkeypatch.setattr(production.scriptwriter, "repair_script",
                        lambda body, f, topic=None, title=None, **_: {
                            "script_body": "It took 290 days. " * 5, "title": title})
    seen = {}
    monkeypatch.setattr(production.subtitles, "burn_captions",
                        lambda v, a, o, **k: seen.update(k) or o)
    production.produce_one(IDEA, str(tmp_path))
    assert seen["key_number"] == ""


def test_the_key_number_reaches_both_burns(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "key_number": "286 days"})
    english = {}
    monkeypatch.setattr(production.subtitles, "burn_captions",
                        lambda v, a, o, **k: english.update(k) or o)
    production.produce_one(IDEA, str(tmp_path))
    assert english["key_number"] == "286 days"

    hinglish = {}
    _hinglish_wiring(monkeypatch)
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "key_number": "286 days"})
    monkeypatch.setattr(production.subtitles, "burn_hinglish",
                        lambda v, a, o, lines, **k: hinglish.update(k) or o)
    production.produce_one(IDEA, str(tmp_path))
    assert hinglish["key_number"] == "286 days"


def test_a_repair_that_fails_the_gate_again_stays_blocked(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    _verdicts(monkeypatch, _BLOCK, _BLOCK)
    monkeypatch.setattr(production.scriptwriter, "repair_script", lambda body, f, topic=None, title=None, **_:
                        {"script_body": "STILL WRONG", "title": title})
    monkeypatch.setattr(production.db, "update_script_body",
                        lambda *a: pytest.fail("a failed repair must not be saved"))
    with pytest.raises(production.FactCheckFailed):
        production.produce_one(IDEA, str(tmp_path))


def test_the_verdict_is_stored_and_a_block_is_marked_blocked(monkeypatch, tmp_path):
    """Verdicts lived only in CI logs, and a gate block looked like the operator's Reject."""
    produced = _wire_happy(monkeypatch, factcheck_ok=False)
    monkeypatch.setenv("ENABLE_FACTCHECK_REPAIR", "false")
    stored = []
    monkeypatch.setattr(production.db, "set_script_factcheck", lambda sid, v: stored.append(v))
    with pytest.raises(production.FactCheckFailed):
        production.produce_one(IDEA, str(tmp_path))
    assert stored and stored[0]["ok"] is False and stored[0]["blocking"]
    assert (IDEA["id"], "blocked") in produced


def test_the_voice_that_spoke_reaches_the_post_row(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    seen = {}
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: seen.update(m) or ("VID1", "u"))
    production.produce_one(IDEA, str(tmp_path))
    assert seen["voice"] == "gemini:gemini-3.1-flash-tts-preview@dev"


def test_the_cron_path_does_not_poll_telegram_in_webhook_mode(monkeypatch):
    """getUpdates against an active webhook is refused (409); the bot already wrote the taps."""
    monkeypatch.setenv("TELEGRAM_APPROVAL_MODE", "webhook")
    monkeypatch.setattr(production.config, "validate", lambda *a, **k: None)
    monkeypatch.setattr(production, "ensure_ideas_and_digest", lambda: 0)
    monkeypatch.setattr(production.approval, "process_responses",
                        lambda **k: pytest.fail("must not poll getUpdates in webhook mode"))
    monkeypatch.setattr(production, "run_production", lambda: {"published": [], "failed": []})
    production.run()


def test_no_fixed_channel_tag_but_the_brand():
    """Design 9.9: 'News Shorts', 'Trending News' and the India tag are gone."""
    script = {"title": "T", "caption": "c", "hashtags": [], "tags": []}
    us = production._build_metadata({"title": "Networks boycott White House coverage"}, script)
    india = production._build_metadata({"title": "Rupee hits a record low against the dollar"},
                                        script)
    assert us["tags"] == india["tags"] == ["But It Matters"]


def test_the_footer_names_the_channel():
    assert "But It Matters" in production._DEFAULT_FOOTER
    assert "@butitmatters" in production._DEFAULT_FOOTER


def test_the_on_screen_source_is_a_publisher_not_the_aggregator():
    assert production._source_domain(["https://news.google.com/rss/articles/X",
                                      "https://www.thehindu.com/news/a"]) == "thehindu.com"
    assert production._source_domain(["https://news.google.com/rss/articles/X"]) == "Google News"
    assert production._source_domain([]) is None


# --- the job's time limit (audit 2026-09-27, ops) ---------------------------------------------
# A kill at timeout-minutes skips every except block: the idea stays 'approved', and one killed
# between the upload and insert_post would be published twice by a rerun.

def test_no_time_limit_is_assumed_when_none_is_configured(monkeypatch):
    monkeypatch.setattr(production.config, "get",
                        lambda k, d=None: None if k == "JOB_TIMEOUT_MINUTES" else d)
    assert production._seconds_left() is None


def test_the_time_left_counts_down_from_the_job_limit(monkeypatch):
    monkeypatch.setattr(production.config, "get",
                        lambda k, d=None: {"JOB_TIMEOUT_MINUTES": "90",
                                           "JOB_SETUP_MINUTES": "5"}.get(k, d))
    monkeypatch.setattr(production, "_STARTED", production.time.monotonic() - 600)
    left = production._seconds_left()
    assert 74 * 60 < left <= 75 * 60, left  # 90 - 5 setup - 10 already spent


def test_the_time_left_counts_from_the_job_start_when_the_workflow_records_it(monkeypatch):
    # 2026-10-22: a crawling Ubuntu mirror held apt for 16+ minutes. Python started that late,
    # so a fixed 5-minute setup allowance would have overstated the time left by 11+ minutes.
    started = production.time.time() - 30 * 60  # job began 30 min ago
    monkeypatch.setattr(production.config, "get",
                        lambda k, d=None: {"JOB_TIMEOUT_MINUTES": "90",
                                           "JOB_STARTED_AT": str(int(started)),
                                           "JOB_SETUP_MINUTES": "5"}.get(k, d))
    monkeypatch.setattr(production, "_STARTED", production.time.monotonic())  # Python just began
    left = production._seconds_left()
    assert 59 * 60 < left <= 60 * 60 + 1, left  # 90 - 30 spent, whatever setup took


def test_a_reel_that_cannot_finish_in_time_is_not_started(monkeypatch):
    monkeypatch.setattr(production.db, "get_approved_ideas",
                        lambda: [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
    monkeypatch.setattr(production, "_seconds_left", lambda: 300.0)
    monkeypatch.setattr(production, "produce_one",
                        lambda *a, **k: pytest.fail("must not start a reel it cannot finish"))
    moved = []
    monkeypatch.setattr(production.db, "set_idea_status",
                        lambda i, s, from_status=None: moved.append((i, s)) or True)
    notes = []
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    summary = production.run_production()
    assert moved == [(1, "pending"), (2, "pending")]
    assert [f["error"] for f in summary["failed"]] == ["out of time", "out of time"]
    assert any("Out of time" in n for n in notes)


def test_the_wait_leaves_room_for_a_reel(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 1}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n, already_pending=0: 0)
    monkeypatch.setattr(production.approval, "send_digest", lambda: 1)
    waited = []
    monkeypatch.setattr(production.approval, "process_responses",
                        lambda **k: waited.append(k["max_seconds"]) or 0)
    monkeypatch.setattr(production, "_seconds_left", lambda: 30 * 60.0)  # 30 min left
    monkeypatch.setattr(production, "_approval_mode", lambda: "polling")
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    monkeypatch.delenv("REEL_BUDGET_MINUTES", raising=False)
    production.make_on_demand(3, 45)
    # Design 6.4: a reel is allowed 14 minutes (was 12), for an ai_video reel's clips.
    assert waited == [16 * 60], "30 min left minus a 14-minute reel leaves a 16-minute wait"


# --- an untapped digest is a pass (2026-09-29) --------------------------------------------------
# The same three ideas went out at 15:35 and again at 01:32 IST: left 'pending', they became the
# next digest and filled it, so no fresh story was generated.

def test_untapped_ideas_from_this_digest_are_passed(monkeypatch):
    monkeypatch.setattr(production.db, "get_pending_ideas",
                        lambda: [{"id": 1}, {"id": 2}, {"id": 9}])
    moves = []
    monkeypatch.setattr(production.db, "set_idea_status",
                        lambda i, s, from_status=None: moves.append((i, s, from_status)) or i != 2)
    assert production._pass_untapped([1, 2]) == 1  # 2 was tapped meanwhile; 9 is not ours
    # "expired" since 2026-11-12 (design 8.5): not tapping is not a verdict on the story.
    assert moves == [(1, "expired", "pending"), (2, "expired", "pending")]


def test_make_on_demand_passes_untapped_ideas_before_production(monkeypatch):
    monkeypatch.setattr(production.config, "validate", lambda: None)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 5}])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas", lambda n, already_pending=0: 0)
    monkeypatch.setattr(production.approval, "send_digest", lambda: 1)
    monkeypatch.setattr(production, "_approval_mode", lambda: "polling")
    order = []
    monkeypatch.setattr(production.approval, "process_responses",
                        lambda **k: order.append("wait") or 0)
    monkeypatch.setattr(production, "_pass_untapped", lambda offered: order.append(("pass", offered)))
    monkeypatch.setattr(production, "run_production",
                        lambda limit=None, only_ids=None: order.append("produce")
                        or {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: None)
    production.make_on_demand(3, 1)
    assert order == ["wait", ("pass", [5]), "produce"]


# --- the format stamp, one row per attempt, "Published" per reel (design 10.1, 8.6) -----------

def _attempts(monkeypatch):
    calls = []
    monkeypatch.setattr(production.db, "start_attempt", lambda idea_id: 1)
    monkeypatch.setattr(production.db, "finish_attempt",
                        lambda attempt_id, **k: calls.append(k))
    return calls


def test_format_stamp_reaches_publish(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    _attempts(monkeypatch)
    seen = {}

    def _publish(v, m, sid):
        seen.update(m)
        return "VID1", "https://www.youtube.com/shorts/VID1"

    monkeypatch.setattr(production.publish_youtube, "publish", _publish)
    production.produce_one(IDEA, str(tmp_path))
    assert seen["format"]["version"] == 1 and seen["format"]["language"] == "en"
    assert seen["format"]["visuals"] == "ai" and seen["audio_language"] == "en"


def test_a_failed_attempt_is_recorded_with_its_stage(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    calls = _attempts(monkeypatch)
    monkeypatch.setattr(production.assembly, "assemble", _raiser(RuntimeError("ffmpeg broke")))
    with pytest.raises(RuntimeError):
        production.produce_one(IDEA, str(tmp_path))
    assert len(calls) == 1 and calls[0]["outcome"] == "failed" and calls[0]["stage"] == "assembly"


def test_a_reel_that_fails_its_check_is_not_uploaded(monkeypatch):
    """Design 11.6: a reel that fails its check is not uploaded; its attempt fails at the check
    with the reason, and its idea goes back to the digest with an alert."""
    statuses = _wire_happy(monkeypatch)
    calls = _attempts(monkeypatch)
    published, alerts, checked = [], [], []
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: published.append(v) or ("VID1", "url"))
    monkeypatch.setattr(gates, "reel_problems", lambda path, seconds: checked.append(
        (os.path.basename(path), seconds)) or ["no audio stream"])
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: [IDEA])
    monkeypatch.setattr(production, "_notify_failure",
                        lambda idea, e, spend=None: alerts.append(f"{type(e).__name__}: {e}"))
    result = production.run_production()
    assert published == [] and checked == [("reel_final.mp4", 30.0)]
    assert calls[0]["outcome"] == "failed" and calls[0]["stage"] == "check"
    assert "no audio stream" in calls[0]["reason"]
    assert (7, "pending") in statuses
    assert alerts == ["ReelCheckFailed: no audio stream"]
    assert result["failed"][0]["error"] == "ReelCheckFailed: no audio stream"


def test_a_held_picture_does_not_stop_todays_format(monkeypatch, tmp_path, caplog):
    """Review 4a I-1: today's formats can hold a picture still (a Ken Burns move that has ended,
    replayed when an image fetch failed) under a held Hinglish sentence. That stretch is logged;
    the reel ships, as it did before the check."""
    _wire_happy(monkeypatch)
    published = []
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: published.append(v) or ("VID1", "url"))
    monkeypatch.setattr(gates, "reel_problems",
                        lambda path, seconds: ["black: 1.2 s", "frozen: 3.0 s"])
    with caplog.at_level("WARNING", logger="production"):
        production.produce_one(IDEA, str(tmp_path))
    assert len(published) == 1
    assert any("frozen: 3.0 s" in r.getMessage() for r in caplog.records)


def test_a_blocked_attempt_is_recorded(monkeypatch, tmp_path):
    _wire_happy(monkeypatch, factcheck_ok=False)
    calls = _attempts(monkeypatch)
    with pytest.raises(production.FactCheckFailed):
        production.produce_one(IDEA, str(tmp_path))
    assert calls[0]["outcome"] == "blocked" and calls[0]["stage"] == "factcheck"


def test_bookkeeping_failure_never_costs_a_reel(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.db, "start_attempt", _raiser(RuntimeError("db down")))
    vid, _url = production.produce_one(IDEA, str(tmp_path))
    assert vid == "VID1"


def test_published_is_sent_as_each_reel_goes_live(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    _attempts(monkeypatch)
    ideas = [dict(IDEA, id=7), dict(IDEA, id=8)]
    monkeypatch.setattr(production.db, "get_approved_ideas", lambda: ideas)
    monkeypatch.setattr(production, "_work_root", lambda: str(tmp_path))
    events = []
    monkeypatch.setattr(production, "_notify", lambda text: events.append(("notify", text)))
    real = production.produce_one

    def _tracked(idea, root, report=None):
        events.append(("start", idea["id"]))
        return real(idea, root)

    monkeypatch.setattr(production, "produce_one", _tracked)
    production.run_production()
    assert events[:3] == [("start", 7), ("notify", "✅ Published: https://www.youtube.com/shorts/VID1"),
                          ("start", 8)]


def test_untapped_ideas_expire(monkeypatch):
    """An idea the operator simply did not tap was banned from the digest for 10 days as
    'passed'; it now ends 'expired', which the story de-duplication ignores (design 8.5)."""
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [{"id": 5}, {"id": 6}])
    set_to = []
    monkeypatch.setattr(production.db, "set_idea_status",
                        lambda i, s, from_status=None: set_to.append((i, s, from_status)) or True)
    assert production._pass_untapped([5]) == 1
    assert set_to == [(5, "expired", "pending")]


def test_the_recheck_sees_the_repaired_title(monkeypatch, tmp_path):
    """The re-check used the original title, so a title the repair fixed was never verified."""
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: dict(SCRIPT))
    verdicts, titles = iter([_BLOCK, _OK]), []

    def _verify(body, sources=None, title="", on_screen=None):
        titles.append(title)
        return next(verdicts)

    monkeypatch.setattr(production.factcheck, "verify", _verify)
    monkeypatch.setattr(production.scriptwriter, "repair_script",
                        lambda body, f, topic=None, title=None, **_:
                        {"script_body": "FIXED BODY", "title": "Fixed title"})
    stored, published = [], []
    monkeypatch.setattr(production.db, "update_script_title", lambda sid, t: stored.append(t))
    monkeypatch.setattr(production.publish_youtube, "publish", lambda v, m, sid: published.append(
        m["title"]) or ("VID1", "https://www.youtube.com/shorts/VID1"))
    production.produce_one(IDEA, str(tmp_path))
    assert titles[1] == "Fixed title" and stored == ["Fixed title"]
    assert published == ["Fixed title"]


def test_the_grounding_is_stored_next_to_the_verdict(monkeypatch, tmp_path):
    """Design 9.7: what grounding did for the draft and the gate is kept on the script row."""
    _wire_happy(monkeypatch)
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "grounding": {"draft_citations": 3}})
    monkeypatch.setattr(production.factcheck, "verify",
                        lambda *a, **k: {**_OK, "citations": [5, 4]})
    stored = []
    monkeypatch.setattr(production.db, "set_script_grounding", lambda sid, g: stored.append((sid, g)))
    production.produce_one(IDEA, str(tmp_path))
    assert stored == [(SCRIPT["script_id"], {"draft_citations": 3, "gate_citations": [5, 4]})]


# --- stage 1b: hashtags, tags, footer, category (design 9.9) --------------------------------

def test_hashtags_are_three_at_most_on_the_last_line():
    script = {"title": "T", "caption": "Line one.\nLine two.",
              "hashtags": ["#ISRO", "#Shorts", "#viral", "#Gaganyaan", "#Space"],
              "tags": ["isro launch"]}
    meta = production._build_metadata({"title": "ISRO launch", "niche": "space"}, script)
    assert meta["description"].endswith("\n\n#ISRO #Gaganyaan #ButItMatters")
    assert meta["tags"] == ["isro launch", "But It Matters"]
    assert production._hashtag_line(["#Space-X", "#fyp", "#ButItMatters", "#Mars"]) == \
        "#Mars #ButItMatters"


def test_tags_are_six_from_the_writer_plus_the_brand():
    tags = ["ISRO", "Gaganyaan", "इसरो", "isro rocket", "reusable rocket", "space India",
            "launch cost", "Sriharikota"]
    script = {"title": "T", "caption": "c", "hashtags": [], "tags": tags}
    meta = production._build_metadata({"title": "Rupee hits a record low"}, script)
    assert meta["tags"] == tags[:6] + ["But It Matters"]


def test_the_footer_makes_no_every_day_claim():
    assert "every day" not in production._DEFAULT_FOOTER.lower()
    assert "#" not in production._DEFAULT_FOOTER and "\n" not in production._DEFAULT_FOOTER


def test_the_category_follows_the_story():
    script = {"title": "T", "caption": "c", "hashtags": [], "tags": []}
    for niche, category in (("tech", "28"), ("science", "28"), ("space", "28"),
                            ("india-politics", "25"), ("money", "25"), (None, "25")):
        meta = production._build_metadata({"title": "T", "niche": niche}, script)
        assert meta["category_id"] == category, niche



def test_the_recheck_sees_the_repaired_description_and_cards(monkeypatch, tmp_path):
    """Design 9.6: the re-check uses the repaired description too. The description's first line
    restates the claim, so a false main claim left there blocked the re-check every time."""
    _wire_happy(monkeypatch)
    caption = ("Old line.\n\nSources:\nexample.org: https://example.org/a\n\n"
               "AI-generated narration, images and music.")
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: {
        **SCRIPT, "caption": caption, "key_points": ["Old card"], "payoff": "P sentence here."})
    verdicts, screens, asked = iter([_BLOCK, _OK]), [], {}

    def _verify(body, sources=None, title="", on_screen=None):
        screens.append(on_screen)
        return next(verdicts)

    def _repair(body, findings, **k):
        asked.update(k)
        return {"script_body": "FIXED BODY", "title": k.get("title"), "summary": "New line.",
                "key_points": ["New card"], "payoff": None}

    monkeypatch.setattr(production.factcheck, "verify", _verify)
    monkeypatch.setattr(production.scriptwriter, "repair_script", _repair)
    stored, published = [], []
    monkeypatch.setattr(production.db, "update_script_caption", lambda sid, c: stored.append(c))
    monkeypatch.setattr(production.publish_youtube, "publish", lambda v, m, sid: published.append(
        m["description"]) or ("VID1", "https://www.youtube.com/shorts/VID1"))
    production.produce_one(IDEA, str(tmp_path))
    assert asked["summary"] == "Old line." and asked["key_points"] == ["Old card"]
    assert asked["payoff"] == "P sentence here."
    assert screens[1] == ["New card", "New line."]
    assert stored and stored[0].startswith("New line.")
    assert published[0].startswith("New line.")


# --- stage 2: Hinglish reels behind NARRATION_LANGUAGE, English as the fallback (design 7.6) ---

_SPOKEN = {"language": "hi", "said": "ISRO का rocket अब खुद land करता है।",
           "lines": [{"en": "ISRO's rocket lands itself.", "hi": "ISRO का rocket अब खुद land करता है।",
                      "said": "ISRO का rocket अब खुद land करता है।", "parts": []}],
           "renderer": "claude", "checker": "gemini"}


def _hinglish_wiring(monkeypatch, spoken=(_SPOKEN, ""), hindi_voice_ok=True):
    _wire_happy(monkeypatch)
    monkeypatch.setenv("NARRATION_LANGUAGE", "hinglish")
    monkeypatch.setattr(production.scriptwriter, "write_script", lambda idea, **k: dict(SCRIPT))
    seen = {"voiced": [], "notes": [], "stored": [], "meta": None, "attempt": None}
    monkeypatch.setattr(production.hinglish, "to_hinglish", lambda body, title, tone: spoken)

    def _synth(body, d, meta=None, tone=None, expected_seconds=None):
        seen["voiced"].append((body, expected_seconds))
        if "का" in body and not hindi_voice_ok:
            raise RuntimeError("voice: no Hindi-capable voice succeeded")
        if meta is not None:
            meta.update(engine="gemini", voice="gemini:x@vertex",
                        **({"route": "hi"} if "का" in body else {}))
        return "a.wav", 30.0

    monkeypatch.setattr(production.voice, "synthesize", _synth)
    monkeypatch.setattr(production.subtitles, "burn_hinglish",
                        lambda v, a, o, lines, **k: seen.update(hinglish_lines=lines) or o)
    monkeypatch.setattr(production.subtitles, "burn_captions",
                        lambda v, a, o, **k: seen.update(english_captions=True) or o)
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: seen.update(meta=m) or ("VID1", "https://y/VID1"))
    monkeypatch.setattr(production, "_notify", seen["notes"].append)
    monkeypatch.setattr(production.db, "set_script_spoken",
                        lambda sid, rec: seen["stored"].append(rec))
    monkeypatch.setattr(production.db, "finish_attempt",
                        lambda *a, **k: seen.update(attempt=k))
    return seen


def test_english_is_unchanged_by_default(monkeypatch, tmp_path):
    _wire_happy(monkeypatch)
    monkeypatch.delenv("NARRATION_LANGUAGE", raising=False)
    monkeypatch.setattr(production.hinglish, "to_hinglish",
                        lambda *a: pytest.fail("no Hinglish without NARRATION_LANGUAGE"))
    monkeypatch.setattr(production.db, "set_script_spoken",
                        lambda *a: pytest.fail("nothing stored on an English-only run"))
    meta = {}
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: meta.update(m) or ("VID1", "https://y/VID1"))
    production.produce_one(IDEA, str(tmp_path))
    assert meta["audio_language"] == "en" and meta["format"]["language"] == "en"


def test_a_hinglish_reel_is_voiced_captioned_and_uploaded_as_hindi(monkeypatch, tmp_path):
    seen = _hinglish_wiring(monkeypatch)
    production.produce_one(IDEA, str(tmp_path))
    body, expected = seen["voiced"][0]
    assert body == _SPOKEN["said"] and len(seen["voiced"]) == 1
    assert expected == pytest.approx(40 / 2.2)  # SCRIPT's 40 English words at 2.2 a second
    assert seen["hinglish_lines"] == _SPOKEN["lines"] and "english_captions" not in seen
    assert seen["meta"]["audio_language"] == "hi" and seen["meta"]["format"]["language"] == "hi"
    assert seen["stored"] == [_SPOKEN] and seen["notes"] == []
    assert "english-narration" not in (seen["attempt"]["downgrades"] or [])


def test_a_hinglish_render_failure_narrates_in_english_and_says_so(monkeypatch, tmp_path):
    seen = _hinglish_wiring(monkeypatch, spoken=(None, "two renderings failed their checks"))
    production.produce_one(IDEA, str(tmp_path))
    assert seen["voiced"] == [(SCRIPT["script_body"], None)]
    assert seen["english_captions"] and seen["meta"]["audio_language"] == "en"
    assert "english-narration" in seen["attempt"]["downgrades"]
    assert any("English" in n and "two renderings failed" in n for n in seen["notes"])
    assert seen["stored"] == [{"language": "en", "reason": "two renderings failed their checks"}]


def test_no_hindi_voice_narrates_in_english(monkeypatch, tmp_path):
    seen = _hinglish_wiring(monkeypatch, hindi_voice_ok=False)
    production.produce_one(IDEA, str(tmp_path))
    assert [b for b, _e in seen["voiced"]] == [_SPOKEN["said"], SCRIPT["script_body"]]
    assert seen["meta"]["audio_language"] == "en" and seen["english_captions"]
    assert "english-narration" in seen["attempt"]["downgrades"]
    assert any("English" in n for n in seen["notes"])
    assert seen["stored"][0]["language"] == "en" and "Hindi" in seen["stored"][0]["reason"]


def _spend_events(monkeypatch, line="🎞️ AI video this run: 1 clip, $0.18; $0.18 this month."):
    """Record the opening sweep, production and the close (the closing sweep and the spend line,
    ai_video.close_run), in order (design 6.7, 6.8)."""
    events, notes = [], []
    monkeypatch.setattr(production.ai_video, "sweep", lambda: events.append("sweep") or {})
    monkeypatch.setattr(production.ai_video, "close_run",
                        lambda since: events.append(("close", since)) or line)
    monkeypatch.setattr(production, "run_production", lambda limit=None, only_ids=None:
                        events.append("produce") or {"published": [], "failed": []})
    monkeypatch.setattr(production, "_notify", lambda t: notes.append(t))
    monkeypatch.setattr(production.config, "validate", lambda: None)
    return events, notes


def _order(events) -> list[str]:
    return [e if isinstance(e, str) else e[0] for e in events]


def test_both_entry_points_sweep_before_and_after_and_report_spend(monkeypatch):
    from datetime import datetime, timedelta, timezone

    events, notes = _spend_events(monkeypatch)
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n, already_pending=0: 1)
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)

    production.make_on_demand(num_ideas=1, wait_minutes=1)
    assert _order(events) == ["sweep", "produce", "close"]
    since = events[-1][1]
    assert since.tzinfo is not None
    assert abs(datetime.now(timezone.utc) - since) < timedelta(minutes=1)
    assert notes[-1].startswith("🎞️ AI video this run")

    events.clear()
    monkeypatch.setattr(production, "ensure_ideas_and_digest", lambda: 0)
    production.run()
    assert _order(events) == ["sweep", "produce", "close"]
    assert notes[-1].startswith("🎞️ AI video this run")


def test_no_spend_line_is_sent_when_nothing_was_bought(monkeypatch):
    events, notes = _spend_events(monkeypatch, line=None)
    monkeypatch.setattr(production, "ensure_ideas_and_digest", lambda: 0)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    production.run()
    assert _order(events) == ["sweep", "produce", "close"]
    assert not any("AI video" in n for n in notes)


# --- stage 3b: AI-video reels behind VISUAL_SOURCE=ai_video (design 6.1, 6.4, 6.8, 9.9) ----------

def _shots(video: int = 6, planned: int = 6, spend: float = 0.945, problems=None):
    return production.ai_video.Shots(
        files=[f"s{i}.mp4" for i in range(6)], kinds=["video"] * video + ["still"] * (6 - video),
        cuts=["CUTS"], planned_video=planned, spend_usd=spend,
        problems=list(problems or []))


def _ai_video_wiring(monkeypatch, shots=None, preflight_ok=True):
    """The chain with VISUAL_SOURCE=ai_video; make_shots answers `shots`, or raises NoShots when
    `shots` is an exception. Returns what each step was handed."""
    _wire_happy(monkeypatch)
    monkeypatch.setenv("VISUAL_SOURCE", "ai_video")
    seen = {"req": None, "assemble": None, "burn": None, "broll": None, "notes": [],
            "attempt": None, "meta": None}
    monkeypatch.setattr(production.subtitles, "pauses", lambda audio: [(1.0, 1.2)])
    monkeypatch.setattr(production.subtitles, "preflight",
                        lambda *a, **k: seen.update(preflight=(a, k)) or preflight_ok)

    def make_shots(req):
        seen["req"] = req
        if isinstance(shots, Exception):
            raise shots
        return shots or _shots(problems=["🎞️ a problem"])

    monkeypatch.setattr(production.ai_video, "make_shots", make_shots)
    monkeypatch.setattr(production.ai_video, "reel_line",
                        lambda s: f"🎞️ AI video: {s.video} of {len(s.files)} shots")
    monkeypatch.setattr(production.assembly, "assemble",
                        lambda a, c, o, **k: seen.update(assemble=(c, k)) or o)
    monkeypatch.setattr(production.subtitles, "burn_captions",
                        lambda v, a, o, **k: seen.update(burn=k) or o)

    def broll(kw, dur, d, setting=None, meta=None, source=None):
        seen["broll"] = source
        meta.update(source="ai", clips=4)
        return ["c1.mp4"]

    monkeypatch.setattr(production.visuals, "fetch_broll", broll)
    monkeypatch.setattr(production.publish_youtube, "publish",
                        lambda v, m, sid: seen.update(meta=m) or ("VID1", "https://y/VID1"))
    monkeypatch.setattr(production, "_notify", seen["notes"].append)
    monkeypatch.setattr(production.db, "finish_attempt", lambda *a, **k: seen.update(attempt=k))
    monkeypatch.setattr(production, "_seconds_left", lambda: 1000.0)
    return seen


def test_an_ai_video_reel_with_a_frozen_stretch_is_not_uploaded(monkeypatch, tmp_path):
    """Review 4a I-1: in an ai_video reel every clip passed its own check and every still moves,
    so a black or frozen stretch means something broke."""
    seen = _ai_video_wiring(monkeypatch)
    monkeypatch.setattr(gates, "reel_problems", lambda path, seconds: ["frozen: 3.0 s"])
    with pytest.raises(production.ReelCheckFailed, match="frozen: 3.0 s"):
        production.produce_one(IDEA, str(tmp_path))
    assert seen["meta"] is None and seen["attempt"]["stage"] == "check"


def test_an_ai_video_reel_on_the_ai_path_ships_with_a_held_picture(monkeypatch, tmp_path):
    seen = _ai_video_wiring(monkeypatch, shots=production.ai_video.NoShots("no picture"))
    monkeypatch.setattr(gates, "reel_problems", lambda path, seconds: ["frozen: 2.4 s"])
    production.produce_one(IDEA, str(tmp_path))
    assert seen["meta"] is not None  # uploaded


def test_ai_video_reels_use_the_shots(monkeypatch, tmp_path):
    import time

    seen = _ai_video_wiring(monkeypatch)
    report = {}
    before = time.monotonic()
    production.produce_one(IDEA, str(tmp_path), report)
    req = seen["req"]
    assert (req.idea_id, req.audio_path, req.duration, req.pauses) == (7, "a.mp3", 30.0,
                                                                      [(1.0, 1.2)])
    assert req.can_buy and req.story.startswith("ISRO rocket, explained")
    assert before + 1000 - 240 <= req.deadline <= time.monotonic() + 1000 - 240
    clips, kw = seen["assemble"]
    assert clips == [f"s{i}.mp4" for i in range(6)] and kw == {"cuts": ["CUTS"], "fps": 24}
    assert seen["burn"]["fps"] == 24
    fmt = seen["meta"]["format"]
    assert (fmt["visuals"], fmt["video_shots"], fmt["shots"]) == ("ai_video", 6, 6)
    assert seen["attempt"]["spend_usd"] == pytest.approx(0.945)
    assert seen["attempt"]["downgrades"] == []
    assert report == {"ai_video": "🎞️ AI video: 6 of 6 shots", "spend_usd": 0.945}
    assert "🎞️ a problem" in seen["notes"]


def test_no_shots_falls_back_to_the_ai_path(monkeypatch, tmp_path):
    seen = _ai_video_wiring(monkeypatch, shots=production.ai_video.NoShots("no picture"))
    production.produce_one(IDEA, str(tmp_path))
    assert seen["broll"] == "ai"
    clips, kw = seen["assemble"]
    assert clips == ["c1.mp4"] and kw == {}  # today's 30 fps render, no cut list
    assert "fps" not in seen["burn"]
    assert "ai-path" in seen["attempt"]["downgrades"]
    assert seen["meta"]["format"]["visuals"] == "ai"


def test_fewer_video_shots_than_planned_is_a_downgrade(monkeypatch, tmp_path):
    seen = _ai_video_wiring(monkeypatch, shots=_shots(video=4, planned=6, spend=0.63))
    production.produce_one(IDEA, str(tmp_path))
    assert seen["attempt"]["downgrades"] == ["still-shots"]


def test_the_disclosure_follows_what_was_shown(monkeypatch, tmp_path):
    seen = _ai_video_wiring(monkeypatch, shots=production.ai_video.NoShots("no picture"))
    caption = f"A claim.\n\n{production.scriptwriter.DISCLOSURE_LINE_AI_VIDEO}"
    monkeypatch.setattr(production.scriptwriter, "write_script",
                        lambda idea, **k: {**SCRIPT, "caption": caption})
    production.produce_one(IDEA, str(tmp_path))
    description = seen["meta"]["description"]
    assert production.scriptwriter.DISCLOSURE_LINE_AI in description
    assert production.scriptwriter.DISCLOSURE_LINE_AI_VIDEO not in description


def test_a_reel_without_a_clip_discloses_images(monkeypatch, tmp_path):
    """An ai_video reel that bought nothing (no key, say) shows stills: its description must not
    say "video". One clip is enough to say it."""
    caption = f"A claim.\n\n{production.scriptwriter.DISCLOSURE_LINE_AI_VIDEO}"
    for video, line in ((0, production.scriptwriter.DISCLOSURE_LINE_AI),
                        (1, production.scriptwriter.DISCLOSURE_LINE_AI_VIDEO)):
        seen = _ai_video_wiring(monkeypatch, shots=_shots(video=video, spend=0.0))
        monkeypatch.setattr(production.scriptwriter, "write_script",
                            lambda idea, **k: {**SCRIPT, "caption": caption})
        production.produce_one(IDEA, str(tmp_path))
        assert line in seen["meta"]["description"]


def test_a_failed_preflight_buys_nothing(monkeypatch, tmp_path):
    seen = _ai_video_wiring(monkeypatch, preflight_ok=False)
    production.produce_one(IDEA, str(tmp_path))
    assert seen["req"].can_buy is False


def test_published_and_failed_lines_carry_the_spend(monkeypatch):
    monkeypatch.setattr(production.db, "get_approved_ideas",
                        lambda: [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
    monkeypatch.setattr(production.db, "set_idea_status", lambda i, s, from_status=None: None)
    notes, alerts = [], []
    monkeypatch.setattr(production, "_notify", notes.append)
    monkeypatch.setattr(production.approval, "_api",
                        lambda method, **params: alerts.append(params["text"]))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def produce(idea, root, report=None):
        if idea["id"] == 1:
            report.update(ai_video="🎞️ AI video: 6 of 6 shots, $0.95", spend_usd=0.945)
            return "V1", "https://y/V1"
        report.update(spend_usd=0.4725)
        raise RuntimeError("assembly: ffmpeg failed")

    monkeypatch.setattr(production, "produce_one", produce)
    production.run_production()
    assert "✅ Published: https://y/V1\n🎞️ AI video: 6 of 6 shots, $0.95" in notes
    assert len(alerts) == 1 and "Reel failed" in alerts[0] and "$0.47" in alerts[0]


def test_both_entry_points_begin_the_run(monkeypatch):
    events, _notes = _spend_events(monkeypatch)
    monkeypatch.setattr(production.ai_video, "begin_run", lambda: events.append("begin"))
    monkeypatch.setattr(production.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(production.ideation_fallback, "seed_ideas",
                        lambda n, already_pending=0: 1)
    monkeypatch.setattr(production.approval, "send_digest", lambda: None)
    monkeypatch.setattr(production.approval, "process_responses", lambda **k: 0)
    production.make_on_demand(num_ideas=1, wait_minutes=1)
    assert _order(events)[:2] == ["begin", "sweep"]
    events.clear()
    monkeypatch.setattr(production, "ensure_ideas_and_digest", lambda: 0)
    production.run()
    assert _order(events)[:2] == ["begin", "sweep"]


def test_settings_defaults(monkeypatch):
    import re

    monkeypatch.delenv("REEL_BUDGET_MINUTES", raising=False)
    assert production._reel_seconds() == 840
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = ("AI_VIDEO_MODEL", "AI_VIDEO_BUDGET_USD", "AI_VIDEO_TIMEOUT_SECONDS",
             "AI_VIDEO_GRACE_SECONDS", "AI_VIDEO_TAIL_SECONDS", "AI_VIDEO_CUTS", "AI_VIDEO_STYLE")
    for flow, step in (("make-short.yml", 85), ("production.yml", 55)):
        with open(os.path.join(root, ".github", "workflows", flow), encoding="utf-8") as f:
            text = f.read()
        # The Python step's own limit, not the job's: _seconds_left() must never be later than
        # the real kill (design 6.4).
        assert int(re.search(r"(?m)^ {8}timeout-minutes:\s*(\d+)", text).group(1)) == step
        assert re.search(r"JOB_TIMEOUT_MINUTES:\s*'(\d+)'", text).group(1) == str(step)
        for name in names:
            assert f"{name}: ${{{{ vars.{name}" in text, (flow, name)
    with open(os.path.join(root, ".env.example"), encoding="utf-8") as f:
        example = f.read()
    assert all(f"\n{name}=" in example for name in names)


def test_a_reel_on_the_ai_path_says_so_under_published(monkeypatch, tmp_path):
    """Design 6.8: a reel that shipped with fewer video shots than planned is told, with the
    count. One that could not have its shots at all shipped with none: its Published line says
    so and why, instead of saying nothing."""
    _ai_video_wiring(monkeypatch, shots=production.ai_video.NoShots("no picture for any shot"))
    report = {}
    production.produce_one(IDEA, str(tmp_path), report)
    line = report["ai_video"]
    assert line.startswith("🎞️ AI video: none") and "NoShots: no picture for any shot" in line
    assert "spend_usd" not in report


def test_no_shots_still_reports_its_spend(monkeypatch, tmp_path):
    """Review I-3: clips paid for before a reel fell back to the ai path are still reported."""
    failure = production.ai_video.NoShots("a still did not render", spend_usd=0.4725,
                                          problems=["🎞️ a problem"])
    seen = _ai_video_wiring(monkeypatch, shots=failure)
    report = {}
    production.produce_one(IDEA, str(tmp_path), report)
    assert report["spend_usd"] == pytest.approx(0.4725) and "$0.47" in report["ai_video"]
    assert "🎞️ a problem" in seen["notes"]
    assert seen["attempt"]["spend_usd"] == pytest.approx(0.4725)
