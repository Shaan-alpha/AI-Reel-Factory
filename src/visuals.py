"""Module 5 — Visuals (stock B-roll).

Contract:
    what it does : finds + downloads CC0 vertical B-roll for a script's keywords.
    input        : script_body or keyword list; target duration; output dir.
    output       : list of local clip paths covering the narration length.
    depends on   : Pexels API (primary) -> Pixabay (backup) (rule 11); requests; src.config.

COPYRIGHT SAFETY (docs/08 §3): CC0 stock only — NEVER broadcaster/agency footage. Both
Pexels and Pixabay are commercial-use, no-attribution. Prefer maps/charts/data-viz for impact
stories (push that via keywords). Assembly cuts every `CLIP_SECONDS` (3.5s by default), so we
gather several short clips for variety, not one long one — and ask `assembly.slice_count()` how
many rather than guessing, so image B-roll covers every cut instead of looping.

Clips are render artifacts: download to a temp dir, let assembly consume them, then delete
(rule 15). Filenames are content-hashed so a cron retry reuses the cache (rule 12).
"""
from __future__ import annotations

import base64
import hashlib
import logging
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
_IMAGE_CLIP_SECONDS = 7.0   # comfortably longer than assembly's 3.5s slice (was documented as
                            # "assembly's 6s slice" — that stale 6.0 was the repeat bug's origin)
_MAX_IMG_CLIPS = 12         # cap API calls + ffmpeg conversions per reel
_MAX_VIDEO_CLIPS = 12       # same cap for the stock-video path (bounds downloads per reel)

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
        f"You are a stock-footage researcher picking B-roll search queries for a news Short. "
        f"Give exactly {n} CONCRETE, literal, FILMABLE queries (1-3 words each) that stock sites "
        f"(Pexels/Pixabay) actually have footage for, matching this narration. Order them to follow "
        f"the story beats so the visuals track what's being said.\n"
        f"KEY RULE: stock sites do NOT have clips of specific people, brands, or named events — "
        f"so TRANSLATE every proper noun into a filmable stand-in:\n"
        f"  politician/government -> 'parliament building', 'indian flag', 'government office'\n"
        f"  court case/legal -> 'courtroom', 'judge gavel', 'law books'\n"
        f"  ISRO/space mission -> 'rocket launch', 'satellite orbit', 'mission control'\n"
        f"  economy/stocks -> 'stock market screen', 'indian currency', 'city skyline'\n"
        f"  AI/tech -> 'data center', 'circuit board', 'person using laptop'\n"
        f"  oil/energy -> 'oil refinery', 'oil pump jack', 'cargo ship'\n"
        f"  defense/military -> 'military jet', 'naval warship', 'radar screen'\n"
        f"  infrastructure -> 'bullet train', 'highway traffic', 'construction crane'\n"
        f"  crypto/finance -> 'bitcoin coin', 'gold bars', 'digital vault'\n"
        f"  sport -> 'football stadium', 'soccer match', 'cheering crowd'\n"
        f"Prefer visually striking, high-motion subjects (they hold attention): places, objects, "
        f"people doing things, nature, cities, crowds, maps. AVOID people's names, brands, logos "
        f"and abstract words (policy, economy, impact) — only things a camera can film.\n"
        f"PLACES ARE THE EXCEPTION: when the story names a country, city or landmark, keep it in "
        f"the query ('Mumbai skyline', 'the White House', 'Nepal mountain village') and never swap "
        f"in a different one. A White House story was illustrated with the US Capitol, and "
        f"generic queries put American skylines on Indian stories.\n\n"
        f"NARRATION:\n{script_body}\n\n"
        f'Output ONE valid JSON object and nothing else, no markdown or fences: '
        f'{{"keywords": ["query one", "query two"]}}'
    )
    # prefer_groq: no web needed → reserve Gemini's free RPD for grounded research (rule 13).
    # 512, not 200: Groq's gpt-oss bills its reasoning trace against this budget (39-118 tokens
    # measured) and at 200 an occasional completion came back EMPTY, which json_object mode
    # rejects as `400 json_validate_failed` (run 34954327606).
    raw = llm.generate(prompt, json=True, max_tokens=512, prefer_groq=True)
    data = llm.parse_json_object(raw)
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

# docs/08: "AI images stay abstract/symbolic ... Never fake photoreal footage of real, named
# people or specific real events presented as real." The old default asked for "photorealistic
# ... documentary news b-roll", i.e. exactly the realistic look that rule rules out. Cinematic,
# but plainly an illustration (2026-09-27). IMAGE_STYLE still overrides it.
_DEFAULT_IMAGE_STYLE = (
    "cinematic editorial illustration, symbolic and stylized, painterly digital art, dramatic "
    "lighting, rich color, depth, no text, no watermark, no logos, no recognizable real people"
)
# One per shot, cycled: a keyword used two or three times in a reel used to get the identical
# prompt each time, so its shots came out near-identical.
_COMPOSITIONS = ("wide establishing shot", "close-up detail", "medium shot", "low angle",
                 "overhead view", "silhouette against the light")


def _img_prompt(keyword: str, index: int = 0, setting: str | None = None) -> str:
    """Build the AI-image prompt. Style is tunable via IMAGE_STYLE for the channel's look.

    `setting` places the scene: an Indian bank-strike story came out with dollar bills and "$"
    coins because the narration never said "India" (local render, 2026-09-28)."""
    style = config.get("IMAGE_STYLE", _DEFAULT_IMAGE_STYLE)
    framing = _COMPOSITIONS[index % len(_COMPOSITIONS)]
    place = f", set in {setting}" + (", Indian rupee currency" if setting == "India" else "") \
        if setting else ""
    return f"{keyword}{place}, {framing}, {style}, vertical 9:16 composition"


def _image_seed(variant: str, index: int) -> int:
    """Deterministic per reel and shot: a re-render draws the same pictures (rule 12) instead of
    spending neurons on new ones, and two reels never share a seed."""
    return int(hashlib.sha1(f"{variant}:{index}".encode("utf-8")).hexdigest()[:8], 16) % 2**31


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


# FLUX.2 [klein] 4B (2026-09-27): a native portrait size and a seed, where flux-1-schnell made a
# square that assembly cropped. About 103 neurons at 768x1344 (26.05 per output 512 tile) against
# 173 measured for schnell, so a reel's 12 images fit the free 10,000/day about 8 times over.
_KLEIN = "@cf/black-forest-labs/flux-2-klein-4b"
_SCHNELL = "@cf/black-forest-labs/flux-1-schnell"


def _cloudflare_image(prompt: str, dest: str, seed: int | None = None) -> bool:
    """Generate an AI image via Cloudflare Workers AI. Needs CF_API_TOKEN + CF_ACCOUNT_ID.

    CF_IMAGE_MODEL (default klein-4b) first; flux-1-schnell is tried if it fails (rule 11)."""
    token, acct = config.get("CF_API_TOKEN"), config.get("CF_ACCOUNT_ID")
    if not (token and acct):
        return False
    first = config.get("CF_IMAGE_MODEL", _KLEIN)
    for model in dict.fromkeys([first, _SCHNELL]):
        if _cloudflare_run(model, prompt, dest, token, acct, seed):
            return True
    return False


def _cloudflare_run(model: str, prompt: str, dest: str, token: str, acct: str,
                    seed: int | None) -> bool:
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"
    try:
        if "flux-2" in model:  # FLUX.2 takes multipart form data, even for a prompt alone
            fields = {"prompt": prompt[:2000], "width": "768", "height": "1344"}
            if seed is not None:
                fields["seed"] = str(seed)
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                              files={k: (None, v) for k, v in fields.items()}, timeout=90)
        else:
            body = {"prompt": prompt[:2000]}
            if seed is not None:
                body["seed"] = seed
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                              json=body, timeout=90)
        if r.status_code >= 400:
            # The body carries the reason (for example 3030, an NSFW false positive on a benign
            # prompt); raise_for_status alone threw it away, so two 400s in September could not
            # be diagnosed.
            log.warning("visuals: Cloudflare image gen HTTP %d for %r: %s",
                        r.status_code, prompt[:80], r.text[:300])
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
        log.warning("visuals: Cloudflare image gen failed on %s (%s)", model, e)
        return False


def _fetch_image(keyword: str, dest: str, seed: int, source: str,
                 variant: str = "", setting: str | None = None) -> bool:
    """Put one image at dest: AI (if source='ai' and CF set) else a Pexels photo. Bool = success.

    `variant` distinguishes one reel from another. `_pexels_photo_urls` is lru_cached for the
    life of the process and this used to index it by cut number alone, so two reels in the
    same batch that shared a keyword ("indian flag") drew the IDENTICAL photo at the identical
    cut. Offsetting by a hash of the variant keeps the cache (it saves API calls) while giving
    each reel its own starting point — and stays deterministic for a given (variant, cut), so
    a retry re-renders the same reel rather than a different one (rule 12).
    """
    if source == "ai" and _cloudflare_image(_img_prompt(keyword, seed, setting), dest,
                                            seed=_image_seed(variant, seed)):
        return True
    urls = _pexels_photo_urls(keyword)
    if not urls:
        return False
    offset = int(hashlib.sha1(str(variant).encode("utf-8")).hexdigest()[:8], 16) if variant else 0
    try:
        _download(urls[(seed + offset) % len(urls)], dest)
        return os.path.getsize(dest) > 1000
    except Exception as e:  # noqa: BLE001
        log.warning("visuals: photo download failed for %r (%s)", keyword, e)
        return False


def _image_to_kenburns_clip(image_path: str, dest: str, seconds: float, index: int = 0) -> None:
    """Render a slow Ken Burns move over an image → 1080x1920 mp4 clip (FFmpeg).

    Motion alternates by index for variety (rule 16): even = slow zoom IN, odd = slow zoom OUT.
    Deterministic per index so cron retries are stable (rule 12)."""
    from src.assembly import BT709_TAGS, _ffmpeg, x264_args

    frames = int(seconds * 30)
    if index % 2 == 0:
        z = "min(zoom+0.0010,1.12)"                      # slow zoom IN
    else:
        z = "if(eq(on,0),1.12,max(zoom-0.0009,1.0))"     # slow zoom OUT (start zoomed, pull back)
    vf = (
        "scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1920:fps=30,setsar=1,"
        # RGB stills -> YUV with the BT.709 matrix the tags declare (swscale defaults to 601).
        "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
        + BT709_TAGS
    )
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-loop", "1", "-i", image_path, "-t", f"{seconds:.2f}",
         "-vf", vf, *x264_args(), "-r", "30", dest],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ken burns failed ({proc.returncode}): {proc.stderr[-400:]}")


def _fetch_image_broll(keywords: list[str], target_seconds: float, out_dir: str, source: str,
                       variant: str = "", setting: str | None = None) -> list[str]:
    """Build Ken Burns clips from photos/AI images covering the narration. Raises if none made.

    One image per cut the assembler will actually make. Sizing this off a local guess (it was
    `ceil(target / 6.0) + 1`) while assembly cut at `CLIP_SECONDS` left a 30s reel 4 shots short
    of its 10 slices, and the slicer filled the gap by replaying earlier ones — which on a pan
    over a single still is unmissable. Ask the module that does the cutting (rule 7).
    """
    from src import assembly  # local: keeps the module importable without ffmpeg present

    n = min(_MAX_IMG_CLIPS, assembly.slice_count(target_seconds))
    clips: list[str] = []
    for i in range(n):
        kw = keywords[i % len(keywords)]
        img = os.path.join(out_dir, f"img_{i:02d}.jpg")
        if not _fetch_image(kw, img, i, source, variant=variant, setting=setting):
            continue
        clip = os.path.join(out_dir, f"imgclip_{i:02d}.mp4")
        try:
            _image_to_kenburns_clip(img, clip, _IMAGE_CLIP_SECONDS, index=i)
            clips.append(clip)
        except Exception as e:  # noqa: BLE001
            log.warning("visuals: ken burns failed (%s); skipping", e)
    if not clips:
        raise RuntimeError(f"visuals: produced no image clips from source={source}")
    log.info("visuals: %d %s Ken Burns clips for target %.0fs", len(clips), source, target_seconds)
    return clips


def fetch_broll(keywords: list[str], target_seconds: float, out_dir: str,
                setting: str | None = None) -> list[str]:
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
            # The work dir is per-idea (production names it idea_<id>), so it is a stable,
            # already-available identifier for "which reel is this" — no new parameter needed
            # at the call site, and identical across a retry of the same reel.
            return _fetch_image_broll(keywords, target_seconds, out_dir, source,
                                      variant=os.path.basename(os.path.normpath(out_dir)),
                                      setting=setting)
        except Exception as e:  # noqa: BLE001 — fall back to stock video (rule 11)
            log.warning("visuals: %s source failed (%s); falling back to stock video", source, e)

    return _fetch_video_broll(keywords, target_seconds, out_dir)


def _fetch_video_broll(keywords: list[str], target_seconds: float, out_dir: str) -> list[str]:
    """Stock-video B-roll: Pexels then Pixabay (the original strategy)."""
    candidates = _gather_candidates(keywords)
    if not candidates:
        raise RuntimeError(f"visuals: no B-roll found on Pexels/Pixabay for {keywords}.")

    paths: list[str] = []
    from src import assembly  # local: keeps the module importable without ffmpeg present

    # Ask assembly how many CUTS it will make, exactly as the image path does (line ~331).
    # This used to accumulate `min(duration, _SLICE_SECONDS)` with _SLICE_SECONDS=8.0 while
    # assembly cuts at CLIP_SECONDS (~3.5s), so a 28s reel stopped at 4 downloads for 10 cuts
    # and assembly replayed the other 6. The 2026-08-25 repeat fix made slice_count the single
    # source of truth but was only wired into the image path; this is the same bug, in the
    # branch that runs precisely when the primary visual source has already failed.
    needed = min(_MAX_VIDEO_CLIPS, assembly.slice_count(target_seconds))
    for c in candidates:
        if len(paths) >= max(2, needed):
            break
        dest = os.path.join(out_dir, _clip_filename(c["url"]))
        try:
            if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                _download(c["url"], dest)
        except Exception as e:  # noqa: BLE001 — skip a failed download, keep covering
            log.warning("visuals: download failed (%s); skipping", e)
            continue
        paths.append(dest)

    if not paths:
        raise RuntimeError("visuals: found candidates but every download failed.")
    log.info("visuals: %d clip(s) for %d cut(s) over %.0fs", len(paths), needed, target_seconds)
    return paths
