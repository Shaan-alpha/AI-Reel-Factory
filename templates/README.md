# Script Templates

Reusable script structures (rule 16: use templates, not pure randomness). These files are the
design source for the scriptwriter's prompt. Only **Template N** is wired: its executable prompt
is embedded in [`src/scriptwriter.py`](../src/scriptwriter.py) (`_PROMPT_N`) and must be kept in
sync with [template-N-news-impact.md](template-N-news-impact.md). Asking the scriptwriter for any
other template raises an error. A, C and D are kept as design notes for a later phase.

| File | Template | When | Wired |
|------|----------|------|-------|
| [template-N-news-impact.md](template-N-news-impact.md) | **N — News Impact Explainer** | ⭐ every reel today | yes |
| [template-D-fast-listicle.md](template-D-fast-listicle.md) | D — Fast listicle | "3 things today that matter" round-ups | no |
| [template-A-problem-solution.md](template-A-problem-solution.md) | A — Hook→Problem→Solution→Twist→CTA | evergreen explainers | no |
| [template-C-story-loop.md](template-C-story-loop.md) | C — Story→Curiosity loop→Reveal | "how this unfolded" backstories | no |

> Template B (controversial statement) has no file. Add it only if it clears the playbook's
> sensitivity filter (docs/08 §5).

See [docs/05-content-system.md](../docs/05-content-system.md) and
[docs/08-news-niche-playbook.md](../docs/08-news-niche-playbook.md).
