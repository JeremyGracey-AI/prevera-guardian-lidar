"""Unit tests for the rolling background model and its foreground hold."""

import numpy as np
import pytest
from prevera_perception.background import Background, BackgroundConfig

BEAMS = 360
WALL_M = 5.0


def _config(**overrides) -> BackgroundConfig:
    base = {"window_size": 40, "warmup_scans": 30, "foreground_margin_m": 0.15}
    base.update(overrides)
    return BackgroundConfig(**base)


def _empty_room() -> np.ndarray:
    return np.full(BEAMS, WALL_M, dtype=np.float32)


def _with_object(beams=slice(100, 112), range_m=2.4) -> np.ndarray:
    scan = _empty_room()
    scan[beams] = range_m
    return scan


def _run(bg: Background, scan: np.ndarray, n: int) -> list[int]:
    """Feed `scan` n times the way the node does; return foreground beam counts."""
    counts = []
    for _ in range(n):
        if bg.ready:
            fg = bg.foreground_mask(scan)
            bg.update(scan, foreground=fg)
            counts.append(int(fg.sum()))
        else:
            bg.update(scan)
    return counts


def test_without_hold_a_still_object_is_absorbed():
    # Documents the original failure: a still person vanishes after ~half the window.
    bg = Background(_config(hold_foreground=False))
    _run(bg, _empty_room(), 40)
    counts = _run(bg, _with_object(), 60)
    assert counts[0] == 12
    assert counts[-1] == 0


def test_hold_keeps_a_still_person_visible_for_10_seconds():
    bg = Background(_config())
    _run(bg, _empty_room(), 40)
    counts = _run(bg, _with_object(), 100)  # 10 s at 10 Hz
    assert min(counts) == 12


def test_hold_releases_after_max_hold_scans():
    bg = Background(_config(max_hold_scans=50))
    _run(bg, _empty_room(), 40)
    counts = _run(bg, _with_object(), 150)
    assert counts[0] == 12
    assert counts[-1] == 0  # a moved chair is learned eventually


def test_background_returns_when_object_leaves():
    bg = Background(_config())
    _run(bg, _empty_room(), 40)
    _run(bg, _with_object(), 50)
    counts = _run(bg, _empty_room(), 5)
    assert counts[-1] == 0


def test_dilation_holds_neighbouring_beams():
    bg = Background(_config(mask_dilation_beams=2))
    mask = np.zeros(10, dtype=bool)
    mask[5] = True
    assert bg._dilate(mask).nonzero()[0].tolist() == [3, 4, 5, 6, 7]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])