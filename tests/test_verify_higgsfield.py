"""tools/verify_higgsfield.py against a fake transport. The tool spends real money the one time it
runs (design 15, step 3), so its flow is tested here first: refuse without --yes-spend, cancel a
queued job at no cost, or wait for a started one and download it, and never print the key."""
from __future__ import annotations

import importlib.util
import json
import os

import pytest
from requests.structures import CaseInsensitiveDict

from src import higgsfield

_TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools",
                     "verify_higgsfield.py")
KEY = "abc123:def456"
RID = "0b6f2a4e-1c1d-4a3e-9a51-6f1d3b2c4e5f"


class _Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self._content = status, body, content
        self.headers = CaseInsensitiveDict()
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if isinstance(self._body, dict):
            return self._body
        raise ValueError("not json")

    def iter_content(self, chunk_size=1):
        yield self._content

    def close(self):
        pass


def _tool():
    spec = importlib.util.spec_from_file_location("verify_higgsfield", _TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(monkeypatch, tmp_path, cancel_status: int, states: list[dict]):
    monkeypatch.setenv("HF_API_KEY", KEY)
    calls = []

    def fake(method, url, **kwargs):
        calls.append((method, url))
        if url.endswith("/files/generate-upload-url"):
            return _Resp(200, {"upload_url": "https://s3.example/put?X-Amz-Signature=sig",
                               "public_url": "https://cdn.example/in.png"})
        if method == "PUT":
            return _Resp(200)
        if "/estimate/" in url:
            return _Resp(200, {"usd": 0.179})
        if url.endswith(higgsfield.KLING):
            return _Resp(200, {"request_id": RID, "status": "queued"})
        if url.endswith("/cancel"):
            return _Resp(cancel_status)
        if url.endswith("/status"):
            return _Resp(200, states.pop(0) if len(states) > 1 else states[0])
        return _Resp(200, content=b"mp4" * 1000)  # the clip download

    monkeypatch.setattr(higgsfield.requests, "request", fake)
    tool = _tool()
    monkeypatch.setattr(tool.time, "sleep", lambda s: None)
    out = tmp_path / "result.json"
    code = tool.main(["--yes-spend", "--out", str(out)])
    return code, json.loads(out.read_text(encoding="utf-8")), calls


def test_it_refuses_to_spend_without_yes_spend(monkeypatch, capsys):
    monkeypatch.setenv("HF_API_KEY", KEY)
    sent = []
    monkeypatch.setattr(higgsfield.requests, "request", lambda *a, **k: sent.append(a))
    assert _tool().main([]) == 2
    assert sent == [] and "--yes-spend" in capsys.readouterr().out


def test_a_queued_job_is_cancelled_at_no_cost(monkeypatch, tmp_path, capsys):
    code, result, calls = _run(monkeypatch, tmp_path, 202, [{"status": "canceled"}])
    assert code == 0
    assert result["same_request_id"] is True and result["quote_usd"] == 0.179
    (job,) = result["jobs"]
    assert (job["cancel_confirmed"], job["final_status"], job["charged"]) == (True, "canceled",
                                                                              "nothing")
    assert calls.count(("POST", f"{higgsfield.BASE}/{higgsfield.KLING}")) == 2  # two submits
    printed = capsys.readouterr().out
    assert KEY not in printed and "X-Amz-Signature" not in printed


def test_a_started_job_is_waited_for_and_downloaded(monkeypatch, tmp_path):
    states = [{"status": "in_progress"}, {"status": "in_progress"},
              {"status": "completed", "video": {"url": "https://cdn.example/v.mp4?sig=s"}}]
    code, result, _ = _run(monkeypatch, tmp_path, 400, states)
    assert code == 0
    (job,) = result["jobs"]
    assert (job["cancel_confirmed"], job["final_status"], job["charged"]) == (False, "completed",
                                                                              "one clip")
    assert job["clip_bytes"] == 3000 and "sig=s" not in job["clip_url"]


def test_a_refused_key_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_API_KEY", KEY)
    monkeypatch.setattr(higgsfield.requests, "request",
                        lambda method, url, **k: _Resp(401, {"detail": f"bad key {KEY}"}))
    out = tmp_path / "r.json"
    assert _tool().main(["--yes-spend", "--out", str(out)]) == 1
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["error"]["kind"] == "auth" and KEY not in json.dumps(result)


@pytest.fixture(autouse=True)
def _no_temp_litter(monkeypatch, tmp_path):
    """The tool's work directory goes under the test's tmp_path, not the system temp."""
    monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="": str(tmp_path / "work"))
    os.makedirs(tmp_path / "work", exist_ok=True)
