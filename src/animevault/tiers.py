"""Canonical Tier system — replaces the numeric score as the personal ranking.

The tier is the user's *personal* evaluation of an anime and is strictly
separate from provider metadata.  Values are a controlled, ordered set:

    SSS > SS > S > A > B > C > D > E > F

Unassigned (``None``) is always valid — a user may not have ranked a show.
"""

from __future__ import annotations

from typing import Optional

# ── Canonical tiers, best → worst ─────────────────────────────────

TIER_SSS = "SSS"
TIER_SS = "SS"
TIER_S = "S"
TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
TIER_D = "D"
TIER_E = "E"
TIER_F = "F"

#: Ordered best-to-worst.  Index order *is* the ranking.
TIERS: tuple[str, ...] = (
    TIER_SSS,
    TIER_SS,
    TIER_S,
    TIER_A,
    TIER_B,
    TIER_C,
    TIER_D,
    TIER_E,
    TIER_F,
)

VALID_TIERS = TIERS

#: Rank helper for sorting: lower number = better tier.
_TIER_RANK: dict[str, int] = {t: i for i, t in enumerate(TIERS)}


class InvalidTierError(ValueError):
    """Raised when a tier string is not part of the controlled set."""


def normalize_tier(value: object) -> Optional[str]:
    """Normalize a raw tier value to a canonical tier, or ``None``.

    Accepts case and whitespace variations (``" sss "`` → ``"SSS"``).

    Raises
    ------
    InvalidTierError
        If *value* is non-empty and cannot be mapped to a valid tier.
    """
    if value is None:
        return None

    # Non-string values that are already valid tiers (e.g. from a DB row).
    if isinstance(value, str):
        text = value.strip().upper()
        if not text:
            return None
        if text in _TIER_RANK:
            return text
        raise InvalidTierError(f"Invalid tier value: {value!r}")

    raise InvalidTierError(f"Invalid tier value: {value!r}")


def is_valid_tier(value: object) -> bool:
    """Return True when *value* is a canonical tier (not "unassigned")."""
    if value is None:
        return False
    try:
        return normalize_tier(value) is not None
    except InvalidTierError:
        return False


def tier_sort_key(tier: Optional[str]) -> tuple:
    """Sort key placing best tier first, and unassigned last.

    ``SSS`` → ``(0, "")`` … ``F`` → ``(8, "")``, unassigned → ``(99, "")``.

    Use as ``sorted(items, key=lambda x: tier_sort_key(x.tier))`` — this
    deliberately does *not* sort alphabetically.
    """
    if not tier:
        return (99, "")
    t = tier.strip().upper()
    return (_TIER_RANK.get(t, 99), "")


def tier_display(tier: Optional[str]) -> str:
    """Human-facing tier label; em-dash when unassigned."""
    return tier if tier else "—"


# ── Optional score → tier conversion ──────────────────────────────
#
# NEVER applied automatically.  The user must explicitly opt in, because
# a numeric rating and a personal tier are not the same judgement.

#: Default boundaries, matching the mapping documented in the spec.
DEFAULT_SCORE_TO_TIER: tuple[tuple[float, float, str], ...] = (
    (9.0, 10.0, TIER_SSS),
    (8.0, 8.999, TIER_SS),
    (7.0, 7.999, TIER_S),
    (6.0, 6.999, TIER_A),
    (5.0, 5.999, TIER_B),
    (4.0, 4.999, TIER_C),
    (3.0, 3.999, TIER_D),
    (2.0, 2.999, TIER_E),
    (0.0, 1.999, TIER_F),
)


def score_to_tier(
    score: Optional[float],
    mapping: Optional[tuple[tuple[float, float, str], ...]] = None,
) -> Optional[str]:
    """Convert a legacy numeric score to a tier using an explicit mapping.

    This is only ever called after the user explicitly chooses to convert;
    see :func:`animevault.migration.migrate_scores_to_tiers`.
    """
    if score is None:
        return None
    table = mapping or DEFAULT_SCORE_TO_TIER
    for low, high, tier in table:
        if low <= score <= high:
            return tier
    return None