# bag_analysis: offline replay harness (no ROS)

`replay_detector.py` runs the ROS-free detector core (`src/prevera_perception/prevera_perception/detector_core.py`)
over a recorded rosbag2 mcap bag and compares the result with what the live node published.
Plan: `docs/plans/replay-harness-plan-v4.md` (step 3; definitions in section 1).

```
bag (*.mcap) ──/scan──────────► DetectorCore.process ──► replayed events / tracks ──┐
     │                                                                              ├─► diff / divergence
     ├──/fall_events ──► extract ──► recorded golden JSON ─────────────────────────┘
     └──/tracks ───────► sanity / transitions / per-second / near_track_range_hist
```

## Environment

Python 3.10 with `numpy<2` (the Jetson floor). On the Mac:

```
~/.local/bin/uv pip install --python ~/.venv-prevera310/bin/python -r tools/bag_analysis/requirements.txt
~/.venv-prevera310/bin/python tools/bag_analysis/replay_detector.py --help     # runs without rclpy
```

`--reader mcap` (default) needs only `mcap` + `mcap-ros2-support`; `--reader rosbag2` imports `rosbag2_py`
lazily (WSL fallback when a bag's mcap schemas are empty).

## Verbs

| Verb | What it does | Output |
|---|---|---|
| `replay <bag>` | feed every `/scan` (up to `--end-s`) through a fresh core | events in the `fall_timeline.py` line format; `--json` writes the golden |
| `extract <bag>` | recorded `/fall_events` -> the same golden schema (`source: recorded`) | `--json` |
| `diff a.json b.json` | `--strict`: same events, floats `isclose(rel 1e-6, abs 1e-4)`, `track_range_hist` equal; else section-1 bijection bar on `events` over `[t0+settle, t0+end]` | exit 0 pass / 1 mismatch / 2 not the same bag (`scan_count`, `first_stamp_ns`, `last_stamp_ns` differ) |
| `divergence <bag>` | per scan, replayed tracks vs recorded `/tracks`; decision diffs classified `same_tracks_diff_events` (must be 0) / `boundary_band_diff_events` / `warn_level_diff` | first divergent scan + cause, counts, examples, `first_agreement_s` |
| `sanity <bag>` | scan count, beam-count histogram, `/tracks`-per-`/scan` ratio post-settle, stamp gaps > 1.5x median dt, `death_gap_t_end_s`, `warm_start`, `warmup_occupied`, per-topic counts, `near_track_range_hist` | text |
| `schemas <bag>` | mcap schemas `(encoding, len)` and channels | text |
| `transitions <bag>` | per new recorded id: previous largest non-near id alive?, distance, scans since, `split_like` | table; `--json` |

Options on every bag verb: `--settle-s S` (default 7.0 = warm-up 30 + window 40 scans at 10 Hz) and
`--end-s E` (header-stamp-relative seconds; default = `death_gap_t_end_s`, the last `/scan` before the first
inter-scan gap > 5 s, relative to the first `/scan`).

Config (`replay`, `divergence`): `--params <yaml>` (default the live `fall_detector.yaml`), `--legacy`
(keep only the 20 keys of `params/2026-09-25-live.yaml`, the `36ca257` snapshot), `--set key=value`
(applied last, always honoured; unknown key raises). Loader casts follow the node (`int`/`float`/`bool`).

`replay` extras: `--spawn-diagnostics` (per new track id, classified from outside the tracker:
`no-candidate` / `gate-fail` / `split-like`; prints the tracker's `spawn_log` beside it when present),
`--compare-labels labels.json` (per-segment counts by level; `empty` segments get the mechanism breakdown
`near<0.3` / `band 0.3-0.4` / `degenerate` / `other` and the R5 HARD/SOFT verdict), `--per-second`,
`--track-range-hist` (always written into the golden as `track_range_hist`).

## Time base and floats

Every time is the header stamp `sec + nanosec * 1e-9`, never the mcap log time. Golden JSON stores
`stamp_ns = sec * 10**9 + nanosec` (int) and every float as `float(np.float32(v))` (the wire is float32);
elongation is clamped to `1e6`; files are written with `allow_nan=False` and the loader rejects
`Infinity`/`NaN`.

## Typical run (step 3b, per bag)

```
H=tools/bag_analysis; P=$H/replay_detector.py
python3 $P schemas   $BAG
python3 $P sanity    $BAG                      # note death_gap_t_end_s -> E
python3 $P extract   $BAG --end-s $E --json rec.json
python3 $P replay    $BAG --end-s $E --params $H/params/2026-09-25-live.yaml --json rep.json --track-range-hist
python3 $P diff rec.json rep.json --settle-s 7.0 --end-s $E --id-mode bijection
python3 $P divergence $BAG --end-s $E --params $H/params/2026-09-25-live.yaml
python3 $P transitions $BAG --json transitions.json
```

## Fixtures and tests

`mcap_fixture.py` writes fixture bags with `mcap_ros2` (schema text per plan Appendix B, message
definitions read from `src/prevera_msgs/msg/`): `write_scene_bag` (the synthetic scene, optionally with the
core's own `/tracks` + `/fall_events`) and `write_scripted_tracks_bag` (scripted `/tracks` rows). Tests:
`src/prevera_perception/test/test_replay_harness.py` (skipped without `mcap_ros2`).

Older one-off scripts (`fall_timeline.py`, `scan_sector.py`, `empty_beams.py`) need a sourced ROS workspace.

## Everything else in this directory

Field data (bags, extracted frames, model results JSON) is **not** in this repository. Each script below takes
its input paths as arguments; the defaults point at where the data lives on the author's machine.

| Script | What it does | Needs | Used in |
|---|---|---|---|
| `fall_timeline.py <bag>` | `/fall_events` plus the largest non-near track, per second | sourced ROS workspace | [`2026-09-25` field test](../../docs/field-tests/2026-09-25-rplidar-fall-tests.md) |
| `scan_sector.py <bag> <x> <y> <empty_s> [s...]` | is a person at (x, y) inside the scan plane? compares the beams toward it with the empty room | sourced ROS workspace | 2026-09-25 |
| `empty_beams.py` | arcs of beams with no return (`inf`) in one `LaserScan` from stdin | numpy, pyyaml | 2026-09-25 |
| `bag_timeline.py <bag>` | per-second person-like track and events by level (camera topics skipped) | `rosbag2_py` | [`2026-09-26` capture](../../docs/field-tests/2026-09-26-capture.md) timelines |
| `bag_frames.py <bag> <topic> <out> <s...>` | one JPEG per requested second from a compressed image topic | `rosbag2_py` | the frames in `docs/field-tests/counter-baseline-*/` |
| `score_rfdetr.py` | scores the pre-declared RF-DETR detection evaluation from the raw results; standard library only | results JSON (not published) | [RF-DETR results](../../docs/field-tests/2026-09-27-rfdetr-results.md) |
| `rfdetr_figures.py` | the blind-spot and contact-sheet figures for that evaluation | supervision, matplotlib, mcap, opencv | [`2026-09-27-rfdetr/`](../../docs/field-tests/2026-09-27-rfdetr/) |
| `rfdetr_keypoints.py run/check/score` | runner, schema check and scorer for the pre-declared keypoint check | rfdetr 1.11.0 (run/check); stdlib (score) | [keypoint plan](../../docs/field-tests/2026-09-27-rfdetr-keypoints-plan.md), [status](../../docs/field-tests/2026-09-27-rfdetr-keypoints-status.md) |
| `rfdetr_keypoint_figure.py` | figure-only drawing of the keypoint run (not scored; see the status note) | supervision, pillow | `2026-09-27-rfdetr/keypoints-B-F.jpg` |

The RF-DETR runner used on the Jetson (`rf_eval.py`) is not in this repository; the results doc lists that as a gap.
