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


def test_truncate_to_words_cuts_at_sentence_boundary():
    body = "One two three. Four five six seven. Eight nine ten eleven twelve."
    out = scriptwriter._truncate_to_words(body, 7)
    assert out == "One two three. Four five six seven."   # last full sentence within 7 words


def test_truncate_to_words_noop_when_within_cap():
    body = "Short enough already."
    assert scriptwriter._truncate_to_words(body, 50) == body


def test_punchup_prompt_targets_short_form():
    assert "110-130" not in scriptwriter._PUNCHUP_PROMPT      # stale long-form gone
    assert "never lengthen" in scriptwriter._PUNCHUP_PROMPT.lower()


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

    def fake_insert(idea_id, template, body, caption, hashtags, title=None, structure=None):
        captured.update(idea_id=idea_id, template=template, body=body,
                        caption=caption, hashtags=hashtags, title=title, structure=structure)
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
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a, **k: 7)
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


def test_enforces_disclosure_and_sources_when_llm_omits_them(monkeypatch):
    reply = json.dumps({
        "script_body": "Body that is long enough to pass the soft word check. " * 4,
        "caption": "A caption with no sources and no disclosure.",
        "hashtags": ["#space"],  # no #Shorts
    })
    scriptwriter_captured = _patch(monkeypatch, reply)
    out = scriptwriter.write_script(IDEA)
    # #Shorts is no longer added (design 9.9)
    assert not any(h.lower() == "#shorts" for h in out["hashtags"])
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

_REWRITE_BODY = "word " * 70  # ~70 words → inside the 25-30s acceptance band (<= SCRIPT_MAX_WORDS)


def test_punch_up_keeps_original_when_hook_already_strong(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"hook_score": 9, "title": "NEW", "script_body": _REWRITE_BODY}))
    title, body = scriptwriter._punch_up_hook("Original Title", "the original body text")
    assert title == "Original Title" and body == "the original body text"  # strong → untouched


def test_punch_up_rewrites_weak_hook(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"hook_score": 3, "title": "PUNCHIER", "script_body": _REWRITE_BODY}))
    title, body = scriptwriter._punch_up_hook("Meh Title", "weak body")
    assert title == "PUNCHIER" and body.strip() == _REWRITE_BODY.strip()


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
    # generate would raise if the judge ran; reply only feeds the script JSON path via _patch.
    # The body opens on a subject: an "ok ..." opener rightly costs one opening-rewrite call.
    reply = json.dumps({"title": "T", "script_body": "Rocket body " * 20,
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


def test_prompt_sets_the_length_in_seconds_and_a_plain_voice():
    """Design 9.1 and 9.5: a plain explainer, its length stated in seconds and in words."""
    prompt = scriptwriter._build_prompt(IDEA, "N").lower()
    assert "about 27 seconds" in prompt and "about 59 words" in prompt
    assert f"never more than {scriptwriter._max_words()}" in prompt  # the cap itself is stated
    assert "don't end early" not in prompt and "do not cut it short" not in prompt
    assert "no sarcasm" in prompt and "sarcastic" not in prompt
    assert "12-20 second" not in prompt and "55-70 words" not in prompt


def test_prompt_json_example_escapes_newlines():
    """A RAW newline inside the JSON example teaches the model to emit invalid JSON. The
    multi-line caption must be shown with the two-character \\n escape instead."""
    prompt = scriptwriter._build_prompt(IDEA, "N")
    example = next(ln for ln in prompt.splitlines() if ln.startswith('{"title"'))
    assert example.rstrip().endswith("}"), "the JSON example must be one complete line"
    assert "\\n" in example, "line breaks in the caption must be shown escaped"


# --- inline delivery tags + tag-aware length enforcement --------------------------------

def test_visible_words_ignores_tags():
    assert scriptwriter._visible_words("a [pause long] b [sarcastic] c") == ["a", "b", "c"]


def test_word_cap_counts_only_spoken_words():
    """Tags are stage direction — counting them would silently shrink the 25-30s budget."""
    body = " ".join(["word"] * 70) + " [pause long] [sarcastic]"
    assert len(_words(body)) == 73          # naive split sees the tags
    assert len(scriptwriter._visible_words(body)) == 70


def _words(body):
    return body.split()


def test_truncate_preserves_tags_and_cuts_on_a_sentence():
    body = "One two three. [pause] Four five six. Seven eight nine."
    out = scriptwriter._truncate_to_words(body, 6)
    assert out.endswith(".")
    assert "[pause]" in out
    assert "Seven" not in out


def test_truncate_does_not_count_tags_toward_the_cap():
    """A tag-heavy script must not be truncated earlier than a tag-free one."""
    plain = "One two three four five six. Seven eight."
    tagged = "One two [pause] three four [sarcastic] five six. Seven eight."
    assert scriptwriter._visible_words(scriptwriter._truncate_to_words(tagged, 6)) == \
           scriptwriter._visible_words(scriptwriter._truncate_to_words(plain, 6))


def test_truncate_noop_when_under_cap_even_with_tags():
    body = "One two. [pause] Three four."
    assert scriptwriter._truncate_to_words(body, 50) == body


def test_prompt_teaches_three_tags_at_most_two():
    """Design 9.1: the tags shrink to [pause], [serious] and [curious], at most two."""
    prompt = scriptwriter._build_prompt(IDEA, "N")
    for tag in ("[pause]", "[serious]", "[curious]"):
        assert tag in prompt, tag
    for gone in ("[sarcastic]", "[deadpan]", "[dry]", "[mischievously]", "[whispers]"):
        assert gone not in prompt, gone
    assert "..." in prompt          # ellipses work on engines with no tag support
    assert "at most two delivery tags" in prompt


def test_prompt_puts_serious_on_the_payoff():
    """The tag floor in code (_ensure_delivery_tag) puts [serious] on the payoff when the writer
    adds no tag; the prompt names the same place."""
    prompt = scriptwriter._build_prompt(IDEA, "N")
    assert "[serious] belongs on the payoff" in prompt


# --- delivery-tag floor (2026-08-07) ---------------------------------------------------------
# Measured against the last 5 produced scripts: 2 shipped with NO delivery tags at all.

def test_untagged_script_gets_serious_on_the_payoff_turn():
    body = ("Fifteen of twenty-two firms had ties to the panel. So much for deep-tech. "
            "Here's why it actually matters: the money was public.")
    out = scriptwriter._ensure_delivery_tag(body)
    assert "[serious] Here's why it actually matters" in out
    assert out.count("[serious]") == 1


def test_floor_leaves_an_already_tagged_script_alone():
    body = "A thing happened. [sarcastic] Shocking. Here's why it matters: it costs you money."
    assert scriptwriter._ensure_delivery_tag(body) == body


def test_floor_does_not_guess_when_there_is_no_bridge():
    """A tag in the wrong sentence is worse than no tag, so this must no-op, not approximate."""
    body = "A thing happened. Another thing happened. Then it stopped."
    assert scriptwriter._ensure_delivery_tag(body) == body


def test_floor_tag_is_one_the_voice_module_will_actually_forward():
    """The bug this whole thread started from: a tag emitted but silently stripped downstream."""
    from src import voice
    out = scriptwriter._ensure_delivery_tag("Stuff happened. Here's why it matters: cost.")
    assert voice.has_style_tag(out)
    assert "[serious]" in voice._style_text(out)


def test_floor_inserts_at_the_sentence_start_not_mid_clause():
    body = "The rule changed in April. It matters because your bill moves."
    out = scriptwriter._ensure_delivery_tag(body)
    assert out == "The rule changed in April. [serious] It matters because your bill moves."


def test_floor_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_TAG_FLOOR", "false")
    body = "Stuff happened. Here's why it matters: cost."
    assert scriptwriter._ensure_delivery_tag(body) == body


def test_missing_why_it_matters_turn_is_warned_about(monkeypatch, caplog):
    """A script with no payoff turn is a bare SUMMARY — the originality/monetization risk in
    docs/08 §1. Found live on script 158, where it shipped because nothing checked."""
    import logging
    monkeypatch.setattr(scriptwriter, "_generate_script_json", lambda _p: {
        "title": "T",
        "script_body": "A thing happened today. Another thing happened. Then it stopped. " * 6,
        "caption": "c", "hashtags": ["#x"]})
    monkeypatch.setattr(scriptwriter, "_punch_up_hook", lambda t, b: (t, b))
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a, **k: 1)

    with caplog.at_level(logging.WARNING):
        scriptwriter.write_script({"id": 1, "title": "t", "sources": ["https://a.example"]})
    assert "NO 'why it matters' turn" in caplog.text


def test_present_why_it_matters_turn_is_not_warned_about(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(scriptwriter, "_generate_script_json", lambda _p: {
        "title": "T",
        "script_body": ("A thing happened today and it was quite something to behold. " * 5
                        + "Here's why it actually matters: the money was public."),
        "caption": "c", "hashtags": ["#x"]})
    monkeypatch.setattr(scriptwriter, "_punch_up_hook", lambda t, b: (t, b))
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a, **k: 1)

    with caplog.at_level(logging.WARNING):
        scriptwriter.write_script({"id": 1, "title": "t", "sources": ["https://a.example"]})
    assert "NO 'why it matters' turn" not in caplog.text


def test_floor_does_not_add_spoken_words():
    """Tags are stage direction — the floor must not eat into the 25-30s word budget."""
    body = "Stuff happened here. Here's why it matters: it costs money."
    before = len(scriptwriter._visible_words(body))
    after = len(scriptwriter._visible_words(scriptwriter._ensure_delivery_tag(body)))
    assert before == after


# --- the word cap must not amputate the payoff --------------------------------------------

def _long_body_with_payoff(filler_sentences: int = 12) -> str:
    filler = " ".join(
        f"Setup sentence number {i} adds context that is not load bearing at all."
        for i in range(filler_sentences))
    return filler + " Here's why it actually matters: your grocery bill goes up next month."


def test_truncation_keeps_the_why_it_matters_turn(monkeypatch):
    """The cap cut from the END, which is exactly where the payoff lives.

    Observed live (run 32920283763): idea 224 logged `104 words > 80 cap; truncating to a
    sentence.` and, on the very next line, `has NO 'why it matters' turn`. The truncation
    CAUSED the warning. That turn is the originality signal the monetization gate turns on
    (docs/08 §1), so losing it is the most expensive word to drop, not the cheapest.
    """
    body = _long_body_with_payoff()
    out = scriptwriter._truncate_to_words(body, 40)

    assert len(scriptwriter._visible_words(out)) <= 40, "the cap must still be respected"
    assert scriptwriter._WHY_IT_MATTERS_RE.search(out), "the payoff turn must survive truncation"
    assert out.rstrip().endswith("."), "must still end on a full sentence, never mid-thought"


def test_truncation_is_unchanged_when_there_is_no_payoff_turn():
    """No bridge to protect -> the original keep-the-front behaviour."""
    body = " ".join(f"Sentence {i} carries no bridge at all." for i in range(20))
    out = scriptwriter._truncate_to_words(body, 30)
    assert len(scriptwriter._visible_words(out)) <= 30
    assert out.startswith("Sentence 0")


def test_truncation_leaves_a_short_script_alone():
    body = "Short and sweet. Here's why it matters: it just does."
    assert scriptwriter._truncate_to_words(body, 80) == body


# --- grounded budget control (2026-09-03 audit) -------------------------------------------
# The scriptwriter's grounded write is 1 of the 7 calls a 3-reel run spends from the shared
# 20/day bucket. When that bucket runs dry the FACT-CHECK gate is what stops working, and the
# gate matters more than grounding the first draft (it re-verifies the finished script anyway).
# So this is a knob the operator can turn, not a silent default change: grounding stays ON.

def test_grounded_write_is_on_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded",
                        lambda *a, **k: calls.append("grounded") or '{"script_body": "b"}')
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: '{"script_body": "u"}')
    assert scriptwriter._generate_script_json("p")["script_body"] == "b"
    assert calls == ["grounded"]


def test_grounded_write_can_be_switched_off_to_save_the_gates_quota(monkeypatch):
    monkeypatch.setenv("ENABLE_GROUNDED_SCRIPT", "false")
    calls = []
    # Recording, not raising: _generate_script_json catches everything and falls back, so a
    # raising double would be swallowed and the test would pass without the feature.
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded",
                        lambda *a, **k: calls.append("grounded") or '{"script_body": "b"}')
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: '{"script_body": "ungrounded"}')

    assert scriptwriter._generate_script_json("p")["script_body"] == "ungrounded"
    assert calls == [], "no grounded request may be sent when the toggle is off"


def test_sources_are_listed_one_per_line(monkeypatch):
    """Citations became Google News article links after the 2026-09-03 sourcing fix — 249-884
    chars each (measured). Joined with ' | ' two of them are an unreadable wall in the YouTube
    description; one per line at least keeps the block scannable."""
    caption = scriptwriter._ensure_sources("Hook.", ["https://a.example/1", "https://b.example/2"])
    assert caption.endswith("Sources:\na.example: https://a.example/1\n"
                            "b.example: https://b.example/2")


def test_sources_already_cited_are_not_repeated():
    caption = scriptwriter._ensure_sources("See https://a.example/1", ["https://a.example/1"])
    assert caption.count("https://a.example/1") == 1


# --- 2026-09-27 audit: length, sources, markdown, disclosure --------------------------------

_SCRIPT_267_SHAPE = (
    "Iran and the UAE just shook hands, two regional rivals who have been, shall we say, at odds "
    "in the West Asia neighbourhood for a very long time over shipping lanes, islands, proxies and "
    "oil. [serious] But it matters because a thaw between them changes what every tanker in the "
    "Gulf pays for insurance. Subscribe for the real story.")


def test_truncation_never_cuts_a_sentence_in_half():
    """Published script 267 went out mid-sentence: '...*at odds* in the West Asia [serious] But
    it matters because...'. A whole sentence is dropped instead, and the CTA goes first."""
    out = scriptwriter._truncate_to_words(_SCRIPT_267_SHAPE, 50)
    assert "Subscribe" not in out, "the call to action is the first thing cut"
    assert "at odds in the West Asia neighbourhood" in out, "the hook stays whole"
    assert "But it matters because" in out
    for sentence in scriptwriter._sentences(out):
        assert sentence.rstrip().endswith((".", "!", "?", "…")), sentence


def test_truncation_drops_the_close_before_the_facts():
    body = ("Hook sentence here. Fact one is important. Fact two matters too. "
            "Here's why it matters: prices rise. And that is the loop back. Subscribe now.")
    out = scriptwriter._truncate_to_words(body, 18)
    assert "Subscribe" not in out and "loop back" not in out
    assert "Fact one" in out and "prices rise" in out


def test_tighten_pass_is_used_when_the_draft_runs_long(monkeypatch):
    """Retired by default (design 9.5); it still works when switched on."""
    monkeypatch.setenv("ENABLE_SCRIPT_TIGHTEN", "true")
    long = " ".join(["Word"] * 90) + ". Here's why it matters: it does."
    tight = " ".join(["Word"] * 50) + ". Here's why it matters: it does."
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: '{"script_body": "%s"}' % tight)
    assert scriptwriter._enforce_length(long, 1) == tight


def test_tighten_pass_leaves_room_for_reasoning(monkeypatch):
    """At 1024 tokens idea 488's tighten failed on both providers (reasoning used the budget
    before the JSON was finished), and its reel shipped at 42 s."""
    seen = {}

    def _gen(prompt, **kw):
        seen.update(kw)
        return '{"script_body": "x"}'

    monkeypatch.setattr(scriptwriter.llm, "generate", _gen)
    scriptwriter._tighten(" ".join(["Word"] * 90) + ". Here's why it matters: it does.", 80)
    assert seen["max_tokens"] >= 4096


def test_tighten_pass_that_drops_the_payoff_is_refused(monkeypatch):
    monkeypatch.setenv("ENABLE_SCRIPT_TIGHTEN", "true")
    long = " ".join(["Word"] * 90) + ". Here's why it matters: it does."
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: '{"script_body": "%s."}' % " ".join(["Word"] * 50))
    out = scriptwriter._enforce_length(long, 1)
    assert scriptwriter._WHY_IT_MATTERS_RE.search(out)


def test_caption_gets_exactly_one_sources_block_of_real_links():
    """Every recent description had TWO 'Sources:' blocks; the model's own was 12/53 dead."""
    model_caption = ("Hook 📺\n\nSummary. 💬 Thoughts?\n\nSources:\n"
                     "https://www.voanews.com/a/invented-404\nhttps://latimes.com/also-invented")
    out = scriptwriter._ensure_sources(model_caption, [
        "https://www.afp.com/en/real", "https://www.afp.com/en/second-afp",
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ",
        "https://news.google.com/rss/articles/CBMi", "https://citizen.digital/a"])
    assert out.count("Sources:") == 1
    assert "voanews" not in out and "latimes" not in out, "model-written links are dropped"
    assert "vertexaisearch" not in out, "unresolved grounding redirects expire"
    assert out.count("afp.com") == 1, "one link per outlet"
    # publishers by name; the aggregator link goes when a publisher is there (design 9.9)
    assert out.splitlines()[-3:] == ["Sources:", "AFP: https://www.afp.com/en/real",
                                     "citizen.digital: https://citizen.digital/a"]
    assert "news.google.com" not in out


def test_a_redirect_is_kept_when_it_is_the_only_citation():
    out = scriptwriter._ensure_sources("Hook.", [
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/X"])
    assert "grounding-api-redirect/X" in out


def test_markdown_emphasis_is_stripped_from_the_narration():
    assert scriptwriter._strip_markdown("They did *that*, and **poof**.") == \
        "They did that, and poof."


def test_disclosure_matches_ai_imagery(monkeypatch):
    monkeypatch.setenv("VISUAL_SOURCE", "ai")
    assert scriptwriter._ensure_disclosure("Hook.").endswith(scriptwriter.DISCLOSURE_LINE_AI)
    monkeypatch.setenv("VISUAL_SOURCE", "photos")
    assert scriptwriter._ensure_disclosure("Hook.").endswith(scriptwriter.DISCLOSURE_LINE)


def test_the_prompt_no_longer_asks_the_model_for_links():
    prompt = scriptwriter._build_prompt(IDEA, "N")
    assert "Line 3: The real source link" not in prompt
    assert "Sources: ..." not in prompt
    assert "SINGLE quotes" in prompt


def test_punch_up_may_not_delete_the_why_it_matters_turn(monkeypatch):
    """Live 2026-09-27, idea 312: the rewrite dropped the payoff and nothing checked."""
    body = " ".join(["Word"] * 45) + ". Here's why it matters: it does."
    rewrite = " ".join(["Better"] * 50) + "."
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k:
                        '{"hook_score": 3, "title": "T2", "script_body": "%s"}' % rewrite)
    assert scriptwriter._punch_up_hook("T", body) == ("T", body)


def test_a_repair_that_loses_the_hook_is_refused(monkeypatch):
    """Live 2026-09-27: the first repair of idea 308 opened "[pause] [sarcastic] Because..."."""
    broken = ("[pause] [sarcastic] Because nothing screams harmony like threats. " +
              " ".join(["Word"] * 45) + ". Here's why it matters: prices rise.")
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded",
                        lambda *a, **k: '{"script_body": "%s"}' % broken)
    body = "The US passed a tariff law. " + " ".join(["Word"] * 45) + ". Here's why it matters: x."
    assert scriptwriter.repair_script(body, ["the law claim is false"], topic="tariffs") is None


def test_a_repair_with_a_corrected_opening_is_accepted(monkeypatch):
    good = ("The US House passed a bill allowing tariffs of up to 100 percent. " +
            " ".join(["Word"] * 45) + ". Here's why it matters: prices rise.")
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded",
                        lambda *a, **k: '{"script_body": "%s"}' % good)
    body = "The US passed a tariff law. " + " ".join(["Word"] * 45) + ". Here's why it matters: x."
    # The corrected facts come from the finding: the repair adds nothing its inputs lack.
    finding = "the law claim is false: the House passed a bill allowing tariffs up to 100 percent"
    out = scriptwriter.repair_script(body, [finding], topic="tariffs")
    assert out and out["script_body"].startswith("The US House passed")


def test_a_story_about_deaths_gets_the_somber_note():
    """The audit found the old fixed sarcastic voice on war strikes and a child-abuse story."""
    idea = {"id": 1, "title": "South Africa Mass Shootings: 27 Dead", "hook": "h", "angle": "a"}
    assert scriptwriter.tone_for(idea) == "somber"
    assert scriptwriter._SOMBER_NOTE in scriptwriter._build_prompt(idea, "N")
    assert scriptwriter._SOMBER_NOTE not in scriptwriter._build_prompt(IDEA, "N")
    assert scriptwriter.tone_for({"title": "Rupee hits a record low", "hook": "", "angle": ""}) \
        == "plain"


def test_the_base_and_ing_forms_of_harm_are_somber():
    """'kill', 'killing', 'deadly', a crash or an attack read as sarcastic until 2026-10-09."""
    for title in ("Russian missiles kill 3 in Kyiv", "Mob killing in Jharkhand",
                  "Deadly heatwave grips Delhi", "Air India plane crash in Ahmedabad",
                  "Terror attack in Pahalgam", "Drone strikes hit Kharkiv",
                  "Boat capsized off Kerala coast", "Stampede at temple fair"):
        assert scriptwriter.tone_for({"title": title}) == "somber", title


def test_everyday_strikes_and_crashes_keep_the_channel_voice():
    for title in ("Bank employees strike today", "Stock market crash wipes out Rs 10 lakh crore",
                  "Attack on press freedom", "Rupee collapses to a record low",
                  "India missing its climate targets"):
        assert scriptwriter.tone_for({"title": title}) == "plain", title


def test_the_finished_script_can_make_a_story_somber():
    """Idea 211's pitch read as not somber while its script said 'killed a woman'."""
    idea = {"title": "India's Aston Martin Crash Covered Up?"}
    assert scriptwriter.tone_for(idea, "An MP's son reportedly killed a woman.") == "somber"


def test_a_somber_story_skips_the_hook_punch_up(monkeypatch):
    monkeypatch.setattr(scriptwriter, "_punch_up_hook",
                        lambda t, b: pytest.fail("no shock copy on a story about deaths"))
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a, **k: 5)
    body = ("Twelve people died when a bridge collapsed in Gujarat on Tuesday. "
            "Here's why it matters: the bridge failed its last two inspections.")
    monkeypatch.setattr(scriptwriter, "_generate_script_json",
                        lambda p: {"title": "Bridge collapse kills 12", "script_body": body,
                                   "caption": "c", "hashtags": [], "tags": [], "key_points": []})
    out = scriptwriter.write_script({"id": 9, "title": "Gujarat bridge collapse", "sources": []})
    assert out["tone"] == "somber"


def test_the_disclosure_is_not_skipped_by_a_mention_of_ai(monkeypatch):
    """'AI-generated' anywhere used to count as the disclosure line."""
    monkeypatch.setenv("VISUAL_SOURCE", "ai")
    out = scriptwriter._ensure_disclosure("Why AI-generated art is everywhere\n\nSources:\nx")
    assert out.endswith("\n\n" + scriptwriter.DISCLOSURE_LINE_AI)
    assert scriptwriter._ensure_disclosure(out) == out  # and never added twice


def test_somber_tone_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("ENABLE_SOMBER_TONE", "false")
    assert scriptwriter.tone_for({"title": "27 killed", "hook": "", "angle": ""}) == "plain"


def test_copying_the_angle_is_detected():
    angle = "this sets a dangerous precedent for what information actually reaches the public"
    assert scriptwriter._copies_the_angle(
        "Here's why it matters: this sets a dangerous precedent for what information actually "
        "reaches the public.", angle)
    assert not scriptwriter._copies_the_angle("Here's why it matters: a new precedent.", angle)


def test_the_script_prompt_carries_todays_date():
    """A grounded draft dated September news to June, and another called a signed law pending."""
    assert scriptwriter._build_prompt(IDEA, "N").startswith("TODAY'S DATE: 20")


def test_a_long_title_is_cut_at_its_dash_when_the_head_fits(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    t = "Bank Strike Cancelled—Why It Almost Crashed the System"
    assert scriptwriter._shorten_title(t, "") == "Bank Strike Cancelled"
    cut = scriptwriter._shorten_title("word " * 30, "")
    assert len(cut) <= 44 and len(cut.split()) <= 7
    assert scriptwriter._shorten_title("Short title", "") == "Short title"


def _no_model(*a, **k):
    raise RuntimeError("model down")


def test_a_punched_up_title_is_held_to_the_limit_too(monkeypatch):
    """The title fit ran on the writer's title only; the hook doctor's replacement went out as is."""
    monkeypatch.setenv("ENABLE_HOOK_JUDGE", "true")
    reply = json.dumps({"title": "Short Title",
                        "script_body": "A clear analysis of why this matters for everyone. " * 6,
                        "caption": "hook line.", "hashtags": ["#Shorts"]})
    _patch(monkeypatch, reply)
    long_title = ("Nationwide Bank Strike Cancelled at the Last Minute—Why It Almost Crashed "
                  "the System")
    monkeypatch.setattr(scriptwriter, "_punch_up_hook", lambda t, b: (long_title, b))
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    out = scriptwriter.write_script(IDEA)
    assert out["title"] == "Nationwide Bank Strike Cancelled at the Last"
    assert len(out["title"]) <= 44 and len(out["title"].split()) <= 7


# --- the opening check on every script (design 9.2; audit data 4, script 3, voice-audio 4) --------

def _raiser(exc):
    def _fn(*_args, **_kwargs):
        raise exc

    return _fn


def test_opening_problem_flags_wind_ups_dates_and_short_openers():
    assert "wind-up" in scriptwriter.opening_problem("So, India just banned an app used by students.")
    assert "date" in scriptwriter.opening_problem("On November 18, Voyager 1 reaches one light-day.")
    assert "five words" in scriptwriter.opening_problem("Big news. India banned it today.")
    assert scriptwriter.opening_problem("India just banned the app millions of students use daily.") is None


def test_hedges_are_not_wind_ups():
    """Cutting 'Apparently,' would turn a hedged claim into a flat one before the fact-check."""
    assert scriptwriter.opening_problem("Apparently, India's new rule ends free UPI for big shops.") is None


def test_an_abbreviation_in_sentence_one_is_not_a_short_opener():
    assert scriptwriter.opening_problem("The U.S. Fed cut rates by 0.25 points today.") is None


def test_a_wind_up_is_cut_when_the_rewrite_fails(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", _raiser(RuntimeError("down")))
    fixed = scriptwriter._fix_opening("So, India banned the app students use daily. More here.",
                                      "opens on the wind-up 'so'", "India banned the app")
    assert fixed.startswith("India banned the app students use daily.")


def test_a_rewrite_that_adds_a_number_is_refused(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k:
                        '{"first_sentence": "India banned 3 apps used by 40 crore people."}')
    fixed = scriptwriter._fix_opening("So, India banned the app students use daily. More here.",
                                      "opens on the wind-up 'so'", "India banned the app")
    assert "40" not in fixed and fixed.startswith("India banned the app")


# --- final review, 2026-11-12 --------------------------------------------------------------

def test_the_cut_never_garbles_an_opening(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", _raiser(RuntimeError("down")))
    fixed = scriptwriter._fix_opening("Did you know that India has 28 states now? More here.",
                                      "it opens on the wind-up 'did you know'", "India 28 states")
    assert fixed.startswith("India has 28 states now.")
    body = "So India banned the app students use daily. More here."
    assert scriptwriter._fix_opening(body, "it opens on the conjunction 'so'", body) == body


def test_names_and_so_far_are_not_wind_ups():
    for opener in ("So far this year, 40 startups have shut down in Bengaluru.",
                   "Imagine Dragons cancelled their Mumbai show after the storm.",
                   "Let's Encrypt revoked millions of certificates this week."):
        assert scriptwriter.opening_problem(opener) is None, opener


def test_a_curly_apostrophe_wind_up_is_caught():
    assert "wind-up" in scriptwriter.opening_problem(
        "Here’s why your UPI payments may soon cost money.")


def test_a_punch_up_that_reopens_on_a_wind_up_is_refused(monkeypatch):
    body = ("India banned the app millions of students use daily. " + "More words here. " * 10
            + "Here's why it matters: exams.")
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: json.dumps(
        {"hook_score": 3, "title": "New", "script_body": "So, " + body}))
    title, new = scriptwriter._punch_up_hook("Old", body)
    assert new == body and title == "Old"


def test_the_payoff_tag_lands_on_the_payoff_after_a_us_sentence():
    out = scriptwriter._ensure_delivery_tag("Prices rose in the U.S. Here's why it matters to you.")
    assert out == "Prices rose in the U.S. [serious] Here's why it matters to you."


# --- stage 1b: the writer's brief (design 9.1) -----------------------------------------------

def test_the_brief_names_the_viewer_and_drops_the_roast():
    p = scriptwriter._PROMPT_N
    assert "Indians aged about 18-34" in p and "what changes for a person in India" in p
    for gone in ("SARCASTIC", "roast", "Here's the catch", "Wait, it gets weirder",
                 "Comment below", "💬", "[sarcastic]", "[deadpan]"):
        assert gone not in p, gone


def test_the_somber_note_needs_no_bridge_phrase():
    assert "Here's why it matters" not in scriptwriter._SOMBER_NOTE


# --- stage 1b: three structures (design 9.3) -------------------------------------------------

def test_the_structure_is_stable_per_idea_and_somber_takes_the_first():
    assert set(scriptwriter.STRUCTURES) == {"what-happened", "number", "belief"}
    idea = {"id": 42, "title": "Rupee hits a record low", "hook": "", "angle": ""}
    assert scriptwriter.structure_for(idea) == scriptwriter.structure_for(dict(idea))
    seen = {scriptwriter.structure_for({"id": i, "title": "Rupee hits a record low"})
            for i in range(1, 61)}
    assert seen == set(scriptwriter.STRUCTURES)
    somber = {"title": "Bridge collapse kills 12 in Gujarat", "hook": "", "angle": ""}
    assert {scriptwriter.structure_for({**somber, "id": i}) for i in range(1, 61)} \
        == {"what-happened"}


def test_the_structure_block_reaches_the_prompt():
    idea = next({**IDEA, "id": i} for i in range(1, 300)
                if scriptwriter.structure_for({**IDEA, "id": i}) == "number")
    prompt = scriptwriter._build_prompt(idea, "N")
    assert scriptwriter.STRUCTURES["number"] in prompt
    assert scriptwriter.STRUCTURES["belief"] not in prompt
    assert scriptwriter.STRUCTURES["what-happened"] not in prompt


def test_write_script_stores_the_writers_known_structure_else_the_chosen_one(monkeypatch):
    chosen = scriptwriter.structure_for(IDEA)
    other = next(s for s in scriptwriter.STRUCTURES if s != chosen)
    body = "ISRO's rocket landed itself on Tuesday. " * 3
    for said, stored in ((other, other), ("a listicle", chosen), (None, chosen)):
        reply = {"script_body": body, "caption": "c", "hashtags": []}
        if said:
            reply["structure"] = said
        captured = _patch(monkeypatch, json.dumps(reply))
        out = scriptwriter.write_script(IDEA)
        assert out["structure"] == stored and captured["structure"] == stored, said


# --- stage 1b: one short title, which is also the banner (design 9.4) ------------------------

_LONG_TITLE = "India has just banned 3 popular apps for every school student in the country"
_TITLE_BODY = "India banned 3 apps for students on Monday. Here's why it matters for schools."


def test_a_title_within_the_limits_is_kept(monkeypatch):
    assert scriptwriter._TITLE_MAX == 44 and scriptwriter._TITLE_MAX_WORDS == 7
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: pytest.fail("no model call for a title that fits"))
    title = "ISRO's new rocket can land itself"
    assert scriptwriter._shorten_title(title, "body") == title


def test_a_long_title_is_shortened_once(monkeypatch):
    calls = []
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: calls.append(a) or
                        json.dumps({"title": "India bans 3 apps for students"}))
    assert scriptwriter._shorten_title(_LONG_TITLE, _TITLE_BODY) == "India bans 3 apps for students"
    assert len(calls) == 1


def test_a_long_title_is_cut_at_a_word(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    out = scriptwriter._shorten_title(_LONG_TITLE, _TITLE_BODY)
    assert len(out) <= 44 and len(out.split()) <= 7
    assert out.split() == _LONG_TITLE.split()[:len(out.split())]  # whole words, never mid-word
    assert out == "India has just banned 3 popular apps"


def test_a_shortened_title_that_adds_a_fact_is_refused(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: json.dumps({"title": "India bans 5 apps for students"}))
    assert scriptwriter._shorten_title(_LONG_TITLE, _TITLE_BODY) == \
        "India has just banned 3 popular apps"


def test_a_shortened_title_still_too_long_is_refused(monkeypatch):
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: json.dumps(
        {"title": "India has banned 3 popular apps for every student"}))
    assert scriptwriter._shorten_title(_LONG_TITLE, _TITLE_BODY) == \
        "India has just banned 3 popular apps"


def test_a_missing_title_falls_back_to_the_idea_title_within_the_limits(monkeypatch):
    """With no title from the writer, the idea's title went out unshortened and unchecked."""
    captured = _patch(monkeypatch, json.dumps({"script_body": "ISRO's rocket landed itself. " * 3,
                                               "caption": "c", "hashtags": []}))
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    out = scriptwriter.write_script(IDEA)  # "ISRO's reusable rocket, explained - why it matters"
    assert out["title"] == "ISRO's reusable rocket, explained" == captured["title"]


# --- stage 1b: length in seconds, writer-marked cuts, the payoff by index (design 9.5, 9.1) ---

def _sent(word: str, n: int) -> str:
    return " ".join([word.capitalize()] + [word.lower()] * (n - 1)) + "."


# 85 spoken words: sentence 0 has 10, the other five 15 each. Sentence 4 is the payoff and says
# nothing the 'why it matters' pattern would match.
_S = [_sent("zero", 10), _sent("one", 15), _sent("two", 15), _sent("three", 15),
      _sent("four", 15), _sent("five", 15)]
_LONG_BODY = " ".join(_S)


def _clear_length(monkeypatch):
    for k in ("SCRIPT_MAX_WORDS", "SCRIPT_MAX_SECONDS", "SCRIPT_TARGET_SECONDS",
              "ENABLE_SCRIPT_TIGHTEN"):
        monkeypatch.delenv(k, raising=False)


def test_the_budget_is_set_in_seconds(monkeypatch):
    _clear_length(monkeypatch)
    assert scriptwriter._max_words() == 73 and scriptwriter._target_words() == 59
    monkeypatch.setenv("SCRIPT_MAX_SECONDS", "30")
    assert scriptwriter._max_words() == 66
    monkeypatch.setenv("SCRIPT_MAX_WORDS", "80")
    assert scriptwriter._max_words() == 80
    monkeypatch.setenv("SCRIPT_TARGET_SECONDS", "25")
    assert scriptwriter._target_words() == 55
    assert "about 25 seconds" in scriptwriter._build_prompt(IDEA, "N")


def test_optional_sentences_go_first_and_never_the_payoff(monkeypatch):
    _clear_length(monkeypatch)
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    assert len(scriptwriter._visible_words(_LONG_BODY)) == 85
    # 85 > 73: dropping sentence 2 is enough (70 words); 4 is the payoff, so it stays.
    out = scriptwriter._enforce_length(_LONG_BODY, 1, optional=[2, 4], payoff=4)
    assert out == " ".join([_S[0], _S[1], _S[3], _S[4], _S[5]])
    # At 50, sentence 2 goes, then whole sentences from the end, never 0 or the payoff.
    monkeypatch.setenv("SCRIPT_MAX_WORDS", "50")
    out = scriptwriter._enforce_length(_LONG_BODY, 1, optional=[2, 4], payoff=4)
    assert _S[0] in out and _S[4] in out and _S[2] not in out
    assert len(scriptwriter._visible_words(out)) <= 50


def test_over_budget_without_optional_sentences_keeps_the_payoff(monkeypatch):
    _clear_length(monkeypatch)
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    monkeypatch.setenv("SCRIPT_MAX_WORDS", "40")
    out = scriptwriter._enforce_length(_LONG_BODY, 1, payoff=2)
    assert out.startswith(_S[0]) and _S[2] in out
    assert len(scriptwriter._visible_words(out)) <= 40


def test_the_tighten_rewrite_is_off_by_default(monkeypatch):
    _clear_length(monkeypatch)
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: pytest.fail("no tighten call by default"))
    scriptwriter._enforce_length(_LONG_BODY, 1)


def test_the_payoff_tag_follows_payoff_index():
    body = "Fact one here. Fact two here. Prices will rise by June. More detail follows."
    out = scriptwriter._ensure_delivery_tag(body, payoff=2)
    assert out == "Fact one here. Fact two here. [serious] Prices will rise by June. " \
                  "More detail follows."
    assert scriptwriter._ensure_delivery_tag(body, payoff=9) == body  # out of range: no guess


def test_write_script_uses_the_writers_payoff_and_optional_marks(monkeypatch, caplog):
    _clear_length(monkeypatch)
    captured = _patch(monkeypatch, json.dumps({
        "title": "Zero news", "script_body": _LONG_BODY, "caption": "c", "hashtags": [],
        "payoff_index": 4, "optional": [2]}))
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)
    with caplog.at_level("WARNING"):
        out = scriptwriter.write_script(IDEA)
    assert _S[2] not in out["script_body"]
    assert "[serious] " + _S[4] in out["script_body"] and captured["body"] == out["script_body"]
    assert "NO 'why it matters'" not in caplog.text


def test_a_script_without_the_new_fields_still_ships(monkeypatch):
    _clear_length(monkeypatch)
    body = "ISRO's rocket landed itself on Tuesday. Here's why it matters: launches get cheaper."
    _patch(monkeypatch, json.dumps({"title": "ISRO rocket lands itself", "script_body": body,
                                    "caption": "c", "hashtags": []}))
    out = scriptwriter.write_script(IDEA)
    assert out["script_body"] == ("ISRO's rocket landed itself on Tuesday. [serious] Here's why it "
                                  "matters: launches get cheaper.")
    assert out["structure"] == scriptwriter.structure_for(IDEA)


def test_the_hook_judge_is_off_by_default(monkeypatch):
    _clear_length(monkeypatch)
    monkeypatch.delenv("ENABLE_HOOK_JUDGE", raising=False)
    body = "ISRO's rocket landed itself on Tuesday. Here's why it matters: launches get cheaper."
    _patch(monkeypatch, json.dumps({"title": "ISRO rocket lands itself", "script_body": body,
                                    "caption": "c", "hashtags": []}))
    calls = []
    monkeypatch.setattr(scriptwriter, "_punch_up_hook", lambda t, b: calls.append(1) or (t, b))
    scriptwriter.write_script(IDEA)
    assert calls == []
    monkeypatch.setenv("ENABLE_HOOK_JUDGE", "true")
    scriptwriter.write_script(IDEA)
    assert calls == [1]


def test_a_punch_up_that_adds_a_fact_is_refused(monkeypatch):
    """Every model-written rewrite passes the added-facts guard (design 9.6)."""
    body = "ISRO's rocket landed itself on Tuesday. " + "word " * 50
    monkeypatch.setattr(scriptwriter.llm, "generate", lambda *a, **k: json.dumps(
        {"hook_score": 2, "title": "ISRO rocket lands 3 times",
         "script_body": "ISRO's rocket landed itself 3 times on Tuesday. " + "word " * 50}))
    assert scriptwriter._punch_up_hook("Old", body) == ("Old", body)


# --- stage 1b: the repair adds no fact and may fix the title (design 9.6) --------------------

_REPAIR_BODY = ("The US passed a tariff law. " + " ".join(["Word"] * 45) +
                ". Here's why it matters: prices rise.")


def _repair_reply(monkeypatch, body, title=None):
    reply = {"script_body": body}
    if title is not None:
        reply["title"] = title
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded", lambda *a, **k: json.dumps(reply))
    monkeypatch.setattr(scriptwriter.llm, "generate", _no_model)


def test_a_repair_that_adds_a_fact_is_refused(monkeypatch):
    _repair_reply(monkeypatch, "The US passed a tariff law of 75 percent. " +
                  " ".join(["Word"] * 45) + ". Here's why it matters: prices rise.")
    assert scriptwriter.repair_script(_REPAIR_BODY, ["the law claim is false"], topic="tariffs",
                                      title="US tariff law passes") is None


def test_the_repair_may_fix_the_title(monkeypatch):
    findings = ["the title calls it a law; only the House passed the bill"]
    fixed = ("The US House passed a tariff bill. " + " ".join(["Word"] * 45) +
             ". Here's why it matters: prices rise.")
    _repair_reply(monkeypatch, fixed, title="US House passes a tariff bill")
    out = scriptwriter.repair_script(_REPAIR_BODY, findings, topic="tariffs",
                                     title="US tariff law passes")
    assert out["script_body"].startswith("The US House passed")
    assert out["title"] == "US House passes a tariff bill"
    # Held to the title limits: the shortening call fails here, so the word cut applies.
    _repair_reply(monkeypatch, fixed, title="The US House passes a tariff bill that is not yet a law")
    out = scriptwriter.repair_script(_REPAIR_BODY, findings, topic="tariffs",
                                     title="US tariff law passes")
    assert len(out["title"]) <= 44 and len(out["title"].split()) <= 7
    # No title in the reply: the original stays.
    _repair_reply(monkeypatch, fixed)
    out = scriptwriter.repair_script(_REPAIR_BODY, findings, topic="tariffs",
                                     title="US tariff law passes")
    assert out["title"] == "US tariff law passes"


# --- stage 1b: the draft's grounding is counted, and Claude is told only what is true (9.7) ---

def test_the_draft_reports_its_citations(monkeypatch):
    draft = json.dumps({"title": "ISRO rocket lands itself", "caption": "c", "hashtags": [],
                        "script_body": "ISRO's rocket landed itself on Tuesday. Here's why it "
                                       "matters: launches get cheaper."})
    monkeypatch.setattr(scriptwriter.db, "insert_script", lambda *a, **k: 1)
    for n, wording in ((3, scriptwriter._DRAFT_SEARCHED), (0, scriptwriter._DRAFT_UNSEARCHED)):
        notes = []

        def _grounded(prompt, meta=None, n=n, **k):
            if meta is not None:
                meta["citations"] = n
            return draft

        monkeypatch.setattr(scriptwriter.llm, "generate_grounded", _grounded)
        monkeypatch.setattr(scriptwriter.llm, "generate_claude",
                            lambda p, **k: notes.append(p) or draft)
        out = scriptwriter.write_script(IDEA)
        assert out["grounding"] == {"draft_citations": n}
        assert wording in notes[-1], n


# --- stage 1b: a readable description (design 9.9) -------------------------------------------

def test_sources_are_publisher_names_with_their_links():
    out = scriptwriter._ensure_sources("Hook.", ["https://www.thehindu.com/news/a",
                                                 "https://news.google.com/rss/articles/X",
                                                 "https://example.org/b"])
    assert out.endswith("Sources:\nThe Hindu: https://www.thehindu.com/news/a\n"
                        "example.org: https://example.org/b")


def test_sources_keep_one_link_when_only_aggregators_exist():
    out = scriptwriter._ensure_sources("Hook.", ["https://news.google.com/rss/articles/A",
                                                 "https://news.google.com/rss/articles/B"])
    assert out.endswith("Sources:\nGoogle News: https://news.google.com/rss/articles/A")


def test_the_disclosure_line_follows_the_visual_source(monkeypatch):
    for source, line in (("ai_video", "AI-generated narration, video and music."),
                         ("ai", scriptwriter.DISCLOSURE_LINE_AI),
                         ("photos", scriptwriter.DISCLOSURE_LINE),
                         ("video", scriptwriter.DISCLOSURE_LINE)):
        monkeypatch.setenv("VISUAL_SOURCE", source)
        assert scriptwriter._ensure_disclosure("Hook.").endswith("\n\n" + line), source


def test_write_script_no_longer_adds_shorts(monkeypatch):
    _patch(monkeypatch, json.dumps({"title": "ISRO rocket lands itself", "caption": "c",
                                    "script_body": "ISRO's rocket landed itself on Tuesday.",
                                    "hashtags": ["#ISRO"]}))
    assert scriptwriter.write_script(IDEA)["hashtags"] == ["#ISRO"]
