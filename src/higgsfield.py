"""Higgsfield: the only code that talks to it (design 6.6). Raw REST with `requests`, no SDK.

Contract:
    input  : HF_API_KEY (the console key, already "id:secret"); an endpoint id and its arguments.
    output : estimate -> USD; upload -> a public URL; submit / status -> Higgsfield's request dict;
             cancel -> whether Higgsfield confirmed it; download -> the local path.
    raises : HiggsfieldError, whose `kind` tells the caller what to do next (see the class).

The key goes only to api.higgsfield.ai. The presigned upload and the result download are sent
without it: it is not theirs to see, and an S3-style presigned PUT rejects a second credential.
Every message raised here passes `redact`, which removes the key, each half of it, and the query
string of any URL (a presigned URL's query is a credential too), and no raw exception is chained
behind it, so a logged traceback cannot print what the message left out.

Retries belong to the caller (src/ai_video.py), which owns the phase deadline (design 6.4): a
submit with no answer is repeated there with the same idempotency key and body, which Higgsfield
answers with the original job and no second charge.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re

import requests

from src import config

log = logging.getLogger(__name__)

BASE = "https://api.higgsfield.ai"
KLING = "kling-video/v2.5-turbo/standard/image-to-video"
TERMINAL = frozenset({"completed", "failed", "nsfw", "canceled"})

_CALL_TIMEOUT = 30    # seconds, every API call
_FILE_TIMEOUT = 180   # seconds, the upload PUT and the clip download
_REQUEST_ID = re.compile(r"[0-9A-Za-z-]{8,64}")
_QUERY = re.compile(r"(?<=\S)\?[^\s'\"<>()]+")
_VISIBLE_ASCII = re.compile(r"[\x21-\x7e]+")
_DETAIL_CHARS = 300


class HiggsfieldError(Exception):
    """A call that did not do what was asked. `kind` is one of:

    - funds: 403, the balance is empty. Never charged.
    - auth: 401; a 403 marked no-store (a disabled or expired key); no key set, or a key holding a
      space or control character. Never charged.
    - refused: any other 4xx (invalid, not found, a reused key with other arguments, model
      blocked). Never charged; repeating it unchanged will not help.
    - busy: 429, the account's queue is full. Never charged; `retry_after` holds the seconds to
      wait when Higgsfield says.
    - unavailable: a 5xx, a timeout, a dropped connection, or an answer without what was asked.
      A submit that ends here may have been accepted: repeat it with the same key and body.

    A failed upload or download is `unavailable` whatever its status: a storage host's 403 is
    not Higgsfield's balance."""

    def __init__(self, kind: str, message: str, *, status: int | None = None,
                 retry_after: float | None = None):
        super().__init__(redact(message))
        self.kind, self.status, self.retry_after = kind, status, retry_after


def _secrets() -> list[str]:
    key = (os.environ.get("HF_API_KEY") or "").strip()
    if not key:
        return []
    halves = [h for h in key.split(":", 1) if len(h) >= 4]
    return sorted({key, *halves}, key=len, reverse=True)


def redact(text: object) -> str:
    """`text` without the key, either half of it, or any URL's query string."""
    out = _QUERY.sub("?…", str(text))
    for secret in _secrets():
        out = out.replace(secret, "[redacted]")
    return out


def _key() -> str:
    key = (config.get("HF_API_KEY") or "").strip()
    if not key:
        raise HiggsfieldError("auth", "HF_API_KEY is not set")
    # A key with a space or control character inside is refused before a header is built:
    # requests would reject the header and quote it, escaped, where redact cannot find it.
    if not _VISIBLE_ASCII.fullmatch(key):
        raise HiggsfieldError("auth", "HF_API_KEY holds a space or control character; "
                                      "paste the console key again")
    return key


def _send(method: str, url: str, *, auth: bool, timeout: float, **kwargs) -> requests.Response:
    """The one place this module touches the network (the test suite's guard sits here).

    `auth` adds the key, and only for a URL on the API host; a file transfer never gets it."""
    headers = dict(kwargs.pop("headers", None) or {})
    if auth:
        if not url.startswith(BASE + "/"):
            raise HiggsfieldError("refused", f"the key is only sent to {BASE}, not {url}")
        headers["Authorization"] = f"Key {_key()}"
    try:
        return requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as e:
        raise HiggsfieldError("unavailable", f"{method} {url}: {type(e).__name__}: {e}") from None


def _detail(r: requests.Response) -> str:
    """The answer's error text, redacted and then cut: cut first, a key straddling the cut would
    lose its whole match and a prefix of its secret half would survive."""
    try:
        body = r.json()
    except ValueError:
        return redact(r.text or "")[:_DETAIL_CHARS]
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        detail = ": ".join(str(detail[k]) for k in ("code", "message") if detail.get(k)) or detail
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    return redact(detail)[:_DETAIL_CHARS]


def _retry_after(r: requests.Response) -> float | None:
    """Seconds from the Retry-After header, or from the queue-full body when the header is absent."""
    candidates = [r.headers.get("Retry-After")]
    try:
        body = r.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            candidates.append(detail.get("retry_after_seconds"))
    except ValueError:
        pass
    for value in candidates:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    return None


def _check(r: requests.Response, what: str, *, api: bool = True) -> requests.Response:
    code = r.status_code
    if code < 400:
        return r
    message = f"{what} -> HTTP {code}: {_detail(r)}"
    if not api:
        raise HiggsfieldError("unavailable", message, status=code)
    if code == 401:
        kind = "auth"
    elif code == 403:
        # A disabled or expired key is also a 403, marked no-store (api-reference_headers.md);
        # told "out of funds", the operator would top up a balance that is not the problem.
        no_store = "no-store" in (r.headers.get("Cache-Control") or "").lower()
        kind = "auth" if no_store else "funds"
    elif code == 429:
        raise HiggsfieldError("busy", message, status=code, retry_after=_retry_after(r))
    elif code >= 500:
        kind = "unavailable"
    else:
        kind = "refused"
    raise HiggsfieldError(kind, message, status=code)


def _api(method: str, path: str, what: str, *, body: dict | None = None,
         headers: dict | None = None) -> dict:
    r = _check(_send(method, f"{BASE}/{path}", auth=True, timeout=_CALL_TIMEOUT, json=body,
                     headers=headers), what)
    try:
        data = r.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise HiggsfieldError("unavailable", f"{what}: the answer was not a JSON object",
                              status=r.status_code)
    return data


def _request_id(request_id: str) -> str:
    if not (isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id)):
        raise HiggsfieldError("refused", f"not a request id: {request_id!r}")
    return request_id


_PER_SECOND = re.compile(r"(?i)\bper (?:video )?second\b")
_RATE = re.compile(r"(\d{3,4})p:\s*\$(\d+(?:\.\d+)?)")


def _per_second_price(text: str, args: dict) -> float:
    """A price from a rate description, which is what /estimate answered for Kling on 2026-11-13
    ("rates in USD per video second: 720p: $0.0315. Total price = selected rate x output
    duration"): the 720p rate, which is what Kling 2.5 Turbo Standard makes, else the highest
    listed, times the job's `duration`. NaN when the text holds no per-second rate."""
    if not _PER_SECOND.search(text):
        return math.nan
    rates = {res: float(usd) for res, usd in _RATE.findall(text)}
    if not rates:
        return math.nan
    try:
        seconds = float(args["duration"])
    except (KeyError, TypeError, ValueError):
        return math.nan
    return rates.get("720", max(rates.values())) * seconds


def estimate(endpoint: str, args: dict) -> float:
    """What one job with these arguments costs, in USD (free to ask). The answer is either a
    total (`usd`) or, for a model priced by the second, a rate description that is multiplied by
    the job's `duration`."""
    data = _api("POST", f"estimate/{endpoint}", "estimate", body=args)
    try:
        usd = float(data["usd"])
    except (KeyError, TypeError, ValueError):
        text = data.get("pricing_description")
        usd = _per_second_price(text, args) if isinstance(text, str) else math.nan
    if not math.isfinite(usd):
        raise HiggsfieldError("unavailable", "estimate: no price in the answer")
    return usd


def upload(path: str, content_type: str) -> str:
    """Put a local file where a job can read it; return its public URL."""
    with open(path, "rb") as f:
        data = _api("POST", "files/generate-upload-url", "upload",
                    body={"content_type": content_type})
        upload_url, public_url = data.get("upload_url"), data.get("public_url")
        if not (isinstance(upload_url, str) and isinstance(public_url, str)):
            raise HiggsfieldError("unavailable", "upload: no upload or public URL in the answer")
        headers = data.get("upload_headers") or {"Content-Type": content_type}
        _check(_send("PUT", upload_url, auth=False, timeout=_FILE_TIMEOUT, data=f,
                     headers=headers), "upload PUT", api=False)
    return public_url


def submit(endpoint: str, args: dict, key: str) -> dict:
    """Start one job; `key` is its idempotency key (a repeat with it returns the same job)."""
    data = _api("POST", endpoint, "submit", body=args, headers={"Idempotency-Key": key})
    if not data.get("request_id"):
        raise HiggsfieldError("unavailable", "submit: no request_id in the answer")
    return data


def status(request_id: str) -> dict:
    """The job's current state; once `completed`, `video.url` holds the clip (valid 7 days)."""
    data = _api("GET", f"requests/{_request_id(request_id)}/status", "status")
    if not isinstance(data.get("status"), str):
        raise HiggsfieldError("unavailable", "status: no status in the answer")
    return data


def cancel(request_id: str) -> bool:
    """Ask Higgsfield to drop a queued job. True only when it confirms (202); never raises.

    An unconfirmed cancel leaves the job counted at its quote (design 6.2 step 9): it may run."""
    try:
        r = _send("POST", f"{BASE}/requests/{_request_id(request_id)}/cancel", auth=True,
                  timeout=_CALL_TIMEOUT)
    except HiggsfieldError as e:
        log.info("higgsfield: cancel %s not sent: %s", redact(request_id), e)
        return False
    if r.status_code != 202:
        log.info("higgsfield: cancel %s not confirmed (HTTP %s)", request_id, r.status_code)
    return r.status_code == 202


def download(url: str, dest: str) -> str:
    """Fetch a finished clip to `dest`. A failure leaves no partial file behind."""
    r = _send("GET", url, auth=False, timeout=_FILE_TIMEOUT, stream=True)
    try:
        _check(r, "download", api=False)
        size = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
        if not size:
            raise HiggsfieldError("unavailable", f"download {url}: the file was empty")
    except requests.RequestException as e:
        _remove(dest)
        raise HiggsfieldError("unavailable", f"download {url}: {type(e).__name__}: {e}") from None
    except BaseException:
        _remove(dest)
        raise
    finally:
        r.close()
    return dest


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
