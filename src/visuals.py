"""Module 5 — Visuals (stock B-roll).

Contract:
    what it does : finds + downloads CC0 vertical B-roll for a script's keywords.
    input        : script_body or keyword list; target duration; output dir.
    output       : list of local clip paths covering the narration length.
    depends on   : Pexels API (primary) -> Pixabay (backup) (rule 11); requests; src.config.

COPYRIGHT SAFETY (docs/08 §3): CC0 stock only — NEVER broadcaster/agency footage. Both
Pexels and Pixabay are commercial-use, no-attribution. Prefer maps/charts/data-viz for impact
stories (push that via keywords). Assembly cuts every 5-8s, so we gather several short clips
for variety, not one long one.

Clips are render artifacts: download to a temp dir, let assembly consume them, then delete
(rule 15). Filenames are content-hashed so a cron retry reuses the cache (rule 12).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import math
import os
import re
import subprocess

from functools import lru_cache

import requests

from src import config, llm

log = logging.getLogger(__name__)

_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
_PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"
_PIXABAY_VIDEO_SEARCH = "https://pixabay.com/api/videos/"
_TIMEOUT = 30          # seconds per HTTP call
_SLICE_SECONDS = 8.0   # planned cut length in assembly → coverage unit per clip
_PER_KEYWORD = 3       # candidates pulled per keyword

# Image-based visuals (photos / AI) → Ken Burns clips. Default source is "photos".
_IMAGE_CLIP_SECONDS = 7.0   # a touch longer than assembly's 6s slice
_MAX_IMG_CLIPS = 12         # cap API calls + ffmpeg conversions per reel

# Minimal stopword set for the heuristic keyword fallback (no NLTK dependency).
_STOPWORDS = frozenset(
    "the a an and or but of to in on for with as at by from is are was were be been it its "
    "this that these those they them their there here what which who how why when where will "
    "would can could should may might just not no so than then too very you your we our us i "
    "about into over after before more most some any all has have had do does did up out".split()
)


# --- keywords --------------------------------------------------------------------------

def _keywords_heuristic(script_body: str, n: int) -> list[str]:
    """Frequency-ranked content words — the deterministic fallback (rule 11)."""
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", script_body.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq, key=lambda w: (-freq[w], w))
    return ranked[:n]


def _keywords_via_llm(script_body: str, n: int) -> list[str]:
    prompt = (
        f"You pick stock-VIDEO search queries for a news Short. Give {n} CONCRETE, literal, "
        f"FILMABLE queries (1-3 words each) that stock sites (Pexels/Pixabay) actually have "
        f"footage for, matching this narration.\n"
        f"KEY RULE: stock sites do NOT have clips of specific people, brands, or named events — "
        f"so TRANSLATE those into filmable stand-ins:\n"
        f"  politician/government -> 'parliament building', 'indian flag', 'government office'\n"
        f"  court case/legal -> 'courtroom', 'judge gavel', 'law books'\n"
        f"  ISRO/space mission -> 'rocket launch', 'satellite orbit', 'mission control'\n"
        f"  economy/stocks -> 'stock market screen', 'indian currency', 'city skyline'\n"
        f"  AI/tech -> 'data center', 'circuit board', 'person using laptop'\n"
        f"Use tangible subjects: places, objects, people doing things, nature, city, crowds, maps. "
        f"AVOID proper nouns and abstract words entirely.\n\n"
        f"NARRATION:\n{script_body}\n\n"
        f'Return ONLY JSON: {{"keywords": ["...", "..."]}}'
    )
    import json

    raw = llm.generate(prompt, json=True, max_tokens=200)
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start : end + 1], strict=False)
    kws = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()]
    if not kws:
        raise ValueError("llm returned no keywords")
    return kws[:n]


def extract_keywords(script_body: str, n: int = 5) -> list[str]:
    """Pull 3-6 search keywords from the script (LLM, with a heuristic fallback)."""
    text = (script_body or "").strip()
    if not text:
        return []
    try:
        return _keywords_via_llm(text, n)
    except Exception as e:  # noqa: BLE001 — never let keyword extraction kill the reel
        log.warning("visuals: LLM keyword extraction failed (%s); using heuristic", e)
        return _keywords_heuristic(text, n)


# --- search providers ------------------------------------------------------------------

def _pick_portrait_file(video: dict) -> str | None:
    """Choose the best portrait mp4 file link (closest to 1080 wide), or None."""
    files = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and (f.get("height") or 0) > (f.get("width") or 0)
    ]
    if not files:
        return None
    best = min(files, key=lambda f: abs((f.get("width") or 0) - 1080))
    return best.get("link")


def _pexels_search(keyword: str) -> list[dict]:
    """Return [{url, duration}] portrait clips from Pexels for one keyword."""
    resp = requests.get(
        _PEXELS_VIDEO_SEARCH,
        headers={"Authorization": config.require("PEXELS_API_KEY")},
        params={"query": keyword, "orientation": "portrait", "per_page": _PER_KEYWORD,
                "size": "medium"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    out = []
    for v in resp.json().get("videos", []):
        link = _pick_portrait_file(v)
        if link:
            out.append({"url": link, "duration": float(v.get("duration") or _SLICE_SECONDS)})
    return out


def _pixabay_search(keyword: str) -> list[dict]:
    """Return [{url, duration}] clips from Pixabay (backup). No portrait filter available."""
    key = config.get("PIXABAY_API_KEY")
    if not key:
        return []
    resp = requests.get(
        _PIXABAY_VIDEO_SEARCH,
        params={"key": key, "q": keyword, "per_page": _PER_KEYWORD, "safesearch": "true"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    out = []
    for hit in resp.json().get("hits", []):
        files = hit.get("videos", {})
        chosen = files.get("large") or files.get("medium") or files.get("small")
        if chosen and chosen.get("url"):
            out.append({"url": chosen["url"], "duration": float(hit.get("duration") or _SLICE_SECONDS)})
    return out


def _gather_candidates(keywords: list[str]) -> list[dict]:
    """Interleave Pexels results across keywords (variety); fall back to Pixabay if empty."""
    per_kw: list[list[dict]] = []
    for kw in keywords:
        try:
            per_kw.append(_pexels_search(kw))
        except Exception as e:  # noqa: BLE001 — one bad keyword/search must not kill the batch
            log.warning("visuals: Pexels search failed for %r (%s)", kw, e)
            per_kw.append([])

    interleaved = _interleave(per_kw)
    if interleaved:
        return interleaved

    log.warning("visuals: Pexels returned nothing; trying Pixabay backup")
    for kw in keywords:
        try:
            per_kw_pb = _pixabay_search(kw)
        except Exception as e:  # noqa: BLE001
            log.warning("visuals: Pixabay search failed for %r (%s)", kw, e)
            per_kw_pb = []
        interleaved.extend(per_kw_pb)
    return interleaved


def _interleave(lists: list[list[dict]]) -> list[dict]:
    """Round-robin flatten so consecutive clips come from different keywords."""
    out: list[dict] = []
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out


# --- download --------------------------------------------------------------------------

def _clip_filename(url: str) -> str:
    return f"broll_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}.mp4"


def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=_TIMEOUT) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)


# --- image-based visuals (photos / AI) → Ken Burns clips -------------------------------

def _img_prompt(keyword: str) -> str:
    """Build the AI-image prompt. Style is tunable via IMAGE_STYLE for the channel's look."""
    style = config.get(
        "IMAGE_STYLE",
        "cinematic, photorealistic, dramatic lighting, shallow depth of field, "
        "high detail, professional documentary news b-roll, no text, no watermark",
    )
    return f"{keyword}, {style}, vertical 9:16 composition"


@lru_cache(maxsize=64)
def _pexels_photo_urls(keyword: str) -> tuple[str, ...]:
    """Portrait stock-photo URLs from Pexels for one keyword (cached). () on failure."""
    try:
        resp = requests.get(
            _PEXELS_PHOTO_SEARCH,
            headers={"Authorization": config.require("PEXELS_API_KEY")},
            params={"query": keyword, "orientation": "portrait", "per_page": 8, "size": "large"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return tuple(
            p["src"].get("large2x") or p["src"].get("portrait") or p["src"]["original"]
            for p in resp.json().get("photos", []) if p.get("src")
        )
    except Exception as e:  # noqa: BLE001
        log.warning("visuals: Pexels photo search failed for %r (%s)", keyword, e)
        return ()


def _cloudflare_image(prompt: str, dest: str) -> bool:
    """Generate an AI image via Cloudflare Workers AI (Flux). Needs CF_API_TOKEN + CF_ACCOUNT_ID."""
    token, acct = config.get("CF_API_TOKEN"), config.get("CF_ACCOUNT_ID")
    if not (token and acct):
        return False
    model = config.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": prompt[:2000]}, timeout=90,
        )
        r.raise_for_status()
        if "application/json" in r.headers.get("content-type", ""):
            b64 = (r.json().get("result") or {}).get("image")
            if not b64:
                return False
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64))
        else:
            with open(dest, "wb") as f:
                f.write(r.content)
        return os.path.getsize(dest) > 1000
    except Exception as e:  # noqa: BLE001
        log.warning("visuals: Cloudflare image gen failed (%s)", e)
        return False


def _fetch_image(keyword: str, dest: str, seed: int, source: str) -> bool:
    """Put one image at dest: AI (if source='ai' and CF set) else a Pexels photo. Bool = success."""
    if source == "ai" and _cloudflare_image(_img_prompt(keyword), dest):
        return True
    urls = _pexels_photo_urls(keyword)
    if not urls:
        return False
    try:
        _download(urls[seed % len(urls)], dest)
        return os.path.getsize(dest) > 1000
    except Exception as e:  # noqa: BLE001
        log.warning("visuals: photo download failed for %r (%s)", keyword, e)
        return False


def _image_to_kenburns_clip(image_path: str, dest: str, seconds: float) -> None:
    """Render a slow Ken Burns zoom over an image → 1080x1920 mp4 clip (FFmpeg)."""
    from src.assembly import _ffmpeg

    frames = int(seconds * 30)
    vf = (
        "scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
        f"zoompan=z='min(zoom+0.0010,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1920:fps=30,setsar=1"
    )
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-loop", "1", "-i", image_path, "-t", f"{seconds:.2f}",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", dest],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ken burns failed ({proc.returncode}): {proc.stderr[-400:]}")


def _fetch_image_broll(keywords: list[str], target_seconds: float, out_dir: str, source: str) -> list[str]:
    """Build Ken Burns clips from photos/AI images covering the narration. Raises if none made."""
    n = min(_MAX_IMG_CLIPS, math.ceil(target_seconds / 6.0) + 1)
    clips: list[str] = []
    for i in range(n):
        kw = keywords[i % len(keywords)]
        img = os.path.join(out_dir, f"img_{i:02d}.jpg")
        if not _fetch_image(kw, img, i, source):
            continue
        clip = os.path.join(out_dir, f"imgclip_{i:02d}.mp4")
        try:
            _image_to_kenburns_clip(img, clip, _IMAGE_CLIP_SECONDS)
            clips.append(clip)
        except Exception as e:  # noqa: BLE001
            log.warning("visuals: ken burns failed (%s); skipping", e)
    if not clips:
        raise RuntimeError(f"visuals: produced no image clips from source={source}")
    log.info("visuals: %d %s Ken Burns clips for target %.0fs", len(clips), source, target_seconds)
    return clips


def fetch_broll(keywords: list[str], target_seconds: float, out_dir: str) -> list[str]:
    """Return vertical clip paths covering target_seconds. VISUAL_SOURCE picks the strategy:
    'photos' (default, Pexels stock photos + Ken Burns), 'ai' (Cloudflare Flux + Ken Burns),
    or 'video' (Pexels/Pixabay stock video). Image sources fall back to stock video on failure.

    Raises RuntimeError if no clip could be obtained — the orchestrator skips that reel (rule 14).
    """
    if not keywords:
        raise ValueError("visuals.fetch_broll: no keywords provided.")
    os.makedirs(out_dir, exist_ok=True)

    source = str(config.get("VISUAL_SOURCE", "photos")).lower()
    if source in ("photos", "ai"):
        try:
            return _fetch_image_broll(keywords, target_seconds, out_dir, source)
        except Exception as e:  # noqa: BLE001 — fall back to stock video (rule 11)
            log.warning("visuals: %s source failed (%s); falling back to stock video", source, e)

    return _fetch_video_broll(keywords, target_seconds, out_dir)


def _fetch_video_broll(keywords: list[str], target_seconds: float, out_dir: str) -> list[str]:
    """Stock-video B-roll: Pexels then Pixabay (the original strategy)."""
    candidates = _gather_candidates(keywords)
    if not candidates:
        raise RuntimeError(f"visuals: no B-roll found on Pexels/Pixabay for {keywords}.")

    paths: list[str] = []
    covered = 0.0
    for c in candidates:
        if covered >= target_seconds and len(paths) >= 2:
            break
        dest = os.path.join(out_dir, _clip_filename(c["url"]))
        try:
            if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                _download(c["url"], dest)
        except Exception as e:  # noqa: BLE001 — skip a failed download, keep covering
            log.warning("visuals: download failed (%s); skipping", e)
            continue
        paths.append(dest)
        covered += min(c["duration"], _SLICE_SECONDS)

    if not paths:
        raise RuntimeError("visuals: found candidates but every download failed.")
    log.info("visuals: %d clips (~%.0fs coverage) for target %.0fs", len(paths), covered, target_seconds)
    return paths
