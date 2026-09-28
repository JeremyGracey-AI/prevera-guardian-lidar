# Field test: RPLIDAR C1 fall detection — 2026-09-25

> **Publication note.** Published 2026-09-27 from the private development repository. Host names, LAN
> addresses, local paths, account names and references to unpublished planning documents were replaced
> (for example `<jetson-ip>`); measurements, tables and findings are unchanged. Commit hashes, branch names
> and PR numbers refer to the private history and do not resolve here. Decision labels such as D0 and D1
> are defined in [`docs/DECISIONS.md`](../DECISIONS.md).

Setup: RPLIDAR C1 → Jetson Orin Nano Super (`<jetson-hostname>`, `<jetson-ip>`), ROS 2 Humble,
`prevera_bringup/perception.launch.py` from branch `fix/background-absorption` (PR #1).
Tester performed controlled falls onto a mat. Recordings (mcap) are **not** in git — too large:
Jetson `/opt/nvme/bags/`, plus a backup drive on the OMEN workstation.

## Runs

| Bag | Sensor height | Falls | Person visible on floor? | Events | Probable-fall (WARN) |
|---|---|---|---|---|---|
| `session-20260926-051900` | original mount | walk-around, 27 min | — | 4,862 L1 (noise) | — (run invalid: two `sllidar_node` instances fought over `/dev/rplidar`, `/scan` died at ~18 min) |
| `fall-test-062816` | original mount | 2 | **No** — scan toward the fall spot identical to empty room (96 pts, nearest 2.62 m) for 50 s after the fall | 5 × L1, all during the descent | **No** |
| `fall-test-lowered-064632` | ~half the original height | 2 (+ extra movement) | **Yes** — lying body tracked, extent 0.8–1.3 m, elongation 5–20 | 167 × L1 | **No** |

## Findings

1. **Scan-plane height was the blocker (the height risk flagged before the trial, confirmed).** At the original height a person lying on
   the floor adds zero returns. After lowering, the body is visible and passes `_looks_horizontal()` on every scan.
2. **Stillness never accumulates, so WARN can't fire.** Max `stillness_duration_s` in the lowered run was **0.4 s**
   (WARN needs 0.5 s after a spike, or 4.0 s sustained). At 3.4–4.9 m the cluster centroid jitters faster than
   `tracker.still_velocity_mps = 0.15` from one scan to the next, and tracks re-spawn (ids 7→8, 14→20→21), resetting stillness.
3. **Falls were at 3.4–4.9 m**, beyond the 1.5–3 m target. Point density on the body drops with range, which
   worsens (2).
4. **Near-sensor clutter:** ~1 track/scan within 0.4 m of the sensor (mount/housing). Needs `min_range_m ≈ 0.3`.
5. **Tracker speed spikes** (up to 4.6 m/s) are association jumps between different clusters, not real motion.
6. **Background absorption** (fixed in PR #1): without the foreground hold a still person vanishes after ~2 s.

## Next changes (code, in priority order)

1. Stillness from displacement over a window (e.g. centroid moved < 0.25 m over the last 1.5 s) instead of
   per-scan instantaneous speed; keep stillness across short track re-spawns at the same spot.
2. `min_range_m: 0.3`; gate association jumps (reject implied speed > 3 m/s).
3. Re-run with falls at 1.5–3 m, sideways and head-toward-sensor, and record ground-truth timestamps.
4. Decide on sensing: a 3D LIDAR or depth sensor removes the single-plane blind spots (lying below the plane,
   end-on falls). Evaluate after (1)–(3) show what the 2D path can reach.

## Tools

- `tools/bag_analysis/fall_timeline.py <bag>` — events + per-second largest track
- `tools/bag_analysis/scan_sector.py <bag> <x> <y> <empty_s> [s...]` — is a person at (x,y) inside the scan plane?
- `tools/bag_analysis/empty_beams.py` — arcs with no return (inf)
- `jetson/guardian-up.sh` / `guardian-down.sh` — start/stop LIDAR + detector + foxglove_bridge (:8765) + rosbridge (:9090); single-instance guard; `@reboot` via crontab
- `jetson/09-ros2-humble.sh` — ROS 2 Humble base + bridges (root)
Next session: [HANDOFF-2026-09-26.md](HANDOFF-2026-09-26.md)
