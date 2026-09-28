#!/bin/bash
# 09-ros2-humble.sh - ROS 2 Humble base + bridges for the GUARDIAN+AI Jetson. Run with sudo on the Jetson:
#   sudo GUARDIAN_WS=$HOME/prevera-guardian-lidar ./jetson/09-ros2-humble.sh
# Idempotent. Configures the invoking (sudo) user: dialout group, ~/.bashrc, rosdep.
# This is the install path the device was actually brought up with (2026-09-25); setup_jetson.sh is the
# workspace build script that runs afterwards.
set -euo pipefail
TARGET_USER="${SUDO_USER:?run this script with sudo from the account that will run the stack}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
GUARDIAN_WS="${GUARDIAN_WS:-$TARGET_HOME/prevera-guardian-lidar}"
echo "START $(date)  user=$TARGET_USER  workspace=$GUARDIAN_WS"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y software-properties-common curl gnupg lsb-release locales
locale-gen en_US en_US.UTF-8 && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
add-apt-repository -y universe
[ -f /usr/share/keyrings/ros-archive-keyring.gpg ] || curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main" > /etc/apt/sources.list.d/ros2.list
apt-get update
# ros-base (headless) + dev tools + demo pieces
apt-get install -y ros-humble-ros-base ros-dev-tools python3-colcon-common-extensions python3-rosdep python3-vcstool git \
  ros-humble-foxglove-bridge ros-humble-rosbag2-storage-mcap \
  ros-humble-slam-toolbox ros-humble-robot-state-publisher ros-humble-xacro ros-humble-nav2-map-server \
  ros-humble-demo-nodes-cpp ros-humble-rosbridge-suite python3-sklearn python3-pytest
[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || rosdep init
# RPLIDAR udev rule + serial access
UDEV_SRC="$GUARDIAN_WS/src/prevera_bringup/udev/99-rplidar.rules"
if [ -f "$UDEV_SRC" ]; then cp "$UDEV_SRC" /etc/udev/rules.d/99-rplidar.rules; udevadm control --reload-rules; udevadm trigger; fi
id -nG "$TARGET_USER" | grep -qw dialout || usermod -aG dialout "$TARGET_USER"
BRC="$TARGET_HOME/.bashrc"
grep -q 'ros/humble/setup.bash' "$BRC" || cat >> "$BRC" <<EOB

# ROS 2 Humble (added by 09-ros2-humble.sh)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=42
[ -f $GUARDIAN_WS/install/setup.bash ] && source $GUARDIAN_WS/install/setup.bash
EOB
chown "$TARGET_USER:$TARGET_USER" "$BRC"
sudo -u "$TARGET_USER" rosdep update || true
echo "DONE $(date)"
