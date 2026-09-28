# Label sidecars

One JSON per bag, in the schema of [plan v4, Appendix C](../../plans/replay-harness-plan-v4.md#appendix-c--golden-json-labels-sidecar-diff-rules):
`bag`, `time_base` (`header_stamp_rel`: seconds from the first `/scan` stamp), `driver_inverted`,
`sensor_height_cm`, `segments` (`t0`, `t1` half-open, `kind` one of `lying`, `empty`, `walking`, `note`), and either
an `empty` segment or `"no_empty_segment": true` with the reason.
`replay_detector.py replay <bag> --compare-labels <file>` validates the file (`validate_labels`), prints the event
counts by level inside every segment, and for `empty` segments the R5 tiers (HARD: 0 WARN; SOFT: 0 events) with
a mechanism breakdown. It prints no R4 line and no time-to-WARN: whether a `lying` segment "yields WARN" is read
off its counts by whoever scores it.

## Which bags are which

Plan v4 **step 9** scores R4 (WARN in the lying segments of `fall-test-lowered-064632`) and R5 (0 WARN in the
empty segments) against label files for the two **09-25** bags, `fall-test-lowered-064632` and
`fall-test-062816` ([plan v4, requirements and step 9](../../plans/replay-harness-plan-v4.md)). Those two files
do not exist yet; their bounds come from `replay --per-second` on the bags plus the field notes, and the bags
have no camera timing and no ground truth beyond that ([plan v4, risks](../../plans/replay-harness-plan-v4.md)).
**The config flip ([DR-06](../../DECISIONS.md#dr-06)) waits on them, and nothing in this directory changes that.**

The two files here are for the **09-27** bags, which step 9 does not name:

| File | Bag | Source of the bounds | Status |
|---|---|---|---|
| [`floor-trials-1.json`](floor-trials-1.json) | `floor-trials-1` (09-27, 537.2 s) | camera-timed segment table, [floor trials](../2026-09-27-floor-mount-grid.md) | **draft**: `confirmed_by` is null until Jeremy checks the bounds against the bag |
| [`grid-stations-1.json`](grid-stations-1.json) | `grid-stations-1` (09-27, 131.6 s) | station windows, [grid walk](../2026-09-27-floor-mount-grid.md) | **draft**, as above |
| `fall-test-lowered-064632.json`, `fall-test-062816.json` | 09-25 | not written | **step 9's files, to do** on the Mac or OMEN with the bags |

They exist so that any future bar on the 09-27 bags can be scored with the same tool. That bar has **not** been
declared, and it cannot be step 9's "WARN in every lying segment": the fixed-config replay of `floor-trials-1` is
already published ([2026-09-27](../2026-09-27-fixed-config-replay.md)), and it shows A, C, D and E reaching WARN
while B and F, the two end-on lie-downs the floor LIDAR cannot see, raise nothing under any config. A plan that
uses these files must be written with that outcome stated as already seen, and must say which lying segments it
expects WARN from. Nothing here is a verdict.

## Rules that hold for every file here

- **An `empty` segment is a claim that nobody was in the room.** Neither 09-27 bag has one: the subject stayed in
  the room, so both carry `no_empty_segment: true` and `--compare-labels` reports R5 as `N/A` for them, not PASS.
  R5 needs a bag recorded with the room empty after the settle window (`t0 >= 7.0 s`); none has been published.
- **`walking` covers standing still.** The schema has no `standing` kind; a station where the subject stood is
  labelled `walking` with the note saying so. The expectation on such a segment is the same (no WARN).
- **The get-ups between lie-downs are not labelled.** An event there falls in no segment and is not counted by
  `--compare-labels`; the replay's own timeline still shows it.
- **A draft is not ground truth.** `--compare-labels` accepts a draft (the schema does not know the difference),
  so any verdict reported against a file with `confirmed_by: null` must say so. Confirming means: open the bag
  and the frames, check every `t0` and `t1` to the second, write the date and name into `confirmed_by`, and commit.
