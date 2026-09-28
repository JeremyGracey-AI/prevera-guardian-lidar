#!/usr/bin/env python3
"""Arrival statistics of /scan (and a count of /fall_events) in a rosbag2 mcap directory, from header stamps.

Written for the co-load measurement of docs/plans/2026-09-28-close-the-gaps-plan.md, Task 5: the same bars
(CL1 count within 10 %, CL2 no gap over 0.5 s) applied to an idle bag and to a bag recorded while the Inference
container was serving frames.

Usage: scan_rate.py <bag-dir> [<bag-dir> ...] [--topic /scan] [--events /fall_events]
Prints one JSON object per bag: bag, count, duration_s, hz, max_gap_s, gaps_over_0_5_s, events.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def scan_rate(stamps_s):
    """count, duration, mean rate, largest gap and the number of gaps over 0.5 s for a list of stamps (seconds)."""
    stamps = sorted(stamps_s)
    if len(stamps) < 2:
        return {"count": len(stamps), "duration_s": 0.0, "hz": None, "max_gap_s": None, "gaps_over_0_5_s": 0}
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    duration = stamps[-1] - stamps[0]
    return {"count": len(stamps), "duration_s": round(duration, 3), "hz": (len(stamps) - 1) / duration,
            "max_gap_s": max(gaps), "gaps_over_0_5_s": sum(1 for g in gaps if g > 0.5)}


def summarise(bag, topic, events):
    from replay_detector import _iter_mcap  # (topic, header_ns, log_ns, msg) for the harness's topics
    stamps, n_events = [], 0
    for name, hdr_ns, _log_ns, _msg in _iter_mcap(bag):
        if name == topic:
            stamps.append(hdr_ns * 1e-9)
        elif name == events:
            n_events += 1
    return {"bag": str(bag), **scan_rate(stamps), "events": n_events}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bags", nargs="+")
    ap.add_argument("--topic", default="/scan")
    ap.add_argument("--events", default="/fall_events")
    a = ap.parse_args()
    for bag in a.bags:
        print(json.dumps(summarise(bag, a.topic, a.events)))


if __name__ == "__main__":
    main()
