"""Claude as the scriptwriter, held to a monthly budget (operator, 2026-10-22).

Claude is billed per call, so the budget guard is the part that must not fail open: no key, an
unusable ledger or a spent month means no request is sent, and a call that may have been billed
is counted at its worst case. The scriptwriter side checks that Claude adds no facts the grounded
draft does not carry, and that every Claude failure lands on the Gemini path the pipeline ran
before (rule 11).
"""
from __future__ import annotations

import json

from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from src import db, llm, scriptwriter

_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, code):
    return cls("err", response=httpx2.Response(code, request=_REQ), body=None)


def _reply(text='{"script_body": "claude"}', stop="end_turn", input_tokens=3000,
           output_tokens=1200):
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_creation_input_tokens=None, cache_read_input_tokens=None),
    )


class _FakeClaude:
    """messages.create answers from `script`: replies are returned, exceptions raised, in turn."""

    def __init__(self, *script):
        self.calls = []
        self.script = list(script) or [_reply()]
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


class _Ledger:
    """In-memory claude_spend: reserve, settle, release and the month's sum."""

    def __init__(self, already_spent=0.0):
        self.already_spent, self.rows, self.next_id = already_spent, {}, 1

    def reserve(self, **row):
        rid, self.next_id = self.next_id, self.next_id + 1
        self.rows[rid] = {**row, "settled": False}
        return rid

    def settle(self, rid, **row):
        self.rows[rid].update(row, settled=True)

    def release(self, rid):
        del self.rows[rid]

    def spent(self):
        return self.already_spent + sum(r["cost_usd"] for r in self.rows.values())


@pytest.fixture
def claude(monkeypatch):
    """A key, an empty ledger and a fake Anthropic client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    for knob in ("ANTHROPIC_EFFORT", "ANTHROPIC_MONTHLY_BUDGET_USD", "ENABLE_CLAUDE_SCRIPT"):
        monkeypatch.delenv(knob, raising=False)  # a local .env must not change the defaults
    monkeypatch.setattr(llm, "_ANTHROPIC_MODEL", "claude-opus-5-5")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    ledger = _Ledger()
    monkeypatch.setattr(db, "reserve_claude_spend", ledger.reserve)
    monkeypatch.setattr(db, "settle_claude_spend", ledger.settle)
    monkeypatch.setattr(db, "release_claude_spend", ledger.release)
    monkeypatch.setattr(db, "claude_spend_this_month", ledger.spent)
    fake = _FakeClaude()
    monkeypatch.setattr(llm, "_anthropic_client", lambda: fake)
    return SimpleNamespace(client=fake, ledger=ledger)


def _use(claude, *script):
    claude.client.script = list(script)


# --- the budget guard ---------------------------------------------------------------------------

def test_no_key_means_no_call(claude, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(llm.ClaudeUnavailable) as e:
        llm.generate_claude("p")
    assert e.value.kind == "no-key"
    assert claude.client.calls == []


def test_an_unusable_ledger_refuses_the_call(claude, monkeypatch):
    def _down(**_row):
        raise RuntimeError("relation claude_spend does not exist")

    monkeypatch.setattr(db, "reserve_claude_spend", _down)
    with pytest.raises(llm.ClaudeUnavailable) as e:
        llm.generate_claude("p")
    assert e.value.kind == "ledger"
    assert claude.client.calls == []


def test_an_unreadable_sum_refuses_the_call_and_drops_its_reservation(claude, monkeypatch):
    def _down():
        raise RuntimeError("timeout")

    monkeypatch.setattr(db, "claude_spend_this_month", _down)
    with pytest.raises(llm.ClaudeUnavailable) as e:
        llm.generate_claude("p")
    assert e.value.kind == "ledger"
    assert claude.ledger.rows == {}
    assert claude.client.calls == []


def test_a_call_that_could_pass_the_budget_is_not_sent(claude):
    # Opus 5.5 at 8,000 output tokens can cost $0.16, so $3.90 spent leaves no room under $4.
    claude.ledger.already_spent = 3.90
    with pytest.raises(llm.ClaudeUnavailable) as e:
        llm.generate_claude("p")
    assert e.value.kind == "budget"
    assert claude.ledger.rows == {}, "a refused call must not leave its reservation behind"
    assert claude.client.calls == []


def test_the_budget_is_configurable(claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MONTHLY_BUDGET_USD", "0")
    with pytest.raises(llm.ClaudeUnavailable):
        llm.generate_claude("p")
    assert claude.client.calls == []


def test_the_reservation_is_counted_before_the_check(claude, monkeypatch):
    """Two runs at once: each reserves its worst case first, so each sees the other's."""
    seen = []
    real_spent = claude.ledger.spent
    monkeypatch.setattr(db, "claude_spend_this_month", lambda: seen.append(
        {k: dict(v) for k, v in claude.ledger.rows.items()}) or real_spent())
    llm.generate_claude("p")
    assert len(seen[0]) == 1 and not next(iter(seen[0].values()))["settled"]


def test_a_call_is_sent_settles_its_real_cost_and_returns_the_text(claude):
    assert llm.generate_claude("write it", purpose="script") == '{"script_body": "claude"}'

    sent = claude.client.calls[0]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] == 8000
    assert sent["messages"] == [{"role": "user", "content": "write it"}]
    assert "thinking" not in sent, "Opus 5.5 rejects disabled thinking; effort is the lever"

    (row,) = claude.ledger.rows.values()
    assert row["settled"]
    assert (row["model"], row["purpose"]) == ("claude-opus-5-5", "script")
    assert (row["input_tokens"], row["output_tokens"]) == (3000, 1200)
    assert row["cost_usd"] == pytest.approx(3000 * 4 / 1e6 + 1200 * 20 / 1e6)


@pytest.mark.parametrize("effort, max_tokens", [("low", 8000), ("medium", 12000),
                                                ("high", 16000), ("MEDIUM", 12000)])
def test_room_to_think_grows_with_the_effort(claude, monkeypatch, effort, max_tokens):
    """Thinking tokens count against max_tokens: a fixed 8,000 cut off high-effort replies."""
    monkeypatch.setenv("ANTHROPIC_EFFORT", effort)
    llm.generate_claude("p")
    assert claude.client.calls[0]["output_config"] == {"effort": effort.lower()}
    assert claude.client.calls[0]["max_tokens"] == max_tokens


def test_an_unknown_effort_is_a_config_error_not_a_400_per_reel(claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EFFORT", "minimal")
    with pytest.raises(llm.ClaudeUnavailable) as e:
        llm.generate_claude("p")
    assert e.value.kind == "config"
    assert claude.client.calls == []


def test_a_refusal_is_paid_for_and_raises(claude):
    _use(claude, _reply(text="", stop="refusal"))
    with pytest.raises(RuntimeError, match="refusal"):
        llm.generate_claude("p")
    (row,) = claude.ledger.rows.values()
    assert row["settled"], "a refused call is billed, so it stays in the ledger"


def test_a_cut_off_reply_raises(claude):
    _use(claude, _reply(text='{"script_body": "half', stop="max_tokens"))
    with pytest.raises(RuntimeError, match="max_tokens"):
        llm.generate_claude("p")


def test_a_timeout_keeps_the_worst_case_and_is_not_retried(claude):
    """The request was sent and may have been billed: the ledger keeps its worst case."""
    _use(claude, anthropic.APITimeoutError(request=_REQ))
    with pytest.raises(anthropic.APITimeoutError):
        llm.generate_claude("p")
    assert len(claude.client.calls) == 1
    (row,) = claude.ledger.rows.values()
    assert not row["settled"]
    assert row["cost_usd"] == pytest.approx(llm.claude_cost_usd("claude-opus-5-5", 1, 8000))


def test_an_overloaded_api_is_retried_once_and_not_counted(claude):
    _use(claude, _status_error(anthropic.InternalServerError, 529), _reply())
    assert llm.generate_claude("p") == '{"script_body": "claude"}'
    assert len(claude.client.calls) == 2
    assert len(claude.ledger.rows) == 1


def test_a_second_overload_gives_up_and_releases_the_reservation(claude):
    _use(claude, _status_error(anthropic.RateLimitError, 429),
         _status_error(anthropic.RateLimitError, 429))
    with pytest.raises(anthropic.RateLimitError):
        llm.generate_claude("p")
    assert claude.ledger.rows == {}, "an error status was not billed"


@pytest.mark.parametrize("cls, code", [(anthropic.AuthenticationError, 401),
                                       (anthropic.PermissionDeniedError, 403),
                                       (anthropic.BadRequestError, 400),
                                       (anthropic.NotFoundError, 404)])
def test_a_rejected_configuration_is_reported_as_misconfigured(claude, cls, code):
    _use(claude, _status_error(cls, code))
    with pytest.raises(llm.ClaudeMisconfigured):
        llm.generate_claude("p")
    assert len(claude.client.calls) == 1, "a bad key or model is not worth a retry"
    assert claude.ledger.rows == {}


def test_a_failed_settle_leaves_the_worst_case_counted(claude, monkeypatch):
    def _cannot_write(*_a, **_k):
        raise RuntimeError("update failed")

    monkeypatch.setattr(db, "settle_claude_spend", _cannot_write)
    assert llm.generate_claude("p") == '{"script_body": "claude"}'
    (row,) = claude.ledger.rows.values()
    assert not row["settled"] and row["cost_usd"] > 0.15


def test_an_unpriced_model_is_costed_at_the_top_tier():
    assert llm.claude_cost_usd("claude-somethng-typo", 1_000_000, 0) == 10.00
    assert llm.claude_cost_usd("claude-opus-5-5", 1_000_000, 1_000_000) == 24.00


# --- the ledger -----------------------------------------------------------------------------------

class _Table:
    def __init__(self, rows=()):
        self.rows, self.op, self.payload, self.filters = list(rows), None, None, []

    def table(self, name):
        assert name == "claude_spend"
        return self

    def select(self, _cols):
        self.op = "select"
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows if self.op == "select" else [{"id": 7}])


def test_the_month_is_summed_from_the_first_of_the_month_utc(monkeypatch):
    fake = _Table([{"cost_usd": "0.037"}, {"cost_usd": 0.066}, {"cost_usd": None}])
    monkeypatch.setattr(db, "get_client", lambda: fake)
    assert db.claude_spend_this_month() == pytest.approx(0.103)
    (_, column, value), = fake.filters
    since, now = datetime.fromisoformat(value), datetime.now(timezone.utc)
    assert column == "created_at" and since.tzinfo is not None
    assert (since.year, since.month, since.day, since.hour) == (now.year, now.month, 1, 0)


def test_a_reservation_is_an_unsettled_worst_case_stamped_with_its_time(monkeypatch):
    fake = _Table()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    assert db.reserve_claude_spend(model="claude-opus-5-5", purpose="script", cost_usd=0.17) == 7
    row = fake.payload
    assert row["settled"] is False and row["cost_usd"] == 0.17
    assert (row["input_tokens"], row["output_tokens"]) == (0, 0)
    assert datetime.fromisoformat(row["created_at"]).tzinfo is not None


def test_settling_writes_the_real_cost(monkeypatch):
    fake = _Table()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    db.settle_claude_spend(7, input_tokens=10, output_tokens=20, cost_usd=0.0004)
    assert fake.op == "update" and fake.filters == [("eq", "id", 7)]
    assert fake.payload == {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.0004,
                            "settled": True}


def test_releasing_deletes_only_that_row(monkeypatch):
    fake = _Table()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    db.release_claude_spend(7)
    assert fake.op == "delete" and fake.filters == [("eq", "id", 7)]


# --- Claude adds no facts -------------------------------------------------------------------------

SOURCE = ("TODAY'S DATE: 2026-10-22 (Thursday), UTC.\n"
          "IDEA: ISRO's reusable rocket lands itself in a test - why it matters\n"
          "HOOK: India just test-fired a rocket that lands itself.\n"
          "ANGLE (the take to develop): Reusability could cut India's launch costs and open "
          "the market to startups.\n"
          + json.dumps({"title": "India's Rocket Just Landed Itself",
                        "script_body": "India just landed a rocket... on purpose. ISRO's RLV test "
                                       "vehicle glided down and touched the runway by itself in "
                                       "Chitradurga. Launch costs could fall 40 percent.",
                        "key_points": ["Rocket lands itself"]}))

# Claude's three real rewrites of this draft, 2026-10-22 (Opus medium, Opus low, Sonnet low).
REAL_REWRITES = [
    "India's got a rocket that lands itself... on a runway. In a test, ISRO's reusable launch "
    "vehicle prototype glided in and landed in Chitradurga, by itself. Catch: it's a landing "
    "test, not a space round-trip. [serious] Here's why it matters... reusing a rocket could "
    "make launches far cheaper than throwing one away. And cheaper rides could open space to "
    "Indian startups. [dry] Turns out the hard part... is coming back.",
    "India's space agency has a rocket... that lands like an airplane. ISRO's reusable launch "
    "vehicle prototype glided down and touched the runway in Chitradurga. By itself. No pilot. "
    "No panic. [pause] [serious] Here's why it matters: most rockets get thrown away after a "
    "single flight. Fly the hardware again, and launches could get cheaper... and cheaper rides "
    "are how Indian space startups get a seat. Turns out the future of rockets is... coming back.",
    "India's space agency dropped a rocket from the sky... and it parked itself. ISRO's RLV test "
    "vehicle glided down and touched a runway by itself in Chitradurga. No pilot. No steering "
    "wheel. Just physics and nerves. [pause] Here's the catch... landing is the easy part to "
    "cheer for. [serious] The real prize is reuse. Cheaper rides, more launches.",
]


@pytest.mark.parametrize("body", REAL_REWRITES)
def test_claudes_real_rewrites_add_no_facts(body):
    assert scriptwriter._added_facts({"script_body": body, "title": "India's Rocket Lands "
                                      "Itself", "key_points": ["Rocket lands itself"]},
                                     SOURCE) == []


@pytest.mark.parametrize("data, added", [
    ({"script_body": "ISRO's rocket landed. It cost 95 crore."}, "95"),
    ({"script_body": "Launch costs could fall forty percent, or sixty."}, "60"),
    ({"script_body": "Launch costs fell 40 percent.", "title": "3 Reasons It Matters"}, "3"),
    ({"script_body": "Fine.", "key_points": ["1,200 km glide"]}, "1200"),
    ({"script_body": "Fine.", "caption": "Since 2019 🚀"}, "2019"),
    ({"script_body": "The rocket, built by Tata, landed in Chitradurga."}, "Tata"),
    ({"script_body": "It landed. NASA was watching."}, "NASA"),
    ({"script_body": "It landed in Chitradurga — Somanath said so."}, "Somanath"),
])
def test_a_new_number_or_name_is_caught(data, added):
    assert added in scriptwriter._added_facts(data, SOURCE)


def test_the_prompts_instruction_numbers_are_not_facts():
    """The real prompt says '55-70 words' and '12-15 search terms'. Read as source text, those
    numbers would let an invented '55 people' through."""
    idea = {"id": 1, "title": "ISRO's rocket lands itself", "hook": "It landed.",
            "angle": "Reuse is cheaper.", "sources": ["https://example.com/isro-rlv"]}
    source = scriptwriter._idea_lines(scriptwriter._build_prompt(idea, "N"))
    assert "ISRO's rocket lands itself" in source and "https://example.com/isro-rlv" in source
    assert "55" in scriptwriter._added_facts({"script_body": "55 engineers cheered."}, source)


def test_names_derived_from_the_draft_are_not_new():
    body = "The Indian rocket glided home, and ISRO's engineers cheered."
    assert scriptwriter._added_facts({"script_body": body}, SOURCE) == []


# --- the scriptwriter -----------------------------------------------------------------------------

DRAFT = '{"script_body": "gemini draft about Chitradurga", "title": "t"}'
PROMPT = "IDEA: a rocket\nHOOK: it lands\n"


def _wire(monkeypatch, *, grounded=DRAFT, claude=None):
    """Stub the three writers; `claude` is a reply string or an exception to raise."""
    seen = {}

    def _grounded(prompt, **_k):
        if isinstance(grounded, Exception):
            raise grounded
        return grounded

    def _claude(prompt, **_k):
        seen["claude_prompt"] = prompt
        if isinstance(claude, Exception):
            raise claude
        return claude

    monkeypatch.delenv("ENABLE_CLAUDE_SCRIPT", raising=False)
    monkeypatch.setattr(scriptwriter.llm, "generate_grounded", _grounded)
    monkeypatch.setattr(scriptwriter.llm, "generate_claude", _claude)
    monkeypatch.setattr(scriptwriter.llm, "generate",
                        lambda *a, **k: '{"script_body": "ungrounded"}')
    return seen


def test_claude_writes_the_final_script_from_the_grounded_draft(monkeypatch):
    seen = _wire(monkeypatch, claude='{"script_body": "It landed in Chitradurga."}')
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "It landed in Chitradurga."
    assert data["writer"] == "claude" and data.get("claude_issue") is None
    sent = seen["claude_prompt"]
    assert sent.startswith(PROMPT)
    assert json.dumps(json.loads(DRAFT), ensure_ascii=False) in sent, "the draft is the fact base"


def test_a_claude_script_that_adds_a_fact_is_dropped_for_the_draft(monkeypatch):
    _wire(monkeypatch, claude='{"script_body": "It landed in Chitradurga after 12 tries."}')
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "gemini draft about Chitradurga"
    assert data["writer"] == "gemini-grounded"


def test_without_claude_the_grounded_draft_ships_and_says_why(monkeypatch):
    _wire(monkeypatch, claude=llm.ClaudeUnavailable("$4.00 budget spent", "budget"))
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "gemini draft about Chitradurga"
    assert data["writer"] == "gemini-grounded"
    assert data["claude_issue"] == {"kind": "budget", "reason": "$4.00 budget spent"}


def test_a_misconfigured_claude_is_reported(monkeypatch):
    _wire(monkeypatch, claude=llm.ClaudeMisconfigured("AuthenticationError: invalid x-api-key"))
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["writer"] == "gemini-grounded"
    assert data["claude_issue"]["kind"] == "misconfigured"


def test_a_transient_claude_error_is_not_reported(monkeypatch):
    _wire(monkeypatch, claude=RuntimeError("529 overloaded"))
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "gemini draft about Chitradurga"
    assert data.get("claude_issue") is None


def test_an_unusable_claude_reply_falls_back_to_the_grounded_draft(monkeypatch):
    _wire(monkeypatch, claude="Sorry, I can't help with that.")
    assert scriptwriter._generate_script_json(PROMPT)["script_body"] == "gemini draft about Chitradurga"


def test_no_grounded_draft_means_no_claude_call(monkeypatch):
    """Without the draft Claude has no fact base, and 'add no facts' cannot hold."""
    seen = _wire(monkeypatch, grounded=RuntimeError("grounding down"),
                 claude='{"script_body": "claude"}')
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "ungrounded" and data["writer"] == "gemini"
    assert "claude_prompt" not in seen


def test_claude_can_be_switched_off(monkeypatch):
    seen = _wire(monkeypatch, claude='{"script_body": "claude"}')
    monkeypatch.setenv("ENABLE_CLAUDE_SCRIPT", "false")
    data = scriptwriter._generate_script_json(PROMPT)
    assert data["script_body"] == "gemini draft about Chitradurga"
    assert "claude_prompt" not in seen and data.get("claude_issue") is None
