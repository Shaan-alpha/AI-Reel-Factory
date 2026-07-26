# News / Impact Niche Playbook

**Niche:** Daily impact news/info explainers — Indian & international developments that could
have a big impact on the world or India.
**Style:** Daily impact explainer (*what happened → why it matters → impact*).
**Lean:** ~~Soft/positive-impact~~ → **Truth-first** (operator policy, 2026-07-27). There is no
positivity requirement and no neutrality requirement: the channel may reach a verdict and name
who is responsible. Politics, government action and court rulings are fully in scope. What
replaces the old tone filter is a harder evidence bar — see §5.

> ⚠️ News is a **special, higher-risk niche** for a faceless auto-channel. This page exists
> because the generic faceless playbook will get a news channel **demonetized or struck** in
> 2026 if followed blindly. Read this before building Modules 1 (ideation), 3 (scriptwriter),
> and 9 (publish).

---

## 1. The #1 rule: ORIGINALITY (or you don't get monetized)

On **2026-07-15** YouTube renamed "repetitious content" → **"Inauthentic Content"** and
demonetized **thousands** of faceless AI channels. AI detection now flags mass-produced
videos that *look, sound, and move the same* and merely repackage someone else's reporting.

**What survives & monetizes:** content with *significant original commentary, perspective,
analysis, or educational value* — a human/creative-director making meaningful decisions.

**Therefore, in this system:**
- The **facts are NOT the product. The analysis is.** Every script must answer **"why does
  this matter / what does it mean for you / India / the world?"** in the creator's own framing.
- Ideation must **prefer under-covered angles** over headlines everyone already ran.
- Vary structure, hook, and pacing across reels — don't ship a visibly identical template
  every time (rotate Template N / A / C / D; vary B-roll and voice cadence).
- **You (the creative director) approve 4–5/day** — this human judgment is itself part of
  the "meaningful creative decisions" that the policy rewards. Use it: reject low-effort or
  duplicative ideas in the digest.

Sources: [invideo](https://invideo.io/blog/youtube-kills-ai-faceless-channels/) ·
[Medium breakdown](https://medium.com/@monkscript/the-faceless-youtube-playbook-just-broke-what-youtubes-2026-inauthentic-content-policy-says-eaebb0e62746) ·
[compliance playbook](https://alici.ai/blog/youtube-ai-monetization-compliance-2026)

---

## 2. AI-content disclosure (required)

- YouTube requires disclosure of **realistic** synthetic/altered content and auto-detects it
  (SynthID / C2PA). For sensitive topics (elections, health, finance, major news) it may add
  a **prominent on-player label**.
- **India:** platforms must label/remove flagged AI content within **3 hours** of notice.
- **Our exposure is low by design:** we use **illustrative visuals** — AI-generated B-roll
  (Cloudflare Flux, symbolic/conceptual stand-ins) and CC0 stock — plus captions + synthetic
  *voiceover*. **Never** fake photoreal footage of real, named people or specific real events
  presented as real. AI images stay abstract/symbolic (e.g. "a stylized digital rupee", not a
  fabricated photo of a named official). That's the safe side of the line.
- **Still, we disclose:** set the "altered/synthetic content" flag on upload (Module 9), add a
  description line (e.g. "Narration and visuals are AI-generated/illustrative; sources linked
  above"), **and burn an on-screen "Source: <domain>" citation** into the first seconds of the
  reel (Module 7). Honesty here protects the channel.

Sources: [YouTube disclosure](https://blog.youtube/news-and-events/disclosing-ai-generated-content/) ·
[India AI labeling](https://www.truefan.ai/blogs/youtube-ai-labeling-policy-india)

---

## 3. Copyright — never trip a strike

- **Never use broadcaster/news-agency footage** (Reuters, AP, ANI, NDTV, etc.) or copyrighted
  clips. AI summaries of news articles are also under active copyright litigation in 2026 —
  so **rewrite in your own words + cite**, never copy phrasing.
- **Narration + original analysis is the primary asset; B-roll is secondary/supporting** — this
  is what makes it commentary/documentary rather than a re-upload.
- Use **AI-generated illustrative B-roll** (Cloudflare Flux, symbolic stand-ins) and **Pexels/Pixabay
  (CC0)** clips, plus **maps, charts, and data visualizations** (great for impact stories and
  inherently safer). Generated images are owned/illustrative — never broadcaster footage.
- **High edit density:** never let a clip run >5–8s without a cut/transition. Helps retention
  *and* defeats automated copy-detection.
- Background music must be royalty-free.

Source: [fair-use guide 2026](https://joyspace.ai/copyright-proof-shorts-fair-use-ai)

---

## 4. Accuracy & trust (a news channel lives or dies on this)

- **Two-source minimum** for any claim before it becomes a reel; Claude must capture source
  URLs in the idea row.
- **Neutral, factual framing.** No sensationalism, no unverified rumor, no "BREAKING" bait.
- **Cite the source** out loud and in the caption ("according to …").
- Prefer **established developments** over fast-moving rumors (the "daily explainer" cadence
  intentionally avoids the breaking-news accuracy trap).
- If a story can't be verified, the digest skips it — better no reel than a wrong one.

---

## 5. What replaced the tone filter: an evidence gate

**Truth over neutrality (2026-07-27).** The soft/positive lean and the "never take sides" rule
are both retired. A well-sourced conclusion is not bias, and hedging a clear finding into mush
is its own kind of dishonesty. The channel may say plainly what the evidence supports.

**The trade is strict: the sharper the verdict, the more certain its facts must be.** That is
enforced in code, not merely requested in a prompt:

| Stage | Guard |
|---|---|
| Ideation | ≥ `MIN_SOURCES` (2) independent real URLs per idea |
| Scriptwriter | writes web-grounded; every load-bearing claim must be checkable |
| **Fact check** | [`src/factcheck.py`](../src/factcheck.py) re-checks the FINISHED script against live search **before it is voiced**. Unsupported claim → the reel is **blocked** and the idea marked `rejected`. **"Cannot verify" counts as unsupported.** |
| Approval | you still make the final call in the Telegram digest |

The fact check is deliberately a **separate, adversarial pass** with its own prompt — the
scriptwriter grounding its own output is a model marking its own homework. It is told to ignore
tone entirely: a harsh verdict the evidence supports is fine; a mild claim it cannot source is not.

⚠️ Grounded search shares one free-tier bucket (~20/day) with ideation and the scriptwriter. If
that is exhausted the gate **cannot run** — by default the reel ships unverified with a loud log
line; set `FACTCHECK_STRICT=true` to block instead.

**Still auto-excluded** (widened what may be *said*, not what may be *targeted*):
- Communal/religious incitement or hate; anything that could inflame violence.
- Unverified claims stated as fact; deepfakes/impersonation.
- Graphic tragedy exploitation; medical/financial advice stated as fact.

---

## 6. How this shapes the pipeline modules

| Module | News-niche requirement |
|--------|------------------------|
| **1 Ideation (Claude)** | Research today's developments in the lane; prefer high-impact under-covered angles; capture **source URLs**; apply the sensitivity filter; output `{title, hook, angle, est_score, sources}`. |
| **2 Approval** | Digest shows the source link per idea so you can sanity-check before approving. |
| **3 Scriptwriter** | Template N; **rewrite facts in own words + cite**; the core of the script is **original "why it matters" analysis**; neutral framing. |
| **5 Visuals** | AI-generated illustrative B-roll (symbolic stand-ins) + CC0 stock + maps/charts/data viz; **no broadcaster footage**; AI images stay abstract, never photoreal fakes of real people/events; high edit density. |
| **7 Subtitles** | Burn an on-screen **"Source: <domain>"** citation in the first seconds (reinforces sourcing on-screen). |
| **9 Publish** | Set the **AI-disclosure / synthetic-content flag**; description includes sources + disclosure line; `#Shorts`. |
| **10 Analytics** | Track which *angles/sub-lanes* retain best to sharpen future ideation. |

---

## 7. Monetization path (context)

YPP eligibility (2026): **1,000 subs + 4,000 watch-hours** (long-form, 12 mo) **OR
1,000 subs + 10M Shorts views** (90 days). The originality rules above are what keep you
*eligible* once you reach the threshold — build them in from reel #1, not later.

Source: [monetization 2026](https://miraflow.ai/blog/can-you-monetize-faceless-youtube-channels-ai-2026)
