#!/usr/bin/env python3
"""2x3 contact sheet of RF-DETR keypoint-preview skeletons on floor-trials-1 (figure only, NOT scored).

Rows are the two end-on lie-downs the floor LIDAR missed: B (feet toward the sensor) and F (head toward the sensor).
Columns are the counter camera (c920), the floor camera (brio), and a floor-camera reference panel: A (lying across)
on the B row and W (standing / walking) on the F row.

No inference is run here. The script reads the raw results that `rfdetr_keypoints.py run` saved
(`keypoints-results.json`, rfdetr 1.11.0, RFDETRKeypointPreview on CPU, predict threshold 0.1) and draws them with
Roboflow's `supervision` (sv.KeyPoints + sv.EdgeAnnotator + sv.VertexAnnotator; COCO-17 edges from
supervision.key_points.skeletons.Skeleton.COCO). The labels are drawn with PIL.

Why this is a figure and not a result:
  * The keypoint run is INVALID under plan definition 9(c): every returned instance has class_id 1 ('person'), none
    has class_id 0, so the plan's scored-instance rule (definition 2) selects nothing and K1-K3 were not scored.
  * The instance drawn here therefore uses a FIGURE-ONLY rule, which is not the plan's: class_id 1 with
    class_name 'person', fused detection_confidence >= 0.3, then the most keypoints at confidence >= 0.5, and a tie
    goes to the higher score. This is definition 2 with class_id 1 in place of class_id 0.
  * Keypoint names are ASSUMED COCO-17 (the package exposes no mapping). The plan's schema check never ran, so the
    names are unverified. Vertices are coloured by group so a human can check that head points sit on the head and
    ankle points at the feet.

Frame choice (fixed rule, no picking by result): for each segment and camera, the middle frame by time
(index n // 2) of the plan-selected frames in the results file. For W/brio, the six plan-listed empty-room times
(442, 445, 466, 469, 472, 475) are dropped first, because the plain middle (475 s) is an empty room.
If the middle frame has no instance, the panel shows the bare frame and says so. The script does not move to a
frame that has one.

Torso angle is plan definition 5, imported from rfdetr_keypoints.py (0 deg = vertical, 90 deg = horizontal; only when
all four shoulder/hip keypoints are >= 0.5 and |v| >= 5 px).

Usage (the kp-venv has supervision 0.30.5 and pillow; opencv is not needed, supervision uses its NumPy fallback):
    <venv>/bin/python tools/bag_analysis/rfdetr_keypoint_figure.py
    <venv>/bin/python tools/bag_analysis/rfdetr_keypoint_figure.py \\
        --no-pixels --out /tmp/layout-check.jpg

--no-pixels replaces every frame with flat grey (same skeletons, boxes and labels). That variant holds no frame
pixels, so it can be checked for layout and legibility without looking at the frames themselves.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rfdetr_keypoints as rk  # noqa: E402  (stdlib-only at import time; heavy imports live inside cmd_run)

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "docs/field-tests/2026-09-27-rfdetr/keypoints-B-F.jpg"
MAX_BYTES = 600_000

FIG_CLASS_ID = 1                 # figure-only: the only class id the run returned (see module docstring)
W_BRIO_EMPTY_T = {442, 445, 466, 469, 472, 475}   # plan "Data": W/Brio empty-room selected times

# (row, col, segment, camera)
PANELS = [
    (0, 0, "B", "c920"), (0, 1, "B", "brio"), (0, 2, "A", "brio"),
    (1, 0, "F", "c920"), (1, 1, "F", "brio"), (1, 2, "W", "brio"),
]
POSE_TEXT = {
    "A": "lying across",
    "B": "end-on, feet toward sensor",
    "F": "end-on, head toward sensor",
    "W": "standing / walking",
}
CAM_TEXT = {
    "c920": "c920 counter camera (98 cm high, 15° down)",
    "brio": "brio floor camera (4 cm high, level)",
}
COL_HEADERS = [CAM_TEXT["c920"], CAM_TEXT["brio"], "brio floor camera: references (A lying, W standing)"]

# keypoint groups for colouring (indices under the assumed COCO-17 order)
VERTEX_GROUPS = [
    ("head", rk.GROUPS["head"], (255, 59, 48)),
    ("shoulders", rk.GROUPS["shoulders"], (255, 149, 0)),
    ("elbows/wrists", [7, 8, 9, 10], (255, 255, 255)),
    ("hips", rk.GROUPS["hips"], (255, 214, 10)),
    ("knees", rk.GROUPS["knees"], (52, 199, 89)),
    ("ankles", rk.GROUPS["ankles"], (10, 132, 255)),
]
EDGE_RGB = (0, 229, 255)
BOX_RGB = (255, 255, 255)
LOWCONF_RGB = (160, 160, 160)

# layout (px)
PW, PH = 640, 360                # panel = 1280x720 frame at 0.5
SCALE = 0.5
M, G = 14, 10                    # outer margin, gap between panels
LEFT_W = 190                     # row-label column
HEADER_H = 92
COLHDR_H = 40
CAP_H = 76
LEGEND_H = 40
BG = (255, 255, 255)
FG = (20, 20, 20)
MUTED = (90, 90, 90)
FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def font(size: int, bold: bool = False):
    from PIL import ImageFont

    for p in ([FONT_DIR / "Arial Bold.ttf"] if bold else []) + [FONT_DIR / "Arial.ttf",
                                                                 Path("/System/Library/Fonts/Helvetica.ttc")]:
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def pick_frame(frames, seg, cam):
    fs = rk.ordered(frames, seg, cam)
    if seg == "W" and cam == "brio":
        fs = [f for f in fs if f["t_s"] not in W_BRIO_EMPTY_T]
    assert fs, f"no frames for {seg}/{cam}"
    return fs[len(fs) // 2], fs


def figure_instance(frame):
    """Definition 2 with class_id 1 in place of class_id 0 (figure only, see module docstring)."""
    cands = [i for i in frame["instances"]
             if i["class_id"] == FIG_CLASS_ID and i["class_name"] == "person"
             and i["detection_confidence"] >= rk.SCORE_CUTOFF]
    if not cands:
        return None
    return max(cands, key=lambda i: (rk.n_conf(i), i["detection_confidence"]))


def draw_panel(frames_dir: Path, frame, inst, no_pixels: bool):
    import numpy as np
    import supervision as sv
    from PIL import Image, ImageDraw
    from supervision.key_points.skeletons import Skeleton

    assert frame["image_size"] == [1280, 720], frame["image_size"]
    if no_pixels:
        img = Image.new("RGB", (PW, PH), (118, 118, 118))
    else:
        img = Image.open(frames_dir / frame["file"]).convert("RGB")
        assert img.size == (1280, 720), img.size
        img = img.resize((PW, PH), Image.LANCZOS)
    info = {"outside_panel_confident_kp": 0}
    if inst is None:
        return img, info

    d = ImageDraw.Draw(img)
    x1, y1, x2, y2 = (v * SCALE for v in inst["xyxy"])
    d.rectangle([x1, y1, x2, y2], outline=BOX_RGB, width=1)

    xy = np.array([[k[1] * SCALE, k[2] * SCALE] for k in inst["keypoints"]], dtype=np.float32)
    conf = np.array([k[3] for k in inst["keypoints"]], dtype=np.float32)
    assert xy.shape == (17, 2)
    ok = conf >= rk.KP_CONF
    inside = (xy[:, 0] >= 0) & (xy[:, 0] < PW) & (xy[:, 1] >= 0) & (xy[:, 1] < PH)
    info["outside_panel_confident_kp"] = int((ok & ~inside).sum())

    def kps(visible):
        return sv.KeyPoints(xy=xy[None], keypoint_confidence=conf[None], class_id=np.array([FIG_CLASS_ID]),
                            visible=np.asarray(visible, dtype=bool)[None])

    # low-confidence points: small grey dots, no edges
    img = sv.VertexAnnotator(color=sv.Color(*LOWCONF_RGB), radius=2).annotate(img, kps(~ok))
    # edges only between two confident points (COCO-17 skeleton, 1-based edges)
    img = sv.EdgeAnnotator(color=sv.Color(*EDGE_RGB), thickness=2,
                           edges=list(Skeleton.COCO.value)).annotate(img, kps(ok))
    # confident vertices, black halo then group colour
    img = sv.VertexAnnotator(color=sv.Color(0, 0, 0), radius=6).annotate(img, kps(ok))
    for _, idxs, rgb in VERTEX_GROUPS:
        mask = np.zeros(17, dtype=bool)
        mask[idxs] = True
        img = sv.VertexAnnotator(color=sv.Color(*rgb), radius=4).annotate(img, kps(ok & mask))
    return img, info


def panel_caption(seg, cam, frame, inst, seg_frames):
    line1 = f"{seg}: {POSE_TEXT[seg]}  |  {cam}  |  t = {frame['t_s']} s"
    n_all = len(frame["instances"])
    if inst is None:
        with_any = [f for f in seg_frames if f["instances"]]
        mx = max((i["detection_confidence"] for f in seg_frames for i in f["instances"]), default=0.0)
        ts = ", ".join(str(f["t_s"]) for f in with_any)
        if n_all == 0:
            parts = ["NO INSTANCE returned at threshold 0.1",
                     f"{len(with_any)}/{len(seg_frames)} {seg}/{cam} frames return any"
                     + (f" (t = {ts}; max score {mx:.2f})" if with_any else "")]
        else:
            best = max(i["detection_confidence"] for i in frame["instances"])
            parts = [f"no instance at fused ≥ 0.3 ({n_all} below it, max {best:.2f})", "torso angle: none"]
        return line1, parts, None
    ang = rk.torso_angle(inst)
    ang_txt = (f"torso {ang:.0f}° from vertical" if ang is not None
               else "torso angle: none (a shoulder/hip kp < 0.5)")
    parts = [f"score {inst['detection_confidence']:.2f} (fused)", f"{rk.n_conf(inst)}/17 kp ≥ 0.5", ang_txt,
             f"+{n_all - 1} other instances"]
    return line1, parts, ang


def wrap_parts(d, parts, fnt, width, sep="  |  "):
    """Greedy wrap of caption parts at the separators; asserts every line fits the panel width."""
    lines, cur = [], ""
    for p in parts:
        cand = p if not cur else cur + sep + p
        if cur and d.textlength(cand, font=fnt) > width:
            lines.append(cur)
            cur = p
        else:
            cur = cand
    lines.append(cur)
    for ln in lines:
        assert d.textlength(ln, font=fnt) <= width, f"caption too wide: {ln!r}"
    return lines


def build(frames_dir: Path, out: Path, no_pixels: bool) -> list[dict]:
    from PIL import Image, ImageDraw

    data = rk.load_results(frames_dir)
    meta, frames = data["meta"], data["frames"]
    classes = {(i["class_id"], i["class_name"]) for f in frames for i in f["instances"]}
    assert classes == {(1, "person")}, f"figure rule assumes only class_id 1 'person'; results have {classes}"

    W = M + LEFT_W + 3 * PW + 2 * G + M
    H = M + HEADER_H + COLHDR_H + 2 * (PH + CAP_H) + G + LEGEND_H + M
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)

    def text_fit(xy, txt, fnt, fill, width):
        assert d.textlength(txt, font=fnt) <= width, f"text too wide ({d.textlength(txt, font=fnt):.0f} px): {txt!r}"
        d.text(xy, txt, font=fnt, fill=fill)
    f_h1, f_h2, f_col = font(22, True), font(17), font(18, True)
    f_cap, f_cap_b, f_row, f_row_s = font(16), font(16, True), font(46, True), font(16)

    pk = meta["packages"]
    text_fit((M, M), "RF-DETR keypoint preview on floor-trials-1: middle frame of each segment "
                   f"(rfdetr {pk['rfdetr']}, {Path(meta['checkpoint']['path']).name}, CPU, predict threshold 0.1)",
           f_h1, FG, W - 2 * M)
    text_fit((M, M + 32), "FIGURE ONLY, NOT SCORED. The run is invalid under plan definition 9(c): every instance is "
                        "class_id 1, so K1-K3 were not scored. Drawn instance (figure rule, not the plan's): "
                        "class_id 1 'person', fused score ≥ 0.3, most keypoints ≥ 0.5.",
           f_h2, (170, 20, 20), W - 2 * M)
    text_fit((M, M + 56), "Keypoint names ASSUMED COCO-17 (schema check never ran). Frame = middle plan-selected frame "
                        "by time (W/brio: empty-room times dropped first). Torso angle = plan definition 5 "
                        "(0° vertical, 90° horizontal). supervision "
                        f"{pk['supervision']} EdgeAnnotator/VertexAnnotator.",
           f_h2, MUTED, W - 2 * M)

    top = M + HEADER_H
    x0 = M + LEFT_W
    for c, txt in enumerate(COL_HEADERS):
        text_fit((x0 + c * (PW + G) + 4, top + 8), txt, f_col, FG, PW - 8)

    row_meta = {0: ("B", "end-on,", "feet toward", "the sensor"), 1: ("F", "end-on,", "head toward", "the sensor")}
    report = []
    for row, col, seg, cam in PANELS:
        frame, seg_frames = pick_frame(frames, seg, cam)
        inst = figure_instance(frame)
        img, info = draw_panel(frames_dir, frame, inst, no_pixels)
        px = x0 + col * (PW + G)
        py = top + COLHDR_H + row * (PH + CAP_H + G)
        sheet.paste(img, (px, py))
        l1, parts, ang = panel_caption(seg, cam, frame, inst, seg_frames)
        assert d.textlength(l1, font=f_cap_b) <= PW - 4, f"caption too wide: {l1!r}"
        d.text((px + 2, py + PH + 6), l1, font=f_cap_b, fill=FG)
        l2 = wrap_parts(d, parts, f_cap, PW - 4)
        assert len(l2) <= 2, l2
        for k, ln in enumerate(l2):
            d.text((px + 2, py + PH + 29 + 21 * k), ln, font=f_cap,
                   fill=FG if inst is not None else (170, 20, 20))
        report.append({
            "panel": f"row{row + 1}/col{col + 1}", "segment": seg, "camera": cam, "file": frame["file"],
            "t_s": frame["t_s"], "pose": frame["pose"], "lidar": frame["lidar"],
            "instances_returned_at_0.1": len(frame["instances"]),
            "figure_instance": None if inst is None else {
                "detection_confidence": inst["detection_confidence"], "n_kp_ge_0.5": rk.n_conf(inst),
                "torso_angle_deg": None if ang is None else round(ang, 1),
                "confident_kp_outside_panel": info["outside_panel_confident_kp"],
                "confident_groups": {g: [rk.COCO17[j] for j in idxs if inst["keypoints"][j][3] >= rk.KP_CONF]
                                     for g, idxs, _ in VERTEX_GROUPS},
            },
            "caption": [l1] + l2,
        })

    for row, (letter, a, b, c3) in row_meta.items():
        ry = top + COLHDR_H + row * (PH + CAP_H + G)
        d.text((M + 4, ry + 8), letter, font=f_row, fill=FG)
        for k, t in enumerate((a, b, c3, "LIDAR: missed")):
            d.text((M + 4, ry + 70 + 22 * k), t, font=f_row_s, fill=FG if k < 3 else (170, 20, 20))
        seg_ts = sorted({f["t_s"] for f in frames if f["segment"] == letter})
        d.text((M + 4, ry + 70 + 22 * 4 + 8), f"bag {seg_ts[0]}-{seg_ts[-1]} s", font=f_row_s, fill=MUTED)

    # legend
    ly = H - M - LEGEND_H + 10
    lx = M + 4
    d.text((lx, ly), "Keypoint colour (assumed COCO-17):", font=f_cap_b, fill=FG)
    lx += int(d.textlength("Keypoint colour (assumed COCO-17):", font=f_cap_b)) + 16
    for name, _, rgb in VERTEX_GROUPS:
        d.ellipse([lx, ly + 2, lx + 14, ly + 16], fill=rgb, outline=(0, 0, 0), width=2)
        d.text((lx + 20, ly), name, font=f_cap, fill=FG)
        lx += 20 + int(d.textlength(name, font=f_cap)) + 22
    d.ellipse([lx + 4, ly + 6, lx + 10, ly + 12], fill=LOWCONF_RGB)
    txt = ("grey dot = keypoint conf < 0.5 (no edge).  Cyan edges join two keypoints ≥ 0.5.  "
           "White box = drawn instance.")
    text_fit((lx + 20, ly), txt, f_cap, FG, W - M - lx - 20)

    out.parent.mkdir(parents=True, exist_ok=True)
    for q in (88, 84, 80, 76, 72, 68):
        sheet.save(out, "JPEG", quality=q, optimize=True)
        if out.stat().st_size <= MAX_BYTES:
            break
    size = out.stat().st_size
    assert size <= MAX_BYTES, f"{out} is {size} bytes > {MAX_BYTES}"
    print(json.dumps({"out": str(out), "bytes": size, "jpeg_quality": q, "sheet_px": [W, H],
                      "no_pixels": no_pixels, "panels": report}, indent=1))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", type=Path, default=rk.DEFAULT_DIR)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-pixels", action="store_true",
                    help="flat grey instead of frame pixels (layout check); requires --out")
    args = ap.parse_args()
    if args.no_pixels and args.out is None:
        ap.error("--no-pixels needs an explicit --out, so the grey layout check never overwrites the real figure")
    out = args.out or DEFAULT_OUT
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # supervision cv2-fallback UserWarning, SupervisionWarnings
        build(args.frames_dir, out, args.no_pixels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
