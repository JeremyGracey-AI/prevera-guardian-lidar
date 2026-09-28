"""Unit tests for the centroid tracker."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from prevera_perception.background import Background
from prevera_perception.clustering import Cluster, cluster_points
from prevera_perception.detector_core import DetectorCore
from prevera_perception.synthetic_scene import SyntheticScene, overrides_v3
from prevera_perception.tracker import Tracker, TrackerConfig

# Same precedent as test_incident_hold.py: reuse the frozen legacy config of test_detector_core
# (hardcoded there, never read from the yaml, so later config commits cannot move it). Not
# test_synthetic_fall's BG/CL/TR: those mirror the yaml and plan v4 steps 6 and 9 rework that module,
# which must never be a reason to regenerate this golden.
from test_detector_core import CONFIG as CORE_LEGACY_CONFIG


CONFIG = TrackerConfig(
    association_gate_m=0.5,
    max_missed_scans=5,
    velocity_window=5,
    still_velocity_mps=0.15,
)

# Plan v4 step 5: every new test uses the yaml tracker values (Y:21-24). Under CONFIG
# (max_missed_scans=5) a spawned track (missed_scans == 1, the kept legacy quirk) is evicted by the
# fifth empty update, so a reacquisition 0.6 s after spawn would see a fresh id.
CONFIG15 = TrackerConfig(association_gate_m=0.5, max_missed_scans=15, velocity_window=10, still_velocity_mps=0.15)

# Per-scan tracker state captured at 337641f (before plan v4 step 5) by the two drivers below.
# The plain-scene driver is test_synthetic_fall.py's `_run` pipeline; its configs at capture time
# were field-for-field CORE_LEGACY_CONFIG.background / .cluster and CONFIG15.
LEGACY_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "tracker_legacy_scenes.json"
SCENE_SCANS = 160
SCENE_ANGLES = SyntheticScene.ANGLE_MIN + np.arange(SyntheticScene.NUM_BEAMS) * SyntheticScene.ANGLE_INCREMENT


def _cluster(x: float, y: float, major: float = 0.2, minor: float = 0.15, point_count: int = 20) -> Cluster:
    return Cluster(
        centroid=np.array([x, y], dtype=np.float32),
        point_count=point_count,
        major_axis_m=major,
        minor_axis_m=minor,
    )


def test_new_cluster_spawns_track():
    tracker = Tracker(CONFIG)
    tracks = tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    assert len(tracks) == 1


def test_nearby_cluster_associates_to_same_track():
    tracker = Tracker(CONFIG)
    t0 = tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    t1 = tracker.update([_cluster(1.1, 0.05)], stamp_s=0.1)
    assert t0[0].track_id == t1[0].track_id


def test_missing_track_ages_out():
    tracker = Tracker(CONFIG)
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    for i in range(CONFIG.max_missed_scans + 1):
        tracker.update([], stamp_s=0.1 * (i + 1))
    assert tracker.tracks == []


def test_velocity_spike_is_recorded():
    tracker = Tracker(CONFIG)
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.1)
    tracker.update([_cluster(1.15, 0.0)], stamp_s=0.2)  # 1.5 m/s spike
    [track] = tracker.tracks
    assert track.peak_recent_velocity >= 1.0


# --------------------------------------------------------------------------- legacy golden (plan v4 step 5)


def _track_row(track) -> list:
    """[id, cx, cy, stillness_s, peak_recent_velocity, missed_scans, age_s] of one track."""
    return [
        int(track.track_id),
        float(track.centroid[0]),
        float(track.centroid[1]),
        float(track.stillness_s),
        float(track.peak_recent_velocity),
        int(track.missed_scans),
        float(track.age_s),
    ]


def _plain_scene_rows(tracker: Tracker | None = None) -> list:
    """Per-scan tracker state on the plain synthetic scene (test_synthetic_fall.py `_run`, 160 scans)."""
    scene, bg = SyntheticScene(np.random.default_rng(42)), Background(CORE_LEGACY_CONFIG.background)
    tracker = tracker if tracker is not None else Tracker(CONFIG15)
    rows = []
    for i in range(SCENE_SCANS):
        t = i * 0.1
        ranges = scene.build_scan(t)
        if not bg.ready:
            bg.update(ranges)
            continue
        fg = bg.foreground_mask(ranges)
        bg.update(ranges, foreground=fg)
        pts = np.stack([ranges[fg] * np.cos(SCENE_ANGLES[fg]), ranges[fg] * np.sin(SCENE_ANGLES[fg])], axis=1)
        tracks = tracker.update(cluster_points(pts.astype(np.float32), CORE_LEGACY_CONFIG.cluster), t)
        rows.append([i, [_track_row(tr) for tr in tracks]])
    return rows


def _v3_scene_rows(core: DetectorCore | None = None) -> list:
    """Per-scan tracker state on override set v3 through DetectorCore under the frozen legacy config."""
    scene = SyntheticScene(np.random.default_rng(42))
    core = core if core is not None else DetectorCore(CORE_LEGACY_CONFIG)
    rows = []
    for i in range(SCENE_SCANS):
        t = i * 0.1
        result = core.process(
            scene.build_scan(t, overrides_v3(i)), SyntheticScene.ANGLE_MIN, SyntheticScene.ANGLE_INCREMENT, t
        )
        if result is None:
            continue
        rows.append([i, [_track_row(tr) for tr in result.tracks]])
    return rows


def _assert_rows_match(actual: list, expected: list, label: str) -> None:
    assert [i for i, _ in actual] == [i for i, _ in expected], label
    for (i, got), (_, want) in zip(actual, expected):
        assert [r[0] for r in got] == [r[0] for r in want], (label, i)      # ids and their order, exact
        for g, w in zip(got, want):
            assert g[5] == w[5], (label, i, g, w)                             # missed_scans, exact
            assert g[1:3] == pytest.approx(w[1:3], abs=1e-6), (label, i)      # float32 centroid
            assert g[3] == pytest.approx(w[3], abs=1e-9), (label, i)          # stillness_s
            assert g[4] == pytest.approx(w[4], rel=1e-6), (label, i)          # peak_recent_velocity
            assert g[6] == pytest.approx(w[6], abs=1e-9), (label, i)          # age_s


def _v3_spawn_log() -> list:
    """(scan_index, SpawnRecord) for every spawn on the override-set-v3 run under the legacy config."""
    scene, core = SyntheticScene(np.random.default_rng(42)), DetectorCore(CORE_LEGACY_CONFIG)
    spawns = []
    for i in range(SCENE_SCANS):
        t = i * 0.1
        result = core.process(
            scene.build_scan(t, overrides_v3(i)), SyntheticScene.ANGLE_MIN, SyntheticScene.ANGLE_INCREMENT, t
        )
        if result is not None:
            spawns.extend((i, rec) for rec in core.tracker.spawn_log)
    return spawns


def test_legacy_defaults_unchanged():
    """A default-config Tracker reproduces the per-scan state captured before plan v4 step 5."""
    golden = json.loads(LEGACY_GOLDEN_PATH.read_text(encoding="utf-8"))
    _assert_rows_match(_plain_scene_rows(), golden["plain_scene"], "plain_scene")
    _assert_rows_match(_v3_scene_rows(), golden["override_set_v3"], "override_set_v3")

    # spawn_log on the v3 run agrees with the harness's outside classification
    # (test_replay_harness.py::test_spawn_diagnostics_outside_classification): the person spawns at
    # 3.5 s with no live track; the line spawns at 4.0 s while the person (matched in that scan by
    # the earlier cluster) is the nearest live track, beyond the 0.5 m gate.
    spawns = _v3_spawn_log()
    assert [(i, rec.track_id, rec.path) for i, rec in spawns] == [(35, 1, "no-candidate"), (40, 2, "gate-fail")]
    person, line = spawns[0][1], spawns[1][1]
    assert person.nearest_live_id is None and person.nearest_live_m is None
    assert person.nearest_live_was_matched is None
    assert line.nearest_live_id == 1 and line.nearest_live_m > 0.5 and line.nearest_live_was_matched is True
    assert np.hypot(line.cluster_centroid[0] - 1.0, line.cluster_centroid[1] + 0.06) <= 0.1
    for _, rec in spawns:
        assert rec.nearest_tomb_id is None and rec.nearest_tomb_m is None and rec.scans_since_nearest_seen is None


# --------------------------------------------------------------------------- step 5: per-track dt + speed gate


def test_association_jump_rejected():
    gated = Tracker(dataclasses.replace(CONFIG15, max_association_speed_mps=3.0))
    gated.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    [spawned] = gated.tracks
    assert spawned.missed_scans == 1                       # legacy quirk: the spawn scan counts as a miss
    assert [(r.track_id, r.path) for r in gated.spawn_log] == [(1, "no-candidate")]

    gated.update([_cluster(1.4, 0.0)], stamp_s=0.1)         # 0.4 m in 0.1 s = 4 m/s, inside the 0.5 m gate
    old, new = sorted(gated.tracks, key=lambda t: t.track_id)
    assert (old.track_id, new.track_id) == (1, 2)
    assert old.missed_scans == 2 and old.peak_recent_velocity == 0.0
    assert new.missed_scans == 1
    [rec] = gated.spawn_log
    assert (rec.track_id, rec.path) == (2, "speed-gate")
    assert rec.nearest_live_id == 1 and rec.nearest_live_was_matched is False
    assert rec.nearest_live_m == pytest.approx(0.4, rel=1e-6)
    assert rec.cluster_centroid.tolist() == pytest.approx([1.4, 0.0], rel=1e-6)

    ungated = Tracker(CONFIG15)                               # max_association_speed_mps == 0: off
    ungated.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    ungated.update([_cluster(1.4, 0.0)], stamp_s=0.1)
    [track] = ungated.tracks
    assert track.track_id == 1
    assert track.peak_recent_velocity == pytest.approx(4.0, rel=1e-6)     # float32: 3.999999761581421
    assert ungated.spawn_log == []


@pytest.mark.parametrize(
    "per_track_dt, max_speed, expected_speed",
    [
        (True, 3.0, 0.5),     # 0.3 m over the 0.6 s since the track was last seen (float32: 0.49999991059303284)
        (False, 0.0, 3.0),    # legacy: 0.3 m over the global 0.1 s dt (float32: 2.999999523162842)
    ],
)
def test_reacquire_after_miss_uses_per_track_dt(per_track_dt, max_speed, expected_speed):
    tracker = Tracker(dataclasses.replace(CONFIG15, per_track_dt=per_track_dt, max_association_speed_mps=max_speed))
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    for i in range(1, 6):
        tracker.update([], stamp_s=i * 0.1)
    [track] = tracker.tracks
    assert track.missed_scans == 6                           # alive under max_missed_scans=15
    tracker.update([_cluster(1.3, 0.0)], stamp_s=6 * 0.1)
    [track] = tracker.tracks
    assert track.track_id == 1
    assert track.peak_recent_velocity == pytest.approx(expected_speed, rel=1e-6)
    assert float(np.linalg.norm(track.last_velocity)) == pytest.approx(expected_speed, rel=1e-6)


def test_speed_gate_falls_through_to_next_candidate():
    tracker = Tracker(dataclasses.replace(CONFIG15, per_track_dt=True, max_association_speed_mps=3.0))
    tracker.update([_cluster(0.0, 0.0), _cluster(0.75, 0.0)], stamp_s=0.0)
    a, b = sorted(tracker.tracks, key=lambda t: t.track_id)
    assert (a.track_id, b.track_id) == (1, 2) and a.missed_scans == 1 and b.missed_scans == 1
    assert [(r.track_id, r.path) for r in tracker.spawn_log] == [(1, "no-candidate"), (2, "gate-fail")]

    for i in range(1, 10):                                   # t = 0.1 .. 0.9: A matched, B misses
        tracker.update([_cluster(0.0, 0.0)], stamp_s=i * 0.1)
    assert a.missed_scans == 0 and b.missed_scans == 10

    # t = 1.0: A is nearest (0.35 m, dt_track 0.1 s -> 3.5 m/s, rejected); B at 0.40 m <= gate with
    # dt_track 1.0 s -> 0.4 m/s, accepted.
    tracker.update([_cluster(0.35, 0.0)], stamp_s=10 * 0.1)
    assert tracker.spawn_log == []
    assert len(tracker.tracks) == 2
    assert b.missed_scans == 0
    assert np.array_equal(b.centroid, np.array([0.35, 0.0], dtype=np.float32))
    assert b.peak_recent_velocity == pytest.approx(0.4, rel=1e-6)
    assert a.missed_scans == 1
    assert np.array_equal(a.centroid, np.array([0.0, 0.0], dtype=np.float32))


@pytest.mark.parametrize("per_track_dt", [False, True])
def test_existing_spikes_pass_with_gate_on(per_track_dt):
    """Done-when: the 1.1-1.5 m/s moves of the four original tests still associate with the gate at 3.0."""
    config = dataclasses.replace(CONFIG, max_association_speed_mps=3.0, per_track_dt=per_track_dt)

    tracker = Tracker(config)                                # test_nearby_cluster_associates_to_same_track
    t0 = tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    t1 = tracker.update([_cluster(1.1, 0.05)], stamp_s=0.1)
    assert len(t1) == 1 and t0[0].track_id == t1[0].track_id

    tracker = Tracker(config)                                # test_velocity_spike_is_recorded
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.1)
    tracker.update([_cluster(1.15, 0.0)], stamp_s=0.2)
    [track] = tracker.tracks
    assert track.peak_recent_velocity >= 1.0
    assert tracker.spawn_log == []


@pytest.mark.parametrize(
    "per_track_dt, expected",
    [
        (True, 0.6),     # the whole gap since last_seen_s (stated consequence: published age_s jumps)
        (False, 0.1),    # legacy: the last global dt only
    ],
)
def test_per_track_dt_drives_age_and_legacy_stillness(per_track_dt, expected):
    tracker = Tracker(dataclasses.replace(CONFIG15, per_track_dt=per_track_dt))
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    [track] = tracker.tracks
    assert track.last_seen_s == pytest.approx(0.0, abs=1e-9)
    for i in range(1, 6):
        tracker.update([], stamp_s=i * 0.1)
    assert track.last_seen_s == pytest.approx(0.0, abs=1e-9)   # unmatched scans do not move it
    tracker.update([_cluster(1.0, 0.0)], stamp_s=6 * 0.1)     # reacquired at the same spot
    assert track.last_seen_s == pytest.approx(0.6, abs=1e-9)
    assert track.age_s == pytest.approx(expected, abs=1e-9)
    assert track.stillness_s == pytest.approx(expected, abs=1e-9)


def test_spawn_log_split_path_and_per_call_reset():
    """A second fragment of a matched track spawns as `split-like` (open-gaps #1); spawn_log is per call."""
    tracker = Tracker(CONFIG15)
    tracker.update([_cluster(3.0, 0.0)], stamp_s=0.0)
    tracker.update([_cluster(3.0, 0.05, point_count=30), _cluster(3.0, -0.15, point_count=8)], stamp_s=0.1)
    assert len(tracker.tracks) == 2
    [rec] = tracker.spawn_log
    assert (rec.track_id, rec.path) == (2, "split-like")
    assert rec.nearest_live_id == 1 and rec.nearest_live_was_matched is True
    assert rec.nearest_live_m == pytest.approx(0.2, rel=1e-6)   # to the track's centroid after its match
    tracker.update([_cluster(3.0, 0.05), _cluster(3.0, -0.15)], stamp_s=0.2)
    assert tracker.spawn_log == []                              # both matched: nothing spawned in this call


def test_spawn_log_matched_flag_is_end_of_update():
    """`nearest_live_was_matched` means matched in this scan, even by a cluster processed after the spawn."""
    tracker = Tracker(CONFIG15)
    tracker.update([_cluster(1.0, 0.0)], stamp_s=0.0)
    # the far cluster comes first in label order and spawns before the track's own cluster matches it
    tracker.update([_cluster(3.0, 0.0), _cluster(1.05, 0.0)], stamp_s=0.1)
    [rec] = tracker.spawn_log
    assert (rec.track_id, rec.path, rec.nearest_live_id) == (2, "gate-fail", 1)
    assert rec.nearest_live_m == pytest.approx(2.0, rel=1e-6)
    assert rec.nearest_live_was_matched is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
