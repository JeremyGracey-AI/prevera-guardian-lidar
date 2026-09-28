"""Legacy reference for the detector_core golden test (NOT a test module).

Verbatim copy of the pre-refactor node's pure functions, taken from
`git show 36ca257:src/prevera_perception/prevera_perception/fall_detector_node.py`:

  * lines 149-166  `_scan_to_points`   (`msg` is any object with `.angle_min` / `.angle_increment`)
  * lines 194-224  `_emit_fall_events` (returns a list instead of publishing), `_evaluate`,
                   `_looks_horizontal`
  * lines 226-241  `_publish_event`    (returns the field dict instead of publishing; line 239 is
                   the `min(track.elongation, 1e6)` clamp)

Substitutions, and nothing else: `FallEvent.NONE/OBSERVE/WARN` -> the ints 0/1/2
(`src/prevera_msgs/msg/FallEvent.msg:5-7`); the `self._*` thresholds -> constructor arguments.
`_already_alerted` lives on the instance exactly as it did on the node (`36ca257` line 58).

This is the reference for `T/test_detector_core.py::test_core_matches_legacy_reference_golden`,
not `T/test_synthetic_fall.py` (whose point builder has no isfinite/min_range/max_range filter).
"""

from __future__ import annotations

import math

import numpy as np

NONE = 0
OBSERVE = 1
WARN = 2


class LegacyReference:

    def __init__(
        self,
        *,
        min_range_m: float,
        max_range_m: float,
        fall_elongation: float,
        fall_major_axis_m: float,
        velocity_spike_mps: float,
        sustained_down_s: float,
    ) -> None:
        self._min_range_m = min_range_m
        self._max_range_m = max_range_m
        self._fall_elongation = fall_elongation
        self._fall_major_axis_m = fall_major_axis_m
        self._velocity_spike_mps = velocity_spike_mps
        self._sustained_down_s = sustained_down_s
        self._already_alerted: set[int] = set()

    # 36ca257 lines 149-166 ------------------------------------------------------
    def _scan_to_points(
        self, msg, ranges: np.ndarray, foreground: np.ndarray
    ) -> np.ndarray:
        valid = (
            foreground
            & np.isfinite(ranges)
            & (ranges >= self._min_range_m)
            & (ranges <= self._max_range_m)
        )
        if not np.any(valid):
            return np.empty((0, 2), dtype=np.float32)

        indices = np.nonzero(valid)[0]
        angles = msg.angle_min + indices * msg.angle_increment
        r = ranges[indices]
        xs = r * np.cos(angles)
        ys = r * np.sin(angles)
        return np.stack([xs, ys], axis=1).astype(np.float32)

    # 36ca257 lines 194-224 ------------------------------------------------------
    def _emit_fall_events(self, tracks) -> list[dict]:
        events: list[dict] = []
        for track in tracks:
            if track.track_id in self._already_alerted:
                continue
            alert, confidence = self._evaluate(track)
            if alert == NONE:
                continue
            events.append(self._publish_event(track, alert, confidence))
            if alert >= WARN:
                self._already_alerted.add(track.track_id)
        return events

    def _evaluate(self, track) -> tuple[int, float]:
        if not self._looks_horizontal(track):
            return NONE, 0.0

        if track.peak_recent_velocity >= self._velocity_spike_mps and track.stillness_s > 0.5:
            confidence = min(1.0, 0.5 + 0.1 * track.stillness_s)
            return WARN, confidence

        if track.stillness_s >= self._sustained_down_s:
            return WARN, 0.6

        return OBSERVE, 0.3

    def _looks_horizontal(self, track) -> bool:
        if not math.isfinite(track.elongation):
            return True  # degenerate (minor ~ 0) -> very flat
        return (
            track.elongation >= self._fall_elongation
            and track.major_axis_m >= self._fall_major_axis_m
        )

    # 36ca257 lines 226-241 (field assignments, incl. the line-239 clamp) ----------
    def _publish_event(self, track, alert_level: int, confidence: float) -> dict:
        event: dict = {}
        event["track_id"] = track.track_id
        event["alert_level"] = alert_level
        event["confidence"] = float(confidence)
        event["location"] = (float(track.centroid[0]), float(track.centroid[1]), 0.0)
        event["horizontal_extent_m"] = float(track.major_axis_m)
        event["elongation_ratio"] = float(min(track.elongation, 1e6))
        event["stillness_duration_s"] = float(track.stillness_s)
        event["preceding_velocity_mps"] = float(track.peak_recent_velocity)
        return event
