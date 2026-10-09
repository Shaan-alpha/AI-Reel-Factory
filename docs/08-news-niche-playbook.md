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
> 2026 if followed blindly. Read this before changing ideation (Module 1), the scriptwriter (3),
> the fact-check gate (11) or publishing (9).

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
  The scriptwriter logs a warning when a script has no "why it matters" turn, or repeats the
  idea's angle word for word.
- Ideation must bring an **angle, not just a headline**: every idea carries its own "why it
  matters" take (`angle`), and the story scout spreads each run across different categories.
- Vary hook and pacing across reels so they don't look, sound and move the same. Only
  Template N is wired (§6), so the variety comes from each story's own hook and angle, AI images
  seeded per reel and shot with rotating compositions, a music bed picked per reel, the delivery
  tags in the read, and the calm read for tragedies.
- **You (the creative director) approve up to 3 ideas a run** (`APPROVAL_CAP`). This human
  judgment is itself part of the "meaningful creative decisions" that the policy rewards. Use it:
  reject low-effort or duplicative ideas in the digest.

Sources: [invideo](https://invideo.io/blog/youtube-kills-ai-faceless-channels/) ·
[Medium breakdown](https://medium.com/@monkscript/the-faceless-youtube-playbook-just-broke-what-youtubes-2026-inauthentic-content-policy-says-eaebb0e62746) ·
[compliance playbook](https://alici.ai/blog/youtube-ai-monetization-compliance-2026)

---

## 2. AI-content disclosure (required)

- YouTube requires disclosure of **realistic** synthetic/altered content and auto-detects it
  (SynthID / C2PA). For sensitive topics (elections, health, finance, major news) it may add
  a **prominent on-player label**.
- **India:** platforms must label/remove flagged AI content within **3 hours** of notice.
- **What is synthetic in our reels:** the narration (Gemini TTS, one male voice), the images
  (Cloudflare FLUX.2 klein illustrations under `VISUAL_SOURCE=ai`, the live setting) and the
  music (four beds generated with Google Lyria 2, SynthID-watermarked). A shot falls back to a
  Pexels photo, and a reel to Pexels/Pixabay stock video, only when image generation fails.
- **The image rule:** AI images are illustrations. **Never** fake photoreal footage of real,
  named people or specific real events presented as real. The default image style in
  `src/visuals.py` (`IMAGE_STYLE` overrides it) asks for a "symbolic and stylized" editorial
  illustration with "no recognizable real people", no text and no logos (e.g. "a stylized
  digital rupee", not a fabricated photo of a named official). Places the story names stay in
  the shot, and an India story is set in India, with rupees only in money shots. That's the safe
  side of the line.
- **We disclose on every reel**, in code rather than by asking the model:
  - YouTube's "altered or synthetic content" flag, `status.containsSyntheticMedia=true`, on
    every upload (`AI_DISCLOSURE`, default true; Module 9);
  - a disclosure line in its own paragraph of the description: **"AI-generated narration,
    images and music."** under `VISUAL_SOURCE=ai`, otherwise **"AI-generated narration and
    music; stock visuals."**;
  - an on-screen **"Source: <publisher>"** label for the first ~3 s (Module 7). It reads
    "Source: Google News" when the idea's only sources are Google News links.

  Honesty here protects the channel.

Sources: [YouTube disclosure](https://blog.youtube/news-and-events/disclosing-ai-generated-content/) ·
[India AI labeling](https://www.truefan.ai/blogs/youtube-ai-labeling-policy-india)

---

## 3. Copyright — never trip a strike

- **Never use broadcaster/news-agency footage** (Reuters, AP, ANI, NDTV, etc.) or copyrighted
  clips. AI summaries of news articles are also under active copyright litigation in 2026 —
  so **rewrite in your own words + cite**, never copy phrasing.
- **Narration + original analysis is the primary asset; B-roll is secondary/supporting** — this
  is what makes it commentary/documentary rather than a re-upload.
- Use **our own AI illustrations** (Cloudflare FLUX.2 klein, symbolic stand-ins) or
  **Pexels/Pixabay** stock. Generated images are ours and illustrative — never broadcaster
  footage. Maps, charts and data visualizations would be safe too, but nothing generates them
  today; maps appear only when the B-roll keywords ask for them.
- **The stock licences are not CC0** (checked 2026-09-28). The Pexels License and the Pixabay
  Content License are free for commercial use with no attribution, but Pexels says identifiable
  people "may not appear in a bad light", and Pixabay forbids misleading use "especially Content
  which features recognisable people". Keep faces out of stock B-roll on news stories: hands,
  silhouettes, distant crowds, places and objects (the keyword prompt in `src/visuals.py` asks for
  exactly that).
- **High edit density:** never let a clip run >5–8s without a cut/transition (assembly cuts
  every ~3.5 s, `CLIP_SECONDS`). Helps retention *and* defeats automated copy-detection.
- **Music:** the four beds in `assets/music` were generated for this channel with Google Lyria 2,
  so nobody else has registered them with Content ID. "Royalty-free" download sites are a
  Content ID gamble: the earlier Pixabay beds were claimed and deleted
  ([assets/music/README.md](../assets/music/README.md)).

Source: [fair-use guide 2026](https://joyspace.ai/copyright-proof-shorts-fair-use-ai)

---

## 4. Accuracy & trust (a news channel lives or dies on this)

- **Two-source minimum** before an idea reaches the digest. Ideation attaches at least
  `MIN_SOURCES` (2) live source URLs to every idea in code (grounded-search citations, then the
  news feed's article link, then a Google News search) and drops any link the publisher answers
  404/410 for. Two gaps remain, both open operator decisions (STATUS.md): the count is of URLs,
  not outlets (the search prefers different publishers but accepts one outlet twice rather than
  drop a true story), and URLs the model wrote itself count too if they pass the 404 probe.
- **Factual framing; a verdict only where the evidence supports it** (§5, truth over neutrality,
  2026-07-27). No sensationalism, no unverified rumor, no "BREAKING" bait.
- **Cite the source**, in code: the description carries one "Sources:" block built from the
  idea's fetched sources (up to three links: one per outlet, then Google News), and the reel shows
  "Source: <publisher>" on screen for its first ~3 s. The model writes no links: remembered URLs
  were often dead.
- Prefer **established developments** over fast-moving rumors (the "daily explainer" cadence
  intentionally avoids the breaking-news accuracy trap).
- If a story can't reach two live sources, it never reaches the digest — better no reel than a
  wrong one.

---

## 5. What replaced the tone filter: an evidence gate

**Truth over neutrality (2026-07-27).** The soft/positive lean and the "never take sides" rule
are both retired. A well-sourced conclusion is not bias, and hedging a clear finding into mush
is its own kind of dishonesty. The channel may say plainly what the evidence supports.

**The trade is strict: the sharper the verdict, the more certain its facts must be.** Most of
that is enforced in code rather than requested in a prompt; the table says which:

| Stage (run order) | Guard | Enforced by |
|---|---|---|
| Ideation | ≥ `MIN_SOURCES` (2) live source URLs per idea (§4 has the gaps); a story pitched in the last 10 days (`IDEA_DEDUP_DAYS`) is not pitched again | code |
| Approval | you approve the **idea** (title, hook, angle, sources) in the Telegram digest. You do not see the script: it is written, checked and published without a second look | you |
| Scriptwriter | writes with web grounding; told that every load-bearing claim must be checkable and that a verdict needs certain facts | prompt |
| **Fact check** | [`src/factcheck.py`](../src/factcheck.py) re-checks the FINISHED script, its title, its on-screen key-point cards and the description summary against live search **before it is voiced**. A **fabricated** claim blocks the reel (rules below) | code |

The fact check is deliberately a **separate, adversarial pass** with its own prompt — the
scriptwriter grounding its own output is a model marking its own homework. It is told to ignore
tone entirely: a harsh verdict the evidence supports is fine; a claim no source supports is not.

### How the gate runs (as of 2026-10-09)

- **Model:** Vertex AI with Google Search grounding, `FACTCHECK_MODEL` (default chain
  `gemini-3.5-flash,gemini-3.5-flash-lite`). Billed per token, about $0.003–0.004 a check, inside
  the ≤ $5/month cap; its searches count against Vertex's 5,000 free Gemini 3 grounding queries
  a month.
- **Two samples** (`FACTCHECK_SAMPLES`, default 2, range 1–3): the check runs twice,
  independently, and a blocking finding from either one blocks. One verdict varies from run to
  run (on 2026-09-27 the same script passed 2 runs of 5). If the second sample cannot run, the
  first decides.
- **One repair** (`ENABLE_FACTCHECK_REPAIR`, default true): on a block, a grounded rewrite of only
  the flagged sentences, then the same gate again. A pass ships the repaired script; a second
  block stands.
- **Blocked:** the idea's status becomes **`blocked`** (not `rejected`, which means the operator's
  own tap), story dedup keeps it out of digests for 10 days, and Telegram gets the blocking
  findings.
- **Strict hold:** `FACTCHECK_STRICT=true` is set as a repo variable (the code default is false).
  If the checker cannot run at all (an outage, or a reply still unreadable after one re-ask), the
  reel is held and its idea goes back to `pending` for the next digest. With strict off, the reel
  would ship unverified with a Telegram warning.
- **Record:** every verdict (blocking and waived findings, claims checked, whether a repair ran)
  is stored in `scripts.factcheck`.

### What blocks, and what doesn't (severity grading, 2026-08-07; tightened 2026-10-09)

The first version of the gate treated **every** discrepancy as fatal, including rounding, a date
off by a day, a figure two sources count differently, and anything one search pass simply failed
to surface ("absence of evidence is failure"). It blocked most ideas over differences that changed
nothing — which is its own failure mode: **a gate that stops everything protects nothing, it just
stops the channel.** Findings are now sorted, and only the first bucket blocks.

| Bucket | Meaning | Examples | Result |
|---|---|---|---|
| **Blocking** | the story is **false** | the event/ruling didn't happen; a named party credited or blamed for something they didn't do; an invented quote, law, court ruling, product, report or statistic; a number off by an order of magnitude, the wrong direction, or >~25%; a blame or causation claim **no** source supports | reel **blocked**, idea `blocked` |
| **Minor** | the story is **true but imprecise** | rounding; a figure that differs because sources count differently; a date off by a few days; wording, emphasis or over-confidence; a claim nothing contradicts but this pass couldn't confirm; sources disagreeing with each other; a detail that isn't load-bearing | **logged loudly, reel ships** |

Two rules decide most cases:

- **Contradiction blocks; non-confirmation does not.** "I could not find this" is minor. "I found
  that this is false" is blocking. One grounded pass missing a real story is common, and is not
  evidence that the story is false.
- **Two sources disagreeing does not make the script wrong.** Both can be wrong, both can be right,
  or they can be measuring different things. Only the **weight** of the evidence blocks.

The checker sorts its own findings, and code then checks the sorting against the checker's own
wording:

- **A "minor" finding the checker itself calls contradicted blocks** (since 2026-10-09; idea 211
  shipped one as minor). Wording such as "contradicted by", "is not true", "did not happen",
  "fabricated" or "does not exist" moves it to blocking.
- **"Could not confirm" is waived, with limits.** A blocking finding worded only as
  non-confirmation, with no word of contradiction, moves to minor. Since 2026-10-09 the waiver
  never covers a quote or statement, a court ruling, a law, or blame, cause, responsibility or
  attribution, nor a finding that says there is "no record" of something: that is how a checker
  reports an invented quote or ruling, so those still block. A statistic the checker merely could
  not confirm stays waived.
- **The findings outrank the verdict word:** "pass" with a blocking finding blocks; "fail" with
  only minor findings ships; "fail" that names nothing blocks.
- **An off-shape reply is asked again once** (no verdict object, or JSON that cannot be read).
  If it is still unusable, the checker counts as not having run (strict hold, above).

This loosens **precision, not the anti-fabrication spine** — the rule-6 trade ("the sharper the
verdict, the more certain its facts must be") is about invented facts and misplaced blame, and
those still block. Escape hatch: **`FACTCHECK_SEVERITY=any`** restores block-on-everything. If the
minor-issue count in the run logs starts climbing, that is the scriptwriter drifting — fix it
there, not by re-tightening the gate.

**Still excluded** (widened what may be *said*, not what may be *targeted*):
- Communal/religious incitement or hate; anything that could inflame violence.
- Unverified claims stated as fact; deepfakes/impersonation.
- Graphic tragedy exploitation; medical/financial advice stated as fact.

Apart from the fact-check gate, which blocks invented claims, these exclusions are **asked of the
models, not enforced in code**. Both ideation prompts list them, and the scriptwriter is told to
roast situations, never people. Only two pieces of code act on them: the **somber-tone detector**
(`scriptwriter.tone_for`), which catches stories about deaths or serious harm (killings, deadly
crashes, attacks, disasters) and switches them to a calm script, a calm read and no hook
punch-up, and the digest's **"⚠️ Sensitive"** flag on those same ideas. The script's tone and the
flag follow the idea's own words; the read and the punch-up also check the finished script.
Everything else rests on your tap in the digest.

---

## 6. How this shapes the pipeline modules

| Module | News-niche requirement |
|--------|------------------------|
| **1 Ideation** ([`src/ideation_fallback.py`](../src/ideation_fallback.py), Gemini on Vertex) | Pick distinct current stories from Google News and Trends; give each an honest hook and a "why it matters" angle; attach **≥ 2 live source URLs** in code (§4); the prompts carry the sensitivity filter (§5); output `{niche, title, hook, angle, est_score, sources}`. The Claude Routine in [`routines/ideation.md`](../routines/ideation.md) is optional and has never run in production. |
| **2 Approval** | The digest shows each idea's hook, angle and up to three source outlets as links, so you can sanity-check before approving, and flags deaths or serious harm as "⚠️ Sensitive". Up to 3 approvals a run. |
| **3 Scriptwriter** | Template N only; **rewrite facts in own words**; the core of the script is **original "why it matters" analysis**; a verdict only where the evidence supports it (§5); the channel's sarcasm targets situations, never people, and drops out entirely for somber stories. |
| **11 Fact check** | §5: two samples, one repair, idea `blocked` on fabrication, reel held under strict mode when the checker cannot run. |
| **5 Visuals** | Our own AI illustrations (no recognizable real people) or Pexels/Pixabay stock without identifiable faces; **no broadcaster footage**; AI images never photoreal fakes of real people/events; places named in the story kept; a cut every ~3.5 s. |
| **7 Subtitles** | Burn an on-screen **"Source: <publisher>"** citation for the first ~3 s. The frame-1 hook banner (the title) and the key-point cards are published claims, so the gate checks them too. |
| **9 Publish** | Set the **AI-disclosure / synthetic-content flag**; the description is summary + Sources block + disclosure line + brand footer + `#Shorts`. |
| **10 Analytics** | Daily view snapshots; the best and worst recent titles feed the ideation prompt. Retention is not pulled: nothing calls the YouTube Analytics API, and the token would first need the `yt-analytics.readonly` scope. |

---

## 7. Monetization path (context)

YPP eligibility (2026): **1,000 subs + 4,000 watch-hours** (long-form, 12 mo) **OR
1,000 subs + 10M Shorts views** (90 days). The originality rules above are what keep you
*eligible* once you reach the threshold — build them in from reel #1, not later.

Source: [monetization 2026](https://miraflow.ai/blog/can-you-monetize-faceless-youtube-channels-ai-2026)
