"""Bring up RPLIDAR C1 + slam_toolbox online async mapping.

Produces a 2D occupancy grid on /map and publishes map->odom->base_link->laser
transforms. Keep this running while walking around the sentinel unit to
build the room map, then save it with:

    ros2 run nav2_map_server map_saver_cli -f ~/prevera_maps/room1
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory("prevera_bringup"))
    description_share = Path(get_package_share_directory("prevera_description"))

    slam_params = bringup_share / "config" / "slam_toolbox.yaml"

    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(description_share / "launch" / "state_publisher.launch.py")
            ),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(bringup_share / "launch" / "lidar.launch.py")
            ),
        ),
        Node(
            package="slam_toolbox",
            executable="async_slam_toolbox_node",
            name="slam_toolbox",
            output="screen",
            parameters=[str(slam_params)],
        ),
    ])
