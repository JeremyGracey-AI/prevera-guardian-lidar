# RF-DETR on the floor-trials-1 frames — pre-declared evaluation (written before any result)

**Question.** The floor-level LIDAR missed both end-on lie-downs in `floor-trials-1` (B: feet toward the sensor,
F: head toward the sensor; the scan plane saw only 0.22–0.33 m of soles or head). Does a stock RF-DETR person
detector, running locally on the Jetson Orin Nano (Roboflow Inference server, JetPack 6.2 image, localhost only),
see the person in exactly those frames — and at what cost in latency and memory next to the running ROS stack?

**Data.** 580 frames, one per second per camera, from `floor-trials-1` (`/opt/nvme/frames/floor-trials-1/`,
`manifest.json` tags segment, pose, camera, LIDAR outcome). Cameras: C920 on the counter (98 cm, 15° down) and
Brio 100 on the floor (4 cm, level). Segments: A across 2.0 m · B end-on feet-first 0.9 m · C across 2.6 m ·
D diagonal 1.6 m · E diagonal 1.3 m · F end-on head-first 0.83 m · W standing/walking (no fall).

**Model.** Stock COCO RF-DETR (no fine-tuning, no frames from this room in training), class `person`,
confidence threshold 0.4, served by `roboflow/roboflow-inference-server-jetson-6.2.0`. Frames never leave the device.

**Pass conditions (declared 2026-09-27 before running):**

1. **Coverage of the LIDAR blind spot:** person detected in **>= 90 %** of B frames and **>= 90 %** of F frames on
   at least one camera.
2. **Detection when nobody is down:** person detected in **>= 90 %** of W frames on the counter camera.
3. **Shape separates lying from standing (counter camera):** median box aspect w/h in every lying segment (A–F)
   is **> 1.0**, and in W is **< 1.0**. (Reported, not tuned: a fail here means box shape alone cannot carry D1 and
   keypoints are needed.)
4. **Fits on the device:** serial latency and minimum `MemAvailable` during the run reported alongside the LIDAR
   stack (driver + detector + bridges running, cameras stopped). No pass bar — this is the number the D0 decision
   (fusion inside a Workflow vs in ROS) needs.

Every failure is reported as a finding with the frames that failed; no threshold is changed after results.

---

## Publication note

Published 2026-09-27 from the private development repository. Host names, LAN addresses, local paths, account
names and references to unpublished planning documents were replaced (for example `<jetson-ip>`); measurements,
tables and findings are unchanged. Commit hashes, branch names and PR numbers refer to the private history and do
not resolve here. Decision labels such as D0 and D1 are defined in [`docs/DECISIONS.md`](../DECISIONS.md). Line
numbers cited into this document from other documents refer to it as published: this note sits at the end so
they hold. This is a pre-declared plan: apart from these replacements its text is exactly as committed before the run.
