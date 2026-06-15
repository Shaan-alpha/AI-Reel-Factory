# assets/music/ — background music beds

Drop **1–3 Content-ID-safe** audio tracks here (`.mp3`, `.m4a`, `.wav`, `.ogg`). Assembly mixes one
quietly under the narration (FFmpeg `amix`), picking a track deterministically per reel so reruns
are stable but different reels vary.

- **Empty dir → no music** (assembly skips it gracefully — so it's safe to leave this empty).
  Disable entirely with `ENABLE_MUSIC=false`.
- Volume is tunable via `MUSIC_VOLUME` (default `0.10` ≈ 10%).

## Where to get safe tracks — READ THIS FIRST

⚠️ **"Royalty-free" ≠ claim-free.** YouTube Content ID flags audio by who **registered** it, not by
its licence — so even CC0 / Pixabay tracks can trigger a copyright claim (this bit us: the previous
Pixabay beds got flagged and were deleted). The only source **guaranteed** claim-free on *your own*
channel is YouTube's own library:

- ✅ **YouTube Audio Library** — [studio.youtube.com](https://studio.youtube.com) → **Audio Library
  → Music** → filter **Mood = Dark / Dramatic / Tense**, tick **"No attribution required"**,
  download 1–3 tracks, drop the files in this folder. Guaranteed safe for monetised uploads.
  **Use this.**
- ⚠️ Pixabay / Tunetank / Chosic / Melody Loops — "free", but you must verify each is
  Content-ID-clear (Melody Loops has a "Hide Content ID" filter). A gamble — prefer the Audio Library.
- ⚠️ Bensound / Uppbeat / NCS — free **with attribution** (a credit line is required in the
  description). Workable, but the credit must be added to every video.

Keep files small (1–3 MB each). They're committed to the repo so GitHub Actions can use them.
