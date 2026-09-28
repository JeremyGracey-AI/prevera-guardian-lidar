#!/usr/bin/env python3
"""RF-DETR keypoint preview on the floor-trials-1 A/B/F/W frames: runner, schema check and scorer.

Plan (declared and committed before any result, commit 2bab653):
    docs/field-tests/2026-09-27-rfdetr-keypoints-plan.md

Three subcommands, run in this order:

    run    Loads rfdetr (needs the kp-venv), selects the 210 frames from manifest.json, checks the
           checkpoint md5, runs RFDETRKeypointPreview(device="cpu") with model.predict(img, threshold=0.1)
           on every frame, and writes the raw results JSON. A second, report-only pass with
           postprocess_trace_alpha=0.0 is run only if that value is confirmed to reach the postprocessor.
    check  Definition 1 schema check on the two plan-named frames (first selected W/brio and first selected
           A/c920 frame with a scored instance, time order). Numeric ordering check (see below) plus labelled
           overlay PNGs written next to the frames for a human read. Writes keypoints-schema-check.json.
    score  Standard library only. Refuses to score unless run validity (definition 9) holds and the schema
           check passed. Computes K1, K2, K3 and the report-only items; prints a report and writes
           keypoints-score.json.

Usage (from any directory; the frames and results files are field data and are not in this repo):
    export RF_HOME=<venv>/models
    <venv>/bin/python rfdetr_keypoints.py run   [--frames-dir DIR]
    <venv>/bin/python rfdetr_keypoints.py check [--frames-dir DIR]
    python3 rfdetr_keypoints.py score [--frames-dir DIR]

Rescore under plan v2 (docs/field-tests/2026-09-28-rfdetr-keypoints-plan-v2.md), which changes only how an
instance is recognised as a person (by `class_name`, not `class_id` 0) and adds a package probe to validity:
    <venv>/bin/python rfdetr_keypoints.py probe-classes [--frames-dir DIR]   # writes keypoints-class-probe.json
    python3 rfdetr_keypoints.py check --plan v2 [--frames-dir DIR]           # keypoints-schema-check-v2.json
    python3 rfdetr_keypoints.py score --plan v2 [--frames-dir DIR]           # keypoints-score-v2.json
Without `--plan v2` every command behaves exactly as before (plan v1), so the invalid v1 verdict stays reproducible.

Why the schema check is numeric and not a visual read by the agent: viewing a frame (or an overlay drawn on
it) through a model tool would send frame pixels to a hosted API, which the run's rules forbid. The overlays
are written to disk for a human to confirm. The numeric check covers the three gross faults the plan lists
(head points not on the head, ankles not at the feet, shoulders and hips swapped):
  * W/brio (standing): mean image y of the confident points of each group must increase
    head < shoulders < hips < [knees, if any is confident] < ankles.
  * A/c920 (lying across): project each group's mean onto the unit vector head-mean -> ankle-mean; the
    order along it must be head < shoulders < hips < [knees] < ankles, and |ankle-mean - head-mean| >= 50 px.
  * A required group (head, shoulders, hips, ankles) with no confident point on the named frame makes the
    check "cannot be read": scoring stops, as the plan says. The check does not move on to another frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- fixed by the plan (do not tune)
PLAN_FILE = "docs/field-tests/2026-09-27-rfdetr-keypoints-plan.md"
PLAN_COMMIT = "2bab6532e45bac5e0a3580645ad4ac61929f1b87"
PREDICT_THRESHOLD = 0.1          # model.predict(img, threshold=0.1)
SCORE_CUTOFF = 0.3               # def 2: fused detection_confidence >= 0.3
KP_CONF = 0.5                    # def 3
KP_MIN_COUNT = 9                 # def 4: at least 9 of 17
TORSO_MIN_PX = 5.0               # def 5
K2_A_MIN_DEG = 60.0
K2_W_MAX_DEG = 30.0
CHECK_MIN_AXIS_PX = 50.0         # schema check, A/c920 head->ankle distance floor (fixed before the run)
EXPECTED_MD5 = "6de511943ee85a547d4c5cb527daf0eb"
CKPT_NAME = "rf-detr-keypoint-preview-xlarge.pth"
CAMERAS = ["c920", "brio"]
SEGMENTS = ["A", "B", "F", "W"]
EXPECTED_FILES = {"A": 24, "B": 66, "F": 60, "W": 60}

COCO17 = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
GROUPS = {
    "head": [0, 1, 2, 3, 4],
    "shoulders": [5, 6],
    "hips": [11, 12],
    "knees": [13, 14],
    "ankles": [15, 16],
}
SKELETON = [(15, 13), (13, 11), (16, 14), (14, 12), (11, 12), (5, 11), (6, 12), (5, 6), (5, 7), (6, 8),
            (7, 9), (8, 10), (1, 2), (0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6)]

DEFAULT_DIR = Path.home() / "src/local/prevera-frames/floor-trials-1"
RESULTS_NAME = "keypoints-results.json"
PLAN_RESULTS_NAME = "results-rfdetr-keypoint-preview.json"   # the plan's name; symlinked to RESULTS_NAME
CHECK_NAME = "keypoints-schema-check.json"
SCORE_NAME = "keypoints-score.json"

# ---------------------------------------------------------------- plan v2 (rescore; the person rule by name)
PLAN_V2_FILE = "docs/field-tests/2026-09-28-rfdetr-keypoints-plan-v2.md"
PLAN_V2_COMMIT = "2a505e544e0b29d3873602bd3ddd5166f29672e5"
PROBE_NAME = "keypoints-class-probe.json"
CHECK_NAME_V2 = "keypoints-schema-check-v2.json"
SCORE_NAME_V2 = "keypoints-score-v2.json"
PERSON_NAME = "person"
PLAN = "v1"   # set once by main() from --plan; every rule below reads it, so the default is byte-for-byte v1


def plan_files() -> tuple[str, str, str, str]:
    """(plan file, plan commit, schema-check file, score file) for the plan in force."""
    if PLAN == "v2":
        return PLAN_V2_FILE, PLAN_V2_COMMIT, CHECK_NAME_V2, SCORE_NAME_V2
    return PLAN_FILE, PLAN_COMMIT, CHECK_NAME, SCORE_NAME


def is_person(inst) -> bool:
    """Definition 2, cutoff clause. v1: `class_id` 0. v2: `class_name` 'person' (plan v2, the one change)."""
    if PLAN == "v2":
        return inst.get("class_name") == PERSON_NAME
    return inst["class_id"] == 0


# ---------------------------------------------------------------- frame selection (plan "Data")
def select_frames(frames_dir: Path) -> list[dict]:
    manifest = json.loads((frames_dir / "manifest.json").read_text())
    first_t: dict[tuple[str, str], int] = {}
    for e in manifest:
        key = (e["segment"], e["camera"])
        first_t[key] = min(first_t.get(key, e["t_s"]), e["t_s"])
    # "first t_s of the segment": the same on both cameras here; asserted so a mismatch cannot pass silently
    for seg in SEGMENTS:
        assert first_t[(seg, "c920")] == first_t[(seg, "brio")], f"first t_s differs by camera in {seg}"
    chosen = []
    for e in manifest:
        seg = e["segment"]
        if seg not in SEGMENTS or e["camera"] not in CAMERAS:
            continue
        if seg in ("A", "W") and (e["t_s"] - first_t[(seg, e["camera"])]) % 3 != 0:
            continue
        chosen.append(e)
    chosen.sort(key=lambda e: (SEGMENTS.index(e["segment"]), e["t_s"], CAMERAS.index(e["camera"])))
    counts = defaultdict(int)
    for e in chosen:
        counts[e["segment"]] += 1
    assert dict(counts) == EXPECTED_FILES, f"frame selection {dict(counts)} != plan {EXPECTED_FILES}"
    assert len(chosen) == 210
    # both cameras at every selected t_s
    by_seg_t = defaultdict(set)
    for e in chosen:
        by_seg_t[(e["segment"], e["t_s"])].add(e["camera"])
    assert all(v == set(CAMERAS) for v in by_seg_t.values()), "a selected t_s is missing a camera"
    for e in chosen:
        assert (frames_dir / e["file"]).is_file(), f"missing frame {e['file']}"
    return chosen


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- run
def _serialize_instances(kp, names) -> list[dict]:
    import numpy as np  # noqa: F401  (rfdetr env only)

    out = []
    n = 0 if kp is None or kp.xy is None else len(kp.xy)
    cov = kp.data.get("covariance") if n else None
    for i in range(n):
        xy = kp.xy[i]
        conf = kp.keypoint_confidence[i]
        inst = {
            "xyxy": [round(float(v), 1) for v in kp.data["xyxy"][i]],
            "detection_confidence": round(float(kp.detection_confidence[i]), 4),
            "class_id": int(kp.class_id[i]),
            "class_name": str(kp.data["class_name"][i]) if "class_name" in kp.data else None,
            "keypoints": [[names[j], round(float(xy[j][0]), 1), round(float(xy[j][1]), 1), round(float(conf[j]), 4)]
                          for j in range(len(xy))],
        }
        if cov is not None:
            c = cov[i]
            inst["covariance"] = [[[round(float(c[j][a][b]), 2) for b in range(2)] for a in range(2)]
                                  for j in range(len(c))]
            inst["cov_sqrt_trace_px"] = [round(math.sqrt(max(0.0, float(c[j][0][0]) + float(c[j][1][1]))), 2)
                                         for j in range(len(c))]
        else:
            inst["covariance"] = None
            inst["cov_sqrt_trace_px"] = None
        out.append(inst)
    return out


def _load_jsonl(path: Path) -> dict[str, dict]:
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["file"]] = rec
    return done


def _run_pass(model, frames, frames_dir, names, jsonl_path: Path, label: str) -> dict[str, dict]:
    from PIL import Image

    done = _load_jsonl(jsonl_path)
    with open(jsonl_path, "a") as fh:
        for i, e in enumerate(frames):
            if e["file"] in done:
                continue
            img = Image.open(frames_dir / e["file"]).convert("RGB")
            t0 = time.perf_counter()
            kp = model.predict(img, threshold=PREDICT_THRESHOLD)
            dt = time.perf_counter() - t0
            rec = {"file": e["file"], "predict_s": round(dt, 4), "order": i,
                   "image_size": list(img.size), "instances": _serialize_instances(kp, names)}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[e["file"]] = rec
            print(f"[{label}] {i + 1:3d}/{len(frames)} {e['file']} {dt:6.2f}s n={len(rec['instances'])}",
                  flush=True)
    return done


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def cmd_run(args) -> int:
    import logging
    import warnings

    frames_dir = args.frames_dir
    frames = select_frames(frames_dir)
    rf_home = os.environ.get("RF_HOME")
    if not rf_home:
        print("RF_HOME must be set (plan: <venv>/models)", file=sys.stderr)
        return 2
    ckpt = Path(rf_home) / CKPT_NAME
    if not ckpt.is_file():
        print(f"checkpoint not found at {ckpt}; download it first (plan URL) so the md5 is checked before use",
              file=sys.stderr)
        return 2
    md5 = md5sum(ckpt)
    size = ckpt.stat().st_size
    print(f"checkpoint {ckpt} size={size} md5={md5}")
    if md5 != EXPECTED_MD5:
        print(f"MD5 MISMATCH (expected {EXPECTED_MD5}); run stops", file=sys.stderr)
        return 3

    records: list[dict] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append({"logger": record.name, "level": record.levelname, "msg": record.getMessage()})

    cap = Capture(level=logging.DEBUG)
    logging.getLogger("rf-detr").addHandler(cap)
    logging.getLogger().addHandler(cap)

    import rfdetr  # noqa: F401
    import torch
    from importlib.metadata import version as pkg_version
    from rfdetr import RFDETRKeypointPreview

    with warnings.catch_warnings(record=True) as wlist:
        warnings.simplefilter("always")
        t0 = time.perf_counter()
        model = RFDETRKeypointPreview(device="cpu")
        load_s = time.perf_counter() - t0
    pywarn = [f"{w.category.__name__}: {w.message}" for w in wlist]
    construct_logs = list(records)
    partial = any("loaded only partially" in r["msg"] for r in construct_logs) or \
        any("loaded only partially" in w for w in pywarn)

    trace_alpha_pass1 = getattr(model.model.postprocess, "trace_alpha", None)
    if model.model_config.pretrain_weights != str(ckpt):
        print(f"model loaded weights from {model.model_config.pretrain_weights}, not {ckpt}", file=sys.stderr)
        return 3

    # def 1: keypoint names from the package if it exposes a mapping; it does not for the pretrained preview
    names_source = "assumed COCO-17 (rfdetr 1.11.0 exposes no index-to-name mapping for the pretrained preview)"
    names = list(COCO17)
    for obj in (model, model.model, getattr(model.model, "args", None)):
        for attr in ("keypoint_names", "kpt_names"):
            v = getattr(obj, attr, None) if obj is not None else None
            if v and len(v) == 17:
                names_source = f"package attribute {type(obj).__name__}.{attr}"
                names = [str(x) for x in v]

    base = frames_dir / RESULTS_NAME
    p1 = base.with_suffix(".pass1.jsonl")
    p2 = base.with_suffix(".pass2-raw.jsonl")
    t_start = datetime.now(timezone.utc).isoformat()
    pass1 = _run_pass(model, frames, frames_dir, names, p1, "pass1 fused")
    run_logs = records[len(construct_logs):]

    # def 9 (c): every returned instance is class_id 0 / 'person'
    bad_class = [(f, i["class_id"], i["class_name"]) for f, r in pass1.items() for i in r["instances"]
                 if i["class_id"] != 0 or i["class_name"] != "person"]

    # report-only second pass with the raw object score, only if trace_alpha=0.0 reaches the postprocessor
    pass2_meta = {"run": False}
    pass2 = {}
    if not args.skip_raw_pass:
        del model
        model2 = RFDETRKeypointPreview(device="cpu", postprocess_trace_alpha=0.0)
        ta2 = getattr(model2.model.postprocess, "trace_alpha", None)
        pass2_meta = {"constructed_with": "RFDETRKeypointPreview(device='cpu', postprocess_trace_alpha=0.0)",
                      "postprocess.trace_alpha_observed": ta2, "run": ta2 == 0.0}
        if ta2 == 0.0:
            pass2 = _run_pass(model2, frames, frames_dir, names, p2, "pass2 raw")
    t_end = datetime.now(timezone.utc).isoformat()

    out_frames = []
    for e in frames:
        r1 = pass1[e["file"]]
        fr = {"file": e["file"], "segment": e["segment"], "camera": e["camera"], "t_s": e["t_s"],
              "pose": e["pose"], "lidar": e["lidar"], "lying": e["lying"],
              "image_size": r1["image_size"], "predict_s": r1["predict_s"], "run_order": r1["order"],
              "instances": r1["instances"]}
        if e["file"] in pass2:
            r2 = pass2[e["file"]]
            raw = [{"xyxy": i["xyxy"], "raw_score": i["detection_confidence"], "class_id": i["class_id"]}
                   for i in r2["instances"]]
            for inst in fr["instances"]:
                best = max(raw, key=lambda r: _iou(r["xyxy"], inst["xyxy"]), default=None)
                if best is not None and _iou(best["xyxy"], inst["xyxy"]) >= 0.9:
                    inst["raw_score_trace_alpha_0"] = best["raw_score"]
                else:
                    inst["raw_score_trace_alpha_0"] = None
            fr["raw_pass"] = {"predict_s": r2["predict_s"], "instances": raw}
        out_frames.append(fr)

    meta = {
        "plan": PLAN_FILE, "plan_commit": PLAN_COMMIT,
        "started_utc": t_start, "finished_utc": t_end,
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "python": platform.python_version()},
        "packages": {"rfdetr": pkg_version("rfdetr"), "supervision": pkg_version("supervision"),
                     "torch": torch.__version__, "torchvision": pkg_version("torchvision"),
                     "transformers": pkg_version("transformers"), "pillow": pkg_version("pillow"),
                     "numpy": pkg_version("numpy")},
        "device": "cpu", "torch_num_threads": torch.get_num_threads(),
        "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
        "model": {"class": "rfdetr.RFDETRKeypointPreview", "size": "rfdetr-keypoint-preview",
                  "constructed_with": "RFDETRKeypointPreview(device='cpu')",
                  "resolution": 576, "load_s": round(load_s, 2),
                  "postprocess_trace_alpha_pass1": trace_alpha_pass1},
        "checkpoint": {"path": str(ckpt), "bytes": size, "md5": md5, "md5_expected": EXPECTED_MD5,
                       "md5_ok": md5 == EXPECTED_MD5},
        "predict_call": f"model.predict(PIL.Image.open(f).convert('RGB'), threshold={PREDICT_THRESHOLD})",
        "keypoint_names": names, "keypoint_names_source": names_source,
        "construct_log_records": construct_logs, "construct_python_warnings": pywarn,
        "run_log_records_warning_plus": [r for r in run_logs if r["level"] in ("WARNING", "ERROR", "CRITICAL")],
        "validity": {
            "a_md5_ok": md5 == EXPECTED_MD5,
            "b_no_partial_load_warning": not partial,
            "c_all_instances_person_class0": not bad_class,
            "c_violations": bad_class[:50], "c_violation_count": len(bad_class),
        },
        "raw_pass": pass2_meta,
        "frame_count": len(out_frames),
        "egress": "frames read from local disk only; no frame sent anywhere; no Roboflow API key used",
    }
    meta["validity"]["valid"] = all(meta["validity"][k] for k in
                                    ("a_md5_ok", "b_no_partial_load_warning", "c_all_instances_person_class0"))
    base.write_text(json.dumps({"meta": meta, "frames": out_frames}, indent=1))
    link = frames_dir / PLAN_RESULTS_NAME
    if not link.exists() and not link.is_symlink():
        link.symlink_to(RESULTS_NAME)
    print(f"wrote {base} ({len(out_frames)} frames); validity={meta['validity']}")
    return 0


# ---------------------------------------------------------------- shared scoring helpers (stdlib only)
def n_conf(inst) -> int:
    return sum(1 for k in inst["keypoints"] if k[3] >= KP_CONF)


def scored_instance(frame):
    """Def 2: the person class (`is_person`: v1 class_id 0, v2 class_name 'person') with fused
    detection_confidence >= 0.3; most confident keypoints, tie -> score."""
    cands = [i for i in frame["instances"] if is_person(i) and i["detection_confidence"] >= SCORE_CUTOFF]
    if not cands:
        return None
    return max(cands, key=lambda i: (n_conf(i), i["detection_confidence"]))


def group_mean(inst, idxs, need_all=False):
    pts = [(inst["keypoints"][j][1], inst["keypoints"][j][2]) for j in idxs if inst["keypoints"][j][3] >= KP_CONF]
    if not pts or (need_all and len(pts) != len(idxs)):
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def torso_angle(inst):
    """Def 5: angle of mid(shoulders)->mid(hips) from image vertical, folded to [0, 90]; None if not computable."""
    if inst is None:
        return None
    idx = GROUPS["shoulders"] + GROUPS["hips"]
    if any(inst["keypoints"][j][3] < KP_CONF for j in idx):
        return None
    k = inst["keypoints"]
    ms = ((k[5][1] + k[6][1]) / 2, (k[5][2] + k[6][2]) / 2)
    mh = ((k[11][1] + k[12][1]) / 2, (k[11][2] + k[12][2]) / 2)
    vx, vy = mh[0] - ms[0], mh[1] - ms[1]
    if math.hypot(vx, vy) < TORSO_MIN_PX:
        return None
    return math.degrees(math.atan2(abs(vx), abs(vy)))


def load_results(frames_dir: Path) -> dict:
    return json.loads((frames_dir / RESULTS_NAME).read_text())


# ---------------------------------------------------------------- plan v2 validity (definition 9, v2 form)
def _mapping_person_ids(mapping) -> list[int]:
    """Ids whose name is 'person' in an explicit mapping given as {id: name} or {name: id}. A bare list of names
    carries no ids (rfdetr's `class_names` is such a list, 0-indexed by position, and the ids `predict()` emits
    are NOT its positions for the keypoint preview), so a list yields nothing here."""
    ids: list[int] = []
    if isinstance(mapping, dict):
        for k, v in mapping.items():
            if isinstance(v, str) and v.lower() == PERSON_NAME and isinstance(k, int):
                ids.append(k)
            elif isinstance(k, str) and k.lower() == PERSON_NAME and isinstance(v, int):
                ids.append(v)
    return sorted(set(ids))


def package_class_mapping(class_names, num_classes=None, num_keypoints_per_class=None, coco_classes=None) -> dict:
    """The id-to-name mapping `rfdetr.detr.RFDETR.predict()` applies in rfdetr 1.11.0, reproduced from its inputs
    (plan v2, c3, amendment of 2026-09-28). Three rules, in the package's order:
      * coco-pretrained: `args.num_classes` > len(class_names) and class_names == the COCO name list -> the COCO
        category ids (1..90 with gaps) in order, from `rfdetr.assets.coco_classes.COCO_CLASSES`;
      * legacy-bg-first-keypoint: `args.num_keypoints_per_class` starts with a 0 slot (background) -> every slot
        with keypoints maps, in order, to class_names[0], class_names[1], ... (slot 1 -> class_names[0]);
      * zero-indexed: class_id i -> class_names[i].
    Returns {"rule", "mapping" ({id: name}), "person_ids", "inputs"}."""
    names = [str(n) for n in (class_names or [])]
    n = len(names)
    schema = list(num_keypoints_per_class or [])
    coco = dict(coco_classes or {})
    coco_names = [coco[k] for k in sorted(coco)] if coco else []
    if num_classes is not None and n and num_classes > n and coco_names and names == coco_names:
        rule = "coco-pretrained"
        mapping = {cid: names[i] for i, cid in enumerate(sorted(coco)) if i < n}
    elif schema and schema[0] == 0:
        rule = "legacy-bg-first-keypoint"
        foreground = [slot for slot, k in enumerate(schema) if k > 0]
        mapping = {slot: names[i] for i, slot in enumerate(foreground) if i < n}
    else:
        rule = "zero-indexed"
        mapping = dict(enumerate(names))
    return {"rule": rule, "mapping": mapping, "person_ids": _mapping_person_ids(mapping),
            "inputs": {"class_names": names, "num_classes": num_classes, "num_keypoints_per_class": schema,
                       "coco_classes_available": bool(coco)}}


def validity_v2(meta: dict, frames: list[dict], frames_dir: Path) -> dict:
    """Plan v2 definition 9: (a) and (b) as v1, re-read from the results file; (c1) every instance is named
    'person'; (c2) every instance carries one and the same class_id; (c3) the package probe, when it exposes a
    mapping, gives that same id for 'person'. Nothing here reads a keypoint."""
    v1 = meta["validity"]
    insts = [i for f in frames for i in f["instances"]]
    not_person = [(f["file"], i["class_id"], i["class_name"]) for f in frames for i in f["instances"]
                  if i.get("class_name") != PERSON_NAME]
    ids = sorted({i["class_id"] for i in insts})
    out = {
        "plan": PLAN_V2_FILE, "plan_commit": PLAN_V2_COMMIT,
        "a_md5_ok": bool(v1.get("a_md5_ok")),
        "b_no_partial_load_warning": bool(v1.get("b_no_partial_load_warning")),
        "instances": len(insts),
        "c1_all_instances_named_person": not not_person,
        "c1_violations": not_person[:50], "c1_violation_count": len(not_person),
        "c2_single_class_id": len(ids) == 1,
        "c2_class_ids_observed": ids,
        "c2_class_id": ids[0] if len(ids) == 1 else None,
    }
    probe_path = frames_dir / PROBE_NAME
    if not probe_path.exists():
        out.update(c3_probe_found=False, c3_package_mapping_exposed=None, c3_person_ids_from_package=None,
                   c3_ok=False, c3_reason=f"{PROBE_NAME} missing: run `probe-classes` in the run environment first")
    else:
        probe = json.loads(probe_path.read_text())
        mappings = [m for m in probe.get("mappings", []) if "error" not in m]
        exposed = [m for m in mappings if m.get("person_ids")]
        pkg_ids = sorted({pid for m in exposed for pid in m["person_ids"]})
        run_rfdetr = (meta.get("packages") or {}).get("rfdetr")
        out.update(c3_probe_found=True, c3_probe_utc=probe.get("probed_utc"),
                   c3_package_mapping_exposed=bool(mappings), c3_person_ids_from_package=pkg_ids,
                   c3_sources=[m.get("source") for m in exposed],
                   c3_probe_rfdetr=probe.get("rfdetr"), c3_run_rfdetr=run_rfdetr,
                   c3_probe_md5_ok=probe.get("md5_ok"))
        # the probe must have run in the run's environment: same rfdetr, same checkpoint (plan v2, c3)
        if probe.get("md5_ok") is not True:
            out.update(c3_ok=False, c3_reason="probe did not verify the run's checkpoint md5 (md5_ok is not true)")
        elif run_rfdetr is not None and probe.get("rfdetr") != run_rfdetr:
            out.update(c3_ok=False, c3_reason=f"probe environment differs: rfdetr {probe.get('rfdetr')!r} in the "
                                              f"probe, {run_rfdetr!r} in the run")
        elif not mappings:
            out.update(c3_ok=True, c3_reason="package exposes no id-to-name mapping; (c3) rests on (c1) and (c2)")
        elif not exposed:
            out.update(c3_ok=False, c3_reason="package exposes a mapping with no 'person' in it")
        elif len(pkg_ids) == 1 and out["c2_class_id"] == pkg_ids[0]:
            out.update(c3_ok=True, c3_reason=f"package maps 'person' to {pkg_ids[0]}, the id every instance carries")
        else:
            out.update(c3_ok=False, c3_reason=f"package person id(s) {pkg_ids} != observed {out['c2_class_id']}")
    out["valid"] = all(out[k] for k in ("a_md5_ok", "b_no_partial_load_warning", "c1_all_instances_named_person",
                                        "c2_single_class_id", "c3_ok"))
    return out


def cmd_probe_classes(args) -> int:
    """Plan v2 definition 9(c3), as amended 2026-09-28: ask the package, in the run's environment, which id it
    maps to 'person' for this model. Loads the model exactly as `run` did (RF_HOME checkpoint, md5 checked
    first), reads the inputs `RFDETR.predict()` builds its id-to-name mapping from (`class_names`,
    `args.num_classes`, `args.num_keypoints_per_class`, the COCO id table) and reproduces that mapping with
    `package_class_mapping`. Any explicit id-to-name dict the package exposes is recorded as well. No inference."""
    frames_dir = args.frames_dir
    rf_home = os.environ.get("RF_HOME")
    if not rf_home:
        print("RF_HOME must be set (plan: <venv>/models), the same as for `run`", file=sys.stderr)
        return 2
    ckpt = Path(rf_home) / CKPT_NAME
    if not ckpt.is_file():
        print(f"checkpoint not found at {ckpt}; the probe must load the run's checkpoint", file=sys.stderr)
        return 2
    md5 = md5sum(ckpt)
    if md5 != EXPECTED_MD5:
        print(f"MD5 MISMATCH (expected {EXPECTED_MD5}); probe stops", file=sys.stderr)
        return 3

    from importlib.metadata import version as pkg_version

    import rfdetr  # type: ignore
    from rfdetr import RFDETRKeypointPreview  # type: ignore

    coco_classes = None
    coco_error = None
    try:
        from rfdetr.assets import coco_classes as _cc  # type: ignore  (rfdetr.util was removed in 1.9.0)
        coco_classes = dict(getattr(_cc, "COCO_CLASSES", {}) or {})
    except Exception as e:  # noqa: BLE001
        coco_error = repr(e)

    model = RFDETRKeypointPreview(device="cpu")
    if model.model_config.pretrain_weights != str(ckpt):
        print(f"model loaded weights from {model.model_config.pretrain_weights}, not {ckpt}", file=sys.stderr)
        return 3
    inner = getattr(model, "model", None)
    margs = getattr(inner, "args", None)
    class_names = list(getattr(model, "class_names", None) or [])
    num_classes = getattr(margs, "num_classes", None)
    schema = list(getattr(margs, "num_keypoints_per_class", None) or [])
    reproduced = package_class_mapping(class_names, num_classes, schema, coco_classes)
    reproduced["mapping"] = {str(k): v for k, v in reproduced["mapping"].items()}
    reproduced["source"] = "rfdetr.detr.RFDETR.predict() id-to-name rule, reproduced from the model's inputs"
    mappings = [reproduced]

    # explicit id<->name dicts the package may expose (none known in 1.11.0; recorded if present)
    for name, obj in (("model", model), ("model.model", inner), ("model.model.args", margs),
                      ("model.model.config", getattr(inner, "config", None))):
        for attr in ("id2label", "class_map", "category_map", "label_map"):
            v = getattr(obj, attr, None) if obj is not None else None
            if isinstance(v, dict) and v:
                mappings.append({"source": f"{name}.{attr}", "rule": "explicit-dict",
                                 "mapping": {str(k): str(x) for k, x in list(v.items())[:100]},
                                 "person_ids": _mapping_person_ids(v)})
    probe = {"plan": PLAN_V2_FILE, "plan_commit": PLAN_V2_COMMIT, "probed_utc": datetime.now(timezone.utc).isoformat(),
             "rfdetr": getattr(rfdetr, "__version__", None) or pkg_version("rfdetr"),
             "python": platform.python_version(),
             "checkpoint": {"path": str(ckpt), "md5": md5, "md5_expected": EXPECTED_MD5},
             "md5_ok": md5 == EXPECTED_MD5,
             "constructed_with": "RFDETRKeypointPreview(device='cpu')", "inference_run": False,
             "coco_classes_error": coco_error,
             "mappings": mappings,
             "person_ids_exposed": sorted({pid for m in mappings for pid in m.get("person_ids", [])})}
    (frames_dir / PROBE_NAME).write_text(json.dumps(probe, indent=1))
    print(json.dumps({k: v for k, v in probe.items() if k != "mappings"}, indent=1))
    for m in mappings:
        print(f"  {m['source']}: rule={m.get('rule')} person_ids={m.get('person_ids')}")
    return 0


def ordered(frames, seg, cam):
    return sorted([f for f in frames if f["segment"] == seg and f["camera"] == cam], key=lambda f: f["t_s"])


# ---------------------------------------------------------------- check (def 1)
def _numeric_check(inst, mode: str) -> dict:
    means = {g: group_mean(inst, idx) for g, idx in GROUPS.items()}
    required = ["head", "shoulders", "hips", "ankles"]
    missing = [g for g in required if means[g] is None]
    res = {"group_means_px": {g: (None if m is None else [round(m[0], 1), round(m[1], 1)]) for g, m in means.items()},
           "confident_per_group": {g: sum(1 for j in idx if inst["keypoints"][j][3] >= KP_CONF)
                                   for g, idx in GROUPS.items()}}
    if missing:
        res.update(verdict="cannot be read", reason=f"no confident keypoint in required group(s) {missing}")
        return res
    order = ["head", "shoulders", "hips"] + (["knees"] if means["knees"] is not None else []) + ["ankles"]
    if mode == "vertical":
        vals = [means[g][1] for g in order]
        res["axis"] = "image y (down is +)"
    else:
        hx, hy = means["head"]
        ax, ay = means["ankles"]
        L = math.hypot(ax - hx, ay - hy)
        res["head_to_ankle_px"] = round(L, 1)
        if L < CHECK_MIN_AXIS_PX:
            res.update(verdict="cannot be read", reason=f"head-ankle distance {L:.1f} px < {CHECK_MIN_AXIS_PX}")
            return res
        ux, uy = (ax - hx) / L, (ay - hy) / L
        vals = [(means[g][0] - hx) * ux + (means[g][1] - hy) * uy for g in order]
        res["axis"] = "projection on unit vector head-mean -> ankle-mean"
    res["order_checked"] = order
    res["values"] = [round(v, 1) for v in vals]
    ok = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
    res["verdict"] = "pass" if ok else "fail"
    if not ok:
        res["reason"] = "group order along the body axis is not head < shoulders < hips < [knees] < ankles"
    return res


def _draw(frames_dir: Path, frame, inst, out_path: Path, blank: bool):
    from PIL import Image, ImageDraw

    if blank:
        img = Image.new("RGB", tuple(frame["image_size"]), (255, 255, 255))
    else:
        img = Image.open(frames_dir / frame["file"]).convert("RGB")
    d = ImageDraw.Draw(img)
    x1, y1, x2, y2 = inst["xyxy"]
    d.rectangle([x1, y1, x2, y2], outline=(0, 160, 255), width=2)
    k = inst["keypoints"]
    for a, b in SKELETON:
        if k[a][3] >= KP_CONF and k[b][3] >= KP_CONF:
            d.line([(k[a][1], k[a][2]), (k[b][1], k[b][2])], fill=(0, 200, 0), width=2)
    for j, (name, x, y, c) in enumerate(k):
        col = (220, 0, 0) if c >= KP_CONF else (150, 150, 150)
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
        d.text((x + 6, y - 6), f"{j}:{name} {c:.2f}", fill=col)
    d.text((10, 10), f"{frame['file']}  det={inst['detection_confidence']:.3f}  "
                     f"{'keypoints only, no frame pixels' if blank else 'overlay'}", fill=(0, 0, 0))
    img.save(out_path)


def cmd_check(args) -> int:
    frames_dir = args.frames_dir
    data = load_results(frames_dir)
    frames = data["frames"]
    plan_file, plan_commit, check_name, _ = plan_files()
    out_dir = frames_dir / ("kp-schema-check-v2" if PLAN == "v2" else "kp-schema-check")
    out_dir.mkdir(exist_ok=True)
    result = {"plan": plan_file, "plan_commit": plan_commit,
              "plan_rule": "first selected W/brio and first selected A/c920 frame with a scored instance, "
                           "time order; numeric ordering proxy (see module docstring)",
              "instance_rule": "class_name == 'person'" if PLAN == "v2" else "class_id == 0",
              "names_under_test": data["meta"]["keypoint_names"], "frames": {}}
    if PLAN == "v2":
        # plan v2: validity comes first; the schema check is not read on an invalid run
        result["validity"] = validity_v2(data["meta"], frames, frames_dir)
        if not result["validity"]["valid"]:
            result["verdict"] = "RUN INVALID (definition 9, v2); schema check not read"
            result["frozen_mapping"] = None
            (frames_dir / check_name).write_text(json.dumps(result, indent=1))
            print(json.dumps(result, indent=1))
            return 5
    verdicts = []
    for seg, cam, mode in (("W", "brio", "vertical"), ("A", "c920", "along-axis")):
        pick = next(((f, scored_instance(f)) for f in ordered(frames, seg, cam) if scored_instance(f)), None)
        key = f"{seg}/{cam}"
        if pick is None:
            result["frames"][key] = {"verdict": "cannot be read", "reason": "no selected frame has a scored instance"}
            verdicts.append("cannot be read")
            continue
        f, inst = pick
        r = _numeric_check(inst, mode)
        r["file"] = f["file"]
        r["detection_confidence"] = inst["detection_confidence"]
        r["n_confident"] = n_conf(inst)
        ov = out_dir / f"{Path(f['file']).stem}-overlay.png"
        bl = out_dir / f"{Path(f['file']).stem}-keypoints-only.png"
        _draw(frames_dir, f, inst, ov, blank=False)
        _draw(frames_dir, f, inst, bl, blank=True)
        r["overlay_png"] = str(ov)
        r["keypoints_only_png"] = str(bl)
        result["frames"][key] = r
        verdicts.append(r["verdict"])
    if all(v == "pass" for v in verdicts):
        result["verdict"] = "pass"
        result["frozen_mapping"] = "COCO-17 as assumed (definition 1 list), frozen before scoring"
    elif any(v == "cannot be read" for v in verdicts):
        result["verdict"] = "cannot be read"
        result["frozen_mapping"] = None
    else:
        result["verdict"] = "fail"
        result["frozen_mapping"] = None
    result["checked_utc"] = datetime.now(timezone.utc).isoformat()
    (frames_dir / check_name).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "pass" else 4


# ---------------------------------------------------------------- score (stdlib only)
def _stats(vals):
    if not vals:
        return {"n": 0, "median": None, "min": None}
    return {"n": len(vals), "median": round(statistics.median(vals), 4), "min": round(min(vals), 4)}


def _k3_block(frs, idxs, names):
    """Per-keypoint median / min / fraction >= 0.5 on the scored instance; plus per-frame group max."""
    scored = [(f, scored_instance(f)) for f in frs]
    with_inst = [(f, i) for f, i in scored if i is not None]
    out = {"frames": len(frs), "no_instance": len(frs) - len(with_inst), "keypoints": {}}
    for j in idxs:
        confs = [i["keypoints"][j][3] for _, i in with_inst]
        sq = [i["cov_sqrt_trace_px"][j] for _, i in with_inst if i.get("cov_sqrt_trace_px")]
        s = _stats(confs)
        s["frac_ge_0.5"] = f"{sum(1 for c in confs if c >= KP_CONF)}/{len(confs)}" if confs else "0/0"
        s["cov_sqrt_trace_px_median"] = round(statistics.median(sq), 1) if sq else None
        out["keypoints"][names[j]] = s
    gmax = [max(i["keypoints"][j][3] for j in idxs) for _, i in with_inst]
    g = _stats(gmax)
    g["frac_ge_0.5"] = f"{sum(1 for c in gmax if c >= KP_CONF)}/{len(gmax)}" if gmax else "0/0"
    out["per_frame_group_max"] = g
    return out


def _report_only(meta, frames) -> dict:
    """Plan "Also reported, not scored" items that do not depend on definition 2 (the scored-instance rule):
    instances returned per frame, CPU time, raw-pass metadata. Emitted even when the run is invalid."""
    inst = {}
    for seg in SEGMENTS:
        for cam in CAMERAS:
            frs = ordered(frames, seg, cam)
            counts = [len(f["instances"]) for f in frs]
            c03 = [sum(1 for i in f["instances"] if i["detection_confidence"] >= SCORE_CUTOFF) for f in frs]
            inst[f"{seg}/{cam}"] = {
                "frames": len(frs),
                "frames_with_any_instance_ge_0.1": sum(1 for c in counts if c > 0),
                "frames_with_any_instance_fused_ge_0.3": sum(1 for c in c03 if c > 0),
                "median_instances_per_frame_ge_0.1": statistics.median(counts) if counts else None,
                "median_instances_per_frame_fused_ge_0.3": statistics.median(c03) if c03 else None,
                "class_ids_returned": sorted({i["class_id"] for f in frs for i in f["instances"]}),
                "class_names_returned": sorted({str(i["class_name"]) for f in frs for i in f["instances"]}),
            }
    times = [f["predict_s"] for f in sorted(frames, key=lambda f: f["run_order"])]
    raw_times = [f["raw_pass"]["predict_s"] for f in frames if "raw_pass" in f]
    return {
        "instances_per_frame": inst,
        "cpu_time": {
            "note": "wall time around model.predict on this Mac, CPU, device='cpu'; not a device latency",
            "torch_num_threads": meta.get("torch_num_threads"),
            "first_frame_s": times[0] if times else None,
            "median_excl_first_s": round(statistics.median(times[1:]), 3) if len(times) > 1 else None,
            "min_s": min(times) if times else None, "max_s": max(times) if times else None,
            "raw_pass_median_s": round(statistics.median(raw_times), 3) if raw_times else None,
        },
        "raw_pass": meta.get("raw_pass"),
    }


def cmd_score(args) -> int:
    frames_dir = args.frames_dir
    data = load_results(frames_dir)
    meta, frames = data["meta"], data["frames"]
    names = meta["keypoint_names"]
    plan_file, plan_commit, check_name, score_name = plan_files()
    validity = validity_v2(meta, frames, frames_dir) if PLAN == "v2" else meta["validity"]
    report = {"plan": plan_file, "plan_commit": plan_commit, "results_file": str(frames_dir / RESULTS_NAME),
              "instance_rule": "class_name == 'person'" if PLAN == "v2" else "class_id == 0",
              "validity": validity}
    report["report_only"] = _report_only(meta, frames)
    if not validity["valid"]:
        report["verdict"] = f"RUN INVALID (definition 9{', v2' if PLAN == 'v2' else ''}); K1-K3 not scored"
        (frames_dir / score_name).write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1))
        return 5
    chk_path = frames_dir / check_name
    if not chk_path.exists():
        print(f"schema check has not been run; run `check{' --plan v2' if PLAN == 'v2' else ''}` first",
              file=sys.stderr)
        return 6
    chk = json.loads(chk_path.read_text())
    report["schema_check"] = {"verdict": chk["verdict"], "frozen_mapping": chk.get("frozen_mapping"),
                              "frames": {k: {kk: v.get(kk) for kk in ("file", "verdict", "reason", "values",
                                                                        "order_checked")}
                                         for k, v in chk["frames"].items()}}
    if chk["verdict"] != "pass":
        report["verdict"] = f"schema check {chk['verdict']}; K1-K3 not scored (definition 1)"
        (frames_dir / score_name).write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1))
        return 7

    # per segment x camera table
    table = {}
    for seg in SEGMENTS:
        for cam in CAMERAS:
            frs = ordered(frames, seg, cam)
            per = []
            for f in frs:
                inst = scored_instance(f)
                per.append({
                    "t_s": f["t_s"],
                    "n_returned": len(f["instances"]),
                    "n_scored_candidates": sum(1 for i in f["instances"] if is_person(i)
                                               and i["detection_confidence"] >= SCORE_CUTOFF),
                    "scored": inst is not None,
                    "det_conf": inst["detection_confidence"] if inst else None,
                    "raw_score": inst.get("raw_score_trace_alpha_0") if inst else None,
                    "n_conf": n_conf(inst) if inst else None,
                    "pose_found": bool(inst and n_conf(inst) >= KP_MIN_COUNT),
                    "angle": None if torso_angle(inst) is None else round(torso_angle(inst), 1),
                })
            angles = [p["angle"] for p in per if p["angle"] is not None]
            nconfs = [p["n_conf"] for p in per if p["n_conf"] is not None]
            dets = [p["det_conf"] for p in per if p["det_conf"] is not None]
            raws = [p["raw_score"] for p in per if p["raw_score"] is not None]
            table[f"{seg}/{cam}"] = {
                "frames": len(frs),
                "scored_instance": sum(p["scored"] for p in per),
                "pose_found": sum(p["pose_found"] for p in per),
                "with_angle": len(angles),
                "median_angle_deg": round(statistics.median(angles), 1) if angles else None,
                "angles_deg": angles,
                "median_n_conf_over_scored": statistics.median(nconfs) if nconfs else None,
                "median_det_conf_scored": round(statistics.median(dets), 4) if dets else None,
                "median_raw_score_scored": round(statistics.median(raws), 4) if raws else None,
                "instances_returned_per_frame": dict(sorted(
                    {k: sum(1 for p in per if p["n_returned"] == k) for k in {p["n_returned"] for p in per}}.items())),
                "scored_candidates_per_frame": dict(sorted(
                    {k: sum(1 for p in per if p["n_scored_candidates"] == k)
                     for k in {p["n_scored_candidates"] for p in per}}.items())),
                "per_frame": per,
            }
    report["table"] = table

    # K1
    k1 = {}
    bars = {"B": 30, "F": 27}
    for seg in ("B", "F"):
        rates = {cam: (table[f"{seg}/{cam}"]["pose_found"], table[f"{seg}/{cam}"]["frames"]) for cam in CAMERAS}
        best_cam = max(CAMERAS, key=lambda c: rates[c][0])
        hits, n = rates[best_cam]
        failing = {cam: [p["t_s"] for p in table[f"{seg}/{cam}"]["per_frame"] if not p["pose_found"]]
                   for cam in CAMERAS}
        k1[seg] = {"per_camera": {c: f"{rates[c][0]}/{rates[c][1]}" for c in CAMERAS}, "best_camera": best_cam,
                   "best": f"{hits}/{n}", "bar": f">= {bars[seg]}/{n}", "pass": hits >= bars[seg],
                   "failing_t_s": failing}
    k1_pass = k1["B"]["pass"] and k1["F"]["pass"]
    strict = {cam: (table[f"B/{cam}"]["pose_found"] >= bars["B"] and table[f"F/{cam}"]["pose_found"] >= bars["F"])
              for cam in CAMERAS}
    report["K1"] = {"verdict": "PASS" if k1_pass else "FAIL", "segments": k1,
                    "stricter_one_camera_reading_not_scored": strict}

    # K2 (brio)
    def k2_seg(seg, need):
        row = table[f"{seg}/brio"]
        measurable = row["with_angle"] >= need
        return {"frames": row["frames"], "with_angle": row["with_angle"], "min_needed": need,
                "measurable": measurable, "median_angle_deg": row["median_angle_deg"]}

    a, w = k2_seg("A", 6), k2_seg("W", 15)
    if not (a["measurable"] and w["measurable"]):
        k2_verdict = "NOT MEASURABLE (not a pass)"
    else:
        k2_verdict = "PASS" if (a["median_angle_deg"] >= K2_A_MIN_DEG and w["median_angle_deg"] <= K2_W_MAX_DEG) \
            else "FAIL"
    report["K2"] = {"verdict": k2_verdict, "A_brio": a, "W_brio": w,
                    "bar": f"A median >= {K2_A_MIN_DEG} deg and W median <= {K2_W_MAX_DEG} deg",
                    "report_only": {k: {"with_angle": f"{table[k]['with_angle']}/{table[k]['frames']}",
                                        "median_angle_deg": table[k]["median_angle_deg"],
                                        "angles_deg": table[k]["angles_deg"]}
                                    for k in ("A/c920", "W/c920", "B/c920", "B/brio", "F/c920", "F/brio")}}

    # K3 (report only)
    report["K3"] = {
        "definition": "on the scored instance; per keypoint: median, min, fraction >= 0.5 over frames with a "
                      "scored instance; per_frame_group_max = max conf over the group in each frame, then "
                      "summarized the same way; frames with no scored instance are counted as no_instance; "
                      "covariance size = sqrt(c00 + c11) px, median over the same frames",
        "F_head": {cam: _k3_block(ordered(frames, "F", cam), GROUPS["head"], names) for cam in CAMERAS},
        "B_ankles": {cam: _k3_block(ordered(frames, "B", cam), GROUPS["ankles"], names) for cam in CAMERAS},
    }

    # CPU time (report only; not a device latency)
    times = [f["predict_s"] for f in sorted(frames, key=lambda f: f["run_order"])]
    raw_times = [f["raw_pass"]["predict_s"] for f in frames if "raw_pass" in f]
    report["cpu_time"] = {
        "note": "wall time around model.predict on this Mac, CPU, device='cpu'; not a device latency",
        "torch_num_threads": meta.get("torch_num_threads"),
        "first_frame_s": times[0] if times else None,
        "median_excl_first_s": round(statistics.median(times[1:]), 3) if len(times) > 1 else None,
        "min_s": min(times) if times else None, "max_s": max(times) if times else None,
        "raw_pass_median_s": round(statistics.median(raw_times), 3) if raw_times else None,
    }
    report["overall"] = {"K1": report["K1"]["verdict"], "K2": k2_verdict, "K3": "report only"}
    report["scored_utc"] = datetime.now(timezone.utc).isoformat()
    (frames_dir / score_name).write_text(json.dumps(report, indent=1))
    _print_report(report)
    return 0


def _print_report(r):
    print(f"validity: {r['validity']['valid']}  schema check: {r['schema_check']['verdict']}")
    print("\n| seg/cam | frames | scored inst | pose found (>=9 kp) | angle n | median angle | median n_conf |")
    print("|---|---|---|---|---|---|---|")
    for k, v in r["table"].items():
        print(f"| {k} | {v['frames']} | {v['scored_instance']} | {v['pose_found']}/{v['frames']} | "
              f"{v['with_angle']} | {v['median_angle_deg']} | {v['median_n_conf_over_scored']} |")
    print("\nK1:", r["K1"]["verdict"], json.dumps({s: {k: v for k, v in d.items() if k != 'failing_t_s'}
                                                   for s, d in r["K1"]["segments"].items()}))
    print("   stricter one-camera reading:", r["K1"]["stricter_one_camera_reading_not_scored"])
    print("K2:", r["K2"]["verdict"], json.dumps({"A": r["K2"]["A_brio"], "W": r["K2"]["W_brio"]}))
    for grp in ("F_head", "B_ankles"):
        for cam, blk in r["K3"][grp].items():
            print(f"K3 {grp} {cam}: no_instance={blk['no_instance']}/{blk['frames']} "
                  f"group_max={blk['per_frame_group_max']}")
            for n, s in blk["keypoints"].items():
                print(f"     {n:15s} {s}")
    print("cpu:", r["cpu_time"])


def main() -> int:
    global PLAN
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check", "score", "probe-classes"):
        p = sub.add_parser(name)
        p.add_argument("--frames-dir", type=Path, default=DEFAULT_DIR)
        if name == "run":
            p.add_argument("--skip-raw-pass", action="store_true",
                           help="skip the report-only postprocess_trace_alpha=0.0 pass")
        if name in ("check", "score"):
            p.add_argument("--plan", choices=("v1", "v2"), default="v1",
                           help="v1 (default): plan 2026-09-27, person = class_id 0. "
                                "v2: plan 2026-09-28, person = class_name 'person' plus the package probe")
    args = ap.parse_args()
    PLAN = getattr(args, "plan", "v1")
    return {"run": cmd_run, "check": cmd_check, "score": cmd_score,
            "probe-classes": cmd_probe_classes}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
