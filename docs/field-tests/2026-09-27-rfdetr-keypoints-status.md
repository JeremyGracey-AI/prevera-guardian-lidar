# RF-DETR keypoint preview on floor-trials-1: status (run invalid under its own rule, not scored)

Companion to the pre-declared plan [`2026-09-27-rfdetr-keypoints-plan.md`](2026-09-27-rfdetr-keypoints-plan.md)
(committed as `2bab653` before any keypoint inference). This is a status note, not a results document: the run
failed one of the plan's own validity checks, so the plan's conditions K1 to K3 were **not scored**. Every value below
is copied from [`2026-09-27-rfdetr/keypoints-validity.json`](2026-09-27-rfdetr/keypoints-validity.json), a
path-scrubbed extract of the scorer's output (`tools/bag_analysis/rfdetr_keypoints.py score`). The raw per-frame
results and the frames themselves are field data and are not published.

## What ran

| Item | Value |
|---|---|
| Frames | 210, the plan's selection (A 24, B 66, F 60, W 60 files) |
| Model | `rfdetr.RFDETRKeypointPreview`, `rfdetr` 1.11.0, `supervision` 0.30.5, constructed with `device="cpu"` |
| Call | `model.predict(PIL.Image.open(f).convert('RGB'), threshold=0.1)` |
| Device | the Mac, CPU (not the Jetson; no device-latency claim is made) |
| When | 2026-09-28 00:44:31 to 00:45:35 UTC |
| Egress | frames read from local disk only; no frame sent anywhere; no Roboflow API key used (runner's own record) |

## Validity (plan definition 9), checked before any scoring

| Check | Result |
|---|---|
| (a) checkpoint md5 = `6de511943ee85a547d4c5cb527daf0eb` | **pass** |
| (b) no "loaded only partially" warning at load | **pass** |
| (c) every returned instance has `class_id` 0 and `class_name` `'person'` | **fail**: 4,882 instances, every one `class_id` 1 with `class_name` `'person'`; none has `class_id` 0 |

The plan says: "If any of the three fails, the run is reported as invalid and K1-K3 are not scored." The scorer
printed `RUN INVALID (definition 9); K1-K3 not scored`. The plan's scored-instance rule (definition 2) requires
`class_id` 0, so it selects nothing on any frame, and the keypoint-schema check (definition 1) could not be read on
either of its two named frames ("no selected frame has a scored instance").

## What this does and does not show

- It shows that the plan's assumption about this model's person class id was wrong: the preview model labels
  its person class `1`, not `0`. Check 9(c) existed to catch exactly this kind of mismatch (the plan cites
  rf-detr issue #1150), and it did.
- It does **not** show whether keypoints separate lying from standing. Nothing in the plan was scored, and no
  informal score under `class_id` 1 is reported here, because that would be choosing a rule after seeing the output.
- The figure [`2026-09-27-rfdetr/keypoints-B-F.jpg`](2026-09-27-rfdetr/keypoints-B-F.jpg) is **figure only**. It is
  drawn under a figure-only instance rule (`class_id` 1, fused score >= 0.3, most confident keypoints) that is not the
  plan's, and its keypoint names are the assumed COCO-17 order, which the schema check never verified. The rule and
  the caveats are printed on the figure itself (`tools/bag_analysis/rfdetr_keypoint_figure.py`).

## Seen so far (report-only items the plan lists; not conditions)

The scorer emits the plan's report-only items even for an invalid run. The one that bears on the next plan is the
count of frames with any instance at fused score >= 0.3 (every instance counted is `class_id` 1):

| Segment / camera | Frames | With an instance at >= 0.3 |
|---|---|---|
| A / c920 | 12 | 12 |
| A / brio | 12 | 12 |
| B / c920 | 33 | 33 |
| B / brio | 33 | 32 |
| F / c920 | 30 | 30 |
| F / brio | 30 | 0 |
| W / c920 | 30 | 30 |
| W / brio | 30 | 23 |

CPU wall time around `model.predict` on the Mac: median 0.14 s per frame after the first (2.16 s). Not a device
latency.

## Next

A rescore needs **its own pre-declared plan**, written and committed before any scoring, that fixes the person-class
rule (for example: the class whose name is `'person'`, confirmed from the package before scoring) and states plainly
that the counts in the table above were already seen. Until then, decision **D1** (boxes vs keypoints) stays open:
box shape failed as the detection plan predicted ([results, C3](2026-09-27-rfdetr-results.md)), and keypoints are
the planned next measurement, not a measured answer. See [`docs/DECISIONS.md`](../DECISIONS.md).
