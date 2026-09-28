#!/usr/bin/env python3
"""Per-second timeline of a Guardian bag without the camera topics: person-like track (range > 0.4 m, largest
extent) x/y/range/is_still, and fall events by level. Usage: bag_timeline.py <bag_dir>"""
import math, sys
from collections import defaultdict
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

bag = sys.argv[1]
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id="mcap"), rosbag2_py.ConverterOptions("", ""))
types = {t.name: t.type for t in reader.get_all_topics_and_types()}
reader.set_filter(rosbag2_py.StorageFilter(topics=["/tracks", "/fall_events"]))
Tr = get_message(types["/tracks"]); Ev = get_message(types["/fall_events"])
t0 = None
sec = defaultdict(lambda: {"n": 0, "r": [], "x": [], "y": [], "still": 0, "ev": defaultdict(int), "ntracks": 0})
while reader.has_next():
    topic, data, ts = reader.read_next()
    if t0 is None: t0 = ts
    s = int((ts - t0) / 1e9)
    if topic == "/tracks":
        m = deserialize_message(data, Tr)
        b = sec[s]; b["ntracks"] = max(b["ntracks"], len(m.tracks))
        cands = [(tr.horizontal_extent_m, tr) for tr in m.tracks if math.hypot(tr.centroid.x, tr.centroid.y) > 0.4]
        if cands:
            cands.sort(key=lambda c: -c[0]); tr = cands[0][1]
            b["n"] += 1; b["r"].append(math.hypot(tr.centroid.x, tr.centroid.y)); b["x"].append(tr.centroid.x); b["y"].append(tr.centroid.y); b["still"] += int(tr.is_still)
    else:
        m = deserialize_message(data, Ev)
        sec[s]["ev"][int(m.alert_level)] += 1
last = max(sec) if sec else 0
print("sec  person  x      y      range  still  L1  L2  tracks")
for s in range(last + 1):
    b = sec[s]
    if b["n"]:
        print("%3d  %2d/10  %+5.2f  %+5.2f  %5.2f  %2d     %2d  %2d  %d" % (s, b["n"], sum(b["x"])/b["n"], sum(b["y"])/b["n"], sum(b["r"])/b["n"], b["still"], b["ev"][1], b["ev"][2], b["ntracks"]))
    else:
        print("%3d   -                              -     %2d  %2d  %d" % (s, b["ev"][1], b["ev"][2], b["ntracks"]))
