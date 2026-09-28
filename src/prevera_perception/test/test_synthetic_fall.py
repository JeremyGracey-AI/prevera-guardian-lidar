"""End-to-end regression (no ROS): the synthetic fall must stay visible and trip the rules.

Before the foreground hold, the rolling median absorbed the fallen person after ~2 s,
so the 4 s sustained-down rule could never fire.
"""

import dataclasses

import numpy as np
import pytest
from prevera_perception.background import Background, BackgroundConfig
from prevera_perception.clustering import ClusterConfig, cluster_points
from prevera_perception.synthetic_scene import SyntheticScene
from prevera_perception.tracker import Tracker, TrackerConfig

# Same values as prevera_bringup/config/fall_detector.yaml.
BG = BackgroundConfig(window_size=40, warmup_scans=30, foreground_margin_m=0.15)
CL = ClusterConfig(eps_m=0.12, min_samples=4, min_points_per_cluster=6)
TR = TrackerConfig(association_gate_m=0.5, max_missed_scans=15, velocity_window=10, still_velocity_mps=0.15)
# Plan v4 step 6: windowed displacement stillness (0.25 m over 1.5 s); off in TR (legacy).
TR_WINDOW = dataclasses.replace(TR, still_window_s=1.5, still_displacement_m=0.25)
N = SyntheticScene.NUM_BEAMS
ANGLES = -np.pi + np.arange(N) * (2.0 * np.pi / N)


def _synthetic():
    # Scan geometry only, no ROS context: the scene is the publisher node's ROS-free core.
    return SyntheticScene(np.random.default_rng(42))


def _run(seconds: float, background_config: BackgroundConfig = BG, tracker_config: TrackerConfig = TR):
    pub, bg, tracker = _synthetic(), Background(background_config), Tracker(tracker_config)
    tracks = []
    for i in range(int(seconds * 10)):
        t = i * 0.1
        ranges = pub.build_scan(t)
        if not bg.ready:
            bg.update(ranges)
            continue
        fg = bg.foreground_mask(ranges)
        bg.update(ranges, foreground=fg)
        pts = np.stack([ranges[fg] * np.cos(ANGLES[fg]), ranges[fg] * np.sin(ANGLES[fg])], axis=1)
        tracks = tracker.update(cluster_points(pts.astype(np.float32), CL), t)
    return tracks


def _flat(track) -> bool:
    return track.elongation >= 3.5 and track.major_axis_m >= 0.8


@pytest.mark.parametrize("tracker_config", [TR, TR_WINDOW], ids=["legacy", "window"])
def test_fallen_person_stays_tracked_and_meets_sustained_down(tracker_config):
    tracks = _run(16.0, tracker_config=tracker_config)  # fall ends at 8.4 s -> ~7.5 s on the floor
    flat = [t for t in tracks if _flat(t)]
    assert flat, "fallen person was absorbed into the background"
    assert max(t.stillness_s for t in flat) >= 4.0


def test_without_hold_the_fallen_person_is_lost():
    no_hold = BackgroundConfig(window_size=40, warmup_scans=30, foreground_margin_m=0.15, hold_foreground=False)
    tracks = _run(16.0, no_hold)
    assert not [t for t in tracks if _flat(t) and t.stillness_s >= 4.0]