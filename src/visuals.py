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

import hashlib
import logging
import os
import re

import requests

from src import config, llm

log = logging.getLogger(__name__)

_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
_PIXABAY_VIDEO_SEARCH = "https://pixabay.com/api/videos/"
_TIMEOUT = 30          # seconds per HTTP call
_SLICE_SECONDS = 8.0   # planned cut length in assembly → coverage unit per clip
_PER_KEYWORD = 3       # candidates pulled per keyword

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
        f"Extract {n} short visual search phrases (1-3 words each) for finding stock B-roll "
        f"that matches this narration. Prefer concrete, filmable subjects (places, objects, "
        f"actions, maps/charts). Avoid abstract words.\n\n"
        f"NARRATION:\n{script_body}\n\n"
        f'Return ONLY JSON: {{"keywords": ["...", "..."]}}'
    )
    import json

    raw = llm.generate(prompt, json=True, max_tokens=200)
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start : end + 1])
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


def fetch_broll(keywords: list[str], target_seconds: float, out_dir: str) -> list[str]:
    """Download enough CC0 vertical clips to cover target_seconds. Pexels then Pixabay.

    Returns local clip paths (≥1). Raises RuntimeError if no clip could be obtained — the
    orchestrator skips that reel (rule 14). Re-uses already-cached files (rule 12).
    """
    if not keywords:
        raise ValueError("visuals.fetch_broll: no keywords provided.")
    os.makedirs(out_dir, exist_ok=True)

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
