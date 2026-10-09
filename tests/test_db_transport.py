"""The Supabase HTTP client resends a request whose connection failed, and never risks a
duplicate insert doing it. Offline: a fake transport stands in for the network."""
from __future__ import annotations

import httpx
import pytest

from src import db


class _Flaky(httpx.BaseTransport):
    """Raises the queued errors in order, then answers 200."""

    def __init__(self, *errors: Exception):
        self.errors = list(errors)
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return httpx.Response(200, json=[])


def _client(inner: httpx.BaseTransport) -> httpx.Client:
    return httpx.Client(transport=db._RetryTransport(inner, delays=(0.0, 0.0)))


def test_a_dropped_connection_on_a_read_is_retried():
    """Run 36804231283: an HTTP/2 GOAWAY on the approval poll ended the whole job."""
    inner = _Flaky(httpx.RemoteProtocolError("ConnectionTerminated"))
    assert _client(inner).get("https://x.supabase.co/rest/v1/ideas").status_code == 200
    assert inner.calls == 2


def test_an_update_is_retried_too():
    inner = _Flaky(httpx.ReadError("reset"))
    assert _client(inner).patch("https://x.supabase.co/rest/v1/ideas", json={}).status_code == 200
    assert inner.calls == 2


def test_an_insert_is_not_resent_once_it_may_have_arrived():
    """A resent POST whose first copy reached the server would write a second post row."""
    inner = _Flaky(httpx.RemoteProtocolError("ConnectionTerminated"))
    with pytest.raises(httpx.RemoteProtocolError):
        _client(inner).post("https://x.supabase.co/rest/v1/posts", json={})
    assert inner.calls == 1


def test_an_insert_is_resent_when_the_connection_never_opened():
    inner = _Flaky(httpx.ConnectError("refused"))
    assert _client(inner).post("https://x.supabase.co/rest/v1/posts", json={}).status_code == 200
    assert inner.calls == 2


def test_retries_are_bounded():
    inner = _Flaky(*[httpx.ReadError("reset")] * 5)
    with pytest.raises(httpx.ReadError):
        _client(inner).get("https://x.supabase.co/rest/v1/ideas")
    assert inner.calls == 3  # the first try plus two retries


def test_the_supabase_client_uses_the_retrying_transport():
    client = db._http_client()
    assert isinstance(client._transport, db._RetryTransport)
