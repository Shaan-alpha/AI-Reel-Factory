"""AI-video shots: FLUX stills animated by Kling on Higgsfield (design Part A).

Stage 3a holds the money's bookkeeping; stage 3b adds one reel's shots (sizing, the shot planner,
stills, buying, waiting, settling).

Contract:
    sweep()           -> {"settled", "left", "errors"} counts. Settles the Higgsfield jobs that
                         earlier runs left open. Never raises.
    spend_line(since) -> the run's Higgsfield spend for Telegram, read from the ledger, or None.
    close_run(since)  -> after the last reel: the closing sweep, then the spend line. Never raises.
    plan_shots(req, durations) -> (one {"still", "motion", "search"} per shot, may clips be bought)
    depends on        : src.db (the ai_video_jobs ledger), src.higgsfield (free status calls),
                        src.llm (the shot planner), src.visuals (keywords and the fallback plan).

Higgsfield has no spend cap in code, by the operator's choice (2026-11-10): every job is reserved
in the ledger before it is bought, and every dollar is reported. These lines are that report.
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from src import config, db, higgsfield, llm, text, visuals

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReelRequest:
    """What production hands over for one ai_video reel (design 6.1)."""

    idea_id: int
    script_body: str      # the fact-checked English, delivery tags and all
    title: str
    tone: str | None      # "somber" for deaths and serious harm
    setting: str | None   # "India" when the story is set there
    story: str            # the idea's hook and angle, and its title unless title-cased
    audio_path: str       # the trimmed narration
    duration: float       # its length in seconds
    pauses: list[tuple[float, float]]
    work_dir: str
    deadline: float | None  # time.monotonic() by which visuals must be done, or None
    can_buy: bool = True    # False when the reel's subtitle burn failed its preflight

_NOT_CHARGED = frozenset({"failed", "nsfw", "canceled"})
# Paid and not on screen: a job that finished after its reel moved on (late), or whose submit
# never answered (reserved, counted at its quote because it may have been charged).
_PAID_UNUSED = frozenset({"late", "reserved", "submitted"})
# HiggsfieldError kinds that say the service, not one request, failed (see higgsfield.py).
_SERVICE_FAILED = frozenset({"auth", "funds", "busy", "unavailable"})


def _have_key() -> bool:
    return bool((config.get("HF_API_KEY") or "").strip())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settlement(state: dict) -> dict | None:
    """The ledger fields for a job Higgsfield reports as finished; None while it still runs."""
    status = state.get("status")
    if status == "completed":
        return {"status": "completed", "result_url": (state.get("video") or {}).get("url"),
                "settled_at": _now()}
    if status in _NOT_CHARGED:
        return {"status": status, "cost_usd": 0, "settled_at": _now()}
    return None


def sweep() -> dict:
    """Settle the jobs earlier runs left open (design 6.7).

    Every `submitted` or `late` row under 7 days old is re-read: `completed` gets its URL (it was
    paid for, so it keeps its cost, and a later reel of the same idea may reuse the clip), and
    `failed`, `nsfw` or `canceled` cost 0. A job still running, or one whose read or write fails,
    is left for the next sweep. The first failure of Higgsfield itself (a timeout, an outage, a
    refused key) leaves all the rest too, so an outage costs one timeout, not one per row.
    Status calls are free. Runs only when HF_API_KEY is set, and is bookkeeping: it never
    raises."""
    counts = {"settled": 0, "left": 0, "errors": 0}
    if not _have_key():
        return counts
    try:
        rows = db.open_ai_video_jobs()
    except Exception as e:  # noqa: BLE001 — LedgerUnavailable included; the run goes on
        log.warning("ai_video: no sweep, the ledger could not be read (%s)", e)
        return counts
    for done, row in enumerate(rows):
        if not row.get("request_id"):  # never answered: nothing to read, it stays at its quote
            counts["left"] += 1
            continue
        try:
            fields = _settlement(higgsfield.status(row["request_id"]))
            if fields is None:
                counts["left"] += 1
                continue
            db.update_ai_video_job(row["id"], **fields)
            counts["settled"] += 1
        except Exception as e:  # noqa: BLE001 — one row's failure leaves it for the next sweep
            counts["errors"] += 1
            log.warning("ai_video: sweep left job %s open (%s)", row.get("id"),
                        higgsfield.redact(e))
            if getattr(e, "kind", None) in _SERVICE_FAILED:
                # Higgsfield itself failed, not this row: each further call would be refused or
                # wait out its timeout, at the start and the end of the run. Leave them for later.
                counts["left"] += len(rows) - done - 1
                break
    if any(counts.values()):
        log.info("ai_video: sweep %s", counts)
    return counts


def _clips(n: int) -> str:
    return f"{n} clip" if n == 1 else f"{n} clips"


def spend_line(since: datetime, unused: set | None = None) -> str | None:
    """This run's Higgsfield spend for Telegram (design 6.8), from the ledger: clips bought,
    dollars, clips paid for and not used, and the month to date. None when this run reserved
    nothing, when HF_API_KEY is unset (nothing can have been bought), or when the ledger cannot
    be read. `unused` holds the ids of the rows that were not on screen, read before a sweep
    could settle them (see close_run); without it the rows' statuses decide. A clip that was paid
    for and then failed its download or gate is still `completed` in the ledger, so the reel's
    own report (stage 3b) is where that one shows."""
    if not _have_key():
        return None
    try:
        rows = db.ai_video_jobs_since(since)
        if not rows:
            return None
        month = db.ai_video_spend_this_month()
    except Exception as e:  # noqa: BLE001 — a report must never fail a run
        log.warning("ai_video: no spend line, the ledger could not be read (%s)", e)
        return None
    paid = [r for r in rows if float(r.get("cost_usd") or 0) > 0]
    dollars = sum(float(r["cost_usd"]) for r in paid)
    if unused is None:
        n_unused = sum(1 for r in paid if r.get("status") in _PAID_UNUSED)
    else:
        n_unused = sum(1 for r in paid if r.get("id") in unused)
    line = f"🎞️ AI video this run: {_clips(len(paid))}, ${dollars:.2f}"
    if n_unused:
        line += f" ({n_unused} paid, not used)"
    return f"{line}; ${month:.2f} this month."


def close_run(since: datetime) -> str | None:
    """After the last reel (design 6.7, 6.8): settle what is still open, then return the run's
    spend line (None when there is nothing to report).

    Which clips this run paid for and did not use is read before the sweep: the sweep turns a
    `late` clip that has since finished into `completed`, which would then read as used (review
    I-2). Never raises."""
    if not _have_key():
        return None
    try:
        before = db.ai_video_jobs_since(since)
    except Exception as e:  # noqa: BLE001 — a report must never fail a run
        log.warning("ai_video: no closing sweep or spend line, the ledger could not be read (%s)",
                    e)
        return None
    sweep()
    unused = {r.get("id") for r in before if r.get("status") in _PAID_UNUSED}
    return spend_line(since, unused=unused)


# --- The shot planner (design 6.5) --------------------------------------------------------------

# Sent with every Kling job, as test 3 did.
NEGATIVE = ("text, subtitles, captions, watermark, logo, distortion, warping, flicker, fast motion, "
            "scene change, people")
# The look of every still (AI_VIDEO_STYLE overrides it); code appends it, the model never writes it.
_DEFAULT_STYLE = ("cinematic 3D animated film still, stylized shapes, rich saturated color, bright "
                  "clear lighting")
# The fallback plan's one motion line. Nothing is bought from a fallback plan, so it only stands
# in for a motion the stills never get.
FALLBACK_MOTION = "A slow, gentle push-in; everything keeps its exact shape and colors."
_STILL_CHARS, _MOTION_CHARS = 1800, 500
_TAG = re.compile(r"\[[^\]]*\]|<[^>]{1,60}>")

# A capitalised word that names no person: places (design 6.5's fixed list of countries, Indian
# states and large cities, as words, with their peoples and languages), months and days, the
# Sun, Moon and planets, and the words that start sentences. "Uttar Pradesh" is two entries.
_NOT_NAMES = frozenset("""
Afghanistan Albania Algeria Angola Argentina Armenia Australia Austria Azerbaijan Bahamas Bahrain
Bangladesh Belarus Belgium Benin Bhutan Bolivia Bosnia Botswana Brazil Brunei Bulgaria Burkina
Burundi Cambodia Cameroon Canada Chad Chile China Colombia Congo Costa Rica Croatia Cuba Cyprus
Czech Czechia Denmark Djibouti Dominican Ecuador Egypt Salvador Eritrea Estonia Eswatini Ethiopia
Fiji Finland France Gabon Gambia Georgia Germany Ghana Greece Guatemala Guinea Guyana Haiti
Honduras Hungary Iceland India Indonesia Iran Iraq Ireland Israel Italy Ivory Coast Jamaica Japan
Jordan Kazakhstan Kenya Korea Kosovo Kuwait Kyrgyzstan Laos Latvia Lebanon Lesotho Liberia Libya
Lithuania Luxembourg Madagascar Malawi Malaysia Maldives Mali Malta Mauritania Mauritius Mexico
Moldova Monaco Mongolia Montenegro Morocco Mozambique Myanmar Burma Namibia Nepal Netherlands
Holland Zealand Nicaragua Niger Nigeria Macedonia Norway Oman Pakistan Palestine Gaza Panama Papua
Paraguay Peru Philippines Poland Portugal Qatar Romania Russia Rwanda Samoa Saudi Arabia Senegal
Serbia Seychelles Sierra Leone Singapore Slovakia Slovenia Somalia Africa Sudan Spain Sri Lanka
Suriname Sweden Switzerland Syria Taiwan Tajikistan Tanzania Thailand Timor Togo Tonga Trinidad
Tobago Tunisia Turkey Turkiye Turkmenistan Uganda Ukraine Emirates Kingdom Britain England
Scotland Wales America Uruguay Uzbekistan Vanuatu Vatican Venezuela Vietnam Yemen Zambia Zimbabwe
US USA UK UAE EU UN Tibet Kashmir Hong Kong Greenland Antarctica Arctic Asia Europe Oceania
Pacific Atlantic Himalaya Himalayas Everest Ganga Ganges Yamuna Brahmaputra Indus Middle East West
North South Gulf Red Sea Ocean Bay Bengal Arabian
Andhra Pradesh Arunachal Assam Bihar Chhattisgarh Goa Gujarat Haryana Himachal Jharkhand Karnataka
Kerala Madhya Maharashtra Manipur Meghalaya Mizoram Nagaland Odisha Orissa Punjab Rajasthan Sikkim
Tamil Nadu Telangana Tripura Uttar Uttarakhand Andaman Nicobar Chandigarh Dadra Nagar Haveli Daman
Diu Delhi Jammu Ladakh Lakshadweep Puducherry Pondicherry
Mumbai Bombay NCR Kolkata Calcutta Chennai Madras Bengaluru Bangalore Hyderabad Ahmedabad Pune
Surat Jaipur Lucknow Kanpur Nagpur Indore Thane Bhopal Visakhapatnam Vizag Patna Vadodara
Ghaziabad Ludhiana Agra Nashik Faridabad Meerut Rajkot Varanasi Srinagar Amritsar Prayagraj
Allahabad Ranchi Coimbatore Gwalior Jodhpur Madurai Raipur Kota Guwahati Thiruvananthapuram Kochi
Noida Gurugram Gurgaon Dehradun Shimla Mysuru Mysore Udaipur Ayodhya Bhubaneswar Mangaluru
London Paris Berlin Rome Madrid Moscow Kyiv Kiev Beijing Shanghai Tokyo Seoul Washington York
Angeles Chicago Toronto Sydney Melbourne Dubai Doha Riyadh Tehran Baghdad Kabul Islamabad Karachi
Lahore Dhaka Kathmandu Colombo Bangkok Jakarta Manila Hanoi Cairo Nairobi Lagos Johannesburg
Istanbul Ankara Jerusalem Tel Aviv Geneva Brussels Vienna Amsterdam Davos
Indian Indians American Americans Chinese Pakistani Pakistanis Russian Russians British Japanese
Korean Koreans European Europeans African Africans Asian Asians Australian Australians Canadian
French German Germans Italian Spanish Israeli Israelis Palestinian Palestinians Iranian Iraqi
Afghan Bangladeshi Nepali Nepalese Lankan Emirati Arab Arabs Ukrainian Ukrainians Turkish
Egyptian Brazilian Mexican Western Eastern Northern Southern Hindu Hindus Muslim Muslims Sikh Sikhs
Christian Christians Buddhist Jain Parsi Hindi English Telugu Bengali Marathi Gujarati Punjabi
Kannada Malayalam Urdu Sanskrit Odia
January February March April May June July August September October November December Jan Feb
Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec Monday Tuesday Wednesday Thursday Friday Saturday Sunday
Sun Moon Earth Mercury Venus Mars Jupiter Saturn Uranus Neptune Pluto Milky Way Solar
The A An And But Or Nor So Yet For Of In On At To By With From Into Over Under After Before About
As Is Are Was Were Be Been Being It Its This That These Those He She They We You I His Her Their
Our Your My Who What Why How When Where Which Here There Now Then Today Yesterday Tomorrow Tonight
If Not No Yes All Some Many Most More Each Every Both One Two Three Four Five Six Seven Eight Nine
Ten First Second Third Last Next New Old Big Small Just Only Also Even Still Already While Since
Until Because Although Though However Meanwhile Instead Again Once Twice Up Down Out Off Over
GDP CEO GST UPI ATM EMI LPG CNG OTT ICU DNA LED USB GPS NRI
""".split())
# Words joined by these are one name ("Sunita Williams"); a hyphen joins "Indo-Pacific" too.
_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’]*")


def _plain(script_body: str) -> str:
    """The narration as words, without delivery tags ([short pause], <emphasis>)."""
    return re.sub(r"\s+", " ", _TAG.sub(" ", script_body or "")).strip()


def _story_names(texts: list[str]) -> set[str]:
    """Every capitalised word the story uses as a name (design 6.5): one capitalised in
    mid-sentence, one in a run of two or more capitalised words ("Sunita Williams" opening a
    sentence), or one with a capital inside it (NASA, SpaceX), less places and common words."""
    names: set[str] = set()
    for chunk in texts:
        for sentence in text.split_sentences(chunk or ""):
            tokens = [re.sub(r"['’]s$", "", t).strip("'’")
                      for t in _NAME_TOKEN.findall(sentence)]
            caps = [bool(t) and t[0].isupper() for t in tokens]
            for i, token in enumerate(tokens):
                if not caps[i] or len(token) < 2:
                    continue
                in_run = (i > 0 and caps[i - 1]) or (i + 1 < len(tokens) and caps[i + 1])
                inner = len(token) >= 3 and any(c.isupper() for c in token[1:])
                if i > 0 or in_run or inner:
                    names.add(token)
    return names - _NOT_NAMES


def _names_in(shots: list[dict], names: set[str]) -> list[str]:
    """The story's names that appear, as whole words, in any still or motion prompt."""
    found = set()
    for shot in shots:
        words = set(_NAME_TOKEN.findall(f"{shot.get('still', '')} {shot.get('motion', '')}"))
        words |= {re.sub(r"['’]s$", "", w) for w in words}
        found |= names & words
    return sorted(found)


def _style_line(mood: str, somber: bool) -> str:
    style = (config.get("AI_VIDEO_STYLE") or _DEFAULT_STYLE).strip().rstrip(".")
    mood = re.sub(r"[^A-Za-z ,'-]", "", mood or "").strip(" ,-")[:40].strip()
    if not mood:
        mood = "calm, quiet, respectful" if somber else "calm, informative"
    return f"Style: {style}. Mood: {mood}."


def _planner_prompt(req: ReelRequest, durations: list[float], note: str = "") -> str:
    m = len(durations)
    somber = (req.tone or "").lower() == "somber"
    seconds = ", ".join(f"{d:.1f} s" for d in durations)
    tone = ("somber: a death or serious harm. Calm, symbolic scenes and minimal motion; nothing "
            "dramatic." if somber else "plain and informative")
    return f"""{note}You plan the pictures for a vertical YouTube Short that explains a news story to viewers in India.
Each shot is one still image; a video model then animates most of them for a few seconds.

NARRATION:
{_plain(req.script_body)}

TITLE: {req.title}
TONE: {tone}
SETTING: {req.setting or "wherever the story happens"}
SHOTS: {m}, in narration order, lasting {seconds}.
Shot 1 shows the opening claim; the last shot shows the payoff, why it matters.

For every shot write:
- "still": one descriptive paragraph of 60 to 100 words, not a list of tags. The subject and its action first, then the setting, then the light (its source, direction and softness). One main subject, large and centred, filling the middle half of a vertical 9:16 frame, brightly and evenly lit; name the shot size and the camera angle. Keep the top fifth and the lower third of the frame simple and calm: a title and subtitles sit there. Describe what you want, never what to avoid (write "all surfaces are plain and unmarked"), and never use a noun that invites lettering: sign, poster, headline, screen, newspaper, label, banner, document. Do not write a style or mood line: one is added.
- "motion": one to three short sentences of motion only. One slow motion of the subject, at most one supporting motion, and what stays still. Exactly one camera instruction: static, or one slow, stable move. Nothing that is not in the picture; say the subject keeps its exact shape and colors.
- "search": one to three plain words a stock-photo site would have for this shot, such as "cargo ship".

Content rules:
- No real person and no likeness of one, and no name from the story in any "still" or "motion". Show places, objects, symbols, hands, or small figures seen from behind.
- No logos, brand marks, flags carrying text, documents, screens or interfaces.
- Nothing that imitates footage of the real event: no disaster in progress, no violence, no bodies, no crowd in distress.{" This is a somber story: calm, symbolic scenes and minimal motion." if somber else ""}

Return one JSON object and nothing else, with exactly {m} shots:
{{"mood": "two or three words for the reel's mood", "shots": [{{"still": "...", "motion": "...", "search": "..."}}]}}"""


def _parse_plan(raw: str, m: int) -> tuple[list[dict], str]:
    """The plan's shots and mood; ValueError when its shape is not m usable shots."""
    data = llm.parse_json_object(raw)
    shots = data.get("shots")
    if not isinstance(shots, list) or len(shots) != m:
        raise ValueError(f"{len(shots) if isinstance(shots, list) else 'no'} shots, not {m}")
    clean = []
    for shot in shots:
        still = str((shot or {}).get("still") or "").strip() if isinstance(shot, dict) else ""
        motion = str((shot or {}).get("motion") or "").strip() if isinstance(shot, dict) else ""
        if not (still and motion):
            raise ValueError("a shot without a still or a motion")
        clean.append({"still": still, "motion": motion[:_MOTION_CHARS],
                      "search": str(shot.get("search") or "").strip()})
    return clean, str(data.get("mood") or "")


def _fallback_plan(req: ReelRequest, m: int) -> list[dict]:
    """Today's `ai` stills from the script's keywords: nothing is bought from this plan."""
    plain = _plain(req.script_body)
    words = (visuals.extract_keywords(plain, m) or visuals._keywords_heuristic(req.title, m)
             or ["city skyline"])
    return [{"still": visuals._img_prompt(words[i % len(words)], i, req.setting),
             "motion": FALLBACK_MOTION, "search": words[i % len(words)]} for i in range(m)]


def plan_shots(req: ReelRequest, durations: list[float]) -> tuple[list[dict], bool]:
    """One {"still", "motion", "search"} per shot, in narration order, and whether clips may be
    bought from it (design 6.5).

    One planner call (Gemini, then Groq). A plan that puts a name from the story in a prompt, or
    has the wrong shape, gets one retry with the problem quoted back. A second failure, or a
    model that cannot answer, gives the fallback plan, and nothing is bought for that reel."""
    m = len(durations)
    names = _story_names([_plain(req.script_body), req.story])
    somber = (req.tone or "").lower() == "somber"
    note = ""
    for _attempt in range(2):
        try:
            raw = llm.generate(_planner_prompt(req, durations, note), json=True, max_tokens=4096)
            shots, mood = _parse_plan(raw, m)
        except ValueError as e:
            note = (f"Your last reply was not usable ({e}). Return exactly {m} shots, each with "
                    f"a still and a motion.\n\n")
            log.warning("ai_video: the shot plan was not usable (%s)", e)
            continue
        except Exception as e:  # noqa: BLE001 — every provider failed: the fallback plan
            log.warning("ai_video: the shot planner failed (%s); no clips for this reel", e)
            break
        found = _names_in(shots, names)
        if found:
            note = (f"Your last plan named these names from the story: {', '.join(found)}. No "
                    f"name from the story may appear in any still or motion; show the scene "
                    f"without them.\n\n")
            log.warning("ai_video: the shot plan named %s", ", ".join(found))
            continue
        style = _style_line(mood, somber)
        words = visuals._keywords_heuristic(_plain(req.script_body), m) or ["city skyline"]
        for i, shot in enumerate(shots):
            room = _STILL_CHARS - len(style) - 1
            shot["still"] = f"{shot['still'][:room].rstrip()} {style}"
            shot["search"] = shot["search"] or words[i % len(words)]
        return shots, True
    return _fallback_plan(req, m), False


# --- A picture for every shot (design 6.2 step 5, 6.9) -----------------------------------------

FPS = 24  # an ai_video reel's rate end to end: Kling's own, so no clip is converted (11.1)


class NoShots(RuntimeError):
    """Not one shot has a picture: the reel falls back to today's `ai` path (design 6.2 step 11)."""


@dataclass(frozen=True)
class Picture:
    """One shot's still."""

    path: str
    animatable: bool  # a FLUX.2 klein still (portrait, seeded): the only kind Kling is given


def _check_still(path: str) -> bool:
    """Stage 4's still gate (stray lettering, a dark subject) plugs in here; in 3b every still
    passes."""
    return True


def _picture(req: ReelRequest, shot: dict, i: int) -> Picture | None:
    """Shot i's still: klein, then schnell, then a Pexels photo found with the planner's search
    words, never with the still prompt (design 6.9). None when all three fail."""
    variant = f"idea_{req.idea_id}"
    still = os.path.join(req.work_dir, f"still_{i:02d}.jpg")
    drew = visuals.ai_still(shot["still"], still, visuals._image_seed(variant, i))
    if drew and _check_still(still):
        return Picture(still, drew == "klein")
    photo = os.path.join(req.work_dir, f"photo_{i:02d}.jpg")
    if visuals.stock_photo(shot["search"], photo, variant, i):
        return Picture(photo, False)
    return None


def _pictures(req: ReelRequest, plan: list[dict]) -> list[Picture]:
    """One picture per shot, drawn in parallel. A shot with none shows its neighbour's (the shot
    before, or for the first shot the next that has one), never animated: a shot is never
    dropped, since the cut list is fixed. NoShots when no shot has a picture at all."""
    os.makedirs(req.work_dir, exist_ok=True)
    workers = max(1, min(len(plan), visuals._visual_workers()))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(lambda i: _picture(req, plan[i], i), range(len(plan))))
    if not any(got):
        raise NoShots(f"no picture for any of the {len(plan)} shots")
    pictures: list[Picture] = []
    for i, pic in enumerate(got):
        if pic is None:
            near = pictures[-1] if pictures else next(p for p in got if p)
            log.warning("ai_video: shot %d has no picture of its own; it shows its neighbour's", i)
            pic = Picture(near.path, False)
        pictures.append(pic)
    return pictures


def _still_clip(picture: Picture, dest: str, seconds: float, index: int) -> str:
    """A Ken Burns move over the shot's still, at the reel's 24 fps, a little longer than the
    shot so its last frame is never short (review finding 7: pace the move to the shot)."""
    visuals._image_to_kenburns_clip(picture.path, dest, seconds + 0.1, index=index, fps=FPS)
    return dest


# --- Buying the clips (design 6.2 step 7, 6.4) --------------------------------------------------

_clock = time.monotonic   # the phase deadline's clock; tests replace it and _sleep
_sleep = time.sleep
_latch: set[str] = set()     # this run's stop latches (6.4): funds, auth, ledger, slow
_alerted: set[str] = set()   # the alert kinds already told this run (6.8: one alert per kind)
_REPEAT_WAITS = (2, 4, 8)    # seconds between repeats of an unanswered submit, then 10
_CLIP_SECONDS = 5


def begin_run() -> None:
    """A new run: no stop latch is set and no alert has been sent."""
    _latch.clear()
    _alerted.clear()


def _stop_buying() -> bool:
    """A stop latch is set, so nothing more is bought this run: Higgsfield is out of funds or
    refused the key, the ledger table is missing, or a reel's queue gave it no clip in time."""
    return bool(_latch)


def video_shots(m: int, k: int) -> list[int]:
    """Which of m shots are video when k clips may be bought (design 6.3): shot 0 (the opening
    claim), then the last (the payoff), then the rest from the start. A still never opens the
    reel while there is a clip to buy."""
    order = [0] + ([m - 1] if m > 1 else []) + list(range(1, m - 1))
    return sorted(order[:max(0, min(m, k))])


@dataclass
class Job:
    """One Kling job of this attempt, as its ledger row records it."""

    shot: int
    row_id: int
    key: str                        # its idempotency key: every repeat of the submit carries it
    request_id: str | None = None
    status: str = "reserved"
    cost: float = 0.0               # the quote until it is known not to be charged
    submitted_at: float | None = None
    ambiguous: bool = False         # a submit went unanswered: one job may exist and be charged
    clip: str | None = None         # the downloaded clip, once usable


def _model() -> str:
    return (config.get("AI_VIDEO_MODEL") or higgsfield.KLING).strip()


def _content_type(path: str) -> str:
    """The still's type from its first bytes: FLUX answers PNG or JPEG under any file name."""
    with open(path, "rb") as f:
        head = f.read(12)
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _record(job: Job, **fields) -> None:
    """Write a job's progress to its row. A failed write is logged and the job goes on: the row
    keeps what it had, and a reserved row counts at its quote."""
    try:
        db.update_ai_video_job(job.row_id, **fields)
    except Exception as e:  # noqa: BLE001 — the reel goes on; the sweep or the quote covers it
        log.warning("ai_video: could not record shot %d's job (%s)", job.shot, e)


def _refuse(job: Job, why: object) -> None:
    """Higgsfield refused the job before it existed, so nothing was charged."""
    job.status, job.cost = "refused", 0.0
    log.warning("ai_video: shot %d was not bought (%s)", job.shot, higgsfield.redact(why))
    _record(job, status="refused", cost_usd=0, settled_at=_now())


def _wait(seconds: float, phase_end: float) -> bool:
    """Sleep up to `seconds`, never past the phase's end; True while time is left after it."""
    left = phase_end - _clock()
    if left <= 0:
        return False
    _sleep(min(seconds, left))
    return _clock() < phase_end


def _submit(job: Job, picture: Picture, motion: str, model: str, phase_end: float) -> None:
    """Upload the shot's still once, then submit its job, repeating only what may be repeated."""
    try:
        url = higgsfield.upload(picture.path, _content_type(picture.path))
    except higgsfield.HiggsfieldError as e:
        if e.kind in ("funds", "auth"):
            _latch.add(e.kind)
        _refuse(job, f"the still was not uploaded: {e}")  # no still, no job
        return
    body = {"prompt": motion, "image_url": url, "duration": _CLIP_SECONDS,
            "negative_prompt": NEGATIVE}
    waits = iter(_REPEAT_WAITS)
    while True:
        try:
            answer = higgsfield.submit(model, body, job.key)
        except higgsfield.HiggsfieldError as e:
            if e.kind == "unavailable":
                # It may have been accepted: repeat with the same key and body, which Higgsfield
                # answers with the original job and no second charge (live check, 2026-11-13).
                job.ambiguous = True
                if _wait(next(waits, 10), phase_end):
                    continue
                log.warning("ai_video: shot %d's submit never answered; its row stays at its "
                            "quote", job.shot)
                return
            if e.kind == "busy":
                wait = e.retry_after if e.retry_after is not None else next(waits, 10)
                if _clock() + wait < phase_end:
                    _sleep(wait)
                    continue
            if e.kind in ("funds", "auth"):
                _latch.add(e.kind)
            if job.ambiguous:
                # An earlier attempt may have created a charged job (3a's I-6): keep the quote.
                log.warning("ai_video: shot %d was refused after an unanswered submit (%s); its "
                            "row stays at its quote", job.shot, e)
                return
            _refuse(job, e)
            return
        job.request_id, job.status = str(answer["request_id"]), "submitted"
        job.submitted_at = _clock()
        _record(job, request_id=job.request_id, status="submitted")
        return


def _buy(req: ReelRequest, positions: list[int], pictures: list[Picture], plan: list[dict],
         price: float, phase_end: float) -> list[Job]:
    """Buy a clip for each video position: shot 0 first, then the reel's last shot, then the rest
    in order. Each row is reserved, at the quote and with a fresh key, before its still is
    uploaded or its job submitted (design 6.2 step 7). A failed reserve buys nothing more for
    this reel; a stop latch, or the phase's end, stops the buying too."""
    model = _model()
    last = len(pictures) - 1
    jobs: list[Job] = []
    for shot in sorted(positions, key=lambda s: (s != 0, s != last, s)):
        if _stop_buying() or _clock() >= phase_end:
            break
        if not pictures[shot].animatable:
            continue  # a schnell still or a stock photo is never animated
        try:
            row = db.reserve_ai_video_job(req.idea_id, shot, model, price)
        except Exception as e:  # noqa: BLE001 — no row, no purchase
            if isinstance(e, db.LedgerUnavailable):
                _latch.add("ledger")
            log.warning("ai_video: shot %d could not be reserved (%s); nothing more is bought "
                        "for idea %s", shot, e, req.idea_id)
            break
        job = Job(shot=shot, row_id=row["id"], key=row["idempotency_key"], cost=float(price))
        jobs.append(job)
        _submit(job, pictures[shot], plan[shot]["motion"], model, phase_end)
    return jobs
