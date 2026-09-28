"""Which beams of one LaserScan have no return (inf), grouped into arcs.

Usage: ros2 topic echo --once /scan | python3 empty_beams.py
"""
import sys, yaml, math, numpy as np
d = yaml.safe_load(sys.stdin.read().split("---")[0])
r = np.array([float(x) for x in d["ranges"]]); N = len(r)
amin, inc = float(d["angle_min"]), float(d["angle_increment"])
ang = np.degrees(amin + np.arange(N) * inc); bad = ~np.isfinite(r)
print(f"beams={N} empty={int(bad.sum())} ({100*bad.mean():.0f}%)")
idx = np.where(bad)[0]; runs=[]
if len(idx):
    s=p=idx[0]
    for i in idx[1:]:
        if i!=p+1: runs.append((s,p)); s=i
        p=i
    runs.append((s,p))
for a,b in sorted(runs,key=lambda t:t[1]-t[0],reverse=True)[:6]:
    print(f"  empty arc {ang[a]:7.1f} .. {ang[b]:7.1f} deg ({b-a+1} beams)")
f = np.isfinite(r)
print(f"finite: min={r[f].min():.2f} m median={np.median(r[f]):.2f} max={r[f].max():.2f}; beams<0.30m={int((r[f]<0.30).sum())} at deg {np.round(ang[f][r[f]<0.30]).astype(int).tolist()[:15]}")