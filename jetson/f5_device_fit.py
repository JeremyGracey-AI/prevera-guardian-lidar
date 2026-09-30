#!/usr/bin/env python3
"""F5, device fit: serial latency and memory of one Roboflow Inference model on the Jetson, next to the LIDAR stack.

Reproduces the cost measurement of the 2026-09-27 results, section 5 (C4), for a fine-tuned model, so the
numbers sit in the same columns: the first call is timed on its own (it includes the model pull and load),
then 3 untimed warm-ups, then one request per manifest frame, serially, one in flight at a time, all to
http://127.0.0.1:9001 by default (only literal loopback overrides are accepted; no proxies or redirects).
`MemAvailable` (and jtop GPU % when jtop is usable) is sampled every
0.5 s from before the first call until the last response.

This is a cost measurement, not a room result. The predictions are not kept: only the number of boxes per frame
is recorded, to show the model ran. Reading what the model detected in these frames needs a plan declared
before anyone looks (docs/PROCESS.md), and this file is written so that there is nothing to look at.

Usage:
    f5_device_fit.py <model_id> [--confidence 0.5] [--frames /opt/nvme/frames/floor-trials-1]
                     [--out /opt/nvme/frames/floor-trials-1/f5-<model>.json] [--limit N]

The API key comes from ROBOFLOW_API_KEY in the environment (the caller sources ~/.roboflow.env); it is never
printed and never written to the output file. `--limit N` runs the first N manifest frames only (smoke test).
"""
import argparse
import base64
import json
import os
import platform
import statistics
import sys
import threading
import time
import urllib.error

from inference_http import URL, InferenceResponseError, request_json, validate_base_url


def mem_available_mb():
    """MemAvailable from /proc/meminfo in MB; -1 where there is no /proc (the test runs on a Mac too)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


class Sampler(threading.Thread):
    """MemAvailable, and GPU % through jtop when it is importable and permitted, every 0.5 s."""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop, self.source = [], threading.Event(), "meminfo"

    def run(self):
        try:
            from jtop import jtop
            with jtop() as j:
                self.source = "jtop"
                while not self.stop.is_set() and j.ok():
                    self.samples.append({"t": time.time(), "mem_avail_mb": mem_available_mb(),
                                         "gpu_pct": j.stats.get("GPU")})
                    time.sleep(0.5)
        except Exception as e:  # jtop missing or not permitted: /proc/meminfo only
            self.source = f"meminfo ({type(e).__name__})"
            while not self.stop.is_set():
                self.samples.append({"t": time.time(), "mem_avail_mb": mem_available_mb()})
                time.sleep(0.5)


def infer(model_id, key, confidence, path, url=URL):
    """One request. Returns (response, client_ms). The body is built before the timer starts, as rf_eval.py did."""
    body = json.dumps({
        "model_id": model_id,
        "api_key": key,
        "confidence": confidence,
        "disable_active_learning": True,
        "image": {"type": "base64", "value": base64.b64encode(open(path, "rb").read()).decode()},
    }).encode()
    t = time.perf_counter()
    out = request_json("/infer/object_detection", data=body, timeout=300, url=url)
    return out, (time.perf_counter() - t) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_id")
    ap.add_argument("--confidence", type=float, default=0.5)
    ap.add_argument("--frames", default="/opt/nvme/frames/floor-trials-1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--url", default=URL, help=argparse.SUPPRESS)  # test stub only
    a = ap.parse_args()
    try:
        a.url = validate_base_url(a.url)
    except ValueError as e:
        ap.error(str(e))
    key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not key:
        sys.exit("ROBOFLOW_API_KEY is not set (source ~/.roboflow.env)")
    manifest = json.load(open(f"{a.frames}/manifest.json"))
    if a.limit:
        manifest = manifest[: a.limit]
    tag = a.model_id.replace("/", "_")
    out_path = a.out or f"{a.frames}/f5-{tag}.json"

    info = request_json("/info", url=a.url)
    idle = mem_available_mb()
    sampler = Sampler()
    sampler.start()

    first_path = f"{a.frames}/{manifest[0]['file']}"
    t0 = time.perf_counter()
    try:
        first, _ = infer(a.model_id, key, a.confidence, first_path, url=a.url)
    except urllib.error.HTTPError as e:
        sampler.stop.set()
        sampler.join(timeout=2)
        sys.exit(f"first call failed: HTTP {e.code}")
    first_call_s = time.perf_counter() - t0
    for _ in range(3):
        infer(a.model_id, key, a.confidence, first_path, url=a.url)  # warm-ups, not timed

    lat, server_ms, boxes, errors = [], [], [], 0
    t_run = time.time()
    for m in manifest:
        try:
            out, ms = infer(a.model_id, key, a.confidence, f"{a.frames}/{m['file']}", url=a.url)
        except urllib.error.HTTPError as e:
            errors += 1
            continue
        lat.append(ms)
        if isinstance(out.get("time"), (int, float)):
            server_ms.append(out["time"] * 1000)
        boxes.append(len(out.get("predictions", [])))
    run_s = time.time() - t_run
    sampler.stop.set()
    sampler.join(timeout=2)

    registry = None
    try:
        registry = [e for e in request_json("/model/registry", url=a.url).get("models", []) if a.model_id in json.dumps(e)]
    except Exception as e:  # the registry endpoint is a bonus; the run stands without it
        registry = f"unavailable ({type(e).__name__})"

    lat_sorted = sorted(lat)
    summary = {
        "model": a.model_id,
        "confidence": a.confidence,
        "frames_requested": len(manifest),
        "frames_answered": len(lat),
        "errors": errors,
        "first_call_s": round(first_call_s, 1),
        "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
        "latency_ms_p90": round(lat_sorted[int(0.9 * len(lat_sorted))], 1) if lat else None,
        "fps_serial": round(1000 / statistics.median(lat), 1) if lat else None,
        "server_time_ms_median": round(statistics.median(server_ms), 1) if server_ms else None,
        "mem_avail_idle_mb": idle,
        "mem_avail_min_mb": min((s["mem_avail_mb"] for s in sampler.samples), default=None),
        "gpu_pct_max": max((s.get("gpu_pct") or 0 for s in sampler.samples), default=None),
        "sampler": sampler.source,
        "boxes_total": sum(boxes),
        "frames_with_a_box": sum(1 for b in boxes if b),
        "run_s": round(run_s, 1),
        "server_version": info.get("version"),
        "device": platform.node(),
        "registry_entries_for_model": registry,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_run)),
        "frames_dir": a.frames,
        "note": "cost measurement only; predictions were not kept (see docstring)",
    }
    json.dump({"summary": summary, "latency_ms": [round(x, 1) for x in lat],
               "samples": sampler.samples}, open(out_path, "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"inference request failed: HTTP {e.code}")
    except InferenceResponseError as e:
        sys.exit(str(e))
