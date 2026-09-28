#!/usr/bin/env python3
"""Score the pre-declared RF-DETR evaluation on the floor-trials-1 frames.

Plan (declared and committed before any result, commit 73ec3f6):
    docs/field-tests/2026-09-27-rfdetr-eval-plan.md

Usage:
    python3 score_rfdetr.py [FRAMES_DIR] [--lidar MODEL=BEFORE/AFTER ...] [--json]

FRAMES_DIR holds results-<model>.json written by rf_eval.py (default: the Mac copy
~/src/local/prevera-frames/floor-trials-1; field data, not in this repo). Read-only; stdout; stdlib only.

Everything is recomputed from each file's raw frames[].persons[] boxes, not from the
runner's summary.per_segment; the runner's numbers are then diffed against ours and any
mismatch is printed (the scorer is an independent check, not a re-print).

Definitions, applied exactly as the plan states them (thresholds are the plan's, not tuned):
  * A frame "detects a person" when it has >= 1 person box with confidence >= 0.4 (the
    declared threshold is re-applied here; boxes it drops are counted and reported).
  * Frames are grouped by the manifest `segment` and `camera` fields, not the `lying` flag.
  * ">= 90 %" is compared in exact integers: 10 * hits >= 9 * n (B: 30/33, F: 27/30, W: 81/90).
  * Best box = the highest-confidence person box; aspect = raw width / height (pixels),
    not the runner's 2-decimal best_aspect_wh.

  C1  Coverage of the LIDAR blind spot: for each of B and F, rate = max over {c920, brio} of
      hits/n; PASS when that camera clears 90 %. (The plan's "on at least one camera" could
      also be read as one camera for both B and F; the table shows both cameras so either
      reading can be checked.)
      Failing frames: every B/F frame with no person box, tagged with the camera and whether
      it changed the verdict (a miss on a camera that is carried by the other one does not).
  C2  Detection when nobody is down: W on c920, hits/n >= 90 %.
      Failing frames: every W/c920 frame with no person box.
  C3  Shape separates lying from standing (c920 only): median best-box aspect w/h over the
      frames of the segment that HAVE a person box (no-box frames have no aspect, so they are
      excluded from the median but counted and listed). Strict: every lying segment A-F
      > 1.0, and W < 1.0. statistics.median is used, so an even count takes the mean of the
      two middle values.
      Per-frame failure (the pass bar is on a median, so a per-frame rule has to be stated):
      a frame fails when its best-box aspect is on the wrong side of 1.0 (<= 1.0 in A-F,
      >= 1.0 in W) or it has no person box. These are listed for segments whose median fails;
      wrong-side counts are reported for every segment. The plan pre-declares the meaning of
      a C3 fail: box shape alone cannot carry D1 (docs/DECISIONS.md) and keypoints are needed.
  C4  Fits on the device: report only (no pass bar). Latency and memory come from the results
      summary (written by rf_eval.py on the Jetson); median server_time_s is computed from frames.
      server_time_s is the server's own response `time` field, which in Inference 1.7.2 spans
      request decode + image decode + resize + forward pass + postprocess
      (inference/core/models/base.py), so it is server processing, not the forward pass alone.
      LIDAR /scan counts are NOT in the results files: they come from guardian-status.sh run by
      the runner before and after each model, and are passed in with --lidar (they bracket the
      run; they are not sampled during it).
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

CONF = 0.4
LYING = ["A", "B", "C", "D", "E", "F"]
SEGMENTS = LYING + ["W"]
CAMERAS = ["c920", "brio"]
MODEL_ORDER = ["rfdetr-nano", "rfdetr-small", "rfdetr-base", "rfdetr-medium", "rfdetr-large"]
DEFAULT_DIR = Path.home() / "src/local/prevera-frames/floor-trials-1"


def at_least_90(hits, n):
    return n > 0 and 10 * hits >= 9 * n


def pct(hits, n):
    return f"{100.0 * hits / n:.1f}%" if n else "n/a"


def load(path):
    data = json.loads(path.read_text())
    frames = data["frames"]
    dropped = 0
    groups = defaultdict(list)
    for f in frames:
        boxes = [p for p in f["persons"] if p["confidence"] >= CONF]
        dropped += len(f["persons"]) - len(boxes)
        best = max(boxes, key=lambda p: p["confidence"]) if boxes else None
        groups[(f["segment"], f["camera"])].append({
            "file": f["file"],
            "t_s": f["t_s"],
            "hit": best is not None,
            "aspect": (best["width"] / best["height"]) if best else None,
            "server_time_s": f.get("server_time_s"),
        })
    for g in groups.values():
        g.sort(key=lambda r: r["t_s"])
    return data["summary"], groups, dropped, len(frames)


def score(name, summary, groups):
    out = {"model": name, "cells": {}, "c1": {}, "c3": {}, "failing": [], "crosscheck": []}

    for seg in SEGMENTS:
        for cam in CAMERAS:
            rows = groups.get((seg, cam), [])
            hits = sum(r["hit"] for r in rows)
            aspects = [r["aspect"] for r in rows if r["aspect"] is not None]
            med = statistics.median(aspects) if aspects else None
            out["cells"][(seg, cam)] = {"hits": hits, "n": len(rows), "median_aspect": med}
            ref = summary.get("per_segment", {}).get(f"{seg}/{cam}")
            if ref:
                if ref["frames"] != len(rows) or (len(rows) and abs(ref["person_rate"] - hits / len(rows)) > 0.006):
                    out["crosscheck"].append(f"{seg}/{cam} rate: runner {ref['person_rate']} ({ref['frames']} frames) vs scorer {hits}/{len(rows)}")
                if med is not None and ref.get("median_aspect_wh") is not None and abs(ref["median_aspect_wh"] - med) > 0.02:
                    out["crosscheck"].append(f"{seg}/{cam} median aspect: runner {ref['median_aspect_wh']} vs scorer {med:.3f}")

    # C1 - B and F, max over cameras
    c1_all = True
    for seg in ["B", "F"]:
        per_cam = {cam: out["cells"][(seg, cam)] for cam in CAMERAS}
        best_cam = max(CAMERAS, key=lambda c: (per_cam[c]["hits"] / per_cam[c]["n"]) if per_cam[c]["n"] else -1)
        passing = [c for c in CAMERAS if at_least_90(per_cam[c]["hits"], per_cam[c]["n"])]
        ok = bool(passing)
        c1_all &= ok
        out["c1"][seg] = {"best_cam": best_cam, "hits": per_cam[best_cam]["hits"], "n": per_cam[best_cam]["n"],
                          "pass": ok, "per_cam": per_cam, "carried_by": passing}
        for cam in CAMERAS:
            misses = [r["file"] for r in groups.get((seg, cam), []) if not r["hit"]]
            if not misses:
                continue
            if ok and cam not in passing:
                tag = f"verdict PASS via {'/'.join(passing)}; this camera alone {per_cam[cam]['hits']}/{per_cam[cam]['n']} < 90%"
            elif ok:
                tag = "verdict PASS, miss within the 10% allowance"
            else:
                tag = "verdict FAIL"
            out["failing"] += [f"c1 {seg}/{cam} no person ({tag}): {f}" for f in misses]
    out["c1_pass"] = c1_all

    # C2 - W on c920
    w = out["cells"][("W", "c920")]
    out["c2"] = {"hits": w["hits"], "n": w["n"], "pass": at_least_90(w["hits"], w["n"])}
    tag = "verdict PASS, miss within the 10% allowance" if out["c2"]["pass"] else "verdict FAIL"
    out["failing"] += [f"c2 W/c920 no person ({tag}): {r['file']}" for r in groups.get(("W", "c920"), []) if not r["hit"]]

    # C3 - c920 median best-box aspect
    c3_all = True
    for seg in SEGMENTS:
        rows = groups.get((seg, "c920"), [])
        med = out["cells"][(seg, "c920")]["median_aspect"]
        lying = seg in LYING
        ok = med is not None and (med > 1.0 if lying else med < 1.0)
        wrong = [r for r in rows if r["aspect"] is not None and (r["aspect"] <= 1.0 if lying else r["aspect"] >= 1.0)]
        nobox = [r for r in rows if r["aspect"] is None]
        c3_all &= ok
        out["c3"][seg] = {"median": med, "n_box": len(rows) - len(nobox), "n": len(rows), "pass": ok,
                          "wrong_side": len(wrong), "no_box": len(nobox)}
        if not ok:
            want = "> 1.0" if lying else "< 1.0"
            medtxt = f"{med:.3f}" if med is not None else "none"
            out["failing"] += [f"c3 {seg}/c920 median {medtxt} (want {want}); frame aspect {r['aspect']:.2f}: {r['file']}" for r in wrong]
            out["failing"] += [f"c3 {seg}/c920 median {medtxt} (want {want}); no person box: {r['file']}" for r in nobox]
    out["c3_pass"] = c3_all

    # C4 - report only
    st = [r["server_time_s"] for g in groups.values() for r in g if r["server_time_s"] is not None]
    out["c4"] = {k: summary.get(k) for k in ["latency_ms_median", "latency_ms_p90", "fps_serial", "first_call_s",
                                             "mem_avail_idle_mb", "mem_avail_min_mb", "gpu_pct_max", "sampler"]}
    out["c4"]["server_ms_median"] = round(1000 * statistics.median(st), 1) if st else None
    return out


def verdict(ok):
    return "PASS" if ok else "FAIL"


def fmt_med(m):
    return f"{m:.2f}" if m is not None else "n/a"


def render(results, lidar, notes):
    names = [r["model"] for r in results]
    L = []
    L.append("### Person-detection rate (frames with >= 1 person box at conf >= 0.4), hits/n")
    L.append("")
    L.append("| segment / camera | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    for seg in SEGMENTS:
        for cam in CAMERAS:
            cells = [f"{r['cells'][(seg, cam)]['hits']}/{r['cells'][(seg, cam)]['n']} ({pct(r['cells'][(seg, cam)]['hits'], r['cells'][(seg, cam)]['n'])})" for r in results]
            L.append(f"| {seg}/{cam} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("### Median best-box aspect w/h (frames with a box only); C3 is judged on c920")
    L.append("")
    L.append("| segment | want (c920) | " + " | ".join(f"{n} c920 (wrong-side, no-box)" for n in names) + " | " + " | ".join(f"{n} brio" for n in names) + " |")
    L.append("|---|---|" + "---|" * (2 * len(names)))
    for seg in SEGMENTS:
        want = "> 1.0" if seg in LYING else "< 1.0"
        c9 = []
        for r in results:
            c = r["c3"][seg]
            c9.append(f"{fmt_med(c['median'])} {verdict(c['pass'])} ({c['wrong_side']}, {c['no_box']})")
        br = [fmt_med(r["cells"][(seg, "brio")]["median_aspect"]) for r in results]
        L.append(f"| {seg} | {want} | " + " | ".join(c9) + " | " + " | ".join(br) + " |")
    L.append("")
    L.append("### Condition verdicts (plan thresholds, unchanged)")
    L.append("")
    L.append("| condition | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    for seg in ["B", "F"]:
        row = []
        for r in results:
            c = r["c1"][seg]
            pc = c["per_cam"]
            row.append(f"{verdict(c['pass'])}: c920 {pc['c920']['hits']}/{pc['c920']['n']}, brio {pc['brio']['hits']}/{pc['brio']['n']}")
        L.append(f"| C1 {seg} >= 90% on one camera | " + " | ".join(row) + " |")
    L.append("| **C1 overall** | " + " | ".join(f"**{verdict(r['c1_pass'])}**" for r in results) + " |")
    L.append("| **C2 W/c920 >= 90%** | " + " | ".join(f"**{verdict(r['c2']['pass'])}** {r['c2']['hits']}/{r['c2']['n']}" for r in results) + " |")
    failing3 = lambda r: ", ".join(s for s in SEGMENTS if not r["c3"][s]["pass"]) or "none"
    L.append("| **C3 c920 aspect (A-F > 1, W < 1)** | " + " | ".join(f"**{verdict(r['c3_pass'])}** (failing: {failing3(r)})" for r in results) + " |")
    L.append("| C4 (report only) | " + " | ".join("see below" for _ in results) + " |")
    L.append("")
    L.append("### C4 - cost next to the LIDAR stack (report only, no pass bar)")
    L.append("")
    L.append("| model | latency median / p90 ms (client) | server processing median ms (decode+pre+forward+post) | fps serial | first call s | MemAvailable idle -> min MB | GPU max % | /scan msgs per ~5 s before -> after (want ~50) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        c = r["c4"]
        lid = lidar.get(r["model"], "not provided")
        L.append(f"| {r['model']} | {c['latency_ms_median']} / {c['latency_ms_p90']} | {c['server_ms_median']} | {c['fps_serial']} | {c['first_call_s']} | {c['mem_avail_idle_mb']} -> {c['mem_avail_min_mb']} | {c['gpu_pct_max']} ({c['sampler']}) | {lid} |")
    L.append("")
    for n in notes:
        L.append(f"- {n}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frames_dir", nargs="?", default=str(DEFAULT_DIR))
    ap.add_argument("--lidar", action="append", default=[], metavar="MODEL=BEFORE/AFTER",
                    help="guardian-status.sh /scan counts from the runner, e.g. rfdetr-nano=39/43")
    ap.add_argument("--json", action="store_true", help="also print a JSON block with every failing frame")
    a = ap.parse_args()

    lidar = {}
    for item in a.lidar:
        model, _, val = item.partition("=")
        lidar[model] = val.replace("/", " -> ")

    paths = sorted(Path(a.frames_dir).glob("results-*.json"),
                   key=lambda p: (MODEL_ORDER.index(p.stem[8:]) if p.stem[8:] in MODEL_ORDER else 99, p.name))
    if not paths:
        sys.exit(f"no results-*.json in {a.frames_dir}")

    results, notes = [], []
    for p in paths:
        summary, groups, dropped, nframes = load(p)
        name = summary.get("model", p.stem[8:])
        r = score(name, summary, groups)
        results.append(r)
        notes.append(f"{name}: {nframes} frames, {dropped} boxes dropped by re-applying conf >= {CONF}; "
                     f"runner per_segment cross-check: {'agrees' if not r['crosscheck'] else '; '.join(r['crosscheck'])}")
        if name not in lidar:
            notes.append(f"{name}: LIDAR /scan counts not provided to the scorer (not in the results file).")

    print(render(results, lidar, notes))
    print()
    print("### Failing frames (conditions 1-3)")
    for r in results:
        print(f"\n{r['model']}: {len(r['failing'])}")
        for f in r["failing"]:
            print(f"  {f}")
    if a.json:
        print()
        print(json.dumps([{"model": r["model"], "c1_pass": r["c1_pass"], "c2_pass": r["c2"]["pass"],
                           "c3_pass": r["c3_pass"], "c4": r["c4"], "failing_frames": r["failing"]} for r in results], indent=1))


if __name__ == "__main__":
    main()
