"""scan_rate() summarises /scan arrival from header stamps: count, rate, the largest gap, gaps over half a second."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "bag_analysis"))
from scan_rate import scan_rate  # noqa: E402


def test_steady_ten_hertz():
    r = scan_rate([i * 0.1 for i in range(600)])
    assert r["count"] == 600 and abs(r["hz"] - 10.0) < 1e-6 and abs(r["max_gap_s"] - 0.1) < 1e-9
    assert r["gaps_over_0_5_s"] == 0


def test_one_dropout_is_counted_once():
    stamps = [i * 0.1 for i in range(100)] + [i * 0.1 + 0.8 for i in range(100, 200)]
    r = scan_rate(stamps)
    assert r["gaps_over_0_5_s"] == 1 and abs(r["max_gap_s"] - 0.9) < 1e-9


def test_empty_and_singleton_do_not_divide_by_zero():
    assert scan_rate([]) == {"count": 0, "duration_s": 0.0, "hz": None, "max_gap_s": None, "gaps_over_0_5_s": 0}
    assert scan_rate([3.0])["count"] == 1 and scan_rate([3.0])["hz"] is None
