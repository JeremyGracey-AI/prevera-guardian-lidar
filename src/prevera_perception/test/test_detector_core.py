"""detector_core: ROS-free detector equals the pre-refactor node (plan v4, step 2).

The golden test drives override set v3 (`prevera_perception.synthetic_scene.overrides_v3`)
through `DetectorCore.process` and, on the same scan arrays, through the legacy pipeline
`Background` + `legacy_reference._scan_to_points` + `cluster_points` + `Tracker` +
`legacy_reference._emit_fall_events` (verbatim from commit 36ca257).

The legacy thresholds are hardcoded here on purpose (the `T/test_synthetic_fall.py` pattern,
not read from the yaml) so later config commits cannot move this golden.

Round-2 values on the pinned Mac venv (Python 3.10.21, numpy 1.26.4, sklearn 1.7.2; plan
Appendix D): line WARN 8.0 s conf 0.6 still 4.0 peak 0.0 at (1.0, -0.057); person WARN 9.0 s
conf 0.56 still 0.6 peak 1.52 at (2.301, 1.282); 46 OBSERVE. Only the DBSCAN-sensitive person
values are asserted as windows.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from prevera_perception.background import Background, BackgroundConfig
from prevera_perception.clustering import ClusterConfig, cluster_points
from prevera_perception.detector_core import (
    AlertLevel,
    DetectorConfig,
    DetectorCore,
    Event,
    FallConfig,
    ScanResult,
    looks_horizontal,
    scan_to_points,
)
from prevera_perception.synthetic_scene import SyntheticScene, overrides_v3
from prevera_perception.tracker import Tracker, TrackerConfig

from legacy_reference import LegacyReference

pytestmark = pytest.mark.filterwarnings("error::RuntimeWarning")

_TEST_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _TEST_DIR.parent / "prevera_perception"
_REPO_ROOT = _TEST_DIR.parents[2]
_NODE_PATH = _PACKAGE_DIR / "fall_detector_node.py"
_YAML_PATH = _REPO_ROOT / "src" / "prevera_bringup" / "config" / "fall_detector.yaml"
_MSG_PATH = _REPO_ROOT / "src" / "prevera_msgs" / "msg" / "FallEvent.msg"

# Legacy thresholds, hardcoded (36ca257 `_declare_parameters` + fall_detector.yaml at 36ca257).
MIN_RANGE_M = 0.05
MAX_RANGE_M = 10.0
FALL_ELONGATION = 3.5
FALL_MAJOR_AXIS_M = 0.8
VELOCITY_SPIKE_MPS = 0.8
SUSTAINED_DOWN_S = 4.0

BG = BackgroundConfig(
    window_size=40, warmup_scans=30, foreground_margin_m=0.15,
    hold_foreground=True, max_hold_scans=1200, mask_dilation_beams=2,
)
CL = ClusterConfig(eps_m=0.12, min_samples=4, min_points_per_cluster=6)
TR = TrackerConfig(association_gate_m=0.5, max_missed_scans=15, velocity_window=10, still_velocity_mps=0.15)
FALL = FallConfig(
    elongation_ratio=FALL_ELONGATION, major_axis_m=FALL_MAJOR_AXIS_M,
    velocity_spike_mps=VELOCITY_SPIKE_MPS, sustained_down_s=SUSTAINED_DOWN_S,
)
CONFIG = DetectorConfig(
    min_range_m=MIN_RANGE_M, max_range_m=MAX_RANGE_M,
    background=BG, cluster=CL, tracker=TR, fall=FALL,
)

ANGLE_MIN = SyntheticScene.ANGLE_MIN
ANGLE_INCREMENT = SyntheticScene.ANGLE_INCREMENT
N_SCANS = 160
WARMUP = BG.warmup_scans
OVERRIDE_BEAMS = (5, 6, 7, 8)


def _scene() -> SyntheticScene:
    return SyntheticScene(np.random.default_rng(42))


def _legacy() -> LegacyReference:
    return LegacyReference(
        min_range_m=MIN_RANGE_M, max_range_m=MAX_RANGE_M,
        fall_elongation=FALL_ELONGATION, fall_major_axis_m=FALL_MAJOR_AXIS_M,
        velocity_spike_mps=VELOCITY_SPIKE_MPS, sustained_down_s=SUSTAINED_DOWN_S,
    )


def _track_tuple(track) -> tuple:
    return (
        track.track_id,
        tuple(float(v) for v in track.centroid),
        track.stillness_s,
        track.elongation,
        track.major_axis_m,
    )


def _beams_of(points: np.ndarray) -> set[int]:
    beams = set()
    for x, y in points:
        angle = math.atan2(float(y), float(x))
        beams.add(int(round((angle - ANGLE_MIN) / ANGLE_INCREMENT)) % SyntheticScene.NUM_BEAMS)
    return beams


@dataclasses.dataclass
class _ScanRecord:
    index: int
    stamp_s: float
    core: ScanResult | None
    core_tracks: list[tuple]
    horizontal_ids: set[int]
    legacy_tracks: list[tuple] | None
    legacy_events: list[dict] | None
    fg_flags: dict[int, bool] | None
    point_beams: set[int] | None


@pytest.fixture(scope="module")
def golden() -> list[_ScanRecord]:
    """One pass over override set v3 feeding the same scan array to three consumers."""
    scene = _scene()
    core = DetectorCore(CONFIG)
    legacy, legacy_bg, legacy_tracker = _legacy(), Background(BG), Tracker(TR)
    direct_bg = Background(BG)
    msg = SimpleNamespace(angle_min=ANGLE_MIN, angle_increment=ANGLE_INCREMENT)
    records: list[_ScanRecord] = []
    for i in range(N_SCANS):
        t = i * 0.1
        ranges = scene.build_scan(t, overrides_v3(i))

        # (a) the core
        result = core.process(ranges, ANGLE_MIN, ANGLE_INCREMENT, t)
        core_tracks = [_track_tuple(tr) for tr in result.tracks] if result is not None else []
        horizontal_ids = (
            {tr.track_id for tr in result.tracks if looks_horizontal(tr, FALL)} if result is not None else set()
        )

        # (b) the legacy pipeline, verbatim functions
        if not legacy_bg.ready:
            legacy_bg.update(ranges)
            legacy_tracks = legacy_events = None
        else:
            fg = legacy_bg.foreground_mask(ranges)
            legacy_bg.update(ranges, foreground=fg)
            points = legacy._scan_to_points(msg, ranges, fg)
            tracks = legacy_tracker.update(cluster_points(points, CL), t)
            legacy_tracks = [_track_tuple(tr) for tr in tracks]
            legacy_events = legacy._emit_fall_events(tracks)

        # (c) foreground_mask + scan_to_points directly
        if not direct_bg.ready:
            direct_bg.update(ranges)
            fg_flags = point_beams = None
        else:
            fg = direct_bg.foreground_mask(ranges)
            direct_bg.update(ranges, foreground=fg)
            points = scan_to_points(ranges, ANGLE_MIN, ANGLE_INCREMENT, fg, MIN_RANGE_M, MAX_RANGE_M)
            fg_flags = {b: bool(fg[b]) for b in OVERRIDE_BEAMS}
            point_beams = _beams_of(points)

        records.append(_ScanRecord(
            index=i, stamp_s=t, core=result, core_tracks=core_tracks, horizontal_ids=horizontal_ids,
            legacy_tracks=legacy_tracks, legacy_events=legacy_events,
            fg_flags=fg_flags, point_beams=point_beams,
        ))
    return records


def test_alert_level_matches_msg():
    source = _MSG_PATH.read_text(encoding="utf-8")
    declared = {m.group(1): int(m.group(2)) for m in re.finditer(r"^uint8\s+(\w+)\s*=\s*(\d+)", source, re.M)}
    assert declared, _MSG_PATH
    for name, value in declared.items():
        assert AlertLevel[name] == value, (name, value)
    assert {lvl.name for lvl in AlertLevel} == set(declared)


def test_warmup_returns_none():
    scene, core = _scene(), DetectorCore(CONFIG)
    for i in range(WARMUP):
        assert core.process(scene.build_scan(i * 0.1, overrides_v3(i)), ANGLE_MIN, ANGLE_INCREMENT, i * 0.1) is None
    result = core.process(scene.build_scan(WARMUP * 0.1, overrides_v3(WARMUP)), ANGLE_MIN, ANGLE_INCREMENT, WARMUP * 0.1)
    assert isinstance(result, ScanResult)


def test_core_matches_legacy_reference_golden(golden):
    # Per-scan identity with the verbatim legacy functions.
    for rec in golden:
        if rec.index < WARMUP:
            assert rec.core is None and rec.legacy_tracks is None
            continue
        assert rec.core is not None and rec.legacy_tracks is not None
        assert rec.core_tracks == rec.legacy_tracks, rec.index
        core_events = [(int(ev.level), ev.track_id, ev.confidence, ev.elongation) for ev in rec.core.events]
        legacy_events = [
            (e["alert_level"], e["track_id"], e["confidence"], e["elongation_ratio"]) for e in rec.legacy_events
        ]
        assert core_events == legacy_events, rec.index

    # One WARN per track id; OBSERVE every scan for horizontal, not-yet-alerted tracks.
    alerted: set[int] = set()
    warn_count: dict[int, int] = {}
    warns: list[tuple[float, Event]] = []
    observe_total = 0
    for rec in golden:
        if rec.core is None:
            continue
        event_ids = [ev.track_id for ev in rec.core.events]
        assert len(event_ids) == len(set(event_ids)), rec.index
        assert set(event_ids) == rec.horizontal_ids - alerted, rec.index
        for ev in rec.core.events:
            assert ev.level in (AlertLevel.OBSERVE, AlertLevel.WARN), ev
            if ev.level == AlertLevel.WARN:
                warn_count[ev.track_id] = warn_count.get(ev.track_id, 0) + 1
                warns.append((rec.stamp_s, ev))
                alerted.add(ev.track_id)
            else:
                observe_total += 1
    assert all(n == 1 for n in warn_count.values()), warn_count

    # Override-set facts: beams 5-8 (Appendix D).
    for rec in golden:
        if rec.fg_flags is None:
            continue
        if rec.index >= 40:
            assert rec.fg_flags == {5: False, 6: True, 7: True, 8: False}, rec.index
        else:
            assert rec.fg_flags == {5: False, 6: False, 7: False, 8: False}, rec.index
        assert not (rec.point_beams & set(OVERRIDE_BEAMS)), (rec.index, rec.point_beams & set(OVERRIDE_BEAMS))

    # Bounded golden facts.
    assert len(warns) == 2, warns
    line = [(t, ev) for t, ev in warns if math.hypot(ev.x - 1.0, ev.y + 0.06) <= 0.1]
    person = [(t, ev) for t, ev in warns if math.hypot(ev.x - 2.4, ev.y - 1.4) <= 0.25]
    assert len(line) == 1 and len(person) == 1, warns
    (t_line, ev_line), (t_person, ev_person) = line[0], person[0]
    assert t_line == pytest.approx(8.0, abs=1e-9)
    assert ev_line.confidence == 0.6
    assert ev_line.peak_recent_velocity == 0.0
    assert ev_line.stillness_s == pytest.approx(4.0, abs=1e-9)
    assert ev_line.elongation == 1e6
    assert 8.6 <= t_person <= 9.4, t_person
    assert ev_person.peak_recent_velocity >= 0.8
    assert 0.5 < ev_person.stillness_s <= 1.0, ev_person.stillness_s
    assert ev_person.confidence == pytest.approx(min(1.0, 0.5 + 0.1 * ev_person.stillness_s), abs=1e-6)
    print(
        f"GOLDEN line_warn={t_line:.1f}s person_warn={t_person:.1f}s "
        f"person_conf={ev_person.confidence} person_still={ev_person.stillness_s} "
        f"person_peak={ev_person.peak_recent_velocity} person_xy=({ev_person.x:.3f}, {ev_person.y:.3f}) "
        f"observe_total={observe_total}"
    )


def test_event_fields_are_python_floats(golden):
    events = [ev for rec in golden if rec.core is not None for ev in rec.core.events]
    assert events
    for ev in events:
        assert type(ev.track_id) is int
        for name in ("x", "y", "confidence", "major_axis_m", "elongation", "stillness_s", "peak_recent_velocity"):
            assert type(getattr(ev, name)) is float, (name, type(getattr(ev, name)))
        json.dumps(dataclasses.asdict(ev), allow_nan=False)


def test_degenerate_cluster_event_is_clamped_and_json_finite():
    # Scene time pinned at 0.0 s: no person, only the v3 line cluster from scan index 40.
    scene, core = _scene(), DetectorCore(CONFIG)
    strict = DetectorCore(dataclasses.replace(CONFIG, fall=dataclasses.replace(FALL, degenerate_requires_extent=True)))
    events, strict_events = [], []
    for i in range(60):
        ranges = scene.build_scan(0.0, overrides_v3(i))
        result = core.process(ranges, ANGLE_MIN, ANGLE_INCREMENT, i * 0.1)
        strict_result = strict.process(ranges, ANGLE_MIN, ANGLE_INCREMENT, i * 0.1)
        if result is not None:
            events.extend(result.events)
        if strict_result is not None:
            strict_events.extend(strict_result.events)
    assert events
    assert all(ev.elongation == 1e6 for ev in events)
    for ev in events:
        json.dumps(dataclasses.asdict(ev), allow_nan=False)

    [track] = core.tracker.tracks
    assert math.isinf(track.elongation)
    assert 0.05 < track.major_axis_m < 0.07 < FALL.major_axis_m
    assert looks_horizontal(track, FALL) is True
    assert looks_horizontal(track, dataclasses.replace(FALL, degenerate_requires_extent=True)) is False
    assert strict_events == []


def test_min_range_filters():
    ranges = np.array([0.2, 2.0], dtype=np.float32)
    foreground = np.array([True, True])
    near_off = scan_to_points(ranges, 0.0, 0.1, foreground, 0.3, MAX_RANGE_M)
    assert near_off.shape == (1, 2) and near_off.dtype == np.float32
    assert float(np.hypot(*near_off[0])) == pytest.approx(2.0, rel=1e-6)
    both = scan_to_points(ranges, 0.0, 0.1, foreground, 0.05, MAX_RANGE_M)
    assert both.shape == (2, 2)


def _flatten(mapping: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in mapping.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{path}."))
        else:
            out[path] = value
    return out


def _config_paths(obj, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for f in dataclasses.fields(obj):
        value = getattr(obj, f.name)
        if dataclasses.is_dataclass(value):
            paths |= _config_paths(value, f"{prefix}{f.name}.")
        else:
            paths.add(f"{prefix}{f.name}")
    return paths


def test_yaml_keys_match_declared_parameters():
    yaml_params = _flatten(yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))["fall_detector"]["ros__parameters"])
    node_source = _NODE_PATH.read_text(encoding="utf-8")
    declared = {
        m.group(1): ast.literal_eval(m.group(2))
        for m in re.finditer(r'self\.declare_parameter\("([^"]+)",\s*([^)]+)\)', node_source)
    }
    assert set(declared) == set(yaml_params)
    assert len(declared) == 20
    config_paths = _config_paths(CONFIG)
    assert set(declared) - {"frame_id"} <= config_paths, set(declared) - {"frame_id"} - config_paths
    mismatches = {k for k in declared if yaml_params[k] != declared[k]}
    assert mismatches == {"fall.major_axis_m"}, mismatches
