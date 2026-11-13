"""One live check of Higgsfield before the AI-video format goes live (design 15, step 3).

Run: python tools/verify_higgsfield.py --yes-spend [--image PATH] [--out result.json]

Spends at most one Kling 2.5 Turbo clip (about $0.18), on one job, to answer what the build relies
on but the spikes did not test:

1. Two submits with one idempotency key: does the second return the same request_id? Charges are
   per request and Higgsfield has no balance endpoint, so one request_id is the evidence of one
   charge. (Should the ids differ, the tool cancels both and says so.)
2. A cancel sent while the job is still queued: does Higgsfield confirm it (202), and does the
   status then read `canceled`, which is not charged?

If the job has already started, the cancel is refused; the tool then waits for the clip, downloads
it without the key (the path a reel uses) and reports its size. That clip is the $0.18.

Needs HF_API_KEY in the local .env. Prints the key nowhere and URLs only redacted. The result goes
into docs/04 (Higgsfield) by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import time
import uuid

# "python tools/verify_higgsfield.py" puts tools/ on sys.path, not the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # the local .env on the dev machine
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import higgsfield  # noqa: E402 — must follow the sys.path fix above

NEGATIVE = ("text, subtitles, captions, watermark, logo, distortion, warping, flicker, "
            "fast motion, scene change, people")
MOTION = ("The sun glows softly while the sky's colors drift slowly. The horizon keeps its exact "
          "shape and colors. The camera stays static.")
WAIT_SECONDS = 600


def _draw_still(path: str) -> str:
    """A plain 768x1344 sky with a sun: something Kling can move gently, free to make."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (768, 1344))
    draw = ImageDraw.Draw(img)
    for y in range(1344):
        t = y / 1343
        draw.line([(0, y), (767, y)],
                  fill=(int(40 + 180 * t), int(90 + 100 * t), int(200 - 80 * t)))
    draw.ellipse([284, 420, 484, 620], fill=(255, 214, 120))
    draw.rectangle([0, 1000, 767, 1343], fill=(40, 70, 60))
    img.save(path, "PNG")
    return path


def _wait(request_id: str) -> dict:
    """Poll until the job is terminal, as a reel does: 2 s, then x1.5 up to 10 s, with jitter."""
    started, delay = time.monotonic(), 2.0
    while True:
        try:
            state = higgsfield.status(request_id)
            if state.get("status") in higgsfield.TERMINAL:
                return state
        except higgsfield.HiggsfieldError as e:
            print(f"  status read failed, retrying: {e}")
        if time.monotonic() - started > WAIT_SECONDS:
            return {"status": "still running after the wait"}
        time.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 1.5, 10.0)


def _settle(request_id: str, work: str) -> dict:
    """Cancel the job at once; if it already started, wait for it and download the clip."""
    out = {"request_id": request_id, "cancel_confirmed": higgsfield.cancel(request_id)}
    state = higgsfield.status(request_id)
    out["status_after_cancel"] = state.get("status")
    if state.get("status") not in higgsfield.TERMINAL:
        print(f"  {request_id} had started; waiting for it (up to {WAIT_SECONDS} s)")
        state = _wait(request_id)
    out["final_status"] = state.get("status")
    url = (state.get("video") or {}).get("url")
    if state.get("status") == "completed" and url:
        dest = higgsfield.download(url, os.path.join(work, f"{request_id}.mp4"))
        out.update(clip_bytes=os.path.getsize(dest), clip_url=higgsfield.redact(url))
    out["charged"] = {"completed": "one clip", "canceled": "nothing", "failed": "nothing",
                      "nsfw": "nothing"}.get(state.get("status"), "unknown (still running)")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes-spend", action="store_true",
                        help="confirm spending up to one Kling clip (about $0.18)")
    parser.add_argument("--image", help="a 9:16 PNG or JPEG to use instead of the drawn still")
    parser.add_argument("--out", help="also write the result as JSON to this path")
    args = parser.parse_args(argv)
    if not args.yes_spend:
        print("This spends up to one Kling clip (about $0.18). Run it again with --yes-spend.")
        return 2
    if not (os.environ.get("HF_API_KEY") or "").strip():
        print("HF_API_KEY is not set (local .env).")
        return 2

    work = tempfile.mkdtemp(prefix="hf_verify_")
    still = args.image or _draw_still(os.path.join(work, "still.png"))
    content_type = "image/png" if still.lower().endswith(".png") else "image/jpeg"
    result: dict = {"endpoint": higgsfield.KLING, "work_dir": work}
    try:
        body = {"prompt": MOTION, "image_url": higgsfield.upload(still, content_type),
                "duration": 5, "negative_prompt": NEGATIVE}
        result["quote_usd"] = higgsfield.estimate(higgsfield.KLING, body)
        print(f"Quote for one 5 s clip: ${result['quote_usd']:.3f}")

        key = str(uuid.uuid4())
        first = higgsfield.submit(higgsfield.KLING, body, key)
        second = higgsfield.submit(higgsfield.KLING, body, key)
        ids = list(dict.fromkeys([first["request_id"], second["request_id"]]))
        result.update(first_status=first.get("status"), same_request_id=len(ids) == 1)
        print(f"Same request_id for two submits with one key: {result['same_request_id']}")
        result["jobs"] = [_settle(rid, work) for rid in ids]
    except higgsfield.HiggsfieldError as e:
        result["error"] = {"kind": e.kind, "status": e.status, "message": str(e)}

    print(json.dumps(result, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    jobs = result.get("jobs") or []
    ok = (result.get("same_request_id") and jobs
          and jobs[0].get("final_status") in ("canceled", "completed"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
