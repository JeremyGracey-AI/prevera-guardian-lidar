"""ROS-free fall detector core: the per-scan pipeline the node and the replay harness share.

Pipeline per scan (`DetectorCore.process`):
    ranges
      -> background warm-up (returns None until `background.warmup_scans` scans are seen)
      -> foreground mask (background subtraction), then update with the mask so a still
         person is held as foreground instead of being absorbed into the rolling median
      -> points (foreground, finite, within [min_range_m, max_range_m])
      -> clusters (DBSCAN + PCA shape features)
      -> tracks (centroid association, velocity history)
      -> events (geometric heuristic below)

The geometric heuristic that fires a WARN-level event:
  * cluster is elongated (major/minor axis ratio high),
  * AND major axis length is human-scaled (>= `fall.major_axis_m`),
  * AND the track has a recent velocity spike followed by stillness,
  * OR the track has been flat and still for `fall.sustained_down_s`.

A degenerate cluster (minor axis ~ 0, elongation `inf`) counts as horizontal without the
extent check unless `fall.degenerate_requires_extent` is set. A track emits OBSERVE on every
scan while it looks horizontal and at most one WARN (`_already_alerted`) -- the legacy latch,
which silences a person who stays down. With `fall.hold_incident` the highest level reached is
held per track and re-emitted every horizontal scan (with the confidence it was reached at);
the incident ends after `fall.incident_clear_s` without a horizontal scan or when the track is
dropped.

Every float field of `Event` is a Python `float` (track centroids are float32 arrays) and
`elongation` is clamped to 1e6 so an event serializes with `json.dumps(..., allow_nan=False)`.
The node publishes these as FallEvent (up to WARN); a confirmed ALERT requires the V-JEPA
verification stage, which is proprietary and not in this repository (interface stub:
`vjepa_bridge.py`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from .background import Background, BackgroundConfig
from .clustering import ClusterConfig, cluster_points
from .tracker import Track, Tracker, TrackerConfig


class AlertLevel(IntEnum):
    """Mirrors the constants in src/prevera_msgs/msg/FallEvent.msg."""

    NONE = 0
    OBSERVE = 1
    WARN = 2
    ALERT = 3
    CRITICAL = 4


ALERT_NAMES = {
    AlertLevel.NONE: "NONE",
    AlertLevel.OBSERVE: "OBSERVE",
    AlertLevel.WARN: "WARN",
    AlertLevel.ALERT: "ALERT",
    AlertLevel.CRITICAL: "CRITICAL",
}


@dataclass(frozen=True)
class FallConfig:
    elongation_ratio: float
    major_axis_m: float
    velocity_spike_mps: float
    sustained_down_s: float
    spike_stillness_s: float = 0.5              # stillness required after a spike (legacy literal)
    degenerate_requires_extent: bool = False    # False = legacy: inf elongation is horizontal as-is
    hold_incident: bool = False                 # False = legacy latch: one WARN per track, then silence
    incident_clear_s: float = 2.0               # hold only: not-horizontal time that ends an incident


@dataclass(frozen=True)
class DetectorConfig:
    min_range_m: float
    max_range_m: float
    background: BackgroundConfig
    cluster: ClusterConfig
    tracker: TrackerConfig
    fall: FallConfig


@dataclass(frozen=True)
class Event:
    track_id: int
    level: AlertLevel
    confidence: float
    x: float
    y: float
    major_axis_m: float
    elongation: float
    stillness_s: float
    peak_recent_velocity: float


@dataclass(frozen=True)
class ScanResult:
    tracks: list[Track]
    events: list[Event]


def scan_to_points(
    ranges: np.ndarray,
    angle_min: float,
    angle_increment: float,
    foreground: np.ndarray,
    min_range_m: float,
    max_range_m: float,
) -> np.ndarray:
    """Foreground returns within range limits as Nx2 float32 (x, y) points."""
    valid = (
        foreground
        & np.isfinite(ranges)
        & (ranges >= min_range_m)
        & (ranges <= max_range_m)
    )
    if not np.any(valid):
        return np.empty((0, 2), dtype=np.float32)

    indices = np.nonzero(valid)[0]
    angles = angle_min + indices * angle_increment
    r = ranges[indices]
    xs = r * np.cos(angles)
    ys = r * np.sin(angles)
    return np.stack([xs, ys], axis=1).astype(np.float32)


def looks_horizontal(track: Track, fall: FallConfig) -> bool:
    if not math.isfinite(track.elongation):
        # degenerate (minor ~ 0) -> very flat
        return (not fall.degenerate_requires_extent) or track.major_axis_m >= fall.major_axis_m
    return (
        track.elongation >= fall.elongation_ratio
        and track.major_axis_m >= fall.major_axis_m
    )


def evaluate(track: Track, fall: FallConfig) -> tuple[AlertLevel, float]:
    if not looks_horizontal(track, fall):
        return AlertLevel.NONE, 0.0

    if track.peak_recent_velocity >= fall.velocity_spike_mps and track.stillness_s > fall.spike_stillness_s:
        confidence = min(1.0, 0.5 + 0.1 * track.stillness_s)
        return AlertLevel.WARN, confidence

    if track.stillness_s >= fall.sustained_down_s:
        return AlertLevel.WARN, 0.6

    return AlertLevel.OBSERVE, 0.3


def _event_from_track(track: Track, level: AlertLevel, confidence: float) -> Event:
    return Event(
        track_id=int(track.track_id),
        level=level,
        confidence=float(confidence),
        x=float(track.centroid[0]),
        y=float(track.centroid[1]),
        major_axis_m=float(track.major_axis_m),
        elongation=float(min(track.elongation, 1e6)),
        stillness_s=float(track.stillness_s),
        peak_recent_velocity=float(track.peak_recent_velocity),
    )


class DetectorCore:
    """Background + clusters + tracker + fall heuristic, driven one scan at a time."""

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config
        self._background = Background(config.background)
        self._tracker = Tracker(config.tracker)
        self._already_alerted: set[int] = set()
        # hold_incident: track_id -> [held level, its confidence, last horizontal stamp_s]
        self._incidents: dict[int, list] = {}

    @property
    def config(self) -> DetectorConfig:
        return self._config

    @property
    def tracker(self) -> Tracker:
        return self._tracker

    def process(
        self,
        ranges: np.ndarray,
        angle_min: float,
        angle_increment: float,
        stamp_s: float,
    ) -> ScanResult | None:
        """Consume one scan. Returns None while the background is warming up."""
        if not self._background.ready:
            self._background.update(ranges)
            return None

        # Mask first, then update with it, so a still person is held as foreground
        # instead of being absorbed into the rolling median (see background.py).
        foreground = self._background.foreground_mask(ranges)
        self._background.update(ranges, foreground=foreground)
        points = scan_to_points(
            ranges, angle_min, angle_increment, foreground,
            self._config.min_range_m, self._config.max_range_m,
        )
        clusters = cluster_points(points, self._config.cluster)
        tracks = self._tracker.update(clusters, stamp_s)
        return ScanResult(tracks=tracks, events=self._emit_fall_events(tracks, stamp_s))

    def _emit_fall_events(self, tracks: list[Track], stamp_s: float) -> list[Event]:
        if self._config.fall.hold_incident:
            return self._emit_held_events(tracks, stamp_s)
        events: list[Event] = []
        for track in tracks:
            if track.track_id in self._already_alerted:
                continue
            level, confidence = evaluate(track, self._config.fall)
            if level == AlertLevel.NONE:
                continue
            events.append(_event_from_track(track, level, confidence))
            if level >= AlertLevel.WARN:
                self._already_alerted.add(track.track_id)
        return events

    def _emit_held_events(self, tracks: list[Track], stamp_s: float) -> list[Event]:
        live = {track.track_id for track in tracks}
        for track_id in [t for t in self._incidents if t not in live]:
            del self._incidents[track_id]

        events: list[Event] = []
        for track in tracks:
            level, confidence = evaluate(track, self._config.fall)
            incident = self._incidents.get(track.track_id)
            if level == AlertLevel.NONE:
                if incident is not None and stamp_s - incident[2] >= self._config.fall.incident_clear_s:
                    del self._incidents[track.track_id]
                continue
            if incident is None:
                incident = self._incidents[track.track_id] = [level, confidence, stamp_s]
            elif level > incident[0] or (level == incident[0] and confidence > incident[1]):
                incident[0], incident[1] = level, confidence
            incident[2] = stamp_s
            events.append(_event_from_track(track, incident[0], incident[1]))
        return events
