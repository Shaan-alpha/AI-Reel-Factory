# assets/music/ — background music beds

Drop **1–3 royalty-free / Content-ID-safe** audio tracks here (`.mp3`, `.m4a`, `.wav`, `.ogg`).
Assembly mixes one quietly under the narration (FFmpeg `amix`, ~12% volume), picking a track
deterministically per reel so reruns are stable but different reels vary.

- **Empty dir → no music** (assembly skips it gracefully). Disable entirely with `ENABLE_MUSIC=false`.
- Volume is tunable via `MUSIC_VOLUME` (default `0.12`).

## Where to get safe tracks (free, monetization-safe)
Pick "cinematic / suspense / thrilling" beds and **verify each is Content-ID-clear + commercial-OK**:
- **YouTube Audio Library** (Studio → Audio Library) — safest; download and drop here.
- **Pixabay Music** (https://pixabay.com/music/) — CC0, no attribution; *preview/verify each track*
  (a few carry Content-ID signatures).
- Uppbeat / Bensound / NCS — usually require credit in the description; read each license.

Keep files small (1–3 MB each). They're committed to the repo so GitHub Actions can use them.
