"""Synthetic LaserScan publisher for hardware-free development.

Publishes the ROS-free `SyntheticScene` (synthetic_scene.py) as a 10 Hz
`/scan`: an empty room with a single "person" who walks, falls and stays
down (see that module's docstring for the phases).

Use this to exercise the detector without the RPLIDAR connected:

    ros2 run prevera_perception synthetic_publisher
    ros2 run prevera_perception fall_detector

You should see an OBSERVE event as the person walks, a WARN when
the fall is simulated, and sustained WARN while they remain down.
"""

from __future__ import annotations

import math
import time

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from prevera_perception.synthetic_scene import SyntheticScene


class SyntheticScanPublisher(Node):

    def __init__(self) -> None:
        super().__init__("synthetic_scan_publisher")
        self._pub = self.create_publisher(LaserScan, "scan", 10)
        self._start = time.monotonic()
        self._scene = SyntheticScene(np.random.default_rng(seed=42))
        self.create_timer(0.1, self._tick)  # 10 Hz
        self.get_logger().info("Synthetic scan publisher running on /scan")

    def _tick(self) -> None:
        t = time.monotonic() - self._start
        ranges = self._build_scan(t)
        self._pub.publish(self._to_message(ranges))

    def _build_scan(self, t: float) -> np.ndarray:
        return self._scene.build_scan(t)

    def _to_message(self, ranges: np.ndarray) -> LaserScan:
        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
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


def main() -> None:
    rclpy.init()
    node = SyntheticScanPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
