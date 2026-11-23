"""Tests for the centralized design-token system (single palette, no theme registry).

The 26-theme registry and ThemeManager are retired. These tests verify the
single, fixed design system and the persistence of appearance preferences.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from animevault.ui.theme import (  # noqa: E402
    ACCENT,
    ACCENT_DIM,
    ACCENT_DEEP,
    ACCENT_VIOLET,
    BG_DEEP,
    BG_INPUT,
    BORDER,
    BORDER_HOVER,
    TEXT_MUTED,
    TEXT_ON_ACCENT,
    TEXT_SECONDARY,
    TIER_COLORS,
    DANGER,
    SUCCESS,
    WARNING,
    reduce_effects,
    set_reduce_effects,
    liquid_glass,
    set_liquid_glass,
    tier_color,
    status_colors,
    tier_badge_style,
    status_badge_style,
)


def test_design_tokens_are_fixed():
    assert BG_DEEP == "#0a0c10"
    assert BG_INPUT == "#08090e"
    assert BORDER == "#2b3140"
    assert ACCENT == "#2dd4bf"
    assert ACCENT_DIM == "#14b8a6"
    assert ACCENT_DEEP == "#0d9488"
    assert ACCENT_VIOLET == "#8b5cf6"
    assert TEXT_MUTED == "#64748b"
    assert TEXT_ON_ACCENT == "#06121f"
    assert DANGER == "#ef4444"
    assert SUCCESS == "#22c55e"
    assert WARNING == "#eab308"


def test_tokens_form_restrained_dark_palette():
    # A functional border must be visually distinct (numerically brighter).
    assert int(BORDER.replace("#", ""), 16) > int(BG_DEEP.replace("#", ""), 16)
    assert int(BORDER.replace("#", ""), 16) > int(BG_INPUT.replace("#", ""), 16)
    # Accent is the brightest token (used for accents/highlights).
    assert int(ACCENT.replace("#", ""), 16) > int(BORDER.replace("#", ""), 16)


def test_tier_colours_span_the_scale():
    assert tier_color("SSS") != tier_color("F")
    assert tier_color("SSS") == TIER_COLORS["SSS"]


def test_unassigned_tier_is_muted_not_gold():
    style = tier_badge_style(None)
    assert "transparent" in style


def test_every_tier_has_a_colour():
    from animevault.tiers import TIERS

    for tier in TIERS:
        assert tier_color(tier)


def test_status_colours_are_accessible_pairs():
    assert status_colors("watching") == ("#0e7490", "#67e8f9")
    assert status_colors("completed") == ("#14532d", "#86efac")
    assert status_colors("missing") == ("#1f2937", TEXT_SECONDARY)


def test_badge_styles_build_qss():
    assert "background:" in tier_badge_style("SSS")
    assert "background:" in status_badge_style("watching")
    assert "border-radius" in tier_badge_style("A")


def test_liquid_glass_default_off_and_persisted():
    # Reset to a known clean state before asserting defaults.
    set_liquid_glass(False)
    set_reduce_effects(False)
    assert liquid_glass() is False
    assert reduce_effects() is False
    set_liquid_glass(True)
    assert liquid_glass() is True
    set_liquid_glass(False)
    assert liquid_glass() is False
    set_reduce_effects(True)
    assert reduce_effects() is True
    set_reduce_effects(False)
    assert reduce_effects() is False


def test_reduce_effects_persists():
    set_liquid_glass(False)
    set_reduce_effects(False)
    set_reduce_effects(True)
    assert reduce_effects() is True
    set_reduce_effects(False)
    assert reduce_effects() is False
