"""Offline replay harness: run `DetectorCore` over a recorded bag without ROS (plan v4 step 3).

    python3 replay_detector.py replay <bag> [--params Y] [--legacy] [--set k=v ...] [--json out.json]
                                          [--spawn-diagnostics] [--compare-labels labels.json]
                                          [--per-second] [--track-range-hist] [--settle-s S] [--end-s E]
    python3 replay_detector.py extract <bag> [--json out.json] [--per-second] [--track-range-hist]
    python3 replay_detector.py diff a.json b.json [--strict | --settle-s S --end-s E --id-mode bijection]
    python3 replay_detector.py divergence <bag> [--params ...]
    python3 replay_detector.py sanity <bag>
    python3 replay_detector.py schemas <bag>
    python3 replay_detector.py transitions <bag> [--json rows.json]

Time base everywhere: the header stamp, `sec + nanosec * 1e-9` (`fall_detector_node.py:113`),
never the mcap log time. Golden JSON stores `stamp_ns = sec * 10**9 + nanosec` as an int and
every float through `float(np.float32(v))` (the wire is float32); files are written with
`allow_nan=False` and loaded with a parser that rejects `Infinity`/`NaN`.

Config precedence: `--params` is loaded first (node casts, unknown key raises, missing key takes
the dataclass default), then `--legacy` keeps only the keys present in `params/2026-09-25-live.yaml`
(the 36ca257 snapshot), then every `--set key=value` is applied last and always honoured.

`--end-s` (header-stamp-relative seconds) defaults to `death_gap_t_end_s`: the stamp, relative to
the first `/scan`, of the last `/scan` before the first inter-scan gap > 5.0 s (or the last `/scan`).
Scans after it are ignored by every bag verb. `--settle-s` (default 7.0) is the evaluation-window
start used by `diff --id-mode bijection`, `divergence` and the `/tracks`-per-`/scan` ratio.

This module imports only `prevera_perception.detector_core` (plus the config dataclasses from
`background`/`clustering`/`tracker`) and `prevera_perception.synthetic_scene`; never the node.
`rosbag2_py` is imported lazily inside the rosbag2 reader only.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import numpy as np
import yaml

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[1]
PACKAGE_SRC = REPO_ROOT / "src" / "prevera_perception"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from prevera_perception.background import BackgroundConfig  # noqa: E402
from prevera_perception.clustering import ClusterConfig  # noqa: E402
from prevera_perception.detector_core import (  # noqa: E402
    AlertLevel,
    DetectorConfig,
    DetectorCore,
    Event,
    FallConfig,
)
from prevera_perception.tracker import Track, TrackerConfig  # noqa: E402

L_PATH = HARNESS_DIR / "params" / "2026-09-25-live.yaml"
Y_PATH = REPO_ROOT / "src" / "prevera_bringup" / "config" / "fall_detector.yaml"

SCAN_TOPIC, TRACKS_TOPIC, EVENTS_TOPIC = "/scan", "/tracks", "/fall_events"
TOPICS = [SCAN_TOPIC, TRACKS_TOPIC, EVENTS_TOPIC]

BAND_EDGES = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, math.inf)]
BANDS = ["[0,0.1)", "[0.1,0.2)", "[0.2,0.3)", "[0.3,0.4)", "[0.4,0.5)", "[0.5,inf)"]

DEFAULT_SETTLE_S = 7.0          # background.warmup_scans + background.window_size at 10 Hz
DEATH_GAP_S = 5.0               # section 1: first inter-scan gap > 5 s ends the evaluation window
GAP_FACTOR = 1.5                # sanity: report stamp gaps > 1.5x the median dt
WARM_START_SCANS = 30           # any /tracks within the first 30 scans -> live node was warm
OCCUPIED_SCANS = 70             # a non-near recorded track within the first 70 scans
NEAR_RANGE_M = 0.4              # fall_timeline.py:22-23 "person-like" = range > 0.4 m
ALIGN_DT_S = 0.15               # OBSERVE alignment tolerances (section 1)
ALIGN_DIST_M = 0.10
FLOAT_REL, FLOAT_ABS = 1e-6, 1e-4
DIV_CENTROID_M, DIV_EXTENT_M, DIV_ELONG_REL, DIV_AGE_S = 0.02, 0.02, 1e-3, 0.05
BAND_EXTENT_M, BAND_ELONG_REL = 0.02, 2e-3
EVICTED_MEMORY_S = 10.0
AGREEMENT_S = 3.0
ELONGATION_CLAMP = 1e6
MECHANISMS = ("near<0.3", "band 0.3-0.4", "degenerate", "other")

LAST_COMPARE_LABELS: dict | None = None   # set by `replay --compare-labels` (test hook)


def _f32(v: float) -> float:
    return float(np.float32(v))


def _isclose(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=FLOAT_REL, abs_tol=FLOAT_ABS)


# =============================================================================== config


_SECTIONS: dict[str, type] = {
    "background": BackgroundConfig,
    "cluster": ClusterConfig,
    "tracker": TrackerConfig,
    "fall": FallConfig,
}
_CASTS: dict[str, type] = {"int": int, "float": float, "bool": bool, "str": str}
NODE_ONLY_KEYS: dict[str, type] = {"frame_id": str}   # declared by the node, not part of DetectorConfig


def _field_types(cls: type) -> dict[str, type]:
    out = {}
    for f in dataclasses.fields(cls):
        name = f.type if isinstance(f.type, str) else f.type.__name__
        if name in _CASTS:           # nested config dataclasses (sections) are handled by _SECTIONS
            out[f.name] = _CASTS[name]
    return out


def _flatten(mapping: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in mapping.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{path}."))
        else:
            out[path] = value
    return out


def _key_type(key: str) -> type:
    if "." in key:
        section, name = key.split(".", 1)
        if section not in _SECTIONS:
            raise ValueError(f"unknown config key {key!r}: no section {section!r}")
        types = _field_types(_SECTIONS[section])
        if name not in types:
            raise ValueError(f"unknown config key {key!r}: {section!r} has no field {name!r}")
        return types[name]
    if key in NODE_ONLY_KEYS:
        return NODE_ONLY_KEYS[key]
    top = _field_types(DetectorConfig)
    if key not in top:
        raise ValueError(f"unknown config key {key!r}")
    return top[key]


def _cast(key: str, value: object, typ: type) -> object:
    # The node's casts (fall_detector_node.py:80-105): int(), float(), bool() per declared type.
    if typ is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.strip().lower() in ("true", "1", "yes", "on"):
                return True
            if value.strip().lower() in ("false", "0", "no", "off"):
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError(f"{key}: cannot read {value!r} as bool")
    if typ is int:
        if isinstance(value, str):
            return int(value.strip())
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{key}: {value!r} is not an int")
        return int(value)
    if typ is float:
        return float(value)
    return str(value)


def legacy_keys() -> set[str]:
    """The dotted keys of `params/2026-09-25-live.yaml` (36ca257 snapshot): the legacy set."""
    raw = yaml.safe_load(L_PATH.read_text(encoding="utf-8"))
    return set(_flatten(raw["fall_detector"]["ros__parameters"]))


def load_config(
    params: Path | str = Y_PATH, legacy: bool = False, sets: Sequence[str] = ()
) -> tuple[DetectorConfig, dict[str, object]]:
    """Load a `fall_detector.ros__parameters` yaml into `DetectorConfig` plus the flat dotted dict."""
    params = Path(params)
    raw = yaml.safe_load(params.read_text(encoding="utf-8"))
    try:
        section = raw["fall_detector"]["ros__parameters"]
    except (KeyError, TypeError):
        raise ValueError(f"{params}: expected fall_detector.ros__parameters") from None
    flat: dict[str, object] = {}
    for key, value in _flatten(section).items():
        flat[key] = _cast(key, value, _key_type(key))
    if legacy:
        keep = legacy_keys()
        flat = {k: v for k, v in flat.items() if k in keep}
    for item in sets:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"--set expects key=value, got {item!r}")
        key = key.strip()
        flat[key] = _cast(key, value.strip(), _key_type(key))
    return _build_config(flat), flat


def _build_config(flat: dict[str, object]) -> DetectorConfig:
    kwargs: dict[str, object] = {}
    for section, cls in _SECTIONS.items():
        sec_kw = {k.split(".", 1)[1]: v for k, v in flat.items() if k.startswith(section + ".")}
        try:
            kwargs[section] = cls(**sec_kw)
        except TypeError as exc:
            raise ValueError(f"config section {section!r}: {exc}") from None
    top = {k: v for k, v in flat.items() if "." not in k and k not in NODE_ONLY_KEYS}
    try:
        return DetectorConfig(**top, **kwargs)
    except TypeError as exc:
        raise ValueError(f"config: {exc}") from None


def config_sha256(flat: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(flat, sort_keys=True).encode("utf-8")).hexdigest()


def code_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# =============================================================================== bag readers


@dataclasses.dataclass
class Msg:
    stamp_ns: int       # header.stamp.sec * 10**9 + nanosec
    log_ns: int         # mcap log time (never used for time arithmetic)
    msg: object


@dataclasses.dataclass
class Bag:
    path: Path
    scans: list[Msg]
    tracks: list[Msg]
    events: list[Msg]
    topic_counts: dict[str, int]

    @property
    def t0_ns(self) -> int:
        if not self.scans:
            raise ValueError(f"{self.path}: no {SCAN_TOPIC} messages")
        return self.scans[0].stamp_ns


def header_ns(msg: object) -> int:
    return int(msg.header.stamp.sec) * 10**9 + int(msg.header.stamp.nanosec)


def header_s(msg: object) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def mcap_files(path: Path | str) -> list[Path]:
    path = Path(path)
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.mcap"))   # rosbag2 splits: <name>_0.mcap, <name>_1.mcap, ...
    if not files:
        raise FileNotFoundError(f"{path}: no *.mcap files")
    return files


def _iter_mcap(path: Path | str) -> Iterator[tuple[str, int, int, object]]:
    from mcap.reader import make_reader
    from mcap_ros2.decoder import DecoderFactory

    for file in mcap_files(path):
        with open(file, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            for _schema, channel, message, decoded in reader.iter_decoded_messages(topics=TOPICS):
                yield channel.topic, header_ns(decoded), int(message.log_time), decoded


def _iter_rosbag2(path: Path | str) -> Iterator[tuple[str, int, int, object]]:
    # fall_timeline.py:10-21, emitting header stamps (WSL fallback when the mcap schemas are empty).
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="mcap"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    while reader.has_next():
        topic, data, log_ns = reader.read_next()
        if topic not in TOPICS:
            continue
        decoded = deserialize_message(data, get_message(types[topic]))
        yield topic, header_ns(decoded), int(log_ns), decoded


def load_bag(path: Path | str, reader: str = "mcap") -> Bag:
    it = _iter_mcap(path) if reader == "mcap" else _iter_rosbag2(path)
    scans: list[Msg] = []
    tracks: list[Msg] = []
    events: list[Msg] = []
    counts: Counter[str] = Counter()
    for topic, stamp_ns, log_ns, decoded in it:
        counts[topic] += 1
        item = Msg(stamp_ns, log_ns, decoded)
        if topic == SCAN_TOPIC:
            scans.append(item)
        elif topic == TRACKS_TOPIC:
            tracks.append(item)
        else:
            events.append(item)
    if not scans:
        raise ValueError(f"{path}: no {SCAN_TOPIC} messages")
    return Bag(Path(path), scans, tracks, events, dict(counts))


# =============================================================================== bag facts


def compute_gaps(stamps_ns: Sequence[int]) -> tuple[float | None, list[list]]:
    """Median dt and `[[stamp_ns of the scan before the gap, dt_s], ...]` for dt > 1.5x median."""
    if len(stamps_ns) < 2:
        return None, []
    dts = np.diff(np.asarray(stamps_ns, dtype=np.int64)) / 1e9
    median = float(np.median(dts))
    gaps = [[int(stamps_ns[i]), float(dt)] for i, dt in enumerate(dts) if dt > GAP_FACTOR * median]
    return median, gaps


def death_gap_t_end(stamps_ns: Sequence[int]) -> tuple[float, int]:
    """(`death_gap_t_end_s` relative to the first scan, absolute stamp_ns)."""
    t0 = stamps_ns[0]
    end = stamps_ns[-1]
    for i in range(1, len(stamps_ns)):
        if (stamps_ns[i] - stamps_ns[i - 1]) / 1e9 > DEATH_GAP_S:
            end = stamps_ns[i - 1]
            break
    return (end - t0) / 1e9, int(end)


def _range(x: float, y: float) -> float:
    return math.hypot(float(x), float(y))


def warm_flags(bag: Bag) -> tuple[bool, bool]:
    """(`warm_start`, `warmup_occupied`) from the recorded `/tracks` (section 1)."""
    scans = bag.scans
    warm_limit = scans[min(WARM_START_SCANS, len(scans)) - 1].stamp_ns
    occupied_limit = scans[min(OCCUPIED_SCANS, len(scans)) - 1].stamp_ns
    warm_start = any(m.stamp_ns <= warm_limit for m in bag.tracks)
    warmup_occupied = any(
        _range(t.centroid.x, t.centroid.y) > NEAR_RANGE_M
        for m in bag.tracks if m.stamp_ns <= occupied_limit
        for t in m.msg.tracks
    )
    return warm_start, warmup_occupied


def tracks_per_scan_ratio(bag: Bag, settle_s: float, end_ns: int) -> float | None:
    start_ns = bag.t0_ns + int(round(settle_s * 1e9))
    stamps = [m.stamp_ns for m in bag.scans if start_ns <= m.stamp_ns <= end_ns]
    if not stamps:
        return None
    have = {m.stamp_ns for m in bag.tracks}
    return sum(1 for s in stamps if s in have) / len(stamps)


def empty_hist() -> dict[str, dict[str, int]]:
    return {band: {"total": 0, "max_per_scan": 0} for band in BANDS}


def hist_add_scan(hist: dict[str, dict[str, int]], ranges: Iterable[float]) -> None:
    per = Counter()
    for r in ranges:
        for band, (lo, hi) in zip(BANDS, BAND_EDGES):
            if lo <= r < hi:
                per[band] += 1
                break
    for band in BANDS:
        hist[band]["total"] += per[band]
        hist[band]["max_per_scan"] = max(hist[band]["max_per_scan"], per[band])


def recorded_track_hist(bag: Bag, end_ns: int) -> dict[str, dict[str, int]]:
    hist = empty_hist()
    for m in bag.tracks:
        if bag.t0_ns <= m.stamp_ns <= end_ns:
            hist_add_scan(hist, (_range(t.centroid.x, t.centroid.y) for t in m.msg.tracks))
    return hist


def resolve_end(bag: Bag, end_s: float | None) -> tuple[float, int]:
    """`--end-s` default = death_gap_t_end_s. Returns (end_s, absolute end stamp ns)."""
    if end_s is None:
        end_s, _ = death_gap_t_end([m.stamp_ns for m in bag.scans])
    return float(end_s), bag.t0_ns + int(round(float(end_s) * 1e9))


def sanity_report(bag: Bag, settle_s: float = DEFAULT_SETTLE_S) -> dict:
    stamps = [m.stamp_ns for m in bag.scans]
    median_dt, gaps = compute_gaps(stamps)
    dg_s, dg_ns = death_gap_t_end(stamps)
    warm_start, warmup_occupied = warm_flags(bag)
    beam_hist = Counter(len(m.msg.ranges) for m in bag.scans)
    return {
        "bag": bag.path.name,
        "scan_count": len(bag.scans),
        "beam_count_hist": {int(k): v for k, v in sorted(beam_hist.items())},
        "first_stamp_ns": bag.t0_ns,
        "first_stamp_s": bag.t0_ns / 1e9,
        "last_stamp_ns": stamps[-1],
        "duration_s": (stamps[-1] - bag.t0_ns) / 1e9,
        "median_dt_s": median_dt,
        "gaps": gaps,
        "death_gap_t_end_s": dg_s,
        "death_gap_t_end_stamp_ns": dg_ns,
        "tracks_per_scan_ratio": tracks_per_scan_ratio(bag, settle_s, dg_ns),
        "warm_start": warm_start,
        "warmup_occupied": warmup_occupied,
        "topic_counts": dict(bag.topic_counts),
        "near_track_range_hist": recorded_track_hist(bag, dg_ns),
    }


def format_sanity(report: dict) -> str:
    lines = [f"SANITY {report['bag']}"]
    for key in ("scan_count", "beam_count_hist", "first_stamp_ns", "first_stamp_s", "last_stamp_ns", "duration_s",
                "median_dt_s", "death_gap_t_end_s", "death_gap_t_end_stamp_ns", "tracks_per_scan_ratio",
                "warm_start", "warmup_occupied", "topic_counts"):
        lines.append(f"  {key}: {report[key]}")
    lines.append(f"  gaps (> {GAP_FACTOR}x median dt): {len(report['gaps'])}")
    for stamp_ns, dt in report["gaps"][:20]:
        lines.append(f"    after stamp_ns={stamp_ns} (t={(stamp_ns - report['first_stamp_ns']) / 1e9:.3f} s): dt={dt:.3f} s")
    lines.append("  near_track_range_hist (recorded /tracks, band: total / max_per_scan):")
    for band, v in report["near_track_range_hist"].items():
        lines.append(f"    {band:>10}: {v['total']} / {v['max_per_scan']}")
    return "\n".join(lines)


# =============================================================================== golden JSON


def event_dict(stamp_ns: int, ev: Event) -> dict:
    return {
        "stamp_ns": int(stamp_ns),
        "track_id": int(ev.track_id),
        "level": int(ev.level),
        "confidence": _f32(ev.confidence),
        "x": _f32(ev.x),
        "y": _f32(ev.y),
        "extent_m": _f32(ev.major_axis_m),
        "elongation": _f32(min(ev.elongation, ELONGATION_CLAMP)),
        "stillness_s": _f32(ev.stillness_s),
        "peak_v": _f32(ev.peak_recent_velocity),
    }


def recorded_event_dict(m: Msg) -> dict:
    e = m.msg
    return {
        "stamp_ns": int(m.stamp_ns),
        "track_id": int(e.track_id),
        "level": int(e.alert_level),
        "confidence": _f32(e.confidence),
        "x": _f32(e.location.x),
        "y": _f32(e.location.y),
        "extent_m": _f32(e.horizontal_extent_m),
        "elongation": _f32(min(float(e.elongation_ratio), ELONGATION_CLAMP)),
        "stillness_s": _f32(e.stillness_duration_s),
        "peak_v": _f32(e.preceding_velocity_mps),
    }


def _golden(bag: Bag, source: str, flat: dict[str, object], end_s: float, end_ns: int, beam_count: int,
            skipped: int, hist: dict, events: list[dict], settle_s: float) -> dict:
    stamps = [m.stamp_ns for m in bag.scans]
    in_window = [s for s in stamps if s <= end_ns]
    _, gaps = compute_gaps(stamps)
    dg_s, _ = death_gap_t_end(stamps)
    warm_start, warmup_occupied = warm_flags(bag)
    return {
        "bag": bag.path.name,
        "source": source,
        "code_rev": code_rev(),
        "config_sha256": config_sha256(flat) if flat else "",
        "config": dict(flat),
        "scan_count": len(in_window),
        "beam_count": beam_count,
        "skipped_scans": skipped,
        "first_stamp_ns": bag.t0_ns,
        "last_stamp_ns": in_window[-1] if in_window else bag.t0_ns,
        "end_s": end_s,
        "gaps": gaps,
        "death_gap_t_end_s": dg_s,
        "warm_start": warm_start,
        "warmup_occupied": warmup_occupied,
        "tracks_per_scan_ratio": tracks_per_scan_ratio(bag, settle_s, end_ns),
        "track_range_hist": hist,
        "events": events,
    }


def load_golden(path: Path | str) -> dict:
    path = Path(path)

    def reject(token: str) -> None:
        raise ValueError(f"{path}: non-finite value {token!r} in golden JSON (inf/nan are not allowed)")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def write_golden(golden: dict, path: Path | str) -> None:
    text = json.dumps(golden, indent=1, allow_nan=False)
    Path(path).write_text(text + "\n", encoding="utf-8")


# =============================================================================== replay / extract


@dataclasses.dataclass
class ReplayResult:
    golden: dict
    scan_tracks: list[tuple[int, list[Track]]]        # (stamp_ns, tracks) for every processed post-warmup scan
    scan_events: list[tuple[int, list[Event]]]
    spawns: list[dict]
    spawn_log: list[object]                            # tracker.spawn_log records when the tracker has them (step 5+)
    skipped: int


class _SpawnClassifier:
    """Outside-the-tracker spawn classification from before/after snapshots of `tracker.tracks`."""

    def __init__(self, gate_m: float) -> None:
        self.gate_m = gate_m
        self.evicted: dict[int, tuple[np.ndarray, float, int]] = {}   # id -> (centroid, stamp_s, scan_ordinal)
        self.spawns: list[dict] = []

    @staticmethod
    def snapshot(tracks: list[Track]) -> dict[int, tuple[np.ndarray, int, float]]:
        return {t.track_id: (np.array(t.centroid, dtype=float), int(t.missed_scans), float(t.age_s)) for t in tracks}

    def observe(self, before: dict, after_tracks: list[Track], stamp_ns: int, stamp_s: float, ordinal: int) -> None:
        after = {t.track_id: t for t in after_tracks}
        matched: set[int] = set()
        for tid, t in after.items():
            if tid not in before:
                continue
            centroid0, missed0, age0 = before[tid]
            if t.age_s > age0 or (missed0 > 0 and t.missed_scans == 0) or not np.array_equal(centroid0, np.asarray(t.centroid, dtype=float)):
                matched.add(tid)
        for tid in before:
            if tid not in after:
                self.evicted[tid] = (before[tid][0], stamp_s, ordinal)
        self.evicted = {k: v for k, v in self.evicted.items() if stamp_s - v[1] <= EVICTED_MEMORY_S}

        for tid, t in after.items():
            if tid in before:
                continue
            c = np.asarray(t.centroid, dtype=float)
            live = sorted(
                ((float(np.linalg.norm(c - before[o][0])), o) for o in before), key=lambda p: (p[0], p[1])
            )
            live_matched = [p for p in live if p[1] in matched]
            live_unmatched = [p for p in live if p[1] not in matched]
            ev = sorted(
                ((float(np.linalg.norm(c - v[0])), o, v[2]) for o, v in self.evicted.items()), key=lambda p: (p[0], p[1])
            )
            if not live:
                path = "no-candidate"
            elif live[0][0] > self.gate_m:
                path = "gate-fail"
            elif live[0][1] in matched:
                path = "split-like"
            else:
                path = "unmatched-in-gate"   # unreachable on the legacy tracker; a speed-gate rejection in pass 2
            self.spawns.append({
                "track_id": int(tid),
                "stamp_ns": int(stamp_ns),
                "t_s": None,   # filled by caller (relative)
                "x": float(c[0]),
                "y": float(c[1]),
                "path": path,
                "nearest_live_id": live[0][1] if live else None,
                "nearest_live_m": live[0][0] if live else None,
                "nearest_live_matched": (live[0][1] in matched) if live else None,
                "nearest_matched_id": live_matched[0][1] if live_matched else None,
                "nearest_matched_m": live_matched[0][0] if live_matched else None,
                "nearest_unmatched_id": live_unmatched[0][1] if live_unmatched else None,
                "nearest_unmatched_m": live_unmatched[0][0] if live_unmatched else None,
                "nearest_evicted_id": ev[0][1] if ev else None,
                "nearest_evicted_m": ev[0][0] if ev else None,
                "scans_since_evicted_seen": (ordinal - ev[0][2]) if ev else None,
            })


def replay_bag(
    bag: Bag,
    config: DetectorConfig,
    flat: dict[str, object],
    end_s: float | None = None,
    spawn_diagnostics: bool = False,
    settle_s: float = DEFAULT_SETTLE_S,
) -> ReplayResult:
    """Feed every `/scan` up to `end_s` through a fresh `DetectorCore`; return the golden and per-scan state."""
    end_s, end_ns = resolve_end(bag, end_s)
    core = DetectorCore(config)
    beam_count = len(bag.scans[0].msg.ranges)
    skipped = 0
    hist = empty_hist()
    events: list[dict] = []
    scan_tracks: list[tuple[int, list[Track]]] = []
    scan_events: list[tuple[int, list[Event]]] = []
    classifier = _SpawnClassifier(config.tracker.association_gate_m) if spawn_diagnostics else None
    spawn_log: list[object] = []
    ordinal = 0
    for m in bag.scans:
        if m.stamp_ns > end_ns:
            continue
        ranges = np.asarray(m.msg.ranges, dtype=np.float32)
        if len(ranges) != beam_count:
            skipped += 1
            continue
        ordinal += 1
        stamp_s = header_s(m.msg)
        before = classifier.snapshot(core.tracker.tracks) if classifier is not None else None
        result = core.process(ranges, float(m.msg.angle_min), float(m.msg.angle_increment), stamp_s)
        if result is None:
            continue
        if classifier is not None:
            classifier.observe(before, result.tracks, m.stamp_ns, stamp_s, ordinal)
            if hasattr(core.tracker, "spawn_log"):
                spawn_log.extend((m.stamp_ns, rec) for rec in core.tracker.spawn_log)
        # Track objects are mutated in place by the tracker on later scans: keep a snapshot.
        scan_tracks.append((m.stamp_ns, [copy.deepcopy(t) for t in result.tracks]))
        scan_events.append((m.stamp_ns, list(result.events)))
        hist_add_scan(hist, (_range(t.centroid[0], t.centroid[1]) for t in result.tracks))
        events.extend(event_dict(m.stamp_ns, ev) for ev in result.events)
    spawns = classifier.spawns if classifier is not None else []
    for s in spawns:
        s["t_s"] = (s["stamp_ns"] - bag.t0_ns) / 1e9
    golden = _golden(bag, "replay", flat, end_s, end_ns, beam_count, skipped, hist, events, settle_s)
    return ReplayResult(golden, scan_tracks, scan_events, spawns, spawn_log, skipped)


def extract_bag(bag: Bag, end_s: float | None = None, settle_s: float = DEFAULT_SETTLE_S) -> dict:
    end_s, end_ns = resolve_end(bag, end_s)
    beam_count = len(bag.scans[0].msg.ranges)
    skipped = sum(1 for m in bag.scans if m.stamp_ns <= end_ns and len(m.msg.ranges) != beam_count)
    events = [recorded_event_dict(m) for m in bag.events if m.stamp_ns <= end_ns]
    hist = recorded_track_hist(bag, end_ns)
    return _golden(bag, "recorded", {}, end_s, end_ns, beam_count, skipped, hist, events, settle_s)


def format_events(events: list[dict], t0_ns: int) -> str:
    # fall_timeline.py:29-30 line format, keyed on the header stamp relative to the first scan.
    lines = ["EVENTS (t_s, level, conf, track, x, y, extent_m, elong, still_s, peak_v)"]
    for e in events:
        lines.append("  %6.1f  L%d  %.2f  #%d  (%.2f,%.2f)  ext=%.2f  el=%.1f  still=%.1f  v=%.2f" % (
            (e["stamp_ns"] - t0_ns) / 1e9, e["level"], e["confidence"], e["track_id"], e["x"], e["y"],
            e["extent_m"], e["elongation"], e["stillness_s"], e["peak_v"]))
    return "\n".join(lines)


def format_hist(hist: dict, title: str) -> str:
    lines = [f"{title} (band: total / max_per_scan)"]
    for band, v in hist.items():
        lines.append(f"  {band:>10}: {v['total']} / {v['max_per_scan']}")
    return "\n".join(lines)


def format_spawns(spawns: list[dict], spawn_log: list[object]) -> str:
    lines = ["SPAWN DIAGNOSTICS (outside classification: snapshots of tracker.tracks before/after each process)"]
    lines.append("  t_s | id | path | (x, y) | nearest live id/m/matched | nearest matched id/m | nearest unmatched id/m | nearest evicted id/m/scans_since")
    for s in spawns:
        lines.append(
            "  %6.1f | #%d | %s | (%.3f, %.3f) | %s/%s/%s | %s/%s | %s/%s | %s/%s/%s" % (
                s["t_s"], s["track_id"], s["path"], s["x"], s["y"],
                s["nearest_live_id"], _fmt(s["nearest_live_m"]), s["nearest_live_matched"],
                s["nearest_matched_id"], _fmt(s["nearest_matched_m"]),
                s["nearest_unmatched_id"], _fmt(s["nearest_unmatched_m"]),
                s["nearest_evicted_id"], _fmt(s["nearest_evicted_m"]), s["scans_since_evicted_seen"]))
    lines.append(f"  totals: {dict(Counter(s['path'] for s in spawns))}")
    if spawn_log:
        lines.append("TRACKER spawn_log (SpawnRecord per spawn; cross-check against the outside classification above)")
        for stamp_ns, rec in spawn_log:
            lines.append(f"  stamp_ns={stamp_ns} {rec}")
    else:
        lines.append("  tracker has no spawn_log attribute (step-2 tracker): outside classification only")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.3f}"


# =============================================================================== per-second table


def per_second_table(bag: Bag) -> list[dict]:
    """fall_timeline.py:22-35: per second, the largest non-near (range > 0.4 m) recorded track."""
    t0 = bag.t0_ns
    per: dict[int, dict] = {}
    for m in bag.tracks:
        s = int((m.stamp_ns - t0) // 10**9)
        d = per.setdefault(s, {"second": s, "n": 0, "near": 0, "best_id": None, "extent_m": None,
                               "elongation": None, "range_m": None, "age_s": None})
        cand = [k for k in m.msg.tracks if _range(k.centroid.x, k.centroid.y) > NEAR_RANGE_M]
        d["n"] += len(cand)
        d["near"] += len(m.msg.tracks) - len(cand)
        for k in cand:
            if d["extent_m"] is None or k.horizontal_extent_m > d["extent_m"]:
                d.update(best_id=int(k.track_id), extent_m=float(k.horizontal_extent_m),
                         elongation=float(k.elongation_ratio), range_m=_range(k.centroid.x, k.centroid.y),
                         age_s=float(k.age_s))
    return [per[s] for s in sorted(per)]


def per_second_from_replay(result: ReplayResult, t0_ns: int) -> list[dict]:
    per: dict[int, dict] = {}
    for stamp_ns, tracks in result.scan_tracks:
        s = int((stamp_ns - t0_ns) // 10**9)
        d = per.setdefault(s, {"second": s, "n": 0, "near": 0, "best_id": None, "extent_m": None,
                               "elongation": None, "range_m": None, "age_s": None})
        cand = [k for k in tracks if _range(k.centroid[0], k.centroid[1]) > NEAR_RANGE_M]
        d["n"] += len(cand)
        d["near"] += len(tracks) - len(cand)
        for k in cand:
            if d["extent_m"] is None or k.major_axis_m > d["extent_m"]:
                d.update(best_id=int(k.track_id), extent_m=float(k.major_axis_m), elongation=float(k.elongation),
                         range_m=_range(k.centroid[0], k.centroid[1]), age_s=float(k.age_s))
    return [per[s] for s in sorted(per)]


def format_per_second(rows: list[dict], title: str) -> str:
    lines = [f"PER-SECOND {title} (largest non-near track): t | extent m | elong | range m | id | near-sensor tracks/s"]
    for d in rows:
        if d["best_id"] is None:
            lines.append("  %4d | --- empty --- | near=%d" % (d["second"], d["near"]))
        else:
            lines.append("  %4d | %.2f | %5.1f | %.2f | #%d | near=%d" % (
                d["second"], d["extent_m"], d["elongation"], d["range_m"], d["best_id"], d["near"]))
    return "\n".join(lines)


# =============================================================================== diff


PRECONDITION_KEYS = ("scan_count", "first_stamp_ns", "last_stamp_ns")
COMPARED_KEYS = ("events", "track_range_hist")
EVENT_INTS = ("stamp_ns", "track_id", "level")
EVENT_FLOATS = ("confidence", "x", "y", "extent_m", "elongation", "stillness_s", "peak_v")


def bijection_bar(n_rec: int, missed: int, extra: int) -> bool:
    """Section-1 OBSERVE pass bar: missed <= max(1, ceil(0.1 N)) and extra <= max(2, ceil(0.1 N))."""
    allowance = math.ceil(0.10 * n_rec)
    return missed <= max(1, allowance) and extra <= max(2, allowance)


def _event_key(e: dict) -> str:
    return f"stamp_ns={e['stamp_ns']} track {e['track_id']} L{e['level']}"


def _side_by_side(a: dict, b: dict) -> list[str]:
    lines = ["UNCOMPARED KEYS (printed only)"]
    for key in sorted(set(a) | set(b)):
        if key in COMPARED_KEYS:
            continue
        va, vb = a.get(key), b.get(key)
        if key == "config":
            va, vb = f"{len(va or {})} keys", f"{len(vb or {})} keys"
        flag = "" if va == vb else "   <- differs"
        lines.append(f"  {key:>22}: {va!r:>24} | {vb!r}{flag}")
    return lines


def _strict_diff(a: dict, b: dict) -> tuple[int, list[str]]:
    lines = ["STRICT: events (count, order, ints exact, floats isclose rel 1e-6 abs 1e-4) and track_range_hist"]
    mismatches: list[str] = []
    ea, eb = a["events"], b["events"]
    if len(ea) != len(eb):
        mismatches.append(f"event count {len(ea)} != {len(eb)}")
    for i, (x, y) in enumerate(zip(ea, eb)):
        for key in EVENT_INTS:
            if x[key] != y[key]:
                mismatches.append(f"event[{i}] {key}: {x[key]} != {y[key]} ({_event_key(x)} | {_event_key(y)})")
        for key in EVENT_FLOATS:
            if not _isclose(x[key], y[key]):
                mismatches.append(f"event[{i}] {key}: {x[key]} != {y[key]} ({_event_key(x)})")
    if a["track_range_hist"] != b["track_range_hist"]:
        mismatches.append(f"track_range_hist differs: {a['track_range_hist']} != {b['track_range_hist']}")
    lines.append(f"  events: {len(ea)} | {len(eb)}; mismatches: {len(mismatches)}")
    for m in mismatches[:3]:
        lines.append(f"  first mismatches: {m}")
    lines.append("RESULT: " + ("PASS (exit 0)" if not mismatches else "FAIL (exit 1)"))
    return (0 if not mismatches else 1), lines


def align_observe(rec: list[dict], rep: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Greedy in time order: each recorded OBSERVE to an unmatched replayed OBSERVE within 0.15 s and 0.10 m."""
    rec = sorted(rec, key=lambda e: (e["stamp_ns"], e["track_id"]))
    rep = sorted(rep, key=lambda e: (e["stamp_ns"], e["track_id"]))
    used = [False] * len(rep)
    pairs: list[tuple[dict, dict]] = []
    missed: list[dict] = []
    for r in rec:
        best = None
        for j, p in enumerate(rep):
            if used[j]:
                continue
            dt = abs(p["stamp_ns"] - r["stamp_ns"]) / 1e9
            if dt > ALIGN_DT_S:
                continue
            dist = math.hypot(p["x"] - r["x"], p["y"] - r["y"])
            if dist > ALIGN_DIST_M:
                continue
            score = (dt, dist)
            if best is None or score < best[0]:
                best = (score, j)
        if best is None:
            missed.append(r)
        else:
            used[best[1]] = True
            pairs.append((r, rep[best[1]]))
    extra = [p for j, p in enumerate(rep) if not used[j]]
    return pairs, missed, extra


def _bijection_diff(a: dict, b: dict, settle_s: float, end_s: float | None) -> tuple[int, list[str]]:
    t0 = a["first_stamp_ns"]
    end_s = a["end_s"] if end_s is None else end_s
    start_ns, end_ns = t0 + int(round(settle_s * 1e9)), t0 + int(round(end_s * 1e9))
    lines = [f"BIJECTION: window [t0 + {settle_s} s, t0 + {end_s} s] on events only (track_range_hist printed, not compared)"]
    rec = [e for e in a["events"] if start_ns <= e["stamp_ns"] <= end_ns]
    rep = [e for e in b["events"] if start_ns <= e["stamp_ns"] <= end_ns]
    warn_a = Counter((e["stamp_ns"], 2) for e in rec if e["level"] == 2)
    warn_b = Counter((e["stamp_ns"], 2) for e in rep if e["level"] == 2)
    hard = warn_a == warn_b
    n_warn = sum(warn_a.values())
    lines.append(f"  HARD WARN multiset on (stamp_ns, level=2): recorded {n_warn}, replayed {sum(warn_b.values())}: "
                 + ("EQUAL" + (" (vacuous: both 0)" if n_warn == 0 and not warn_b else "") if hard else "DIFFERS"))
    if not hard:
        only_a = sorted((warn_a - warn_b).elements())[:3]
        only_b = sorted((warn_b - warn_a).elements())[:3]
        lines.append(f"    WARN only recorded: {only_a}; only replayed: {only_b}")
    pairs, missed, extra = align_observe([e for e in rec if e["level"] == 1], [e for e in rep if e["level"] == 1])
    n_rec = len(pairs) + len(missed)
    ok = bijection_bar(n_rec, len(missed), len(extra))
    id_map: dict[int, int] = {}
    for r, p in pairs:
        id_map.setdefault(r["track_id"], p["track_id"])
    lines.append(f"  OBSERVE: N_rec={n_rec} matched={len(pairs)} missed={len(missed)} extra={len(extra)} "
                 f"bar: missed <= {max(1, math.ceil(0.1 * n_rec))}, extra <= {max(2, math.ceil(0.1 * n_rec))} -> "
                 + ("PASS" if ok else "FAIL"))
    lines.append(f"  id map (recorded -> replayed, first co-occurrence): {id_map}")
    for e in missed[:3]:
        lines.append(f"  first missed (recorded, unmatched): {_event_key(e)} t={(e['stamp_ns'] - t0) / 1e9:.1f} s ({e['x']:.2f}, {e['y']:.2f})")
    for e in extra[:3]:
        lines.append(f"  first extra (replayed, unmatched): {_event_key(e)} t={(e['stamp_ns'] - t0) / 1e9:.1f} s ({e['x']:.2f}, {e['y']:.2f})")
    passed = hard and ok
    lines.append(json.dumps({"N_rec": n_rec, "matched": len(pairs), "missed": len(missed), "extra": len(extra),
                             "warn_equal": hard, "pass": passed}))
    lines.append("RESULT: " + ("PASS (exit 0)" if passed else "FAIL (exit 1)"))
    return (0 if passed else 1), lines


def diff_goldens(
    a: dict, b: dict, strict: bool = True, settle_s: float = DEFAULT_SETTLE_S,
    end_s: float | None = None, id_mode: str = "bijection",
) -> tuple[int, str]:
    """Exit 0 pass / 1 event mismatch / 2 same-bag precondition failed."""
    lines = [f"DIFF {a.get('source')} ({a.get('bag')}) | {b.get('source')} ({b.get('bag')})"]
    for key in PRECONDITION_KEYS:
        if a.get(key) != b.get(key):
            lines.append(f"PRECONDITION FAILED: {key} {a.get(key)!r} != {b.get(key)!r} (not the same bag/window) -> exit 2")
            return 2, "\n".join(lines)
    lines.extend(_side_by_side(a, b))
    lines.append(format_hist(a["track_range_hist"], "track_range_hist A"))
    lines.append(format_hist(b["track_range_hist"], "track_range_hist B"))
    if strict:
        code, more = _strict_diff(a, b)
    else:
        if id_mode != "bijection":
            raise ValueError(f"unknown --id-mode {id_mode!r}")
        code, more = _bijection_diff(a, b, settle_s, end_s)
    lines.extend(more)
    return code, "\n".join(lines)


# =============================================================================== divergence


def pair_tracks(rec_tracks: list, rep_tracks: list[Track], gate_m: float) -> tuple[list[tuple[object, Track]], int]:
    """Greedy nearest centroid within the association gate; recorded tracks taken in order of decreasing
    horizontal_extent_m (ties by id). Neither side carries a point count, so extent is the size proxy."""
    order = sorted(rec_tracks, key=lambda t: (-float(t.horizontal_extent_m), int(t.track_id)))
    free = list(rep_tracks)
    pairs: list[tuple[object, Track]] = []
    unpaired = 0
    for r in order:
        best = None
        for j, p in enumerate(free):
            d = math.hypot(float(r.centroid.x) - float(p.centroid[0]), float(r.centroid.y) - float(p.centroid[1]))
            if d <= gate_m and (best is None or d < best[0]):
                best = (d, j)
        if best is None:
            unpaired += 1
        else:
            pairs.append((r, free.pop(best[1])))
    # Callers pair only when the counts are equal, so unpaired recorded == leftover replayed.
    return pairs, max(unpaired, len(free))


def _track_mismatch(r: object, p: Track) -> str | None:
    if math.hypot(float(r.centroid.x) - float(p.centroid[0]), float(r.centroid.y) - float(p.centroid[1])) > DIV_CENTROID_M:
        return "centroid"
    if abs(float(r.horizontal_extent_m) - float(p.major_axis_m)) > DIV_EXTENT_M:
        return "extent"
    er, ep = float(r.elongation_ratio), float(p.elongation)
    if math.isfinite(er) != math.isfinite(ep):
        return "elongation"
    if math.isfinite(er) and not math.isclose(er, ep, rel_tol=DIV_ELONG_REL):
        return "elongation"
    if abs(float(r.age_s) - float(p.age_s)) > DIV_AGE_S:
        return "age"
    if bool(r.is_still) != bool(p.stillness_s > 0.0):
        return "is_still"
    return None


def _in_band(extent: float, elongation: float, fall: FallConfig) -> bool:
    if abs(extent - fall.major_axis_m) <= BAND_EXTENT_M:
        return True
    return math.isfinite(elongation) and abs(elongation - fall.elongation_ratio) <= BAND_ELONG_REL * fall.elongation_ratio


def divergence_report(
    bag: Bag, config: DetectorConfig, flat: dict[str, object],
    settle_s: float = DEFAULT_SETTLE_S, end_s: float | None = None,
) -> dict:
    result = replay_bag(bag, config, flat, end_s=end_s, settle_s=settle_s)
    t0 = bag.t0_ns
    start_ns = t0 + int(round(settle_s * 1e9))
    rec_tracks = {m.stamp_ns: m.msg for m in bag.tracks}
    rec_levels: dict[tuple[int, int], int] = {}
    rec_warned_at: dict[int, int] = {}
    for m in sorted(bag.events, key=lambda m: m.stamp_ns):
        key = (m.stamp_ns, int(m.msg.track_id))
        rec_levels[key] = max(rec_levels.get(key, 0), int(m.msg.alert_level))
        if int(m.msg.alert_level) >= 2:
            rec_warned_at.setdefault(int(m.msg.track_id), m.stamp_ns)
    rep_warned_at: dict[int, int] = {}
    fall = config.fall
    gate = config.tracker.association_gate_m

    counts = {"same_tracks_diff_events": 0, "boundary_band_diff_events": 0, "warn_level_diff": 0}
    examples: dict[str, list[dict]] = {k: [] for k in counts}
    first_divergent: dict | None = None
    first_divergent_any: dict | None = None
    agreement_start: int | None = None
    first_agreement_s: float | None = None
    compared = divergent = missing_recorded = 0

    def decision(level: int, tid: int, warned_at: dict[int, int], stamp_ns: int) -> str:
        if level:
            return f"L{level}"
        return "ALERTED" if tid in warned_at and warned_at[tid] < stamp_ns else "NONE"

    for stamp_ns, tracks in result.scan_tracks:
        in_window = stamp_ns >= start_ns
        rec = rec_tracks.get(stamp_ns)
        rep_events = {ev.track_id: int(ev.level) for _s, evs in result.scan_events if _s == stamp_ns for ev in evs}
        for tid, lvl in rep_events.items():
            if lvl >= 2:
                rep_warned_at.setdefault(tid, stamp_ns)
        if rec is None:
            missing_recorded += 1
            continue
        cause = None
        detail = ""
        pairs: list[tuple[object, Track]] = []
        if len(rec.tracks) != len(tracks):
            cause, detail = "tracks-count", f"recorded {len(rec.tracks)} vs replayed {len(tracks)}"
        else:
            pairs, unpaired = pair_tracks(rec.tracks, tracks, gate)
            if unpaired:
                cause, detail = "tracks-count", f"{unpaired} track(s) without a partner within {gate} m"
            else:
                for r, p in pairs:
                    field = _track_mismatch(r, p)
                    if field is not None:
                        cause = field
                        detail = (f"recorded #{r.track_id} ({r.centroid.x:.3f}, {r.centroid.y:.3f}) ext={r.horizontal_extent_m:.3f} "
                                  f"el={r.elongation_ratio:.3f} age={r.age_s:.2f} still={r.is_still} vs replayed #{p.track_id} "
                                  f"({p.centroid[0]:.3f}, {p.centroid[1]:.3f}) ext={p.major_axis_m:.3f} el={p.elongation:.3f} "
                                  f"age={p.age_s:.2f} still={p.stillness_s > 0.0}")
                        break
        if cause is not None:
            record = {"stamp_ns": stamp_ns, "t_s": (stamp_ns - t0) / 1e9, "cause": cause, "detail": detail}
            if first_divergent_any is None:
                first_divergent_any = record
            if in_window:
                divergent += 1
                if first_divergent is None:
                    first_divergent = record
            agreement_start = None
            continue
        if agreement_start is None:
            agreement_start = stamp_ns
        if first_agreement_s is None and (stamp_ns - agreement_start) / 1e9 >= AGREEMENT_S:
            first_agreement_s = (agreement_start - t0) / 1e9
        if not in_window:
            continue
        compared += 1
        for r, p in pairs:
            lvl_rec = rec_levels.get((stamp_ns, int(r.track_id)), 0)
            lvl_rep = rep_events.get(p.track_id, 0)
            d_rec = decision(lvl_rec, int(r.track_id), rec_warned_at, stamp_ns)
            d_rep = decision(lvl_rep, p.track_id, rep_warned_at, stamp_ns)
            if d_rec == d_rep:
                continue
            if _in_band(float(r.horizontal_extent_m), float(r.elongation_ratio), fall) or _in_band(float(p.major_axis_m), float(p.elongation), fall):
                cls = "boundary_band_diff_events"
            elif d_rec != "NONE" and d_rep != "NONE":
                cls = "warn_level_diff"
            else:
                cls = "same_tracks_diff_events"
            counts[cls] += 1
            if len(examples[cls]) < 3:
                examples[cls].append({
                    "stamp_ns": stamp_ns, "t_s": (stamp_ns - t0) / 1e9,
                    "recorded": {"id": int(r.track_id), "extent_m": float(r.horizontal_extent_m),
                                 "elongation": float(r.elongation_ratio), "decision": d_rec},
                    "replayed": {"id": int(p.track_id), "extent_m": float(p.major_axis_m),
                                 "elongation": float(p.elongation), "decision": d_rep},
                })
    return {
        "bag": bag.path.name,
        "settle_s": settle_s,
        "end_s": result.golden["end_s"],
        "compared_scans": compared,
        "divergent_scans": divergent,
        "missing_recorded_tracks_msgs": missing_recorded,
        "first_divergent": first_divergent,
        "first_divergent_any": first_divergent_any,
        "first_agreement_s": first_agreement_s,
        **counts,
        "examples": examples,
    }


def format_divergence(rep: dict) -> str:
    lines = [f"DIVERGENCE {rep['bag']} window [t0 + {rep['settle_s']} s, t0 + {rep['end_s']} s]"]
    lines.append(f"  compared scans: {rep['compared_scans']}, divergent scans: {rep['divergent_scans']}, "
                 f"scans without a recorded /tracks message: {rep['missing_recorded_tracks_msgs']}")
    fd = rep["first_divergent"]
    lines.append("  first divergent scan (in window): " + ("none" if fd is None else
                 f"t={fd['t_s']:.1f} s stamp_ns={fd['stamp_ns']} cause={fd['cause']}: {fd['detail']}"))
    fa = rep["first_divergent_any"]
    lines.append("  first divergent scan (any, incl. settle): " + ("none" if fa is None else
                 f"t={fa['t_s']:.1f} s cause={fa['cause']}: {fa['detail']}"))
    lines.append(f"  first_agreement_s (track sets agree for {AGREEMENT_S} s): {rep['first_agreement_s']}")
    for cls in ("same_tracks_diff_events", "boundary_band_diff_events", "warn_level_diff"):
        note = " (must be 0; > 0 blocks steps 4-9)" if cls == "same_tracks_diff_events" else " (informational)"
        lines.append(f"  {cls}: {rep[cls]}{note}")
        for ex in rep["examples"][cls]:
            r, p = ex["recorded"], ex["replayed"]
            lines.append(f"    t={ex['t_s']:.1f} s recorded #{r['id']} ext={r['extent_m']:.3f} el={r['elongation']:.3f} {r['decision']} "
                         f"| replayed #{p['id']} ext={p['extent_m']:.3f} el={p['elongation']:.3f} {p['decision']}")
    return "\n".join(lines)


# =============================================================================== schemas / transitions


def schemas_report(path: Path | str) -> dict:
    from mcap.reader import make_reader

    schemas: dict[str, tuple[str, int]] = {}
    channels: list[tuple[str, str]] = []
    for file in mcap_files(path):
        with open(file, "rb") as fh:
            summary = make_reader(fh).get_summary()
            if summary is None:
                continue
            for s in summary.schemas.values():
                schemas[s.name] = (s.encoding, len(s.data))
            for c in summary.channels.values():
                if (c.topic, c.message_encoding) not in channels:
                    channels.append((c.topic, c.message_encoding))
    return {"schemas": schemas, "channels": channels}


def transitions_report(bag: Bag) -> tuple[list[dict], dict]:
    """Per new recorded id: was the previous largest non-near id still alive, distance from its last centroid,
    scans since it was last seen, and split_like (within 0.5 m of an id matched in this scan).
    "matched" on the wire = present in the previous message with age_s increased or centroid changed
    (tracker.py:111 adds dt to age_s only on a match)."""
    scan_index = {m.stamp_ns: i for i, m in enumerate(bag.scans)}
    last_seen: dict[int, tuple[int, float, float, float]] = {}      # id -> (scan index, x, y, extent)
    prev: dict[int, tuple[float, float, float]] = {}                # id -> (x, y, age_s) in the previous message
    seen: set[int] = set()
    last_nonnear: tuple[int, int] | None = None                     # (scan index, largest non-near id)
    rows: list[dict] = []
    for ordinal, m in enumerate(bag.tracks):
        s = scan_index.get(m.stamp_ns, ordinal)
        cur = {int(t.track_id): t for t in m.msg.tracks}
        matched = {
            tid for tid, t in cur.items()
            if tid in prev and (float(t.age_s) > prev[tid][2] or (float(t.centroid.x), float(t.centroid.y)) != prev[tid][:2])
        }
        for tid, t in cur.items():
            if tid in seen:
                continue
            x, y = float(t.centroid.x), float(t.centroid.y)
            row = {"new_id": tid, "scan_index": s, "stamp_ns": m.stamp_ns, "t_s": (m.stamp_ns - bag.t0_ns) / 1e9,
                   "x": x, "y": y, "range_m": _range(x, y), "extent_m": float(t.horizontal_extent_m),
                   "prev_id": None, "old_alive": None, "distance_m": None, "scans_since": None,
                   "split_like": any(math.hypot(x - float(cur[o].centroid.x), y - float(cur[o].centroid.y)) <= 0.5
                                     for o in matched if o != tid)}
            if last_nonnear is not None:
                _, pid = last_nonnear
                ps, px, py, _ = last_seen[pid]
                row.update(prev_id=pid, old_alive=pid in cur, distance_m=math.hypot(x - px, y - py), scans_since=s - ps)
            rows.append(row)
        seen.update(cur)
        for tid, t in cur.items():
            last_seen[tid] = (s, float(t.centroid.x), float(t.centroid.y), float(t.horizontal_extent_m))
        nonnear = [t for t in cur.values() if _range(t.centroid.x, t.centroid.y) > NEAR_RANGE_M]
        if nonnear:
            best = max(nonnear, key=lambda t: (float(t.horizontal_extent_m), -int(t.track_id)))
            last_nonnear = (s, int(best.track_id))
        prev = {tid: (float(t.centroid.x), float(t.centroid.y), float(t.age_s)) for tid, t in cur.items()}
    totals = {
        "new_ids": len(rows),
        "old_alive": sum(1 for r in rows if r["old_alive"] is True),
        "split_like": sum(1 for r in rows if r["split_like"]),
        "with_prev": sum(1 for r in rows if r["prev_id"] is not None),
    }
    return rows, totals


def format_transitions(rows: list[dict], totals: dict) -> str:
    lines = ["TRANSITIONS (recorded /tracks): t_s | new id | (x, y) range | prev largest non-near id | old_alive | distance m | scans_since | split_like"]
    for r in rows:
        lines.append("  %6.1f | #%d | (%.2f, %.2f) r=%.2f | %s | %s | %s | %s | %s" % (
            r["t_s"], r["new_id"], r["x"], r["y"], r["range_m"], r["prev_id"], r["old_alive"],
            _fmt(r["distance_m"]), r["scans_since"], r["split_like"]))
    lines.append(f"  totals: {totals}")
    return "\n".join(lines)


# =============================================================================== labels (R5)


LABEL_KINDS = {"lying", "empty", "walking"}


def mechanism(e: dict) -> str:
    r = _range(e["x"], e["y"])
    if r < 0.3:
        return "near<0.3"
    if r < 0.4:
        return "band 0.3-0.4"
    if e["elongation"] >= ELONGATION_CLAMP:
        return "degenerate"
    return "other"


def validate_labels(labels: dict, death_gap_t_end_s: float, settle_s: float = DEFAULT_SETTLE_S) -> list[dict]:
    segments = labels.get("segments")
    if not isinstance(segments, list):
        raise ValueError("labels: 'segments' must be a list")
    for seg in segments:
        if seg.get("kind") not in LABEL_KINDS:
            raise ValueError(f"labels: segment kind {seg.get('kind')!r} not in {sorted(LABEL_KINDS)}")
        if not (isinstance(seg.get("t0"), (int, float)) and isinstance(seg.get("t1"), (int, float)) and seg["t0"] < seg["t1"]):
            raise ValueError(f"labels: segment {seg!r} needs numeric t0 < t1")
        if seg["kind"] == "empty":
            if seg["t0"] < settle_s:
                raise ValueError(f"labels: empty segment starts at {seg['t0']} < settle {settle_s:.1f} (must start >= 7.0)")
            if seg["t1"] > death_gap_t_end_s + 1e-9:
                raise ValueError(f"labels: empty segment ends at {seg['t1']} > death_gap_t_end_s {death_gap_t_end_s}")
    if not any(seg["kind"] == "empty" for seg in segments) and labels.get("no_empty_segment") is not True:
        raise ValueError("labels: no empty segment; the file must carry \"no_empty_segment\": true and the reason")
    return segments


def compare_labels(events: list[dict], labels: dict, t0_ns: int, death_gap_t_end_s: float,
                   settle_s: float = DEFAULT_SETTLE_S) -> dict:
    segments = validate_labels(labels, death_gap_t_end_s, settle_s)
    out_segments: list[dict] = []
    for seg in segments:
        inseg = [e for e in events if seg["t0"] <= (e["stamp_ns"] - t0_ns) / 1e9 < seg["t1"]]
        counts = {"L1": 0, "L2": 0}
        for e in inseg:
            counts[f"L{e['level']}"] = counts.get(f"L{e['level']}", 0) + 1
        row = {"kind": seg["kind"], "t0": seg["t0"], "t1": seg["t1"], "note": seg.get("note", ""), "counts": counts,
               "n_events": len(inseg)}
        if seg["kind"] == "empty":
            mech = Counter(mechanism(e) for e in inseg)
            row["mechanisms"] = {k: mech[k] for k in MECHANISMS if mech[k]}
            row["events"] = [{"t_s": (e["stamp_ns"] - t0_ns) / 1e9, "level": e["level"], "track_id": e["track_id"],
                              "range_m": _range(e["x"], e["y"]), "extent_m": e["extent_m"], "elongation": e["elongation"],
                              "mechanism": mechanism(e)} for e in inseg]
            row["r5_hard"] = "PASS" if sum(v for k, v in counts.items() if int(k[1:]) >= 2) == 0 else "FAIL"
            row["r5_soft"] = "PASS" if not inseg else "FAIL"
        out_segments.append(row)
    empties = [s for s in out_segments if s["kind"] == "empty"]
    if not empties:
        r5 = r5_soft = "N/A"
    else:
        r5 = "PASS" if all(s["r5_hard"] == "PASS" for s in empties) else "FAIL"
        r5_soft = "PASS" if all(s["r5_soft"] == "PASS" for s in empties) else "FAIL"
    return {"segments": out_segments, "no_empty_segment": not empties, "r5": r5, "r5_soft": r5_soft}


def format_compare_labels(result: dict) -> str:
    lines = ["LABELS (per segment, half-open [t0, t1) on header-stamp-relative seconds)"]
    for s in result["segments"]:
        lines.append(f"  {s['kind']:>8} [{s['t0']}, {s['t1']}): {s['counts']}")
        if s["kind"] == "empty":
            lines.append(f"           mechanisms: {s['mechanisms']}  R5 HARD (0 events level >= 2): {s['r5_hard']}  "
                         f"R5 SOFT (0 events any level): {s['r5_soft']}")
            for e in s["events"][:50]:
                lines.append("           t=%5.1f L%d #%d range=%.3f ext=%.3f el=%.1f -> %s" % (
                    e["t_s"], e["level"], e["track_id"], e["range_m"], e["extent_m"], e["elongation"], e["mechanism"]))
    if result["no_empty_segment"]:
        lines.append("  no empty segment in the labels file")
    lines.append(f"R5: {result['r5']} (HARD tier; SOFT tier: {result['r5_soft']})")
    return "\n".join(lines)


def compare_labels_file(bag_path: Path | str, labels_path: Path | str, params: Path | str = Y_PATH,
                        legacy: bool = False, sets: Sequence[str] = (), settle_s: float = DEFAULT_SETTLE_S,
                        end_s: float | None = None, reader: str = "mcap") -> dict:
    bag = load_bag(bag_path, reader)
    config, flat = load_config(params, legacy, sets)
    result = replay_bag(bag, config, flat, end_s=end_s, settle_s=settle_s)
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    return compare_labels(result.golden["events"], labels, bag.t0_ns, result.golden["death_gap_t_end_s"], settle_s)


# =============================================================================== CLI


def _add_bag_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("bag", help="bag directory (rosbag2 layout, *.mcap inside) or a single .mcap file")
    p.add_argument("--reader", choices=("mcap", "rosbag2"), default="mcap")
    p.add_argument("--settle-s", type=float, default=DEFAULT_SETTLE_S, help="evaluation window start (default 7.0)")
    p.add_argument("--end-s", type=float, default=None, help="header-stamp-relative end (default: death_gap_t_end_s)")


def _add_config_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--params", default=str(Y_PATH), help=f"fall_detector yaml (default {Y_PATH})")
    p.add_argument("--legacy", action="store_true", help="keep only the keys present in params/2026-09-25-live.yaml")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a dotted key (applied last)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay_detector.py", description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("replay", help="run DetectorCore over the bag's /scan; print events; --json writes the golden")
    _add_bag_options(p)
    _add_config_options(p)
    p.add_argument("--json", help="write the golden JSON (Appendix C) here")
    p.add_argument("--spawn-diagnostics", action="store_true")
    p.add_argument("--compare-labels", metavar="LABELS_JSON")
    p.add_argument("--per-second", action="store_true")
    p.add_argument("--track-range-hist", action="store_true")

    p = sub.add_parser("extract", help="recorded /fall_events -> the same golden JSON (source: recorded)")
    _add_bag_options(p)
    p.add_argument("--json")
    p.add_argument("--per-second", action="store_true")
    p.add_argument("--track-range-hist", action="store_true")

    p = sub.add_parser("diff", help="compare two goldens: exit 0 pass, 1 mismatch, 2 not the same bag")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--settle-s", type=float, default=DEFAULT_SETTLE_S)
    p.add_argument("--end-s", type=float, default=None)
    p.add_argument("--id-mode", choices=("bijection",), default="bijection")

    p = sub.add_parser("divergence", help="per-scan replayed vs recorded /tracks; the three decision-diff counts")
    _add_bag_options(p)
    _add_config_options(p)

    p = sub.add_parser("sanity", help="bag facts: counts, gaps, death_gap_t_end_s, warm flags, near hist")
    _add_bag_options(p)

    p = sub.add_parser("schemas", help="mcap schemas and channels")
    p.add_argument("bag")

    p = sub.add_parser("transitions", help="recorded /tracks id transitions")
    _add_bag_options(p)
    p.add_argument("--json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    global LAST_COMPARE_LABELS
    args = build_parser().parse_args(argv)
    verb = args.verb

    if verb == "diff":
        a, b = load_golden(args.a), load_golden(args.b)
        code, text = diff_goldens(a, b, strict=args.strict, settle_s=args.settle_s, end_s=args.end_s, id_mode=args.id_mode)
        print(text)
        return code

    if verb == "schemas":
        report = schemas_report(args.bag)
        print(f"SCHEMAS {Path(args.bag).name}")
        for name, (encoding, length) in report["schemas"].items():
            print(f"  {name}: ({encoding!r}, {length})")
        print("CHANNELS")
        for topic, encoding in report["channels"]:
            print(f"  {topic}: {encoding}")
        return 0

    bag = load_bag(args.bag, args.reader)
    end_s, _ = resolve_end(bag, args.end_s)
    print(f"BAG {bag.path.name}: {len(bag.scans)} /scan, {len(bag.tracks)} /tracks, {len(bag.events)} /fall_events; "
          f"t0 stamp_ns={bag.t0_ns}; --end-s {end_s} ({'given' if args.end_s is not None else 'default = death_gap_t_end_s'}); "
          f"--settle-s {args.settle_s}")

    if verb == "sanity":
        print(format_sanity(sanity_report(bag, args.settle_s)))
        return 0

    if verb == "transitions":
        rows, totals = transitions_report(bag)
        print(format_transitions(rows, totals))
        if args.json:
            Path(args.json).write_text(json.dumps({"bag": bag.path.name, "rows": rows, "totals": totals}, indent=1,
                                                  allow_nan=False) + "\n", encoding="utf-8")
        return 0

    if verb == "extract":
        golden = extract_bag(bag, args.end_s, args.settle_s)
        print(f"EXTRACT source=recorded code_rev={golden['code_rev']} scan_count={golden['scan_count']} "
              f"skipped_scans={golden['skipped_scans']} warm_start={golden['warm_start']} warmup_occupied={golden['warmup_occupied']}")
        print(format_events(golden["events"], bag.t0_ns))
        if args.track_range_hist:
            print(format_hist(golden["track_range_hist"], "track_range_hist (recorded /tracks)"))
        if args.per_second:
            print(format_per_second(per_second_table(bag), "recorded /tracks"))
        if args.json:
            write_golden(golden, args.json)
            print(f"wrote {args.json}")
        return 0

    config, flat = load_config(args.params, args.legacy, args.set)
    if verb == "divergence":
        print(format_divergence(divergence_report(bag, config, flat, args.settle_s, args.end_s)))
        return 0

    # replay
    result = replay_bag(bag, config, flat, end_s=args.end_s, spawn_diagnostics=args.spawn_diagnostics, settle_s=args.settle_s)
    golden = result.golden
    print(f"REPLAY params={args.params} legacy={args.legacy} set={args.set} config_sha256={golden['config_sha256'][:12]} "
          f"code_rev={golden['code_rev']} scan_count={golden['scan_count']} skipped_scans={golden['skipped_scans']} "
          f"beam_count={golden['beam_count']} warm_start={golden['warm_start']} warmup_occupied={golden['warmup_occupied']} "
          f"death_gap_t_end_s={golden['death_gap_t_end_s']}")
    print(format_events(golden["events"], bag.t0_ns))
    levels = Counter(e["level"] for e in golden["events"])
    print(f"  totals: {dict(sorted(levels.items()))}")
    if args.track_range_hist:
        print(format_hist(golden["track_range_hist"], "track_range_hist (replayed tracks)"))
    if args.per_second:
        print(format_per_second(per_second_from_replay(result, bag.t0_ns), "replayed tracks"))
        if bag.tracks:
            print(format_per_second(per_second_table(bag), "recorded /tracks"))
    if args.spawn_diagnostics:
        print(format_spawns(result.spawns, result.spawn_log))
    if args.compare_labels:
        labels = json.loads(Path(args.compare_labels).read_text(encoding="utf-8"))
        LAST_COMPARE_LABELS = compare_labels(golden["events"], labels, bag.t0_ns, golden["death_gap_t_end_s"], args.settle_s)
        print(format_compare_labels(LAST_COMPARE_LABELS))
    if args.json:
        write_golden(golden, args.json)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
