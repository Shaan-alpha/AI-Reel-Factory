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


# --- Stage 3b: buying the clips (design 6.2 step 7, 6.4) -----------------------------------------

PRICE = 0.1575  # the live check of 2026-11-13: $0.0315 a second at 720p, 5 s a clip


class _Clock:
    """A fake monotonic clock that only moves when the code under test sleeps."""

    def __init__(self, start: float = 1000.0):
        self.now, self.slept = start, []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


@pytest.fixture
def fresh_run(monkeypatch):
    """A new run (no latch set) on a fake clock."""
    clock = _Clock()
    monkeypatch.setattr(ai_video, "_clock", clock)
    monkeypatch.setattr(ai_video, "_sleep", clock.sleep)
    ai_video.begin_run()
    yield clock
    ai_video.begin_run()


def _shop(monkeypatch, answers: dict, reserve_fails_at: int | None = None,
          reserve_error: Exception | None = None) -> list:
    """The ledger and Higgsfield replaced. answers[shot] is the list of submit answers, in turn
    (a HiggsfieldError is raised; the last one repeats). Returns every call, in order."""
    events, rows = [], {}

    def reserve(idea_id, shot, endpoint, cost_usd):
        if reserve_fails_at is not None and len(rows) == reserve_fails_at:
            events.append(("reserve-failed", shot))
            raise reserve_error or RuntimeError("insert failed")
        row = {"id": 100 + shot, "idempotency_key": f"key-{shot}"}
        rows[row["id"]] = shot
        events.append(("reserve", shot, endpoint, cost_usd))
        return row

    def update(row_id, **fields):
        events.append(("update", rows[row_id], fields))

    def upload(path, content_type):
        events.append(("upload", path, content_type))
        return f"https://cdn.example/{os.path.basename(path)}"

    asked: dict[int, int] = {}

    def submit(endpoint, args, key):
        shot = int(key.split("-")[1])
        events.append(("submit", shot, dict(args), key))
        turn = asked[shot] = asked.get(shot, 0) + 1
        seq = answers.get(shot, [{"request_id": f"req-{shot:04d}-abcd", "status": "queued"}])
        answer = seq[min(turn, len(seq)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(db, "reserve_ai_video_job", reserve)
    monkeypatch.setattr(db, "update_ai_video_job", update)
    monkeypatch.setattr(higgsfield, "upload", upload)
    monkeypatch.setattr(higgsfield, "submit", submit)
    return events


def _stills(tmp_path, animatable=(0, 1, 2, 3, 4, 5)) -> list:
    pictures = []
    for i in range(6):
        path = tmp_path / f"still_{i:02d}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xe0jpeg")
        pictures.append(ai_video.Picture(str(path), i in animatable))
    return pictures


def _kinds(events) -> list:
    return [(e[0], e[1]) for e in events]


UNANSWERED = higgsfield.HiggsfieldError("unavailable", "submit: ReadTimeout")


def test_video_positions():
    assert ai_video.video_shots(6, 6) == [0, 1, 2, 3, 4, 5]
    assert ai_video.video_shots(7, 6) == [0, 1, 2, 3, 4, 6]
    assert ai_video.video_shots(6, 2) == [0, 5]
    assert ai_video.video_shots(1, 6) == [0]
    assert ai_video.video_shots(6, 0) == []


def test_a_row_is_reserved_before_anything_is_sent(monkeypatch, tmp_path, fresh_run):
    events = _shop(monkeypatch, {})
    pictures = _stills(tmp_path)
    jobs = ai_video._buy(_req(work_dir=str(tmp_path)), [0, 5], pictures, PLAN6, PRICE,
                         fresh_run.now + 300)
    assert _kinds(events) == [("reserve", 0), ("upload", pictures[0].path), ("submit", 0),
                              ("update", 0), ("reserve", 5), ("upload", pictures[5].path),
                              ("submit", 5), ("update", 5)]
    assert events[0][2:] == (higgsfield.KLING, PRICE)
    assert events[1][2] == "image/jpeg"
    _kind, _shot, body, key = events[2]
    assert key == "key-0" and body == {"prompt": PLAN6[0]["motion"],
                                       "image_url": "https://cdn.example/still_00.jpg",
                                       "duration": 5, "negative_prompt": ai_video.NEGATIVE}
    assert events[3][2] == {"request_id": "req-0000-abcd", "status": "submitted"}
    assert [(j.shot, j.status, j.cost, j.request_id) for j in jobs] == [
        (0, "submitted", PRICE, "req-0000-abcd"), (5, "submitted", PRICE, "req-0005-abcd")]


def test_a_failed_reserve_buys_nothing_more(monkeypatch, tmp_path, fresh_run):
    events = _shop(monkeypatch, {}, reserve_fails_at=1)
    jobs = ai_video._buy(_req(work_dir=str(tmp_path)), [0, 1, 5], _stills(tmp_path), PLAN6,
                         PRICE, fresh_run.now + 300)
    assert [j.shot for j in jobs] == [0]
    assert _kinds(events)[-1] == ("reserve-failed", 5)  # the reel's last shot is bought second
    assert not ai_video._stop_buying()  # one failed insert is this reel's, not the run's

    events = _shop(monkeypatch, {}, reserve_fails_at=0,
                   reserve_error=db.LedgerUnavailable("ai_video_jobs is missing"))
    assert ai_video._buy(_req(work_dir=str(tmp_path)), [0, 1], _stills(tmp_path), PLAN6, PRICE,
                         fresh_run.now + 300) == []
    assert ai_video._stop_buying()  # no table: nothing is bought for the rest of the run


def test_an_unanswered_submit_is_repeated_with_the_same_key_and_body(monkeypatch, tmp_path,
                                                                     fresh_run):
    answer = {"request_id": "req-0000-abcd", "status": "queued"}
    events = _shop(monkeypatch, {0: [UNANSWERED, UNANSWERED, answer]})
    (job,) = ai_video._buy(_req(work_dir=str(tmp_path)), [0], _stills(tmp_path), PLAN6, PRICE,
                           fresh_run.now + 300)
    submits = [e for e in events if e[0] == "submit"]
    assert len(submits) == 3 and len({(str(e[2]), e[3]) for e in submits}) == 1
    assert [e[0] for e in events].count("upload") == 1
    assert fresh_run.slept == [2, 4]
    assert (job.status, job.request_id, job.ambiguous) == ("submitted", "req-0000-abcd", True)

    events = _shop(monkeypatch, {0: [UNANSWERED]})
    (job,) = ai_video._buy(_req(work_dir=str(tmp_path)), [0], _stills(tmp_path), PLAN6, PRICE,
                           fresh_run.now + 20)
    assert (job.status, job.cost, job.request_id) == ("reserved", PRICE, None)
    assert not [e for e in events if e[0] == "update"]  # it may have been charged: no refund


def test_a_refusal_after_an_unanswered_submit_keeps_the_quote(monkeypatch, tmp_path, fresh_run):
    """Review Focus 2 (3a's I-6): the first submit may have created a charged job, so a refusal
    of the repeat does not make the row free."""
    refused = higgsfield.HiggsfieldError("refused", "submit -> HTTP 422", status=422)
    events = _shop(monkeypatch, {0: [UNANSWERED, refused]})
    (job,) = ai_video._buy(_req(work_dir=str(tmp_path)), [0], _stills(tmp_path), PLAN6, PRICE,
                           fresh_run.now + 300)
    assert (job.status, job.cost) == ("reserved", PRICE)
    assert not [e for e in events if e[0] == "update"]


def test_refusals_cost_nothing(monkeypatch, tmp_path, fresh_run):
    refused = higgsfield.HiggsfieldError("refused", "submit -> HTTP 422", status=422)
    events = _shop(monkeypatch, {0: [refused]})
    jobs = ai_video._buy(_req(work_dir=str(tmp_path)), [0, 5], _stills(tmp_path), PLAN6, PRICE,
                         fresh_run.now + 300)
    assert [(j.shot, j.status, j.cost) for j in jobs] == [(0, "refused", 0.0),
                                                          (5, "submitted", PRICE)]
    update = next(e for e in events if e[0] == "update" and e[1] == 0)[2]
    assert update["status"] == "refused" and update["cost_usd"] == 0 and update["settled_at"]


@pytest.mark.parametrize("kind, status", [("funds", 403), ("auth", 401)])
def test_funds_and_auth_stop_buying_for_the_run(monkeypatch, tmp_path, fresh_run, kind, status):
    stop = higgsfield.HiggsfieldError(kind, f"submit -> HTTP {status}", status=status)
    events = _shop(monkeypatch, {2: [stop]})
    jobs = ai_video._buy(_req(work_dir=str(tmp_path)), [0, 1, 2, 3, 4, 5], _stills(tmp_path),
                         PLAN6, PRICE, fresh_run.now + 300)
    assert [j.shot for j in jobs] == [0, 5, 1, 2]  # shot 0, the last shot, then in order
    assert (jobs[-1].status, jobs[-1].cost) == ("refused", 0.0)
    assert ("reserve", 3) not in _kinds(events) and ai_video._stop_buying()


def test_busy_waits_out_retry_after_inside_the_phase(monkeypatch, tmp_path, fresh_run):
    answer = {"request_id": "req-0000-abcd", "status": "queued"}
    busy = higgsfield.HiggsfieldError("busy", "account_queue_full", status=429, retry_after=7)
    events = _shop(monkeypatch, {0: [busy, answer]})
    (job,) = ai_video._buy(_req(work_dir=str(tmp_path)), [0], _stills(tmp_path), PLAN6, PRICE,
                           fresh_run.now + 60)
    assert fresh_run.slept == [7] and job.status == "submitted" and not job.ambiguous
    assert {e[3] for e in events if e[0] == "submit"} == {"key-0"}

    long_wait = higgsfield.HiggsfieldError("busy", "account_queue_full", status=429,
                                           retry_after=90)
    _shop(monkeypatch, {0: [long_wait]})
    (job,) = ai_video._buy(_req(work_dir=str(tmp_path)), [0], _stills(tmp_path), PLAN6, PRICE,
                           fresh_run.now + 60)
    assert (job.status, job.cost) == ("refused", 0.0)


def test_a_still_that_cannot_animate_is_not_bought(monkeypatch, tmp_path, fresh_run):
    events = _shop(monkeypatch, {})
    jobs = ai_video._buy(_req(work_dir=str(tmp_path)), [0, 5],
                         _stills(tmp_path, animatable=(0, 1, 2, 3, 4)), PLAN6, PRICE,
                         fresh_run.now + 300)
    assert [j.shot for j in jobs] == [0] and ("reserve", 5) not in _kinds(events)


# --- Stage 3b: waiting, settling and the clips (design 6.2 steps 8-10) ---------------------------

from src import assembly  # noqa: E402

LENGTHS = [4.906, 5.0, 4.6, 4.654, 5.0, 4.049]


def _job(shot: int, clock) -> "ai_video.Job":
    return ai_video.Job(shot=shot, row_id=100 + shot, key=f"key-{shot}",
                        request_id=f"req-{shot:04d}-abcd", status="submitted", cost=PRICE,
                        submitted_at=clock.now)


def _watch(monkeypatch, states: dict, cancels: dict | None = None, probe: float = 5.04,
           download_error: Exception | None = None) -> dict:
    """Higgsfield's status, cancel and download, and the ledger, replaced. states[request_id]
    is a list of answers in turn (the last repeats; an Exception is raised). Returns the calls."""
    seen = {"status": [], "cancel": [], "download": [], "update": []}
    turns: dict[str, int] = {}

    def status(request_id):
        seen["status"].append(request_id)
        turns[request_id] = turns.get(request_id, 0) + 1
        seq = states[request_id]
        answer = seq[min(turns[request_id], len(seq)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def cancel(request_id):
        seen["cancel"].append(request_id)
        return (cancels or {}).get(request_id, False)

    def download(url, dest, timeout=None):
        seen["download"].append((url, os.path.basename(dest), timeout))
        if download_error:
            raise download_error
        with open(dest, "wb") as f:
            f.write(b"mp4")
        return dest

    monkeypatch.setattr(higgsfield, "status", status)
    monkeypatch.setattr(higgsfield, "cancel", cancel)
    monkeypatch.setattr(higgsfield, "download", download)
    monkeypatch.setattr(db, "update_ai_video_job",
                        lambda row_id, **fields: seen["update"].append((row_id - 100, fields)))
    monkeypatch.setattr(assembly, "probe_duration", lambda path: probe)
    monkeypatch.setattr(ai_video, "_jitter", lambda: 0.0)
    return seen


def _done(i: int) -> dict:
    return {"status": "completed", "video": {"url": f"https://cdn.example/clip{i}.mp4"}}


QUEUED, RUNNING = {"status": "queued"}, {"status": "in_progress"}


def test_jobs_are_polled_until_they_finish(monkeypatch, tmp_path, fresh_run):
    jobs = [_job(i, fresh_run) for i in range(3)]
    seen = _watch(monkeypatch, {
        "req-0000-abcd": [QUEUED, RUNNING, RUNNING, _done(0)],
        "req-0001-abcd": [RUNNING, RUNNING, {"status": "failed"}],
        "req-0002-abcd": [{"status": "nsfw"}]})
    start = fresh_run.now
    ai_video._settle_jobs(jobs, start + 300, start + 420, LENGTHS, str(tmp_path))
    assert fresh_run.slept == [2, 3, 4.5, 6.75]
    assert jobs[0].status == "completed" and jobs[0].clip == str(tmp_path / "clip_00.mp4")
    done = next(fields for shot, fields in seen["update"] if shot == 0)
    assert done["status"] == "completed" and done["seconds"] == pytest.approx(16.2, abs=0.1)
    assert done["result_url"] == "https://cdn.example/clip0.mp4" and done["settled_at"]
    assert seen["download"][0][:2] == ("https://cdn.example/clip0.mp4", "clip_00.mp4")
    assert [(j.status, j.cost, j.clip) for j in jobs[1:]] == [("failed", 0.0, None),
                                                               ("nsfw", 0.0, None)]
    assert {shot: fields["cost_usd"] for shot, fields in seen["update"] if shot} == {1: 0, 2: 0}
    assert seen["cancel"] == []

    jobs = [_job(i, fresh_run) for i in range(1)]
    _watch(monkeypatch, {"req-0000-abcd": [RUNNING] * 9 + [_done(0)]})
    fresh_run.slept.clear()
    ai_video._settle_jobs(jobs, fresh_run.now + 300, fresh_run.now + 420, LENGTHS, str(tmp_path))
    assert fresh_run.slept[:6] == [2, 3, 4.5, 6.75, 10, 10]  # x1.5 up to 10 s


def test_a_status_error_is_retried_next_tick(monkeypatch, tmp_path, fresh_run):
    (job,) = jobs = [_job(0, fresh_run)]
    seen = _watch(monkeypatch, {"req-0000-abcd": [
        higgsfield.HiggsfieldError("unavailable", "status: ReadTimeout"), _done(0)]})
    ai_video._settle_jobs(jobs, fresh_run.now + 300, fresh_run.now + 420, LENGTHS,
                          str(tmp_path))
    assert seen["status"] == ["req-0000-abcd"] * 2 and job.clip


def test_at_the_deadline_a_queued_job_is_cancelled(monkeypatch, tmp_path, fresh_run):
    jobs = [_job(i, fresh_run) for i in range(3)]
    seen = _watch(monkeypatch, {
        "req-0000-abcd": [QUEUED],
        "req-0001-abcd": [QUEUED, QUEUED, QUEUED, QUEUED, {"status": "canceled"}],
        "req-0002-abcd": [QUEUED, QUEUED, QUEUED, QUEUED, RUNNING, RUNNING, _done(2)]},
        cancels={"req-0000-abcd": True})
    start = fresh_run.now
    ai_video._settle_jobs(jobs, start + 12, start + 130, LENGTHS, str(tmp_path))
    assert seen["cancel"] == ["req-0000-abcd", "req-0001-abcd", "req-0002-abcd"]
    assert [(j.status, j.cost) for j in jobs[:2]] == [("canceled", 0.0), ("canceled", 0.0)]
    assert {shot: fields for shot, fields in seen["update"]}[1]["cost_usd"] == 0
    assert jobs[2].status == "completed" and jobs[2].clip  # an unconfirmed cancel is waited out


def test_a_running_job_gets_the_grace_period(monkeypatch, tmp_path, fresh_run):
    jobs = [_job(i, fresh_run) for i in range(2)]
    seen = _watch(monkeypatch, {"req-0000-abcd": [RUNNING] * 8 + [_done(0)],
                                "req-0001-abcd": [RUNNING]})
    start = fresh_run.now
    ai_video._settle_jobs(jobs, start + 30, start + 60, LENGTHS, str(tmp_path))
    assert jobs[0].status == "completed" and jobs[0].clip  # it arrived inside the grace
    assert (jobs[1].status, jobs[1].cost, jobs[1].clip) == ("late", PRICE, None)
    assert {shot: fields for shot, fields in seen["update"]}[1] == {"status": "late"}
    assert seen["cancel"] == []  # a running job is paid for: it is never cancelled
    assert fresh_run.now <= start + 60 + 1e-6


def test_a_clip_too_short_for_its_shot_becomes_a_still(monkeypatch, tmp_path, fresh_run):
    """Review Focus 3: a clip shorter than its shot would move every later cut off its pause."""
    (job,) = jobs = [_job(2, fresh_run)]
    seen = _watch(monkeypatch, {"req-0002-abcd": [_done(2)]}, probe=3.9)
    ai_video._settle_jobs(jobs, fresh_run.now + 300, fresh_run.now + 420, LENGTHS,
                          str(tmp_path))
    assert job.status == "completed" and job.clip is None
    assert [fields["status"] for _shot, fields in seen["update"]] == ["completed"]


def test_a_failed_download_leaves_the_row_completed(monkeypatch, tmp_path, fresh_run):
    (job,) = jobs = [_job(0, fresh_run)]
    seen = _watch(monkeypatch, {"req-0000-abcd": [_done(0)]},
                  download_error=higgsfield.HiggsfieldError("unavailable", "download: reset"))
    ai_video._settle_jobs(jobs, fresh_run.now + 300, fresh_run.now + 420, LENGTHS,
                          str(tmp_path))
    assert job.status == "completed" and job.clip is None
    assert [fields["status"] for _shot, fields in seen["update"]] == ["completed"]
    assert 0 < seen["download"][0][2] <= 180  # bounded by the time to grace_end


# --- Stage 3b: one reel's shots, and the run's latches (design 6.2, 6.4, 6.8) --------------------

def _trimmed_test4() -> tuple[float, list[tuple[float, float]]]:
    """Test 4's narration as voice.trim_silence leaves it (as in test_assembly)."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", "hinglish_test4.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lead = data["pauses"][0][1]
    return (round(data["duration"] - lead, 3),
            [(round(s - lead, 3), round(e - lead, 3)) for s, e in data["pauses"][1:]])


def _ready(monkeypatch, tmp_path, plan_ok=True, price=PRICE, ledger=()) -> dict:
    """Everything below make_shots replaced but the buying and settling: the plan, the pictures,
    the still clips, the quote and this idea's ledger rows. Returns what was asked."""
    asked = {"stills": [], "quotes": []}
    monkeypatch.setattr(ai_video, "plan_shots", lambda req, durations: (
        [dict(PLAN6[i % 6]) for i in range(len(durations))], plan_ok))
    pictures = _stills(tmp_path)
    monkeypatch.setattr(ai_video, "_pictures", lambda req, plan: pictures[:len(plan)])
    monkeypatch.setattr(ai_video, "_still_clip", lambda picture, dest, seconds, index: (
        asked["stills"].append(index) or dest))

    def estimate(endpoint, args):
        asked["quotes"].append((endpoint, args))
        if isinstance(price, Exception):
            raise price
        return price

    def rows(idea_id, days=7):
        if isinstance(ledger, Exception):
            raise ledger
        return [dict(r) for r in ledger]

    monkeypatch.setattr(higgsfield, "estimate", estimate)
    monkeypatch.setattr(db, "ai_video_jobs_for_idea", rows)
    return asked


def _test4_req(tmp_path, **kw) -> "ai_video.ReelRequest":
    duration, pauses = _trimmed_test4()
    return _req(work_dir=str(tmp_path), duration=duration, pauses=pauses, **kw)


def test_a_reel_end_to_end(monkeypatch, tmp_path, fresh_run):
    asked = _ready(monkeypatch, tmp_path)
    events = _shop(monkeypatch, {})
    _watch(monkeypatch, {f"req-{i:04d}-abcd": [_done(i)] for i in range(6)})
    req = _test4_req(tmp_path)
    shots = ai_video.make_shots(req)
    assert shots.kinds == ["video"] * 6 and shots.video == 6 and shots.planned_video == 6
    assert shots.spend_usd == pytest.approx(0.945) and shots.problems == []
    assert shots.files == [str(tmp_path / f"clip_{i:02d}.mp4") for i in range(6)]
    assert shots.cuts == assembly.cut_list(req.duration, req.pauses)
    assert asked["stills"] == []
    ((endpoint, body),) = asked["quotes"]
    assert endpoint == higgsfield.KLING and body == {
        "prompt": PLAN6[0]["motion"], "image_url": "https://example.com/still.png",
        "duration": 5, "negative_prompt": ai_video.NEGATIVE}
    assert [e[1] for e in events if e[0] == "reserve"] == [0, 5, 1, 2, 3, 4]


@pytest.mark.parametrize("case", ["no-key", "latch", "preflight", "planner", "ledger",
                                  "quote-fails", "quote-zero", "no-time"])
def test_nothing_is_bought_without_the_means(monkeypatch, tmp_path, fresh_run, case):
    price = {"quote-fails": higgsfield.HiggsfieldError("unavailable", "estimate: timeout"),
             "quote-zero": 0.0}.get(case, PRICE)
    asked = _ready(monkeypatch, tmp_path, plan_ok=case != "planner", price=price,
                   ledger=RuntimeError("connection reset") if case == "ledger" else ())
    events = _shop(monkeypatch, {})
    if case == "no-key":
        monkeypatch.delenv("HF_API_KEY")
    if case == "latch":
        ai_video._latch.add("funds")
    extra = {"preflight": {"can_buy": False},
             "no-time": {"deadline": fresh_run.now + 100}}.get(case, {})
    shots = ai_video.make_shots(_test4_req(tmp_path, **extra))
    assert shots.kinds == ["still"] * 6 and shots.spend_usd == 0
    assert sorted(asked["stills"]) == [0, 1, 2, 3, 4, 5]  # Ken Burns, rendered in parallel
    assert not [e for e in events if e[0] == "reserve"]
    assert shots.planned_video == 6  # the downgrade production reports


def test_paid_clips_are_reused(monkeypatch, tmp_path, fresh_run):
    ledger = [
        {"id": 50, "shot": 0, "status": "completed", "cost_usd": PRICE,
         "result_url": "https://cdn.example/old0.mp4"},
        {"id": 55, "shot": 5, "status": "completed", "cost_usd": PRICE,
         "result_url": "https://cdn.example/old5.mp4"},
        {"id": 51, "shot": 1, "status": "late", "cost_usd": PRICE, "result_url": None},
        {"id": 52, "shot": 2, "status": "reserved", "cost_usd": PRICE},
        {"id": 53, "shot": 3, "status": "failed", "cost_usd": 0}]
    _ready(monkeypatch, tmp_path, ledger=ledger)
    events = _shop(monkeypatch, {})
    seen = _watch(monkeypatch, {f"req-{i:04d}-abcd": [_done(i)] for i in range(6)})
    shots = ai_video.make_shots(_test4_req(tmp_path))
    assert [e[1] for e in events if e[0] == "reserve"] == [1, 2]  # k = 6, 4 already paid
    assert [url for url, _name, _t in seen["download"]][:2] == [
        "https://cdn.example/old0.mp4", "https://cdn.example/old5.mp4"]
    assert shots.kinds == ["video", "video", "video", "still", "still", "video"]
    assert shots.spend_usd == pytest.approx(2 * PRICE)  # reused clips cost nothing new


def test_the_phase_and_grace_times(monkeypatch, tmp_path, fresh_run):
    _ready(monkeypatch, tmp_path)
    times = []
    monkeypatch.setattr(ai_video, "_buy", lambda req, positions, pictures, plan, price,
                        phase_end: times.append(phase_end) or [])
    monkeypatch.setattr(ai_video, "_settle_jobs", lambda jobs, phase_end, grace_end, lengths,
                        out_dir: times.append((phase_end, grace_end)))
    now = fresh_run.now
    ai_video.make_shots(_test4_req(tmp_path))
    ai_video.make_shots(_test4_req(tmp_path, deadline=now + 350))
    monkeypatch.setenv("AI_VIDEO_TIMEOUT_SECONDS", "200")
    monkeypatch.setenv("AI_VIDEO_GRACE_SECONDS", "60")
    ai_video.make_shots(_test4_req(tmp_path))
    assert times == [now + 300, (now + 300, now + 420),
                     now + 300, (now + 300, now + 350),
                     now + 200, (now + 200, now + 260)]


def test_one_alert_per_kind_per_run(monkeypatch, tmp_path, fresh_run):
    """Review Focus 4: three reels and no key make one alert, and every reel still ships."""
    _ready(monkeypatch, tmp_path)
    monkeypatch.delenv("HF_API_KEY")
    reels = [ai_video.make_shots(_test4_req(tmp_path)) for _ in range(3)]
    problems = [p for shots in reels for p in shots.problems]
    assert len(problems) == 1 and "HF_API_KEY" in problems[0]
    assert all(shots.kinds == ["still"] * 6 for shots in reels)
    ai_video.begin_run()
    assert len(ai_video.make_shots(_test4_req(tmp_path)).problems) == 1


def test_a_reel_with_no_clip_stops_buying_for_the_run(monkeypatch, tmp_path, fresh_run):
    """Review Focus 5: a queue too slow to give one reel one clip would charge every later reel
    of the run for clips that arrive too late."""
    _ready(monkeypatch, tmp_path)
    events = _shop(monkeypatch, {})
    _watch(monkeypatch, {f"req-{i:04d}-abcd": [RUNNING] for i in range(6)})
    first = ai_video.make_shots(_test4_req(tmp_path))
    assert first.kinds == ["still"] * 6 and first.spend_usd == pytest.approx(6 * PRICE)
    assert ai_video._stop_buying() and any("in time" in p for p in first.problems)
    events.clear()
    second = ai_video.make_shots(_test4_req(tmp_path))
    assert not [e for e in events if e[0] == "reserve"] and second.problems == []


def test_reel_line(monkeypatch):
    shots = ai_video.Shots(files=["a"] * 6, kinds=["video"] * 5 + ["still"], cuts=[],
                           planned_video=6, spend_usd=5 * PRICE, problems=[])
    monkeypatch.setattr(db, "ai_video_spend_this_month", lambda: 14.3)
    assert ai_video.reel_line(shots) == "🎞️ AI video: 5 of 6 shots, $0.79 ($14.30 this month)"

    def missing():
        raise db.LedgerUnavailable("ai_video_jobs is missing")

    monkeypatch.setattr(db, "ai_video_spend_this_month", missing)
    assert ai_video.reel_line(shots) == "🎞️ AI video: 5 of 6 shots, $0.79"
