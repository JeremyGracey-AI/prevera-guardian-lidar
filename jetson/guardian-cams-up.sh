#!/bin/bash
# guardian-cams-up.sh: both webcams into ROS (usb_cam, mjpeg2rgb 1280x720@30) plus the browser views.
# Top cam C920 on /dev/video0 -> /camera, floor cam Brio 100 on /dev/video2 -> /camera_floor.
# Views: http://<jetson>:8081/ (top), :8082 (floor), :8083 (both). Stop: ~/guardian-cams-down.sh.
# Refuses to start a second copy. Not part of guardian-up.sh. SECURITY: the views bind 0.0.0.0 with no auth: trusted LAN only.
if pgrep -f "[u]sb_cam_node" >/dev/null; then echo "already running (usb_cam up); run ~/guardian-cams-down.sh first"; exit 0; fi
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=42
mkdir -p ~/guardian-logs
GUARDIAN_WS="${GUARDIAN_WS:-$HOME/prevera-guardian-lidar}"; T="$GUARDIAN_WS/jetson"   # this repo's checkout
cam() { # ns device name frame log
  setsid nohup ros2 run usb_cam usb_cam_node_exe --ros-args -r __ns:=$1 -p video_device:=$2 -p pixel_format:=mjpeg2rgb -p image_width:=1280 -p image_height:=720 -p framerate:=30.0 -p camera_name:=$3 -p frame_id:=$4 > ~/guardian-logs/$5.log 2>&1 < /dev/null &
}
cam /camera /dev/video0 c920 camera camera
cam /camera_floor /dev/video2 brio100 camera_floor camera_floor
sleep 5
setsid nohup python3 $T/mjpeg_server.py /camera/image_raw/compressed 8081 > ~/guardian-logs/mjpeg.log 2>&1 < /dev/null &
setsid nohup python3 $T/mjpeg_server.py /camera_floor/image_raw/compressed 8082 > ~/guardian-logs/mjpeg_floor.log 2>&1 < /dev/null &
(cd $T/www && setsid nohup python3 -m http.server 8083 --bind 0.0.0.0 > ~/guardian-logs/www.log 2>&1 < /dev/null &)
sleep 3
ss -ltn | grep -E ":808[123]" | awk '{print $4}'
echo "started"
