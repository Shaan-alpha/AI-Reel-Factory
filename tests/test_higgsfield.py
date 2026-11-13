"""The Higgsfield client (design 6.6): every call through one transport, the key only to the API
host, every message redacted, and each HTTP answer sorted into what the caller does next.

No test here reaches the network: `requests.request` is replaced by a fake that answers from a
per-test handler and records what was sent."""
from __future__ import annotations

import io
import json

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from src import higgsfield

KEY = "abc123:def456"
SIGNED = "https://bucket.s3.example.com/in/x.png?X-Amz-Signature=deadbeef&X-Amz-Credential=abc123"


class _Resp:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code = status
        self._body = body
        self.headers = CaseInsensitiveDict(headers or {})
        self._content = content
        self.text = body if isinstance(body, str) else json.dumps(body) if body is not None else ""

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        raise ValueError("not json")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


class _Transport:
    """Stands in for requests.request: `handler(method, url, kwargs)` returns a _Resp or raises."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, method, url, **kwargs):
        sent = dict(kwargs)
        data = sent.get("data")
        if hasattr(data, "read"):
            sent["data"] = data.read()
        self.calls.append((method, url, sent))
        return self.handler(method, url, sent)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", KEY)


def _use(monkeypatch, handler) -> _Transport:
    fake = _Transport(handler)
    monkeypatch.setattr(higgsfield.requests, "request", fake)
    return fake


def _auth_header(kwargs) -> str | None:
    headers = CaseInsensitiveDict(kwargs.get("headers") or {})
    return headers.get("Authorization")


def test_estimate_reads_the_quote(monkeypatch):
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, {"usd": 0.179}))
    args = {"prompt": "a slow pan", "image_url": "https://cdn.example/in.png", "duration": 5}
    assert higgsfield.estimate(higgsfield.KLING, args) == pytest.approx(0.179)
    method, url, sent = fake.calls[0]
    assert (method, url) == ("POST", f"{higgsfield.BASE}/estimate/{higgsfield.KLING}")
    assert sent["json"] == args
    assert sent["timeout"] == 30


@pytest.mark.parametrize("body", [{"usd": "free"}, {"usd": float("nan")}, {}, ["usd"]])
def test_a_quote_without_a_price_is_unavailable(monkeypatch, body):
    _use(monkeypatch, lambda m, u, k: _Resp(200, body))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.estimate(higgsfield.KLING, {})
    assert err.value.kind == "unavailable"


def test_upload_puts_the_file_and_returns_the_public_url(monkeypatch, tmp_path):
    still = tmp_path / "still.png"
    still.write_bytes(b"png-bytes")
    upload_headers = {"Content-Type": "image/png", "x-amz-tagging": "retention=temporary"}

    def handler(method, url, kwargs):
        if url.endswith("/files/generate-upload-url"):
            return _Resp(200, {"upload_url": SIGNED, "public_url": "https://cdn.example/in.png",
                               "upload_headers": upload_headers})
        return _Resp(200)

    fake = _use(monkeypatch, handler)
    assert higgsfield.upload(str(still), "image/png") == "https://cdn.example/in.png"
    (m1, u1, k1), (m2, u2, k2) = fake.calls
    assert (m1, k1["json"]) == ("POST", {"content_type": "image/png"})
    assert (m2, u2) == ("PUT", SIGNED)
    assert dict(k2["headers"]) == upload_headers
    assert k2["data"] == b"png-bytes" and k2["timeout"] == 180


def test_upload_without_headers_sends_the_content_type(monkeypatch, tmp_path):
    still = tmp_path / "still.jpg"
    still.write_bytes(b"jpg")

    def handler(method, url, kwargs):
        if method == "POST":
            return _Resp(200, {"upload_url": SIGNED, "public_url": "https://cdn.example/in.jpg"})
        return _Resp(200)

    fake = _use(monkeypatch, handler)
    higgsfield.upload(str(still), "image/jpeg")
    assert dict(fake.calls[1][2]["headers"]) == {"Content-Type": "image/jpeg"}


def test_submit_sends_the_idempotency_key(monkeypatch):
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, {"request_id": "1f0c", "status": "queued"}))
    args = {"prompt": "slow push in", "image_url": "https://cdn.example/in.png", "duration": 5}
    first = higgsfield.submit(higgsfield.KLING, args, "key-1")
    again = higgsfield.submit(higgsfield.KLING, args, "key-1")
    assert first == again == {"request_id": "1f0c", "status": "queued"}
    for method, url, sent in fake.calls:
        assert (method, url) == ("POST", f"{higgsfield.BASE}/{higgsfield.KLING}")
        assert CaseInsensitiveDict(sent["headers"])["Idempotency-Key"] == "key-1"
        assert sent["json"] == args


def test_status_and_cancel(monkeypatch):
    rid = "0b6f2a4e-1c1d-4a3e-9a51-6f1d3b2c4e5f"
    done = {"status": "completed", "request_id": rid, "video": {"url": "https://cdn.example/v.mp4"}}
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, done))
    assert higgsfield.status(rid) == done
    assert fake.calls[0][:2] == ("GET", f"{higgsfield.BASE}/requests/{rid}/status")

    for answer, confirmed in [(_Resp(202), True), (_Resp(400, {"detail": "started"}), False),
                              (_Resp(404, {"detail": "no"}), False), (_Resp(500), False)]:
        fake = _use(monkeypatch, lambda m, u, k, a=answer: a)
        assert higgsfield.cancel(rid) is confirmed
        assert fake.calls[0][:2] == ("POST", f"{higgsfield.BASE}/requests/{rid}/cancel")

    def times_out(method, url, kwargs):
        raise requests.Timeout("read timed out")

    _use(monkeypatch, times_out)
    assert higgsfield.cancel(rid) is False


def test_a_request_id_that_is_not_an_id_is_never_sent(monkeypatch):
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, {"status": "queued"}))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.status("../files/generate-upload-url")
    assert err.value.kind == "refused"
    assert higgsfield.cancel("../x") is False
    assert fake.calls == []


@pytest.mark.parametrize("status, headers, body, kind, retry_after", [
    (403, {}, {"detail": "Insufficient balance"}, "funds", None),
    (401, {}, {"detail": "Invalid credentials"}, "auth", None),
    (400, {}, {"detail": "bad image"}, "refused", None),
    (404, {}, {"detail": "not found"}, "refused", None),
    (409, {}, {"detail": "still running"}, "refused", None),
    (422, {}, {"detail": [{"loc": ["body", "duration"], "msg": "bad"}]}, "refused", None),
    (423, {}, {"detail": "model blocked"}, "refused", None),
    (429, {"Retry-After": "7"}, {"detail": {"code": "account_queue_full"}}, "busy", 7.0),
    (429, {}, {"detail": {"code": "account_queue_full", "retry_after_seconds": 30}}, "busy", 30.0),
    (429, {}, {"detail": "slow down"}, "busy", None),
    (500, {}, "Internal Server Error", "unavailable", None),
    (503, {}, {"detail": {"code": "admission_control_unavailable"}}, "unavailable", None),
])
def test_errors_are_classified(monkeypatch, status, headers, body, kind, retry_after):
    _use(monkeypatch, lambda m, u, k: _Resp(status, body, headers))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.submit(higgsfield.KLING, {"prompt": "p"}, "key-1")
    assert (err.value.kind, err.value.status, err.value.retry_after) == (kind, status, retry_after)


@pytest.mark.parametrize("failure", [requests.Timeout("read timed out"),
                                     requests.ConnectionError("connection reset")])
def test_no_answer_is_unavailable(monkeypatch, failure):
    def handler(method, url, kwargs):
        raise failure

    _use(monkeypatch, handler)
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.submit(higgsfield.KLING, {"prompt": "p"}, "key-1")
    assert err.value.kind == "unavailable" and err.value.status is None


@pytest.mark.parametrize("body", [{"status": "queued"}, "<html>gateway</html>"])
def test_a_submit_answered_without_a_request_id_is_unavailable(monkeypatch, body):
    """A 2xx without the id may still have created the job: the caller repeats it with the same
    key, which returns the original (design 6.2 step 7.4)."""
    _use(monkeypatch, lambda m, u, k: _Resp(200, body))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.submit(higgsfield.KLING, {"prompt": "p"}, "key-1")
    assert err.value.kind == "unavailable"


def test_download_writes_the_file(monkeypatch, tmp_path):
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, content=b"mp4-bytes" * 100))
    dest = tmp_path / "clip.mp4"
    assert higgsfield.download("https://cdn.example/v.mp4", str(dest)) == str(dest)
    assert dest.read_bytes() == b"mp4-bytes" * 100
    assert fake.calls[0][2]["stream"] is True and fake.calls[0][2]["timeout"] == 180


@pytest.mark.parametrize("answer", [_Resp(403), _Resp(200, content=b"")])
def test_a_failed_download_leaves_no_file(monkeypatch, tmp_path, answer):
    _use(monkeypatch, lambda m, u, k: answer)
    dest = tmp_path / "clip.mp4"
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.download("https://cdn.example/v.mp4", str(dest))
    assert err.value.kind == "unavailable"  # a storage 403 is not Higgsfield's balance
    assert not dest.exists()


def test_the_key_goes_only_to_the_api_host(monkeypatch, tmp_path):
    still = tmp_path / "still.png"
    still.write_bytes(b"png")

    def handler(method, url, kwargs):
        if url.endswith("/files/generate-upload-url"):
            return _Resp(200, {"upload_url": SIGNED, "public_url": "https://cdn.example/in.png"})
        if url.endswith("/status"):
            return _Resp(200, {"status": "completed", "video": {"url": "https://cdn.example/v.mp4"}})
        return _Resp(200, content=b"bytes")

    fake = _use(monkeypatch, handler)
    higgsfield.upload(str(still), "image/png")
    higgsfield.status("0b6f2a4e-1c1d-4a3e-9a51-6f1d3b2c4e5f")
    higgsfield.download("https://cdn.example/v.mp4", str(tmp_path / "v.mp4"))
    for method, url, sent in fake.calls:
        expected = f"Key {KEY}" if url.startswith(higgsfield.BASE + "/") else None
        assert _auth_header(sent) == expected, (method, url)

    with pytest.raises(higgsfield.HiggsfieldError):
        higgsfield._send("GET", "https://api.higgsfield.ai.evil.example/x", auth=True, timeout=1)


def test_no_message_carries_the_key_or_a_query_string(monkeypatch, tmp_path):
    still = tmp_path / "still.png"
    still.write_bytes(b"png")
    forbidden = (KEY, "abc123", "def456", "X-Amz-Signature", "deadbeef")
    caught = []

    # 1. An error body that echoes the credential header.
    _use(monkeypatch, lambda m, u, k: _Resp(401, {"detail": f"Invalid credentials: Key {KEY}"}))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.estimate(higgsfield.KLING, {})
    caught.append(err.value)

    # 2. A requests exception that quotes the signed upload URL.
    def put_fails(method, url, kwargs):
        if method == "POST":
            return _Resp(200, {"upload_url": SIGNED, "public_url": "https://cdn.example/in.png"})
        raise requests.ConnectionError(
            "HTTPSConnectionPool(host='bucket.s3.example.com', port=443): Max retries exceeded "
            "with url: /in/x.png?X-Amz-Signature=deadbeef&X-Amz-Credential=abc123")

    _use(monkeypatch, put_fails)
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.upload(str(still), "image/png")
    caught.append(err.value)

    # 3. A failed download of a signed result URL.
    _use(monkeypatch, lambda m, u, k: _Resp(500, "boom"))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.download(SIGNED, str(tmp_path / "v.mp4"))
    caught.append(err.value)

    for e in caught:
        for text in (str(e), repr(e), " ".join(map(str, e.args))):
            assert not any(f in text for f in forbidden), text
        # No unredacted exception chained behind it, where a logged traceback would print it.
        assert e.__cause__ is None and (e.__context__ is None or e.__suppress_context__)

    assert higgsfield.redact(f"Key {KEY} at {SIGNED}") == "Key [redacted] at " \
        "https://bucket.s3.example.com/in/x.png?…"


def test_no_key_is_auth(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    fake = _use(monkeypatch, lambda m, u, k: _Resp(200, {"usd": 0.179}))
    with pytest.raises(higgsfield.HiggsfieldError) as err:
        higgsfield.estimate(higgsfield.KLING, {})
    assert err.value.kind == "auth"
    assert fake.calls == []
    assert higgsfield.cancel("0b6f2a4e-1c1d-4a3e-9a51-6f1d3b2c4e5f") is False


def test_the_upload_reads_the_file_it_was_given(monkeypatch):
    """A missing still is the caller's bug, not an outage to retry: it raises before anything is
    asked of Higgsfield."""
    def handler(method, url, kwargs):
        return _Resp(200, {"upload_url": SIGNED, "public_url": "https://cdn.example/in.png"})

    fake = _use(monkeypatch, handler)
    with pytest.raises(OSError):
        higgsfield.upload("does/not/exist.png", "image/png")
    assert fake.calls == []


def test_byte_streams_are_accepted_as_upload_data(monkeypatch):
    """`_send` hands the open file to requests unchanged (streamed, not read into memory)."""
    seen = {}

    def fake_request(method, url, **kwargs):
        seen["data"] = kwargs.get("data")
        return _Resp(200)

    monkeypatch.setattr(higgsfield.requests, "request", fake_request)
    stream = io.BytesIO(b"abc")
    higgsfield._send("PUT", SIGNED, auth=False, timeout=1, data=stream)
    assert seen["data"] is stream
