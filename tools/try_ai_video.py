"""One AI-video test render, nothing uploaded (stage 3b's plan, the operator's go-ahead).

Run: python tools/try_ai_video.py --yes-spend [--script ID] [--english] [--somber] [--out PATH]

Takes one stored, fact-checked script through what a reel does with VISUAL_SOURCE=ai_video: the
Hinglish rendering (unless --english), the voice, the subtitle burn tried on a blank second,
ai_video.make_shots (which buys up to AI_VIDEO_BUDGET_USD of Kling clips, every job reserved in
ai_video_jobs first), the cut-list render at 24 fps and the subtitle burn. The reel is written to
test-videos/, never uploaded.

Spends about $0.95 of Higgsfield clips (6 at $0.1575), plus cents for the Hinglish rendering and
the voice. It refuses to start without the ai_video_jobs table (the SQL at the end of docs/03 §4),
since without it nothing could be bought and the render would only show stills.

Needs the local .env (Higgsfield, Supabase, Cloudflare, the models and the voice). Prints no key.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

# "python tools/try_ai_video.py" puts tools/ on sys.path, not the project root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:  # the local .env on the dev machine
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from src import (  # noqa: E402 — must follow the sys.path fix above
    ai_video,
    assembly,
    db,
    hinglish,
    production,
    scriptwriter,
    subtitles,
    voice,
)


def _pick(script_id: int | None) -> tuple[dict, dict]:
    """The script to render and its idea: the given one, else the newest script whose idea was
    not blocked or rejected (so it passed the fact-check)."""
    client = db.get_client()
    query = client.table("scripts").select("id,idea_id,body,title,caption")
    rows = (query.eq("id", script_id) if script_id else query.order("id", desc=True)
            .limit(25)).execute().data or []
    for row in rows:
        ideas = client.table("ideas").select("*").eq("id", row["idea_id"]).execute().data or []
        if ideas and (script_id or ideas[0].get("status") not in ("blocked", "rejected")):
            return row, ideas[0]
    raise SystemExit("No usable script found (pass --script ID).")


def main(argv: list[str] | None = None) -> int:
    # A Windows console (cp1252) cannot print "🎞️": the first real render died on it after
    # paying for its clips, before it wrote the reel (2026-11-13).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes-spend", action="store_true",
                        help="confirm spending up to AI_VIDEO_BUDGET_USD of Kling clips")
    parser.add_argument("--script", type=int, help="a scripts.id to render (default: newest)")
    parser.add_argument("--english", action="store_true", help="narrate in English")
    parser.add_argument("--somber", action="store_true", help="render with the somber tone")
    parser.add_argument("--out", help="where to write the reel (default: test-videos/)")
    parser.add_argument("--key-number",
                        help="the reel's key number, copied exactly from the script (stored "
                             "scripts predate the writer's key number)")
    args = parser.parse_args(argv)
    if not args.yes_spend:
        print("This buys up to AI_VIDEO_BUDGET_USD of Kling clips (about $0.95). Run it again "
              "with --yes-spend.")
        return 2
    if not (os.environ.get("HF_API_KEY") or "").strip():
        print("HF_API_KEY is not set (local .env).")
        return 2
    try:
        month = db.ai_video_spend_this_month()
    except db.LedgerUnavailable:
        print("The ai_video_jobs table is missing: run the SQL at the end of docs/03 §4 in "
              "Supabase first. Nothing was spent.")
        return 2

    script, idea = _pick(args.script)
    title = script.get("title") or idea.get("title") or ""
    # Production's own check: a number the narration does not say gets no card.
    key_number = scriptwriter.checked_key_number(args.key_number, script["body"]) or None
    if args.key_number and not key_number:
        print(f"--key-number {args.key_number!r} is not in the script as written, so there is "
              f"no number card.")
    tone = "somber" if args.somber else "plain"
    print(f"Script {script['id']} (idea {idea['id']}): {title!r}; ${month:.2f} spent this month "
          f"so far.")
    work = tempfile.mkdtemp(prefix="try_ai_video_")
    started = datetime.now(timezone.utc)
    ai_video.begin_run()

    spoken, why = (None, "--english") if args.english else hinglish.to_hinglish(
        script["body"], title, tone)
    spoke: dict = {}
    if spoken:
        expected = len(scriptwriter._visible_words(script["body"])) / 2.2
        audio, duration = voice.synthesize(spoken["said"], work, meta=spoke, tone=tone,
                                           expected_seconds=expected)
    else:
        print(f"Narrating in English ({why}).")
        audio, duration = voice.synthesize(script["body"], work, meta=spoke, tone=tone)
    print(f"Voiced by {spoke.get('voice')}: {duration:.1f} s.")

    lines = spoken["lines"] if spoken else None
    source = production._source_domain(idea.get("sources"))
    can_buy = subtitles.preflight(audio, os.path.join(work, "preflight"), lines=lines,
                                  hook_text=title, source_label=source)
    story = production._story_text(idea)
    setting = "India" if production._INDIA_RE.search(f"{idea.get('title')} {story}") else None
    shots = ai_video.make_shots(ai_video.ReelRequest(
        idea_id=idea["id"], script_body=script["body"], title=title, tone=tone, setting=setting,
        story=story, audio_path=audio, duration=duration, pauses=subtitles.pauses(audio),
        work_dir=os.path.join(work, "shots"), deadline=None, can_buy=can_buy))
    for problem in shots.problems:
        print(problem)
    print(ai_video.reel_line(shots))
    print("Shots:", ", ".join(f"{i}:{kind}" for i, kind in enumerate(shots.kinds)))

    raw = assembly.assemble(audio, shots.files, os.path.join(work, "reel_raw.mp4"),
                            cuts=shots.cuts, fps=ai_video.FPS)
    final = os.path.join(work, "reel_final.mp4")
    if lines:
        subtitles.burn_hinglish(raw, audio, final, lines, hook_text=title, source_label=source,
                                fps=ai_video.FPS, key_number=key_number)
    else:
        subtitles.burn_captions(raw, audio, final, hook_text=title, source_label=source,
                                script_text=script["body"], fps=ai_video.FPS,
                                key_number=key_number)
    out = args.out or os.path.join(ROOT, "test-videos", f"ai_video_try_{script['id']}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    shutil.copyfile(final, out)
    print(f"Wrote {out}")
    line = ai_video.close_run(started)
    if line:
        print(line)
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
