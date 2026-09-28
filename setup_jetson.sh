#!/usr/bin/env bash
# PREVERA GUARDIAN+AI - Jetson Orin Nano setup
#
# Target: JetPack 6.2 / Ubuntu 22.04 / ROS 2 Humble
#
# Idempotent: safe to re-run. Each step checks state before acting.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

say() { echo -e "\n\033[1;36m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
die() { echo -e "\033[1;31m[x] $*\033[0m" >&2; exit 1; }

# --------------------------------------------------------------- preflight
[[ -f /etc/os-release ]] || die "Cannot detect OS."
. /etc/os-release
[[ "${VERSION_ID:-}" == "22.04" ]] || warn "Expected Ubuntu 22.04; got ${VERSION_ID}. Continuing."

if ! command -v ros2 >/dev/null 2>&1; then
    die "ROS 2 not found. Install ROS 2 Humble first:
  https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html
Then re-run this script."
fi

# --------------------------------------------------------------- apt deps
say "Installing system packages"
sudo apt-get update
sudo apt-get install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    git \
    ros-humble-slam-toolbox \
    ros-humble-robot-state-publisher \
    ros-humble-xacro \
    ros-humble-rviz2 \
    ros-humble-nav2-map-server

# --------------------------------------------------------------- python deps
say "Installing Python deps"
# numpy stays on 1.x: the Jetson runs Python 3.10 with apt numpy/scikit-learn, and the test suite enforces
# that floor (src/prevera_perception/test/test_python_floor.py; tools/bag_analysis/requirements.txt).
pip3 install --user --upgrade 'numpy<2' scikit-learn

# --------------------------------------------------------------- rosdep
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    say "Initializing rosdep"
    sudo rosdep init || true
fi
rosdep update

# --------------------------------------------------------------- sllidar_ros2
SLLIDAR_DIR="src/sllidar_ros2"
if [[ ! -d "$SLLIDAR_DIR" ]]; then
    say "Cloning Slamtec sllidar_ros2"
    git clone --depth 1 https://github.com/Slamtec/sllidar_ros2.git "$SLLIDAR_DIR"
else
    say "sllidar_ros2 already cloned; pulling latest"
    git -C "$SLLIDAR_DIR" pull --ff-only || warn "Could not fast-forward sllidar_ros2."
fi

# --------------------------------------------------------------- udev rule
UDEV_SRC="src/prevera_bringup/udev/99-rplidar.rules"
UDEV_DST="/etc/udev/rules.d/99-rplidar.rules"
if [[ ! -f "$UDEV_DST" ]] || ! cmp -s "$UDEV_SRC" "$UDEV_DST"; then
    say "Installing RPLIDAR udev rule"
    sudo cp "$UDEV_SRC" "$UDEV_DST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

# --------------------------------------------------------------- dialout group
if ! id -nG "$USER" | grep -qw dialout; then
    say "Adding $USER to dialout group (log out + back in to take effect)"
    sudo usermod -aG dialout "$USER"
fi

# --------------------------------------------------------------- rosdep deps
say "Resolving ROS package dependencies"
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y || warn "rosdep reported unresolved keys; review above."

# --------------------------------------------------------------- build
say "Building workspace"
colcon build --symlink-install

cat <<EOF

==============================================================================
 PREVERA GUARDIAN+AI workspace built.

 To use it, source the workspace in every shell:
     source $SCRIPT_DIR/install/setup.bash

 Add this to your ~/.bashrc to make it automatic:
     echo "source $SCRIPT_DIR/install/setup.bash" >> ~/.bashrc

 Hardware-free quick test (no RPLIDAR required):
     ros2 launch prevera_perception synthetic_dev.launch.py

 With the RPLIDAR C1 connected:
     ros2 launch prevera_bringup perception.launch.py

 Full stack (SLAM + detector + RViz on a desktop):
     ros2 launch prevera_bringup guardian.launch.py enable_rviz:=true

 If you were just added to the dialout group, log out and back in
 before attempting to open the RPLIDAR serial device.
==============================================================================
EOF
