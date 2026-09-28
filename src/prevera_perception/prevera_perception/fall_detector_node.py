"""Main fall detector node: a thin rclpy adapter around `detector_core.DetectorCore`.

Per scan:
    LaserScan -> DetectorCore.process(ranges, angle_min, angle_increment, stamp_s)
              -> PersonTrackArray on `tracks`, one FallEvent per event on `fall_events`

The pipeline and the geometric heuristic live in `detector_core.py` (shared with the
offline replay harness). Parameters are declared here and parsed into a
`DetectorConfig`; `frame_id` stays in the node.
"""

from __future__ import annotations

import numpy as np
import rclpy
from geometry_msgs.msg import Point, Vector3
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles
from sensor_msgs.msg import LaserScan

from prevera_msgs.msg import FallEvent, PersonTrack, PersonTrackArray

from .background import BackgroundConfig
from .clustering import ClusterConfig
from .detector_core import ALERT_NAMES, DetectorConfig, DetectorCore, Event, FallConfig
from .tracker import Track, TrackerConfig


class FallDetectorNode(Node):

    def __init__(self) -> None:
        super().__init__("fall_detector")

        self._declare_parameters()
        config = self._read_parameters()

        self._frame_id = self.get_parameter("frame_id").value
        self._core = DetectorCore(config)

        self.create_subscription(
            LaserScan, "scan", self._on_scan, QoSPresetProfiles.SENSOR_DATA.value
        )
        self._track_pub = self.create_publisher(PersonTrackArray, "tracks", 10)
        self._event_pub = self.create_publisher(FallEvent, "fall_events", 10)

        self.get_logger().info(
            f"Fall detector up. Background warmup: {config.background.warmup_scans} scans."
        )

    # ------------------------------------------------------------------ params

    def _declare_parameters(self) -> None:
        self.declare_parameter("frame_id", "laser")
        self.declare_parameter("min_range_m", 0.05)
        self.declare_parameter("max_range_m", 10.0)

        self.declare_parameter("background.window_size", 40)
        self.declare_parameter("background.warmup_scans", 30)
        self.declare_parameter("background.foreground_margin_m", 0.15)
        self.declare_parameter("background.hold_foreground", True)
        self.declare_parameter("background.max_hold_scans", 1200)
        self.declare_parameter("background.mask_dilation_beams", 2)

        self.declare_parameter("cluster.eps_m", 0.12)
        self.declare_parameter("cluster.min_samples", 4)
        self.declare_parameter("cluster.min_points_per_cluster", 6)

        self.declare_parameter("tracker.association_gate_m", 0.5)
        self.declare_parameter("tracker.max_missed_scans", 15)
        self.declare_parameter("tracker.velocity_window", 10)
        self.declare_parameter("tracker.still_velocity_mps", 0.15)

        self.declare_parameter("fall.elongation_ratio", 3.5)
        self.declare_parameter("fall.major_axis_m", 0.6)
        self.declare_parameter("fall.velocity_spike_mps", 0.8)
        self.declare_parameter("fall.sustained_down_s", 4.0)

    def _read_parameters(self) -> DetectorConfig:
        return DetectorConfig(
            min_range_m=float(self.get_parameter("min_range_m").value),
            max_range_m=float(self.get_parameter("max_range_m").value),
            background=BackgroundConfig(
                window_size=int(self.get_parameter("background.window_size").value),
                warmup_scans=int(self.get_parameter("background.warmup_scans").value),
                foreground_margin_m=float(self.get_parameter("background.foreground_margin_m").value),
                hold_foreground=bool(self.get_parameter("background.hold_foreground").value),
                max_hold_scans=int(self.get_parameter("background.max_hold_scans").value),
                mask_dilation_beams=int(self.get_parameter("background.mask_dilation_beams").value),
            ),
            cluster=ClusterConfig(
                eps_m=float(self.get_parameter("cluster.eps_m").value),
                min_samples=int(self.get_parameter("cluster.min_samples").value),
                min_points_per_cluster=int(self.get_parameter("cluster.min_points_per_cluster").value),
            ),
            tracker=TrackerConfig(
                association_gate_m=float(self.get_parameter("tracker.association_gate_m").value),
                max_missed_scans=int(self.get_parameter("tracker.max_missed_scans").value),
                velocity_window=int(self.get_parameter("tracker.velocity_window").value),
                still_velocity_mps=float(self.get_parameter("tracker.still_velocity_mps").value),
            ),
            fall=FallConfig(
                elongation_ratio=float(self.get_parameter("fall.elongation_ratio").value),
                major_axis_m=float(self.get_parameter("fall.major_axis_m").value),
                velocity_spike_mps=float(self.get_parameter("fall.velocity_spike_mps").value),
                sustained_down_s=float(self.get_parameter("fall.sustained_down_s").value),
            ),
        )

    # ------------------------------------------------------------------ scan callback

    def _on_scan(self, msg: LaserScan) -> None:
        ranges = np.asarray(msg.ranges, dtype=np.float32)
        stamp_s = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        result = self._core.process(ranges, msg.angle_min, msg.angle_increment, stamp_s)
        if result is None:
            return

        self._publish_tracks(result.tracks, msg)
        for event in result.events:
            self._publish_event(event, msg)

    # ------------------------------------------------------------------ publishers

    def _publish_tracks(self, tracks: list[Track], scan: LaserScan) -> None:
        array = PersonTrackArray()
        array.header.stamp = scan.header.stamp
        array.header.frame_id = self._frame_id
        array.tracks = [self._track_to_msg(t, scan) for t in tracks]
        self._track_pub.publish(array)

    def _track_to_msg(self, track: Track, scan: LaserScan) -> PersonTrack:
        msg = PersonTrack()
        msg.header.stamp = scan.header.stamp
        msg.header.frame_id = self._frame_id
        msg.track_id = track.track_id
        msg.centroid = Point(x=float(track.centroid[0]), y=float(track.centroid[1]), z=0.0)
        msg.velocity = Vector3(
            x=float(track.last_velocity[0]), y=float(track.last_velocity[1]), z=0.0
        )
        msg.horizontal_extent_m = float(track.major_axis_m)
        msg.elongation_ratio = float(track.elongation)
        msg.age_s = float(track.age_s)
        msg.is_still = track.stillness_s > 0.0
        return msg

    def _publish_event(self, ev: Event, scan: LaserScan) -> None:
        event = FallEvent()
        event.header.stamp = scan.header.stamp
        event.header.frame_id = self._frame_id
        event.track_id = ev.track_id
        event.alert_level = int(ev.level)
        event.confidence = ev.confidence
        event.location = Point(x=ev.x, y=ev.y, z=0.0)
        event.horizontal_extent_m = ev.major_axis_m
        event.elongation_ratio = float(ev.elongation)
        event.stillness_duration_s = ev.stillness_s
        event.preceding_velocity_mps = ev.peak_recent_velocity
        event.vjepa_confidence = float("nan")
        self._event_pub.publish(event)

        level_name = ALERT_NAMES.get(ev.level, str(int(ev.level)))
        self.get_logger().warn(
            f"[{level_name}] track={ev.track_id} conf={ev.confidence:.2f} "
            f"major={ev.major_axis_m:.2f}m elong={ev.elongation:.1f} "
            f"still={ev.stillness_s:.1f}s peak_v={ev.peak_recent_velocity:.2f}m/s"
        )


def main() -> None:
    rclpy.init()
    node = FallDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
