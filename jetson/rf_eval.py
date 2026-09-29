#!/usr/bin/env python3
# Verbatim copy (2026-09-28, md5 a219263582e5209f0dd55b9ab72baee9) of /opt/nvme/frames/rf_eval.py on the Jetson: the
# runner behind docs/field-tests/2026-09-27-rfdetr-results.md (sections 2 and 5), versioned here as that document's
# section 7 asked. It keeps `person` boxes, so it is a scoring runner; jetson/f5_device_fit.py supersedes it for cost
# measurements and discards predictions. Not changed on purpose: what ran is what is recorded.
"""Run a local Roboflow Inference model over the floor-trials-1 frames; record detections, latency, memory.

Usage: rf_eval.py <model_id> [confidence]
Reads  /opt/nvme/frames/floor-trials-1/manifest.json (+ the JPEGs beside it).
Writes /opt/nvme/frames/floor-trials-1/results-<model>.json (per frame + summary).
The API key comes from ROBOFLOW_API_KEY in the environment (caller sources ~/.roboflow.env); never printed.
"""
import base64
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

DIR = "/opt/nvme/frames/floor-trials-1"
URL = "http://127.0.0.1:9001/infer/object_detection"
MODEL = sys.argv[1]
CONF = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
KEY = os.environ.get("ROBOFLOW_API_KEY", "")


def mem_available_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return -1


samples, stop = [], threading.Event()


def sampler():
    try:
        from jtop import jtop
        with jtop() as j:
            while not stop.is_set() and j.ok():
                s = j.stats
                samples.append({"t": time.time(), "ram_used_mb": int(j.memory["RAM"]["used"] / 1024),
                                "gpu_pct": s.get("GPU"), "mem_avail_mb": mem_available_mb()})
                time.sleep(0.5)
    except Exception as e:  # jtop missing or not permitted: fall back to /proc/meminfo only
        while not stop.is_set():
            samples.append({"t": time.time(), "mem_avail_mb": mem_available_mb(), "jtop_error": str(e)[:80]})
            time.sleep(0.5)


def infer(path):
    body = json.dumps({"model_id": MODEL, "api_key": KEY, "confidence": CONF,
                       "image": {"type": "base64", "value": base64.b64encode(open(path, "rb").read()).decode()}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    return out, (time.perf_counter() - t) * 1000


man = json.load(open(f"{DIR}/manifest.json"))
idle_avail = mem_available_mb()
th = threading.Thread(target=sampler, daemon=True)
th.start()

t_load = time.perf_counter()
first, first_ms = infer(f"{DIR}/{man[0]['file']}")      # includes model download/compile on first use
load_s = time.perf_counter() - t_load
for _ in range(3):
    infer(f"{DIR}/{man[0]['file']}")                     # warm-up, not timed

rows, lat = [], []
for m in man:
    out, ms = infer(f"{DIR}/{m['file']}")
    lat.append(ms)
    persons = [p for p in out.get("predictions", []) if p.get("class") == "person"]
    best = max(persons, key=lambda p: p["confidence"], default=None)
    rows.append({**m, "latency_ms": round(ms, 1), "n_person": len(persons),
                 "best_conf": round(best["confidence"], 3) if best else 0.0,
                 "best_w": best and best["width"], "best_h": best and best["height"],
                 "best_aspect_wh": round(best["width"] / best["height"], 2) if best else None,
                 "server_time_s": out.get("time"),
                 "persons": [{k: (round(p[k], 3) if isinstance(p[k], float) else p[k]) for k in ("x", "y", "width", "height", "confidence")} for p in persons]})
stop.set()
th.join(timeout=2)

summary = {"model": MODEL, "confidence": CONF, "frames": len(rows), "first_call_s": round(load_s, 1),
           "latency_ms_median": round(statistics.median(lat), 1), "latency_ms_p90": round(sorted(lat)[int(0.9 * len(lat))], 1),
           "fps_serial": round(1000 / statistics.median(lat), 1), "mem_avail_idle_mb": idle_avail,
           "mem_avail_min_mb": min((s["mem_avail_mb"] for s in samples), default=None),
           "gpu_pct_max": max((s.get("gpu_pct") or 0 for s in samples), default=None),
           "sampler": "jtop" if samples and "jtop_error" not in samples[0] else (samples[0].get("jtop_error") if samples else "none")}
by = {}
for r in rows:
    k = (r["segment"], r["camera"])
    b = by.setdefault(k, {"n": 0, "hit": 0, "aspects": []})
    b["n"] += 1
    if r["n_person"]:
        b["hit"] += 1
        b["aspects"].append(r["best_aspect_wh"])
summary["per_segment"] = {f"{s}/{c}": {"frames": v["n"], "person_rate": round(v["hit"] / v["n"], 2),
                                       "median_aspect_wh": statistics.median(v["aspects"]) if v["aspects"] else None}
                          for (s, c), v in sorted(by.items())}
tag = MODEL.replace("/", "_")
json.dump({"summary": summary, "frames": rows}, open(f"{DIR}/results-{tag}.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
