#!/bin/bash
# guardian-status.sh: one-screen health check. Run first thing: ssh jetson ~/guardian-status.sh
source /opt/ros/humble/setup.bash
# Workspace checkout (this repository, built with colcon). Override with GUARDIAN_WS=/path.
GUARDIAN_WS="${GUARDIAN_WS:-$HOME/prevera-guardian-lidar}"
source "$GUARDIAN_WS/install/setup.bash" 2>/dev/null
export ROS_DOMAIN_ID=42
ok(){ printf "  %-28s %s\n" "$1" "$2"; }
echo "GUARDIAN status  $(date '+%F %T')  up $(uptime -p | sed 's/up //')"
ok "lidar driver (want 1)"   "$(pgrep -c -x sllidar_node)"
ok "fall detector (want 1)"  "$(pgrep -fc 'prevera_perception/lib/prevera_perception/[f]all_detector')"
ok "foxglove_bridge :8765"   "$(ss -ltn | grep -q ':8765 ' && echo listening || echo DOWN)"
ok "rosbridge :9090"         "$(ss -ltn | grep -q ':9090 ' && echo listening || echo DOWN)"
ok "/dev/rplidar"            "$(ls -l /dev/rplidar 2>/dev/null | awk '{print $NF}' || echo MISSING)"
N=$(timeout 6 ros2 topic echo --no-daemon --qos-reliability best_effort /scan sensor_msgs/msg/LaserScan --field header.stamp.sec 2>/dev/null | grep -c '^[0-9]')
ok "/scan msgs in ~5 s (≈50)" "$N"
ok "bag recording"           "$(pgrep -f '[b]ag record' >/dev/null && echo YES || echo no)"
ok "branch"                  "$(git -C "$GUARDIAN_WS" rev-parse --abbrev-ref HEAD) @ $(git -C "$GUARDIAN_WS" rev-parse --short HEAD)"
ok "NVMe free"               "$(df -h /opt/nvme | awk 'NR==2{print $4}')"
echo "  recent bags:"; ls -td /opt/nvme/bags/*/ 2>/dev/null | head -4 | sed 's|^|    |'