"""Full PREVERA GUARDIAN+AI stack.

Brings up:
  * Sentinel URDF + TF tree
  * RPLIDAR C1 driver
  * slam_toolbox (online async)
  * Fall detector node
  * RViz2 with the guardian dashboard

This is the production bring-up for a sentinel unit. For hardware-free
development, use:

    ros2 launch prevera_perception synthetic_dev.launch.py
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory("prevera_bringup"))
    description_share = Path(get_package_share_directory("prevera_description"))

    detector_params = bringup_share / "config" / "fall_detector.yaml"
    slam_params = bringup_share / "config" / "slam_toolbox.yaml"
    rviz_config = bringup_share / "rviz" / "guardian.rviz"

    enable_slam = LaunchConfiguration("enable_slam")
    enable_rviz = LaunchConfiguration("enable_rviz")

    return LaunchDescription([
        DeclareLaunchArgument("enable_slam", default_value="true"),
        DeclareLaunchArgument("enable_rviz", default_value="false"),

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
            condition=IfCondition(enable_slam),
        ),
        Node(
            package="prevera_perception",
            executable="fall_detector",
            name="fall_detector",
            output="screen",
            parameters=[str(detector_params)],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", str(rviz_config)],
            condition=IfCondition(enable_rviz),
        ),
    ])
