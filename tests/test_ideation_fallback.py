"""Tests for the ideation fallback (Module 1 fallback).

Mock llm + db — no network/DB. Verify JSON parsing, the source/field validation that protects
the news-niche sourcing gate, dedup, idempotency, and the thin-digest guard.
"""
from __future__ import annotations

import json
import os

import pytest

from src import ideation_fallback as fb


@pytest.fixture(autouse=True)
def _offline_source_check(monkeypatch):
    """Keep this module offline (see its docstring).

    _validate_and_clean now probes every source URL for liveness, so without this the existing
    fixtures — which cite made-up hosts like https://x.example — would each make a real HTTP
    request and wait for DNS to time out. The liveness tests below re-enable the check and stub
    the probe.

    Same for the source SEARCH: an under-sourced idea now queries the Google News RSS search to
    top itself up, which is a real network call. Tests that exercise that path install their own
    stub, which replaces this one.
    """
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "false")
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: [])


def _idea(title, n_sources=2, **over):
    d = {
        "niche": "impact-news",
        "title": title,
        "hook": f"hook for {title}",
        "angle": f"why {title} matters",
        "est_score": 0.7,
        "sources": [f"https://src{i}.example/{title}" for i in range(n_sources)],
    }
    d.update(over)
    return d


def _patch(monkeypatch, ideas, pending=None):
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: pending or [])
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])  # no network in tests
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])      # no network in tests
    # The search top-up is a REAL rescue path (it is what keeps an under-sourced idea
    # alive), so it has to be stubbed off here or these fixtures would hit the network and
    # the "drop the unsourced idea" tests would never see an unsourced idea.
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])  # no DB in tests
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])         # no Groq in tests
    # _produce_ideas tries grounded research first; mock that as the primary path. It returns
    # (text, real citations) since 2026-09-03 — those citations are what stopped ideation
    # having to ask the model for source URLs it cannot know.
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: (json.dumps({"ideas": ideas}), []))
    # A thin grounded pass now tops up from the ungrounded call; keep that offline too.
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": []}))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas",
                        lambda rows: captured.setdefault("rows", rows) or rows)
    return captured


def test_inserts_valid_ideas(monkeypatch):
    ideas = [_idea(f"Idea {i}") for i in range(6)]
    captured = _patch(monkeypatch, ideas)
    n = fb.run_fallback_ideation()
    assert n == 6
    assert all(set(r) == {"niche", "title", "hook", "angle", "est_score", "sources"}
               for r in captured["rows"])


def test_drops_ideas_with_too_few_sources(monkeypatch):
    ideas = [_idea(f"Good {i}") for i in range(5)] + [_idea("Bad", n_sources=1)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    titles = [r["title"] for r in captured["rows"]]
    assert "Bad" not in titles and len(titles) == 5


def test_dedupes_by_title(monkeypatch):
    ideas = [_idea("Same") for _ in range(3)] + [_idea(f"U{i}") for i in range(4)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    titles = [r["title"].lower() for r in captured["rows"]]
    assert titles.count("same") == 1


def test_est_score_coerced_and_clamped(monkeypatch):
    ideas = [_idea("A", est_score="not-a-number"), _idea("B", est_score=5.0)]
    ideas += [_idea(f"C{i}") for i in range(4)]
    captured = _patch(monkeypatch, ideas)
    fb.run_fallback_ideation()
    by = {r["title"]: r["est_score"] for r in captured["rows"]}
    assert by["A"] == 0.5 and by["B"] == 1.0


def test_idempotent_when_pending_exists(monkeypatch):
    captured = _patch(monkeypatch, [_idea(f"x{i}") for i in range(6)], pending=[{"id": 1}])
    assert fb.run_fallback_ideation() == 0
    assert "rows" not in captured  # insert never called


def test_thin_digest_raises(monkeypatch):
    _patch(monkeypatch, [_idea("only one")])  # 1 valid < _MIN_IDEAS
    with pytest.raises(RuntimeError, match="thin digest"):
        fb.run_fallback_ideation()


def test_parses_fenced_json(monkeypatch):
    ideas = [_idea(f"f{i}") for i in range(6)]
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: ("```json\n" + json.dumps({"ideas": ideas}) + "\n```", []))
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": []}))
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    assert fb.run_fallback_ideation() == 6


def test_caps_at_max(monkeypatch):
    ideas = [_idea(f"n{i}") for i in range(30)]
    captured = _patch(monkeypatch, ideas)
    n = fb.run_fallback_ideation()
    assert n == fb._MAX_IDEAS == len(captured["rows"])


def test_generate_ideas_on_demand_no_pending_guard(monkeypatch):
    # generate_ideas must NOT skip just because pending ideas already exist
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [{"id": 1}])
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    ideas = [_idea(f"od{i}", est_score=0.1 * i) for i in range(8)]
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: (json.dumps({"ideas": ideas}), []))
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": []}))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    n = fb.generate_ideas(3)
    assert n == 3 and len(captured["rows"]) == 3
    # keeps the highest-scored 3
    assert [r["est_score"] for r in captured["rows"]] == pytest.approx([0.7, 0.6, 0.5])


def test_generate_ideas_raises_when_none_valid(monkeypatch):
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    empty = lambda *a, **k: json.dumps({"ideas": []})
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources", empty)  # grounded empty → falls back...
    monkeypatch.setattr(fb.llm, "generate", empty)            # ...ungrounded also empty
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    with pytest.raises(RuntimeError, match="could not generate"):
        fb.generate_ideas(3)


def test_parse_ideas_tolerates_raw_control_chars():
    # grounded LLM JSON sometimes contains literal newlines inside string values
    raw = '{"ideas": [{"title": "Line one\nline two", "hook": "h", "angle": "a", "sources": []}]}'
    out = fb._parse_ideas(raw)
    assert out[0]["title"] == "Line one\nline two"


def test_produce_ideas_falls_back_when_grounding_fails(monkeypatch):
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: ["NASDAQ", "ISRO"])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    def _boom(*a, **k):
        raise RuntimeError("grounding unavailable")
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources", _boom)
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": [_idea("Fallback")]}))
    out = fb._produce_ideas(3)
    assert out and out[0]["title"] == "Fallback"


def test_produce_ideas_falls_back_on_malformed_grounded_json(monkeypatch):
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    # grounded returns broken JSON (missing comma / truncated) → must fall back, not crash
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: ('{"ideas": [{"title": "Broken" "hook": "x"}]', []))
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": [_idea("Clean")]}))
    out = fb._produce_ideas(3)
    assert out and out[0]["title"] == "Clean"


def test_load_routine_ideas_reads_file(monkeypatch, tmp_path):
    f = tmp_path / "daily-ideas.json"
    f.write_text(json.dumps({"ideas": [_idea("Routine A"), _idea("Routine B")]}), encoding="utf-8")
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(f))
    out = fb.load_routine_ideas()
    assert {i["title"] for i in out} == {"Routine A", "Routine B"}


def test_load_routine_ideas_absent_or_bad(monkeypatch, tmp_path):
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(tmp_path / "nope.json"))
    assert fb.load_routine_ideas() == []
    bad = tmp_path / "bad.json"; bad.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(fb, "_ROUTINE_IDEAS_FILE", str(bad))
    assert fb.load_routine_ideas() == []


def test_seed_ideas_prefers_routine_file(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [_idea(f"R{i}", est_score=0.1 * i) for i in range(6)])
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: pytest.fail("must not call LLM when routine file present"))
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: set())
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    assert fb.seed_ideas(3) == 3
    assert [r["est_score"] for r in captured["rows"]] == pytest.approx([0.5, 0.4, 0.3])


def test_seed_ideas_falls_back_to_llm(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [])
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: [_idea(f"G{i}") for i in range(5)])
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: set())
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: rows)
    assert fb.seed_ideas(2) == 2


def test_seed_ideas_dedupes_against_db(monkeypatch):
    monkeypatch.setattr(fb, "load_routine_ideas", lambda: [_idea("Dup"), _idea("New1"), _idea("New2")])
    monkeypatch.setattr(fb.db, "existing_idea_titles", lambda: {"dup"})
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    fb.seed_ideas(5)
    assert "Dup" not in [r["title"] for r in captured["rows"]]


def test_live_real_llm_ideation(monkeypatch):
    """Real Gemini/Groq generates parseable, well-sourced ideas (DB mocked). Skips offline.

    Opt-in like every other live test here (TELEGRAM_LIVE_TEST, FACTCHECK_LIVE_TEST,
    GEMINI_TTS_LIVE_TEST, YOUTUBE_LIVE_UPLOAD_TEST). It was the one live test that ran by
    DEFAULT, and it is the most expensive one in the suite: `run_fallback_ideation()` spends
    several grounded Gemini requests against a free tier of 20/day/model, so every casual
    `pytest` run was competing with production for the day's budget — and it is exactly that
    budget running out that leaves the pipeline with no working provider (STATUS 2026-09-01).
    """
    if os.environ.get("IDEATION_LIVE_TEST") != "1":
        pytest.skip("set IDEATION_LIVE_TEST=1 to run (spends the shared 20/day Gemini quota)")
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas", lambda rows: captured.setdefault("rows", rows) or rows)
    try:
        n = fb.run_fallback_ideation()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"llm unavailable (offline / quota / unkeyed): {e}")
    assert n >= fb._MIN_IDEAS
    for r in captured["rows"]:
        assert r["title"] and r["hook"] and r["angle"]
        assert len(r["sources"]) >= int(fb.config.get("MIN_SOURCES", "2"))


# --- two-stage production + ranking ----------------------------------------------------

def test_produce_ideas_runs_two_stages(monkeypatch):
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [{"title": "Real headline - PTI", "url": "https://feed.example/a", "source": "PTI"}])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    calls = {"select": 0}
    def _sel(target, headlines, trending, winners):
        calls["select"] += 1
        return [{"story": "Story X", "category": "world", "why_shareworthy": "stakes"}]
    monkeypatch.setattr(fb, "_select_stories", _sel)
    captured = {}
    def _grounded(prompt, **k):
        captured["prompt"] = prompt
        return json.dumps({"ideas": [_idea("Expanded", share_score=0.9)]}), []
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources", _grounded)
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": []}))
    out = fb._produce_ideas(3)
    assert calls["select"] == 1
    assert out and out[0]["title"] == "Expanded"
    assert "Story X" in captured["prompt"]  # selected story flowed into Stage 2


def test_rank_key_orders_by_share_then_est():
    a = {"title": "a", "est_score": 0.9, "share_score": 0.2}
    b = {"title": "b", "est_score": 0.1, "share_score": 0.8}
    assert sorted([a, b], key=fb._rank_key)[0]["title"] == "b"  # higher share wins


def test_generate_ideas_ranks_by_share_score(monkeypatch):
    monkeypatch.setattr(fb.db, "get_pending_ideas", lambda: [])
    ideas = [
        _idea("Low share", est_score=0.9, share_score=0.1),
        _idea("High share", est_score=0.2, share_score=0.9),
        _idea("Mid share", est_score=0.5, share_score=0.5),
    ]
    monkeypatch.setattr(fb, "_produce_ideas", lambda t: fb._validate_and_clean(ideas))
    captured = {}
    monkeypatch.setattr(fb.db, "insert_ideas",
                        lambda rows: captured.setdefault("rows", rows) or rows)
    fb.generate_ideas(2)
    assert [r["title"] for r in captured["rows"]] == ["High share", "Mid share"]


# --- stage-1 story selection -----------------------------------------------------------

def test_select_stories_parses_distinct_stories(monkeypatch):
    payload = {"stories": [
        {"story": "West Asia ceasefire talks", "category": "world", "why_shareworthy": "war stakes"},
        {"story": "Weakest monsoon in 17 years", "category": "climate", "why_shareworthy": "food prices"},
    ]}
    seen = {}
    def _gen(prompt, **kw):
        seen.update(kw)
        return json.dumps(payload)
    monkeypatch.setattr(fb.llm, "generate", _gen)
    out = fb._select_stories(2, ["West Asia ceasefire - The Hindu", "Monsoon fails - PTI"], [], [])
    assert [s["story"] for s in out] == ["West Asia ceasefire talks", "Weakest monsoon in 17 years"]
    assert seen.get("prefer_groq") is True  # spares Gemini RPD (rule 13)


def test_select_stories_empty_without_headlines(monkeypatch):
    monkeypatch.setattr(fb.llm, "generate",
                        lambda *a, **k: pytest.fail("must not call LLM with no headlines"))
    assert fb._select_stories(3, [], ["ISRO"], []) == []


def test_select_stories_returns_empty_on_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("groq down")
    monkeypatch.setattr(fb.llm, "generate", _boom)
    assert fb._select_stories(3, ["a headline"], [], []) == []


# --- dedup backstop --------------------------------------------------------------------

def test_dedup_backstop_drops_same_story_near_duplicate():
    ideas = [
        _idea("ISRO launches new navigation satellite NVS-02"),
        _idea("ISRO launches new navigation satellite today"),  # same story, reworded
        _idea("RBI cuts repo rate by 25 basis points"),
    ]
    out = fb._validate_and_clean(ideas)
    titles = [o["title"] for o in out]
    assert "RBI cuts repo rate by 25 basis points" in titles
    assert len(titles) == 2  # one of the two ISRO near-duplicates dropped


def test_dedup_backstop_keeps_distinct_short_titles():
    # synthetic distinct titles (used widely in other tests) must NOT be over-merged
    out = fb._validate_and_clean([_idea(f"Idea {i}") for i in range(6)])
    assert len(out) == 6


# --- share_score + row projection ------------------------------------------------------

def test_validate_adds_share_score_default_to_est(monkeypatch):
    out = fb._validate_and_clean([_idea("A", est_score=0.8)])
    assert out[0]["share_score"] == 0.8  # defaults to est_score when model omits it


def test_validate_share_score_coerced_and_clamped():
    out = fb._validate_and_clean([
        _idea("A", share_score=5.0),
        _idea("B", share_score="nope", est_score=0.4),
    ])
    by = {r["title"]: r["share_score"] for r in out}
    assert by["A"] == 1.0 and by["B"] == 0.4  # clamp high; bad value -> est_score


def test_to_rows_projects_to_db_columns_only():
    ideas = fb._validate_and_clean([_idea("A", share_score=0.9)])
    rows = fb._to_rows(ideas)
    assert set(rows[0]) == {"niche", "title", "hook", "angle", "est_score", "sources"}
    assert "share_score" not in rows[0]


# --- de-hyped ideation framing ---------------------------------------------------------

def test_ideation_prompt_dehyped():
    prompt = fb._PROMPT.lower()
    assert "honest" in prompt          # new: honest scroll appeal
    assert "why it matters" in prompt  # kept: original analysis requirement
    assert "scroll" in prompt          # kept: still wants a strong (honest) hook


def test_ideation_prompt_asks_for_spread_scores():
    prompt = fb._PROMPT.lower()
    assert "score calibration" in prompt   # require relative, spread-out scores
    assert "spread" in prompt and "0.0-1.0" in prompt
    assert "do not give everything" in prompt


# --- source liveness: an idea may not enter the digest citing a dead link ------------------

def test_url_is_dead_only_on_404_and_410(monkeypatch):
    """Only a hard 'this page does not exist' counts as dead.

    News sites routinely answer 401/403 to a bot (NDTV, Bloomberg measured 2026-09-01), so
    treating those as dead would throw away good ideas citing real articles.
    """
    codes = {}

    class _Resp:
        def __init__(self, url):
            self.status_code = codes[url]

        def close(self):
            pass

    monkeypatch.setattr(fb.requests, "get", lambda url, **k: _Resp(url))
    for code, dead in ((404, True), (410, True), (200, False), (401, False),
                       (403, False), (429, False), (500, False)):
        codes["https://x.example/a"] = code
        assert fb._url_is_dead("https://x.example/a") is dead, f"code {code}"


def test_url_is_not_dead_when_the_check_itself_fails(monkeypatch):
    """A timeout/DNS blip must never be read as 'the article does not exist' (rule 14)."""
    def _boom(url, **k):
        raise OSError("connection reset")
    monkeypatch.setattr(fb.requests, "get", _boom)
    assert fb._url_is_dead("https://x.example/a") is False


def test_ideas_citing_only_dead_links_are_dropped(monkeypatch):
    """The 2026-09-01 finding: 23 of 75 published Shorts cited nothing but 404s, because
    _clean_sources only checked that a string starts with http."""
    monkeypatch.setenv("MIN_SOURCES", "2")
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "true")
    dead = {"https://ok.example/1": False, "https://ok.example/2": False,
            "https://gone.example/1": True, "https://gone.example/2": True}
    monkeypatch.setattr(fb, "_url_is_dead", lambda u: dead[u])
    ideas = [
        {"title": "Real story", "hook": "h", "angle": "a",
         "sources": ["https://ok.example/1", "https://ok.example/2"]},
        {"title": "Fabricated story", "hook": "h", "angle": "a",
         "sources": ["https://gone.example/1", "https://gone.example/2"]},
    ]
    kept = fb._validate_and_clean(ideas)
    assert [i["title"] for i in kept] == ["Real story"]


def test_an_idea_keeps_only_its_live_sources_and_needs_min_sources_of_them(monkeypatch):
    monkeypatch.setenv("MIN_SOURCES", "1")
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "true")
    monkeypatch.setattr(fb, "_url_is_dead",
                        lambda u: u.endswith("/dead"))
    ideas = [{"title": "Half sourced", "hook": "h", "angle": "a",
              "sources": ["https://x.example/live", "https://x.example/dead"]}]
    kept = fb._validate_and_clean(ideas)
    assert kept[0]["sources"] == ["https://x.example/live"], "dead citation must not reach the reel"


def test_source_check_can_be_disabled(monkeypatch):
    monkeypatch.setenv("MIN_SOURCES", "2")
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "false")
    monkeypatch.setattr(fb, "_url_is_dead",
                        lambda u: pytest.fail("must not probe when disabled"))
    ideas = [{"title": "Unchecked", "hook": "h", "angle": "a",
              "sources": ["https://gone.example/1", "https://gone.example/2"]}]
    assert len(fb._validate_and_clean(ideas)) == 1


# --- REAL citations (2026-09-03) ----------------------------------------------------------
# Root cause of both the failed on-demand run and the one-idea digest: the prompt asked the model
# for source URLs and the model invented them (`articleshow/115000000.cms`), so `_url_is_dead`
# culled every idea. Sources must come from things we actually fetched — the grounded search's
# own citations and the news feed's article links — not from the model's memory.

_STORIES = [
    {"title": "Rescue efforts continue as Nepal-China flood death toll surpasses 1,270 - Al Jazeera",
     "url": "https://news.google.com/rss/articles/NEPAL1", "source": "Al Jazeera"},
    {"title": "Nepal floods: 1,270 dead as rescue teams reach cut-off villages - BBC",
     "url": "https://news.google.com/rss/articles/NEPAL2", "source": "BBC"},
    {"title": "Belgian PM explains chocolate India Gate replica for Modi - Moneycontrol",
     "url": "https://news.google.com/rss/articles/CHOCO", "source": "Moneycontrol"},
]


def test_match_story_urls_finds_the_feed_articles_behind_an_idea():
    idea = {"title": "Nepal-China Floods: 1,270+ Dead", "hook": "The toll keeps climbing.",
            "angle": "Why the world looked away."}
    assert fb._match_story_urls(idea, _STORIES) == [
        "https://news.google.com/rss/articles/NEPAL1",
        "https://news.google.com/rss/articles/NEPAL2",
    ]


def test_match_story_urls_ignores_an_unrelated_story():
    """Citing an article that does not support the claim is still a bad citation (docs/08 §1)."""
    idea = {"title": "Belgian Chocolate India Gate Snub", "hook": "It never arrived.",
            "angle": "Diplomatic gifts are never just gifts."}
    assert fb._match_story_urls(idea, _STORIES) == [
        "https://news.google.com/rss/articles/CHOCO"]


def test_match_story_urls_needs_more_than_one_shared_word():
    """A single common word ('india') is coincidence, not the same story."""
    idea = {"title": "India Signs New Trade Pact", "hook": "Tariffs move.",
            "angle": "Who pays."}
    assert fb._match_story_urls(idea, _STORIES) == []


def test_attach_real_sources_prefers_the_grounded_publisher_url(monkeypatch):
    """Operator chose 'both, publisher first': a resolved publisher URL reads better in a YouTube
    description than a news.google.com reader link, but the feed link guarantees we have one."""
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: "https://aljazeera.com/real-article")
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "h", "angle": "a",
              "sources": ["https://timesofindia.example/articleshow/115000000.cms"]}]
    raw = '{"ideas": [{"title": "Nepal-China Floods: 1,270+ Dead"}]}'
    grounded = [{"uri": "https://redirect/aaa", "domain": "aljazeera.com", "spans": [(10, 40)]}]

    out = fb._attach_real_sources(ideas, raw, grounded, _STORIES)

    assert out[0]["sources"][0] == "https://aljazeera.com/real-article"
    assert "https://news.google.com/rss/articles/NEPAL1" in out[0]["sources"]
    # the model's own invented URL is kept last; the liveness probe culls it later
    assert out[0]["sources"][-1] == "https://timesofindia.example/articleshow/115000000.cms"


def test_attach_real_sources_gives_each_idea_only_its_own_citation(monkeypatch):
    """grounding_supports spans say which part of the reply a citation backs — so a two-idea
    reply must not cross-contaminate, or every reel cites every story."""
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    raw = ('{"ideas": [{"title": "Nepal-China Floods: 1,270+ Dead", "x": "AAAAAAAAAA"}, '
           '{"title": "Belgian Chocolate India Gate Snub", "y": "BBBBBBBBBB"}]}')
    first, second = raw.index("Nepal"), raw.index("Belgian")
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "h", "angle": "a", "sources": []},
             {"title": "Belgian Chocolate India Gate Snub", "hook": "h", "angle": "a", "sources": []}]
    grounded = [{"uri": "https://pub/nepal", "domain": "aljazeera.com", "spans": [(first, first + 5)]},
                {"uri": "https://pub/choco", "domain": "moneycontrol.com", "spans": [(second, second + 5)]}]

    out = fb._attach_real_sources(ideas, raw, grounded, _STORIES)

    assert "https://pub/nepal" in out[0]["sources"]
    assert "https://pub/choco" not in out[0]["sources"]
    assert "https://pub/choco" in out[1]["sources"]


def test_attach_real_sources_shares_an_unattributable_citation(monkeypatch):
    """A chunk with no support span still names a real article. Withholding it entirely is what
    leaves an idea below MIN_SOURCES and gets it dropped."""
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "h", "angle": "a", "sources": []}]
    raw = '{"ideas": [{"title": "Nepal-China Floods: 1,270+ Dead"}]}'
    grounded = [{"uri": "https://pub/loose", "domain": "bbc.com", "spans": []}]

    out = fb._attach_real_sources(ideas, raw, grounded, _STORIES)
    assert "https://pub/loose" in out[0]["sources"]


def test_produce_ideas_sources_an_idea_whose_model_urls_are_all_dead(monkeypatch):
    """The exact 2026-09-03 failure: the model cited only invented URLs, every one 404'd, and the
    idea was dropped — emptying the digest and killing the job. The feed link keeps it alive."""
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "true")
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: _STORIES)
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    # only the invented URL is dead; the feed's own article links are live
    monkeypatch.setattr(fb, "_url_is_dead", lambda u: "articleshow" in u)

    reply = json.dumps({"ideas": [{
        "niche": "impact-news", "title": "Nepal-China Floods: 1,270+ Dead",
        "hook": "The toll keeps climbing.", "angle": "Why the world looked away.",
        "est_score": 0.8, "share_score": 0.9,
        "sources": ["https://timesofindia.example/articleshow/115000000.cms"]}]})
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources", lambda *a, **k: (reply, []))
    monkeypatch.setattr(fb.llm, "generate", lambda *a, **k: json.dumps({"ideas": []}))

    out = fb._produce_ideas(2)

    assert len(out) == 1, "the idea must survive on real feed sources"
    assert out[0]["sources"] == ["https://news.google.com/rss/articles/NEPAL1",
                                 "https://news.google.com/rss/articles/NEPAL2"]


def test_produce_ideas_tops_up_from_ungrounded_when_grounded_is_thin(monkeypatch):
    """Grounded returning ONE valid idea used to be accepted as the whole pool, so a request for
    3 shipped a digest of 1. Only a total grounded failure triggered the ungrounded pass."""
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "false")
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: (json.dumps({"ideas": [_idea("Grounded One")]}), []))
    monkeypatch.setattr(fb.llm, "generate",
                        lambda *a, **k: json.dumps({"ideas": [_idea("Extra Two"),
                                                              _idea("Extra Three")]}))

    out = fb._produce_ideas(3)
    assert [i["title"] for i in out] == ["Grounded One", "Extra Two", "Extra Three"]


def test_produce_ideas_does_not_spend_the_ungrounded_call_when_grounded_suffices(monkeypatch):
    """Rule 13: the top-up must not become an extra request on every single run."""
    monkeypatch.setenv("ENABLE_SOURCE_CHECK", "false")
    monkeypatch.setattr(fb.trends, "fetch_trending", lambda *a, **k: [])
    monkeypatch.setattr(fb.db, "top_performing_titles", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "fetch_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb, "_select_stories", lambda *a, **k: [])
    monkeypatch.setattr(fb.llm, "generate_grounded_with_sources",
                        lambda *a, **k: (json.dumps({"ideas": [_idea("A"), _idea("B")]}), []))

    def _boom(*a, **k):
        raise AssertionError("ungrounded call must not run when grounded already met the target")

    monkeypatch.setattr(fb.llm, "generate", _boom)
    assert len(fb._produce_ideas(2)) == 2


# --- citation QUALITY (2026-09-03, from a live run) ---------------------------------------
# The live check produced ideas citing 'https://www.bbc.com/' and 'https://timesofindia.
# indiatimes.com/'. A homepage always answers 200, so the liveness probe passes it — but it
# supports no claim, which is the same originality/monetization failure as a dead link
# (docs/08 §1). A citation has to point at an ARTICLE.

def test_bare_homepages_are_not_citations():
    assert fb._is_homepage("https://www.bbc.com/") is True
    assert fb._is_homepage("https://timesofindia.indiatimes.com") is True
    assert fb._is_homepage("https://www.bbc.com/news/world-asia-123") is False
    assert fb._is_homepage("https://news.google.com/rss/articles/AAA") is False


def test_attach_real_sources_drops_a_model_cited_homepage(monkeypatch):
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: [])
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "h", "angle": "a",
              "sources": ["https://www.bbc.com/", "https://www.bbc.com/news/real-article"]}]
    raw = '{"ideas": [{"title": "Nepal-China Floods: 1,270+ Dead"}]}'

    out = fb._attach_real_sources(ideas, raw, [], _STORIES)
    assert "https://www.bbc.com/" not in out[0]["sources"]
    assert "https://www.bbc.com/news/real-article" in out[0]["sources"]


def test_attach_real_sources_searches_for_an_under_sourced_idea(monkeypatch):
    """The top-stories feed only holds the front page. When nothing there matches, the free RSS
    search finds the story — which is what keeps an idea above MIN_SOURCES with no API quota."""
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    searched = {}

    def _search(query, limit=6):
        searched["q"] = query
        return [{"title": "El Nino supersized - BBC", "url": "https://news.google/EL1", "source": "BBC"},
                {"title": "UN warns on El Nino - Reuters", "url": "https://news.google/EL2", "source": "Reuters"}]

    monkeypatch.setattr(fb.news, "search_stories", _search)
    ideas = [{"title": "UN Warning: 'Supersized' El Nino Threat", "hook": "h", "angle": "a",
              "sources": []}]
    raw = '{"ideas": []}'

    out = fb._attach_real_sources(ideas, raw, [], _STORIES)
    assert "El Nino" in searched["q"]
    assert out[0]["sources"] == ["https://news.google/EL1", "https://news.google/EL2"]


def test_attach_real_sources_does_not_search_when_already_sourced(monkeypatch):
    """One HTTP request per under-sourced idea is fine; one per idea always is waste (rule 13)."""
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)

    def _never(*a, **k):
        raise AssertionError("search must not run for an already-sourced idea")

    monkeypatch.setattr(fb.news, "search_stories", _never)
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "The toll keeps climbing.",
              "angle": "a", "sources": []}]
    raw = '{"ideas": []}'
    out = fb._attach_real_sources(ideas, raw, [], _STORIES)
    assert len(out[0]["sources"]) == 2  # both feed articles about the same event


def test_search_prefers_distinct_publishers(monkeypatch):
    """MIN_SOURCES means INDEPENDENT sources (docs/08 §1). The live 2026-09-03 run came back with
    two feed links whose ids shared a long prefix — the same story twice reads as two sources but
    corroborates nothing. The feed names the publisher, so use it."""
    monkeypatch.setenv("MIN_SOURCES", "2")
    results = [
        {"title": "ISRO launch - The Hindu", "url": "https://news.google/A1", "source": "The Hindu"},
        {"title": "ISRO launch again - The Hindu", "url": "https://news.google/A2", "source": "The Hindu"},
        {"title": "ISRO launch - Reuters", "url": "https://news.google/B1", "source": "Reuters"},
    ]
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: results)
    idea = {"title": "Can 'Naughty Boy' Save ISRO?", "hook": "h", "angle": "a"}
    assert fb._search_for_more(idea, []) == ["https://news.google/A1", "https://news.google/B1"]


def test_search_falls_back_to_a_repeat_publisher_rather_than_leaving_an_idea_short(monkeypatch):
    """One outlet twice still beats dropping a true story for want of a second link."""
    monkeypatch.setenv("MIN_SOURCES", "2")
    results = [
        {"title": "Only outlet - PTI", "url": "https://news.google/P1", "source": "PTI"},
        {"title": "Only outlet follow-up - PTI", "url": "https://news.google/P2", "source": "PTI"},
    ]
    monkeypatch.setattr(fb.news, "search_stories", lambda *a, **k: results)
    idea = {"title": "A story only PTI covered", "hook": "h", "angle": "a"}
    assert fb._search_for_more(idea, []) == ["https://news.google/P1", "https://news.google/P2"]


def test_search_runs_when_only_the_models_own_urls_make_up_the_count(monkeypatch):
    """Live 2026-09-03: an idea carrying one feed link plus one INVENTED link counted as 2, so the
    search top-up was skipped — then the liveness probe killed the invented one and the idea was
    dropped at 1. Only sources we actually fetched may count toward 'do I need to search?'."""
    monkeypatch.setenv("MIN_SOURCES", "2")
    monkeypatch.setattr(fb, "_resolve_redirect", lambda u: u)
    searched = []
    monkeypatch.setattr(fb.news, "search_stories",
                        lambda q, limit=6: searched.append(q) or
                        [{"title": "t", "url": "https://news.google/EXTRA", "source": "BBC"}])
    ideas = [{"title": "Nepal-China Floods: 1,270+ Dead", "hook": "The toll keeps climbing.",
              "angle": "a", "sources": ["https://invented.example/articleshow/115000000.cms"]}]

    out = fb._attach_real_sources(ideas, '{"ideas": []}', [], _STORIES[:1])

    assert searched, "an idea with only one FETCHED source must still be searched"
    assert "https://news.google/EXTRA" in out[0]["sources"]


def test_search_query_keeps_a_number_intact():
    """'1,250' must not be split into '1 250' — that is a different, much worse search."""
    assert fb._search_query({"title": "1,250 Dead: Nepal's Warning to South Asia"}) == \
        "1,250 Dead Nepal's Warning to South Asia"
