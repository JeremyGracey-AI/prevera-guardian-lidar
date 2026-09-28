"""Launch the fall detector alongside a synthetic scan publisher.

This is the hardware-free development path: no RPLIDAR required.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg = Path(get_package_share_directory("prevera_bringup"))
    detector_params = pkg / "config" / "fall_detector.yaml"

    return LaunchDescription([
        Node(
            package="prevera_perception",
            executable="synthetic_publisher",
            name="synthetic_scan_publisher",
            output="screen",
        ),
        Node(
            package="prevera_perception",
            executable="fall_detector",
            name="fall_detector",
            output="screen",
            parameters=[str(detector_params)],
        ),
    ])
