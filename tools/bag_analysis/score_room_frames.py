#!/usr/bin/env python3
"""Score the pre-declared room-frame evaluation of the fine-tuned RF-DETR on the floor-trials-1 frames.

Plan (declared and committed before any result):
    docs/field-tests/2026-09-29-room-frames-plan.md

Usage:
    python3 score_room_frames.py RESULTS.json [--json]

RESULTS.json is written by jetson/rf_room_eval.py on the Jetson (field data, not in this repo until its
extract is committed). Read-only; stdout; stdlib only. Everything is recomputed from each frame's raw
`predictions`; the runner writes no rate and no verdict for this file to agree with.
Exit status: 0 when the run is valid (whatever the verdicts), 2 when it is not.

A run is VALID, and gets a verdict, only when all of this holds. Otherwise the scorer prints the reasons and
nothing else: no reading, no count of readings and no verdict. The file is reported and kept.
  * The summary names the declared model, the declared confidence, the loopback URL and server 1.7.2, and
    says the run is complete with 580 frames requested and 580 answered. Values are compared with their types.
  * The summary's manifest md5 and frame digest are the declared ones, and its digest of the rows is the
    digest of the rows in the file.
  * The rows are the manifest's 580 files, in the manifest's order, in the fourteen declared groups with
    their declared counts.
  * No row carries a request error.
  * Every prediction has a class name and a number for its confidence, and every class name is one of
    `bed`, `standing`, `sitting`, `lying`. Another name means the harness does not match the model.
These checks read the runner's own record of the run. They catch the wrong model, the wrong threshold, a
partial run and a file patched by hand; they cannot show who wrote a file.

Definitions, applied exactly as the plan states them (thresholds are the plan's, not tuned):
  * Pose classes are `standing`, `sitting` and `lying`, compared exactly as the model returns them. `bed`
    labels the furniture: it is counted and never read.
  * The declared confidence, 0.56, is re-applied here: a box under it is dropped whatever the server sent.
  * A frame READS the class of its highest-confidence pose box. No pose box: `none`. The top confidence shared
    by two DIFFERENT pose classes: `tie` (two boxes of one class sharing it read that class).
  * Frames are grouped by the manifest `segment` and `camera` fields, not the `lying` flag.
  * Percentages are compared in exact integers: ">= 80 %" is 5 * hits >= 4 * n (B: 27/33, F: 24/30);
    "<= 5 %" is 20 * hits <= n (W: 4/90).

  R1  The blind spot reads lying: at least one camera reads `lying` in >= 80 % of its B frames AND in >= 80 %
      of its F frames. The same camera has to carry both segments. The looser reading (a camera per segment),
      under which the 09-27 verdict was computed, is printed beside the verdict as `per_segment_reading` and
      is not the verdict. A `tie` is not a lying reading.
      Failing frames: every B and F frame that did not read lying, on both cameras.
  R2  Walking does not read lying: on the counter camera (c920), `lying` plus `tie` in <= 5 % of W frames.
      A `tie` counts as lying here, so a tie counts against the bar on both sides.
      Failing frames: every W/c920 frame that read lying or tie.
  Report only, no bar: every other segment and camera (A, C, D, E; W on the floor camera), with the full
  distribution of readings and the number of `bed` boxes per group.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

MODEL = "jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--e65db0"
CONF = 0.56
URL = "http://127.0.0.1:9001"
MANIFEST_MD5 = "9da67efcc98c6ffd2bbbeb4fb1d82d1d"
FRAMES_SHA256 = "a6d168682234a74af0a01c3c790baf1961e3795a4a0d060d7aa428d2b27d6cc7"  # frame bytes, manifest order
FILES_SHA256 = "34ff824c94479bcc64d8a9f7217c6497346c8ed22a04b62b4ac09cb70d43dfc0"   # file names, one per line
SERVER = "1.7.2"
POSES = ("standing", "sitting", "lying")
CLASSES = POSES + ("bed",)
READINGS = ("lying", "standing", "sitting", "none", "tie", "error")
CAMERAS = ["c920", "brio"]
EXPECTED = {"A": 35, "B": 33, "C": 34, "D": 35, "E": 33, "F": 30, "W": 90}  # frames per camera
SEGMENTS = list(EXPECTED)
FRAMES = 2 * sum(EXPECTED.values())


def at_least_80(hits, n):
    return n > 0 and 5 * hits >= 4 * n


def at_most_5(hits, n):
    return n > 0 and 20 * hits <= n


def pct(hits, n):
    return f"{100.0 * hits / n:.1f}%" if n else "n/a"


def well_formed(p):
    return isinstance(p.get("class"), str) and isinstance(p.get("confidence"), (int, float)) \
        and not isinstance(p.get("confidence"), bool)


def reading(predictions, conf=CONF):
    """What one frame reads: a pose class, `none` or `tie`."""
    poses = [p for p in predictions if well_formed(p) and p["class"] in POSES and p["confidence"] >= conf]
    if not poses:
        return "none"
    top = max(p["confidence"] for p in poses)
    classes = {p["class"] for p in poses if p["confidence"] == top}
    return classes.pop() if len(classes) == 1 else "tie"


def names_digest(frames):
    return hashlib.sha256("\n".join(str(f.get("file")) for f in frames).encode()).hexdigest()


def rows_digest(frames):
    """As jetson/rf_room_eval.py computes it: sha256 of the rows as canonical JSON."""
    return hashlib.sha256(json.dumps(frames, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def frame_defects(frames):
    """Why these rows are not the declared 580 frames answered once each, as a list of sentences."""
    out, seen, counts, other, malformed, errors = [], set(), {}, {}, [], []
    for f in frames:
        key = (f.get("segment"), f.get("camera"))
        counts[key] = counts.get(key, 0) + 1
        if f.get("file") in seen:
            out.append(f"file twice: {f.get('file')}")
        seen.add(f.get("file"))
        if f.get("error"):
            errors.append(f.get("file"))
        for p in f.get("predictions", []):
            if not well_formed(p):
                malformed.append(f.get("file"))
            elif p["class"] not in CLASSES:
                other[p["class"]] = other.get(p["class"], 0) + 1
    if len(frames) != FRAMES:
        out.append(f"{len(frames)} rows, the manifest has {FRAMES}")
    if names_digest(frames) != FILES_SHA256:
        out.append("the rows are not the manifest's files in the manifest's order")
    for key in sorted(counts, key=str):
        seg, cam = key
        if seg not in EXPECTED or cam not in CAMERAS:
            out.append(f"unexpected group {seg}/{cam}: {counts[key]} rows")
    for seg, n in EXPECTED.items():
        for cam in CAMERAS:
            if counts.get((seg, cam), 0) != n:
                out.append(f"{seg}/{cam} has {counts.get((seg, cam), 0)} rows, declared {n}")
    if errors:
        out.append(f"{len(errors)} request errors, first: {errors[0]}")
    if malformed:
        out.append(f"{len(malformed)} predictions without a class or a confidence, first in: {malformed[0]}")
    if other:
        out.append("class names outside the declared four: "
                   + ", ".join(f"{k!r} x{v}" for k, v in sorted(other.items())))
    return out


def summary_defects(summary, frames):
    """Why this file is not the declared run, read from what the runner recorded about itself."""
    want = {"model": MODEL, "confidence": CONF, "url": URL, "server_version": SERVER, "complete": True,
            "frames_requested": FRAMES, "frames_answered": FRAMES, "errors": 0,
            "manifest_md5": MANIFEST_MD5, "frames_sha256": FRAMES_SHA256}
    missing = object()
    out = [f"summary {k} is {summary.get(k, 'missing')!r}, declared {v!r}" for k, v in want.items()
           if type(summary.get(k, missing)) is not type(v) or summary.get(k, missing) != v]
    if summary.get("rows_sha256") != rows_digest(frames):
        out.append("summary rows_sha256 is not the digest of the rows in the file")
    return out


def score(frames, summary=None, conf=CONF):
    """Cells for every group, and R1 and R2 when the run is valid. `summary=None` checks the frames only."""
    cells = {f"{seg}/{cam}": {"n": 0, **{r: 0 for r in READINGS}, "bed_boxes": 0}
             for seg in SEGMENTS for cam in CAMERAS}
    read = []
    for f in sorted(frames, key=lambda f: (str(f.get("segment")), str(f.get("camera")), f.get("t_s", 0))):
        r = "error" if f.get("error") else reading(f.get("predictions", []), conf)
        cell = cells.setdefault(f"{f.get('segment')}/{f.get('camera')}",
                                {"n": 0, **{k: 0 for k in READINGS}, "bed_boxes": 0})
        cell["n"] += 1
        cell[r] += 1
        if not f.get("error"):
            cell["bed_boxes"] += sum(1 for p in f.get("predictions", [])
                                     if well_formed(p) and p["class"] == "bed" and p["confidence"] >= conf)
        read.append((f.get("segment"), f.get("camera"), f.get("file"), r))

    invalid = frame_defects(frames) + (summary_defects(summary, frames) if summary is not None else [])
    out = {"confidence": conf, "frames": len(read), "valid": not invalid, "invalid": invalid, "cells": cells,
           "r1": None, "r2": None, "failing": []}
    if invalid:                                        # rows and errors per group, and no reading
        out["cells"] = {k: {"n": c["n"], "error": c["error"]} for k, c in cells.items()}
        return out

    def clears(seg, cam):
        return at_least_80(cells[f"{seg}/{cam}"]["lying"], cells[f"{seg}/{cam}"]["n"])

    carried_by = [cam for cam in CAMERAS if clears("B", cam) and clears("F", cam)]
    out["r1"] = {"pass": bool(carried_by), "carried_by": carried_by,
                 "per_segment_reading": all(any(clears(seg, cam) for cam in CAMERAS) for seg in ("B", "F")),
                 "per_cam": {cam: {seg: {"lying": cells[f"{seg}/{cam}"]["lying"], "n": cells[f"{seg}/{cam}"]["n"],
                                         "clears": clears(seg, cam)} for seg in ("B", "F")} for cam in CAMERAS}}
    w = cells["W/c920"]
    out["r2"] = {"pass": at_most_5(w["lying"] + w["tie"], w["n"]), "lying": w["lying"], "tie": w["tie"], "n": w["n"]}
    out["failing"] = [f"r1 {seg}/{cam} read {r}: {name}" for seg, cam, name, r in read
                      if seg in ("B", "F") and r != "lying"]
    out["failing"] += [f"r2 {seg}/{cam} read {r}: {name}" for seg, cam, name, r in read
                       if (seg, cam) == ("W", "c920") and r in ("lying", "tie")]
    return out


def report(summary, s):
    lines = [f"model {summary.get('model')} · confidence sent {summary.get('confidence')} · scored at {CONF}",
             f"rows {s['frames']} · answered {summary.get('frames_answered')} · errors {summary.get('errors')}"
             f" · started {summary.get('started_utc')}", ""]
    if not s["valid"]:
        lines.append("INVALID RUN: no verdict on R1 or R2, and no reading is shown.")
        lines += [f"  - {why}" for why in s["invalid"]]
        return lines
    lines.append(f"{'group':<9}{'n':>4}{'lying':>7}{'rate':>8}  " + "".join(f"{r:>10}" for r in READINGS[1:])
                 + f"{'bed boxes':>11}")
    for key in sorted(s["cells"]):
        c = s["cells"][key]
        lines.append(f"{key:<9}{c['n']:>4}{c['lying']:>7}{pct(c['lying'], c['n']):>8}  "
                     + "".join(f"{c[r]:>10}" for r in READINGS[1:]) + f"{c['bed_boxes']:>11}")
    lines.append("")
    r1, r2 = s["r1"], s["r2"]
    lines.append(f"R1 blind spot reads lying (one camera, B and F each >= 80 %): {'PASS' if r1['pass'] else 'FAIL'}"
                 f" · carried by {', '.join(r1['carried_by']) or 'no camera'}"
                 f" · a camera per segment would {'clear' if r1['per_segment_reading'] else 'not clear'} it")
    lines.append(f"R2 walking does not read lying (W on c920 <= 5 %): {'PASS' if r2['pass'] else 'FAIL'}"
                 f" · {r2['lying']} lying + {r2['tie']} tie of {r2['n']} ({pct(r2['lying'] + r2['tie'], r2['n'])})")
    if s["failing"]:
        lines.append(f"\nframes behind the verdicts ({len(s['failing'])}):")
        lines += [f"  {line}" for line in s["failing"]]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        data = json.loads(a.results.read_text())
        summary, frames = data["summary"], data["frames"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"INVALID RUN: no verdict on R1 or R2, and no reading is shown.\n"
              f"  - the file cannot be read as a run ({type(e).__name__})")
        sys.exit(2)
    s = score(frames, summary)
    print(json.dumps({"summary": summary, "score": s}, indent=1) if a.json else "\n".join(report(summary, s)))
    sys.exit(0 if s["valid"] else 2)


if __name__ == "__main__":
    main()
