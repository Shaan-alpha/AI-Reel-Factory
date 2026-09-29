"""Generate the channel's background-music beds with Google Lyria 2 on Vertex AI.

    python tools/generate_music_beds.py OUT_DIR            # prints the plan and the cost, spends nothing
    python tools/generate_music_beds.py OUT_DIR --yes      # generates (billed, see below)
    python tools/generate_music_beds.py OUT_DIR --loop-only RAW_DIR   # loop existing clips, free

Why generated: YouTube Content ID flags audio by who REGISTERED it, not by its licence, and the
earlier Pixabay beds were claimed and had to be deleted. A bed generated for this channel is
original, so nobody else has registered it. Lyria 2 (`lyria-002`) returns a 32.8 s instrumental
WAV (48 kHz stereo, SynthID-watermarked) and is billed at $0.06 per 30 s of output, about $0.066
a clip: the four beds below cost about $0.26. Nothing here is part of the daily pipeline; the
beds are committed to assets/music once and reused.

Each clip is crossfaded into itself (3 s, equal power) to make a 62.5 s loop: the clip ends
abruptly, and a longer bed lets assembly start each reel at a different point
(ENABLE_MUSIC_OFFSET). A linear crossfade dipped 2-4.5 dB at the seam; equal power holds it within
normal variation. Credentials: Application Default Credentials for GCP_PROJECT (the same Vertex
setup the pipeline uses).
"""
from __future__ import annotations

import argparse
import base64
import os
import struct
import subprocess
import sys
import tempfile
import wave

_PROJECT = os.environ.get("GCP_PROJECT", "but-it-matters-tts")
_LOCATION = "us-central1"
_URL = (f"https://{_LOCATION}-aiplatform.googleapis.com/v1/projects/{_PROJECT}/locations/"
        f"{_LOCATION}/publishers/google/models/lyria-002:predict")
_COST_PER_CLIP = 0.066
_NEGATIVE = ("vocals, singing, choir, spoken words, dramatic, dark, tense, epic, cinematic "
             "trailer, heavy drums, loud bass, distorted guitar, sudden changes, build-up, drop")

# The beds in assets/music (generated 2026-09-29, picked from nine candidates by measurement:
# the least energy below 150 Hz of each style, no vocals, intros within 1 dB of the body).
BEDS = {
    "calm-lofi-piano": ("Soft lo-fi piano with light brushed percussion and a warm round bass, "
                        "relaxed and thoughtful, about 80 BPM, background music under a spoken "
                        "explainer, instrumental.", 29),
    "calm-marimba": ("Light modern documentary underscore: soft marimba and felt piano ostinato, "
                     "airy pads, a subtle pulse, calm and inquisitive, about 100 BPM, "
                     "instrumental.", 29),
    "calm-pads": ("Calm minimal ambient electronic background for a news explainer: soft warm "
                  "synth pads, a gentle plucked arpeggio, slow steady pulse around 90 BPM, "
                  "neutral and curious mood, unobtrusive, no lead melody, instrumental.", 29),
    "calm-guitar": ("Gentle acoustic guitar fingerpicking over a soft string pad, calm and "
                    "quietly hopeful, simple and understated, background for narration, "
                    "instrumental.", 29),
}


def clean_wav(audio: bytes) -> bytes:
    """Lyria's WAV carries a second WAV header at the start of its data chunk, which a player
    reads as a click. Rebuild the file around the real PCM."""
    if audio[:4] != b"RIFF" or audio[44:48] != b"RIFF":
        return audio
    channels, rate, bits = struct.unpack("<HIxxxxxxH", audio[22:36])
    pcm = audio[audio.find(b"data", 48) + 8:]
    with tempfile.SpooledTemporaryFile() as buf:
        with wave.open(buf, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(bits // 8)
            w.setframerate(rate)
            w.writeframes(pcm)
        buf.seek(0)
        return buf.read()


def make_loop(raw_wav: str, dest_mp3: str) -> None:
    """The clip crossfaded into itself (3 s, equal power), encoded as a VBR MP3 (about 190 kb/s)."""
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw_wav, "-i",
                    raw_wav, "-filter_complex", "[0][1]acrossfade=d=3:c1=qsin:c2=qsin",
                    "-c:a", "libmp3lame", "-q:a", "2", dest_mp3], check=True)


def _generate(session, prompt: str, seed: int) -> bytes:
    r = session.post(_URL, json={"instances": [{"prompt": prompt, "negative_prompt": _NEGATIVE,
                                                "seed": seed}], "parameters": {}}, timeout=180)
    r.raise_for_status()
    pred = (r.json().get("predictions") or [{}])[0]
    b64 = pred.get("bytesBase64Encoded") or pred.get("audioContent")
    if not b64:
        raise RuntimeError(f"no audio in the Lyria response: {str(r.json())[:300]}")
    return clean_wav(base64.b64decode(b64))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--yes", action="store_true", help="generate (billed)")
    ap.add_argument("--loop-only", metavar="RAW_DIR",
                    help="loop RAW_DIR/<bed>.wav clips already generated (free)")
    ap.add_argument("--max-calls", type=int, default=len(BEDS))
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.loop_only:
        for bed in BEDS:
            make_loop(os.path.join(args.loop_only, f"{bed}.wav"),
                      os.path.join(args.out_dir, f"{bed}.mp3"))
            print("looped:", bed)
        return 0

    calls = min(args.max_calls, len(BEDS))
    print(f"{calls} Lyria call(s), about ${calls * _COST_PER_CLIP:.2f}, project {_PROJECT}.")
    if not args.yes:
        print("Nothing generated: re-run with --yes to spend it.")
        return 0

    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(creds)
    raw_dir = os.path.join(args.out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    for n, (bed, (prompt, seed)) in enumerate(BEDS.items()):
        if n >= calls:
            print("stopped at --max-calls")
            break
        raw = os.path.join(raw_dir, f"{bed}.wav")
        with open(raw, "wb") as f:
            f.write(_generate(session, prompt, seed))
        make_loop(raw, os.path.join(args.out_dir, f"{bed}.mp3"))
        print("generated:", bed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
