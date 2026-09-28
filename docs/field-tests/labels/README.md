# Label sidecars for plan v4 step 9

One JSON per bag, in the schema of [plan v4, Appendix C](../../plans/replay-harness-plan-v4.md#appendix-c--golden-json-labels-sidecar-diff-rules):
`bag`, `time_base` (`header_stamp_rel`: seconds from the first `/scan` stamp), `driver_inverted`,
`sensor_height_cm`, `segments` (`t0`, `t1` half-open, `kind` one of `lying`, `empty`, `walking`, `note`), and either
an `empty` segment or `"no_empty_segment": true` with the reason. `replay_detector.py replay <bag> --compare-labels
<file>` validates the file (`validate_labels`) and prints the step-9 R4 and R5 verdicts per segment.

Step 9 scores **R4** (WARN in every `lying` segment) and **R5** (0 WARN in every `empty` segment, two tiers) against
these files. Until 2026-09-28 they did not exist, which is what held the config flip
([DR-06](../../DECISIONS.md#dr-06)) behind "label files that do not exist yet".

| File | Bag | Source of the bounds | Status |
|---|---|---|---|
| [`floor-trials-1.json`](floor-trials-1.json) | `floor-trials-1` (09-27, 537.2 s) | camera-timed segment table, [floor trials](../2026-09-27-floor-mount-grid.md) | **draft**: `confirmed_by` is null until Jeremy checks the bounds against the bag |
| [`grid-stations-1.json`](grid-stations-1.json) | `grid-stations-1` (09-27, 131.6 s) | station windows, [grid walk](../2026-09-27-floor-mount-grid.md) | **draft**, as above |
| `fall-test-lowered-064632.json` | 09-25, lowered mount | not written: the 09-25 bags have no camera timing and no ground truth ([plan v4, risks](../../plans/replay-harness-plan-v4.md)); bounds come from `replay --per-second` on the bag plus the field notes | to do, on the Mac or OMEN with the bag |
| `fall-test-062816.json` | 09-25, original mount | as above | to do |

Rules that hold for every file here:

- **An `empty` segment is a claim that nobody was in the room.** Neither 09-27 bag has one: the subject stayed in
  the room, so both carry `no_empty_segment: true` and R5 reports `N/A` for them, not PASS. R5 needs a bag recorded
  with the room empty after the settle window (`t0 >= 7.0 s`); none has been published.
- **`walking` covers standing still.** The schema has no `standing` kind; a station where the subject stood is
  labelled `walking` with the note saying so. The bar on such a segment is the same (no WARN expected).
- **The get-ups between lie-downs are not labelled.** A WARN there is neither a hit nor a false alarm under step 9
  and is reported separately by the replay.
- **A draft is not ground truth.** `--compare-labels` accepts a draft (the schema does not know the difference),
  so a step-9 verdict reported against a file with `confirmed_by: null` must say so. Confirming means: open the bag
  and the frames, check every `t0` and `t1` to the second, write the date and name into `confirmed_by`, and commit.
