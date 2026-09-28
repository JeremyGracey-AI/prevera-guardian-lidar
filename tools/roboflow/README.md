# Roboflow Workflow: time on the floor

[`time_on_floor_workflow.json`](time_on_floor_workflow.json) is the camera half of the fusion this repository has
not built ([DR-14](../../docs/DECISIONS.md#dr-14)), written as a Roboflow Workflow so that it runs unchanged on the
hosted API, in the Inference container on the Jetson, or in batch over recorded video. It is also the public
stand-in for `rf_eval.py`, the RF-DETR runner used on the device that is not published.

```
image ──► detector (fine-tuned RF-DETR, pose as a class) ──► ByteTrack ──► class lock (majority vote per track)
                                                                                   │
                       floor_zone ──► time_in_zone ◄── keep only down_classes ◄────┘
                                          │
                        ┌─────────────────┴──────────────────┐
                 down_on_floor                          warn (time_in_zone >= warn_after_s)
```

| Input | Default | Meaning |
|---|---|---|
| `model_id` | `fall_detection-johan-jsi2o/1` | the model of arm A in the [fine-tune plan](../../docs/field-tests/2026-09-28-roboflow-finetune-plan.md); any detector whose classes include a down pose works |
| `confidence` | 0.5 | detector, tracker activation and class-lock vote threshold, one number |
| `down_classes` | `lying`, `fall`, `person-fall`, `fallen` | the class names that mean "on the floor" in the three public datasets of the plan |
| `floor_zone` | lower 420 px of a 1280x720 frame | the polygon in which a down pose counts; a bed in the upper part of the frame is outside it, which is how the workflow keeps "lying in bed" out of the count (`bed` is only a furniture label) |
| `warn_after_s` | 4.0 | seconds down inside the zone before the `warn` output is non-empty; 4.0 s is the detector's `sustained_down_s` ([ARCHITECTURE](../../docs/ARCHITECTURE.md)) |

Outputs: `detections` (every box the model returned), `down_on_floor` (tracked down poses inside the zone, each
with `time_in_zone` in seconds), `warn` (the subset past `warn_after_s`), `visualization` (zone, boxes and the
time label). Time only accumulates on video: on a single image `time_in_zone` is 0 and `warn` is empty.

## What it does and does not claim

- Nothing here fuses with the LIDAR. The Workflow gives the camera side one number, seconds down inside the floor
  zone, in the same units as the LIDAR detector's stillness clock. Where the two meet (D0) is still open.
- It has been run on the hosted API on **public images only**. With the public model `lying3/3` on the
  arm-A dataset's cover image it returned one box, `sit` at 0.996, and an empty `down_on_floor`, which is the
  correct answer for that image. No frame from the test room has been sent to the hosted API and none will be:
  on the device the same JSON runs against the local Inference server (below).
- `time_in_zone` measures time since the track's centre entered the zone, not time since a fall. A person who lies
  down on purpose accumulates it too. The LIDAR path has the same limitation and the same name for it: WARN is
  "down and still", ALERT is the verification stage's word ([DR-15](../../docs/DECISIONS.md#dr-15)).

## Running it

Hosted, on a public image (the model must be trained; the workflow is saved in the workspace as
`guardian-time-on-floor-fine-tuned-rf-detr-floor-zone`):

```python
from inference_sdk import InferenceHTTPClient
import json, os
spec = json.load(open("tools/roboflow/time_on_floor_workflow.json"))
client = InferenceHTTPClient(api_url="https://serverless.roboflow.com", api_key=os.environ["ROBOFLOW_API_KEY"])
out = client.run_workflow(specification=spec, images={"image": "https://.../public-image.jpg"},
                          parameters={"model_id": "fall_detection-johan-jsi2o/1"})
```

On the Jetson, against the local Inference server started with the hardened command in
[DR-11](../../docs/DECISIONS.md#dr-11) (`--read-only`, `127.0.0.1:9001`, `ACTIVE_LEARNING_ENABLED=False`,
`TELEMETRY_OPT_OUT=True`; and `TRITON_CACHE_DIR=/tmp/triton-cache` until
[roboflow/inference#3072](https://github.com/roboflow/inference/pull/3072) is released), the same file, with
`api_url="http://127.0.0.1:9001"`. On video, use `InferencePipeline.init_with_workflow(...)` from the `inference`
package with `workflow_specification=spec`, so that the tracker and the zone timer see consecutive frames.

The workflow-level API key stays in the environment, never in this file or in a commit (`.gitignore`).
