"""Suite-wide guards: unit tests never reach the LIVE database or a live model.

Both the local .env and every CI run hand the suite real Supabase credentials, because the one
live round trip (test_db_integration.py) needs them. So any test that reached src.db without
stubbing it read and WROTE production rows: make_on_demand's age-out ran against the live ideas
table on every run, and releasing leftover approvals would have turned a real tap back to
'pending' while a digest was waiting on it. `db.get_client` now raises everywhere except that
opt-in module; a test that needs a database stubs the db function, or get_client, itself.

Models likewise: the fact-check repair pass was unstubbed in `_wire_happy`, so one test made
real grounded Gemini and Groq calls on every run (and would on every CI push, which carries
GROQ_API_KEY). The Gemini and Groq client factories raise outside the tests that call a real
service on purpose: those are named `test_live_*` or marked `@pytest.mark.live`, and each is
already gated behind its own key or env var.
"""
import pytest

_LIVE_DB_MODULES = {"test_db_integration.py"}


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls a real service on purpose (gated by its key)")


@pytest.fixture(autouse=True)
def _no_live_database(request, monkeypatch):
    if request.node.path.name in _LIVE_DB_MODULES:
        return
    from src import db

    def _blocked():
        raise RuntimeError("a test tried to reach the live database; stub src.db for it")

    monkeypatch.setattr(db, "get_client", _blocked)


@pytest.fixture(autouse=True)
def _no_live_telegram(request, monkeypatch):
    """Unit tests never message the operator. On 2026-10-09 a publish test run with the local
    .env sent a real "post row could not be saved" alert to the operator's chat: best-effort
    alert paths call approval._api, and a test that does not stub it reaches Telegram. A test
    that mocks requests.post still exercises the real _api; only a real network call is refused."""
    if request.node.name.startswith("test_live") or request.node.get_closest_marker("live"):
        return
    from src import approval

    real_api, real_post = approval._api, approval.requests.post

    def _guarded(method, **params):
        if approval.requests.post is real_post:
            raise RuntimeError("a test tried to message Telegram; stub approval._api for it")
        return real_api(method, **params)

    monkeypatch.setattr(approval, "_api", _guarded)


@pytest.fixture(autouse=True)
def _no_live_youtube_preflight(request, monkeypatch):
    """The entry points refresh the YouTube token before any work (publish_youtube.preflight);
    a unit test of make_on_demand must not reach Google for it. Tests of the pre-flight itself
    are named test_preflight_*."""
    if request.node.name.startswith(("test_preflight", "test_live")):
        return
    from src import publish_youtube

    monkeypatch.setattr(publish_youtube, "preflight", lambda: None)

    # The read-back after an upload builds its own read-only client (design 9.9). Unstubbed, a
    # publish test would refresh the operator's real token against Google; the read-back fails
    # soft, so the guard costs a test nothing and tests that need it stub _reader_client.
    def _no_reader():
        raise RuntimeError("a test tried to reach YouTube; stub publish_youtube._reader_client")

    monkeypatch.setattr(publish_youtube, "_reader_client", _no_reader)


@pytest.fixture(autouse=True)
def _no_live_models(request, monkeypatch):
    if (request.node.name.startswith("test_live") or request.node.get_closest_marker("live")
            or request.node.path.name in _LIVE_DB_MODULES):
        return
    from src import llm

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("a test tried to call a live model; stub src.llm for it")

    real = llm._gemini_client
    _blocked.__wrapped__ = getattr(real, "__wrapped__", real)  # test_llm reaches the uncached one
    monkeypatch.setattr(llm, "_gemini_client", _blocked)
    monkeypatch.setattr(llm, "_groq_client", _blocked)
    # Claude is billed per call: with the operator's key in .env, one unstubbed test is real money.
    monkeypatch.setattr(llm, "_anthropic_client", _blocked)


@pytest.fixture(autouse=True)
def _no_live_demand(request, monkeypatch):
    """Ideation reads two public feeds for demand (src/demand.py, design 8.3). Unit tests never
    fetch them; tests/test_demand.py tests the readers on hand-built responses."""
    if request.node.path.name == "test_demand.py" or request.node.name.startswith("test_live"):
        return
    from src import demand

    monkeypatch.setattr(demand, "demand_lines", lambda: [])


@pytest.fixture(autouse=True)
def _before_the_tts_shutdown(monkeypatch):
    """The Developer API's TTS models shut down on 2026-11-17 (voice._DEV_TTS_SHUTDOWN), and the
    voice skips them from that day. Tests run as on 2026-11-12, so the daily test run does not
    turn red by the calendar alone; tests of the shutdown pass their own date."""
    from datetime import date

    from src import voice

    monkeypatch.setattr(voice, "_today", lambda: date(2026, 11, 12))
