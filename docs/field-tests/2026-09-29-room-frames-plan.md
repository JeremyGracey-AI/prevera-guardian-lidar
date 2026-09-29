# Fine-tuned RF-DETR on the floor-trials-1 room frames — pre-declared evaluation (written before any result)

**Question.** A detector fine-tuned to predict the pose as a class passed its two bars on public data
([results of 09-28, F1 and F2](2026-09-28-roboflow-finetune-results.md)). That result said nothing about the test
room, and said so. This plan asks the room question for the device-sized model: in the recorded `floor-trials-1`
frames, does it read `lying` in the two end-on lie-downs the floor LIDAR missed (B: feet toward the sensor, F: head
toward the sensor), and does it keep from reading `lying` while the same person stands and walks?

**Data.** The 580 frames of the 09-27 plan: one per second per camera from `floor-trials-1`
(`/opt/nvme/frames/floor-trials-1/` on the Jetson, `manifest.json` tags segment, pose and camera). Cameras: C920 on
the counter (98 cm, 15° down) and Brio 100 on the floor (4 cm, level). One subject, one room, one recording, lying
down on purpose: there is no fall in it. The set is pinned: `manifest.json` md5
`9da67efcc98c6ffd2bbbeb4fb1d82d1d`; sha256 of the 580 files' bytes in manifest order
`a6d168682234a74af0a01c3c790baf1961e3795a4a0d060d7aa428d2b27d6cc7` (124,664,680 bytes), the same on the Jetson and
on the Mac copy when this was written. The runner records both and the scorer compares them.

| Segment | Pose | Frames per camera |
|---|---|---|
| A | across, 2.0 m | 35 |
| **B** | end-on, feet first, 0.9 m | **33** |
| C | across, 2.6 m | 34 |
| D | diagonal, 1.6 m | 35 |
| E | diagonal, 1.3 m | 33 |
| **F** | end-on, head first, 0.83 m | **30** |
| **W** | standing and walking, nobody down | **90** |

Two things the 09-27 results found about these frames hold here. Frames within a segment are near-duplicates, so
each segment on each camera is closer to one trial than to thirty
([results of 09-27](2026-09-27-rfdetr-results.md)): 27 of 33 is not 27 independent hits. And on the counter camera
the walking frames show hips and legs only.

**Model.** `jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--e65db0`, 288 x 288. Its classes are `bed`,
`standing`, `sitting` and `lying`, spelled as the platform's evaluation of this model lists them. It is the
platform's recommended child of the 09-28 architecture search and the faster of the two models measured on the
device (78.7 ms median, serial, cameras off). **It is not the model that passed F1 and F2**: those bars were
declared for, and passed by, `...--00ba18`. `e65db0` was reported beside it with no bar. Its training split was 518
public images ([plan of 09-28](2026-09-28-roboflow-finetune-plan.md), data table); no frame from this room was in
training, validation or test. `00ba18` is not run under this plan.

**Confidence.** 0.56, sent in every request and re-applied by the scorer. It is the `f1ConfThresh` the platform
reports for this child on the valid split of the public data
([`arm-A-nas-run.json`](2026-09-28-roboflow/arm-A-nas-run.json), `platform_recommended_children`), and the
confidence the device-fit run used. It is not tuned on room frames, and it is not moved after the result.

**Serving.** Roboflow Inference 1.7.2 in the JetPack 6.2 container on the Jetson Orin Nano, started by
[`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh) with the flags of
[DR-11](../DECISIONS.md#dr-11). When this was written the running server was the process the last capture
recorded, with its inspect line
([`yolo-offline-capture.json`](2026-09-28-roboflow/yolo-offline-capture.json), `container`); the results say
whether that still held at the run. The runner posts to `127.0.0.1:9001` and nowhere else, and does not honour
proxy settings. This run is not captured on the network. What DR-11 records as still leaving during inference,
the usage collector's aggregated record, is expected to leave during this run as well. If the model is not in
memory the first request loads it: from the cache volume when it is there, as on 09-28, and from the platform
when it is not, and a pull has never been captured. Nothing here measures either again.

**Runner and scorer.** [`jetson/rf_room_eval.py`](../../jetson/rf_room_eval.py) sends one request per manifest
frame and writes each frame's predictions as returned (class, confidence, box), with no rate and no verdict. It
never writes over a file, and it has no smoke mode: every run asks all 580 frames, so there is no small run to
look at first. A run that is interrupted still writes the rows it has and says it is not complete.
[`tools/bag_analysis/score_room_frames.py`](../../tools/bag_analysis/score_room_frames.py) reads that file, decides
whether the run is valid and applies the definitions below. Both are committed with this plan, with their tests
(`src/prevera_perception/test/test_room_frames.py`), before the run.

**A valid run.** A run gets a verdict only when all of this holds, and the scorer checks each item:

- the file names this model, confidence 0.56, the loopback URL and server 1.7.2, and says the run is complete;
- its manifest md5 and frame digest are the two above, and its digest of the rows matches the rows;
- it holds the 580 manifest files once each, in the manifest's order, in the fourteen groups of the table;
- no request failed;
- every prediction has a class and a confidence, and every class is one of the four.

A run that is not valid gets no verdict, and the scorer shows no reading from it: it prints its reasons, which
come from counts, names and the runner's own record, and nothing else. The file is kept and reported, and the run
is repeated whole under a new file name. **The first valid run is the result, and a valid run is not repeated.**
One reason has a different exit. A class name outside the four means the harness does not match the model; the
names and their counts are then already seen, so the run cannot be scored under this plan and a new plan is
written before the scorer changes.

These checks read the runner's record of itself. They catch the wrong model, the wrong threshold, a partial run
and a file patched by hand. They cannot show who wrote a file, so the results give the command as it was run and
the sha256 of the file as it left the Jetson.

**What a frame reads.** Of the boxes at confidence 0.56 or more whose class is `standing`, `sitting` or `lying`,
the frame reads the class of the most confident one. `bed` labels furniture and is never a reading. No such box:
the frame reads `none`. Two different pose classes sharing the top confidence: `tie`.

**Pass conditions (declared 2026-09-29 before running):**

1. **R1, the blind spot reads lying:** at least one camera reads `lying` in **>= 80 %** of its B frames
   (27 of 33) **and** in **>= 80 %** of its F frames (24 of 30). The same camera has to carry both segments. The
   09-27 plan's "on at least one camera" was scored per segment, a camera for B and a camera for F, and that data
   satisfied both readings. Here the per-segment reading is reported beside the verdict and is not the verdict.
   A `tie` is not a lying reading.
2. **R2, walking does not read lying:** on the counter camera, `lying` is read in **<= 5 %** of W frames
   (at most 4 of 90). A `tie` counts as lying here.
3. **Report only, no bar:** the full distribution of readings for every segment and camera, A, C, D and E and W on
   the floor camera included, and the number of `bed` boxes per group. Nothing in the room was labelled as a bed.

**What a verdict means.** The two bars can rest on different cameras: R1 names the camera that carried it, and R2
is about the counter camera alone. If the floor camera carries R1, R2 says nothing about that camera, and the
result is worded camera by camera with W on the floor camera beside it. With that said, R1 and R2 both passing
means that for one subject in one room, in recorded frames of one lie-down per segment, the class split read the
two poses the LIDAR missed as lying on the named camera, and did not read walking as lying on the counter camera:
the first room result for this option of D1 ([DR-13](../DECISIONS.md#dr-13)). It does not mean fall detection
works. Nobody fell; other people, rooms, light, clothing, occlusion and a bed in view are untested; live video and
the time-on-floor Workflow are untested; and it does not touch D0. Either bar failing means this model at this
confidence is a measured no in this room, the public-data result stays a public-data result, and the next step is
a new plan (room frames labelled and trained on, or the other model), not a second look at this one. Every failure
is reported with the frames behind it; no threshold is changed after results.

**Already seen.** The same 580 frames went through this model on 09-28 for cost and for the network captures
(`f5_device_fit.py`: four full runs and a 5-frame smoke test). Those runs wrote two counts and no prediction: 516
boxes in all, in 514 of the 580 frames, at confidence 0.56, the same in all four
([`f5-e65db0.json`](2026-09-28-roboflow/f5-e65db0.json)). The predictions themselves do exist in two places
nobody has read. The two egress captures recorded the docker bridge as well as the uplink, so the server's
plaintext responses to those runs are inside the capture files on the Jetson
([`egress-recapture-e65db0.json`](2026-09-28-roboflow/egress-recapture-e65db0.json), `capture`); the summaries were
made from packet headers (`tcpdump -q`), and the payloads were not decoded. And by the 09-28 reading of the
server's source, until the pingback was switched off the server sent the platform a per-request record with class
and confidence ([results of 09-28, EG1](2026-09-28-roboflow-finetune-results.md)); the capture could not read it,
and the owner has not opened model monitoring for this model. No class, confidence or box from a room frame was
looked at before this plan. The frames themselves have been seen many times, with the stock model's `person` boxes
on them.
