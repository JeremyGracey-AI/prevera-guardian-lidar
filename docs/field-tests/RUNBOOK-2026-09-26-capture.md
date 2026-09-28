# Capture runbook — 2026-09-26 (counter baseline + floor trials)

> **Publication note.** Published 2026-09-27 from the private development repository. Host names, LAN
> addresses, local paths, account names and references to unpublished planning documents were replaced
> (for example `<jetson-ip>`); measurements, tables and findings are unchanged. Commit hashes, branch names
> and PR numbers refer to the private history and do not resolve here. Decision labels such as D0 and D1
> are defined in [`docs/DECISIONS.md`](../DECISIONS.md).

> **Status 2026-09-26 22:50:** Phases 0–1 done (`counter-baseline-2` is the counter baseline; `-1` was made with the LIDAR
> on its side). Phases 2–4 (floor trials) are tomorrow's first chunk: see `HANDOFF-2026-09-27.md`, which also
> replaces steps 3 and 7 with `guardian-cams-up.sh` and the sign result (forward = +y, camera-left = +x).

One pass, in order, about 60 minutes. Every `ssh jetson …` line runs in the **OMEN PowerShell**. Two
recordings come out of it: `counter-baseline-1` (LIDAR high and level, camera looking down) and
`floor-trials-1` (LIDAR low, the clean-data protocol). Each is **one bag** holding `/scan`, `/tracks`,
`/fall_events` and the camera (`/camera/image_raw/compressed`, MJPEG straight from the C920, one clock
for everything), plus a typed `labels.txt`.

**Who runs what (as of 17:50):** the Mac Studio reaches the Jetson (`ssh <user>@<jetson-ip>`), so the
Claude session on the Mac runs every `ssh jetson …` line below and says when each physical step is due.
Jeremy does the physical steps, types labels, and runs the one `sudo` line (step 2, done 17:54).

Live view, on the OMEN and on the Mac:
- **Camera in any browser:** `http://<jetson-ip>:8081/` (`jetson/mjpeg_server.py` on the harness
  branch; `/snap` gives one JPEG). Aim the C920 while watching this.
- **Foxglove** (OMEN and Mac), first time:
  1. Foxglove → **Open connection** → **Foxglove WebSocket** → URL `ws://<jetson-ip>:8765` → Open.
  2. Left sidebar → **Layouts** → **⋯** (or the import icon) → **Import from file** → pick
     `foxglove/guardian.json` from the repo. That gives four panels: **3D** (`/scan` in flat green,
     10 m grid, top-down), **Image** (`/camera/image_raw/compressed`), **Raw Messages** on
     `/fall_events`, and a **Plot** of track speed.
  3. If the 3D panel is empty: panel gear → **Frame** → display frame `laser`; **Topics** → `/scan` →
     visible on.
  4. Save any tweak: Layouts → the layout's ⋯ → **Save** (and **Export** back to the repo file if it's
     worth keeping).

  Without the file, by hand: **+ Add panel** → 3D → gear → Topics → `/scan` visible, Color mode
  **Flat**, point size 5; + Add panel → Image → gear → Image topic `/camera/image_raw/compressed`;
  + Add panel → Raw Messages → topic `/fall_events`. Drag panel edges to arrange.

## Positions

| | LIDAR window (floor→) | LIDAR aim | Camera lens (floor→) | Camera pitch | Why |
|---|---|---|---|---|---|
| **A. Counter** | 115.5 cm, inverted | level | 103 cm | **15° down** | Baseline: LIDAR should track a walker and go blind when they lie down; camera keeps them |
| **B. Floor** | 25–35 cm, inverted, hung under the arm (**measure**) | level | ~20–25 cm (**measure**) | **~10° up** | Clean-data trials at the height class that worked on 09-25 |

Camera pitch: phone inclinometer app flat on top of the C920, write the number down. "Level" for the
LIDAR: inclinometer on the flat top of the C1 body.

## Zone (top view; tape on the floor, distances from the point directly under the LIDAR)

```
                    room
   3.0 m  ─────────────●───────────        T5  sideways
   2.5 m  ─────────────X───────────        FALL HERE (Recording A lie-down)
   2.0 m  ─────────────●───────────        T1 T2 sideways · T3 T4 head toward sensor
                 ●  (2.0 m at 45° to the side; optional walk-through point)
   1.5 m  ─────────────────────────        nobody lies closer than this
   ═══════════════╤════════════════        counter edge (position A: sensor hangs over it)
               [LIDAR]                      position B: tripod on the floor directly below
               [ CAM ]
```

"Sideways" = lying across the line of sight (body broadside to the sensor). "Head toward sensor" =
body along the line of sight, head nearest. Lie on a mat, on your side, stay still 15 s, get up, walk
out of view, wait 10 s (the tracker re-arms after ~2 s out of view).

## Phase 0 — Prep (15 min)

1. **Inverted flag** (sensor is upside down; without this left/right are mirrored):
   ```
   ssh jetson "sed -i 's/inverted: false/inverted: true/' ~/prevera-guardian-lidar/src/prevera_bringup/config/rplidar_c1.yaml && grep -n inverted ~/prevera-guardian-lidar/src/prevera_bringup/config/rplidar_c1.yaml"
   ```
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash && cd ~/prevera-guardian-lidar && colcon build --symlink-install --packages-select prevera_bringup 2>&1 | tail -3'
   ```
2. **Camera driver** (root, you; ~1 min):
   ```
   ssh -t jetson 'sudo apt install -y ros-humble-usb-cam'
   ```
3. **Start the camera node**, detached. `pixel_format:=mjpeg2rgb`: the node decodes the C920's MJPEG
   and the compressed transport re-encodes it (measured 17:56: 30.0 Hz, usb_cam at 50% of one core,
   no memory to speak of). **Not `raw_mjpeg`**: on usb_cam 0.8.1 it copies the MJPEG bytes into a
   YUV422 buffer and publishes noise. The node stays up across `guardian-down`/`up` because those
   scripts don't know about it.
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=42; mkdir -p ~/guardian-logs; setsid nohup ros2 run usb_cam usb_cam_node_exe --ros-args -r __ns:=/camera -p video_device:=/dev/video0 -p pixel_format:=mjpeg2rgb -p image_width:=1280 -p image_height:=720 -p framerate:=30.0 -p camera_name:=c920 -p frame_id:=camera > ~/guardian-logs/camera.log 2>&1 < /dev/null & sleep 5; tail -5 ~/guardian-logs/camera.log'
   ```
   Check it publishes (~30 Hz; warnings about `exposure_auto`/`focus_auto` controls are harmless):
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=42; timeout 8 ros2 topic hz /camera/image_raw/compressed 2>&1 | tail -3'
   ```
   **Floor cam** (Brio 100 on `/dev/video2`, added 21:29), same pattern, namespace `/camera_floor`:
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=42; setsid nohup ros2 run usb_cam usb_cam_node_exe --ros-args -r __ns:=/camera_floor -p video_device:=/dev/video2 -p pixel_format:=mjpeg2rgb -p image_width:=1280 -p image_height:=720 -p framerate:=30.0 -p camera_name:=brio100 -p frame_id:=camera_floor > ~/guardian-logs/camera_floor.log 2>&1 < /dev/null & sleep 5; tail -3 ~/guardian-logs/camera_floor.log'
   ```
   Then the browser views, one instance per camera (`mjpeg_server.py [topic] [port]`), in a command
   line of their own (a `pkill` for them must never share a command line with this launch: lesson 8 bit
   again at 17:58):
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=42; setsid nohup python3 ~/guardian-tools/mjpeg_server.py /camera/image_raw/compressed 8081 > ~/guardian-logs/mjpeg.log 2>&1 < /dev/null & setsid nohup python3 ~/guardian-tools/mjpeg_server.py /camera_floor/image_raw/compressed 8082 > ~/guardian-logs/mjpeg_floor.log 2>&1 < /dev/null & sleep 3; ss -ltn | grep -E ":808[12]"'
   ```
   Open `http://<jetson-ip>:8081/` (top cam) and `http://<jetson-ip>:8082/` (floor cam).
4. **Tape the marks**: 1.5, 2.0, 2.5, 3.0 m straight out from under the LIDAR, plus 2.0 m at 45°. Put the
   tripod's floor spot (position B) directly under its counter spot so the same marks serve both.
5. **Restart the LIDAR side with nobody in view**, two commands, then 10 s of empty room:
   ```
   ssh jetson '~/guardian-down.sh'
   ```
   ```
   ssh jetson '~/guardian-up.sh'
   ```
6. **Status**: want driver 1, detector 1, both ports listening, ~50 scans in 5 s.
   ```
   ssh jetson '~/guardian-status.sh'
   ```
7. **Foxglove** (OMEN and Mac) → `ws://<jetson-ip>:8765`. **Framing, position A**: put the angle
   gauge on top of the C920 and set **15.0° down** (it read 27.4° at 21:35, which puts the top of the
   frame below the horizon: no heads at any range). Check in the `:8081` window: the 1.5 m line just
   above the bottom edge, the 3 m line about 40 % up. Floor cam stays **level (0.3°)**.
7b. **Calibration walk** (Claude samples `/tracks` from the Mac while you move; say `go` first):
   walk the **2 m cross line** end to end, back and forth, for 40 s; then **stand on the X for 10 s**.
   From the samples Claude writes down: the sign of `y` when you are on the **camera's left**
   (expected +y with `inverted: true`), the heading of the centre line in the `laser` frame (the
   LIDAR's +x is not camera-forward; the offset is a constant for the URDF), and the measured range of
   the X (expected ≈ 2.5 m). If the sign is wrong we record anyway and fix it in software.

## Phase 1 — Recording A: counter baseline (8 min)

8. Stand behind the sensor, out of view. Start the bag (workspace sourced, domain 42, five topics: the
   LIDAR three plus both cameras):
   ```
   ssh jetson 'source /opt/ros/humble/setup.bash; source ~/prevera-guardian-lidar/install/setup.bash; export ROS_DOMAIN_ID=42; D=/opt/nvme/bags/counter-baseline-1; mkdir -p $D; setsid nohup ros2 bag record -s mcap -o $D/bag /scan /tracks /fall_events /camera/image_raw/compressed /camera_floor/image_raw/compressed > $D/bag.log 2>&1 < /dev/null & sleep 5; tail -7 $D/bag.log'
   ```
   Want: `bag.log` lists all five topics as subscribed. Two 720p30 MJPEG streams write roughly 10–12 MB/s
   together; a 5-minute recording is ~3 GB on the 909 GB NVMe.
9. Second PowerShell window, the label prompt (type a word, Enter, at each phase; Ctrl-C at the end):
   ```
   ssh -t jetson 'while read -p "label> " l; do echo "$(date +%s.%N) $l" | tee -a /opt/nvme/bags/counter-baseline-1/labels.txt; done'
   ```
10. The trial. Type each label as you start the phase:

    | Label | Do |
    |---|---|
    | `empty` | nobody in view, 30 s |
    | `walk-2m` | walk across the zone along the 2.0 m line |
    | `walk-3m` | walk back along the 3.0 m line |
    | `lie-2.5m` | lie down sideways on the X (FALL HERE, ≈ 2.5 m) |
    | `still` | hold still 15 s |
    | `up` | get up |
    | `sit` | sit on a chair at ~2.5 m, 20 s, then stand |
    | `exit` | walk out of view; 20 s empty |

11. Stop the bag (SIGINT so it flushes) and check:
    ```
    ssh jetson 'pkill -INT -f "[r]os2 bag record"; sleep 3; ls -la /opt/nvme/bags/counter-baseline-1 /opt/nvme/bags/counter-baseline-1/bag; wc -l /opt/nvme/bags/counter-baseline-1/labels.txt'
    ```
    Want: `bag/*.mcap` in the hundreds of MB (camera), `labels.txt` 8 lines.

## Phase 2 — Move to position B (10 min)

12. Tripod on the floor directly under its counter spot. LIDAR hung under the arm, **level**, as low as
    the arm allows with nothing (legs, cables, adapter board) inside 30 cm of it in the scan plane.
    Camera on the ball head, pitched ~10° up.
13. **Measure and write down** (tell me; they go in the field-test doc and the URDF): floor→LIDAR window
    (cm), floor→lens (cm), camera pitch (°), LIDAR→camera horizontal offset (cm).
14. Framing in the Foxglove Image panel. Want: the 1.5 m mark in frame, a standing person's torso at
    3 m in frame. Heads cut off inside 2 m is fine.
15. **Restart the LIDAR side with nobody in view** (step 5, both commands), wait 10 s. Moving the sensor
    invalidates the background; skipping this is how yesterday's second bug hid.
16. Foxglove: `/scan` alive, near-sensor clutter small. With the live config still at
    `min_range_m: 0.05` the detector will emit OBSERVE on tripod legs; expected, the harness fixes it
    later; the raw `/scan` is what matters.

## Phase 3 — Recording B: floor trials (25 min)

17. Start the bag as step 8 with `D=/opt/nvme/bags/floor-trials-1` (change it in both places), and the
    label prompt (step 9) writing to `/opt/nvme/bags/floor-trials-1/labels.txt`.
18. Trials. Labels `tN-enter`, `tN-fall`, `tN-still`, `tN-up`, `tN-exit`; after each exit, 10 s out of view.

    | Trial | Where | How |
    |---|---|---|
    | `empty` | — | 30 s, nobody in view |
    | T1 | 2.0 m | sideways |
    | T2 | 2.0 m | sideways |
    | T3 | 2.0 m | head toward sensor |
    | T4 | 2.0 m | head toward sensor |
    | T5 | 3.0 m | sideways |
    | `walk` | 1.5–3 m | 60 s normal walking, no falls (false-alarm baseline) |
    | `exit` | — | 20 s empty |

    If anything breaks mid-way, stop (step 11 with the new path) and start `floor-trials-2`; don't
    resume into the same files.
19. Stop (step 11 with `floor-trials-1`). Want: mcap files present, `labels.txt` 33 lines.

## Phase 4 — Wrap (5 min)

20. Facts the plan needs (library versions to pin the Mac test env, build mode, bag metadata, the
    address the Jetson actually has):
    ```
    ssh jetson 'hostname -I; python3 -c "import numpy, sklearn; print(numpy.__version__, sklearn.__version__)"; ls -la ~/prevera-guardian-lidar/install/prevera_perception/lib/python3.10/site-packages/ | head -5; source /opt/ros/humble/setup.bash; for b in /opt/nvme/bags/*/ /opt/nvme/bags/*/bag/; do [ -f "$b/metadata.yaml" ] || continue; echo "== $b"; ros2 bag info "$b" 2>&1 | grep -E "Duration|Files|Topic:" | head -8; done; grep -h "bag record" ~/.bash_history | tail -3'
    ```
21. Copy to the laptop (the camera makes these GB-scale; the NVMe copy on the Jetson stays):
    ```
    scp -r jetson:/opt/nvme/bags/counter-baseline-1 <backup-dir>
    ```
    ```
    scp -r jetson:/opt/nvme/bags/floor-trials-1 <backup-dir>
    ```
22. Paste me: the four measurements from step 13, both `labels.txt`, the `ls` from steps 11/19, and the
    step-20 output. I write `docs/field-tests/2026-09-26-capture.md` from that. The camera node keeps
    running; stop it with `ssh jetson 'pkill -INT -f "[u]sb_cam_node"'` when the session ends.

## If

- `apt install ros-humble-usb-cam` fails → fall back to the gst file path in
  `docs/hardware/rig-2026-09-26.md` § Counter baseline scan (camera not viewable live).
- usb_cam says the device is busy → something else holds `/dev/video0`: `ssh jetson 'fuser -v /dev/video0'`.
- `bag.log` doesn't list `/camera/image_raw/compressed` → the camera node isn't up (step 3 log) or the topic name differs: `ssh jetson 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=42; ros2 topic list --no-daemon | grep -i image'`.
- `/scan` dies → two `sllidar_node`s (lesson 7): `~/guardian-down.sh`, then `~/guardian-up.sh`.
- Foxglove connects but shows nothing → `ROS_DOMAIN_ID`: the bridge runs inside `guardian-up.sh` with 42, and the camera node was started with 42 above.
