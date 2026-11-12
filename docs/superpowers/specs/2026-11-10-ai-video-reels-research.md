# Research notes: Shorts reach, and prompts for the image and video models

**Date:** 2026-11-10
**Used by:** [2026-11-10-ai-video-reels-design.md](2026-11-10-ai-video-reels-design.md)

Two web-research passes run on 2026-11-10, kept here so the evidence behind the design stays with
it. Help Center pages are undated and are cited as read on that day. Each claim carries its
source number and how strong the evidence is. Where nothing reliable was found, the note says so.

Evidence labels: **official** (YouTube, Google, the model maker), **data study** (sample size
given), **host docs** (an API host's documentation), **practitioner**, **inference** (the
researcher's own reading, not a source).

---

## Part 1: what raises reach for Shorts

**Headline:** YouTube's documentation says Shorts are ranked on whether viewers choose to watch,
how long they stay and whether they were satisfied. Hashtags, tags and `#shorts` are officially
minor. The levers with evidence behind them are the first seconds, retention, topic demand and
more distinct attempts. The main risk for this channel is reading as templated AI output as it
scales.

Two sources could not be opened: The Hollywood Reporter (paywall) and MediaPost (HTTP 403).

### 1.1 Changes ranked by likely effect

| # | Change | Evidence | Strength |
|---|---|---|---|
| 1 | **Hook.** Open on the consequence or surprise within 1-2 seconds; the banner states that claim; voice and motion start at frame 0. | YouTube ranks on "% of viewers who chose to view" [3]. Shorts under 60% stayed-to-watch rarely performed; the best sat at 70-90% [33]. | Official; data study (5,400 Shorts, 2023) |
| 2 | **Retention.** The shortest script that still lands "why it matters"; no intro, no sign-off. | Average view duration and average % viewed inform ranking [3]. Best length in 2026 and loop tricks: no good evidence found, so keep 25-35 s. | Official |
| 3 | **Topic demand.** Score ideas against Studio's Trends tab [16] and Google Trends "Trending now" [25]. The Trending page is gone [47]. | YouTube lists topic interest and competition as reach factors [3]. | Official; effect unmeasured |
| 4 | **One audience.** New channels are matched to viewers by topic; YouTube's discovery lead advises aligning a channel with one audience [29]. India politics plus world science looks like two. | The "two audiences" reading is an inference. | Official statement; no data |
| 5 | **Feedback loop.** Steer by engaged views, stayed-to-watch and average % viewed per Short; public views now count every start and replay [5][6]. Rotate hook styles and compare. | | Official |
| 6 | **Volume.** In 367,243 new Shorts channels, views did not rise from upload 1 to 10, but the best of ten got about 6.5x the first [36]. Among channels over 1,000 subscribers, 12+ uploads a month went with 4.1x the view growth of under one [35]. | YouTube sets no minimum cadence [3] and says low-quality volume hurts [27]. Add output only while each Short stays distinct. | Data studies, correlational; official |
| 7 | **Speed on news.** Hour of day fades to a few percent by day 30, less so for News & Politics [37]; YouTube sees no long-term effect of publish time [8]. India timing: no good evidence found. | | Data study (40.2M US long-form videos, Shorts not split out); official |
| 8 | **Title and description.** Main 1-2 keywords first and an accurate title; a unique description repeating them in its first lines, then sources and the AI line [9]. | Search matches title, description and content [10], but was about 9% of views against 61% from the Shorts feed in one sample [34]. Google Search traffic to Shorts: no good evidence found. | Official; modest upside |
| 9 | **Captions and banner.** Keep them inside the safe area in 1.2. Captions raising views: no good evidence found. | | Official ad spec |
| 10 | **Hashtags.** One to three specific topic or event hashtags; drop `#shorts` and generic ones. | "Not required" [27]; Shorts with hashtags had about 10% fewer views and 9% more engagement [34]. | Official statement; data study, correlational |
| 11 | **Tags.** Alternate spellings only. | Tags play "a minimal role" [2]. | Official |
| 12 | **Language.** Leave auto-dubbing on and check the Hindi track [18][32]. Hindi or Hinglish versus English reach: no good evidence found. | | Official; benefit unmeasured |
| 13 | **No engagement bait.** | Likes, comments and shares showed no strong link to views [33]. Calls to action and pinned comments: no good evidence found. | Data study; otherwise thin |

### 1.2 Exact numbers

| Item | Number | Source |
|---|---|---|
| Title | 100 characters maximum | [4] official |
| Description | 5,000 characters maximum | [9] official |
| Hashtags | More than 60 and all are ignored; up to 3 shown by the title | [1] official |
| Short | Square or vertical, up to 3 minutes; over 1 minute with a copyright claim is blocked | [11] official |
| View | Each start or replay, no minimum watch time (Shorts from 2025-03-31, all formats from 2026-08-24) | [4][5] official |
| Engaged view | Stayed past "the initial seconds", loops excluded; the seconds are not published; Partner Program earnings use it | [5][6] official |
| Stayed to watch | Under 60% rarely performed; best 70-90% | [33] data study, 2023 |
| Safe area, 1080x1920 | Keep clear: top 288 px, bottom 672 px, right 192 px, left 48 px. Safe box 840x960 at x 48-888, y 288-1248 | [20] official, vertical ads overlay |
| Looser Shorts-ads rule | Avoid top 10% (192 px), bottom 25% (480 px), right 10% (108 px) | [21] official, ads |
| New Shorts channels | Median Short about 1,300 views at 30 days; 56.6% reach 1,000 | [36] data study |
| Cadence | Per-Short average peaks at 2-4 a week | [34] data study |

No official safe area for organic Shorts was found, and no official retention or stayed-to-watch
target. Vendor figures such as "70-85% retention" have no stated method.

### 1.3 Myths, or claims with no support

- "`#shorts` is required." Classification is by aspect ratio and length [11]; hashtags are "not required" [27].
- "15 hashtags maximum." The Help page now says 60 [1]; neither is a target.
- "Tags drive discovery." Official: minimal [2].
- "Post daily, never take a break, hit the right hour." YouTube found no such correlation [8].
- "Delete and re-upload a flop." YouTube's Shorts lead advises against it [27].
- "An AI label cuts reach." YouTube says it does not [14].
- "Faceless or AI voice is banned." The policy is tool-agnostic [30]; reports of faceless demonetisation are anecdotal [44].
- "80% at 3 seconds", "captions add 40%". Vendor figures with no method.
- "Shorts die after 30 days." A self-described working theory [46]; other data shows late spikes [39].
- "Shadowbans" and "the first hour decides." Both rejected by YouTube staff [30][29].

### 1.4 Policy risks for an AI-voiced, AI-visual news channel

- **Inauthentic content (channel-wide, Partner Program).** Templated, mass-produced AI content
  without original insight cannot monetise, nor can readings of news feeds [12]. Reviewers sample
  the main theme, top and newest videos, metadata and the About page [12]. What reduces it: real
  analysis in every script, varied structure and visuals, a stated human review, and scaling
  slowly. Google's published detector keys on shared templates and non-human posting frequency
  (130,000 channels in six months; not confirmed as the live system) [45].
- **AI personas on sensitive topics (July 2026 guidance).** An AI persona posing as a human
  expert on health, law, finance or politics cannot monetise [12][41]. Whether a faceless
  narrator counts is unstated. What reduces it: no avatar or named expert, no advice, and
  attribution for every claim.
- **Disclosure.** Realistic AI of real people, events or places must be disclosed. Since May 2026
  YouTube auto-labels photoreal AI, as an overlay on Shorts. Labels do not change reach or pay;
  repeated non-disclosure risks suspension from the Partner Program [13][14]. What reduces it:
  keep the flag on, favour plainly illustrative visuals, no AI likeness of real people (officials
  and journalists can request removal [23]) and no realistic fake disasters [12].
- **Ad suitability.** Non-graphic coverage of controversial issues is monetisable since January
  2026; exploiting a sensitive event is not [15].
- **News authority.** YouTube raises established outlets on news queries [22][10], so the feed,
  not search, will carry breaking stories.
- **Enforcement so far** hit mass AI channels: 16 removed or wiped in January 2026 with 4.7
  billion views [44]; counts vary by outlet [43].

### 1.5 Sources

**Official (YouTube and Google; Help pages undated, read 2026-11-10)**

1. [YouTube Help: hashtags](https://support.google.com/youtube/answer/6390658). Over 60 hashtags are all ignored; up to three show by the title; unrelated hashtags can get a video removed.
2. [YouTube Help: tags](https://support.google.com/youtube/answer/146402). Tags play "a minimal role"; useful for common misspellings.
3. [YouTube Help: search and discovery tips, Shorts](https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts). Ranking uses watch versus skip versus "not interested", % who chose to view, average view duration, average % viewed, likes and post-watch surveys; no minimum cadence.
4. [YouTube Help: get started creating Shorts](https://support.google.com/youtube/answer/10059070). Title maximum 100 characters; Shorts views redefined from 2025-03-31.
5. [YouTube Help: how engagement metrics are counted](https://support.google.com/youtube/answer/2991785). From 2026-08-24 views count at start of play in all formats; Partner Program earnings still use engaged views.
6. [YouTube Help: content reach and engagement](https://support.google.com/youtube/answer/12220281). Definitions of "Stayed to watch", engaged views (loops excluded) and average percentage viewed.
7. [YouTube Help: content performance and the recommendation system](https://support.google.com/youtube/answer/16559650). "The initial seconds" decide whether viewers stay.
8. [YouTube Help: performance FAQ](https://support.google.com/youtube/answer/141805). No need to upload daily; breaks and publish time show no long-term effect; tags "not important".
9. [YouTube Help: title tips](https://support.google.com/youtube/answer/12340300) and [description tips](https://support.google.com/youtube/answer/12948449). Most important words first; 1-2 main keywords in both; unique descriptions; 5,000-character limit.
10. [YouTube Help: how search works](https://support.google.com/youtube/answer/16090438). Relevance (title, tags, description, content), engagement, and channel authoritativeness.
11. [YouTube Help: three-minute Shorts](https://support.google.com/youtube/answer/15424877). Square or vertical up to 3 minutes is a Short; over 1 minute with a copyright claim is blocked.
12. [YouTube Help: channel monetization policies](https://support.google.com/youtube/answer/1311392). Notice dated 2025-07-15 renames "repetitious" to "inauthentic" content; current text covers generic or repetitive content, reused content, and AI personas on sensitive topics.
13. [YouTube Help: disclosing altered or synthetic content](https://support.google.com/youtube/answer/14328491). What needs disclosure; scripts, captions and unrealistic visuals do not; generic text-to-speech narration is not addressed; penalties for repeated non-disclosure.
14. [YouTube Blog: improving AI labels](https://blog.youtube/news-and-events/improving-ai-labels-viewers-creators/), 2026-05-27. Automatic labels for photoreal AI, overlay on Shorts; a label "alone does not change" recommendation or earnings.
15. [YouTube Help: advertiser-friendly guidelines update log](https://support.google.com/youtube/answer/9725604). January 2026 relaxation for non-graphic controversial issues; August and October 2026 news and public-interest clarifications.
16. [YouTube Help: Trends tab](https://support.google.com/youtube/answer/11962757) and [Inspiration tab](https://support.google.com/youtube/answer/15575509). Trends cards including content gaps for Shorts; Inspiration tab deprecated from August 2026 in favour of Ask Studio.
17. [YouTube Blog: Made on YouTube](https://blog.youtube/news-and-events/made-on-youtube-new-tools-power-creation-journey/), 2026-09-23. Ask Studio draft feedback; A/B testing of up to three cuts for hooks "coming soon".
18. [YouTube Blog: auto dubbing](https://blog.youtube/news-and-events/youtube-auto-dubbing-expressive-speech/), 2026-02-04, and [Help: automatic dubbing](https://support.google.com/youtube/answer/15569972). 27 languages; Expressive Speech in 8 including Hindi; "no negative impact" on the original's discovery.
19. [YouTube Blog: multi-language audio](https://blog.youtube/news-and-events/multi-language-audio/), 2025-09-10. Creators with uploaded dubs saw over 25% of watch time from non-primary languages; Shorts not mentioned.
20. [Google Ads Help: video ad specs](https://support.google.com/google-ads/answer/13547298) and [vertical safe-zone overlay](https://services.google.com/fh/files/misc/youtubesafezoneoverlay_vertical_final.png). The 288/672/192/48 px margins, read from the image.
21. [Google: YouTube Shorts ads](https://business.google.com/us/ad-solutions/youtube-ads/shorts-ads/). Avoid top 10%, bottom 25%, right 10%; calls Shorts a "sound-on environment".
22. [YouTube Blog: the Four Rs, part 2](https://blog.youtube/inside-youtube/the-four-rs-of-responsibility-raise-and-reduce/), 2019-12-03. Authoritative outlets raised for news queries. Old.
23. [YouTube Blog: likeness detection for civic leaders and journalists](https://blog.youtube/news-and-events/expanding-likeness-detection-civic-leaders-journalists/), 2026-03-10. Enrolled officials, candidates and journalists can request removal of AI likenesses.
24. [YouTube Blog: CEO letter 2026](https://blog.youtube/inside-youtube/the-future-of-youtube-2026/), 2026-01-21. Pledge to reduce "low quality AI content"; 200 billion daily Shorts views.
25. [Google Trends Help: Trending now](https://support.google.com/trends/answer/3076011). Surging news-linked queries, refreshed about every ten minutes, CSV and RSS export.
26. [YouTube Help: sharing links](https://support.google.com/youtube/answer/13748639). URLs in Shorts descriptions and comments are not clickable.

**Official statements reported second-hand**

27. [Social Media Today on Todd Sherman, Shorts product lead](https://www.socialmediatoday.com/news/youtube-shares-advice-for-shorts-creators-including-notes-on-hashtags-the/691835/), 2023-08-24. Hashtags not required, useful for events; volume neither boosts nor cuts reach; do not delete and re-upload. Old.
28. [Search Engine Journal on a Creator Insider Q&A](https://www.searchenginejournal.com/youtube-shorts-algorithm-explained-in-qa-format/459513/), 2022-07-29. "Every Short is given a chance" regardless of channel size. Old.
29. [PPC Land on Todd Beaupré with Rene Ritchie, Creator Insider 2026-09-01](https://ppc.land/subscribers-skip-90-of-uploads-in-their-feed-youtube-director-says/) ([video](https://www.youtube.com/watch?v=rHLjxrbXmmY)). New channels matched on topic; "align channels with audiences"; no single metric decides.
30. [vidIQ TubeTalk with Rene Ritchie](https://www.buzzsprout.com/271511/episodes/18630508-shadow-banning-inauthentic-content-and-dislikes-with-youtube-s-rene-ritchie), 2026-02-16. Inauthentic content "doesn't apply specifically to AI"; faceless formats not penalised; labels unknown to the discovery system.
31. [PPC Land on Creator Insider, 2026-07-03](https://ppc.land/youtube-kills-shorts-dislike-button-adds-2x-speed-and-mute-today/), 2026-07-05. Shorts dislike button retired; "not interested" kept; mute and 2x speed added.
32. [Social Media Today on auto-dubbing](https://www.socialmediatoday.com/news/youtube-expands-auto-dubbing-dream-screen-inspiration-tab/751554/), 2025-06-24. "All new content, both shorts and VODs" dubbed on upload.

**Data studies (sample size given)**

33. [Paddy Galloway thread](https://threadreaderapp.com/thread/1646898356419981315.html), 2023-04-14. 33 channels, 5,400 Shorts, 3.3 billion views. Stayed-to-watch thresholds; no strong link between likes, comments, shares and views. Old.
34. [Metricool: YouTube Trends 2026](https://metricool.com/youtube-trends/), 2026-07-29. 799,718 videos, 71,177 accounts; vendor. Its year-on-year Shorts figures do not address the view redefinition, so treat them as inflated (inference).
35. [vidIQ: upload frequency study](https://vidiq.com/research/youtube-upload-frequency-study/), 2026-07-08. 10,210,278 channels with 1,000+ subscribers; correlational.
36. [vidIQ: first 10 videos study](https://vidiq.com/research/youtube-first-10-videos-study/), 2026-07-28. 448,413 new channels (367,243 Shorts); a selected cohort that posted at least 10 times in 90 days.
37. [vidIQ: best time to publish](https://vidiq.com/blog/post/best-time-publish-video-youtube/), updated 2026-06-23. 40.2M US long-form uploads; Shorts not split out.
38. [Buffer: best time to post on YouTube](https://buffer.com/resources/best-time-to-post-on-youtube/), 2026-07-24. About 1.8M videos; no effect size.
39. [Socialinsider: how long Shorts take to get views](https://www.socialinsider.io/blog/how-long-does-it-take-for-yt-shorts-to-get-views/), 2026-01-27, updated 2026-11-06. Largest view window was days 25-30; sample counts are internally inconsistent.
40. [Kapwing: AI slop report](https://www.kapwing.com/blog/ai-slop-report-the-global-rise-of-low-quality-ai-videos/), 2025-11-28. 104 of the first 500 Shorts shown to one new account were AI-generated; vendor, single account.

**Reporting and expert opinion**

41. [Tubefilter: inauthentic content guidance update](https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/), 2026-07-13. Guidance split into three categories; described as a clarification, not a new policy.
42. [TechCrunch: automatic AI labels](https://techcrunch.com/2026/05/27/youtube-will-now-automatically-label-ai-videos/), 2026-05-27. Corroborates [14].
43. [Tubefilter: slop channel bans](https://www.tubefilter.com/2026/01/29/youtube-ai-slop-channel-crackdown-bans/), 2026-01-29. At least 18 channels deleted or hidden per Kapwing.
44. [The Next Web: faceless creators as collateral damage](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage), 2026-06-15. 16 channels, 35M subscribers, 4.7B views removed in January 2026; faceless demonetisation claims are creator anecdotes.
45. [Fstoppers on Google's detection paper](https://fstoppers.com/artificial-intelligence/how-google-machine-terminated-130000-ai-slop-youtube-channels-six-months-903645), 2026-07-19. 50,000 clusters and 130,000 channels in six months; a research paper, not confirmed as YouTube's live system.
46. [Search Engine Journal](https://www.searchenginejournal.com/youtube-shorts-algorithm-may-now-favor-fresh-over-evergreen/562661/) and [Tubefilter](https://www.tubefilter.com/2025/12/05/youtube-shorts-algorithm-change-new-uploads/) on Mario Joos, 2025-12-05. Claim that Shorts older than about 30 days lost distribution; seven anonymous channels; unconfirmed by YouTube.
47. [TechCrunch: Trending page removed](https://techcrunch.com/2025/07/10/youtube-is-getting-rid-of-its-trending-page-and-trending-now-list), 2025-07-10. Replaced by category Charts, Explore and personalised recommendations.
48. [Tubefilter: search filters](https://www.tubefilter.com/2026/01/09/youtube-search-filters-shorts-vs-long-form/), 2026-01-09. Search gained a "Shorts" type filter.

---

## Part 2: prompts for FLUX.2 klein stills and Kling 2.5 Turbo image-to-video

Limits of this evidence:

- Black Forest Labs' klein-specific guide now returns 404 and its live prompting docs target a
  newer model. The klein rules below survive in its Prompt Reference and help centre.
- Kling has no official 2.5 Turbo prompt guide and publishes no word-count guidance. Its guides
  are version-agnostic (November 2025) or written for Kling 3.0 (2026).
- Kling's API reference is JavaScript-rendered and would not load; its field text was read
  through host mirrors.
- The researcher assumed fal.ai as the Kling host and quoted fal's price ($0.21 per 5-second
  clip). This pipeline calls Kling through Higgsfield, where the live quote on 2026-11-10 was
  $0.179. Prompt guidance carries over; the price does not.

### 2.1 FLUX.2 klein 4B stills

1. **Prose, not tag lists.** Klein has no prompt upsampling: "What you write is exactly what the model receives." [P1][P3][P4] official
2. **Subject and action first**, then setting, light, framing: "FLUX.2 pays more attention to what comes first." [P2] official (pro/max guide)
3. **Name the light:** source, direction, softness. [P1] official
4. **End with `Style: ... Mood: ...`** to hold one look across shots. [P1] official
5. **60 to 100 words.** Black Forest Labs calls 30 to 80 "usually ideal" [P2]; klein testers report 40 to 120 [P11].
6. **No negative prompts:** neither endpoint has the field [P8][P9]. Describe the wanted state, as the maker's "empty scene" replaces "no people" [P2]. Never quote a string, and avoid nouns that imply lettering, such as sign or poster (inference).
7. **Colour:** hex codes work when tied to an object, for example "hull in color #C9CED6". [P4][P5] official
8. **Composition:** write "centered composition" plus shot size and angle [P10][P11]. Keeping areas empty: no reliable guidance found; describe those bands as simple content (inference).

Structured (JSON) prompting: no klein-specific guidance found; the maker lists it under pro/max
and tells klein users to write prose [P1][P5].

Weaknesses of the 4B model: unreliable text; prompt-following "heavily influenced by the
prompting style" [P6]; inconsistent detail in busy scenes [P12]; extra limbs in complex poses
(unverified). Use one hero subject and keep any figures distant and silhouetted (inference).

Template:

```
{Subject, 2-3 visual details} {action, setting}, centered in the middle of the frame, {shot size} from {angle}. {Light: source, direction, softness}. The top and lower third of the frame are {simple content}. All surfaces are plain and unmarked. Style: cinematic 3D animated film still, stylized shapes, {finish}. Mood: {mood}.
```

Example:

```
A small deep-space probe with a wide white dish and a gold-foil body drifts through interstellar space, centered in the middle of the frame, medium-wide shot from slightly below. A distant star at upper left throws warm, hard-edged light along one edge of the dish. The top and lower third of the frame are empty dark space with sparse dim stars. All surfaces are plain and unmarked. Style: cinematic 3D animated film still, stylized shapes, rich saturated color. Mood: quiet, vast, lonely.
```

### 2.2 Kling 2.5 Turbo image-to-video

1. **Motion only, in one to three short sentences:** "Subject + Movement, Background + Movement". The still already supplies the scene. [P13][P14] official
2. **One named physical motion**, at most one supporting motion, and say what stays still. "Make it come alive" gives the model nothing to animate. [P14][P16] official
3. **Stay inside the picture:** "A description that significantly deviates from the image may cause a camera cut or transition." [P13] official
4. **State the camera, one move per shot.** Start with "static camera" or "camera locked off"; then push in, pull back, pan, tilt or orbit, with "slow, stable, no sudden motion". [P14][P15] official (Kling 3.0-era); a host says 2.5 Turbo follows such moves more reliably than earlier versions [P19]
5. **2.5 Turbo specifics:** its maker claims better multi-step instruction following, closer retention of the still's colour and light, and larger motion and camera amplitude [P17]. Ask for subtlety explicitly (inference).
6. **`negative_prompt` and `cfg_scale`:** no controlled test on 2.5 Turbo was found for either. Kling's own field text recommends "negative sentences directly within positive prompts" [P18], so put constraints in the prompt. Keep `cfg_scale` at the 0.5 default; hosts suggest 0.3 to 0.7 but show no tests [P19][P22].

Negative prompt (unverified; a host default plus practitioner lists [P20][P21], minus
"cartoonish", which describes this channel's look):

```
blur, distortion, low quality, morphing, warping, flicker, jitter, camera shake, scene change, text, watermark, logo
```

Template:

```
{Subject} {one slow motion}. [{Background element} {one slow motion}.] {Static camera | Slow, stable push in}, no sudden motion, no cuts. {Subject} keeps its exact shape and colors; everything else stays still.
```

Example:

```
The probe rotates very slowly, a few degrees, as light slides along the edge of its dish. Slow, stable push in, no sudden motion, no cuts. The probe keeps its exact shape and colors; the stars stay fixed.
```

### 2.3 Parameters not in use

- Cloudflare's endpoint accepts `prompt`, `width` and `height` (256 to 1920), `seed`, `guidance` and `input_image_0` to `3`; steps are fixed at 4 [P9].
- `guidance` has no documented default or range and is probably inert: the reference pipeline says it "is ignored" for step-distilled models [P7].
- Reference images (each under 512x512) [P9]: one approved still could anchor the style of every shot (inference; untested here).

### 2.4 Sources (accessed 2026-11-10)

- P1. Official. Black Forest Labs Prompt Reference, FLUX.2 [klein] section. https://docs.bfl.ai/guides/prompting_unified_reference.md
- P2. Official. "Prompting Guide - FLUX.2 [pro] & [max]". https://docs.bfl.ai/guides/prompting_guide_flux2 (does not mention klein)
- P3. Official. FLUX.2 overview. https://docs.bfl.ai/flux_2/flux2_overview.md
- P4. Official. Help centre, "How do I generate quickly with FLUX.2 [klein]?" https://help.bfl.ai/articles/7592221790-how-do-i-generate-quickly-with-flux-2-klein
- P5. Official. Hex colour and JSON guides. https://docs.bfl.ai/guides/usecases_t2i_hex_color_prompting.md and https://docs.bfl.ai/guides/usecases_t2i_json_prompting.md
- P6. Official. Hugging Face model card, FLUX.2-klein-4B, Limitations. https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- P7. Reference code. Hugging Face diffusers, `pipeline_flux2_klein.py`. https://raw.githubusercontent.com/huggingface/diffusers/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py
- P8. Official. API reference, `flux-2-klein-4b`. https://docs.bfl.ai/api-reference/models/generate-or-edit-an-image-with-flux2-[klein]-4b.md
- P9. Official. Cloudflare changelog, FLUX.2 [klein] 4B on Workers AI, 2026-01-15. https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
- P10. Practitioner. fal, "Flux 2 [klein] Prompt Guide", 2026-01-16. https://fal.ai/learn/devs/flux-2-klein-prompt-guide (its `negative_prompt` and `guidance_scale` advice does not apply to Cloudflare's distilled endpoint)
- P11. Practitioner with outputs. deAPI, "Prompting FLUX.2 Klein: What Works, What Doesn't, and Why", 2026-04-29. https://deapi.ai/blog/prompting-flux-2-klein-what-works-what-doesnt-and-why
- P12. Practitioner with outputs. Everypixel Journal, "FLUX.2 Klein OR FLUX.2 Pro?", 2026-04-03. https://journal.everypixel.com/?p=2077
- P13. Official. Kling "Image-to-Video" guide, 2025-11-24. https://kling.ai/quickstart/image-to-video-guide
- P14. Official. Kling image-to-video prompts page, 2026-07-10. https://kling.ai/topics/image-to-video-prompts
- P15. Official. Kling blog, "Camera Control: Master Push, Pull, Pan & Tilt", 2026-08-13. https://kling.ai/blog/kling-ai-camera-control-video-guide
- P16. Official. Kling blog on animating a picture, 2026-09-30. https://kling.ai/blog/how-to-animate-a-picture
- P17. Official, promotional. Kuaishou press release, "Kling AI Launches 2.5 Turbo Video Model", 2025-09-29. https://mrem.bernama.com/viewsm.php?idm=52282
- P18. Host docs. Kling API field descriptions as reproduced by hosts. https://docs.comfy.org/development/comfy-router/models/kling/kling-v2-5-turbo/code.md and https://docs.gmicloud.ai/model-quickstarts/video/kling-v2-5-turbo.md
- P19. Host docs. fal Kling 2.5 Turbo pages. https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/standard/image-to-video/llms.txt and https://blog.fal.ai/kling-2-5-turbo-is-now-available-on-fal/
- P20. Practitioner. VEED, "Kling 2.5 Turbo Prompting Guide", 2026-07-29. https://www.veed.io/learn/kling-2-5-turbo-prompts
- P21. Practitioner. Akool, "Kling 2.5 Video Prompt Guide", updated 2026-10-28. https://akool.com/blog-posts/kling-2-5-video-prompt-guide
- P22. Host docs. WaveSpeed, Kling 2.6 Pro image-to-video docs (a different Kling version). https://wavespeed.ai/docs/docs-api/kwaivgi/kwaivgi-kling-v2.6-pro-image-to-video
