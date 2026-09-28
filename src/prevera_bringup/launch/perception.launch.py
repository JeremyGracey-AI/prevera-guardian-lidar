"""Lidar + fall detector, no SLAM.

Minimum runtime configuration for fall detection on a sentinel unit
where you don't need a persistent map.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory("prevera_bringup"))
    detector_params = bringup_share / "config" / "fall_detector.yaml"

    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(bringup_share / "launch" / "lidar.launch.py")
            ),
        ),
        Node(
            package="prevera_perception",
            executable="fall_detector",
            name="fall_detector",
            output="screen",
            parameters=[str(detector_params)],
        ),
    ])
