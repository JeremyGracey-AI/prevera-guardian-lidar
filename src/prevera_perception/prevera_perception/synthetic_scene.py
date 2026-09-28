"""ROS-free synthetic LIDAR scene: a 10 Hz 2D scan of an empty room with one "person".

The scenario (`_person_pose`):
  0. absent for the first 3.5 s, so the detector learns an empty room,
  1. walks across the room (tangentially, 2.4 m out) at 0.4 m/s,
  2. suddenly drops (centroid jumps ~0.6 m in 0.4 s = velocity spike),
  3. remains stationary as an elongated silhouette on the floor, lying
     broadside to the sensor so the 2D scan sees its full length.

A body lying end-on (along the sensor's line of sight) shows the LIDAR
only its ~25 cm near end; that is a real blind spot of a single 2D
sensor, not something this dev scenario tries to cover.

`SyntheticScanPublisher` (synthetic_publisher_node.py) wraps this class in a
ROS node; the unit tests and the replay harness drive it directly. This module
imports only the standard library and `numpy` so it collects on a machine
without ROS.

Determinism: `build_scan` draws exactly one `normal(0, 0.01, NUM_BEAMS)` from the
generator per call, before painting and regardless of `overrides`, so a given
seed yields the same scan sequence whether or not overrides are applied.

Override sets (`overrides_v3`, `overrides_v3_near_arc`) live here and nowhere
else: the tests, the mcap fixture writer and the replay harness all import them
from this module.
"""

from __future__ import annotations

import math
from collections.abc import Collection

import numpy as np


class SyntheticScene:

    NUM_BEAMS = 720
    RANGE_MAX = 12.0
    ROOM_WALL_RANGE = 5.0
    ANGLE_MIN = -math.pi
    ANGLE_INCREMENT = 2.0 * math.pi / NUM_BEAMS

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def build_scan(self, t: float, overrides: dict[int, float] | None = None) -> np.ndarray:
        """Return the float32 range array for time `t` (seconds since scene start).

        `overrides` maps beam index -> range value applied after the person is
        painted (e.g. `inf`, `nan`, `0.02`, `11.0`). `None` (default) leaves the
        output identical to the un-overridden scan.
        """
        # Base: 4-wall square room.
        ranges = np.full(self.NUM_BEAMS, self.ROOM_WALL_RANGE, dtype=np.float32)
        ranges += self._rng.normal(0.0, 0.01, size=self.NUM_BEAMS).astype(np.float32)

        pose = self._person_pose(t)
        if pose is not None:
            person_x, person_y, is_fallen = pose
            self._paint_person(ranges, person_x, person_y, is_fallen)

        if overrides:
            for beam, value in overrides.items():
                ranges[beam] = value
        return ranges

    def _person_pose(self, t: float) -> tuple[float, float, bool] | None:
        # Phase 0 (0-3.5s): empty room (detector warmup).
        # Phase 1 (3.5-8s): walk across at x=2.4 m, y from -1.0 to +0.8 m (0.4 m/s).
        # Phase 2 (8-8.4s): fall - centroid moves 0.6 m in 0.4 s (1.5 m/s spike).
        # Phase 3 (>8.4s): lying broadside at (2.4, 1.4), still.
        if t < 3.5:
            return None
        if t < 8.0:
            return 2.4, -1.0 + 0.4 * (t - 3.5), False
        if t < 8.4:
            return 2.4, 0.8 + 1.5 * (t - 8.0), False
        return 2.4, 1.4, True

    def _paint_person(
        self, ranges: np.ndarray, person_x: float, person_y: float, is_fallen: bool
    ) -> None:
        # Standing: narrow cylinder ~15 cm wide at the person's location.
        # Fallen:  1.6 m long, ~25 cm wide silhouette aligned along +Y
        #          (broadside to a sensor at the origin looking down +X).
        x_extent = 0.25 if is_fallen else 0.15
        y_extent = 1.6 if is_fallen else 0.15

        for i in range(self.NUM_BEAMS):
            angle = self.ANGLE_MIN + i * self.ANGLE_INCREMENT
            hit = self._ray_ellipse_hit(angle, person_x, person_y, x_extent, y_extent)
            if hit is None:
                continue
            if hit < ranges[i]:
                ranges[i] = hit
        return

    def _ray_ellipse_hit(
        self,
        angle: float,
        cx: float,
        cy: float,
        x_extent: float,
        y_extent: float,
    ) -> float | None:
        # Ray from origin direction (cos a, sin a), find nearest hit with an
        # axis-aligned ellipse centered at (cx, cy). Closed-form via substitution.
        dx = math.cos(angle)
        dy = math.sin(angle)
        a = x_extent / 2.0
        b = y_extent / 2.0
        A = (dx * dx) / (a * a) + (dy * dy) / (b * b)
        B = -2.0 * ((cx * dx) / (a * a) + (cy * dy) / (b * b))
        C = (cx * cx) / (a * a) + (cy * cy) / (b * b) - 1.0
        disc = B * B - 4.0 * A * C
        if disc < 0.0:
            return None
        sqrt_disc = math.sqrt(disc)
        t1 = (-B - sqrt_disc) / (2.0 * A)
        if t1 <= 0.0:
            return None
        return float(t1)


# ----------------------------------------------------------------- override sets
#
# Beams overridden after the person is painted, keyed by scan index `i` (10 Hz,
# stamps i*0.1). Designed against the detector's edge cases without ever adding a
# point from beams 5-8 and without an all-NaN column reaching `nanmedian`.

LINE_BEAMS = range(350, 358)
NEAR_ARC_BEAMS = range(100, 111)
_LINE_X_M = 1.0
_NEAR_ARC_RANGE_M = 0.20


def overrides_v3(i: int, line_scans: Collection[int] | None = None) -> dict[int, float]:
    """Override set v3 for scan index `i`.

    * beam 5 -> inf on every scan (never foreground);
    * beam 7 -> 11.0 for i < 40 (bakes 11.0 into the median), 10.5 for i >= 40
      (foreground, held, then dropped by `max_range_m`);
    * beam 6 -> untouched for i < 40 (scene wall), 0.02 for i >= 40 (foreground,
      held, then dropped by `min_range_m`);
    * beam 8 -> untouched for i < 40, nan for i >= 40 (never foreground; the hold
      on beams 6 and 7 plus `mask_dilation_beams` keeps it out of the history);
    * a collinear line x = 1.0 m on `LINE_BEAMS` (minor axis 0, elongation inf,
      8 points) for i >= 40 when `line_scans` is None, otherwise only when
      `i in line_scans`.
    """
    overrides: dict[int, float] = {5: float("inf")}
    if i < 40:
        overrides[7] = 11.0
        return overrides
    overrides[6] = 0.02
    overrides[7] = 10.5
    overrides[8] = float("nan")
    if line_scans is None or i in line_scans:
        for beam in LINE_BEAMS:
            angle = SyntheticScene.ANGLE_MIN + beam * SyntheticScene.ANGLE_INCREMENT
            overrides[beam] = _LINE_X_M / math.cos(angle)
    return overrides


def overrides_v3_near_arc(i: int) -> dict[int, float]:
    """`overrides_v3(i)` plus an 11-beam arc at 0.20 m on `NEAR_ARC_BEAMS` for i >= 40.

    Harness-verb tests only: it shifts the DBSCAN label order and adds a third WARN,
    so it is never the step-2 golden or the node adapter input.
    """
    overrides = overrides_v3(i)
    if i >= 40:
        for beam in NEAR_ARC_BEAMS:
            overrides[beam] = _NEAR_ARC_RANGE_M
    return overrides
