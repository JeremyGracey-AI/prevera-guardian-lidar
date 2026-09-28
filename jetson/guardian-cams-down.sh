#!/bin/bash
# guardian-cams-down.sh: stop both usb_cam nodes, the MJPEG servers and the dual-view page.
# Own script on purpose: a pkill pattern must never share a command line with the launch it targets.
pkill -INT -f "[u]sb_cam_node" ; pkill -INT -f "[m]jpeg_server.py" ; pkill -INT -f "[h]ttp.server 8083"
sleep 2
pgrep -f "[u]sb_cam_node|[m]jpeg_server|[h]ttp.server 8083" >/dev/null && echo "some still running" || echo "stopped"
