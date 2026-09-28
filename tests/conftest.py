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
