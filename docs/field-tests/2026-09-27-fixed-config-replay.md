# Fixed detector config, replayed on floor-trials-1

Offline replay, 2026-09-27. The fixes in [DR-06 to DR-09](../DECISIONS.md#dr-06) sit behind default-off keys and do
not run on the Jetson. This replay switches them on for one question: does the fixed detector reach WARN on the
lie-downs the legacy detector only observed, without raising anything while a person walks or stands?

This is **not** the plan v4 step 9 scoring. Step 9's bars (WARN in every lying segment, 0 WARN in every empty-room
segment) are scored against label files that do not exist yet. The segments below are the camera-timed ones in the
[floor-trials document](2026-09-27-floor-mount-grid.md). No threshold was changed for this run.

## Setup

- **Recording:** `floor-trials-1`, LIDAR topics as mcap, 5,378 scans, 537.2 s (not published).
- **Code:** `detector_core.py`, `tracker.py` and [`replay_detector.py`](../../tools/bag_analysis/replay_detector.py)
  as in this repository. They match the private commit `fc73c11` that produced the numbers, apart from one docstring.
- **Configs:** *legacy* is [`fall_detector.yaml`](../../src/prevera_bringup/config/fall_detector.yaml), the config on
  the Jetson. *Fixed* is the same file with five overrides. *Fixed + hold* adds `fall.hold_incident=true`.

```bash
python tools/bag_analysis/replay_detector.py replay floor-trials-1-lidar_0.mcap \
  --params src/prevera_bringup/config/fall_detector.yaml \
  --set tracker.per_track_dt=true --set tracker.max_association_speed_mps=3.0 \
  --set tracker.still_window_s=1.5 --set tracker.still_displacement_m=0.25 --set min_range_m=0.3 \
  --json fixed.json          # fixed + hold: add --set fall.hold_incident=true
# config_sha256 in the JSON: legacy 2c1716900c01…, fixed c7d5070c0a7a…, fixed + hold e17507afa254…
```

## Result

Times are seconds from the first `/scan` stamp. **Onset** is the first OBSERVE of the segment: the first scan on
which the lying track looks horizontal. It is the same under both configs and lies within a second of the
camera-timed segment start.

| Seg | Pose | Onset | Legacy config | Fixed: first WARN | Rule, at the WARN | Stillness rule alone |
|---|---|---|---|---|---|---|
| A | across, 2.0 m | 28.9 | OBSERVE only | 32.9 (**+4.0 s**) | spike: 1.64 m/s, still 1.60 s | 35.4 (+6.5 s) |
| B | end-on, feet | none | none | none | | |
| C | across, 2.6 m | 157.2 | one WARN at 165.3 (+8.1 s), then silent | 160.5 (**+3.3 s**) | spike: 1.61 m/s, still 3.20 s | 161.4 (+4.2 s) |
| D | diagonal, 1.6 m | 238.0 | OBSERVE only | 238.7 (**+0.7 s**) | spike: 1.23 m/s, still 1.50 s | 241.3 (+3.3 s) |
| E | diagonal, 1.3 m | 302.1 | OBSERVE only | 304.2 (**+2.1 s**) | spike: 0.89 m/s, still 1.50 s | 306.8 (+4.7 s) |
| F | end-on, head | none | none | none | | |
| W | walking, 428–522 s | | 0 WARN | **0 events of any level** | | |

Without the hold, each fixed WARN is followed by silence on that track, the same latch as legacy C; fixed + hold
keeps WARN until the get-up (caveat 6).

`grid-stations-1` (standing at six stations, 131.6 s): 0 events of any level under both configs. Between the
segments of `floor-trials-1` the fixed config raises five OBSERVE and no WARN, all while getting up after C and F.

**Stillness rule alone** is the first scan on which the lying track's windowed stillness reached 4.0 s, read from
the fixed + hold run (the hold keeps the track emitting after its first WARN; stillness does not depend on it). It is
when the sustained rule would have fired had the spike rule not fired first.

**In short:** with the fixed config, the four lie-downs the LIDAR can see reach WARN 0.7 to 4.0 s after onset, and
3.3 to 6.5 s after onset on stillness alone. Walking and standing raise nothing. The legacy config reached WARN in one
of the four, 8.1 s after onset, and then went silent.

## Caveats

1. **The spike rule set the early times, and in three of the four it fired on jitter.** All four WARNs came from
   the spike rule (a speed of at least 0.8 m/s among the track's last 10 matched updates, plus stillness over 0.5 s),
   not the 4 s stillness rule. With windowed stillness, stillness stays 0 until the track has 1.5 s of samples within
   0.25 m of its centroid, so the rule fires on the first qualifying speed once that window has filled.
   - A, C and E: the qualifying speed was a centroid jump of 0.09 to 0.16 m between scans while the person already
     lay still, the jitter described in [DR-07](../DECISIONS.md#dr-07). C's window filled at 158.8 s; its WARN came
     1.7 s later, on such a jump. E's peak (0.89 m/s) barely clears the threshold.
   - D: the 1.23 m/s speed is already on D's first OBSERVE, so it was recorded as the person went down. The WARN fired
     the moment the window filled, 0.7 s after onset.

   The last column is the result that does not depend on these speeds.
2. **This corrects an earlier claim.** The README and [DR-09](../DECISIONS.md#dr-09) said that without spike memory
   only the 4 s sustained rule could fire. The replay shows the spike rule firing once the stillness window has filled,
   on whatever qualifying speed is still among the track's last 10 matched updates. Time-based spike memory (plan v4
   step 8) is meant to tie the rule to the fall's own motion on purpose; this replay is the baseline it has to beat.
3. **Scope.** One subject, one room, one session, lying segments of 30 to 35 s. A replay, not the live node; the
   Jetson still runs the legacy config.
4. **B and F are still missed.** End-on, the person is a 0.33 m or 0.22 m cluster, which never passes the shape
   gate (major axis at least 0.8 m); the stillness fix cannot change that. The cameras cover these
   ([RF-DETR results](2026-09-27-rfdetr-results.md)).
5. **`min_range_m` 0.3 is required.** Without it, the 6 cm track at 0.07 m reaches the stillness rule at 24.0 s
   (21 s still), before the first lie-down ([DR-09](../DECISIONS.md#dr-09)).
6. **The incident hold does not move the first WARN** on any segment; it then holds WARN until the get-up.
7. **Other recordings, replayed the same way** (no labels, so not scored):
   - `fall-test-lowered-064632` (09-25, falls at 3.4 to 4.9 m): legacy 0 WARN, fixed 4 (at 4.4 to 4.9 m), all
     through the spike rule and on four different track ids (the track re-spawns; spot memory, plan v4 step 7, is not built). No event in the
     run shows more than 1.8 s of stillness.
   - `counter-baseline-1` (09-26, vertical scan plane): the false WARN while sitting in a chair stays and comes
     earlier, 114.0 s legacy (spike rule; still 0.50 s, 2.64 m/s) and 107.6 s fixed (stillness rule, 4.29 s).
   - `session-20260926-051900`, whose run the 09-25 notes mark invalid: over the plan's window (157.6 s) the fixed
     config raises nothing; over the whole recording (10,725 scans, about 18 min, with no `/scan` from 157.6 s
     to 694.7 s), legacy 9 WARN and fixed 10, every fixed one after the scans resume. One is a static 5 cm cluster at
     1.17 m that reaches the stillness rule after 116 s. That is the case `fall.degenerate_requires_extent` is for.
   - `fall-test-062816`, `counter-baseline-2`: 0 WARN under both configs.

The per-run JSON outputs are kept with the unpublished recordings.
