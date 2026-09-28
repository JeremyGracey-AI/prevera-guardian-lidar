# RF-DETR keypoint preview on the floor-trials-1 B and F frames: rescore plan v2 (written before any rescoring)

Written 2026-09-28. This is the rescore plan the [status note](2026-09-27-rfdetr-keypoints-status.md) said a
rescore needs. It changes exactly one thing in [plan v1](2026-09-27-rfdetr-keypoints-plan.md): how an instance is
recognised as a person. Every other definition, both bars and all three conditions are v1's, unchanged, and are not
restated here.

**Why a v2.** Plan v1 assumed the preview model labels its person class `class_id` 0. It does not: all 4,882 instances
of the 2026-09-28 run came back `class_id` 1 with `class_name` `'person'`, so validity check 9(c) failed and K1 to K3
were not scored, as v1 said they would not be. The mismatch is an index convention (rf-detr #1150), not a model
fault, and v1's check 9(c) existed to catch it.

**Already seen, stated plainly.** Before this plan was written, the following had been looked at from the invalid
run, and nothing else: the validity extract ([`keypoints-validity.json`](2026-09-27-rfdetr/keypoints-validity.json)),
which holds the class counts and the report-only table of frames with any instance at fused score >= 0.3 (A/c920
12/12, A/brio 12/12, B/c920 33/33, B/brio 32/33, F/c920 30/30, F/brio 0/30, W/c920 30/30, W/brio 23/30); the
figure-only overlay [`keypoints-B-F.jpg`](2026-09-27-rfdetr/keypoints-B-F.jpg), drawn under a rule that is not the
plan's; and the schema-check overlays on disk, which nobody scored. No keypoint coordinate, angle or per-keypoint
confidence from the run has been read into any number. The per-frame counts above make one thing predictable: F/brio
cannot reach the K1 bar on the Brio, so K1 for F will be decided by the C920, as definition 7 already allows. No bar
moves because of it.

## The one change

**Definition 2 (scored instance), cutoff clause**, v1: "it is the person class (`class_id` 0)". v2: **it is the
person class, meaning its `class_name` is `'person'`**. The rest of definition 2 (fused score >= 0.3, most confident
keypoints, tie to the higher score, the same instance feeds K1 to K3) is unchanged.

**Definition 9(c) (run validity)**, v1: "every returned instance has `class_id` 0 and `class_name` `'person'`". v2:

- (c1) every returned instance has `class_name` `'person'`;
- (c2) every returned instance carries the **same** `class_id`, whatever integer it is, and that integer is recorded;
- (c3) the package is asked, before scoring, which id it maps to `'person'` for this model
  (`rfdetr_keypoints.py probe-classes`, which loads the model in the run's environment and records every
  id-to-name mapping it exposes, without running inference). If the package exposes a mapping, the id it gives for
  `'person'` must equal the id from (c2). If it exposes none, the probe records that, and (c3) is satisfied by
  (c1) and (c2) alone; the results say which of the two cases held.

Checks (a) and (b) are v1's, re-read from the same results file. If any of (a), (b), (c1), (c2) or (c3) fails, the
rescore is reported invalid and K1 to K3 are not scored, exactly as v1 says.

## What is rescored, and how

- **No new inference.** The rescore reads the results file the 2026-09-28 run wrote
  (`keypoints-results.json`, 210 frames, checkpoint md5 `6de511943ee85a547d4c5cb527daf0eb`, `rfdetr` 1.11.0). The
  frames stay on the Mac; nothing is re-run and nothing leaves the disk.
- **Order of operations, as v1.** Validity first (definition 9, v2 form), then the definition-1 schema check on the
  two plan-named frames, then K1 to K3. The schema check is repeated under the v2 instance rule because under v1's
  rule it selected no instance; its frozen mapping is decided on those two frames and nowhere else.
- **Commands.** `python3 rfdetr_keypoints.py probe-classes` (run environment, writes
  `keypoints-class-probe.json`), then `python3 rfdetr_keypoints.py check --plan v2`, then
  `python3 rfdetr_keypoints.py score --plan v2` (both standard library only; they write
  `keypoints-schema-check-v2.json` and `keypoints-score-v2.json` and leave the v1 files untouched).
- **Default stays v1.** Without `--plan v2` the scorer behaves byte-for-byte as it did, so the invalid v1 verdict
  can be reproduced at any time.

## Conditions

K1, K2 and K3 are [plan v1's](2026-09-27-rfdetr-keypoints-plan.md#pre-declared-conditions), with the bars
B >= 30/33, F >= 27/30, A median torso angle >= 60 deg and W median <= 30 deg on the Brio, and K3 report only.
Every failure is reported as a finding with the frames behind it; no threshold is changed after results.

**What a verdict means.** K1 and K2 both passing means keypoints are a measured live option for D1
([DR-13](../DECISIONS.md#dr-13)), on these 210 frames of one subject in one room. Either failing means keypoints
join box shape as a measured no on this data, and D1 turns to the fine-tuned class split
([2026-09-28 fine-tune plan](2026-09-28-roboflow-finetune-plan.md)) or a different measurement. K3 says nothing
about D1 either way.

## Amendments (dated; written before any rescore was run)

**2026-09-28, later the same day, from the branch review, before `probe-classes` has been run on the Mac.**

1. **(c3), what "the mapping the package exposes" means.** rfdetr 1.11.0 exposes `RFDETR.class_names` as a plain
   0-indexed list of names, and the class ids `predict()` emits are **not** that list's positions for this model:
   `predict()` builds its id-to-name table from `class_names` together with `args.num_classes` and
   `args.num_keypoints_per_class` (`rfdetr/detr.py`, the `_is_legacy_bgfirst_keypoint` branch: slot 0 is background,
   slot 1 is `class_names[0]`), and for COCO-pretrained detectors from `rfdetr.assets.coco_classes.COCO_CLASSES`
   (`rfdetr.util` was removed in 1.9.0). The probe therefore reproduces that rule from the same inputs
   (`package_class_mapping` in `rfdetr_keypoints.py`) and records the rule it took, its inputs and the mapping; any
   explicit id-to-name dict the package exposes is recorded beside it. A list position is never read as an id. The
   plan's (c3) test is unchanged: the id that rule gives for `'person'` must equal the id from (c2).
2. **(c3), the run's environment.** The probe loads the run's checkpoint from `RF_HOME` and stops if its md5 is not
   `6de511943ee85a547d4c5cb527daf0eb`, the same rule as `run`; it records the rfdetr version. (c3) fails if the
   probe did not verify the md5, if its rfdetr version differs from the one in the results file, or if the package
   exposes a mapping with no `'person'` in it. A package that exposes no mapping at all still leaves (c3) to (c1)
   and (c2), as written.
3. **Corrections to the text above.** `check` is not standard-library only: it draws the schema-check overlays
   with Pillow, as v1 did. "Changes exactly one thing" means one rule (how an instance is recognised as a person),
   which touches definition 2 and definition 9(c) and adds the probe; no bar and no other definition moves.

Nothing from the invalid run has been looked at since the "Already seen" section was written.
