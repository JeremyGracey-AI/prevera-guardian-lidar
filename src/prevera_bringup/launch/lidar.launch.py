"""Bring up the RPLIDAR C1 driver only.

Uses Slamtec's official `sllidar_ros2` driver. Expects the device to
appear at `/dev/rplidar` (symlinked by the bundled udev rule) or
`/dev/ttyUSB0` as a fallback.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg = Path(get_package_share_directory("prevera_bringup"))
    config = pkg / "config" / "rplidar_c1.yaml"

    serial_port = LaunchConfiguration("serial_port")

    return LaunchDescription([
        DeclareLaunchArgument(
            "serial_port",
            default_value="/dev/rplidar",
            description="Serial device for the RPLIDAR C1 (udev rule creates /dev/rplidar).",
        ),
        Node(
            package="sllidar_ros2",
            executable="sllidar_node",
            name="sllidar_node",
            output="screen",
            parameters=[
                str(config),
                {"serial_port": serial_port},
            ],
        ),
    ])
