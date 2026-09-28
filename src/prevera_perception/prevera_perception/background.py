"""Rolling background model for 2D LIDAR scans.

We keep a per-beam median of the last N scans as the "background" range
for each angular bin. A new scan's returns are considered foreground if
they are noticeably *closer* than the background (something entered the
scene). This handles static furniture, walls, and room geometry without
a prior map.

Foreground hold: a plain rolling median absorbs anything that stops
moving. With a 40-scan window at 10 Hz, a person lying still on the floor
became "background" after ~2 s, so the detector lost them before its
4 s sustained-down rule could fire. When `hold_foreground` is on, beams
that currently see foreground (plus `mask_dilation_beams` neighbours on
each side) push the existing background value into the history instead
of the new reading, so a still person stays foreground. A beam held for
more than `max_hold_scans` consecutive scans is released, so a moved
chair or a new box is eventually learned as background instead of
tracking forever.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BackgroundConfig:
    window_size: int            # number of scans in the rolling median
    warmup_scans: int           # refuse to classify anything until this many scans seen
    foreground_margin_m: float  # how much closer than background to count as foreground
    hold_foreground: bool = True    # keep foreground beams out of the background history
    max_hold_scans: int = 1200      # release a beam held this long (1200 = 2 min at 10 Hz)
    mask_dilation_beams: int = 2    # also hold this many neighbouring beams on each side


class Background:
    """Per-beam rolling median range.

    All scans fed in must share the same beam count. The first scan seen
    fixes that count; later scans with a different shape are rejected by
    the caller (validated at the node boundary).
    """

    def __init__(self, config: BackgroundConfig) -> None:
        self._config = config
        self._history: deque[np.ndarray] = deque(maxlen=config.window_size)
        self._held_scans: np.ndarray | None = None

    @property
    def ready(self) -> bool:
        return len(self._history) >= self._config.warmup_scans

    def background(self) -> np.ndarray:
        """Current per-beam background range. Requires at least one scan."""
        return np.nanmedian(np.stack(self._history, axis=0), axis=0)

    def update(self, ranges: np.ndarray, foreground: np.ndarray | None = None) -> None:
        """Add a scan to the history.

        `foreground` is the mask returned by `foreground_mask` for this
        scan. When given and `hold_foreground` is on, those beams keep
        their current background value instead of the new reading.
        """
        sample = ranges.copy()
        if foreground is not None and self._config.hold_foreground and self._history:
            hold = self._dilate(foreground)
            if self._held_scans is None or self._held_scans.shape != hold.shape:
                self._held_scans = np.zeros(hold.shape, dtype=np.int64)
            self._held_scans = np.where(hold, self._held_scans + 1, 0)
            hold &= self._held_scans <= self._config.max_hold_scans
            sample[hold] = self.background()[hold]
        self._history.append(sample)

    def foreground_mask(self, ranges: np.ndarray) -> np.ndarray:
        """Return a boolean mask of which beams saw a foreground return.

        Must not be called before `ready` is True.
        """
        return ranges < (self.background() - self._config.foreground_margin_m)

    def _dilate(self, mask: np.ndarray) -> np.ndarray:
        k = self._config.mask_dilation_beams
        if k <= 0 or not mask.any():
            return mask.copy()
        out = mask.copy()
        for shift in range(1, k + 1):
            out[shift:] |= mask[:-shift]
            out[:-shift] |= mask[shift:]
        return out