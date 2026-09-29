#!/usr/bin/env python3
"""Room frames: what a fine-tuned Roboflow Inference model says about each floor-trials-1 frame, kept as it said it.

The runner behind docs/field-tests/2026-09-29-room-frames-plan.md. One request per manifest frame, serially, all
to http://127.0.0.1:9001 and nowhere else, with active learning asked off in every body. Each frame's
predictions are written beside its manifest tags: class, confidence and box, unrounded and in the order the
server returned them. A request that fails, for any reason, is a row with an `error` and no predictions, and
the run goes on; the file is written even when the run is interrupted, with `complete` false.

This file scores nothing. It writes no rate and no verdict: tools/bag_analysis/score_room_frames.py reads the
output, decides whether the run is valid and applies the bars the plan declared. It measures no cost either
(no warm-up, no memory sampling; the first request may include the model load): jetson/f5_device_fit.py is
the cost measurement.

It never writes over a file. If the output exists it stops before the first request, so a second run needs a
second name and the first run stays on disk. `--limit N` is a smoke test: its file is named
room-smoke-<model>.json, it records the limit, and the scorer gives it no verdict.

Usage:
    rf_room_eval.py <model_id> [--confidence 0.56] [--frames /opt/nvme/frames/floor-trials-1]
                    [--out /opt/nvme/frames/floor-trials-1/room-<model>.json] [--limit N]

The API key comes from ROBOFLOW_API_KEY in the environment (the caller sources ~/.roboflow.env); it is never
printed and never written to the output file.
"""
import argparse
import base64
import hashlib
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:9001"  # the only host this file ever posts to; --url exists for the test stub
CONFIDENCE = 0.56
KEPT = ("class", "confidence", "x", "y", "width", "height")


def positive(text):
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("--limit takes a positive number of frames")
    return n


def get_json(path, timeout=10, url=URL):
    with urllib.request.urlopen(f"{url}{path}", timeout=timeout) as r:
        return json.load(r)


def infer(model_id, key, confidence, image, url=URL):
    """One request for one frame's bytes. Returns (response, client_ms)."""
    body = json.dumps({
        "model_id": model_id,
        "api_key": key,
        "confidence": confidence,
        "disable_active_learning": True,
        "image": {"type": "base64", "value": base64.b64encode(image).decode()},
    }).encode()
    req = urllib.request.Request(f"{url}/infer/object_detection", data=body,
                                 headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    return out, (time.perf_counter() - t) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_id")
    ap.add_argument("--confidence", type=float, default=CONFIDENCE)
    ap.add_argument("--frames", default="/opt/nvme/frames/floor-trials-1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=positive, default=None)
    ap.add_argument("--url", default=URL, help=argparse.SUPPRESS)  # test stub only
    a = ap.parse_args()
    key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not key:
        sys.exit("ROBOFLOW_API_KEY is not set (source ~/.roboflow.env)")
    manifest_bytes = open(f"{a.frames}/manifest.json", "rb").read()
    manifest = json.loads(manifest_bytes)
    if a.limit:
        manifest = manifest[: a.limit]
    tag = a.model_id.replace("/", "_")
    out_path = a.out or f"{a.frames}/room-{'smoke-' if a.limit else ''}{tag}.json"
    if os.path.exists(out_path):
        sys.exit(f"{out_path} exists and is not written over: a second run needs a second --out")

    info = get_json("/info", url=a.url)
    rows, errors, digest = [], 0, hashlib.sha256()
    t_run = time.time()
    try:
        for m in manifest:
            try:
                image = open(f"{a.frames}/{m['file']}", "rb").read()
                digest.update(image)
                out, ms = infer(a.model_id, key, a.confidence, image, url=a.url)
                if not isinstance(out, dict) or not isinstance(out.get("predictions"), list):
                    raise ValueError("no predictions in the response")
                rows.append({**m, "latency_ms": round(ms, 1),
                             "predictions": [{k: p.get(k) for k in KEPT} for p in out["predictions"]]})
            except urllib.error.HTTPError as e:
                errors += 1
                rows.append({**m, "predictions": [], "error": f"HTTP {e.code}"})
            except Exception as e:  # whatever went wrong with this frame, the next one is still asked
                errors += 1
                rows.append({**m, "predictions": [], "error": f"{type(e).__name__}: {e}"[:120]})
    finally:
        summary = {
            "model": a.model_id,
            "confidence": a.confidence,
            "url": a.url,
            "limit": a.limit,
            "complete": len(rows) == len(manifest),
            "frames_requested": len(manifest),
            "frames_answered": len(rows) - errors,
            "errors": errors,
            "run_s": round(time.time() - t_run, 1),
            "manifest_md5": hashlib.md5(manifest_bytes).hexdigest(),
            "frames_sha256": digest.hexdigest(),
            "server_version": info.get("version"),
            "device": platform.node(),
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_run)),
            "frames_dir": a.frames,
            "note": "predictions kept as returned; nothing scored here (see docstring)",
        }
        with open(out_path, "x") as f:
            json.dump({"summary": summary, "frames": rows}, f, indent=1)
        print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
