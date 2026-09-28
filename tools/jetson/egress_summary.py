#!/usr/bin/env python3
"""Sum bytes by destination outside the LAN in `tcpdump -n -q -tt` output, inside a time window.

Written for the egress capture of docs/plans/2026-09-28-close-the-gaps-plan.md, Task 6 (bars EG1, EG2).
Direction comes from the Jetson's own address (src == self_ip is outbound), so the interface and In/Out columns
tcpdump prints only for `-i any` are optional. Every line that does not parse is counted in `unparsed_lines`,
never dropped silently.

Usage: egress_summary.py <tcpdump-text> --t0 <epoch> --t1 <epoch> [--lan <prefix,prefix,...>] [--self-ip <ip,ip>]
"""
import argparse
import json
import re

LINE = re.compile(r"^(?P<t>\d+\.\d+)\s+(?:\S+\s+(?:In|Out)\s+)?IP6?\s+(?P<src>[\w.:]+?)\.(?P<sp>\d+)\s+>\s+"
                  r"(?P<dst>[\w.:]+?)\.(?P<dp>\d+):\s+(?:tcp\s+(?P<tcp>\d+)|UDP, length (?P<udp>\d+)|(?P<other>.*))$")


def _is_lan(addr, lan_prefixes):
    return (any(addr.startswith(p) for p in lan_prefixes) or addr.startswith("127.") or addr.startswith("169.254.")
            or addr.startswith("224.") or addr.startswith("239.") or addr.startswith("fe80") or addr.startswith("ff"))


def egress_summary(lines, t0, t1, lan, self_ip):
    """`lan`: comma-separated address prefixes that count as the LAN (a /22 needs four); `self_ip`: comma-separated
    addresses of this device (wired and Wi-Fi), a packet from any of them is outbound."""
    lan = [p.strip() for p in lan.split(",") if p.strip()]
    selves = {a.strip() for a in self_ip.split(",") if a.strip()}
    out = {"out_bytes_non_lan": 0, "in_bytes_non_lan": 0, "by_destination": {}, "unparsed_lines": 0, "lines": 0}
    for line in lines:
        if not line.strip():
            continue
        out["lines"] += 1
        m = LINE.match(line.strip())
        if not m:
            out["unparsed_lines"] += 1
            continue
        t = float(m.group("t"))
        if not (t0 <= t <= t1):
            continue
        n = int(m.group("tcp") or m.group("udp") or 0)
        if m.group("src") in selves and not _is_lan(m.group("dst"), lan):
            key = f'{m.group("dst")}:{m.group("dp")}'
            out["out_bytes_non_lan"] += n
            out["by_destination"][key] = out["by_destination"].get(key, 0) + n
        elif m.group("dst") in selves and not _is_lan(m.group("src"), lan):
            out["in_bytes_non_lan"] += n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--t0", type=float, required=True)
    ap.add_argument("--t1", type=float, required=True)
    ap.add_argument("--lan", default="192.168.4.,192.168.5.,192.168.6.,192.168.7.")  # the room LAN is a /22
    ap.add_argument("--self-ip", default="192.168.4.60,192.168.4.39")  # wired (default route), Wi-Fi
    a = ap.parse_args()
    with open(a.text) as f:
        print(json.dumps(egress_summary(f, a.t0, a.t1, a.lan, a.self_ip), indent=1))


if __name__ == "__main__":
    main()
