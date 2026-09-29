# Roboflow Workflow: time on the floor

[`time_on_floor_workflow.json`](time_on_floor_workflow.json) is the camera half of the fusion this repository has
not built ([DR-14](../../docs/DECISIONS.md#dr-14)), written as a Roboflow Workflow so that it runs unchanged on the
hosted API, in the Inference container on the Jetson, or in batch over recorded video. It is also the public
counterpart of [`jetson/rf_eval.py`](../../jetson/rf_eval.py), the RF-DETR runner used on the device (in the repo since 2026-09-28).

```
image ──► detector (fine-tuned RF-DETR, pose as a class)
              │
              ▼
       keep only down_classes            (a standing or sitting person never reaches the tracker)
              │
              ▼
          ByteTrack                      (a track exists only while the detector says "down";
              │                           it dies lost_track_buffer frames after the person gets up)
              ▼
     floor_zone ──► time_in_zone         (seconds since this track's centre entered the zone)
              │
      ┌───────┴───────────────┐
 down_on_floor            warn (time_in_zone >= warn_after_s)
```

| Input | Default | Meaning |
|---|---|---|
| `model_id` | `jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--00ba18` | the arm-A model the [fine-tune plan](../../docs/field-tests/2026-09-28-roboflow-finetune-plan.md)'s rule picked; `…--e65db0` is the fast child (see the [results](../../docs/field-tests/2026-09-28-roboflow-finetune-results.md)). Any detector whose classes include a down pose works |
| `confidence` | 0.5 | one number for the three gates a detection passes to become a timed track: the detector's threshold, ByteTrack's `high_conf_det_threshold` and its `track_activation_threshold` |
| `down_classes` | `lying`, `fall` | the class names that mean "on the floor" in the plan's three datasets (`lying` in arms A and C, `fall` in arm B) |
| `floor_zone` | `[[0,300],[1280,300],[1280,720],[0,720]]` | the polygon in which a down pose counts, in pixels of a **1280x720** frame (rescale it for any other size); a bed in the upper part of the frame is outside it, which is how the workflow keeps "lying in bed" out of the count (`bed` is only a furniture label) |
| `warn_after_s` | 4.0 | seconds down inside the zone before `warn` is non-empty; 4.0 s is the LIDAR detector's `sustained_down_s` ([ARCHITECTURE](../../docs/ARCHITECTURE.md)) |

Outputs: `detections` (every box the model returned), `down_on_floor` (tracked down poses inside the zone, each
with `time_in_zone` in seconds), `warn` (the subset past `warn_after_s`), `visualization` (zone, boxes and the
time label).

## How the clock behaves, exactly

- **It counts only while the detector reports a down pose.** Upright detections are dropped before the tracker,
  so no track, and no clock, exists for a standing or sitting person. This is why the tracker runs *after* the
  class filter: `time_in_zone` clears a track's entry time only when it sees that track outside the zone, never
  when the track simply stops arriving, so a tracker in front of the filter would carry a person's first
  lie-down into the next one.
- **Getting up ends the track** within `lost_track_buffer` (10) frames; the next lie-down gets a new tracker id
  and a clock at zero. A second lie-down that starts inside those 10 frames can re-attach to the old track and
  continue its clock: at 10 frames per second that is a one-second window.
- **A flicker of the detector breaks the track**, and a new one needs `minimum_consecutive_frames` (2) to be
  confirmed, so flicker under-counts time down. It never over-counts. There is no class lock: a majority vote
  would delay the clock by its vote window and hold "lying" after the person is up.
- **Time accumulates on video only.** On a single image no track is ever confirmed, so `down_on_floor` and
  `warn` are empty whatever the image shows; `detections` still carries the model's boxes.
- **`time_in_zone` is time since the centre entered the zone, not time since a fall.** A person who lies down on
  purpose accumulates it too. The LIDAR path has the same limitation and the same word for it: WARN is "down and
  still", ALERT is the verification stage's ([DR-15](../../docs/DECISIONS.md#dr-15)).
- Entry times of dead tracks stay in the block's per-video state (one small entry per lie-down); harmless for a
  session, noted for a long-running stream.

## What has been checked, and what has not

- The specification validates against Roboflow's block manifests (2026-09-28), and its selectors resolve
  ([test](../../src/prevera_perception/test/test_roboflow_workflow_spec.py)).
- It ran once on the hosted API on **one public image** with the public model `lying3/3` (an earlier revision with
  a class lock, same detector and filter): the model returned one `sit` box; nothing reached the timer, as nothing
  can on a single image. That run shows the specification executes, nothing more.
- **Not checked:** the clock on video, the reset when a person gets up, `warn` firing. Those need a recorded
  sequence run through `InferencePipeline`, which has not been done. No frame from the test room has been sent
  to the hosted API and none will be: on the device the same JSON runs against the local Inference server.
- Nothing here fuses with the LIDAR. Where the two meet (D0) is still open.

## Running it

Hosted, on a public image or video (the workflow is saved in the workspace as
`guardian-time-on-floor-fine-tuned-rf-detr-floor-zone`):

```python
from inference_sdk import InferenceHTTPClient
import json, os
spec = json.load(open("tools/roboflow/time_on_floor_workflow.json"))
client = InferenceHTTPClient(api_url="https://serverless.roboflow.com", api_key=os.environ["ROBOFLOW_API_KEY"])
out = client.run_workflow(specification=spec, images={"image": "https://.../public-image.jpg"})
```

On the Jetson, start the local Inference server with
[`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh), the DR-11 command, and run the same file with
`api_url="http://127.0.0.1:9001"`. The command sets `--read-only`, `127.0.0.1:9001`,
`ACTIVE_LEARNING_ENABLED=False`, `METRICS_ENABLED=False`, `DISABLE_VERSION_CHECK=True`, `YOLO_OFFLINE=True`,
`TELEMETRY_OPT_OUT=True` (inert in 1.7.2, kept for documentation), and `TRITON_CACHE_DIR=/tmp/triton-cache` until
[roboflow/inference#3072](https://github.com/roboflow/inference/pull/3072) is released. While requests arrive, the
usage collector's aggregated record still goes to `api.roboflow.com`
([DR-11](../../docs/DECISIONS.md#dr-11)). On video, `InferencePipeline.init_with_workflow(...)` from the `inference`
package with `workflow_specification=spec`, so that the tracker and the zone timer see consecutive frames with
their frame numbers.

The API key lives in the environment (`ROBOFLOW_API_KEY`), never in this file or in a commit.
