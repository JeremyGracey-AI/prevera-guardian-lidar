"""egress_summary() sums bytes by destination outside the LAN from `tcpdump -n -q -tt` lines within a time window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "jetson"))
from egress_summary import egress_summary  # noqa: E402

LINES = """1790640000.100000 IP 192.168.4.39.40000 > 34.120.1.2.443: tcp 1200
1790640000.200000 IP 192.168.4.39.40001 > 192.168.4.60.9090: tcp 500
1790640000.300000 IP 34.120.1.2.443 > 192.168.4.39.40000: tcp 300
1790640001.000000 eth0  Out IP 192.168.4.39.40002 > 8.8.8.8.53: UDP, length 40
1790640050.000000 IP 192.168.4.39.40003 > 1.2.3.4.443: tcp 100
""".splitlines()
ARGS = dict(t0=1790640000.0, t1=1790640010.0, lan="192.168.4.", self_ip="192.168.4.39")


def test_sums_outbound_bytes_to_non_lan_destinations_inside_the_window():
    s = egress_summary(LINES, **ARGS)
    assert s["out_bytes_non_lan"] == 1240
    assert s["by_destination"] == {"34.120.1.2:443": 1200, "8.8.8.8:53": 40}
    assert s["in_bytes_non_lan"] == 300


def test_lines_outside_the_window_and_lan_traffic_are_excluded():
    s = egress_summary(LINES, **ARGS)
    assert "1.2.3.4:443" not in s["by_destination"] and "192.168.4.60:9090" not in s["by_destination"]


def test_unparseable_line_is_counted_not_dropped():
    s = egress_summary(["garbage"], t0=0, t1=1e12, lan="192.168.4.", self_ip="192.168.4.39")
    assert s["unparsed_lines"] == 1


def test_two_lan_prefixes_and_two_self_addresses_wired_and_wifi():
    lines = ["1790640000.100000 IP 192.168.4.60.40000 > 34.120.1.2.443: tcp 700",   # wired, out
             "1790640000.200000 IP 192.168.4.39.40001 > 34.120.1.2.443: tcp 50",    # wifi, out
             "1790640000.300000 IP 192.168.4.60.40002 > 192.168.6.9.5000: tcp 900"]  # LAN /22, excluded
    s = egress_summary(lines, t0=0, t1=1e12, lan="192.168.4.,192.168.5.,192.168.6.,192.168.7.",
                       self_ip="192.168.4.60,192.168.4.39")
    assert s["out_bytes_non_lan"] == 750 and list(s["by_destination"]) == ["34.120.1.2:443"]


def test_any_interface_direction_letters_parse_and_the_container_leg_does_not_count():
    # tcpdump -i any (SLL2) prints In/Out and single letters P (passed up on a veth), B (broadcast), M (multicast)
    lines = ["1790638883.708375 veth79bb483 P   IP 172.17.0.2.40018 > 151.101.65.195.443: tcp 100",
             "1790638883.708400 enP8p1s0 Out IP 192.168.4.60.40018 > 151.101.65.195.443: tcp 100",
             "1790638873.355456 enP8p1s0 B   IP 192.168.4.40.59384 > 192.168.7.255.13305: UDP, length 107",
             "1790638877.750141 wlP1p1s0 M   IP 192.168.4.39.5353 > 224.0.0.251.5353: UDP, length 129"]
    s = egress_summary(lines, t0=0, t1=1e12, lan="192.168.4.,192.168.5.,192.168.6.,192.168.7.",
                       self_ip="192.168.4.60,192.168.4.39")
    assert s["unparsed_lines"] == 0
    assert s["out_bytes_non_lan"] == 100 and s["by_destination"] == {"151.101.65.195:443": 100}


# --- review I2: nothing with a non-LAN endpoint may pass through the parser uncounted ---
def _s(lines):
    return egress_summary(lines, t0=0, t1=1e12, lan="192.168.4.,192.168.5.,192.168.6.,192.168.7.",
                          self_ip="192.168.4.60,192.168.4.39")


def test_icmp_without_ports_from_self_counts_its_length():
    s = _s(["1790640000.1 IP 192.168.4.60 > 8.8.8.8: ICMP echo request, id 1, seq 1, length 64"])
    assert s["unparsed_lines"] == 0 and s["out_bytes_non_lan"] == 64 and s["by_destination"] == {"8.8.8.8": 64}


def test_traffic_between_two_addresses_that_are_neither_self_nor_lan_is_counted_as_other():
    s = _s(["1790640000.1 IP6 2001:db8::1.443 > 2001:db8::2.5000: tcp 100",
            "1790640000.2 IP 10.9.9.9.1234 > 151.101.65.195.443: tcp 7"])
    assert s["out_bytes_non_lan"] == 0 and s["other_non_lan_bytes"] == 107
    assert set(s["other_endpoints"]) == {"2001:db8::1:443 > 2001:db8::2:5000", "10.9.9.9:1234 > 151.101.65.195:443"}


def test_container_leg_is_the_positive_control_not_egress():
    s = _s(["1790640000.1 docker0 Out IP 172.17.0.1.40076 > 172.17.0.2.9001: tcp 100000",
            "1790640000.2 veth79bb483 P   IP 172.17.0.2.40018 > 151.101.65.195.443: tcp 500"])
    assert s["out_bytes_non_lan"] == 0 and s["other_non_lan_bytes"] == 0
    assert s["container_leg_bytes"] == 100500


def test_unparsed_lines_are_characterised():
    s = _s(["1790640000.1 enP8p1s0 B   ARP, Request who-has 192.168.4.56 tell 192.168.4.56, length 60",
            "1790640000.2 enP8p1s0 B   ifindex 4 24:2d:6c:e0:01:14"])
    assert s["unparsed_lines"] == 2 and s["unparsed_kinds"] == {"ARP,": 1, "ifindex": 1}
