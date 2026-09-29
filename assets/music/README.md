# assets/music/ — background music beds

Assembly mixes one of these quietly under the narration (FFmpeg `amix`), picking a track
deterministically per reel so reruns are stable but different reels vary.

- **Empty dir → no music** (assembly skips it gracefully — so it's safe to leave this empty).
  Disable entirely with `ENABLE_MUSIC=false`.
- Level: each reel measures its bed and sets it `MUSIC_LU_BELOW_VOICE` (default 11 LU) under the
  narration, whatever the track's own loudness. `MUSIC_VOLUME` (default `0.10`) is used only if
  that measurement fails. Each reel starts its bed at a different point (`ENABLE_MUSIC_OFFSET`).

## The current beds (2026-09-29): generated for this channel

`calm-lofi-piano`, `calm-marimba`, `calm-pads`, `calm-guitar` — calm, neutral instrumentals made
with **Google Lyria 2** (`lyria-002`) on the channel's Vertex project by
[`tools/generate_music_beds.py`](../../tools/generate_music_beds.py), which records each prompt
and seed. They replaced four YouTube Audio Library tracks tagged Dark/Dramatic, which fought the
channel's soft/positive lean.

- **Why generated:** Content ID flags audio by who *registered* it, not by its licence (the earlier
  Pixabay beds were claimed and deleted). A bed generated for this channel is original, so nobody
  else has registered it. Lyria output is SynthID-watermarked, and the video description
  discloses AI-generated music.
- **How they were picked:** nine candidates (five styles, two seeds); these four have the least
  energy below 150 Hz of each style (8-26%; the boomy ones measured 48-70%), no vocals (speech
  detection found none), and intros within 1 dB of the body. Each 32.8 s clip is crossfaded into
  itself (3 s, equal power) to make a 62.5 s loop.
- **Measured in the production mix** (under the channel voice): -14.5 LUFS, true peak -2.1 dBTP,
  for all four.
- **Cost:** $0.06 per 30 s of output; the nine candidates cost $0.66 once. There is no ongoing
  cost: the files are committed and reused.

## Adding or replacing a bed

- Generate more: `python tools/generate_music_beds.py OUT_DIR` prints the plan and cost; `--yes`
  spends it. Listen under a voice before committing anything.
- Or download from the **YouTube Audio Library** ([studio.youtube.com](https://studio.youtube.com)
  → Audio Library → Music, "No attribution required"), which is guaranteed claim-safe on your own
  channel.
- ⚠️ "Royalty-free" sites (Pixabay, Tunetank, Chosic, ...) are a gamble for Content ID, and
  Bensound / Uppbeat / NCS need a credit line in every description.

Keep files small (1–3 MB each). They're committed to the repo so GitHub Actions can use them.
