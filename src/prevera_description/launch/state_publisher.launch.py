"""Publish the sentinel URDF to /tf for visualization and perception."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    pkg = Path(get_package_share_directory("prevera_description"))
    xacro = pkg / "urdf" / "sentinel.urdf.xacro"

    use_sim_time = LaunchConfiguration("use_sim_time")

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Use /clock from rosbag or simulation",
        ),
        DeclareLaunchArgument(
            "lidar_mount_height",
            default_value="0.02",
            description="Scan window height above the floor, metres; 0.65 draws the original mast rig",
        ),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{
                "use_sim_time": use_sim_time,
                # A string, declared as one: launch_ros sniffs a bare Command value with yaml.safe_load, which
                # rejects the URDF's header comment and raises TypeError.
                "robot_description": ParameterValue(
                    Command(["xacro ", str(xacro), " lidar_mount_height:=", LaunchConfiguration("lidar_mount_height")]),
                    value_type=str,
                ),
            }],
        ),
    ])
