"""Alert latch vs incident hold (floor-trials-1 segment C, 2026-09-27).

Legacy (`fall.hold_incident: false`): a track that reaches WARN is added to `_already_alerted`
and never emits again, even while the person stays down. In floor-trials-1 segment C the one
WARN at 165.3 s was followed by 26 s of silence with the track still present and horizontal.

Fixed (`fall.hold_incident: true`): the highest level reached is held per track and re-emitted
every scan the track looks horizontal; the incident clears only after the track has not looked
horizontal for `fall.incident_clear_s`, or when the tracker drops the track.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from prevera_perception.detector_core import AlertLevel, DetectorCore
from prevera_perception.tracker import Track

from test_detector_core import CONFIG, FALL

HOLD = dataclasses.replace(CONFIG, fall=dataclasses.replace(FALL, hold_incident=True, incident_clear_s=2.0))
DT = 0.1


def _track(track_id: int = 7, *, stillness_s: float = 0.0, horizontal: bool = True) -> Track:
    return Track(
        track_id=track_id,
        centroid=np.array([-2.6, 0.1], dtype=np.float32),
        last_velocity=np.zeros(2, dtype=np.float32),
        peak_recent_velocity=0.0,
        elongation=10.0 if horizontal else 1.5,
        major_axis_m=1.6 if horizontal else 0.3,
        age_s=30.0,
        missed_scans=0,
        stillness_s=stillness_s,
    )


def _levels(core: DetectorCore, frames: list[list[Track]]) -> list[list[AlertLevel]]:
    return [[ev.level for ev in core._emit_fall_events(tracks, i * DT)] for i, tracks in enumerate(frames)]


def test_legacy_latch_goes_silent_after_warn():
    # WARN (sustained stillness >= 4 s), then stillness resets as it does on the floor bag.
    frames = [[_track(stillness_s=4.0)]] + [[_track(stillness_s=0.2)]] * 20
    levels = _levels(DetectorCore(CONFIG), frames)
    assert levels[0] == [AlertLevel.WARN]
    assert all(lv == [] for lv in levels[1:])


def test_hold_keeps_reporting_at_the_held_level():
    frames = [[_track(stillness_s=4.0)]] + [[_track(stillness_s=0.2)]] * 20
    levels = _levels(DetectorCore(HOLD), frames)
    assert all(lv == [AlertLevel.WARN] for lv in levels)


def test_hold_reports_observe_before_any_warn():
    levels = _levels(DetectorCore(HOLD), [[_track(stillness_s=0.2)]] * 5)
    assert all(lv == [AlertLevel.OBSERVE] for lv in levels)


def test_hold_keeps_the_warn_confidence_while_held():
    core = DetectorCore(HOLD)
    first = core._emit_fall_events([_track(stillness_s=4.0)], 0.0)
    later = core._emit_fall_events([_track(stillness_s=0.2)], DT)
    assert later[0].level == AlertLevel.WARN
    assert later[0].confidence == first[0].confidence == 0.6


def test_brief_shape_flicker_does_not_clear_the_incident():
    # Segment C: `major` flipped 1.61 <-> 1.29 m scan to scan; one non-horizontal scan must not
    # drop the incident back to OBSERVE.
    frames = [[_track(stillness_s=4.0)], [_track(horizontal=False)], [_track(horizontal=False)], [_track(stillness_s=0.2)]]
    levels = _levels(DetectorCore(HOLD), frames)
    assert levels == [[AlertLevel.WARN], [], [], [AlertLevel.WARN]]


def test_incident_clears_after_clear_window_without_horizontal():
    clear_scans = int(round(HOLD.fall.incident_clear_s / DT))
    frames = [[_track(stillness_s=4.0)]] + [[_track(horizontal=False)]] * (clear_scans + 1) + [[_track(stillness_s=0.2)]]
    levels = _levels(DetectorCore(HOLD), frames)
    assert levels[-1] == [AlertLevel.OBSERVE]


def test_incident_is_dropped_with_the_track():
    core = DetectorCore(HOLD)
    core._emit_fall_events([_track(track_id=7, stillness_s=4.0)], 0.0)
    core._emit_fall_events([], DT)                       # tracker evicted track 7
    again = core._emit_fall_events([_track(track_id=7, stillness_s=0.2)], 2 * DT)
    assert [ev.level for ev in again] == [AlertLevel.OBSERVE]


def test_incidents_are_per_track():
    core = DetectorCore(HOLD)
    core._emit_fall_events([_track(track_id=1, stillness_s=4.0)], 0.0)
    out = core._emit_fall_events([_track(track_id=1, stillness_s=0.2), _track(track_id=2, stillness_s=0.2)], DT)
    assert {ev.track_id: ev.level for ev in out} == {1: AlertLevel.WARN, 2: AlertLevel.OBSERVE}
