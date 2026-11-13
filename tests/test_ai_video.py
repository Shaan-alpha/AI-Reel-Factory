"""AI-video shots (design Part A). Stage 3a: the ledger sweep and the run's spend line (6.7, 6.8).

Nothing here reaches Higgsfield or the database: both are replaced per test."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src import ai_video, db, higgsfield

ZERO = {"settled": 0, "left": 0, "errors": 0}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "abc123:def456")


def _ledger(monkeypatch, rows, failing_updates=()) -> list:
    updates = []

    def update(row_id, **fields):
        if row_id in failing_updates:
            raise RuntimeError("statement timeout")
        updates.append((row_id, fields))

    monkeypatch.setattr(db, "open_ai_video_jobs", lambda days=7: rows)
    monkeypatch.setattr(db, "update_ai_video_job", update)
    return updates


def _answers(monkeypatch, answers: dict) -> list:
    asked = []

    def status(request_id):
        asked.append(request_id)
        answer = answers[request_id]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(higgsfield, "status", status)
    return asked


def test_the_sweep_settles_what_it_can(monkeypatch):
    """A failure that belongs to one row (Higgsfield has no such request; the row's write fails)
    leaves that row for the next sweep, and the rows after it are still settled."""
    rows = [{"id": i, "request_id": f"job-000{i}", "status": s, "cost_usd": 0.179}
            for i, s in enumerate(["submitted", "late", "submitted", "late", "submitted",
                                   "submitted", "late"], start=1)]
    _answers(monkeypatch, {
        "job-0001": {"status": "completed", "video": {"url": "https://cdn.example/v1.mp4"}},
        "job-0002": higgsfield.HiggsfieldError("refused", "status -> HTTP 404: not found",
                                               status=404),
        "job-0003": {"status": "failed", "error": "Generation failed"},
        "job-0004": {"status": "completed", "video": {"url": "https://cdn.example/v4.mp4"}},
        "job-0005": {"status": "nsfw"},
        "job-0006": {"status": "canceled"},
        "job-0007": {"status": "in_progress"},
    })
    updates = _ledger(monkeypatch, rows, failing_updates={4})

    assert ai_video.sweep() == {"settled": 4, "left": 1, "errors": 2}
    settled = dict(updates)
    # Completed was paid for: it keeps its quote and gains the URL a later reel may reuse.
    assert settled[1]["status"] == "completed"
    assert settled[1]["result_url"] == "https://cdn.example/v1.mp4"
    assert "cost_usd" not in settled[1]
    for row_id, status in ((3, "failed"), (5, "nsfw"), (6, "canceled")):
        assert (settled[row_id]["status"], settled[row_id]["cost_usd"]) == (status, 0)
    for fields in settled.values():
        assert datetime.fromisoformat(fields["settled_at"]).tzinfo is not None
    assert not {2, 4, 7} & set(settled)  # unreadable, unwritten, still running: next sweep


@pytest.mark.parametrize("kind", ["unavailable", "busy", "funds"])
def test_an_outage_stops_the_sweep(monkeypatch, kind):
    """With Higgsfield down, each remaining row would wait out its 30 s timeout, at the start and
    the end of every run (review I-4): the first failure of the service, not of a row, leaves the
    rest for the next sweep."""
    rows = [{"id": i, "request_id": f"job-000{i}", "status": "submitted"} for i in (1, 2, 3, 4)]
    asked = _answers(monkeypatch, {
        "job-0001": {"status": "completed", "video": {"url": "https://cdn.example/v1.mp4"}},
        "job-0002": higgsfield.HiggsfieldError(kind, "read timed out"),
        "job-0003": {"status": "failed"}, "job-0004": {"status": "failed"}})
    _ledger(monkeypatch, rows)
    assert ai_video.sweep() == {"settled": 1, "left": 2, "errors": 1}
    assert asked == ["job-0001", "job-0002"]


def test_a_reserved_row_is_not_read(monkeypatch):
    """Its submit never answered, so there is no request to read; it stays at its quote."""
    asked = _answers(monkeypatch, {})
    updates = _ledger(monkeypatch, [{"id": 9, "request_id": None, "status": "reserved",
                                     "cost_usd": 0.179}])
    assert ai_video.sweep() == {"settled": 0, "left": 1, "errors": 0}
    assert asked == [] and updates == []


def test_a_refused_key_stops_the_sweep(monkeypatch):
    rows = [{"id": i, "request_id": f"job-000{i}", "status": "submitted"} for i in (1, 2, 3)]
    asked = _answers(monkeypatch, {r["request_id"]: higgsfield.HiggsfieldError("auth", "401")
                                   for r in rows})
    _ledger(monkeypatch, rows)
    assert ai_video.sweep() == {"settled": 0, "left": 2, "errors": 1}
    assert asked == ["job-0001"]


def test_no_key_or_no_table_means_no_sweep(monkeypatch):
    read = []
    monkeypatch.setattr(db, "open_ai_video_jobs", lambda days=7: read.append(days) or [])
    monkeypatch.delenv("HF_API_KEY")
    assert ai_video.sweep() == ZERO
    assert read == []

    def missing(days=7):
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setenv("HF_API_KEY", "abc123:def456")
    monkeypatch.setattr(db, "open_ai_video_jobs", missing)
    assert ai_video.sweep() == ZERO

    def broken(days=7):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "open_ai_video_jobs", broken)
    assert ai_video.sweep() == ZERO


def test_spend_line(monkeypatch):
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    rows = ([{"status": "completed", "cost_usd": 0.179}] * 4
            + [{"status": "late", "cost_usd": "0.1790"}, {"status": "reserved", "cost_usd": 0.179},
               {"status": "failed", "cost_usd": 0}, {"status": "refused", "cost_usd": 0}])
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: rows if s == since else [])
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 14.3)
    assert ai_video.spend_line(since) == (
        "🎞️ AI video this run: 6 clips, $1.07 (2 paid, not used); $14.30 this month.")

    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: [{"status": "completed",
                                                               "cost_usd": 0.179}])
    assert ai_video.spend_line(since) == "🎞️ AI video this run: 1 clip, $0.18; $14.30 this month."


def test_the_closing_sweep_keeps_paid_not_used(monkeypatch):
    """Review I-2: after the last reel the sweep settles this run's late clips. One that has since
    finished becomes `completed`, which reads as used, so what was not used is taken from the
    ledger as it stood before the sweep; one that failed costs nothing and drops out."""
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    before = [{"id": 1, "status": "completed", "cost_usd": 0.179},
              {"id": 2, "status": "late", "cost_usd": 0.179},
              {"id": 3, "status": "late", "cost_usd": 0.179},
              {"id": 4, "status": "reserved", "cost_usd": 0.179}]
    after = [{"id": 1, "status": "completed", "cost_usd": 0.179},
             {"id": 2, "status": "completed", "cost_usd": 0.179},  # finished after its reel
             {"id": 3, "status": "failed", "cost_usd": 0},  # never charged
             {"id": 4, "status": "reserved", "cost_usd": 0.179}]  # may have been charged
    reads, events = [before, after], []
    monkeypatch.setattr(db, "ai_video_jobs_since",
                        lambda s: events.append("read") or reads.pop(0))
    monkeypatch.setattr(ai_video, "sweep", lambda: events.append("sweep") or dict(ZERO))
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 2.0)
    assert ai_video.close_run(since) == (
        "🎞️ AI video this run: 3 clips, $0.54 (2 paid, not used); $2.00 this month.")
    assert events == ["read", "sweep", "read"]


def test_close_run_needs_the_key_and_the_ledger(monkeypatch):
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    events = []
    monkeypatch.setattr(ai_video, "sweep", lambda: events.append("sweep") or dict(ZERO))

    def missing(s):
        events.append("read")
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setattr(db, "ai_video_jobs_since", missing)
    assert ai_video.close_run(since) is None
    assert events == ["read"]  # no table: nothing to sweep either, and nothing raised

    events.clear()
    monkeypatch.delenv("HF_API_KEY")
    assert ai_video.close_run(since) is None
    assert events == []  # no key: nothing can have been bought


def test_no_spend_line_without_purchases_a_key_or_a_ledger(monkeypatch):
    since = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 14.3)
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: [])
    assert ai_video.spend_line(since) is None

    def missing(s):
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setattr(db, "ai_video_jobs_since", missing)
    assert ai_video.spend_line(since) is None

    read = []
    monkeypatch.setattr(db, "ai_video_jobs_since", lambda s: read.append(s) or [])
    monkeypatch.delenv("HF_API_KEY")
    assert ai_video.spend_line(since) is None
    assert read == []  # an English run without the key never reads the ledger


def test_tests_never_reach_higgsfield(monkeypatch):
    """The conftest guard (design 17): Higgsfield is billed per clip, so with requests unpatched
    the client refuses to send at all. The proxy points at a dead port so that, were the guard
    missing, this test would fail on the proxy instead of reaching the real API."""
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    with pytest.raises(RuntimeError, match="Higgsfield"):
        higgsfield.submit(higgsfield.KLING, {"prompt": "p"}, "key-1")


# --- Stage 3b: the shot planner (design 6.5) ------------------------------------------------------

import json  # noqa: E402

from src import llm, visuals  # noqa: E402

SCRIPT = ("Sunita Williams returned to Earth after 286 days in orbit. NASA says [short pause] the "
          "capsule splashed down safely. Here's why it matters: India's own crew flight is next.")
DUR6 = [4.906, 5.0, 3.146, 4.654, 5.0, 4.049]
STYLE = ("Style: cinematic 3D animated film still, stylized shapes, rich saturated color, bright "
         "clear lighting.")


def _req(**kw) -> "ai_video.ReelRequest":
    fields = dict(idea_id=7, script_body=SCRIPT, title="Back after 286 days", tone="plain",
                  setting="India", story="Sunita Williams comes home after 286 days.",
                  audio_path="narr.wav", duration=26.755, pauses=[], work_dir="work",
                  deadline=None)
    fields.update(kw)
    return ai_video.ReelRequest(**fields)


def _shot(i: int, still: str | None = None, search: str | None = "space capsule") -> dict:
    shot = {"still": still or (f"A small white capsule {i} bobs on calm blue water, large and "
                               f"centred, under a bright even sky; all surfaces plain."),
            "motion": "The capsule rocks gently. The water ripples. The camera stays static."}
    if search is not None:
        shot["search"] = search
    return shot


def _reply(shots: list[dict], mood: str = "hopeful, curious") -> str:
    return json.dumps({"mood": mood, "shots": shots})


def _llm(monkeypatch, replies: list) -> list:
    """llm.generate answers from `replies` in turn (an Exception is raised); returns the prompts."""
    prompts = []

    def generate(prompt, **kw):
        prompts.append((prompt, kw))
        reply = replies[min(len(prompts), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "generate", generate)
    return prompts


def test_a_good_plan_is_used(monkeypatch):
    shots = [_shot(i) for i in range(6)]
    shots[3]["still"] = "A capsule on the sea. " * 150  # far over the cap
    prompts = _llm(monkeypatch, [_reply(shots)])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert ok and len(plan) == 6
    assert all(s["still"].endswith(f"{STYLE} Mood: hopeful, curious.") for s in plan)
    assert len(plan[3]["still"]) <= 1800
    assert all(s["motion"] and s["search"] == "space capsule" for s in plan)
    ((prompt, kw),) = prompts
    assert kw.get("json") is True
    assert "SHOTS: 6" in prompt and "4.9 s, 5.0 s, 3.1 s, 4.7 s, 5.0 s, 4.0 s" in prompt
    assert "SETTING: India" in prompt and "[short pause]" not in prompt
    assert "minimal motion" not in prompt  # the somber rule is for somber stories only

    prompts = _llm(monkeypatch, [_reply([_shot(i) for i in range(6)], mood="")])
    plan, ok = ai_video.plan_shots(_req(tone="somber"), DUR6)
    assert ok and "calm, symbolic scenes and minimal motion" in prompts[0][0]
    assert plan[0]["still"].endswith("Mood: calm, quiet, respectful.")


def test_ai_video_style_overrides_the_look(monkeypatch):
    monkeypatch.setenv("AI_VIDEO_STYLE", "flat paper-cut collage, soft daylight.")
    _llm(monkeypatch, [_reply([_shot(i) for i in range(6)])])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert ok and plan[0]["still"].endswith(
        "Style: flat paper-cut collage, soft daylight. Mood: hopeful, curious.")


def test_a_name_from_the_story_rejects_the_plan(monkeypatch):
    named = [_shot(i) for i in range(6)]
    named[2]["still"] = "Sunita Williams floating inside a capsule window, centred, bright light."
    prompts = _llm(monkeypatch, [_reply(named), _reply([_shot(i) for i in range(6)])])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert ok and len(prompts) == 2
    assert "Sunita, Williams" in prompts[1][0]  # the offending names, quoted back
    assert not any("Sunita" in s["still"] for s in plan)

    names = ai_video._story_names([SCRIPT, "The Indian team in Delhi watched Earth. India's "
                                           "crew waits."])
    assert {"Sunita", "Williams", "NASA"} <= names
    assert not names & {"India", "Delhi", "Earth", "The", "Indian", "Here"}


def test_a_second_failure_buys_nothing(monkeypatch):
    named = [_shot(i, still="NASA engineers cheer as Sunita Williams waves.") for i in range(6)]
    prompts = _llm(monkeypatch, [_reply(named), _reply(named)])
    monkeypatch.setattr(visuals, "extract_keywords", lambda body, n=5: ["space capsule", "ocean"])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert not ok and len(prompts) == 2
    kws = ["space capsule", "ocean"]
    assert [s["still"] for s in plan] == [visuals._img_prompt(kws[i % 2], i, "India")
                                          for i in range(6)]
    assert {s["motion"] for s in plan} == {ai_video.FALLBACK_MOTION}
    assert [s["search"] for s in plan] == [kws[i % 2] for i in range(6)]


def test_a_broken_reply_buys_nothing(monkeypatch):
    monkeypatch.setattr(visuals, "extract_keywords", lambda body, n=5: ["space capsule"])
    prompts = _llm(monkeypatch, [_reply([_shot(i) for i in range(5)])])  # five, not six, twice
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert not ok and len(prompts) == 2 and len(plan) == 6
    _llm(monkeypatch, [RuntimeError("every provider failed")])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    assert not ok and len(plan) == 6 and plan[0]["motion"] == ai_video.FALLBACK_MOTION


def test_search_words_never_come_from_the_still(monkeypatch):
    shots = [_shot(i, search=None) for i in range(6)]
    shots[1]["search"] = "  "
    _llm(monkeypatch, [_reply(shots)])
    plan, ok = ai_video.plan_shots(_req(), DUR6)
    words = visuals._keywords_heuristic(ai_video._plain(SCRIPT), 6)
    assert ok and [s["search"] for s in plan] == [words[i % len(words)] for i in range(6)]


# --- Stage 3b: a picture for every shot (design 6.2 step 5, 6.9) ----------------------------------

import os  # noqa: E402
import re  # noqa: E402

PLAN6 = [{"still": f"Still prompt {i}: a capsule on the sea.", "motion": "It rocks.",
          "search": f"search words {i}"} for i in range(6)]


def _draws(monkeypatch, klein=(), schnell=(), photos=()) -> dict:
    """visuals.ai_still and stock_photo replaced: shot i is drawn by klein or schnell, or found
    as a stock photo, when its index is in that set. Returns what was asked."""
    asked = {"still": [], "photo": []}

    def ai_still(prompt, dest, seed):
        i = int(re.search(r"(\d+)\.\w+$", dest).group(1))
        asked["still"].append((i, prompt, seed))
        if i in klein or i in schnell:
            with open(dest, "wb") as f:
                f.write(b"img")
            return "klein" if i in klein else "schnell"
        return None

    def stock_photo(query, dest, variant, index):
        asked["photo"].append((index, query, variant))
        if index in photos:
            with open(dest, "wb") as f:
                f.write(b"img")
            return True
        return False

    monkeypatch.setattr(visuals, "ai_still", ai_still)
    monkeypatch.setattr(visuals, "stock_photo", stock_photo)
    return asked


def test_only_a_klein_still_is_animatable(monkeypatch, tmp_path):
    asked = _draws(monkeypatch, klein={0, 1, 2}, schnell={3, 4, 5})
    pics = ai_video._pictures(_req(work_dir=str(tmp_path)), PLAN6)
    assert [p.animatable for p in pics] == [True, True, True, False, False, False]
    assert all(os.path.exists(p.path) for p in pics)
    assert sorted((i, seed) for i, _prompt, seed in asked["still"]) == [
        (i, visuals._image_seed("idea_7", i)) for i in range(6)]
    assert asked["photo"] == []


def test_a_shot_without_ai_falls_back_to_its_search_words(monkeypatch, tmp_path):
    asked = _draws(monkeypatch, klein={0, 1, 2, 4, 5}, photos={3})
    pics = ai_video._pictures(_req(work_dir=str(tmp_path)), PLAN6)
    assert asked["photo"] == [(3, "search words 3", "idea_7")]  # never the still prompt
    assert not pics[3].animatable and pics[3].path not in {p.path for p in pics[:3]}


def test_a_shot_with_nothing_borrows_its_neighbour(monkeypatch, tmp_path):
    _draws(monkeypatch, klein={1, 2, 4, 5})
    pics = ai_video._pictures(_req(work_dir=str(tmp_path)), PLAN6)
    assert pics[3].path == pics[2].path and not pics[3].animatable
    assert pics[0].path == pics[1].path and not pics[0].animatable
    assert pics[1].animatable and pics[2].animatable


def test_no_picture_at_all_is_no_shots(monkeypatch, tmp_path):
    _draws(monkeypatch)
    with pytest.raises(ai_video.NoShots):
        ai_video._pictures(_req(work_dir=str(tmp_path)), PLAN6)


def test_a_still_clip_covers_its_shot_at_24_fps(monkeypatch, tmp_path):
    made = []
    monkeypatch.setattr(visuals, "_image_to_kenburns_clip",
                        lambda image, dest, seconds, index=0, fps=30: made.append(
                            (image, dest, seconds, index, fps)))
    pic = ai_video.Picture(str(tmp_path / "still_02.jpg"), True)
    out = ai_video._still_clip(pic, str(tmp_path / "shot_02.mp4"), 4.654, 2)
    assert out == str(tmp_path / "shot_02.mp4")
    assert made == [(pic.path, out, pytest.approx(4.754), 2, 24)]
