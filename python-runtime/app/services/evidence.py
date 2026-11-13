"""Checks that a memory claim is grounded in what the user actually wrote.

Plan memory accepts a decision or constraint as user-authored only when it can
be tied to a real user message. A model rarely restates a decision word for
word, so grounding is judged on normalised text and content-word overlap, and a
bare approval ("ok, go with that") can accept the proposal it is replying to.
"""
from __future__ import annotations

import re

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "its",
    "of", "on", "or", "our", "should", "that", "the", "this", "to", "we", "will", "with",
    "use", "using", "user", "wants", "want", "let", "lets", "let's", "go", "all", "be",
}
_APPROVAL = re.compile(
    r"^\W*(?:yes|yeah|yep|ok(?:ay)?|sure|agreed|approved|sounds good|perfect|great|do (?:it|that)|"
    r"go (?:with|ahead)|let'?s (?:do|go)|that works|fine)\b",
    re.IGNORECASE,
)
_OVERLAP = 0.6


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_QUOTES)).strip().casefold()


def is_verbatim(quote: str, source: str) -> bool:
    """The quote occurs in the source, ignoring case, whitespace and typographic quotes."""
    quote = normalise(quote)
    return bool(quote) and quote in normalise(source)


def _content_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9][a-z0-9.+#_-]*", normalise(text)) if word not in _STOPWORDS}


def overlaps(statement: str, source: str, threshold: float = _OVERLAP) -> bool:
    """Most of the statement's content words appear in the source."""
    words = _content_words(statement)
    if not words:
        return False
    return len(words & _content_words(source)) / len(words) >= threshold


def is_approval(quote: str) -> bool:
    return bool(_APPROVAL.match(quote or "")) and len(normalise(quote)) <= 120


def grounded_in_user(statement: str, quote: str, user_text: str, prior_assistant_text: str = "") -> bool:
    """A user-authored decision/constraint: the quote is real and supports the statement.

    Accepted when the user's own words cover the statement, or when the user
    approved a proposal the assistant had just made and the statement matches it.
    """
    if not is_verbatim(quote, user_text):
        return False
    if is_verbatim(statement, quote) or overlaps(statement, quote):
        return True
    return bool(prior_assistant_text) and is_approval(quote) and overlaps(statement, prior_assistant_text)
