"""Tests for the canonical Tier system."""

import pytest

from animevault.tiers import (
    DEFAULT_SCORE_TO_TIER,
    TIERS,
    InvalidTierError,
    is_valid_tier,
    normalize_tier,
    score_to_tier,
    tier_display,
    tier_sort_key,
)


class TestTierConstants:
    def test_all_nine_tiers_present(self):
        assert TIERS == ("SSS", "SS", "S", "A", "B", "C", "D", "E", "F")

    def test_tier_order_is_ranked_not_alphabetical(self):
        # Canonical order must be best-to-worst, which differs from
        # alphabetical order (A, B, C ...).
        assert list(TIERS) != sorted(TIERS)
        assert TIERS[0] == "SSS"
        assert TIERS[-1] == "F"


class TestNormalizeTier:
    @pytest.mark.parametrize("raw", ["SSS", "sss", "Sss", " sSs ", "\tsss\n"])
    def test_case_and_whitespace_variants_normalize(self, raw):
        assert normalize_tier(raw) == "SSS"

    @pytest.mark.parametrize("raw,expected", [
        ("ss", "SS"), ("s", "S"), ("a", "A"), ("b", "B"),
        ("c", "C"), ("d", "D"), ("e", "E"), ("f", "F"),
    ])
    def test_lowercase_single_letters(self, raw, expected):
        assert normalize_tier(raw) == expected

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_becomes_unassigned(self, empty):
        assert normalize_tier(empty) is None

    @pytest.mark.parametrize("bad", ["Legendary", "S+", "AAA", "10", "Z", "SSSS"])
    def test_invalid_raises(self, bad):
        with pytest.raises(InvalidTierError):
            normalize_tier(bad)

    def test_error_message_mentions_value(self):
        with pytest.raises(InvalidTierError, match="Legendary"):
            normalize_tier("Legendary")

    def test_non_string_raises(self):
        with pytest.raises(InvalidTierError):
            normalize_tier(123)


class TestIsValidTier:
    @pytest.mark.parametrize("t", list(TIERS))
    def test_valid_tiers(self, t):
        assert is_valid_tier(t) is True

    def test_invalid_value(self):
        assert is_valid_tier("Legendary") is False

    def test_none_is_not_a_valid_tier_value(self):
        # None is "unassigned", not a tier.
        assert is_valid_tier(None) is False


class TestTierSortKey:
    def test_ranks_are_sequential(self):
        ranks = [tier_sort_key(t)[0] for t in TIERS]
        assert ranks == list(range(9))

    def test_sss_sorts_before_ss(self):
        assert tier_sort_key("SSS") < tier_sort_key("SS")

    def test_s_sorts_before_a(self):
        assert tier_sort_key("S") < tier_sort_key("A")

    def test_f_is_best_worst_end(self):
        assert tier_sort_key("F") > tier_sort_key("E")

    def test_unassigned_sorts_last(self):
        assert tier_sort_key(None) > tier_sort_key("F")

    def test_sorting_is_not_alphabetical(self):
        # Alphabetical would give A, B, C, D, E, F, S, SS, SSS.
        ordered = sorted(TIERS, key=tier_sort_key)
        assert ordered == list(TIERS)


class TestTierDisplay:
    def test_displays_tier(self):
        assert tier_display("SSS") == "SSS"

    def test_displays_dash_when_unassigned(self):
        assert tier_display(None) == "—"

    def test_displays_dash_for_empty(self):
        assert tier_display("") == "—"


class TestScoreToTier:
    @pytest.mark.parametrize("score,expected", [
        (10.0, "SSS"), (9.5, "SSS"), (9.0, "SSS"),
        (8.9, "SS"), (8.0, "SS"),
        (7.9, "S"), (7.0, "S"),
        (6.5, "A"), (6.0, "A"),
        (5.5, "B"), (5.0, "B"),
        (4.5, "C"), (4.0, "C"),
        (3.5, "D"), (3.0, "D"),
        (2.5, "E"), (2.0, "E"),
        (1.9, "F"), (1.0, "F"), (0.0, "F"),
    ])
    def test_default_mapping(self, score, expected):
        assert score_to_tier(score) == expected

    def test_none_score_yields_none(self):
        assert score_to_tier(None) is None

    def test_custom_mapping_is_honoured(self):
        # A user could choose a completely different rule set.
        mapping = ((0.0, 4.9, "C"), (5.0, 10.0, "SSS"))
        assert score_to_tier(3.0, mapping) == "C"
        assert score_to_tier(9.0, mapping) == "SSS"

    def test_score_above_range_yields_none(self):
        assert score_to_tier(10.5) is None