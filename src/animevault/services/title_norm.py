"""Shared title normalization for the recommendation pipeline.

This module provides a single, well-defined title-normalization routine used by
both the recommendation engine (owned-item exclusion, candidate deduplication)
and the discovery layer (candidate deduplication).

The normalization is deliberately conservative: it handles the cases the
recommendation subsystem must treat as identical (``ONE PIECE`` vs ``One
Piece``, leading/trailing or repeated whitespace, punctuation differences, and
common Unicode normalization differences) while preserving word structure so
that a short word or a substring can never cause two distinct works to be
merged.

What it does
------------
* NFKC Unicode normalization (`` FULLWIDTH `` -> ASCII, ligatures, combining
  marks, etc.).
* Case folding (more thorough than ``lower()`` for Unicode).
* Removes punctuation, but keeps letters, digits and whitespace.
* Collapses repeated / leading / trailing whitespace to a single space and
  strips it.

What it does not do
-------------------
* It does not drop words, stem, or remove a leading article such as "the" or
  "a".  Two titles that differ in more than case/whitespace/punctuation (even
  by a single word) therefore never merge.  This protects against the task's
  warning: "Do not remove unrelated titles merely because they share a short
  word or substring."
"""

from __future__ import annotations

import re
import unicodedata

#: Matches any character that is not a letter, digit, or whitespace.  These
#: characters are removed during normalization (punctuation, symbols, ...).
_TITLE_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)  # noqa: WPS326

#: Matches sequences of whitespace, collapsed to a single space.
_TITLE_WS_RE = re.compile(r"\s+", re.UNICODE)


def normalize_title(title: object) -> str:
    """Normalize a title for comparison.

    Args:
        title: The raw title (may be ``None`` or a non-string).

    Returns:
        A case-folded, NFKC-normalized, punctuation-stripped, whitespace
        collapsed version of the title ready for equality comparisons.
    """
    if title is None:
        return ""
    text = str(title)
    # NFKC maps full-width / ligature / combining-mark forms to their
    # composed, canonical equivalents.
    text = unicodedata.normalize("NFKC", text)
    # Case folding is more thorough than lowercasing for Unicode text.
    text = text.casefold()
    # Remove punctuation while preserving word structure and whitespace.
    text = _TITLE_NON_WORD_RE.sub("", text)
    # Collapse repeated or leading/trailing whitespace.
    text = _TITLE_WS_RE.sub(" ", text).strip()
    return text
