#!/usr/bin/env python3
"""Save one JPEG per requested second from a compressed image topic in a bag.
Usage: bag_frames.py <bag_dir> <topic> <outdir> <sec> [<sec> ...]"""
import os, sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
bag, topic, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
want = sorted(float(s) for s in sys.argv[4:])
os.makedirs(outdir, exist_ok=True)
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id="mcap"), rosbag2_py.ConverterOptions("", ""))
types = {t.name: t.type for t in reader.get_all_topics_and_types()}
reader.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
Msg = get_message(types[topic]); t0 = None; i = 0
tag = topic.strip("/").split("/")[0]
while reader.has_next() and i < len(want):
    _, data, ts = reader.read_next()
    if t0 is None: t0 = ts
    t = (ts - t0) / 1e9
    if t >= want[i]:
        m = deserialize_message(data, Msg)
        p = os.path.join(outdir, "%s-%03ds.jpg" % (tag, int(want[i])))
        open(p, "wb").write(bytes(m.data)); print(p, len(m.data)); i += 1
