"""Compare the scan toward (x, y) against the empty room over time.

Shows whether a person at (x, y) adds any returns, i.e. whether they are inside the scan plane.
Usage: python3 scan_sector.py <bag_dir> <x> <y> <empty_room_second> [seconds...]
"""
import sys
import rosbag2_py, numpy as np, math
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan
r=rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=sys.argv[1],storage_id="mcap"),rosbag2_py.ConverterOptions("cdr","cdr"))
r.set_filter(rosbag2_py.StorageFilter(topics=["/scan"]))
t0=None; snaps={}
X, Y, BASE = float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
want = [BASE] + [int(a) for a in sys.argv[5:]]
while r.has_next():
    _,d,ts=r.read_next(); t=ts/1e9
    if t0 is None: t0=t
    s=int(t-t0)
    if s in want and s not in snaps: snaps[s]=deserialize_message(d,LaserScan)
def sector(m, x, y, halfw=25):
    a=math.degrees(math.atan2(y,x)); N=len(m.ranges)
    ang=np.degrees(m.angle_min+np.arange(N)*m.angle_increment); rr=np.array(m.ranges)
    sel=(np.abs((ang-a+180)%360-180)<halfw)&np.isfinite(rr)
    return rr[sel]
base=sector(snaps[BASE],X,Y)
print("empty-room sector toward (x,y) +-25 deg: %d pts, closest %.2f m, median %.2f m"%(len(base),base.min(),np.median(base)))
for s in sorted(snaps):
    v=sector(snaps[s],X,Y); close=v[v<np.median(base)-0.3]
    print("  t=%3ds: pts=%3d  closer-than-room=%3d  nearest=%.2f m"%(s,len(v),len(close),v.min() if len(v) else float('nan')))