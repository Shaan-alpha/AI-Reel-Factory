"""The one sentence splitter shared by the scriptwriter, the voice and the subtitles.

It used to break on "U.S." and on "...", so the opening guard read "A U.S." as a whole first
sentence and failed 2 of the last 9 published scripts (audit 2026-11-10, script 9).
"""
from src.text import ends_clause, split_sentences


def test_abbreviations_do_not_end_a_sentence():
    assert split_sentences("A U.S. court ruled today. Markets fell.") == [
        "A U.S. court ruled today.", "Markets fell."]
    assert split_sentences("Dr. Rao and J. Smith spoke. Then it rained.") == [
        "Dr. Rao and J. Smith spoke.", "Then it rained."]


def test_an_ellipsis_before_lowercase_continues_the_sentence():
    assert split_sentences("India's biggest IPO ever... and it flopped. Here's why.") == [
        "India's biggest IPO ever... and it flopped.", "Here's why."]


def test_decimals_short_answers_and_the_hindi_full_stop():
    assert split_sentences("Rates fell 0.25 points. Did it work? No. यह बड़ा है। Why?") == [
        "Rates fell 0.25 points.", "Did it work?", "No.", "यह बड़ा है।", "Why?"]


def test_a_tag_stays_with_the_sentence_it_introduces():
    assert split_sentences("One fact. [pause] Here's why it matters.") == [
        "One fact.", "[pause] Here's why it matters."]


def test_ends_clause():
    assert ends_clause("today.") and ends_clause("matters:") and ends_clause("है।")
    assert not ends_clause("U.S.") and not ends_clause("Dr.") and not ends_clause("J.")
