"""Fixture bag writer for the replay harness (plan v4 step 3, Appendix B). No ROS.

Writes rosbag2-layout bag directories (`<path>/<name>_0.mcap`) with `mcap_ros2.writer.Writer`.
Schema text = rosbag2_storage_mcap's concatenated `ros2msg` form: the top-level `.msg` text,
then for each dependency a line of 80 `=`, a `MSG: <pkg>/<Type>` line and that dependency's
`.msg` text (`builtin_interfaces/Time` needs no definition). The prevera_msgs definitions are
read from `src/prevera_msgs/msg/` so the fixture cannot drift from the real interface.

Header stamps are integer: `stamp_ns(i) = i * 10**8` plus every injected gap before scan `i`,
`sec, nanosec = divmod(stamp_ns, 10**9)`. The mcap log time is deliberately **not** the header
stamp (`stamp_ns + 5 ms`) so a harness that reads log time fails the stamp tests instead of
passing by accident (plan section 1: never mcap log time).

Two writers:
  * `write_scene_bag(path, overrides=overrides_v3, with_outputs=True, params=L)`: `/scan` from
    `SyntheticScene` (seed 42, 160 scans); with `with_outputs`, `/tracks` and `/fall_events`
    produced by `DetectorCore` itself under `params`, written with the node's float32 fields
    (`fall_detector_node.py` `_track_to_msg` / `_publish_event`). `gaps_after={i: seconds}`
    shifts every scan after index `i`; `beam_counts={i: n}` truncates scan `i` to `n` beams
    (the core skips it, as the harness does).
  * `write_scripted_tracks_bag(path, script)`: `/scan` as above plus `/tracks` messages taken
    verbatim from `script`, a list of `(scan_index, [ {track_id, x, y, extent, elongation,
    age_s, is_still}, ... ])`. The rows are data; the detector never runs for them.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Collection
from pathlib import Path

import numpy as np
from mcap.writer import CompressionType
from mcap_ros2.writer import Writer

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[1]
PACKAGE_SRC = REPO_ROOT / "src" / "prevera_perception"
MSG_DIR = REPO_ROOT / "src" / "prevera_msgs" / "msg"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

import replay_detector  # noqa: E402  (same directory; provides load_config and L_PATH)
from prevera_perception.detector_core import DetectorCore, Event  # noqa: E402
from prevera_perception.synthetic_scene import SyntheticScene, overrides_v3  # noqa: E402
from prevera_perception.tracker import Track  # noqa: E402

SEED = 42
N_SCANS = 160
SCAN_PERIOD_NS = 10**8
LOG_TIME_OFFSET_NS = 5_000_000
FRAME_ID = "laser"
SEP = "=" * 80

HEADER_MSG = "builtin_interfaces/Time stamp\nstring frame_id\n"
POINT_MSG = "float64 x\nfloat64 y\nfloat64 z\n"
VECTOR3_MSG = "float64 x\nfloat64 y\nfloat64 z\n"
LASERSCAN_MSG = (
    "std_msgs/Header header\nfloat32 angle_min\nfloat32 angle_max\nfloat32 angle_increment\n"
    "float32 time_increment\nfloat32 scan_time\nfloat32 range_min\nfloat32 range_max\n"
    "float32[] ranges\nfloat32[] intensities\n"
)


def _dep(name: str, text: str) -> str:
    return f"{SEP}\nMSG: {name}\n{text}"


def _msg_text(name: str) -> str:
    return (MSG_DIR / f"{name}.msg").read_text(encoding="utf-8")


def schema_texts() -> dict[str, str]:
    """`{datatype: concatenated ros2msg text}` for the three fixture schemas."""
    person_track = _msg_text("PersonTrack")
    return {
        "sensor_msgs/msg/LaserScan": LASERSCAN_MSG + _dep("std_msgs/Header", HEADER_MSG),
        "prevera_msgs/msg/FallEvent": (
            _msg_text("FallEvent") + _dep("std_msgs/Header", HEADER_MSG) + _dep("geometry_msgs/Point", POINT_MSG)
        ),
        "prevera_msgs/msg/PersonTrackArray": (
            _msg_text("PersonTrackArray")
            + _dep("prevera_msgs/PersonTrack", person_track)
            + _dep("std_msgs/Header", HEADER_MSG)
            + _dep("geometry_msgs/Point", POINT_MSG)
            + _dep("geometry_msgs/Vector3", VECTOR3_MSG)
        ),
    }


# ----------------------------------------------------------------------------- stamps / messages


def scan_stamps_ns(n_scans: int = N_SCANS, gaps_after: dict[int, float] | None = None) -> list[int]:
    """Header stamps in ns: `i * 10**8` plus every injected gap (`gaps_after[k]` seconds, scans > k)."""
    stamps = []
    offset = 0
    for i in range(n_scans):
        stamps.append(i * SCAN_PERIOD_NS + offset)
        if gaps_after and i in gaps_after:
            offset += int(round(gaps_after[i] * 1e9))
    return stamps


def _header(stamp_ns: int) -> dict:
    sec, nanosec = divmod(stamp_ns, 10**9)
    return {"stamp": {"sec": sec, "nanosec": nanosec}, "frame_id": FRAME_ID}


def _scan_dict(stamp_ns: int, ranges: np.ndarray) -> dict:
    return {
        "header": _header(stamp_ns),
        "angle_min": SyntheticScene.ANGLE_MIN,
        "angle_max": math.pi,
        "angle_increment": SyntheticScene.ANGLE_INCREMENT,
        "time_increment": 0.0,
        "scan_time": 0.1,
        "range_min": 0.05,
        "range_max": SyntheticScene.RANGE_MAX,
        "ranges": ranges.tolist(),
        "intensities": [],
    }


def _track_dict(stamp_ns: int, track: Track) -> dict:
    # fall_detector_node._track_to_msg, field for field.
    return {
        "header": _header(stamp_ns),
        "track_id": int(track.track_id),
        "centroid": {"x": float(track.centroid[0]), "y": float(track.centroid[1]), "z": 0.0},
        "velocity": {"x": float(track.last_velocity[0]), "y": float(track.last_velocity[1]), "z": 0.0},
        "horizontal_extent_m": float(track.major_axis_m),
        "elongation_ratio": float(track.elongation),
        "age_s": float(track.age_s),
        "is_still": bool(track.stillness_s > 0.0),
    }


def _scripted_track_dict(stamp_ns: int, row: dict) -> dict:
    return {
        "header": _header(stamp_ns),
        "track_id": int(row["track_id"]),
        "centroid": {"x": float(row["x"]), "y": float(row["y"]), "z": 0.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "horizontal_extent_m": float(row["extent"]),
        "elongation_ratio": float(row["elongation"]),
        "age_s": float(row["age_s"]),
        "is_still": bool(row["is_still"]),
    }


def _event_dict(stamp_ns: int, ev: Event) -> dict:
    # fall_detector_node._publish_event, field for field.
    return {
        "header": _header(stamp_ns),
        "track_id": int(ev.track_id),
        "alert_level": int(ev.level),
        "confidence": ev.confidence,
        "location": {"x": ev.x, "y": ev.y, "z": 0.0},
        "horizontal_extent_m": ev.major_axis_m,
        "elongation_ratio": float(ev.elongation),
        "stillness_duration_s": ev.stillness_s,
        "preceding_velocity_mps": ev.peak_recent_velocity,
        "vjepa_confidence": float("nan"),
    }


def _scans(
    overrides: Callable[[int], dict[int, float]] | None,
    stamps: list[int],
    beam_counts: dict[int, int] | None,
    seed: int = SEED,
) -> list[tuple[int, np.ndarray]]:
    scene = SyntheticScene(np.random.default_rng(seed))
    out = []
    for i, stamp_ns in enumerate(stamps):
        ranges = scene.build_scan(i * 0.1, overrides(i) if overrides else None)
        if beam_counts and i in beam_counts:
            ranges = ranges[: beam_counts[i]]
        out.append((stamp_ns, ranges))
    return out


class _BagWriter:
    def __init__(self, path: Path) -> None:
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / f"{self.dir.name}_0.mcap"
        self._fh = open(self.file, "wb")
        self._writer = Writer(self._fh, compression=CompressionType.NONE)
        self.schemas = {name: self._writer.register_msgdef(name, text) for name, text in schema_texts().items()}

    def write(self, topic: str, datatype: str, message: dict, stamp_ns: int) -> None:
        log_time = stamp_ns + LOG_TIME_OFFSET_NS
        self._writer.write_message(topic, self.schemas[datatype], message, log_time=log_time, publish_time=log_time)

    def close(self) -> None:
        self._writer.finish()
        self._fh.close()


# ----------------------------------------------------------------------------- public writers


def write_scene_bag(
    path: Path | str,
    overrides: Callable[[int], dict[int, float]] | None = overrides_v3,
    with_outputs: bool = True,
    params: Path | str = replay_detector.L_PATH,
    *,
    gaps_after: dict[int, float] | None = None,
    beam_counts: dict[int, int] | None = None,
    n_scans: int = N_SCANS,
    seed: int = SEED,
) -> Path:
    """Write `/scan` (and, with `with_outputs`, the core's `/tracks` + `/fall_events`) to a bag dir."""
    stamps = scan_stamps_ns(n_scans, gaps_after)
    scans = _scans(overrides, stamps, beam_counts, seed)
    core = None
    if with_outputs:
        config, _ = replay_detector.load_config(params)
        core = DetectorCore(config)
    # The wire carries float32 angles; feed the core what the harness will read back.
    angle_min = float(np.float32(SyntheticScene.ANGLE_MIN))
    angle_increment = float(np.float32(SyntheticScene.ANGLE_INCREMENT))
    beam_count = len(scans[0][1])

    bag = _BagWriter(Path(path))
    try:
        for stamp_ns, ranges in scans:
            bag.write("/scan", "sensor_msgs/msg/LaserScan", _scan_dict(stamp_ns, ranges), stamp_ns)
            if core is None or len(ranges) != beam_count:
                continue
            sec, nanosec = divmod(stamp_ns, 10**9)
            result = core.process(ranges, angle_min, angle_increment, sec + nanosec * 1e-9)
            if result is None:
                continue
            tracks_msg = {"header": _header(stamp_ns), "tracks": [_track_dict(stamp_ns, t) for t in result.tracks]}
            bag.write("/tracks", "prevera_msgs/msg/PersonTrackArray", tracks_msg, stamp_ns)
            for ev in result.events:
                bag.write("/fall_events", "prevera_msgs/msg/FallEvent", _event_dict(stamp_ns, ev), stamp_ns)
    finally:
        bag.close()
    return bag.dir


def write_scripted_tracks_bag(
    path: Path | str,
    script: Collection[tuple[int, list[dict]]],
    overrides: Callable[[int], dict[int, float]] | None = overrides_v3,
    *,
    n_scans: int = N_SCANS,
    seed: int = SEED,
) -> Path:
    """Write `/scan` from the scene plus `/tracks` messages taken verbatim from `script`."""
    stamps = scan_stamps_ns(n_scans)
    scans = _scans(overrides, stamps, None, seed)
    by_index: dict[int, list[dict]] = {}
    for scan_index, rows in script:
        if not 0 <= scan_index < n_scans:
            raise ValueError(f"scripted scan index {scan_index} outside 0..{n_scans - 1}")
        by_index.setdefault(int(scan_index), []).extend(rows)

    bag = _BagWriter(Path(path))
    try:
        for i, (stamp_ns, ranges) in enumerate(scans):
            bag.write("/scan", "sensor_msgs/msg/LaserScan", _scan_dict(stamp_ns, ranges), stamp_ns)
            if i in by_index:
                tracks_msg = {"header": _header(stamp_ns), "tracks": [_scripted_track_dict(stamp_ns, r) for r in by_index[i]]}
                bag.write("/tracks", "prevera_msgs/msg/PersonTrackArray", tracks_msg, stamp_ns)
    finally:
        bag.close()
    return bag.dir
