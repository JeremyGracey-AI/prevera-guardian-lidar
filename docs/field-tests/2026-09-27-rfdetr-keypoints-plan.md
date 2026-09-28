# RF-DETR keypoint preview on the floor-trials-1 B and F frames: pre-declared check (written before any result)

> **Publication note.** Published 2026-09-27 from the private development repository. Host names, LAN
> addresses, local paths, account names, one branch name and references to unpublished planning documents were replaced
> (for example `<jetson-ip>`); measurements, tables and findings are unchanged. Commit hashes, branch names
> and PR numbers refer to the private history and do not resolve here. Decision labels such as D0 and D1
> are defined in [`docs/DECISIONS.md`](../DECISIONS.md).
> This is a pre-declared plan: apart from these replacements its text is exactly as committed before the run.

Written 2026-09-27 on branch `<docs-branch>`. At the time of writing, `RFDETRKeypointPreview` has not been run on any
frame from this room. The stock-detection results from `6460492` ([`2026-09-27-rfdetr-results.md`](2026-09-27-rfdetr-results.md))
are already known. They were used only to write the definitions below (which W/Brio frames show an empty room, where
boxes touch the frame edge). They were not used to pick any threshold.

**Question.** The floor-level LIDAR missed both end-on lie-downs in `floor-trials-1`: B (feet toward the sensor, bag
seconds 94-127) and F (head toward the sensor, 370-400). Stock RF-DETR detection sees the person there, but its box
shape does not separate lying from standing (detection C3 failed), so open design decision **D1 (boxes vs
keypoints)** is still open. Two questions:

1. Does Roboflow's RF-DETR **keypoint preview** model, run locally on this Mac, return usable human keypoints on the
   B and F frames?
2. Does a simple keypoint feature (torso angle) separate lying (A) from standing (W)?

## Data

Frames are read from `~/src/local/prevera-frames/floor-trials-1/`. They are JPEG 1280x720, one per second per
camera, with `manifest.json`. No new frames are extracted from the bag.

**Selection rule.** Take every B and F frame. From A and W, take the frames where `(t_s - first t_s of the segment)
mod 3 == 0`. Use both cameras at every selected `t_s`.

| Seg | Pose (manifest) | LIDAR | Selected `t_s` | Per camera | Files |
|---|---|---|---|---|---|
| A | lying across, 2.0 m | detected | 28, 31, 34, ..., 61 | 12 | 24 |
| B | end-on, feet toward the sensor, 0.9 m | missed | 94-126, all | 33 | 66 |
| F | end-on, head toward the sensor, 0.83 m | missed | 370-399, all | 30 | 60 |
| W | standing / walking, no fall | n/a | 430, 433, 436, ..., 517 | 30 | 60 |
| | | | | **Total** | **210** |

Cameras: `c920` is the counter camera (98 cm high, 15 deg down). `brio` is the floor camera (4 cm high, level).

What the detection run already showed about these frames (known now, not changed here):
- **W/Brio empty frames.** W/Brio frames at t = 440-447 s and 464-475 s show an empty room. Six selected W times fall
  there: 442, 445, 466, 469, 472 and 475. They stay in the denominator.
- **W/C920 shows no torso.** On the C920 in W, every person box starts at the top pixel row, so a standing person's
  torso and head are not in view. That is why K2 is scored on the Brio.
- **F/Brio heads may be cropped.** F/Brio boxes touched the top edge of the frame, so the head may be cropped. This
  is part of what K3 measures. It is not a reason to exclude frames.
- **Near-duplicate frames.** At 1 fps, frames within a segment are near-duplicates. Each segment on each camera is
  closer to one trial than to 30.

## Model and run

**Model and weights**
- **Package:** `rfdetr==1.11.0` from PyPI (Apache 2.0) and `supervision>=0.29.0`. No `[train]` or `[lora]` extras.
- **torch:** the default PyPI macOS arm64 wheel (CPU+MPS build). Its version will be recorded.
- **Class:** `rfdetr.RFDETRKeypointPreview`, size `rfdetr-keypoint-preview`, config `RFDETRKeypointPreviewConfig`.
  - Input 576 px, 17 keypoints per class, `dinov2_windowed_small` backbone, 40.7M params.
  - Stock pretrained COCO person-keypoint weights, no fine-tuning.
  - Constructed with `device="cpu"` and nothing else. In particular, no `num_classes`.
- **Checkpoint:** `rf-detr-keypoint-preview-xlarge.pth`.
  - Source: `https://storage.googleapis.com/rfdetr/rf-detr-keypoint-preview-xlarge.pth`, 163,696,618 bytes.
  - md5 `6de511943ee85a547d4c5cb527daf0eb`, checked locally before the first inference. A mismatch stops the run.
  - The "xlarge" in the filename does not make this an `rfdetr_plus` / PML 1.0 model. It sits in the core
    `ModelWeights` enum and is Apache 2.0.

**Environment and device**
- **Environment:**
  - venv `<venv>` (a throwaway local venv), created with `~/.local/bin/uv`, Python 3.11.
  - `UV_CACHE_DIR=<venv>/.uv-cache`.
  - `RF_HOME=<venv>/models`.
- **Device:** this Mac, CPU, with `device="cpu"` passed explicitly (the default would pick MPS). MPS is not used for
  the scored run.
  - Per-frame wall time around `model.predict` is recorded and reported.
  - It is **not** a device-latency measurement, and it is not comparable to the Jetson numbers in the detection
    results.
  - This check does not answer whether the keypoint model fits on the Orin Nano next to the ROS stack.

**Input and call**
- **Input:** each JPEG is opened with PIL, converted with `.convert("RGB")`, and passed at its native 1280x720. The
  script does no crop, resize or enhancement. Only the model's own preprocessing is applied.
- **Call:** `model.predict(img, threshold=0.1)`. Every returned instance is logged with `xyxy`,
  `detection_confidence`, `class_id`, `class_name`, `xy` (17x2), `keypoint_confidence` (17) and `covariance`
  (17x2x2).

**Egress**
- The Jetson and its inference server are not used.
- No frame is uploaded to any cloud service or hosted API, and no Roboflow API key is used.
- The only network traffic is the pip install and the checkpoint download.

**Planned outputs (not part of this commit)**
- Raw results: `results-rfdetr-keypoint-preview.json`, next to the frames.
- The runner and a stdlib-only scorer, under `tools/bag_analysis/`. They are committed with the results doc.

## Definitions (fixed now)

1. **Keypoint schema.**
   - **Source of the mapping.** The index-to-name mapping is read from the package if the package exposes one, and it
     is recorded. Otherwise the COCO-17 order is assumed: 0 nose, 1 left_eye, 2 right_eye, 3 left_ear, 4 right_ear,
     5 left_shoulder, 6 right_shoulder, 7 left_elbow, 8 right_elbow, 9 left_wrist, 10 right_wrist, 11 left_hip,
     12 right_hip, 13 left_knee, 14 right_knee, 15 left_ankle, 16 right_ankle.
   - **Check before scoring.** Before any condition is computed, labelled keypoints are drawn on two frames: the first
     selected W/Brio frame with a scored instance, and the first selected A/C920 frame with one (both in time order).
   - **What the check looks for.** Only gross mislabelling: head points not on the head, ankles not at the feet,
     shoulders and hips swapped.
   - **If the order differs.** If the drawing shows a different order that can be read without ambiguity, that
     mapping is written down before scoring and used. If it cannot be read, the run stops and is reported.
   - **Left/right swaps** do not matter here. K2 uses midpoints, and K3 pools the head group and the ankle pair.
   - The mapping is frozen once the check is done.
   - **Named groups:**
     - head = nose, left_eye, right_eye, left_ear, right_ear
     - shoulders = left_shoulder, right_shoulder
     - hips = left_hip, right_hip
     - ankles = left_ankle, right_ankle
2. **Scored instance.**
   - **Cutoff.** An instance counts only if it is the person class (`class_id` 0) and its `detection_confidence` is
     >= 0.3.
   - **The score is fused.** `detection_confidence` is the fused object-and-keypoint-uncertainty score as returned
     (default `postprocess_trace_alpha` 0.2). It is not comparable to the 0.90-0.96 detection confidences of the
     earlier run.
   - **Instances between 0.1 and 0.3** are listed in the results but never count toward K1-K3.
   - **More than one instance in a frame.** The scored instance is the one with the most keypoints at confidence
     >= 0.5. A tie goes to the higher `detection_confidence`.
   - **The same instance feeds K1, K2 and K3** for that frame.
3. **Confident keypoint** = `keypoint_confidence >= 0.5`. The `visible` flag is ignored, because in 1.11.0 it is
   always True.
4. **"At least half of its keypoints"** = at least 9 of the 17 keypoints are confident.
5. **Torso angle.**
   - `mid_s` = mean of the two shoulder points and `mid_h` = mean of the two hip points, in image pixels.
   - `v = mid_h - mid_s`.
   - `angle = degrees(atan2(|v_x|, |v_y|))`, folded into [0, 90]. 0 = vertical and 90 = horizontal, and head-up versus
     head-down does not matter.
   - The angle is computed only when all four torso keypoints are confident on the scored instance and `|v| >= 5 px`.
     Otherwise the frame has **no angle**.
6. **Median for K2.** Per segment on the Brio:
   - **Median:** taken over the frames that have an angle.
   - **Denominator:** every selected frame of that segment and camera (A 12, W 30), including the six empty-room W
     frames.
   - **Minimum count:** a segment's median counts toward K2 only if at least half of its selected frames have an angle
     (A >= 6/12, W >= 15/30). Otherwise that half of K2 is **not measurable**, which is not a pass.
   - This defines the median. It is not an extra condition.
7. **"On at least one camera" (K1).** For each of B and F separately, the rate is the higher of the two cameras'
   rates, so B may pass on one camera and F on the other. The detection scorer used the same reading. The stricter
   reading, where one camera must carry both B and F, will also be tabulated but not scored.
8. **Integer bars.**
   - B: 90 % of 33 is 29.7, so B passes at >= 30/33. 29/33 (87.9 %) fails.
   - F: F passes at >= 27/30. Exactly 90 % passes.
9. **Run validity.** Three things are recorded before scoring:
   - (a) the checkpoint md5;
   - (b) no "loaded only partially" warning when the checkpoint loads (rf-detr #1145);
   - (c) every returned instance has `class_id` 0 and `class_name` `'person'` (rf-detr #1150).

   If any of the three fails, the run is reported as invalid and K1-K3 are not scored.

## Pre-declared conditions

**K1: pose found.** >= 90 % of B frames and >= 90 % of F frames on at least one camera have a person instance with at
least half of its keypoints at confidence >= 0.5.
- Bars: B >= 30/33 and F >= 27/30.
- The camera reading is definition 7.
- The instance and keypoint rules are definitions 2-4.

**K2: lying vs standing on the FLOOR camera (brio).**
- Torso axis = midpoint(shoulders) -> midpoint(hips) in image pixels; its angle from image vertical.
- Pass when the median angle in A is >= 60 deg (lying reads horizontal) **and** the median angle in W is <= 30 deg
  (standing reads vertical).
- Both medians are Brio-only and follow definitions 5-6.
- B and F are reported, not scored: end-on foreshortening is the question being explored.

**K3: report only, no pass bar.** Keypoint confidences for the head keypoints in F and the ankle keypoints in B, the
parts the LIDAR saw.
- **Per camera, on the scored instance:** for each of the five head keypoints (F) and the two ankles (B), the median,
  the minimum and the fraction >= 0.5, plus the per-frame maximum over the group.
- **Frames with no scored instance** are counted as "no instance", not as confidence 0.
- **Keypoint uncertainty:** the covariance size, sqrt(trace) in px, is reported alongside the confidences.

**Also reported, not scored:**
- K2 angles on the C920 for A and W.
- Angle distributions for B and F on both cameras.
- The number of instances per frame.
- CPU time per frame.
- The stricter one-camera reading of K1.
- Raw object scores from a second pass with `postprocess_trace_alpha=0.0`, but only if that constructor argument is
  confirmed to reach the postprocessor. Those scores are never used in a condition.

## What cannot change after results

The following are fixed now and cannot change after results:
- the frame set (210 files above);
- the package, version and checkpoint md5;
- the device;
- the predict threshold of 0.1 and the scoring cutoff of 0.3;
- the keypoint confidence of 0.5 and the 9-of-17 rule;
- the instance-selection rule;
- the torso definition and its gating, including the 5 px floor;
- the half-of-frames rule for the K2 median;
- the per-segment camera reading;
- the K1 and K2 bars.

The keypoint mapping is frozen after the two-frame schema check and before any condition is computed. Every failure
is reported as a finding with the frames that failed. If a definition turns out to be wrong, that is written next to
the unchanged verdict. Any rerun gets its own new pre-declared plan.

## Gaps, stated before the run

- **One subject, one room, one session.** Frames within a segment are near-duplicates. This is a feasibility check,
  not a recall estimate.
- **Out-of-distribution poses.** The COCO keypoint training data is mostly upright people. Lying and foreshortened
  poses seen from a camera 4 cm off the floor are out of distribution, which is part of what this measures.
- **Preview model.** The API and the weights may change before the stable release. Results are tied to
  `rfdetr==1.11.0` and md5 `6de511943ee85a547d4c5cb527daf0eb`.
- **CPU on the Mac, not the Jetson.** No latency or memory claim is made for the device.
- **K2 is a single hand-picked feature on A vs W.** A pass shows separation on these frames. It is not a lying
  classifier. The other lying segments (C, D, E) are not in this check.
- **K2 cannot be tested on the counter camera,** because W/C920 never shows the standing torso.
- **Telemetry.** The `rfdetr` / `supervision` packages have not been audited for telemetry, and no egress capture is
  made. The runner itself sends no frame anywhere.
