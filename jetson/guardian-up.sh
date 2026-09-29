#!/bin/bash
# guardian-up.sh: RPLIDAR + fall_detector + foxglove_bridge (:8765) + rosbridge (:9090), detached.
# The bridges bind 127.0.0.1 unless GUARDIAN_BIND says otherwise (GUARDIAN_BIND=0.0.0.0 ~/guardian-up.sh to expose
# them on the LAN for a capture session, or tunnel 8765 and 9090 over ssh); same rule as guardian-cams-up.sh.
# Safe to re-run: refuses to start a second copy (two sllidar_nodes fight over /dev/rplidar and kill /scan).
# Logs in ~/guardian-logs/. Stop: ~/guardian-down.sh. Also runs at boot via crontab @reboot.
if pgrep -x sllidar_node >/dev/null; then echo "already running (sllidar_node up); run ~/guardian-down.sh first"; exit 0; fi
source /opt/ros/humble/setup.bash
source "${GUARDIAN_WS:-$HOME/prevera-guardian-lidar}/install/setup.bash"   # GUARDIAN_WS = this repo's colcon workspace
export ROS_DOMAIN_ID=42
BIND="${GUARDIAN_BIND:-127.0.0.1}"   # loopback unless exposed on purpose; empty means loopback too
mkdir -p ~/guardian-logs
setsid nohup ros2 launch prevera_bringup perception.launch.py > ~/guardian-logs/perception.log 2>&1 < /dev/null &
setsid nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 address:="$BIND" > ~/guardian-logs/foxglove.log 2>&1 < /dev/null &
if [ -d /opt/ros/humble/share/rosbridge_server ]; then
  setsid nohup ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=9090 address:="$BIND" > ~/guardian-logs/rosbridge.log 2>&1 < /dev/null &
fi
echo "started (bridges bound to $BIND; GUARDIAN_BIND=0.0.0.0 to expose)"