#!/bin/bash
# 09-ros2-humble.sh - ROS 2 Humble base + bridges for GUARDIAN+AI. Run with sudo on the Jetson from the stack's account.
# Idempotent. Configures $SUDO_USER (dialout, ~/.bashrc, rosdep); workspace = $GUARDIAN_WS (default ~/prevera-guardian-lidar).
set -euo pipefail; U="${SUDO_USER:?run with sudo from the account that runs the stack}"; UH="$(getent passwd "$U" | cut -d: -f6)"; WS="${GUARDIAN_WS:-$UH/prevera-guardian-lidar}"
echo "START $(date) user=$U workspace=$WS"
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
# RPLIDAR udev rule (from the workspace: src/prevera_bringup/udev/99-rplidar.rules) + serial access
if [ -f "$WS/src/prevera_bringup/udev/99-rplidar.rules" ]; then cp "$WS/src/prevera_bringup/udev/99-rplidar.rules" /etc/udev/rules.d/99-rplidar.rules; udevadm control --reload-rules; udevadm trigger; fi
id -nG "$U" | grep -qw dialout || usermod -aG dialout "$U"
BRC="$UH/.bashrc"
grep -q 'ros/humble/setup.bash' "$BRC" || cat >> "$BRC" <<EOF

# ROS 2 Humble (added by 09-ros2-humble.sh)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=42
[ -f $WS/install/setup.bash ] && source $WS/install/setup.bash
EOF
chown "$U:$U" "$BRC"
sudo -u "$U" rosdep update || true
echo "DONE $(date)"
