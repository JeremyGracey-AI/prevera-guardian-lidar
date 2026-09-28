#!/usr/bin/env python3
"""Evidence figures for the RF-DETR evaluation on the floor-trials-1 frames.

Writes into --out:
  blind-spot-B.(png|jpg)  LIDAR top-down at t = 110 s | counter C920 | floor Brio, with RF-DETR boxes
  blind-spot-F.(png|jpg)  same at t = 385 s
  segments-grid.jpg       contact sheet: rows A-F and W, columns C920 | Brio, one mid-segment frame each

Every number that appears in a caption is derived here from the bag / results JSON and printed to stdout,
so the figures can be checked against this script's output. Nothing is uploaded anywhere.

Data: the frames, results JSON and LIDAR mcap are NOT in this repository (field data is not published);
the defaults below are where they live on the author's machine. Pass --frames/--bag to point elsewhere.

Usage (throwaway venv, not part of the ROS workspace):
  uv venv <venv> --python 3.10
  uv pip install --python <venv>/bin/python \
      supervision matplotlib mcap mcap-ros2-support opencv-python-headless
  <venv>/bin/python tools/bag_analysis/rfdetr_figures.py [--model rfdetr-base]

Conventions
  * Scan time = seconds since the first /scan header stamp in the mcap.
  * Frame time = manifest t_s (1 fps extraction). The zero of t_s was not cross-checked against the scan
    stamps; the lie-downs were held still for ~30 s, so a <= 1 s offset does not change what is shown.
  * Top-down plots show the ROS scan frame looking down: horizontal = +y (east / fridge to the right),
    vertical = -x (toward the desk, up). Both cameras look toward the desk, so left/right match the frames.
  * Box format in the results JSON: x, y = box centre, width, height, pixels on 1280x720 frames.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import supervision as sv  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402
from mcap.reader import make_reader  # noqa: E402
from mcap_ros2.decoder import DecoderFactory  # noqa: E402

HOME = Path.home()
DEF_FRAMES = HOME / "src/local/prevera-frames/floor-trials-1"
DEF_BAG = HOME / "src/local/prevera-bags/floor-trials-1-lidar/floor-trials-1-lidar_0.mcap"
DEF_OUT = Path(__file__).resolve().parents[2] / "docs/field-tests/2026-09-27-rfdetr"

# The two end-on segments the LIDAR missed, and the scan instant to show (task-specified).
BLIND = {"B": 110.0, "F": 385.0}
SEG_TEXT = {  # segment -> (pose, distance) from the floor-trials-1 run sheet
    "A": ("across the beam", "2.0 m"),
    "B": ("end-on, feet toward the sensor", "0.9 m"),
    "C": ("across the beam", "2.6 m"),
    "D": ("diagonal", "1.6 m"),
    "E": ("diagonal", "1.3 m"),
    "F": ("end-on, head toward the sensor", "0.83 m"),
    "W": ("standing / walking over the grid", "no fall"),
}
SEG_ORDER = ["A", "B", "C", "D", "E", "F", "W"]
CAM_TEXT = {"c920": "Counter C920 (98 cm, 15° down)", "brio": "Floor Brio 100 (4 cm, level)"}
# Detector gate in the repo config (src/prevera_bringup/config/fall_detector.yaml:27-28). Repo value, not
# read from the Jetson.
GATE_ELONG, GATE_MAJOR_M = 3.5, 0.8
PERSON_MIN_RANGE_M = 0.4  # excludes the static Brio / counter-edge track at ~5 cm
BORN_AFTER_START_S = 5.0  # person track: born after the previous segment ended, <= 5 s after this start

# Palette (dataviz reference instance): text inks, neutral scan, one accent for LIDAR person clusters,
# a separate hue for RF-DETR boxes, status colours only for the LIDAR outcome tags (always with a label).
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
SURFACE = "#fcfcfb"
LIDAR_PERSON = "#eb6834"  # categorical slot 2
BOX_HEX = "#eda100"  # categorical slot 4; black label text
STATUS = {"detected": "#0ca30c", "missed": "#d03b3b", "no-fall": "#52514e"}
SIZE_LIMIT = 600 * 1024

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


# ----------------------------------------------------------------------------------------------- data
def load_results(frames_dir: Path, model: str):
    res = json.loads((frames_dir / f"results-{model}.json").read_text())
    by_file = {f["file"]: f for f in res["frames"]}
    return res["summary"], by_file, res["frames"]


def seg_stats(frames):
    """Per (segment, camera): detected count, total, median best aspect over detected frames, sorted t_s."""
    out = defaultdict(lambda: {"n": 0, "hit": 0, "aspects": [], "ts": [], "lidar": None})
    for f in frames:
        d = out[(f["segment"], f["camera"])]
        d["n"] += 1
        d["ts"].append(f["t_s"])
        d["lidar"] = f["lidar"]
        if f["n_person"] > 0:
            d["hit"] += 1
            d["aspects"].append(f["best_aspect_wh"])
    for d in out.values():
        d["ts"].sort()
        d["median_aspect"] = float(np.median(d["aspects"])) if d["aspects"] else float("nan")
        d["window"] = (d["ts"][0], d["ts"][-1] + 1)
    return out


def stamp(m) -> float:
    return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9


def read_bag(bag: Path, targets: dict[str, float], windows: dict[str, tuple[float, float]]):
    """One pass over /scan, /tracks, /fall_events. Times are relative to the first /scan header stamp."""
    t0 = None
    best_scan = {k: (1e9, None, None) for k in targets}  # seg -> (|dt|, t, msg)
    tracks_at = {}  # scan time -> tracks msg (only for chosen scans; filled in a second step)
    all_tracks = []  # (t, [(id, x, y, extent, elong, age, still)])
    first_seen = {}
    events = []
    with open(bag, "rb") as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for _, ch, _, m in reader.iter_decoded_messages(topics=["/scan", "/tracks", "/fall_events"]):
            st = stamp(m)
            if ch.topic == "/scan":
                if t0 is None:
                    t0 = st
                s = st - t0
                for k, T in targets.items():
                    if abs(s - T) < best_scan[k][0]:
                        best_scan[k] = (abs(s - T), s, m)
                continue
            if t0 is None:
                continue
            s = st - t0
            if ch.topic == "/tracks":
                rows = [(k.track_id, k.centroid.x, k.centroid.y, k.horizontal_extent_m, k.elongation_ratio,
                         k.age_s, k.is_still) for k in m.tracks]
                for r in rows:
                    first_seen.setdefault(r[0], s)
                if any(a - 3 <= s <= b + 3 for a, b in windows.values()):
                    all_tracks.append((s, rows))
            else:
                events.append(s)
    scans = {k: (v[1], v[2]) for k, v in best_scan.items()}
    for k, (s, _) in scans.items():
        tracks_at[k] = min(all_tracks, key=lambda tr: abs(tr[0] - s))
    return t0, scans, tracks_at, all_tracks, first_seen, np.array(events)


def person_tracks(rows, first_seen, born_lo, born_hi):
    """Tracks at range > 0.4 m born between the previous segment's end and this segment's start + 5 s.

    Tracks are born while the person walks in and gets down (a few seconds before the manifest start), so
    the lower bound is the end of the previous lie-down, which also excludes static clutter (e.g. #1).
    """
    lo, hi = born_lo, born_hi
    return [r for r in rows
            if math.hypot(r[1], r[2]) > PERSON_MIN_RANGE_M and lo <= first_seen[r[0]] <= hi]


def track_window_stats(all_tracks, ids, window):
    st = defaultdict(lambda: {"ext": [], "el": [], "nonfinite": 0})
    for s, rows in all_tracks:
        if not (window[0] <= s <= window[1]):
            continue
        for r in rows:
            if r[0] in ids:
                st[r[0]]["ext"].append(r[3])
                if math.isfinite(r[4]):
                    st[r[0]]["el"].append(r[4])
                else:
                    st[r[0]]["nonfinite"] += 1
    return st


def scan_xy(m):
    rr = np.asarray(m.ranges, dtype=float)
    a = m.angle_min + np.arange(len(rr)) * m.angle_increment
    ok = np.isfinite(rr) & (rr >= m.range_min) & (rr <= m.range_max)
    return rr[ok] * np.cos(a[ok]), rr[ok] * np.sin(a[ok]), rr[ok], a[ok]


def bearing_deg(x, y):
    return math.degrees(math.atan2(y, x)) % 360.0


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi




# ----------------------------------------------------------------------------------------- annotation
def annotate(frames_dir: Path, rec, width: int | None = None) -> np.ndarray:
    """RF-DETR person boxes drawn with supervision on the untouched frame (optionally resized first).

    Returns RGB. Resizing happens before drawing so line and label sizes are chosen for the display size.
    """
    bgr = cv2.imread(str(frames_dir / rec["file"]))
    k = 1.0
    if width:
        k = width / bgr.shape[1]
        bgr = cv2.resize(bgr, (width, round(bgr.shape[0] * k)), interpolation=cv2.INTER_AREA)
    ps = rec["persons"]
    if ps:
        u = max(k, 0.5)
        box = sv.BoxAnnotator(color=sv.Color.from_hex(BOX_HEX), thickness=max(2, round(6 * u)))
        lab = sv.LabelAnnotator(color=sv.Color.from_hex(BOX_HEX), text_color=sv.Color.BLACK,
                                text_scale=1.5 * u, text_thickness=max(1, round(3 * u)),
                                text_padding=max(4, round(10 * u)), text_position=sv.Position.TOP_LEFT,
                                smart_position=True)
        xyxy = np.array([[p["x"] - p["width"] / 2, p["y"] - p["height"] / 2,
                          p["x"] + p["width"] / 2, p["y"] + p["height"] / 2] for p in ps], dtype=float) * k
        det = sv.Detections(xyxy=xyxy, confidence=np.array([p["confidence"] for p in ps]),
                            class_id=np.zeros(len(ps), dtype=int))
        bgr = box.annotate(scene=bgr.copy(), detections=det)
        bgr = lab.annotate(scene=bgr, detections=det, labels=[f"person {c:.2f}" for c in det.confidence])
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def frame_line(rec) -> str:
    if rec["n_person"] == 0:
        return "no person box ≥ 0.4"
    return f"person {rec['best_conf']:.2f} · box w/h {rec['best_aspect_wh']:.2f}"


# ------------------------------------------------------------------------------------------- output
def save(fig, stem: Path, prefer: str) -> Path:
    """Save as `prefer`; a PNG over the size limit is re-saved as JPG (photos do not fit in 600 KB PNG)."""
    if prefer == "png":
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        if buf.tell() <= SIZE_LIMIT:
            path = stem.with_suffix(".png")
            path.write_bytes(buf.getvalue())
            _drop(stem.with_suffix(".jpg"))
            return path
        print(f"  {stem.name}.png would be {buf.tell() / 1024:.0f} KB > {SIZE_LIMIT // 1024} KB -> JPG")
    for q in (90, 85, 80, 75):
        buf = io.BytesIO()
        fig.savefig(buf, format="jpg", pil_kwargs={"quality": q, "optimize": True, "progressive": True})
        if buf.tell() <= SIZE_LIMIT:
            break
    path = stem.with_suffix(".jpg")
    path.write_bytes(buf.getvalue())
    print(f"  {path.name}: JPEG quality {q}")
    if prefer == "png":
        _drop(stem.with_suffix(".png"))
    return path


def _drop(p: Path):
    if p.exists():
        p.unlink()


def rgba(hex_, a):
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


# -------------------------------------------------------------------------------------- blind-spot fig
def lidar_panel(ax, s_scan, scan, trk_rows, wstats):
    x, y, rr, aa = scan_xy(scan)
    # Assign scan returns to the nearest person-track centroid (within half its extent + 8 cm).
    assign = np.full(len(x), -1)
    dmin = np.full(len(x), np.inf)
    for i, r in enumerate(trk_rows):
        d = np.hypot(x - r[1], y - r[2])
        lim = max(0.12, 0.5 * r[3] + 0.08)
        take = (d <= lim) & (d < dmin)
        assign[take], dmin[take] = i, d[take]

    # Occlusion wedge behind each person cluster: from its returns out to 8 m, over its angular span.
    # Data-derived: every ray in the span ended on the person, so nothing behind it was seen.
    for i, r in enumerate(trk_rows):
        sel = assign == i
        if sel.sum() < 2:
            continue
        ac = math.atan2(r[2], r[1])
        rel = np.array([wrap(a - ac) for a in aa[sel]])
        order = np.argsort(rel)
        near = [(y[sel][j], -x[sel][j]) for j in order]
        far = [(8 * math.sin(ac + rel[j]), -8 * math.cos(ac + rel[j])) for j in order[::-1]]
        ax.add_patch(Polygon(near + far, closed=True, facecolor=rgba(LIDAR_PERSON, 0.10),
                             edgecolor=rgba(LIDAR_PERSON, 0.55), lw=0, hatch="///", zorder=1,
                             label="shadow behind the person returns" if i == 0 else None))

    for rad in (1.0, 2.0, 3.0):
        ax.add_patch(Circle((0, 0), rad, fill=False, ls=(0, (2, 3)), lw=0.6, color=MUTED, alpha=0.7, zorder=0))

    other = assign < 0
    ax.scatter(y[other], -x[other], s=8, color=MUTED, lw=0, zorder=2, label="scan returns (2 cm plane)")
    ax.scatter(y[~other], -x[~other], s=18, color=LIDAR_PERSON, lw=0.4, edgecolor=SURFACE, zorder=3,
               label="person clusters (/tracks)")
    ax.plot([0], [0], marker="^", ms=10, color=INK, lw=0, zorder=4, label="RPLIDAR C1 (origin)")
    ax.plot([], [], ls=(0, (2, 3)), lw=0.8, color=MUTED, label="range rings 1, 2, 3 m")

    info = []
    placed = {-1: -1e9, 1: -1e9}
    for i in sorted(range(len(trk_rows)), key=lambda i: -trk_rows[i][1]):  # nearest first
        r = trk_rows[i]
        sel = assign == i
        pts = np.c_[x[sel], y[sel]]
        pext = max((float(np.hypot(*(p - q))) for p in pts for q in pts), default=0.0)
        rng, brg = math.hypot(r[1], r[2]), bearing_deg(r[1], r[2])
        w = wstats[r[0]]
        info.append(dict(id=r[0], x=r[1], y=r[2], range=rng, bearing=brg, ext=r[3], elong=r[4],
                         npts=int(sel.sum()), pt_extent=pext, seg_ext_med=float(np.median(w["ext"])),
                         seg_ext_max=float(np.max(w["ext"])), el=w["el"], nonfinite=w["nonfinite"]))
        side = 1 if r[2] >= 0 else -1
        v = max(-r[1] + 0.40, placed[side] + 0.36)
        placed[side] = v
        ax.annotate(f"#{r[0]} · {rng:.2f} m\nextent {r[3]:.2f} m", xy=(r[2], -r[1]), xytext=(side * 1.02, v),
                    fontsize=8.5, color=INK, ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.7, shrinkA=0, shrinkB=3),
                    bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec=MUTED, lw=0.5), zorder=5)

    ax.text(1.45, 2.27, "desk (−x) ↑", ha="right", va="top", fontsize=8.5, color=INK2, zorder=5,
            bbox=dict(boxstyle="square,pad=0.15", fc=SURFACE, ec="none"))
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-0.25, 2.35)
    ax.set_aspect("equal")
    ax.set_xlabel("y (m):  ← west (couch)    east (fridge) →")
    ax.set_ylabel("−x (m): toward the desk")
    ax.set_title(f"Floor LIDAR, top-down · /scan at t = {s_scan:.2f} s", fontsize=10.5, color=INK, loc="left")
    ax.legend(loc="lower left", fontsize=7.5, frameon=True, framealpha=0.95, edgecolor=MUTED, borderpad=0.4,
              handlelength=1.6)
    return info


def blind_spot_figure(seg, T, frames_dir, by_file, stats, bag_data, born_lo, model, out_dir):
    t0, scans, tracks_at, all_tracks, first_seen, events = bag_data
    s_scan, scan = scans[seg]
    s_trk, rows = tracks_at[seg]
    window = stats[(seg, "c920")]["window"]
    born_hi = window[0] + BORN_AFTER_START_S
    trk = person_tracks(rows, first_seen, born_lo, born_hi)
    wstats = track_window_stats(all_tracks, {r[0] for r in trk}, window)
    n_ev = int(((events >= window[0]) & (events <= window[1])).sum())
    after = events[(events > window[1]) & (events < window[1] + 5)]

    fig = plt.figure(figsize=(17.0, 6.9), dpi=110)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.2, 1.5, 1.5], left=0.05, right=0.99, top=0.845, bottom=0.265,
                          wspace=0.07)
    info = lidar_panel(fig.add_subplot(gs[0]), s_scan, scan, trk, wstats)

    t_frame = int(round(T))
    recs = {}
    for j, cam in enumerate(("c920", "brio")):
        rec = by_file[f"{seg}-{t_frame:03d}s-{cam}.jpg"]
        recs[cam] = rec
        ax = fig.add_subplot(gs[1 + j])
        ax.imshow(annotate(frames_dir, rec))
        ax.set_anchor("N")
        ax.set_axis_off()
        st = stats[(seg, cam)]
        ax.set_title(f"{CAM_TEXT[cam]} · frame t = {rec['t_s']} s", fontsize=10.5, color=INK, loc="left")
        ax.text(0.0, -0.03, f"This frame: {frame_line(rec)}\nSegment {seg}: person in {st['hit']}/{st['n']} "
                f"frames · median box w/h {st['median_aspect']:.2f}", transform=ax.transAxes, va="top",
                ha="left", fontsize=9.5, color=INK2, linespacing=1.35)

    pose, dist = SEG_TEXT[seg]
    c, b = stats[(seg, "c920")], stats[(seg, "brio")]
    fig.text(0.05, 0.965, f"Segment {seg} — lying {pose} ({dist}): floor LIDAR raised {n_ev} events; "
             f"RF-DETR found a person in C920 {c['hit']}/{c['n']} and Brio {b['hit']}/{b['n']} frames",
             fontsize=13.5, color=INK, weight="bold", va="top")
    fig.text(0.05, 0.918, f"floor-trials-1, 2026-09-27 · camera boxes: {model} (stock COCO weights, class "
             f"person, conf ≥ 0.4), run locally on the Jetson Orin Nano (Roboflow Inference 1.7.2, localhost); "
             f"rf_eval.py posted only to 127.0.0.1:9001", fontsize=9.5, color=INK2, va="top")

    # What the LIDAR saw. Every number below is also printed to stdout.
    parts = [f"#{d['id']} at {d['range']:.2f} m, bearing {d['bearing']:.0f}°, extent {d['ext']:.2f} m"
             for d in info]
    main_t = max(info, key=lambda d: d["seg_ext_max"])
    el_all = np.concatenate([d["el"] for d in info])
    nonfinite = sum(d["nonfinite"] for d in info)
    pct = 100.0 * (el_all >= GATE_ELONG).sum() / max(1, len(el_all) + nonfinite)
    table = {"B": "0.33 m", "F": "0.22 m"}.get(seg, "n/a")
    cap = (f"What the LIDAR saw: {len(info)} small cluster{'s' if len(info) > 1 else ''} at this scan "
           f"({'; '.join(parts)}). Over segment {seg} ({window[0]}–{window[1]} s) no person track exceeded "
           f"{main_t['seg_ext_max']:.2f} m (#{main_t['id']}: median {main_t['seg_ext_med']:.2f} m; field-test "
           f"table: {table}). _looks_horizontal() needs elongation ≥ {GATE_ELONG} AND major axis ≥ "
           f"{GATE_MAJOR_M} m (repo fall_detector.yaml:27–28): elongation was ≥ {GATE_ELONG} in {pct:.1f} % of "
           f"track updates, but the major axis never reached {GATE_MAJOR_M} m, so the gate never passed and "
           f"there were {n_ev} /fall_events in {window[0]}–{window[1]} s"
           + (f" ({len(after)} at {after.min():.1f}–{after.max():.1f} s, while getting up)" if len(after) else "")
           + ". The rest of the body lies along the beam, inside the hatched shadow of these returns, which the "
             "2 cm scan plane cannot see past.")
    fig.text(0.05, 0.188, "\n".join(textwrap.wrap(cap, 200)), fontsize=9.5, color=INK, va="top",
             linespacing=1.35)
    note = (f"Scan t = seconds since the first /scan header stamp in floor-trials-1-lidar_0.mcap (tracks msg at "
            f"{s_trk:.2f} s). Frame t = manifest t_s (1 fps); the zero offset between the two clocks was not "
            f"cross-checked (≤ ~1 s; the person was still for ~30 s). Person clusters = /tracks at range > "
            f"{PERSON_MIN_RANGE_M} m born after the previous lie-down ended ({born_lo:g} s) and ≤ "
            f"{BORN_AFTER_START_S:g} s after this segment's start; returns assigned to the nearest such track. "
            f"Frames are unaltered apart from the supervision box/label overlay. "
            f"Figure: tools/bag_analysis/rfdetr_figures.py.")
    fig.text(0.05, 0.062, "\n".join(textwrap.wrap(note, 235)), fontsize=8, color=INK2, va="top")

    path = save(fig, out_dir / f"blind-spot-{seg}", prefer="png")
    plt.close(fig)

    print(f"\n[{seg}] scan used: t = {s_scan:.3f} s (target {T}); tracks msg t = {s_trk:.3f} s; "
          f"t0 (first /scan header) = {t0:.6f}")
    print(f"[{seg}] person tracks (rule: range > {PERSON_MIN_RANGE_M} m, first seen in [{born_lo}, {born_hi}] s):")
    for d in info:
        el = np.asarray(d["el"])
        print("   #%d  x=%.2f y=%.2f  range=%.2f m  bearing=%.1f deg  first seen %.2f s  track extent=%.3f m  "
              "elong=%.1f  returns=%d  return-span=%.3f m | segment: extent median %.3f max %.3f, "
              "elong %.1f-%.1f (%d/%d >= %.1f, %d non-finite)"
              % (d["id"], d["x"], d["y"], d["range"], d["bearing"], first_seen[d["id"]], d["ext"], d["elong"],
                 d["npts"], d["pt_extent"], d["seg_ext_med"], d["seg_ext_max"], el.min(), el.max(),
                 (el >= GATE_ELONG).sum(), len(el), GATE_ELONG, d["nonfinite"]))
    others = [(r[0], round(math.hypot(r[1], r[2]), 2), round(first_seen[r[0]], 1)) for r in rows
              if r[0] not in {q[0] for q in trk}]
    print(f"[{seg}] other tracks in that msg (id, range m, first seen s): {others}")
    print(f"[{seg}] elongation >= {GATE_ELONG}: {pct:.1f} % of person-track updates in the window")
    print(f"[{seg}] /fall_events in {window}: {n_ev}; within 5 s after: {[round(float(e), 2) for e in after]}")
    for cam, rec in recs.items():
        st = stats[(seg, cam)]
        print(f"[{seg}] {cam} {rec['file']}: {frame_line(rec)}; segment {st['hit']}/{st['n']}, "
              f"median w/h {st['median_aspect']:.2f}")
    print(f"[{seg}] wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
    return path


# ------------------------------------------------------------------------------------- contact sheet
def contact_sheet(frames_dir, by_file, stats, model, out_dir):
    n = len(SEG_ORDER)
    head_in, row_in, foot_in = 1.35, 2.98, 0.25
    H = head_in + n * row_in + foot_in
    fig = plt.figure(figsize=(11.0, H), dpi=120)
    gs = fig.add_gridspec(n, 3, width_ratios=[0.40, 1, 1], left=0.012, right=0.992, top=1 - head_in / H,
                          bottom=foot_in / H, hspace=0.30, wspace=0.025)
    fig.text(0.012, 1 - 0.14 / H, "floor-trials-1 · one mid-segment frame per segment and camera", fontsize=13,
             weight="bold", color=INK, va="top")
    fig.text(0.012, 1 - 0.46 / H, f"{model} (stock COCO weights, class person, conf ≥ 0.4), run locally on the "
             f"Jetson Orin Nano. Mid frame = sorted(t_s)[n // 2] within the segment (no hand-picking).\n"
             f"Under each frame: frames in the segment with ≥ 1 person box / frames, and median best-box w/h over "
             f"those frames.", fontsize=8.8, color=INK2, va="top", linespacing=1.35)
    chosen = []
    for i, seg in enumerate(SEG_ORDER):
        ax = fig.add_subplot(gs[i, 0])
        ax.set_axis_off()
        pose, dist = SEG_TEXT[seg]
        lidar = stats[(seg, "c920")]["lidar"]
        ax.text(0.03, 0.90, seg, fontsize=24, weight="bold", color=INK, va="top", transform=ax.transAxes)
        ax.text(0.03, 0.62, "\n".join(textwrap.wrap(pose, 17)) + f"\n{dist}", fontsize=9.5, color=INK,
                va="top", transform=ax.transAxes, linespacing=1.25)
        tag = {"detected": "✓ LIDAR: detected", "missed": "✗ LIDAR: missed", "no-fall": "LIDAR: 0 alarms"}[lidar]
        ax.text(0.03, 0.06, tag, fontsize=8.8, color="white", weight="bold", va="bottom",
                transform=ax.transAxes, bbox=dict(boxstyle="round,pad=0.35", fc=STATUS[lidar], ec="none"))
        for j, cam in enumerate(("c920", "brio")):
            st = stats[(seg, cam)]
            t_mid = st["ts"][len(st["ts"]) // 2]
            rec = by_file[f"{seg}-{t_mid:03d}s-{cam}.jpg"]
            chosen.append(rec)
            ax = fig.add_subplot(gs[i, 1 + j])
            ax.imshow(annotate(frames_dir, rec, width=640))
            ax.set_axis_off()
            ax.set_title(f"t = {rec['t_s']} s · {frame_line(rec)}", fontsize=9, loc="left", color=INK, pad=3)
            ax.text(0.0, -0.018, f"segment {seg}: {st['hit']}/{st['n']} frames · median w/h "
                    f"{st['median_aspect']:.2f}", transform=ax.transAxes, fontsize=8.5, color=INK2,
                    va="top", ha="left")
            if i == 0:
                pos = ax.get_position()
                fig.text(pos.x0, 1 - (head_in - 0.30) / H, CAM_TEXT[cam], fontsize=11, weight="bold",
                         color=INK, va="bottom", ha="left")
    path = save(fig, out_dir / "segments-grid", prefer="jpg")
    plt.close(fig)
    print("\n[grid] mid-segment frames:")
    for rec in chosen:
        st = stats[(rec["segment"], rec["camera"])]
        print(f"   {rec['file']}: {frame_line(rec)} | segment {st['hit']}/{st['n']}, "
              f"median w/h {st['median_aspect']:.2f}, lidar {rec['lidar']}")
    print(f"[grid] wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="rfdetr-base")
    ap.add_argument("--frames", type=Path, default=DEF_FRAMES)
    ap.add_argument("--bag", type=Path, default=DEF_BAG)
    ap.add_argument("--out", type=Path, default=DEF_OUT)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    summary, by_file, frames = load_results(a.frames, a.model)
    stats = seg_stats(frames)
    print(f"model {summary['model']} conf {summary['confidence']} frames {summary['frames']}")
    for (seg, cam), d in sorted(stats.items()):
        ps = summary["per_segment"][f"{seg}/{cam}"]
        print(f"  {seg}/{cam}: {d['hit']}/{d['n']} (summary rate {ps['person_rate']}), median w/h "
              f"{d['median_aspect']:.3f} (summary {ps['median_aspect_wh']}), lidar {d['lidar']}")

    windows = {s: stats[(s, "c920")]["window"] for s in BLIND}
    bag_data = read_bag(a.bag, BLIND, windows)
    written = []
    for seg, T in BLIND.items():
        prev = SEG_ORDER[SEG_ORDER.index(seg) - 1]
        born_lo = stats[(prev, "c920")]["window"][1] if SEG_ORDER.index(seg) > 0 else 0.0
        written.append(blind_spot_figure(seg, T, a.frames, by_file, stats, bag_data, born_lo, a.model, a.out))
    written.append(contact_sheet(a.frames, by_file, stats, a.model, a.out))
    print("\nwritten:", *[f"{p} ({p.stat().st_size / 1024:.0f} KB)" for p in written], sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
