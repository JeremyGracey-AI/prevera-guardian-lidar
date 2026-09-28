"""The only test that executes `FallDetectorNode`: its published events equal `DetectorCore`.

Needs rclpy plus the built `prevera_msgs` (OMEN WSL, Jetson); skipped where rclpy is absent
(this Mac). Plan v4 step 2, round-3 design: one executor for both nodes, KEEP_ALL reliable
subscriptions on the test side, lockstep publish-then-drain so every scan (warm-up included)
is consumed before the next is published.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pytest

rclpy = pytest.importorskip("rclpy")

from rclpy.executors import SingleThreadedExecutor, TimeoutException  # noqa: E402
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy  # noqa: E402
from sensor_msgs.msg import LaserScan  # noqa: E402

from prevera_msgs.msg import FallEvent, PersonTrackArray  # noqa: E402

from prevera_perception.detector_core import DetectorCore  # noqa: E402
from prevera_perception.fall_detector_node import FallDetectorNode  # noqa: E402
from prevera_perception.synthetic_scene import SyntheticScene, overrides_v3  # noqa: E402

Y = Path(__file__).resolve().parents[3] / "src" / "prevera_bringup" / "config" / "fall_detector.yaml"
N_SCANS = 160
WARMUP = 30  # background.warmup_scans in Y; scan index 30 is the first that publishes
DISCOVERY_TIMEOUT_S = 5.0
PER_SCAN_DEADLINE_S = 1.0
QUIET_S = 0.5


def _stamp(i: int) -> tuple[int, int]:
    return divmod(i * 10**8, 10**9)


def _scan_msg(i: int, ranges: np.ndarray) -> LaserScan:
    msg = LaserScan()
    sec, nanosec = _stamp(i)
    msg.header.stamp.sec = sec
    msg.header.stamp.nanosec = nanosec
    msg.header.frame_id = "laser"
    msg.angle_min = SyntheticScene.ANGLE_MIN
    msg.angle_max = math.pi
    msg.angle_increment = SyntheticScene.ANGLE_INCREMENT
    msg.time_increment = 0.0
    msg.scan_time = 0.1
    msg.range_min = 0.05
    msg.range_max = SyntheticScene.RANGE_MAX
    msg.ranges = ranges.tolist()
    msg.intensities = []
    return msg


def _drain_until_idle(executor: SingleThreadedExecutor) -> None:
    while True:
        try:
            handler, *_ = executor.wait_for_ready_callbacks(timeout_sec=0.1)
        except TimeoutException:
            return
        handler()
        if handler.exception() is not None:
            raise handler.exception()


def test_node_adapter_matches_core():
    rclpy.init(args=["--ros-args", "--params-file", str(Y)])
    detector = test_node = executor = None
    try:
        detector = FallDetectorNode()
        test_node = rclpy.create_node("adapter_test")
        pub_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10)
        sub_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_ALL)
        scan_pub = test_node.create_publisher(LaserScan, "/scan", pub_qos)
        tracks_msgs: list = []
        events_msgs: list = []
        test_node.create_subscription(PersonTrackArray, "/tracks", tracks_msgs.append, sub_qos)
        test_node.create_subscription(FallEvent, "/fall_events", events_msgs.append, sub_qos)

        executor = SingleThreadedExecutor()
        executor.add_node(detector)
        executor.add_node(test_node)

        deadline = time.monotonic() + DISCOVERY_TIMEOUT_S
        while (
            scan_pub.get_subscription_count() < 1
            or detector._track_pub.get_subscription_count() < 1
            or detector._event_pub.get_subscription_count() < 1
        ):
            assert time.monotonic() < deadline, "discovery timed out"
            executor.spin_once(timeout_sec=0.1)

        scene = SyntheticScene(np.random.default_rng(42))
        scans = [scene.build_scan(i * 0.1, overrides_v3(i)) for i in range(N_SCANS)]

        first_deadline_expired: int | None = None
        for i, ranges in enumerate(scans):
            scan_pub.publish(_scan_msg(i, ranges))
            _drain_until_idle(executor)  # scan i consumed by _on_scan before scan i+1
            if i >= WARMUP:
                per_scan_deadline = time.monotonic() + PER_SCAN_DEADLINE_S
                while len(tracks_msgs) < i - WARMUP + 1:
                    if time.monotonic() >= per_scan_deadline:
                        if first_deadline_expired is None:
                            first_deadline_expired = i
                        break
                    executor.spin_once(timeout_sec=0.05)

        seen = len(events_msgs)
        quiet_until = time.monotonic() + QUIET_S
        while time.monotonic() < quiet_until:
            executor.spin_once(timeout_sec=0.05)
            if len(events_msgs) != seen:
                seen = len(events_msgs)
                quiet_until = time.monotonic() + QUIET_S

        # Reference: the node's own parsed config; angle scalars as the node receives them
        # (float32 on the wire), stamps reconstructed from the header ints.
        cfg = detector._read_parameters()
        reference = DetectorCore(cfg)
        angle_min = float(np.float32(SyntheticScene.ANGLE_MIN))
        angle_increment = float(np.float32(SyntheticScene.ANGLE_INCREMENT))
        expected: list[tuple] = []
        for i, ranges in enumerate(scans):
            sec, nanosec = _stamp(i)
            result = reference.process(ranges, angle_min, angle_increment, sec + nanosec * 1e-9)
            if result is None:
                continue
            stamp_ns = sec * 10**9 + nanosec
            for ev in result.events:
                expected.append((
                    stamp_ns, ev.track_id, int(ev.level),
                    float(np.float32(ev.confidence)), float(np.float32(ev.elongation)),
                ))

        assert len(tracks_msgs) == N_SCANS - WARMUP, (
            f"{len(tracks_msgs)} /tracks messages, first deadline-expired scan index: {first_deadline_expired}"
        )
        observed = [
            (m.header.stamp.sec * 10**9 + m.header.stamp.nanosec, m.track_id, m.alert_level, m.confidence, m.elongation_ratio)
            for m in events_msgs
        ]
        assert observed == expected

        line_events = [m for m in events_msgs if math.hypot(m.location.x - 1.0, m.location.y + 0.06) <= 0.1]
        if cfg.fall.degenerate_requires_extent:
            # Non-finite elongation with major 0.061 < fall.major_axis_m: the line emits nothing.
            assert line_events == []
        else:
            assert line_events and all(m.elongation_ratio == 1e6 for m in line_events)
    finally:
        if executor is not None:
            executor.shutdown()
        if test_node is not None:
            test_node.destroy_node()
        if detector is not None:
            detector.destroy_node()
        rclpy.shutdown()
