# Fine-tuned RF-DETR on public fall datasets: results

Results of the [pre-declared plan](2026-09-28-roboflow-finetune-plan.md) (committed `4adc303`, 2026-09-28
11:30 PDT, before any training started). Every number here is copied from the evaluation extracts in
[`2026-09-28-roboflow/`](2026-09-28-roboflow/), which hold what Roboflow's Model Evaluation returned; nothing was
recomputed. Public data only: no frame from the test room was uploaded, trained on or scored.

## 1. Answer

**F1 and F2 pass on public data.** A detector fine-tuned to predict the pose as a class separates a lying person
from a standing or sitting one on the arm-A test split: `lying` precision **1.000** and recall **1.000** at the
threshold the rule fixed (F1, bar >= 0.90 each), and **0** lying-to-upright or upright-to-lying confusions in 24
ground-truth lying instances (F2, bar <= 5 %). So a fine-tuned class split is a live option for **D1**
([DR-13](../DECISIONS.md#dr-13)) beside keypoints. What this does not show, as the plan says: whether the model
works in the test room (that needs the room-frame plan), and anything about D0.

The test split is small: 73 images, 89 instances (bed 16, lying 24, sitting 11, standing 38), one Universe
dataset of one author's rooms. The comparison arms say the same recipe reaches `fall` 0.93 / 0.98 on the URFD
frames and `lying` 0.91 / 0.95 on lying3, with 0 and 4 pose swaps respectively. Treat the pass as "the approach
is not dead on arrival", not as a recall estimate.

## 2. What ran

| Arm | Dataset (fork) | Version | Model | Training | Credits (run) |
|---|---|---|---|---|---|
| A, primary | `fall_detection-johan-jsi2o` (736 images; bed, standing, lying, sitting) | v1, 640 stretch, no offline augmentation | RF-DETR NAS (Standard), `rfdetr-nas-parent` | 18:31 to 20:30 UTC, 1 h 59 min; 37 frontier children + 4 stock baselines out of 5,011 architectures | 3.94 (NAS page, in the extract) |
| B | `fall-detection-urfd-vzgtq` (2,204; fall, not_fall) | v1, same | `rfdetr-nano` | 30 min | not recorded |
| C | `lying3-vcr6i` (5,323; standing, lying, sit), splits rebalanced 70/20/10 | v1, same | `rfdetr-nano` | 40 min | not recorded |

Deviations from the plan, all forced by tooling. Each was decided when it arose, before the verdict it could
have touched was read, and all are written down here, in the document written after the evaluations:

- **Arm B trained twice.** The first `trainings_create` call returned an internal error after it had started a
  run; the retry started a second. Same version, same recipe. The rule, fixed when the duplicate was found and
  before either evaluation was read: the run whose creation call returned successfully (`...-nano-t2`) is arm B;
  the first (`...-nano-t1`, test mAP@50 0.987 against 0.993) is reported as a seed-variance reading and not
  scored. Both are report-only arms, so no verdict depends on the choice.
- **The rule's arm-A model had no evaluation.** The platform evaluates its own `recommended` child (the fast end of
  the frontier). The plan's rule picks the child with the highest valid mAP@50-95, `...--00ba18` (96.85), so its
  evaluation was started by hand from the model page at 21:01 UTC and read when it finished. The recommended
  child is reported beside it as the device-sized candidate, which is what the plan asked for in the absence of
  size names on NAS children.
- **Confusion matrices exist at 0.1 steps only.** The rule's thresholds are 0.75 (A), 0.39 (B) and 0.44 (C); the
  matrices are read at 0.70 and 0.80 (A, identical), 0.40 (B) and 0.40 (C). Per-class precision and recall are at
  the exact thresholds.
- **NAS latency is measured on the platform's targets (AI1, T4), not on the Jetson.** F5 stays a device
  measurement and was not run today (section 5).

## 3. Arm A, scored

Model `...-rfdetr-nas-t1--00ba18`. Two valid-split mAP@50-95 figures exist for it and both are quoted with
their source: **96.85** is the NAS run's own per-child metric (`trainings_get`, the NAS page), the number the
selection rule was applied to because no Model Evaluation existed at selection time; **0.963** is what Model
Evaluation reported afterwards for the same model and split. They are two evaluators, not one number rounded
twice; the results below use Model Evaluation throughout. Test mAP@50 **0.974**, test mAP@50-95 **0.952**
(per class, test: bed 1.000 / 0.971, lying **1.000 / 0.950**, sitting 0.928 / 0.928, standing 0.967 / 0.958).
Valid-optimal threshold **0.75** (valid: precision 0.972, recall 0.971), applied to test.

| Test split at 0.75 | Precision | Recall | F1 |
|---|---|---|---|
| overall | 0.933 | 0.967 | 0.944 |
| bed | 1.000 | 1.000 | 1.000 |
| **lying** | **1.000** | **1.000** | 1.000 |
| sitting | 0.733 | 1.000 | 0.846 |
| standing | 1.000 | 0.868 | 0.930 |

Confusion matrix, test split, read at 0.70 and at 0.80 (the two are identical; rows: ground truth, columns:
predicted):

| | bed | lying | sitting | standing | missed |
|---|---|---|---|---|---|
| **bed** (16) | 16 | 0 | 0 | 0 | 0 |
| **lying** (24) | 0 | **24** | 0 | 0 | 0 |
| **sitting** (11) | 0 | 0 | 11 | 0 | 0 |
| **standing** (38) | 0 | 0 | 4 | 33 | 1 |
| **false positives** | 0 | 0 | 0 | 0 | |

| Condition | Bar | Measured | Verdict |
|---|---|---|---|
| **F1** lying separable | precision >= 0.90 and recall >= 0.90 | 1.000 / 1.000 | **PASS** |
| **F2** lying not confused with upright | <= 5 % of 24 lying instances | 0 of 24 (0 %) | **PASS** |
| **F3** bed (report only) | none | bed as lying 0, lying as bed 0 | reported |

The model's errors are all on the upright side: 4 standing instances read as sitting and 1 missed. The platform's
own recommendations for this evaluation say the same (missed standing 2, standing confused with sitting 3, at its
0.85 threshold) and flag class imbalance: sitting has 11 test instances. `lying` is 1.000 / 1.000 on the test
split at every threshold from 0.11 to 0.87 in the committed
[per-threshold sweep](2026-09-28-roboflow/arm-A-00ba18-sweep.json), so F1 does not hinge on the 0.75.

**Device-sized candidate.** The platform's `recommended` child, `...--e65db0`, is the fast end of the frontier
(2.93 ms on AI1, 1.16 ms on T4, against 18.2 / 4.66 ms for `00ba18`) at a lower box accuracy: test mAP@50 0.971,
mAP@50-95 0.841, `lying` 1.000 / 0.866. At each class's own optimal threshold on test it reads lying 1.000 /
1.000, sitting 0.786 / 1.000, standing 1.000 / 0.947 (report only; not the plan's threshold rule, not scored). The
four stock RF-DETR baselines trained inside the same run scored valid mAP@50-95 93.3 to 96.0 at 7.6 to 25.1 ms on
AI1; the search's gain over them is in latency (82.9 % by the platform's figure), not accuracy.

## 4. Arms B and C, report only (F4)

Both trained `rfdetr-nano` from the COCO checkpoint with default hyperparameters. Threshold rule as declared.

| Arm | Model | Test mAP@50 | Test mAP@50-95 | Valid-optimal threshold | Test at that threshold, overall P / R / F1 | Down class on test, P / R |
|---|---|---|---|---|---|---|
| B, URFD | `fall-detection-urfd-vzgtq-1-rfdetr-nano-t2` | 0.993 | 0.901 | 0.39 | 0.952 / 0.986 / 0.969 | `fall` 0.931 / 0.982 |
| C, lying3 | `lying3-vcr6i-1-rfdetr-nano-t1` | 0.926 | 0.658 | 0.44 | 0.837 / 0.933 / 0.882 | `lying` 0.910 / 0.950 |

| B, URFD, test at 0.40 | fall | not_fall | missed |
|---|---|---|---|
| **fall** (110) | 108 | 0 | 2 |
| **not_fall** (109) | 0 | 108 | 1 |
| **false positives** | 8 | 3 | |

| C, lying3, test at 0.40 | lying | sit | standing | missed |
|---|---|---|---|---|
| **lying** (299) | 286 | 2 | 0 | 11 |
| **sit** (176) | 2 | 163 | 0 | 11 |
| **standing** (305) | 0 | 0 | 295 | 10 |
| **false positives** | 30 | 54 | 63 | |

Read the way F2 reads arm A (not scored): arm B swaps `fall` and `not_fall` **0** times in 110; arm C swaps
`lying` with an upright pose **4** times in 299 (1.3 %). Arm C's errors are misses (11 of 299 lying) and false
positives on background, and its weakest class is `sit` (precision 0.771), which is the pose behind the 09-26
false WARN on the LIDAR side. The gap between arm A and arm C is not scored; it says that the harder, larger
dataset with a nano model lands around 0.91 / 0.95 on the down class. No bar applies to arms B and C.

## 5. Not run: F5, device fit

Nothing was measured on the Jetson today. To run F5 the way [section 5 of the stock RF-DETR results](2026-09-27-rfdetr-results.md#5-cost-on-the-device-c4-report-only)
did: start the Inference container with the hardened command of [DR-11](../DECISIONS.md#dr-11) plus
`-e TRITON_CACHE_DIR=/tmp/triton-cache` ([PR #3072](https://github.com/roboflow/inference/pull/3072)), request
`fall_detection-johan-jsi2o-1-rfdetr-nas-t1--e65db0` and `...--00ba18` by model id on the two 1280x720 test
frames used for C4, 3 warm-ups then the serial median and p90, `MemAvailable` before and minimum during, `/scan`
counts before and after, with the LIDAR stack running and the cameras stopped. The frames stay on the device; the
server posts nothing but the model pull. Until then, the round trip carried forward for D0 is still the stock
models' 108 to 127 ms.

## 6. What this changes

- **D1** ([DR-13](../DECISIONS.md#dr-13)) now has one measured "no" (box shape, C3), one unscored run (the v1
  keypoint run, invalid under its own rule, awaiting the [v2 rescore](2026-09-28-rfdetr-keypoints-plan-v2.md)) and
  one measured "yes on public data" (this plan). The room-frame measurement is the next step for the class split;
  which of the two runs first is Jeremy's call.
- **D0** ([DR-14](../DECISIONS.md#dr-14)) gets its camera half as a runnable artefact: the
  [time-on-floor Workflow](../../tools/roboflow/README.md) takes any of these models by id and returns seconds since
  a down-pose track entered a floor polygon, the unit the LIDAR detector's stillness clock uses. Its clock is
  specified and validated structurally; it has not been run on video.
- **The bed.** `bed` labels the furniture, and the model never confused it with a lying person on 16 + 24
  instances. A person lying **in** the bed is a different question that this label set cannot ask; the Workflow's
  floor polygon is the mechanism that keeps in-bed lying out of the count until a dataset asks it.

## 7. What is not known

- **Whether train and test share near-duplicate frames.** The three datasets are video-derived and their splits
  are the uploaders'; nothing here checked for frames of the same sequence on both sides of the split, which is
  the most likely way a 24-of-24 could be inflated. Until that is checked, the arm-A numbers are an upper bound.
- **One run per arm.** Arm A was trained once; its seed variance is unmeasured (arm B's accidental duplicate moved
  test mAP@50 by 0.006). One dataset, 73 test images, 89 instances, 11 of them sitting.
- **Two evaluators.** The selection rule ran on the NAS run's own valid metric; the scoring ran on Model
  Evaluation. Whether the rule would have picked the same child under Model Evaluation's numbers is not known,
  because only two children were evaluated.
- **Thresholds.** Per-class precision and recall are at the rule's exact thresholds; the confusion matrices are at
  the nearest stored 0.1 step. For arm A the two neighbours (0.70, 0.80) agree, which bounds F2; for arms B and
  C the matrix at 0.40 stands in for 0.39 and 0.44.
- **The device-sized candidate is not scored** under the plan's rule; its per-class numbers are at each class's
  own optimal threshold, as the platform reports them.
- **F5 was not run.** Nothing in this document is a Jetson latency or memory figure; the NAS latencies are the
  platform's AI1 and T4 targets.
- **Licences and provenance** are as the Universe uploaders state them; the URFD copy's CC BY 4.0 was not checked
  against the original dataset's terms.
- **Nothing here is a room result.** No frame from the test room was involved, by design.

## Reproduce

Forks, versions, training ids, model ids and evaluation ids are in the three extracts. Training and evaluation
ran on Roboflow (Core plan, 2026-09-28); the NAS run is at
`app.roboflow.com/jeremy-gracey/fall_detection-johan-jsi2o/nas-runs/1`, the evaluations at
`.../fall_detection-johan-jsi2o/evaluation/1`, `.../fall-detection-urfd-vzgtq/evaluation/1` and
`.../lying3-vcr6i/evaluation/1` (workspace login). Trained models are under Roboflow's Platform Model License
(PML-1.0, as shown on the run); the datasets are CC BY 4.0 by their Universe authors:

```
@misc{fall_detection-johan_dataset, title={Fall_Detection Dataset}, author={FYP}, year={2026}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/fyp-isiva/fall_detection-johan}}}
@misc{fall-detection-urfd_dataset, title={Fall detection URFD Dataset}, author={Me}, year={2026}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/me-15gfc/fall-detection-urfd}}}
@misc{lying3_dataset, title={lying3 Dataset}, author={poscoproject}, year={2022}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/poscoproject/lying3}}}
```

The URFD frames derive from the UR Fall Detection Dataset (Kwolek and Kepski, 2014); the Universe copy carries a
CC BY 4.0 label from its uploader, which this repository relays without verifying against the original terms.
