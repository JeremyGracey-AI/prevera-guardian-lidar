# 2026-09-27 — floor-mount LIDAR: level, orientation, and the six-station grid walk

Rig: RPLIDAR C1 **on the tile** at the counter base, at the start of the centre tape (scan plane ≈ 2 cm);
arrow on the housing points at the desk. Brio 100 flush against the counter base beside it. C920 on the counter
corner (unchanged). Photos: `docs/hardware/photos/2026-09-27-*`.

## Setup checks

| Check | Result |
|---|---|
| Level | Milwaukee gauge on the C1 top: **0.0°** (one axis on the unit; the other axis read on the floor beside it) |
| `/scan` | 41–47 msgs / 5 s idle; 33 / 5 s with both cameras up (load 2.1) — watch |
| Memory | Other GPU services on the Jetson stopped: 5.0–5.6 GB available |
| Driver dropout 14:02 | USB-UART lead disturbed while positioning; replug re-enumerated to `ttyUSB1`; driver needed a restart (it holds the old fd) |

## Orientation (settled from two stands on opposite sides)

```
                 N (desk)  = −x     ROS bearing 180°
                    ↑
  W (couch) = −y  ←   →  +y = E (fridge)
                    ↓
                 S (counter, C1) = +x
```

Right-handed. The housing arrow points along −x (sllidar reports 180° from the arrow).

## Grid walk — bag `grid-stations-1` (131.6 s, 1.6 GB, `/opt/nvme/bags/`)

Jeremy faced the cameras (south) at every station. Positions are the mean non-clutter track centroid over the still
window. His labels: lanes named 1 / 2 / 3 m across the room, rows near / far.

| # | Jeremy's label | Bag time | x | y | range | Lane / row |
|---|---|---|---|---|---|---|
| 1 | 2 m, centre | 12–31 s | −1.44 | −0.05 | 1.44 | centre, near row |
| 2 | 1 m, toward the glass door | 36–45 s | −1.48 | −0.99 | 1.78 | west (−y), near row |
| 3 | 1 m, up toward the black chair | 50–60 s | −2.58 | −1.02 | 2.77 | west, far row |
| 4 | 2 m | 65–81 s | −2.64 | 0.00 | 2.64 | centre, far row |
| 5 | 3 m | 87–97 s | −2.64 | +0.93 | 2.80 | east (+y), far row |
| 6 | the X | 103–114 s | −2.01 | −0.06 | 2.01 | centre, X |

- Lanes measure **0.94–1.02 m** apart (tape is 1 m): ✓. Rows: near ≈ 1.45 m, X ≈ 2.0 m, far ≈ 2.6 m from the C1.
  The handoff's "X ≈ 2.5 m" was last night's origin; use these ranges from now on.
- **Continuous tracking at every station, zero dropouts, zero fall events.**
- At the near row each shoe is its own track (≈ 20 track rows/s); from the far row on the two shoes merge into
  one (≈ 10/s). Standing and walking at 2 cm is a feet problem, not a torso problem.
- Static clutter tracks persist (not absorbed): Brio/counter edge at 5 cm, furniture feet at (−2.75, −2.09),
  (−3.94, +1.78), (−4.81, +1.37); elongated (6–9) and still — the same signature as a lying person.
  Zero events so far, but this is the false-alarm risk for the fall trials.
- `track_sampler.py` picks the *largest* track, so at 2 cm it prefers a 23 cm table leg over two 13–18 cm shoes.
  Use the bag, not the sampler, for floor-mount analysis.

## Floor trials — bag `floor-trials-1` (537 s, 6.4 GB, `/opt/nvme/bags/`)

Detector restarted on an empty room at 14:58 (the furniture-foot clutter tracks disappeared; only the 6 cm
Brio/counter-edge track remains). Six lie-downs (Jeremy's order; F was an added head-toward-sensor case), then a
walking baseline over the grid stations. Body pose from the C920/Brio frames at mid-segment.

| Seg | Bag time | Pose (camera) | Track: x, y · extent · elongation | `/fall_events` |
|---|---|---|---|---|
| A | 28–63 s | across the beam at the X, head east | −1.93, −0.34 · **1.64 m** · 10 | 350, all level 1, from 28.9 s (onset) to 63.8 s |
| B | 94–127 s | **along the beam, feet toward the C1** (soles at 0.9 m) | −0.91, −0.25 · **0.33 m** · 7 | **none — missed** |
| C | 157–191 s | across, far row (2.6 m), head west | −2.61, +0.11 · **1.62 m** · 9 | 97, 157.2–165.3 s (one level 2, conf 0.55), **then silent for 26 s while still down** |
| D | 238–273 s | diagonal, west lane near row | −1.35, −0.86 · **0.99 m** · 10 | 347, all level 1, full duration |
| E | 302–335 s | diagonal, east lane near row | −1.08, +0.69 · **0.92 m** · 20 | 335, all level 1, full duration |
| F | 370–400 s | **along the beam, head toward the C1** (head at 0.83 m) | −0.83, +0.01 · **0.22 m** · 12 | **none — missed** (3 msgs at 402.7 s while getting up) |
| W | 428–522 s | standing/walking over the grid stations | 0.2–0.5 m | **0 — no false alarms** |

Findings:

1. **Geometry, not range, decides detection.** Across or diagonal to the beam, a lying body is a 0.9–1.65 m,
   elongated cluster and fires within a second of going down, at every range tried (1.3–2.6 m). End-on (along the
   beam, either way round) the plane sees only the soles or the head — 0.22–0.33 m — and the body behind is occluded.
   Both end-on trials were missed. A single 2D LIDAR at floor level cannot cover this; the camera can (the Brio frame
   of B is two soles filling the image; of F, a head and shoulders at 0.8 m).
2. **Nothing escalated.** 1,129 of 1,132 events are level 1 (OBSERVE, conf 0.30). `stillness_duration_s` never
   exceeded 3.4 s although each lie-down was held still for ~30 s: `is_still` toggles every second or two on the
   lying cluster, which resets the stillness clock. This is plan v4's *windowed stillness* step, now with a golden bag.
3. **C went silent after its one level-2 event** while the person stayed down and tracked (track and extent unchanged
   to 191 s). Unexplained; read the event-publication logic before trusting any escalation result.
4. **Zero false alarms** across the 95 s walking baseline and all transitions except the get-up from F (3 msgs,
   person genuinely on the floor).
5. `/scan` held 47/5 s with both cameras streaming after the restart.

## Process lessons (2026-09-27)

1. **Record with `-s mcap`.** `ros2 bag record` defaulted to sqlite3 today; the Mac harness reads mcap only.
   Both bags were converted on the Jetson (`ros2 bag convert`, topics `/scan /tracks /fall_events`) to
   `<bag>-lidar/` mcaps (34 MB and 8 MB); schemas survived intact. The `.db3` originals stay as the camera record.
2. **Start the bag before the detector restart.** `floor-trials-1` began 7 min after the empty-room restart, so the
   live tracker carried hidden state (track ages 413 s, a 7-min background) that a cold replay cannot reproduce:
   `divergence` compared 0 scans. Event-level agreement per segment (1,130 of 1,132 events) was the evidence instead.
   Starting the recorder first, then restarting on the empty room, makes the strict track-level bar reachable.
3. **Split camera and LIDAR storage.** The Mac Studio disk filled (129 MB free) during a 6.9 GB rsync; the partial
   copy kept the final filename. Full bags live on the Jetson NVMe and on the OMEN's backup drive (all 20
   files size-checked against the Jetson); the Mac keeps LIDAR-only mcaps.
4. **`guardian-cams-up.sh` points at the repo checkout**, which lacks the camera tools on the Jetson's branch; it ran
   with `T=~/guardian-tools` substituted. Fix the script or merge `feat/capture-tools` before relying on it.
5. **A driver restart is needed after any USB replug** (`/dev/rplidar` follows the new `ttyUSBn`; the running driver
   keeps the dead fd).
6. Permissions set up today: the Mac's agent session is allowed to SSH to the Jetson; on the Jetson a sudoers
   drop-in allows password-less service control (`systemctl` stop/start/restart/status), `jetson_clocks`,
   `nvpmodel -q` and shutdown/reboot only (verified: plain `sudo -n true` is refused). Other GPU services disabled.

---

## Publication note

Published 2026-09-27 from the private development repository. Host names, LAN addresses, local paths, account
names and references to unpublished planning documents were replaced (for example `<jetson-ip>`); measurements,
tables and findings are unchanged. Commit hashes, branch names and PR numbers refer to the private history and do
not resolve here. Decision labels such as D0 and D1 are defined in [`docs/DECISIONS.md`](../DECISIONS.md). Line
numbers cited into this document from other documents refer to it as published: this note sits at the end so
they hold.

**Erratum (2026-09-27, found in the publication review).** Finding 2's count is wrong as written. A recount of the
recorded `/fall_events` in `floor-trials-1` (`replay_detector.py extract --settle-s 0`) gives 1,132 events: 1,131 at
level 1 and 1 at level 2, which is segment C's WARN at 165.3 s in the table above. Finding 2 is left as recorded.
