#!/usr/bin/env python3
"""Sum bytes by destination outside the LAN in `tcpdump -n -q -tt` output, inside a time window.

Written for the egress capture of docs/plans/2026-09-28-close-the-gaps-plan.md, Task 6 (bars EG1, EG2), and
hardened after its review: nothing with an endpoint outside the LAN passes through uncounted.

Buckets, all in bytes of payload as tcpdump -q prints them (`tcp N`, `length N`):
- out_bytes_non_lan / by_destination: from one of this device's addresses to an address outside the LAN (EG1, EG2);
- in_bytes_non_lan: the reverse direction;
- container_leg_bytes: either side in 172.16.0.0/12, the docker bridge; the same packet seen again on `docker0` or
  a veth with `-i any`. It is the positive control that the capture saw the frames go to the container;
- other_non_lan_bytes / other_endpoints: any parsed line with an endpoint that is neither this device, nor the LAN,
  nor link-local, multicast, loopback or the container: an unexpected address, counted, never dropped;
- unparsed_lines / unparsed_kinds: lines that are not IP or IP6 (ARP, 802.1 frames tcpdump prints as `ifindex`),
  counted with their first token. They carry no timestamp window, so the count is for the whole file.

Direction comes from this device's own addresses (`--self-ip`, wired and Wi-Fi), so the interface and direction
columns tcpdump prints for `-i any` (In, Out, P, B, M) are optional and never trusted.

Usage: egress_summary.py <tcpdump-text> --t0 <epoch> --t1 <epoch> [--lan <prefix,...>] [--self-ip <ip,...>]
"""
import argparse
import json
import re

LINE = re.compile(r"^(?P<t>\d+\.\d+)\s+(?:\S+\s+(?:In|Out|P|B|M)\s+)?IP6?\s+(?P<src>\S+)\s+>\s+(?P<dst>\S+):(?:\s+(?P<rest>.*))?$")
LOCAL = ("127.", "169.254.", "224.", "239.", "255.255.255.255", "fe80", "ff", "fd", "::1")


def _endpoint(token):
    """'192.168.4.60.40000' -> ('192.168.4.60', '40000'); '8.8.8.8' -> ('8.8.8.8', None); IPv6 'addr.port' likewise."""
    if ":" in token:
        addr, _, port = token.rpartition(".")
        return (addr, port) if port.isdigit() and addr else (token, None)
    parts = token.split(".")
    if len(parts) == 5 and parts[4].isdigit():
        return ".".join(parts[:4]), parts[4]
    return token, None


def _fmt(addr, port):
    return f"{addr}:{port}" if port else addr


def _payload(rest):
    m = re.search(r"\btcp (\d+)\b", rest) or re.search(r"\blength (\d+)\b", rest)
    return int(m.group(1)) if m else 0


def _is_container(addr):
    parts = addr.split(".")
    return len(parts) == 4 and parts[0] == "172" and parts[1].isdigit() and 16 <= int(parts[1]) <= 31


def _is_lan_or_local(addr, lan_prefixes):
    return any(addr.startswith(p) for p in lan_prefixes) or any(addr.startswith(p) for p in LOCAL)


def egress_summary(lines, t0, t1, lan, self_ip):
    lan = [p.strip() for p in lan.split(",") if p.strip()]
    selves = {a.strip() for a in self_ip.split(",") if a.strip()}
    out = {"out_bytes_non_lan": 0, "in_bytes_non_lan": 0, "by_destination": {}, "container_leg_bytes": 0,
           "other_non_lan_bytes": 0, "other_endpoints": {}, "unparsed_lines": 0, "unparsed_kinds": {}, "lines": 0}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        out["lines"] += 1
        m = LINE.match(line)
        if not m:
            out["unparsed_lines"] += 1
            words = line.split()
            kind = words[3] if len(words) > 3 else words[-1]
            out["unparsed_kinds"][kind] = out["unparsed_kinds"].get(kind, 0) + 1
            continue
        if not (t0 <= float(m.group("t")) <= t1):
            continue
        src, sp = _endpoint(m.group("src"))
        dst, dp = _endpoint(m.group("dst"))
        n = _payload(m.group("rest") or "")
        if src in selves and not _is_lan_or_local(dst, lan) and not _is_container(dst):
            out["out_bytes_non_lan"] += n
            out["by_destination"][_fmt(dst, dp)] = out["by_destination"].get(_fmt(dst, dp), 0) + n
        elif dst in selves and not _is_lan_or_local(src, lan) and not _is_container(src):
            out["in_bytes_non_lan"] += n
        elif _is_container(src) or _is_container(dst):
            out["container_leg_bytes"] += n
        else:
            unknown = [a for a in (src, dst) if a not in selves and not _is_lan_or_local(a, lan)]
            if unknown:
                key = f"{_fmt(src, sp)} > {_fmt(dst, dp)}"
                out["other_non_lan_bytes"] += n
                out["other_endpoints"][key] = out["other_endpoints"].get(key, 0) + n
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
