#!/usr/bin/env python3
"""Sample /tracks for N seconds and print the person-like track (range > 0.4 m, largest extent) twice a second.

Usage: track_sampler.py [seconds]   (default 20). Prints CSV rows: t_rel, track_id, x, y, range_m, bearing_deg, extent_m, is_still
then a summary: mean y over the first part (the walk) and the mean position over the last 10 s (the stand).
"""
import math
import sys
import time
import rclpy
from rclpy.node import Node
from prevera_msgs.msg import PersonTrackArray

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
rows = []
t0 = None
last_print = 0.0

class S(Node):
    def __init__(self):
        super().__init__("track_sampler")
        self.create_subscription(PersonTrackArray, "/tracks", self.cb, 10)
    def cb(self, m):
        global t0, last_print
        now = time.time()
        if t0 is None:
            t0 = now
        t = now - t0
        cands = []
        for tr in m.tracks:
            x, y = tr.centroid.x, tr.centroid.y
            r = math.hypot(x, y)
            if r > 0.4:
                cands.append((tr.horizontal_extent_m, tr.track_id, x, y, r, math.degrees(math.atan2(y, x)), tr.is_still))
        if cands:
            cands.sort(reverse=True)
            ext, tid, x, y, r, bearing, still = cands[0]
            rows.append((t, tid, x, y, r, bearing, ext, still))
            if now - last_print >= 0.5:
                last_print = now
                print(f"{t:6.1f}  id={tid:<3d} x={x:+6.2f} y={y:+6.2f} r={r:5.2f} bearing={bearing:+7.1f}deg ext={ext:4.2f} still={int(still)}", flush=True)
        elif now - last_print >= 2.0:
            last_print = now
            print(f"{t:6.1f}  (no person-like track; {len(m.tracks)} tracks total)", flush=True)

def main():
    rclpy.init()
    n = S()
    end = time.time() + DUR
    while rclpy.ok() and time.time() < end:
        rclpy.spin_once(n, timeout_sec=0.1)
    if not rows:
        print("SUMMARY: no person-like track seen"); return
    T = rows[-1][0]
    walk = [r for r in rows if r[0] < max(0.0, T - 10.0)] or rows
    stand = [r for r in rows if r[0] >= T - 10.0] or rows
    my = sum(r[3] for r in walk) / len(walk)
    ys = [r[3] for r in walk]
    sx = sum(r[2] for r in stand) / len(stand); sy = sum(r[3] for r in stand) / len(stand)
    print(f"SUMMARY walk: n={len(walk)} mean_y={my:+.2f} y_min={min(ys):+.2f} y_max={max(ys):+.2f} x_range=[{min(r[2] for r in walk):+.2f},{max(r[2] for r in walk):+.2f}]")
    print(f"SUMMARY stand (last 10 s): n={len(stand)} x={sx:+.2f} y={sy:+.2f} range={math.hypot(sx, sy):.2f} bearing={math.degrees(math.atan2(sy, sx)):+.1f}deg")

if __name__ == "__main__":
    main()
