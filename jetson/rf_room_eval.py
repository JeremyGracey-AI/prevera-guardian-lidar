#!/usr/bin/env python3
"""Room frames: what a fine-tuned Roboflow Inference model says about each floor-trials-1 frame, kept as it said it.

The runner behind docs/field-tests/2026-09-29-room-frames-plan.md. One request per manifest frame, serially, all
to http://127.0.0.1:9001 by default (only literal loopback overrides are accepted; no proxies or redirects), with active learning
asked off in every body. Each frame's predictions are written beside its manifest tags: class, confidence and
box, unrounded and in the order the server returned them. A request that fails, for any reason, is a row with
an `error` and no predictions, and the run goes on.

This file scores nothing. It writes no rate and no verdict: tools/bag_analysis/score_room_frames.py reads the
output, decides whether the run is valid and applies the bars the plan declared. It measures no cost either
(no warm-up, no memory sampling; the first request may include the model load): jetson/f5_device_fit.py is
the cost measurement.

It never writes over a file, and it has no smoke mode: every run asks every manifest frame. The output file is
created before the first request and the run stops there if the name is taken or the directory is missing, so a
second run needs a second name and the first run stays on disk. A run that is interrupted (Ctrl-C, a dropped
session, a kill) still writes the rows it has, with `complete` false.

Usage:
    rf_room_eval.py <model_id> [--confidence 0.56] [--frames /opt/nvme/frames/floor-trials-1]
                    [--out /opt/nvme/frames/floor-trials-1/room-<model>.json]

The API key comes from ROBOFLOW_API_KEY in the environment (the caller sources ~/.roboflow.env); it is never
printed and never written to the output file.
"""
import argparse
import base64
import hashlib
import json
import os
import platform
import signal
import sys
import time
import urllib.error

from inference_http import URL, InferenceResponseError, request_json, validate_base_url

CONFIDENCE = 0.56
KEPT = ("class", "confidence", "x", "y", "width", "height")


def rows_digest(rows):
    """sha256 of the rows as canonical JSON: the scorer recomputes it, so a row edited by hand shows."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def infer(model_id, key, confidence, image, url=URL):
    """One request for one frame's bytes. Returns (response, client_ms)."""
    body = json.dumps({
        "model_id": model_id,
        "api_key": key,
        "confidence": confidence,
        "disable_active_learning": True,
        "image": {"type": "base64", "value": base64.b64encode(image).decode()},
    }).encode()
    t = time.perf_counter()
    out = request_json("/infer/object_detection", data=body, timeout=300, url=url)
    return out, (time.perf_counter() - t) * 1000


def stop(signum, _frame):
    raise SystemExit(128 + signum)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_id")
    ap.add_argument("--confidence", type=float, default=CONFIDENCE)
    ap.add_argument("--frames", default="/opt/nvme/frames/floor-trials-1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--url", default=URL, help=argparse.SUPPRESS)  # test stub only
    a = ap.parse_args()
    try:
        a.url = validate_base_url(a.url)
    except ValueError as e:
        ap.error(str(e))
    key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not key:
        sys.exit("ROBOFLOW_API_KEY is not set (source ~/.roboflow.env)")
    manifest_bytes = open(f"{a.frames}/manifest.json", "rb").read()
    manifest = json.loads(manifest_bytes)
    out_path = a.out or f"{a.frames}/room-{a.model_id.replace('/', '_')}.json"
    try:
        out_file = open(out_path, "x")
    except FileExistsError:
        sys.exit(f"{out_path} exists and is not written over: a second run needs a second --out")
    except OSError as e:
        sys.exit(f"{out_path} cannot be created ({type(e).__name__}); nothing was requested")
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, stop)

    rows, errors, digest, info = [], 0, hashlib.sha256(), {}
    t_run = time.time()
    try:
        info = request_json("/info", url=a.url)
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
            except InferenceResponseError as e:
                errors += 1
                rows.append({**m, "predictions": [], "error": str(e)})
            except Exception as e:  # whatever went wrong with this frame, the next one is still asked
                errors += 1
                rows.append({**m, "predictions": [], "error": f"{type(e).__name__}: {e}"[:120]})
    finally:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, signal.SIG_IGN)      # the file is written whole, whatever arrives now
        summary = {
            "model": a.model_id,
            "confidence": a.confidence,
            "url": a.url,
            "complete": len(rows) == len(manifest),
            "frames_requested": len(manifest),
            "frames_answered": len(rows) - errors,
            "errors": errors,
            "run_s": round(time.time() - t_run, 1),
            "manifest_md5": hashlib.md5(manifest_bytes).hexdigest(),
            "frames_sha256": digest.hexdigest(),
            "rows_sha256": rows_digest(rows),
            "server_version": info.get("version"),
            "device": platform.node(),
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_run)),
            "frames_dir": a.frames,
            "note": "predictions kept as returned; nothing scored here (see docstring)",
        }
        with out_file:
            json.dump({"summary": summary, "frames": rows}, out_file, indent=1)
        print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"inference request failed: HTTP {e.code}")
    except InferenceResponseError as e:
        sys.exit(str(e))
