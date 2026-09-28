"""Timeline of /fall_events and the largest non-near track per second from a GUARDIAN rosbag (mcap).

Usage: python3 fall_timeline.py <bag_dir>   (source the workspace first so prevera_msgs resolves)
"""
import sys
import rosbag2_py, numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
B = sys.argv[1]
r=rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=B,storage_id="mcap"),rosbag2_py.ConverterOptions("cdr","cdr"))
types={t.name:t.type for t in r.get_all_topics_and_types()}
t0=None; ev=[]; sec={}
while r.has_next():
    topic,data,ts=r.read_next(); t=ts/1e9
    if t0 is None: t0=t
    s=int(t-t0)
    if topic=="/fall_events":
        m=deserialize_message(data,get_message(types[topic]))
        ev.append((t-t0,m.alert_level,m.confidence,m.track_id,m.location.x,m.location.y,m.horizontal_extent_m,m.elongation_ratio,m.stillness_duration_s,m.preceding_velocity_mps))
    elif topic=="/tracks":
        m=deserialize_message(data,get_message(types[topic]))
        # "person-like" = not within 0.4 m of sensor
        cand=[k for k in m.tracks if (k.centroid.x**2+k.centroid.y**2)**0.5>0.4]
        d=sec.setdefault(s,{"n":0,"near":0,"best":None})
        d["n"]+=len(cand); d["near"]+=len(m.tracks)-len(cand)
        for k in cand:
            if d["best"] is None or k.horizontal_extent_m>d["best"][0]:
                d["best"]=(k.horizontal_extent_m,k.elongation_ratio,(k.centroid.x**2+k.centroid.y**2)**0.5,k.track_id,k.age_s)
print("EVENTS (t_s, level, conf, track, x, y, extent_m, elong, still_s, peak_v)")
for e in ev: print("  %6.1f  L%d  %.2f  #%d  (%.2f,%.2f)  ext=%.2f  el=%.1f  still=%.1f  v=%.2f"%e)
print("\nPER-SECOND (largest non-near track): t | extent m | elong | range m | id | near-sensor tracks/s")
for s in sorted(sec):
    d=sec[s]; b=d["best"]
    if b and (b[0]>0.35 or s%20==0): print("  %4d | %.2f | %5.1f | %.2f | #%d | near=%d"%(s,b[0],b[1],b[2],b[3],d["near"]))
    elif not b and s%20==0: print("  %4d | --- empty --- | near=%d"%(s,d["near"]))