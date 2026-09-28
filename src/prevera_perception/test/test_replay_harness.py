"""Replay harness (tools/bag_analysis/replay_detector.py, mcap_fixture.py): plan v4 step 3.

Every replay in this file passes `--params L` (the 36ca257 legacy snapshot shipped with the
harness), never the live yaml, so steps 4 and 9 do not move these expectations. Fixture bags
are written once per session into `tmp_path_factory`. Values come from plan Appendices D/E
(pinned Mac venv: Python 3.10.21, numpy 1.26.4, sklearn 1.7.2); DBSCAN-sensitive stamps are
asserted as windows, WARNs are selected by location, never as "the" WARN.

The harness is imported through `conftest.py` (tools/bag_analysis on sys.path); without
`mcap_ros2` the whole file is skipped.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mcap_ros2")

import mcap_fixture  # noqa: E402
import replay_detector  # noqa: E402
from prevera_perception.background import BackgroundConfig  # noqa: E402
from prevera_perception.clustering import ClusterConfig  # noqa: E402
from prevera_perception.detector_core import (  # noqa: E402
    AlertLevel,
    DetectorConfig,
    DetectorCore,
    FallConfig,
)
from prevera_perception.synthetic_scene import (  # noqa: E402
    SyntheticScene,
    overrides_v3,
    overrides_v3_near_arc,
)
from prevera_perception.tracker import TrackerConfig  # noqa: E402

L = replay_detector.L_PATH
Y = replay_detector.Y_PATH
BANDS = replay_detector.BANDS
N_SCANS = 160


def _f32(v: float) -> float:
    return float(np.float32(v))


def _warn_at(events: list[dict], x: float, y: float, radius: float) -> list[dict]:
    return [e for e in events if e["level"] == 2 and math.hypot(e["x"] - x, e["y"] - y) <= radius]


def _stamp_s(ev: dict) -> float:
    return ev["stamp_ns"] / 1e9


# ----------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def bag_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("bags")


@pytest.fixture(scope="session")
def std_bag(bag_dir) -> Path:
    return mcap_fixture.write_scene_bag(bag_dir / "std", overrides=overrides_v3, with_outputs=True, params=L)


@pytest.fixture(scope="session")
def near_bag(bag_dir) -> Path:
    return mcap_fixture.write_scene_bag(
        bag_dir / "near", overrides=overrides_v3_near_arc, with_outputs=True, params=L
    )


@pytest.fixture(scope="session")
def std_replay(std_bag, tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("golden") / "std_replay.json"
    assert replay_detector.main(["replay", str(std_bag), "--params", str(L), "--json", str(out)]) == 0
    return replay_detector.load_golden(out)


def _walking_id1(i: int) -> dict:
    # id 1 walks at range ~3 m, 0.05 m per scan (0.5 m/s); age_s grows every scan (= matched).
    return dict(track_id=1, x=3.0, y=-1.0 + 0.05 * (i - 30), extent=0.2, elongation=1.2,
                age_s=0.1 * (i - 30), is_still=False)


def _near_id9(i: int) -> dict:
    return dict(track_id=9, x=0.2, y=0.2, extent=0.05, elongation=1.0, age_s=0.1 * (i - 30), is_still=True)


def transitions_script() -> list[tuple[int, list[dict]]]:
    """Four scripted id transitions on top of a walking id 1 (plan step 3, transitions test)
    plus a near-sensor id 9 (range 0.28 m) on every scan for the per-second exclusion test."""
    script: list[tuple[int, list[dict]]] = []
    id1_last = _walking_id1(60)
    for i in range(30, N_SCANS):
        rows = [_near_id9(i)]
        if 30 <= i <= 60:
            rows.append(_walking_id1(i))
        if 50 <= i <= 55:
            prev = _walking_id1(49)          # (a) 0.1 m from id 1's last centroid, id 1 matched this scan
            rows.append(dict(track_id=2, x=prev["x"] + 0.1, y=prev["y"], extent=0.15, elongation=1.1,
                             age_s=0.1 * (i - 50), is_still=False))
        if 70 <= i <= 100:                   # (b) id 1's last centroid + 0.05 m, id 1 last seen at scan 60
            rows.append(dict(track_id=3, x=id1_last["x"] + 0.05, y=id1_last["y"], extent=0.9, elongation=5.0,
                             age_s=0.1 * (i - 70), is_still=True))
        if 90 <= i <= 100:                   # (c) 3.0 m away from id 3 while id 3 is alive
            rows.append(dict(track_id=4, x=id1_last["x"] + 0.05, y=id1_last["y"] + 3.0, extent=0.3,
                             elongation=1.5, age_s=0.1 * (i - 90), is_still=False))
        if i >= 120:                         # (d) no non-near id alive for 20 scans
            rows.append(dict(track_id=5, x=2.0, y=2.0, extent=0.4, elongation=2.0,
                             age_s=0.1 * (i - 120), is_still=False))
        script.append((i, rows))
    return script


@pytest.fixture(scope="session")
def scripted_bag(bag_dir) -> Path:
    return mcap_fixture.write_scripted_tracks_bag(bag_dir / "scripted", transitions_script())


# ----------------------------------------------------------------------------- tests


def test_fixture_bag_replays_to_warn(std_replay):
    events = std_replay["events"]
    warns = [e for e in events if e["level"] == 2]
    assert len(warns) == 2, warns
    assert std_replay["source"] == "replay"

    [person] = _warn_at(events, 2.4, 1.4, 0.25)
    t_person = _stamp_s(person)
    assert 8.6 <= t_person <= 9.4, t_person
    assert person["peak_v"] >= 0.8
    assert 0.5 < person["stillness_s"] <= 1.0, person
    assert person["confidence"] == pytest.approx(min(1.0, 0.5 + 0.1 * person["stillness_s"]), abs=1e-6)
    later = [e for e in events if e["track_id"] == person["track_id"] and e["level"] == 2 and e["stamp_ns"] > person["stamp_ns"]]
    assert later == []

    [line] = _warn_at(events, 1.0, -0.06, 0.1)
    assert _stamp_s(line) == pytest.approx(8.0, abs=1e-9)
    assert line["stillness_s"] == pytest.approx(4.0, abs=1e-9)
    assert line["peak_v"] == 0.0
    assert line["confidence"] == pytest.approx(0.6, abs=1e-6)
    assert line["elongation"] == 1e6
    print(f"REPLAY person_warn={t_person} conf={person['confidence']} still={person['stillness_s']} "
          f"peak={person['peak_v']} xy=({person['x']:.3f}, {person['y']:.3f})")


def test_replay_matches_core_driven_directly(std_bag, std_replay):
    config, _ = replay_detector.load_config(L)
    core = DetectorCore(config)
    scene = SyntheticScene(np.random.default_rng(42))
    angle_min, angle_inc = _f32(SyntheticScene.ANGLE_MIN), _f32(SyntheticScene.ANGLE_INCREMENT)
    expected = []
    for i in range(N_SCANS):
        sec, nanosec = divmod(i * 10**8, 10**9)
        stamp_s = sec + nanosec * 1e-9
        result = core.process(scene.build_scan(i * 0.1, overrides_v3(i)), angle_min, angle_inc, stamp_s)
        if result is None:
            continue
        for ev in result.events:
            expected.append((sec * 10**9 + nanosec, ev.track_id, int(ev.level), _f32(ev.confidence), _f32(ev.x),
                             _f32(ev.y), _f32(ev.major_axis_m), _f32(ev.elongation), _f32(ev.stillness_s),
                             _f32(ev.peak_recent_velocity)))
    got = [(e["stamp_ns"], e["track_id"], e["level"], e["confidence"], e["x"], e["y"], e["extent_m"],
            e["elongation"], e["stillness_s"], e["peak_v"]) for e in std_replay["events"]]
    assert got == expected
    assert len(got) == 48


def test_recorded_events_reproduce_exactly_on_fixture(std_bag, tmp_path):
    rec, rep = tmp_path / "rec.json", tmp_path / "rep.json"
    assert replay_detector.main(["extract", str(std_bag), "--json", str(rec)]) == 0
    assert replay_detector.main(["replay", str(std_bag), "--params", str(L), "--json", str(rep)]) == 0
    recorded = replay_detector.load_golden(rec)
    assert recorded["source"] == "recorded"
    assert any(e["elongation"] == 1e6 for e in recorded["events"])
    assert recorded["track_range_hist"]["[0.5,inf)"]["max_per_scan"] >= 1
    assert replay_detector.main(["diff", str(rec), str(rep), "--strict"]) == 0

    config, flat = replay_detector.load_config(L)
    bag = replay_detector.load_bag(std_bag)
    for settle in (7.0, 3.0):
        div = replay_detector.divergence_report(bag, config, flat, settle_s=settle, end_s=None)
        assert div["first_divergent"] is None, div
        assert div["same_tracks_diff_events"] == 0
        assert div["boundary_band_diff_events"] == 0
        assert div["warn_level_diff"] == 0
        assert div["compared_scans"] > 0
    assert replay_detector.main(["divergence", str(std_bag), "--params", str(L)]) == 0

    san = replay_detector.sanity_report(bag)
    assert san["warm_start"] is False
    assert san["warmup_occupied"] is True
    assert san["death_gap_t_end_s"] == pytest.approx(15.9, abs=1e-9)
    assert san["scan_count"] == N_SCANS
    assert san["beam_count_hist"] == {720: N_SCANS}
    assert san["tracks_per_scan_ratio"] == pytest.approx(1.0)
    assert san["gaps"] == []
    assert replay_detector.main(["sanity", str(std_bag)]) == 0


def test_diff_detects_perturbation_and_flags(std_bag, bag_dir, tmp_path, capsys):
    rec, rep = tmp_path / "rec.json", tmp_path / "rep.json"
    assert replay_detector.main(["extract", str(std_bag), "--json", str(rec)]) == 0
    assert replay_detector.main(["replay", str(std_bag), "--params", str(L), "--json", str(rep)]) == 0
    golden = replay_detector.load_golden(rep)

    # one level changed -> exit 1 naming stamp and track
    bad = json.loads(json.dumps(golden))
    target = next(e for e in bad["events"] if e["level"] == 2)
    target["level"] = 1
    p = tmp_path / "level.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    capsys.readouterr()
    assert replay_detector.main(["diff", str(rec), str(p), "--strict"]) == 1
    out = capsys.readouterr().out
    assert str(target["stamp_ns"]) in out and f"track {target['track_id']}" in out

    # scan_count changed -> exit 2 (same-bag precondition)
    bad = json.loads(json.dumps(golden))
    bad["scan_count"] -= 1
    p = tmp_path / "count.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    assert replay_detector.main(["diff", str(rec), str(p), "--strict"]) == 2

    # tie-break 2: the golden loader rejects inf/nan in a JSON file with a clear error
    text = json.dumps(golden)
    first = golden["events"][0]
    text_inf = text.replace(f'"elongation": {first["elongation"]}', '"elongation": Infinity', 1)
    assert "Infinity" in text_inf
    p = tmp_path / "inf.json"
    p.write_text(text_inf, encoding="utf-8")
    with pytest.raises(ValueError, match="inf|nan|NaN|Infinity"):
        replay_detector.load_golden(p)
    p.write_text(text.replace(f'"confidence": {first["confidence"]}', '"confidence": NaN', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="inf|nan|NaN|Infinity"):
        replay_detector.load_golden(p)
    # and the writer itself refuses a non-finite value (allow_nan=False)
    bad = json.loads(json.dumps(golden))
    bad["events"][0]["elongation"] = float("inf")
    with pytest.raises(ValueError):
        replay_detector.write_golden(bad, tmp_path / "never.json")

    # warm_start / warmup_occupied on scripted /tracks
    early = [(i, [dict(track_id=1, x=0.3, y=0.0, extent=0.1, elongation=1.0, age_s=0.1 * i, is_still=True)])
             for i in range(10, 41)]
    b = mcap_fixture.write_scripted_tracks_bag(bag_dir / "warm_early", early)
    assert replay_detector.sanity_report(replay_detector.load_bag(b))["warm_start"] is True

    near_only = [(i, [dict(track_id=1, x=0.3, y=0.0, extent=0.1, elongation=1.0, age_s=0.1 * (i - 30), is_still=True)])
                 for i in range(30, 101)]
    b = mcap_fixture.write_scripted_tracks_bag(bag_dir / "warm_near", near_only)
    san = replay_detector.sanity_report(replay_detector.load_bag(b))
    assert san["warm_start"] is False and san["warmup_occupied"] is False

    with_person = [(i, rows + ([dict(track_id=2, x=2.0, y=0.0, extent=0.2, elongation=1.2, age_s=0.0, is_still=False)]
                               if i == 50 else [])) for i, rows in near_only]
    b = mcap_fixture.write_scripted_tracks_bag(bag_dir / "warm_occupied", with_person)
    san = replay_detector.sanity_report(replay_detector.load_bag(b))
    assert san["warm_start"] is False and san["warmup_occupied"] is True

    # injected 0.5 s stamp gap after scan 50 appears in gaps
    b = mcap_fixture.write_scene_bag(bag_dir / "gap05", overrides=overrides_v3, with_outputs=True, params=L,
                                     gaps_after={50: 0.5})
    san = replay_detector.sanity_report(replay_detector.load_bag(b))
    assert len(san["gaps"]) == 1
    [(gap_stamp_ns, gap_dt)] = san["gaps"]
    assert gap_stamp_ns == 50 * 10**8 and gap_dt == pytest.approx(0.6, abs=1e-9)
    assert san["death_gap_t_end_s"] == pytest.approx(15.9 + 0.5, abs=1e-9)

    # injected 6 s gap after scan 100 -> death_gap_t_end_s == 10.0; replay default --end-s stops there
    b = mcap_fixture.write_scene_bag(bag_dir / "gap6", overrides=overrides_v3, with_outputs=True, params=L,
                                     gaps_after={100: 6.0})
    san = replay_detector.sanity_report(replay_detector.load_bag(b))
    assert san["death_gap_t_end_s"] == pytest.approx(10.0, abs=1e-9)
    assert san["scan_count"] == N_SCANS
    default_out = tmp_path / "gap6_default.json"
    assert replay_detector.main(["replay", str(b), "--params", str(L), "--json", str(default_out)]) == 0
    g_default = replay_detector.load_golden(default_out)
    assert g_default["end_s"] == pytest.approx(10.0, abs=1e-9)
    assert g_default["scan_count"] == 101
    assert g_default["last_stamp_ns"] == 100 * 10**8
    assert all(e["stamp_ns"] <= 10 * 10**9 for e in g_default["events"])
    assert len(_warn_at(g_default["events"], 2.4, 1.4, 0.25)) == 1
    # an explicit --end-s before the person's WARN drops it; an explicit larger end processes every scan
    short_out = tmp_path / "gap6_short.json"
    assert replay_detector.main(["replay", str(b), "--params", str(L), "--end-s", "8.5", "--json", str(short_out)]) == 0
    g_short = replay_detector.load_golden(short_out)
    assert _warn_at(g_short["events"], 2.4, 1.4, 0.25) == []
    assert len(_warn_at(g_short["events"], 1.0, -0.06, 0.1)) == 1
    assert all(e["stamp_ns"] <= int(8.5e9) for e in g_short["events"])
    long_out = tmp_path / "gap6_long.json"
    assert replay_detector.main(["replay", str(b), "--params", str(L), "--end-s", "30", "--json", str(long_out)]) == 0
    g_long = replay_detector.load_golden(long_out)
    assert g_long["scan_count"] == N_SCANS and g_long["last_stamp_ns"] == 159 * 10**8 + 6 * 10**9
    assert replay_detector.main(["diff", str(default_out), str(long_out), "--strict"]) == 2

    # a scan with 719 beams is skipped and counted
    b = mcap_fixture.write_scene_bag(bag_dir / "beam719", overrides=overrides_v3, with_outputs=True, params=L,
                                     beam_counts={45: 719})
    san = replay_detector.sanity_report(replay_detector.load_bag(b))
    assert san["beam_count_hist"] == {720: N_SCANS - 1, 719: 1}
    out = tmp_path / "beam719.json"
    assert replay_detector.main(["replay", str(b), "--params", str(L), "--json", str(out)]) == 0
    g = replay_detector.load_golden(out)
    assert g["skipped_scans"] == 1 and g["beam_count"] == 720 and g["scan_count"] == N_SCANS


def _golden_pair(rec_events: list[dict], rep_events: list[dict]) -> tuple[dict, dict]:
    base = dict(bag="synthetic", code_rev="x", config_sha256="x", config={}, scan_count=300, beam_count=720,
                skipped_scans=0, first_stamp_ns=0, last_stamp_ns=299 * 10**8, end_s=29.9, gaps=[],
                death_gap_t_end_s=29.9, warm_start=False, warmup_occupied=False, tracks_per_scan_ratio=1.0,
                track_range_hist={b: {"total": 0, "max_per_scan": 0} for b in BANDS})
    a = dict(base, source="recorded", events=rec_events)
    b = dict(base, source="replay", events=rep_events)
    return a, b


def _observe(i: int, level: int = 1, x: float = 2.0, dx: float = 0.0) -> dict:
    stamp_ns = 8 * 10**9 + i * 10**8
    return dict(stamp_ns=stamp_ns, track_id=1 + (level == 2), level=level, confidence=0.3, x=x + dx, y=1.0,
                extent_m=1.0, elongation=5.0, stillness_s=0.0, peak_v=0.0)


def test_bijection_bar_math():
    bar = replay_detector.bijection_bar
    assert bar(5, missed=1, extra=0) is True and bar(5, missed=2, extra=0) is False
    assert bar(167, missed=17, extra=0) is True and bar(167, missed=18, extra=0) is False
    assert bar(5, missed=0, extra=2) is True and bar(5, missed=0, extra=3) is False
    assert bar(167, missed=0, extra=17) is True and bar(167, missed=0, extra=18) is False
    assert bar(0, missed=0, extra=0) is True

    rec5 = [_observe(i) for i in range(5)]
    a, b = _golden_pair(rec5, rec5[:4])                 # one missed of 5 -> PASS
    code, text = replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")
    assert code == 0 and "PASS" in text and "missed=1" in text and "N_rec=5" in text
    a, b = _golden_pair(rec5, rec5[:3])                 # two missed -> FAIL
    code, text = replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")
    assert code == 1 and "FAIL" in text and "missed=2" in text
    rec167 = [_observe(i) for i in range(167)]
    a, b = _golden_pair(rec167, rec167[:150])           # 17 missed -> PASS
    assert replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")[0] == 0
    a, b = _golden_pair(rec167, rec167[:149])           # 18 missed -> FAIL
    assert replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")[0] == 1
    # tolerances: 0.1 s / 0.09 m still aligns; 0.2 s or 0.11 m does not
    shifted = [dict(e, stamp_ns=e["stamp_ns"] + 10**8, x=e["x"] + 0.09) for e in rec5]
    a, b = _golden_pair(rec5, shifted)
    assert replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")[0] == 0
    far = [dict(e, x=e["x"] + 0.11) for e in rec5]
    a, b = _golden_pair(rec5, far)
    code, text = replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")
    assert code == 1 and "missed=5" in text and "extra=5" in text
    # extras: 2 extra of 5 -> PASS, 3 -> FAIL
    a, b = _golden_pair(rec5, rec5 + [_observe(10), _observe(11)])
    assert replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")[0] == 0
    a, b = _golden_pair(rec5, rec5 + [_observe(10), _observe(11), _observe(12)])
    assert replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")[0] == 1
    # HARD: the WARN multiset on (stamp_ns, level=2) must be equal
    warn = _observe(20, level=2)
    a, b = _golden_pair(rec5 + [warn], rec5 + [dict(warn, stamp_ns=warn["stamp_ns"] + 10**8)])
    code, text = replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")
    assert code == 1 and "WARN" in text
    # the window: events before t0 + settle are ignored on both sides
    early = [dict(e, stamp_ns=e["stamp_ns"] - 5 * 10**9) for e in rec5]   # 3.0..3.4 s < 7.0
    a, b = _golden_pair(rec5 + early, rec5)
    code, text = replay_detector.diff_goldens(a, b, strict=False, settle_s=7.0, end_s=29.9, id_mode="bijection")
    assert code == 0 and "N_rec=5" in text


def test_yaml_loader_matches_node_casts():
    config, flat = replay_detector.load_config(L)
    expected = DetectorConfig(
        min_range_m=0.05, max_range_m=10.0,
        background=BackgroundConfig(window_size=40, warmup_scans=30, foreground_margin_m=0.15,
                                    hold_foreground=True, max_hold_scans=1200, mask_dilation_beams=2),
        cluster=ClusterConfig(eps_m=0.12, min_samples=4, min_points_per_cluster=6),
        tracker=TrackerConfig(association_gate_m=0.5, max_missed_scans=15, velocity_window=10, still_velocity_mps=0.15),
        fall=FallConfig(elongation_ratio=3.5, major_axis_m=0.8, velocity_spike_mps=0.8, sustained_down_s=4.0),
    )
    assert config == expected
    assert len(flat) == 20 and flat["frame_id"] == "laser"
    for key, value in flat.items():
        assert type(value) in (int, float, bool, str), (key, value)
    assert type(flat["background.window_size"]) is int
    assert type(flat["background.hold_foreground"]) is bool
    assert type(flat["min_range_m"]) is float
    assert type(flat["fall.major_axis_m"]) is float and flat["fall.major_axis_m"] == 0.8

    config_y, flat_y = replay_detector.load_config(Y)
    assert isinstance(config_y, DetectorConfig)
    assert set(flat_y) >= set(flat)

    config_set, flat_set = replay_detector.load_config(L, sets=["tracker.association_gate_m=0.6"])
    assert config_set.tracker.association_gate_m == 0.6 and flat_set["tracker.association_gate_m"] == 0.6
    assert dataclasses.replace(config_set, tracker=config.tracker) == config
    with pytest.raises(ValueError, match="tracker.no_such_key"):
        replay_detector.load_config(L, sets=["tracker.no_such_key=1"])
    with pytest.raises(ValueError, match="no_such_section"):
        replay_detector.load_config(L, sets=["no_such_section.x=1"])
    config_bool, _ = replay_detector.load_config(L, sets=["background.hold_foreground=false", "cluster.min_samples=5"])
    assert config_bool.background.hold_foreground is False and config_bool.cluster.min_samples == 5
    assert type(config_bool.cluster.min_samples) is int

    config_legacy, flat_legacy = replay_detector.load_config(Y, legacy=True)
    assert config_legacy.tracker == config.tracker and config_legacy.fall == config.fall
    assert set(flat_legacy) == set(flat)
    config_ls, _ = replay_detector.load_config(Y, legacy=True, sets=["min_range_m=0.3"])
    assert config_ls.min_range_m == 0.3 and config_ls.fall == config.fall


def test_schemas_verb_on_fixture(std_bag, capsys):
    report = replay_detector.schemas_report(std_bag)
    schemas = report["schemas"]
    for name in ("sensor_msgs/msg/LaserScan", "prevera_msgs/msg/FallEvent", "prevera_msgs/msg/PersonTrackArray"):
        encoding, length = schemas[name]
        assert encoding == "ros2msg" and length > 0, (name, schemas[name])
    assert ("/scan", "cdr") in report["channels"]
    assert ("/tracks", "cdr") in report["channels"] and ("/fall_events", "cdr") in report["channels"]
    assert replay_detector.main(["schemas", str(std_bag)]) == 0
    assert "sensor_msgs/msg/LaserScan" in capsys.readouterr().out


def test_transitions_verb_on_scripted_tracks(scripted_bag, tmp_path):
    rows, totals = replay_detector.transitions_report(replay_detector.load_bag(scripted_bag))
    by_id = {r["new_id"]: r for r in rows}
    assert set(by_id) == {9, 1, 2, 3, 4, 5}
    assert by_id[1]["prev_id"] is None and by_id[9]["prev_id"] is None

    a = by_id[2]
    assert a["scan_index"] == 50 and a["prev_id"] == 1
    assert a["old_alive"] is True and a["split_like"] is True
    assert a["distance_m"] == pytest.approx(0.1, abs=1e-6) and a["scans_since"] == 1

    b = by_id[3]
    assert b["scan_index"] == 70 and b["prev_id"] == 1
    assert b["old_alive"] is False and b["split_like"] is False
    assert b["scans_since"] == 10 and b["distance_m"] == pytest.approx(0.05, abs=1e-6)

    c = by_id[4]
    assert c["scan_index"] == 90 and c["prev_id"] == 3
    assert c["old_alive"] is True and c["split_like"] is False
    assert c["distance_m"] == pytest.approx(3.0, abs=1e-6) and c["scans_since"] == 1

    d = by_id[5]
    assert d["scan_index"] == 120 and d["prev_id"] == 3
    assert d["old_alive"] is False and d["split_like"] is False and d["scans_since"] == 20

    assert totals == {"new_ids": 6, "old_alive": 2, "split_like": 1, "with_prev": 4}
    out = tmp_path / "transitions.json"
    assert replay_detector.main(["transitions", str(scripted_bag), "--json", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["totals"] == totals


def _labels(segments: list[tuple[str, float, float]], **extra) -> dict:
    return dict(bag="near", time_base="header_stamp_rel", driver_inverted=False, sensor_height_cm=None,
                segments=[dict(t0=a, t1=b, kind=k, note="") for k, a, b in segments],
                confirmed_by="test 2026-09-26", **extra)


def test_compare_labels_mechanisms_on_near_arc_fixture(near_bag, tmp_path, capsys):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(_labels([("walking", 3.5, 8.0), ("lying", 8.4, 16.0), ("empty", 7.0, 8.0)])), encoding="utf-8")
    capsys.readouterr()
    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--compare-labels", str(labels)]) == 0
    out = capsys.readouterr().out
    result = replay_detector.LAST_COMPARE_LABELS
    seg = {s["kind"]: s for s in result["segments"]}
    assert seg["empty"]["counts"] == {"L1": 20, "L2": 0}
    assert seg["empty"]["mechanisms"] == {"near<0.3": 10, "degenerate": 10}
    assert seg["empty"]["r5_hard"] == "PASS" and seg["empty"]["r5_soft"] == "FAIL"
    assert seg["lying"]["counts"]["L2"] == 1 and seg["lying"]["counts"]["L1"] == 6
    assert "mechanisms" not in seg["lying"]
    assert "R5" in out and "empty" in out

    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--set", "min_range_m=0.3",
                                 "--compare-labels", str(labels)]) == 0
    seg = {s["kind"]: s for s in replay_detector.LAST_COMPARE_LABELS["segments"]}
    assert seg["empty"]["counts"] == {"L1": 10, "L2": 0}
    assert seg["empty"]["mechanisms"] == {"degenerate": 10}

    no_empty = tmp_path / "no_empty.json"
    no_empty.write_text(json.dumps(_labels([("walking", 3.5, 8.0), ("lying", 8.4, 16.0)], no_empty_segment=True,
                                           reason="fixture has no empty segment")), encoding="utf-8")
    capsys.readouterr()
    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--compare-labels", str(no_empty)]) == 0
    out = capsys.readouterr().out
    assert "no empty segment" in out and "R5: N/A" in out and "R5: PASS" not in out
    assert replay_detector.LAST_COMPARE_LABELS["r5"] == "N/A"

    early = tmp_path / "early.json"
    early.write_text(json.dumps(_labels([("empty", 6.9, 8.0)])), encoding="utf-8")
    with pytest.raises(ValueError, match="7.0"):
        replay_detector.compare_labels_file(near_bag, early, params=L)


def test_track_range_hist_and_sanity_near_hist(near_bag, tmp_path):
    rep, rec = tmp_path / "near_rep.json", tmp_path / "near_rec.json"
    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--track-range-hist", "--json", str(rep)]) == 0
    assert replay_detector.main(["extract", str(near_bag), "--json", str(rec)]) == 0
    hist = replay_detector.load_golden(rep)["track_range_hist"]
    assert list(hist) == BANDS
    assert hist["[0.1,0.2)"] == {"total": 120, "max_per_scan": 1}
    assert hist["[0.5,inf)"] == {"total": 245, "max_per_scan": 2}
    for band in ("[0,0.1)", "[0.2,0.3)", "[0.3,0.4)", "[0.4,0.5)"):
        assert hist[band] == {"total": 0, "max_per_scan": 0}, band
    san = replay_detector.sanity_report(replay_detector.load_bag(near_bag))
    assert san["near_track_range_hist"] == hist
    assert replay_detector.load_golden(rec)["track_range_hist"] == hist


def test_min_range_removes_near_track_on_fixture(near_bag, tmp_path):
    out = tmp_path / "near_minrange.json"
    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--set", "min_range_m=0.3",
                                 "--track-range-hist", "--json", str(out)]) == 0
    g = replay_detector.load_golden(out)
    assert g["config"]["min_range_m"] == 0.3
    for band in ("[0,0.1)", "[0.1,0.2)", "[0.2,0.3)"):
        assert g["track_range_hist"][band] == {"total": 0, "max_per_scan": 0}, band
    warns = [e for e in g["events"] if e["level"] == 2]
    assert len(warns) == 2
    assert len(_warn_at(g["events"], 2.4, 1.4, 0.25)) == 1 and len(_warn_at(g["events"], 1.0, -0.06, 0.1)) == 1
    assert sum(1 for e in g["events"] if e["level"] == 1) == 46
    # and under L unmodified the near arc adds a third WARN (Appendix E)
    out_l = tmp_path / "near_l.json"
    assert replay_detector.main(["replay", str(near_bag), "--params", str(L), "--json", str(out_l)]) == 0
    g_l = replay_detector.load_golden(out_l)
    assert sum(1 for e in g_l["events"] if e["level"] == 2) == 3
    assert sum(1 for e in g_l["events"] if e["level"] == 1) == 86


def test_spawn_diagnostics_outside_classification(std_bag, near_bag):
    config, flat = replay_detector.load_config(L)
    result = replay_detector.replay_bag(replay_detector.load_bag(std_bag), config, flat, spawn_diagnostics=True)
    spawns = sorted(result.spawns, key=lambda s: s["stamp_ns"])
    assert len(spawns) == 2, spawns
    person, line = spawns
    assert person["stamp_ns"] == int(3.5e9) and person["path"] == "no-candidate"
    assert person["nearest_live_id"] is None and person["nearest_evicted_id"] is None
    assert line["stamp_ns"] == int(4.0e9) and line["path"] == "gate-fail"
    assert line["nearest_live_id"] == person["track_id"] and line["nearest_live_m"] > 0.5
    assert line["nearest_live_matched"] is True
    assert math.hypot(line["x"] - 1.0, line["y"] + 0.06) <= 0.1

    result = replay_detector.replay_bag(replay_detector.load_bag(near_bag), config, flat, spawn_diagnostics=True)
    spawns = sorted(result.spawns, key=lambda s: s["stamp_ns"])
    assert len(spawns) == 3, spawns
    near = [s for s in spawns if math.hypot(s["x"], s["y"]) < 0.3]
    assert len(near) == 1 and near[0]["stamp_ns"] == int(4.0e9) and near[0]["path"] == "gate-fail"
    assert {s["path"] for s in spawns} == {"no-candidate", "gate-fail"}
    assert replay_detector.main(["replay", str(std_bag), "--params", str(L), "--spawn-diagnostics"]) == 0


def test_per_second_table_on_scripted_tracks(scripted_bag, capsys):
    bag = replay_detector.load_bag(scripted_bag)
    rows = replay_detector.per_second_table(bag)
    by_s = {r["second"]: r for r in rows}
    assert set(by_s) == set(range(3, 16))
    assert all(r["best_id"] != 9 for r in rows)
    assert all(r["near"] == 10 for r in rows)
    assert by_s[3]["best_id"] == 1 and by_s[5]["best_id"] == 1 and by_s[6]["best_id"] == 1
    assert by_s[7]["best_id"] == 3 and by_s[9]["best_id"] == 3 and by_s[10]["best_id"] == 3
    assert by_s[11]["best_id"] is None
    assert all(by_s[s]["best_id"] == 5 for s in range(12, 16))
    assert by_s[9]["extent_m"] == pytest.approx(0.9, rel=1e-6)
    capsys.readouterr()
    assert replay_detector.main(["extract", str(scripted_bag), "--per-second"]) == 0
    out = capsys.readouterr().out
    assert "PER-SECOND" in out and "#9" not in out and "#3" in out
