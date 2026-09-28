#!/bin/bash
pkill -INT -f "prevera_bringup perception.launch.py"; pkill -INT -f foxglove_bridge; pkill -INT -f rosbridge; sleep 2
pkill -f sllidar_node; pkill -f fall_detector; pkill -f foxglove_bridge; pkill -f rosbridge_websocket; pkill -f rosapi_node; echo "stopped"