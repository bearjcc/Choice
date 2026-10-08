# SPDX-License-Identifier: AGPL-3.0-only

from choice.gesture import resolve_swipe


def test_resolve_swipe_cardinal():
    assert resolve_swipe(120, 5) == "right"
    assert resolve_swipe(-120, 5) == "left"
    assert resolve_swipe(5, -120) == "up"
    assert resolve_swipe(5, 120) == "down"


def test_resolve_swipe_below_threshold():
    assert resolve_swipe(50, 0) is None
    assert resolve_swipe(0, 50) is None


def test_resolve_swipe_dominant_axis():
    assert resolve_swipe(100, 90) == "right"
    assert resolve_swipe(90, 100) == "down"
