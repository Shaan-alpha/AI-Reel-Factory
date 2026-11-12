"""Sentence boundaries, shared by the scriptwriter, the voice and the subtitles.

Contract:
    what it does : splits narration into sentences, and says whether a word ends a clause.
    input        : plain text (English or Hinglish; inline delivery tags allowed).
    output       : list of sentences / a bool.
    depends on   : nothing but `re`.

Three copies of "a sentence ends at . ! ? followed by a space" lived in three modules, and all
three broke on "U.S." and on "...": the opening guard read "A U.S." as a whole first sentence and
failed 2 of the last 9 published scripts (audit 2026-11-10). None knew the Hindi full stop "।",
which every Hinglish line ends with. One definition now serves all three.
"""
from __future__ import annotations

import re

# A full stop after these is not a sentence end. "No" is deliberately absent: "Did it work? No."
# is a real one-word sentence in a narration.
_ABBREVIATIONS = ("U.S.A", "U.S", "U.K", "U.N", "E.U", "Dr", "Mr", "Mrs", "Ms", "St", "vs",
                  "Jr", "Sr", "Inc", "Ltd")

# A sentence end and the whitespace after it: `.`, `!`, `?`, `…` or `।`, any closing quotes or
# brackets, then space. Not after an abbreviation or a single capital initial ("J. Smith"), and
# not when the next word starts in lower case, which is how "ever... and it flopped" continues.
SENTENCE_END_RE = re.compile(
    "".join(rf"(?<!\b{re.escape(a)})" for a in _ABBREVIATIONS)
    + r"(?<!\b[A-Z])[.!?…।](?:[\"')\]]*)\s+(?![a-z])"
)

_CLAUSE_END_RE = re.compile(r"[.!?…।:;][\"')\]]*$")


def split_sentences(text: str) -> list[str]:
    """Sentences in order, stripped, empties dropped. A delivery tag after a sentence end stays
    with the sentence it introduces ("[pause] Here's why it matters.")."""
    out, last = [], 0
    for m in SENTENCE_END_RE.finditer(text or ""):
        out.append(text[last:m.end()].strip())
        last = m.end()
    out.append((text or "")[last:].strip())
    return [s for s in out if s]


def ends_clause(word: str) -> bool:
    """True if `word` closes a sentence or a clause (. ! ? … । : ;), so a caption may break
    after it. An abbreviation ("U.S.", "Dr.") or a single initial ("J.") does not."""
    w = (word or "").strip()
    if not _CLAUSE_END_RE.search(w):
        return False
    core = w.rstrip("\"')]").rstrip(".")
    return core not in _ABBREVIATIONS and not re.fullmatch(r"[A-Z]", core)
