# Fine-tuned RF-DETR on the floor-trials-1 room frames — results (2026-09-29)

Scored against the [pre-declared plan](2026-09-29-room-frames-plan.md). The plan, the runner and the scorer were
committed and pushed before the run; no bar, threshold or definition was changed after it. Every count below is
in the [extract](2026-09-29-room-frames/room-e65db0.json).

**R1 and R2 pass, and the counter camera carries both.** On the counter camera the device-sized model read
`lying` in 32 of 33 frames of the feet-first end-on lie-down and in 30 of 30 of the head-first one, the two poses
the floor LIDAR missed, and it read `lying` in 0 of 90 walking frames. **The floor camera did not do the same:**
it read the head-first lie-down as `standing` in 30 of 30 frames, and on its own it would fail R1.

This is one subject in one room, in recorded frames of one lie-down per segment. Frames within a segment are
near-duplicates, so each count is closer to one trial than to thirty. Nobody fell.

## 1. Verdicts

| Bar | Declared | Measured | Verdict |
|---|---|---|---|
| **R1** the blind spot reads `lying`: one camera, B and F each | >= 80 % of B (27 of 33) and >= 80 % of F (24 of 30), same camera | counter camera: B **32 of 33** (97.0 %), F **30 of 30** (100 %) | **PASS**, carried by the counter camera |
| **R2** walking does not read `lying`: counter camera, W | <= 5 % (at most 4 of 90) | **0 of 90**, no tie | **PASS** |

The looser reading of R1 that the plan reports beside the verdict (a camera per segment) is also cleared, by the
same camera. The floor camera alone: B 32 of 33, F **0 of 30**.

The two bars rest on the same camera here, so the plan's warning about two cameras disagreeing does not apply to
the verdict. It applies to the floor camera, which is reported below.

## 2. What ran

| | |
|---|---|
| Plan, runner, scorer | commits `560006a` (16:14:31 PDT) and `2f39402` (16:51:03 PDT), pushed by 23:51:33 UTC as [pull request 8](https://github.com/JeremyGracey-AI/prevera-guardian-lidar/pull/8) |
| Run started | 23:52:02 UTC by the Jetson's clock, at least 29 s after the push by the Mac's; the offset between the two clocks was not recorded. Output written 23:52:53 UTC |
| Command, on the Jetson | `python3 /opt/nvme/frames/rf_room_eval.py jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--e65db0`, defaults for everything else, detached from the session |
| Runner | sha256 `50f7c8a1…8f86a` on the Jetson, the file at `2f39402` |
| Runs made | one. No smoke run; the runner has none |
| Runner's summary | 580 requested, 580 answered, 0 errors, complete, 50.4 s, confidence 0.56, server 1.7.2 |
| Frame set | manifest md5 and frame digest equal to the two the plan pinned |
| Output | 200,501 bytes, sha256 `879b3fd5901e93cba84a714745c395238048123f91fbc69f7fcd551a387b4a61`, the same on the Jetson and on the Mac copy |
| Scored | once, at 23:54:08 UTC, by the scorer at `2f39402`; exit status 0, run valid |
| Server | the process the last capture recorded (uvicorn pid 16863, started 03:11:36 UTC), before and after the run |
| Next to it | the LIDAR driver and detector running; no camera process |

**Not verified at the run.** The container's environment was not inspected: `docker` on the Jetson needs a
password the agent that made the run does not have. What is known is that the serving process is the one whose
inspect line [`yolo-offline-capture.json`](2026-09-28-roboflow/yolo-offline-capture.json) records. The run was not
captured on the network; what DR-11 says leaves during inference is assumed to have left.

**A cross-check the plan did not ask for.** The file holds 516 boxes in 514 of the 580 frames. Those are the two
counts the four cost runs of 09-28 wrote down for this model at this confidence, when they kept no class.

## 3. Every group

`none` is a frame with no pose box at confidence 0.56 or more. There was no tie, no request error and no `bed`
box in any group.

| Segment | Pose | Counter camera: `lying` | other readings | Floor camera: `lying` | other readings |
|---|---|---|---|---|---|
| A | across, 2.0 m | 33 of 35 (94.3 %) | standing 1, sitting 1 | 34 of 35 (97.1 %) | standing 1 |
| **B** | end-on, feet first | **32 of 33 (97.0 %)** | standing 1 | 32 of 33 (97.0 %) | standing 1 |
| C | across, 2.6 m | 34 of 34 (100 %) | | 34 of 34 (100 %) | |
| D | diagonal, 1.6 m | 34 of 35 (97.1 %) | sitting 1 | 14 of 35 (40.0 %) | sitting 1, none 20 |
| E | diagonal, 1.3 m | 33 of 33 (100 %) | | 22 of 33 (66.7 %) | none 11 |
| **F** | end-on, head first | **30 of 30 (100 %)** | | **0 of 30** | **standing 30** |
| **W** | standing and walking | **0 of 90** | standing 79, none 11 | 0 of 90 | standing 66, none 24 |

Only B and F on one camera, and W on the counter camera, carry a bar. Everything else in the table is report only.

## 4. Findings

- **The floor camera called a person lying head-first `standing`, every time and with confidence.** F on the floor
  camera: 30 of 30 `standing`, confidence 0.820 to 0.874. The camera sits 4 cm off the floor, level. Why the model
  reads that view as `standing` was not examined. It is the largest single fact in the run, and it is a failure.
- **The floor camera often returned nothing in the diagonal segments.** D: 20 of 35 frames with no pose box, and
  the 14 `lying` readings sit just over the threshold (0.560 to 0.678). E: 11 of 33 with none. The 09-27 results
  note that in D and E the body is partly outside both cameras' views.
- **Every upright reading in a lying segment other than F is in the segment's first two seconds.** A at 28 s and
  29 s, B at 94 s, D at 238 s, on the cameras listed in the extract. Whether the person was already down in those
  frames was not checked; the frames were not looked at again for this.
- **Walking was never read as `lying` or `sitting`, on either camera.** 145 of 180 W frames read `standing`; the
  other 35 had no pose box. On the counter camera the walking frames show hips and legs only, so this is the
  model reading legs as `standing`, not a whole person.
- **The counter camera's `lying` readings are well clear of the threshold.** Lowest confidence of a `lying`
  reading on the counter camera, by segment: A 0.858, B 0.785, C 0.845, D 0.822, E 0.781, F 0.900.

## 5. What the verdict means

As the plan declared it. For one subject in one room, in recorded frames of one lie-down per segment, the class
split read the two poses the LIDAR missed as lying on the counter camera, and did not read walking as lying on
the counter camera. That is the first room result for this option of D1 ([DR-13](../DECISIONS.md#dr-13)), and D1
stays the owner's decision.

It does not mean fall detection works. Nobody fell. Other people, rooms, light, clothing, occlusion and a bed in
view are untested. Live video and the time-on-floor Workflow are untested. D0 is untouched. The model under test
is not the one that passed F1 and F2 on public data. And one camera out of two failed a pose the other passed: the
result differs between the two cameras, and why was not examined.

## 6. How the plan was reviewed, and what was done outside it

- **Two adversarial reviews, both before the run.** The first found two ways a broken run could have been scored
  as a pass: a server that stopped answering still cleared R2, because a failed request counted against R1 and for
  R2; and a partial file got a verdict. Both were closed in the scorer before the first commit. The second review
  could not reopen them and found six smaller defects, fixed in `2f39402`. Forty-four seeded mutations of the
  runner and the scorer are each caught by a test. The findings of both reviews, and of the review of this
  document, are in [`reviews.md`](2026-09-29-room-frames/reviews.md); the mutation script and its output are
  beside it.
- **The detail in sections 3 and 4 beyond the scorer's table** (confidence ranges, which seconds) was computed
  after the verdict, from the same file, by a one-off script. It is report only and is marked so in the extract.
- **Latency was not measured here.** The runner sends no warm-up and samples no memory. For the record, the first
  request took 3.0 s (the model load) and the median of the 580 was 76.4 ms, next to the 78.7 ms of the cost run.

## 7. Limits

- One subject, one room, one recording, near-duplicate frames, a person lying down on purpose.
- One model at one confidence. `00ba18` was not run.
- The validity checks read the runner's record of itself. They cannot show who wrote a file; the hash and the
  command above are what ties this document to the run.
- The per-frame predictions are not published. The raw file stays on the Jetson and on the Mac.
