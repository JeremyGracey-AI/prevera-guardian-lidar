"""Windowed displacement stillness (plan v4 step 6).

With `still_window_s > 0` a matched track is "still" once every centroid it had over the last
`still_window_s` seconds (plus the one sample straddling the window start) lies within
`still_displacement_m` of the current centroid; `stillness_s` then counts from the oldest retained
sample. Legacy (`still_window_s == 0`, the default) is the per-scan speed threshold.

Every scenario uses W = 1.5 s, D = 0.25 m, `max_missed_scans=15` (the yaml value) and stamps
`i * 0.1` from 0.0, with float64 centroids so distances are exact. Expectations follow the plan's
test float rule: stillness `pytest.approx(x, abs=1e-9)` (raw values on this Mac are one ulp off,
e.g. 2.9000000000000004 for 2.9, plan Appendix E).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from prevera_perception.clustering import Cluster
from prevera_perception.tracker import Tracker, TrackerConfig

W = 1.5          # still_window_s
D = 0.25         # still_displacement_m
SPOT = (1.0, 0.0)


def _config(**overrides) -> TrackerConfig:
    base = TrackerConfig(
        association_gate_m=0.5,
        max_missed_scans=15,
        velocity_window=10,
        still_velocity_mps=0.15,
        still_window_s=W,
        still_displacement_m=D,
    )
    return dataclasses.replace(base, **overrides)


def _cluster(x: float, y: float) -> Cluster:
    return Cluster(centroid=np.array([x, y], dtype=np.float64), point_count=20, major_axis_m=0.2, minor_axis_m=0.15)


def _t(i: int) -> float:
    return i * 0.1


def _only(tracker: Tracker):
    [track] = tracker.tracks
    return track


def _jitter_centroids(n: int = 60) -> list[tuple[float, float]]:
    # Sampling spec (plan step 6): per scan, in this order, r then a, from default_rng(1).
    rng = np.random.default_rng(1)
    out = []
    for _ in range(n):
        r = 0.10 * math.sqrt(rng.random())
        a = 2 * math.pi * rng.random()
        out.append((SPOT[0] + r * math.cos(a), SPOT[1] + r * math.sin(a)))
    return out


def _run_jitter(config: TrackerConfig) -> tuple[list[float], set[int]]:
    tracker = Tracker(config)
    stillness, ids = [], set()
    for i, (x, y) in enumerate(_jitter_centroids()):
        tracker.update([_cluster(x, y)], _t(i))
        track = _only(tracker)
        stillness.append(track.stillness_s)
        ids.add(track.track_id)
    return stillness, ids


def test_window_accumulates_with_jitter():
    pts = np.array(_jitter_centroids())
    max_pairwise = max(float(np.linalg.norm(p - q)) for p in pts for q in pts)
    steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert max_pairwise < D                                   # plan: 0.1975 m, inside the 0.25 m disc
    assert max_pairwise == pytest.approx(0.1975, abs=5e-5)
    assert steps.max() / 0.1 > 0.15                           # plan: 0.175 m per scan = 1.75 m/s
    assert steps.max() == pytest.approx(0.175, abs=5e-4)

    stillness, ids = _run_jitter(_config())
    assert ids == {1}
    first = next(i for i, s in enumerate(stillness) if s > 0.0)
    assert _t(first) == pytest.approx(1.5, abs=1e-9)
    assert stillness[first] == pytest.approx(1.5, abs=1e-9)
    assert stillness[-1] == pytest.approx(5.9, abs=1e-9)

    # Legacy (per-scan speed threshold) on the same seeded input never sees the lying body as
    # still: the jitter alone exceeds 0.15 m/s between scans (field notes 2026-09-25 :20-22).
    legacy, legacy_ids = _run_jitter(_config(still_window_s=0.0))
    assert legacy_ids == {1}
    assert legacy[-1] == pytest.approx(0.0, abs=1e-9)
    assert max(legacy) == pytest.approx(0.0, abs=1e-9)


def test_walk_never_still():
    tracker = Tracker(_config())
    for i in range(30):                                       # 0.4 m/s along x for 3 s
        tracker.update([_cluster(SPOT[0] + 0.04 * i, SPOT[1])], _t(i))
        track = _only(tracker)
        assert track.track_id == 1
        assert track.stillness_s == pytest.approx(0.0, abs=1e-9), _t(i)


def test_starts_at_stamp_zero():
    # Guards the `is None` rule (an `or` would drop still_since_s == 0.0) and the spawn seeding:
    # either mistake gives 2.8.
    tracker = Tracker(_config())
    for i in range(30):
        tracker.update([_cluster(*SPOT)], _t(i))
        if i == 14:
            assert _only(tracker).stillness_s == pytest.approx(0.0, abs=1e-9)
        if i == 15:
            assert _only(tracker).stillness_s == pytest.approx(1.5, abs=1e-9)
    track = _only(tracker)
    assert track.still_since_s == pytest.approx(0.0, abs=1e-9)
    assert track.stillness_s == pytest.approx(2.9, abs=1e-9)


def test_spawn_seeds_history():
    tracker = Tracker(_config())
    tracker.update([_cluster(*SPOT)], _t(3))
    track = _only(tracker)
    assert [(t, c.tolist()) for t, c in track.position_history] == [(pytest.approx(0.3, abs=1e-9), [1.0, 0.0])]
    assert track.still_since_s is None
    assert track.stillness_s == 0.0


def test_short_gap_credited():
    tracker = Tracker(_config())
    for i in range(20):                                       # still t = 0.0 .. 1.9
        tracker.update([_cluster(*SPOT)], _t(i))
    for i in range(20, 28):                                   # 8 unmatched t = 2.0 .. 2.7
        tracker.update([], _t(i))
        assert _only(tracker).stillness_s == pytest.approx(1.9, abs=1e-9)   # frozen during the gap
    for i in range(28, 48):                                   # still t = 2.8 .. 4.7, same spot
        tracker.update([_cluster(*SPOT)], _t(i))
    track = _only(tracker)
    assert track.track_id == 1
    assert track.stillness_s == pytest.approx(4.7, abs=1e-9)


def _still_then_long_gap() -> Tracker:
    tracker = Tracker(_config())
    for i in range(20):                                       # still t = 0.0 .. 1.9
        tracker.update([_cluster(*SPOT)], _t(i))
    for i in range(20, 35):                                   # 15 unmatched t = 2.0 .. 3.4
        tracker.update([], _t(i))
    track = _only(tracker)                                    # not evicted at max_missed_scans=15
    assert track.missed_scans == 15
    assert track.stillness_s == pytest.approx(1.9, abs=1e-9)
    return tracker


def test_long_gap_credited_when_reacquired_at_same_spot():
    tracker = _still_then_long_gap()
    tracker.update([_cluster(*SPOT)], _t(35))
    track = _only(tracker)
    assert track.track_id == 1
    assert track.stillness_s == pytest.approx(3.5, abs=1e-9)
    for i in range(36, 40):
        tracker.update([_cluster(*SPOT)], _t(i))
    assert _only(tracker).stillness_s == pytest.approx(3.9, abs=1e-9)


def test_long_gap_resets_when_reacquired_elsewhere():
    tracker = _still_then_long_gap()
    elsewhere = (SPOT[0] + 0.45, SPOT[1])                     # inside the 0.5 m gate, outside D
    for i in range(35, 50):                                   # t = 3.5 .. 4.9
        tracker.update([_cluster(*elsewhere)], _t(i))
        track = _only(tracker)
        assert track.track_id == 1
        assert track.stillness_s == pytest.approx(0.0, abs=1e-9), _t(i)
    tracker.update([_cluster(*elsewhere)], _t(50))
    assert _only(tracker).stillness_s == pytest.approx(1.5, abs=1e-9)


def test_two_samples_apart_reset():
    tracker = Tracker(_config())
    for i in range(20):                                       # still t = 0.0 .. 1.9
        tracker.update([_cluster(*SPOT)], _t(i))
    assert _only(tracker).stillness_s == pytest.approx(1.9, abs=1e-9)
    tracker.update([_cluster(SPOT[0] + 0.3, SPOT[1])], _t(20))   # one scan 0.3 m away
    assert _only(tracker).stillness_s == pytest.approx(0.0, abs=1e-9)
    seen = {}
    for i in range(21, 40):                                   # back at the old spot from t = 2.1
        tracker.update([_cluster(*SPOT)], _t(i))
        seen[i] = _only(tracker).stillness_s
    for i in range(21, 36):                                   # the excursion is still inside the window
        assert seen[i] == pytest.approx(0.0, abs=1e-9), _t(i)
    assert seen[36] == pytest.approx(1.5, abs=1e-9)
    assert seen[39] == pytest.approx(1.8, abs=1e-9)
    assert _only(tracker).track_id == 1


def _header_stamp(i: int) -> float:
    sec, nanosec = divmod(i * 10**8, 10**9)       # the node/harness reconstruction (plan v4 section 1)
    return sec + nanosec * 1e-9


@pytest.mark.parametrize(
    "stamp, move_at",
    [
        (_t, 28),               # 4.3 - 2.8000000000000003 = 1.4999999999999996
        (_header_stamp, 8),     # 2.3 - 0.8 = 1.4999999999999998
    ],
    ids=["i*0.1", "header"],
)
def test_window_boundary_is_inclusive_under_both_stamp_sources(stamp, move_at):
    """The two window comparisons use the 1e-6 s stamp epsilon: at a stamp pair whose float difference
    falls just short of W, the sample exactly W old becomes the straddling sample (its predecessor is
    popped) and the window counts as covered. Without the epsilon the track moved at `move_at` stays
    at 0 one scan longer; dropping it from either comparison alone breaks this test (the pop keeps the
    pre-move sample, or the coverage check rejects the window)."""
    tracker = Tracker(_config())
    for i in range(move_at):                                  # at SPOT
        tracker.update([_cluster(*SPOT)], stamp(i))
    elsewhere = (SPOT[0] + 0.45, SPOT[1])                     # moved: inside the gate, outside D
    for i in range(move_at, move_at + 15):
        tracker.update([_cluster(*elsewhere)], stamp(i))
        assert _only(tracker).stillness_s == pytest.approx(0.0, abs=1e-9), stamp(i)
    tracker.update([_cluster(*elsewhere)], stamp(move_at + 15))
    track = _only(tracker)
    assert track.track_id == 1
    assert track.still_since_s == pytest.approx(stamp(move_at), abs=1e-9)
    assert track.stillness_s == pytest.approx(1.5, abs=1e-9)


def test_legacy_mode_keeps_only_the_spawn_sample():
    """Open-gaps #5 resolved: the history grows only when the window is on (memory stays O(1) per track
    in the default configuration; the harness deep-copies every track on every scan)."""
    tracker = Tracker(_config(still_window_s=0.0))
    for i in range(200):
        tracker.update([_cluster(*SPOT)], _t(i))
    track = _only(tracker)
    assert len(track.position_history) == 1
    assert track.still_since_s is None
    assert track.stillness_s == pytest.approx(19.9, abs=1e-9)     # legacy accrual: 199 global dt of 0.1 s


def test_window_history_is_bounded():
    tracker = Tracker(_config())
    for i in range(200):
        tracker.update([_cluster(*SPOT)], _t(i))
    # W / 0.1 s = 15 samples inside the window plus the straddling one
    assert len(_only(tracker).position_history) == 16


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
