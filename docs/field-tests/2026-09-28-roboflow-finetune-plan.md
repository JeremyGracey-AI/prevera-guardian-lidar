# Fine-tuned RF-DETR on public fall datasets — pre-declared evaluation (written before any result)

**Question.** Detection condition C3 failed: on the counter camera, a stock COCO RF-DETR box's aspect ratio does
not separate a lying person from a standing one (median width/height 0.78 to 0.87 in the lying segments B, D and E;
[results, C3](2026-09-27-rfdetr-results.md)). The pre-declared consequence was keypoints, and the first keypoint run
was invalid under its own rule ([status](2026-09-27-rfdetr-keypoints-status.md)). This plan tests a third option for
**D1** ([DR-13](../DECISIONS.md#dr-13)) that the earlier plans did not name: a detector **fine-tuned to predict the
pose as a class** (`lying` against `standing` and `sitting`), instead of reading the pose off a person box or off
keypoints. It is measured on public data only. No frame from the test room leaves the Mac or the Jetson; the room
frames are a separate, later plan.

**Data.** Three public datasets from Roboflow Universe, forked unchanged into the project workspace on 2026-09-28. All
three are licensed CC BY 4.0 by their authors on Universe; the citations are in the results document.

| Arm | Source (Universe) | Images | Classes (annotations) | Splits as forked |
|---|---|---|---|---|
| **A, primary** | `fyp-isiva/fall_detection-johan` | 736 | bed 133 · standing 366 · lying 238 · sitting 131 | train 518 · valid 145 · test 73 |
| B, comparison | `me-15gfc/fall-detection-urfd` (frames of the UR Fall Detection benchmark) | 2,204 | fall 1,096 · not_fall 1,108 (a third class `\` has 0 annotations and is ignored) | train 1,549 · valid 437 · test 218 |
| C, comparison | `poscoproject/lying3` | 5,323 | standing 2,990 · lying 2,918 · sit 1,693 | as forked: train 3,724 · valid 1,593 · **test 6**; rebalanced to 70/20/10 before versioning because six test images cannot score anything |

Arm A is primary because it is the only one with a room, a bed and all three poses in the label set: the bed is the
false-alarm object this repository already names ([README, limitations](../../README.md#limitations)), and
`sitting` is the pose the 09-26 false WARN came from. Arms B and C are context: they say whether the same recipe holds
on other people, rooms and cameras, and nothing more.

**Versioning.** One dataset version per arm: auto-orient, resize to 640 × 640 (stretch), no offline augmentation
(the trainer's online augmentation is left at its defaults). Splits are the datasets' own, except arm C as noted.

**Models.** Trained on Roboflow from the public COCO checkpoint, default hyperparameters, no recipe edits. Arm A:
RF-DETR neural architecture search (`rfdetr-nas-parent`) when the workspace plan allows it, which returns a frontier
of RF-DETR sizes; the arm-A model scored below is the frontier child with the **highest mAP@50-95 on the valid
split**, chosen by that rule and nothing else, and a Nano-class child is reported beside it as the device-sized
candidate. If NAS is refused by the plan, arm A trains `rfdetr-medium` and `rfdetr-nano` as two named runs and the
medium run is the scored model. Arms B and C: `rfdetr-nano`, one run each. Every training id, model id and dataset
version id is recorded in the results document.

**Scoring.** Roboflow Model Evaluation on the **test** split of each arm's own dataset, at the confidence threshold
the evaluation reports as optimal for the **valid** split (the threshold is taken from valid, applied to test, and
not tuned on test). Per-class precision and recall and the confusion matrix are read from the evaluation as it
reports them; nothing is recomputed.

**Pass conditions (declared 2026-09-28 before any training starts):**

1. **F1, lying is separable (arm A, test split):** class `lying` reaches precision **>= 0.90** and recall
   **>= 0.90**.
2. **F2, lying is not confused with upright (arm A, test split):** in the confusion matrix at the threshold above,
   ground-truth `lying` predicted as `standing` or `sitting`, plus ground-truth `standing` or `sitting` predicted as
   `lying`, together number **<= 5 %** of the ground-truth `lying` instances. Misses (`lying` predicted as nothing)
   count against F1, not F2.
3. **F3, bed (arm A, report only):** the `bed` ↔ `lying` cells of the same matrix, reported with no bar. Nothing here
   tests a person in a bed: `bed` labels the furniture.
4. **F4, other data (arms B and C, report only):** mAP@50 and per-class precision and recall on each arm's own test
   split, no bar. A large gap between arm A and arms B and C is reported as a finding about the recipe, not scored.
5. **F5, device fit (report only, may be deferred):** the arm-A device-sized candidate served by the Roboflow Inference
   container on the Jetson (localhost, active learning and telemetry off, the container command of
   [DR-11](../DECISIONS.md#dr-11)), median serial latency next to the running LIDAR stack, measured the way
   [section 5 of the RF-DETR results](2026-09-27-rfdetr-results.md) measured the stock models. No bar. If it is not
   run before the results are published, the results document says so.

**What a verdict means.** F1 and F2 both passing means a fine-tuned class split is a live option for D1 alongside
keypoints, on public data; it does not mean the model works in the test room, which only a room-frame plan can
show, and it does not touch D0. Either failing means the class split joins box shape as a measured no, and keypoints
stay the next measurement. Every failure is reported as a finding with the confusion cells behind it; no threshold
is changed after results.

**Already seen.** Before this plan was written, the only things seen from these datasets were their Universe
overview pages (class lists, image counts, licences, thumbnails) and the class and split counts returned by the fork.
No image and no model output from any of the three had been looked at.
