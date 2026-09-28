#!/bin/bash
# guardian-up.sh: RPLIDAR + fall_detector + foxglove_bridge (:8765) + rosbridge (:9090), detached.
# Safe to re-run: refuses to start a second copy (two sllidar_nodes fight over /dev/rplidar and kill /scan).
# Logs in ~/guardian-logs/. Stop: ~/guardian-down.sh. Also runs at boot via crontab @reboot.
if pgrep -x sllidar_node >/dev/null; then echo "already running (sllidar_node up); run ~/guardian-down.sh first"; exit 0; fi
source /opt/ros/humble/setup.bash
# Workspace checkout (this repository, built with colcon). Override with GUARDIAN_WS=/path.
GUARDIAN_WS="${GUARDIAN_WS:-$HOME/prevera-guardian-lidar}"
source "$GUARDIAN_WS/install/setup.bash"
export ROS_DOMAIN_ID=42
mkdir -p ~/guardian-logs
setsid nohup ros2 launch prevera_bringup perception.launch.py > ~/guardian-logs/perception.log 2>&1 < /dev/null &
setsid nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 > ~/guardian-logs/foxglove.log 2>&1 < /dev/null &
if [ -d /opt/ros/humble/share/rosbridge_server ]; then
  setsid nohup ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=9090 > ~/guardian-logs/rosbridge.log 2>&1 < /dev/null &
fi
echo "started"