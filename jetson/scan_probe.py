#!/usr/bin/env python3
"""Histogram live /scan returns by 15-degree sector: valid count, min and median range. Finds blind sectors."""
import math, statistics, time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

got = []
class S(Node):
    def __init__(self):
        super().__init__("scan_probe")
        self.create_subscription(LaserScan, "/scan", lambda m: got.append(m), qos_profile_sensor_data)

rclpy.init(); n = S(); t0 = time.time()
while time.time() - t0 < 3.0 and len(got) < 20:
    rclpy.spin_once(n, timeout_sec=0.1)
m = got[-1]
print("scans=%d beams=%d angle_min=%.1f angle_max=%.1f inc=%.3f range=[%.2f,%.2f]" % (
    len(got), len(m.ranges), math.degrees(m.angle_min), math.degrees(m.angle_max), math.degrees(m.angle_increment), m.range_min, m.range_max))
sect = {}
for i, r in enumerate(m.ranges):
    a = math.degrees(m.angle_min + i * m.angle_increment)
    k = int(math.floor(a / 15.0)) * 15
    ok = (r == r) and (r != float("inf")) and (m.range_min <= r <= m.range_max)
    sect.setdefault(k, []).append(r if ok else None)
print("sector_deg     valid/total   min    median")
for k in sorted(sect):
    v = [r for r in sect[k] if r is not None]
    mn = ("%5.2f" % min(v)) if v else "  -  "
    md = ("%5.2f" % statistics.median(v)) if v else "  -  "
    bar = "#" * int(round(20.0 * len(v) / max(1, len(sect[k]))))
    print("%+5d..%+4d   %3d/%3d   %s  %s  %s" % (k, k + 15, len(v), len(sect[k]), mn, md, bar))
