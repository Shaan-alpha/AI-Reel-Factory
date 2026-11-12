"""Sentence boundaries, shared by the scriptwriter, the voice and the subtitles.

Contract:
    what it does : splits narration into sentences, and says whether a word ends a clause.
    input        : plain text (English or Hinglish; inline delivery tags allowed).
    output       : list of sentences / sentence-end offsets / a bool.
    depends on   : nothing but `re`.

Three copies of "a sentence ends at . ! ? followed by a space" lived in three modules, and all
three broke on "U.S." and on "...": the opening guard read "A U.S." as a whole first sentence and
failed 2 of the last 9 published scripts (audit 2026-11-10). None knew the Hindi full stop "।",
which every Hinglish line ends with. One definition now serves all three.

A full stop after an abbreviation is ambiguous: "the U.S. President" goes on, "prices rose in the
U.S. Here's why" ends. So each candidate end is decided by the word before it and the word after.
"""
from __future__ import annotations

import re

# Before a name: a full stop after these never ends a sentence.
_NAME_TITLES = frozenset(("Dr", "Mr", "Mrs", "Ms", "Prof", "Gen", "Lt", "Col", "Sgt", "St",
                          "Jr", "Sr", "vs"))
# Before a number ("Rs. 500", "No. 5"): no sentence end. "Did it work? No. It failed." still
# ends, because "It" is not a number.
_NUMBER_ABBREVIATIONS = frozenset(("Rs", "No"))
# These end a sentence only when a sentence plainly starts after them: "the U.S. President spoke"
# goes on, "prices rose in the U.S. Here's why" ends. A single capital initial behaves the same
# way ("J. Smith" goes on, "Plan B. The rest failed." ends).
_PLACE_ABBREVIATIONS = frozenset(("U.S.A", "U.S", "U.K", "U.N", "E.U", "Inc", "Ltd"))
_SENTENCE_STARTERS = frozenset((
    "The This That These Those It It's Its There There's Here Here's But And So Now Then Yet "
    "Still Why What How When Who Where If In On At For By We You They He She A An Today "
    "India India's Indians China That's What's").split())

# A candidate end: a terminator, any closing quotes or brackets, then whitespace.
_CANDIDATE_RE = re.compile(r"[.!?…।][\"')\]]*\s+")
_CLAUSE_END_RE = re.compile(r"[.!?…।:;][\"')\]]*$")
_WORD_BEFORE_RE = re.compile(r"(\S+)$")


def _ends_here(text: str, m: re.Match) -> bool:
    """Whether the candidate end `m` in `text` really ends a sentence."""
    after = text[m.end():].split(None, 1)
    nxt = after[0] if after else ""
    if not nxt:
        return True
    if nxt[0].islower():  # "ever... and it flopped", "U.S. officials"
        return False
    if text[m.start()] != ".":  # ! ? … । end a sentence
        return True
    before = _WORD_BEFORE_RE.search(text[:m.start()])
    word = before.group(1).lstrip("\"'(“‘[") if before else ""
    if word in _NAME_TITLES:
        return False
    if word in _NUMBER_ABBREVIATIONS and nxt[0].isdigit():
        return False
    if word in _PLACE_ABBREVIATIONS or re.fullmatch(r"[A-Z]", word):
        return nxt.startswith("[") or nxt.strip("\"'“”‘’,") in _SENTENCE_STARTERS
    return True


def sentence_ends(text: str, start: int = 0, end: int | None = None) -> list[int]:
    """Offsets just past each sentence end (and the whitespace after it) found in
    text[start:end]. The word after `end` still decides the last one."""
    text = text or ""
    scope = text if end is None else text[:end]
    return [m.end() for m in _CANDIDATE_RE.finditer(scope, start) if _ends_here(text, m)]


def split_sentences(text: str) -> list[str]:
    """Sentences in order, stripped, empties dropped. A delivery tag after a sentence end stays
    with the sentence it introduces ("[pause] Here's why it matters.")."""
    text = text or ""
    out, last = [], 0
    for e in sentence_ends(text):
        out.append(text[last:e].strip())
        last = e
    out.append(text[last:].strip())
    return [s for s in out if s]


def ends_clause(word: str) -> bool:
    """True if `word` closes a sentence or a clause (. ! ? … । : ;), so a caption may break
    after it. An abbreviation ("U.S.", "Dr.") or a single initial ("J.") does not."""
    w = (word or "").strip()
    if not _CLAUSE_END_RE.search(w):
        return False
    core = w.rstrip("\"')]").rstrip(".")
    abbreviations = _NAME_TITLES | _NUMBER_ABBREVIATIONS | _PLACE_ABBREVIATIONS
    return core not in abbreviations and not re.fullmatch(r"[A-Z]", core)
