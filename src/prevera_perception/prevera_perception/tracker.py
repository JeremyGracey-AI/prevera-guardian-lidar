"""Nearest-centroid tracker for LIDAR clusters.

Associates each incoming cluster to the closest existing track within a
gating radius. Unmatched clusters start new tracks; unmatched tracks
age out. The tracker also maintains a short velocity history so the
fall detector can see "sudden velocity spike → stillness".

Optional (plan v4 step 5; defaults = legacy): `per_track_dt` measures a
track's velocity, age and stillness over the time since that track was last
seen instead of the tracker-global dt, and `max_association_speed_mps`
rejects a candidate whose implied speed is above the limit (the cluster
falls through to the next candidate by distance, else spawns).
`Tracker.spawn_log` records why each new track was spawned in the last
`update()` call (diagnostics only; no published field depends on it).

Optional (plan v4 step 6; default = legacy): `still_window_s > 0` replaces the
per-scan speed threshold with windowed displacement stillness. A matched track
is still when it has samples covering the last `still_window_s` seconds (one
sample straddling the window start is kept) and every one of them lies within
`still_displacement_m` of the current centroid; `stillness_s` then counts from
the oldest retained sample, so the first still scan credits the whole window and
a gap is credited when the track is reacquired at the same spot. Window
boundaries are compared with a 1e-6 s stamp epsilon because core-driven stamps
(`i * 0.1`) and header stamps (`sec + nanosec * 1e-9`) differ by < 1e-15 s.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from itertools import count

import numpy as np

from .clustering import Cluster

# Why a cluster spawned a new track (SpawnRecord.path). "split-like" is not in plan v4 section 1's
# list: it is the legacy greedy-exclusion path (P/tracker.py `exclude=matched`) where the nearest
# live track is within the gate but already claimed by an earlier cluster in the same scan
# (open-gaps #1). The harness's outside classification uses the same name. "tombstone-reuse"
# arrives with spot memory (plan v4 step 7).
SPAWN_PATHS = ("no-candidate", "gate-fail", "speed-gate", "split-like")

STAMP_EPS = 1e-6   # seconds; module constant, not a declared parameter (plan v4 section 1)


@dataclass(frozen=True)
class TrackerConfig:
    association_gate_m: float    # max distance from predicted centroid to match
    max_missed_scans: int        # drop a track after this many consecutive misses
    velocity_window: int         # scans of velocity history to keep
    still_velocity_mps: float    # below this speed a track is considered "still"
    max_association_speed_mps: float = 0.0   # 0 = off (legacy): distance/dt above this rejects a candidate
    per_track_dt: bool = False               # False = legacy: one tracker-global dt for every matched track
    still_window_s: float = 0.0              # 0 = legacy per-scan speed threshold; > 0 = windowed displacement stillness
    still_displacement_m: float = 0.25       # windowed mode: max distance of any window sample from the current centroid


@dataclass
class Track:
    track_id: int
    centroid: np.ndarray
    last_velocity: np.ndarray
    peak_recent_velocity: float
    elongation: float
    major_axis_m: float
    age_s: float
    missed_scans: int
    stillness_s: float
    last_seen_s: float = 0.0     # stamp of the spawn or of the last match
    velocity_history: deque[float] = field(default_factory=deque)
    # (stamp_s, centroid) samples; seeded at spawn, grown only when still_window_s > 0 (legacy keeps
    # the spawn sample alone, so default-config memory per track stays constant).
    position_history: deque[tuple[float, np.ndarray]] = field(default_factory=deque)
    still_since_s: float | None = None   # windowed mode: stamp the current still window opened at


@dataclass(frozen=True, eq=False)   # eq=False: the ndarray field makes value equality ambiguous
class SpawnRecord:
    track_id: int
    path: str                                   # one of SPAWN_PATHS
    cluster_centroid: np.ndarray
    # Nearest over every track alive at the moment of the spawn, matched or not, including tracks
    # spawned earlier in the same update (they are association candidates too); distance to the
    # track's centroid at that moment (after its match, if it was already matched this scan).
    nearest_live_id: int | None
    nearest_live_m: float | None
    nearest_live_was_matched: bool | None       # matched by any cluster of this update (set after the loop)
    nearest_tomb_id: int | None = None          # tombstone fields: None until plan v4 step 7
    nearest_tomb_m: float | None = None
    scans_since_nearest_seen: int | None = None


class Tracker:
    def __init__(self, config: TrackerConfig) -> None:
        self._config = config
        self._tracks: dict[int, Track] = {}
        self._id_source = count(start=1)
        self._last_stamp_s: float | None = None
        self.spawn_log: list[SpawnRecord] = []   # reset at the start of every update(); this call only

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks.values())

    def update(self, clusters: list[Cluster], stamp_s: float) -> list[Track]:
        self.spawn_log = []
        dt = 0.0 if self._last_stamp_s is None else stamp_s - self._last_stamp_s
        self._last_stamp_s = stamp_s

        matched_track_ids = self._associate(clusters, dt, stamp_s)
        # "Matched this scan" includes clusters processed after the spawn; the path itself was
        # decided from the matched set at spawn time.
        self.spawn_log = [
            replace(rec, nearest_live_was_matched=rec.nearest_live_id in matched_track_ids)
            if rec.nearest_live_id is not None else rec
            for rec in self.spawn_log
        ]
        self._age_unmatched_tracks(matched_track_ids)
        self._evict_stale_tracks()
        return self.tracks

    def _track_dt(self, track: Track, dt: float, stamp_s: float) -> float:
        return stamp_s - track.last_seen_s if self._config.per_track_dt else dt

    def _associate(self, clusters: list[Cluster], dt: float, stamp_s: float) -> set[int]:
        gate = self._config.association_gate_m
        max_speed = self._config.max_association_speed_mps
        matched: set[int] = set()
        for cluster in clusters:
            chosen: int | None = None
            speed_rejected = False
            for track_id, distance in self._candidates(cluster.centroid, exclude=matched):
                if distance > gate:
                    break   # sorted by distance: every later candidate is beyond the gate too
                dt_track = self._track_dt(self._tracks[track_id], dt, stamp_s)
                if max_speed <= 0.0 or dt_track <= 0 or distance / dt_track <= max_speed:
                    chosen = track_id
                    break
                speed_rejected = True
            if chosen is None:
                self._spawn_track(cluster, stamp_s, matched, speed_rejected)
                continue
            self._update_track(chosen, cluster, dt, stamp_s)
            matched.add(chosen)
        return matched

    def _candidates(self, centroid: np.ndarray, exclude: set[int]) -> list[tuple[int, float]]:
        # Stable sort on distance only: ties keep dict (spawn) order, which is the element the legacy
        # single-min `min(distances, key=...)` returned, so with the speed gate off the first candidate
        # is exactly the legacy nearest track.
        distances = [
            (tid, float(np.linalg.norm(centroid - t.centroid))) for tid, t in self._tracks.items() if tid not in exclude
        ]
        return sorted(distances, key=lambda pair: pair[1])

    def _spawn_track(self, cluster: Cluster, stamp_s: float, matched: set[int], speed_rejected: bool) -> None:
        live = sorted(
            ((tid, float(np.linalg.norm(cluster.centroid - t.centroid))) for tid, t in self._tracks.items()),
            key=lambda pair: pair[1],
        )
        if not live:
            path = "no-candidate"
        elif speed_rejected:
            path = "speed-gate"       # an unmatched candidate inside the gate failed only the speed check
        elif live[0][1] <= self._config.association_gate_m:
            path = "split-like"       # nearest live track is inside the gate but already matched this scan
        else:
            path = "gate-fail"
        track_id = next(self._id_source)
        self._tracks[track_id] = Track(
            track_id=track_id,
            centroid=cluster.centroid.copy(),
            last_velocity=np.zeros(2),
            peak_recent_velocity=0.0,
            elongation=cluster.elongation,
            major_axis_m=cluster.major_axis_m,
            age_s=0.0,
            missed_scans=0,
            stillness_s=0.0,
            last_seen_s=stamp_s,
            velocity_history=deque(maxlen=self._config.velocity_window),
            position_history=deque([(stamp_s, cluster.centroid.copy())]),   # the spawn is the first sample
            still_since_s=None,
        )
        self.spawn_log.append(SpawnRecord(
            track_id=track_id,
            path=path,
            cluster_centroid=cluster.centroid.copy(),
            nearest_live_id=live[0][0] if live else None,
            nearest_live_m=live[0][1] if live else None,
            nearest_live_was_matched=(live[0][0] in matched) if live else None,
        ))

    def _update_track(self, track_id: int, cluster: Cluster, dt: float, stamp_s: float) -> None:
        track = self._tracks[track_id]
        dt_track = self._track_dt(track, dt, stamp_s)
        velocity = (cluster.centroid - track.centroid) / dt_track if dt_track > 0 else np.zeros(2)
        speed = float(np.linalg.norm(velocity))
        windowed = self._config.still_window_s > 0.0
        if windowed:
            self._update_window_stillness(track, cluster.centroid, stamp_s)   # before the centroid moves

        track.velocity_history.append(speed)
        track.centroid = cluster.centroid.copy()
        track.last_velocity = velocity
        track.peak_recent_velocity = max(track.velocity_history) if track.velocity_history else 0.0
        track.elongation = cluster.elongation
        track.major_axis_m = cluster.major_axis_m
        track.age_s += dt_track
        track.missed_scans = 0
        if not windowed:
            track.stillness_s = track.stillness_s + dt_track if speed < self._config.still_velocity_mps else 0.0
        track.last_seen_s = stamp_s

    def _update_window_stillness(self, track: Track, centroid: np.ndarray, stamp_s: float) -> None:
        window, history = self._config.still_window_s, track.position_history
        history.append((stamp_s, centroid.copy()))
        while len(history) > 1 and history[1][0] <= stamp_s - window + STAMP_EPS:
            history.popleft()   # keep exactly one sample straddling the window start
        covered = (stamp_s - history[0][0]) >= window - STAMP_EPS
        displacement = max(float(np.linalg.norm(c - centroid)) for _, c in history)
        if covered and displacement < self._config.still_displacement_m:
            if track.still_since_s is None:   # `is None`, never `or`: a window opened at stamp 0.0 is valid
                track.still_since_s = history[0][0]
            track.stillness_s = stamp_s - track.still_since_s   # never rounded (published as-is)
        else:
            track.still_since_s = None
            track.stillness_s = 0.0

    def _age_unmatched_tracks(self, matched_track_ids: set[int]) -> None:
        # Legacy quirk kept (plan v4 step 5): a spawned track is not in `matched`, so its spawn scan
        # counts as a miss (missed_scans == 1 right after spawn).
        for tid, track in self._tracks.items():
            if tid in matched_track_ids:
                continue
            track.missed_scans += 1

    def _evict_stale_tracks(self) -> None:
        stale = [tid for tid, t in self._tracks.items() if t.missed_scans > self._config.max_missed_scans]
        for tid in stale:
            del self._tracks[tid]
