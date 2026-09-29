"""Room-frame plan of 2026-09-29: the runner keeps what the model said, the scorer decides validity and applies the bars.

Two files under test. jetson/rf_room_eval.py runs as a subprocess against a stub Inference server on a free
loopback port, and the stub records every request body, so the test reads what the runner sent. The scorer,
tools/bag_analysis/score_room_frames.py, is imported and fed frames built here: no result of the real run is
in this file, and the bars are written as the plan declares them (docs/field-tests/2026-09-29-room-frames-plan.md).
"""
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "jetson" / "rf_room_eval.py"
SCORER = ROOT / "tools" / "bag_analysis" / "score_room_frames.py"
NAS_RUN = ROOT / "docs" / "field-tests" / "2026-09-28-roboflow" / "arm-A-nas-run.json"
sys.path.insert(0, str(SCORER.parent))
import score_room_frames as srf  # noqa: E402
from score_room_frames import at_least_80, at_most_5, reading, score  # noqa: E402


def box(cls, conf):
    return {"class": cls, "confidence": conf, "x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}


def frames(segment, camera, n, n_lying, other="standing"):
    """n frames of one segment and camera: the first n_lying read lying, the rest read `other`."""
    return [{"file": f"{segment}-{i:03d}s-{camera}.jpg", "segment": segment, "camera": camera, "t_s": i,
             "predictions": [box("lying", 0.9)] if i < n_lying else ([box(other, 0.9)] if other else [])}
            for i in range(n)]


def room(b=(33, 33), f=(30, 30), w=(0, 0)):
    """A whole run of 580 frames: (c920, brio) frames read lying in B, F and W; A, C, D, E all lying."""
    out = []
    for seg, n in (("A", 35), ("C", 34), ("D", 35), ("E", 33)):
        for cam in ("c920", "brio"):
            out += frames(seg, cam, n, n)
    for seg, n, hits in (("B", 33, b), ("F", 30, f), ("W", 90, w)):
        for cam, h in zip(("c920", "brio"), hits):
            out += frames(seg, cam, n, h)
    return out


def declared_summary(**changes):
    s = {"model": srf.MODEL, "confidence": 0.56, "url": "http://127.0.0.1:9001", "limit": None, "complete": True,
         "frames_requested": 580, "frames_answered": 580, "errors": 0,
         "manifest_md5": srf.MANIFEST_MD5, "frames_sha256": srf.FRAMES_SHA256}
    s.update(changes)
    return s


# ---- what is declared

def test_the_declared_model_and_threshold_are_the_ones_the_platform_recorded():
    children = json.loads(NAS_RUN.read_text())["platform_recommended_children"]
    child = next(c for c in children if c["model_id"] == srf.MODEL)
    assert child["f1ConfThresh"] == srf.CONF == 0.56
    assert srf.URL == "http://127.0.0.1:9001"


def test_the_declared_frame_counts_are_the_manifests():
    assert srf.EXPECTED == {"A": 35, "B": 33, "C": 34, "D": 35, "E": 33, "F": 30, "W": 90}
    assert srf.FRAMES == 580 and srf.CAMERAS == ["c920", "brio"]


# ---- the reading of one frame

def test_a_frame_reads_the_pose_of_its_most_confident_pose_box():
    assert reading([box("standing", 0.70), box("lying", 0.91)]) == "lying"
    assert reading([box("standing", 0.91), box("lying", 0.70)]) == "standing"
    assert reading([box("sitting", 0.60)]) == "sitting"


def test_two_boxes_of_one_class_sharing_the_top_confidence_read_that_class():
    assert reading([box("lying", 0.80), box("lying", 0.80)]) == "lying"
    assert reading([box("lying", 0.80), box("lying", 0.80), box("standing", 0.70)]) == "lying"


def test_bed_is_furniture_and_never_a_reading():
    assert reading([box("bed", 0.99), box("lying", 0.60)]) == "lying"
    assert reading([box("bed", 0.99)]) == "none"
    assert reading([box("bed", 0.80), box("lying", 0.80)]) == "lying"


def test_boxes_under_the_threshold_are_dropped_again_by_the_scorer():
    assert reading([box("lying", 0.55)]) == "none"
    assert reading([box("lying", 0.5599999)]) == "none"
    assert reading([box("lying", 0.55), box("standing", 0.57)]) == "standing"
    assert reading([box("lying", 0.56)]) == "lying"


def test_no_box_reads_none_and_a_top_confidence_shared_by_two_classes_reads_tie():
    assert reading([]) == "none"
    assert reading([box("lying", 0.80), box("standing", 0.80)]) == "tie"
    assert reading([box("sitting", 0.80), box("standing", 0.80)]) == "tie"
    assert reading([box("sitting", 0.80), box("standing", 0.80), box("lying", 0.80)]) == "tie"


def test_class_names_are_compared_exactly():
    for name in ("Lying", "LYING", "lying ", "laying", "fall"):
        assert reading([box(name, 0.9)]) == "none", name


# ---- the bars, in exact integers

def test_eighty_percent_is_27_of_33_and_24_of_30():
    assert at_least_80(27, 33) and not at_least_80(26, 33)
    assert at_least_80(24, 30) and not at_least_80(23, 30)
    assert not at_least_80(0, 0)


def test_five_percent_is_4_of_90_and_no_frames_cannot_pass():
    assert at_most_5(4, 90) and not at_most_5(5, 90)
    assert not at_most_5(0, 0)


# ---- R1 and R2 on a valid run

def test_a_whole_synthetic_run_is_valid():
    s = score(room(), declared_summary())
    assert s["valid"] and s["invalid"] == [] and s["frames"] == 580


def test_both_bars_pass_when_one_camera_carries_b_and_f_and_walking_is_not_read_lying():
    s = score(room(b=(27, 0), f=(24, 0), w=(4, 90)), declared_summary())
    assert s["r1"]["pass"] and s["r1"]["carried_by"] == ["c920"]
    assert s["r2"]["pass"] and (s["r2"]["lying"], s["r2"]["n"]) == (4, 90)
    assert s["cells"]["B/c920"]["lying"] == 27 and s["cells"]["B/c920"]["n"] == 33
    # the floor camera read every walking frame as lying: R2 does not see it, the report does
    assert s["cells"]["W/brio"]["lying"] == 90


def test_r1_needs_the_same_camera_in_b_and_in_f():
    s = score(room(b=(33, 0), f=(0, 30)))
    assert s["valid"] and not s["r1"]["pass"] and s["r1"]["carried_by"] == []
    # the looser reading (a camera per segment) is reported beside the verdict, and is not the verdict
    assert s["r1"]["per_segment_reading"] is True


def test_r1_fails_one_frame_under_the_bar():
    assert not score(room(b=(26, 26), f=(30, 30)))["r1"]["pass"]
    assert not score(room(b=(33, 33), f=(23, 23)))["r1"]["pass"]


def test_r2_is_the_counter_camera_only():
    assert score(room(w=(0, 90)))["r2"]["pass"]
    assert not score(room(w=(5, 0)))["r2"]["pass"]


def test_a_tie_counts_against_the_bar_on_both_sides():
    tie = [box("lying", 0.8), box("standing", 0.8)]
    run = [r for r in room() if r["segment"] not in ("B", "W")]
    for cam in ("c920", "brio"):
        b = frames("B", cam, 33, 26)
        b[-1]["predictions"] = tie                      # 26 lying + 1 tie: not 27
        w = frames("W", cam, 90, 4)
        w[-1]["predictions"] = tie                      # 4 lying + 1 tie: counted as 5
        run += b + w
    s = score(run)
    assert s["valid"]
    assert s["cells"]["B/c920"]["tie"] == 1 and not s["r1"]["pass"]
    assert (s["r2"]["lying"], s["r2"]["tie"]) == (4, 1) and not s["r2"]["pass"]
    assert "r1 B/c920 read tie: B-032s-c920.jpg" in s["failing"]
    assert "r2 W/c920 read tie: W-089s-c920.jpg" in s["failing"]


def test_the_other_lying_segments_are_reported_with_no_verdict():
    s = score(room())
    for seg in ("A", "C", "D", "E"):
        for cam in ("c920", "brio"):
            assert s["cells"][f"{seg}/{cam}"]["lying"] == s["cells"][f"{seg}/{cam}"]["n"]
    assert "r3" not in s


def test_failing_frames_are_named():
    s = score(room(b=(32, 33), f=(30, 30), w=(1, 0)))
    assert "r1 B/c920 read standing: B-032s-c920.jpg" in s["failing"]
    assert "r2 W/c920 read lying: W-000s-c920.jpg" in s["failing"]
    assert not [line for line in s["failing"] if line.startswith("r2 W/brio")]


def test_bed_boxes_are_counted_per_cell_at_the_declared_confidence():
    run = room()
    run[0]["predictions"] += [box("bed", 0.9), box("bed", 0.55)]
    assert score(run)["cells"]["A/c920"]["bed_boxes"] == 1


# ---- a run that is not the declared run gets no verdict

def invalid(frames_, summary=None):
    s = score(frames_, summary)
    assert not s["valid"] and s["r1"] is None and s["r2"] is None and s["failing"] == []
    return " | ".join(s["invalid"])


def test_a_server_that_stops_answering_is_not_a_pass():
    run = room()
    order = {"c920": 0, "brio": 1}
    run.sort(key=lambda r: (order[r["camera"]], r["segment"] == "W", r["segment"], r["t_s"]))
    for r in run[200:]:                                   # A to F on c920 answered, everything after failed
        r["predictions"], r["error"] = [], "URLError"
    why = invalid(run, declared_summary(frames_answered=200, errors=380))
    assert "380 request errors" in why
    s = score(run)
    assert s["cells"]["W/c920"] == {"n": 90, "lying": 0, "standing": 0, "sitting": 0, "none": 0, "tie": 0,
                                    "error": 90, "bed_boxes": 0}


def test_one_request_error_is_enough():
    run = room()
    run[5]["predictions"], run[5]["error"] = [], "HTTP 500"
    assert "1 request errors, first: A-005s-c920.jpg" in invalid(run)


def test_a_row_with_an_error_is_not_read_from_its_predictions():
    run = room()
    run[0]["error"] = "HTTP 500"                          # predictions left in place on purpose
    run[0]["predictions"] = [box("lying", 0.9), box("bed", 0.9)]
    c = score(run)["cells"]["A/c920"]
    assert (c["error"], c["lying"], c["bed_boxes"]) == (1, 34, 0)


def test_a_file_that_is_not_the_whole_manifest_gets_no_verdict():
    three = [frames("B", "c920", 1, 1)[0], frames("F", "c920", 1, 1)[0], frames("W", "c920", 1, 0)[0]]
    assert "3 rows, the manifest has 580" in invalid(three)
    trimmed = [r for r in room() if not (r["segment"] == "B" and r["camera"] == "c920" and r["t_s"] >= 5)]
    assert "B/c920 has 5 rows, declared 33" in invalid(trimmed)
    twice = room() + [room()[0]]
    assert "file twice: A-000s-c920.jpg" in invalid(twice)


def test_a_camera_or_segment_the_plan_does_not_name_gets_no_verdict():
    run = room(w=(90, 0))
    for r in run:
        if r["segment"] == "W" and r["camera"] == "c920" and r["t_s"] >= 3:
            r["camera"] = "C920"
    why = invalid(run)
    assert "unexpected group W/C920: 87 rows" in why and "W/c920 has 3 rows, declared 90" in why


def test_a_class_name_outside_the_four_means_the_harness_does_not_match_the_model():
    run = room()
    for r in run:
        for p in r["predictions"]:
            p["class"] = p["class"].capitalize()
    why = invalid(run)
    assert "class names outside the declared four" in why and "'Lying' x" in why and "'Standing' x" in why


def test_a_prediction_without_a_confidence_is_a_defect_and_not_a_crash():
    run = room()
    run[0]["predictions"] = [{"class": "lying", "confidence": None, "x": 1, "y": 2, "width": 3, "height": 4}]
    assert "1 predictions without a class or a confidence, first in: A-000s-c920.jpg" in invalid(run)


@pytest.mark.parametrize("field, value", [
    ("model", "jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--00ba18"),
    ("confidence", 0.9),
    ("confidence", 0.4),
    ("url", "http://192.0.2.1:9001"),
    ("limit", 580),
    ("complete", False),
    ("frames_requested", 579),
    ("frames_answered", 579),
    ("errors", 1),
    ("manifest_md5", "0" * 32),
    ("frames_sha256", "0" * 64),
])
def test_a_summary_that_is_not_the_declared_run_gets_no_verdict(field, value):
    assert f"summary {field} is {value!r}" in invalid(room(), declared_summary(**{field: value}))


def test_a_summary_that_leaves_a_field_out_gets_no_verdict():
    s = declared_summary()
    del s["frames_sha256"], s["url"]
    why = invalid(room(), s)
    assert "summary frames_sha256 is 'missing'" in why and "summary url is 'missing'" in why


# ---- the scorer's command line

def _cli(tmp_path, frames_, summary):
    path = tmp_path / "room.json"
    path.write_text(json.dumps({"summary": summary, "frames": frames_}))
    return subprocess.run([sys.executable, str(SCORER), str(path)], capture_output=True, text=True, timeout=60)


def test_the_printed_r1_verdict_is_the_same_camera_reading(tmp_path):
    proc = _cli(tmp_path, room(b=(33, 0), f=(0, 30), w=(5, 0)), declared_summary())
    assert proc.returncode == 0, proc.stderr
    r1, r2 = [line for line in proc.stdout.splitlines() if line.startswith(("R1 ", "R2 "))]
    assert ": FAIL" in r1 and "carried by no camera" in r1 and "a camera per segment would clear it" in r1
    assert ": FAIL" in r2 and "5 lying + 0 tie of 90" in r2


def test_a_passing_run_prints_pass_twice_and_exits_zero(tmp_path):
    proc = _cli(tmp_path, room(w=(4, 0)), declared_summary())
    assert proc.returncode == 0
    assert proc.stdout.count(": PASS") == 2 and "INVALID" not in proc.stdout


def test_an_invalid_run_prints_no_verdict_and_exits_two(tmp_path):
    proc = _cli(tmp_path, room(), declared_summary(confidence=0.9))
    assert proc.returncode == 2
    assert "INVALID RUN: no verdict" in proc.stdout and "summary confidence is 0.9, declared 0.56" in proc.stdout
    assert not [line for line in proc.stdout.splitlines() if line.startswith(("R1 ", "R2 "))]
    assert "PASS" not in proc.stdout and "FAIL" not in proc.stdout


# ---- the runner

def _runner_module():
    spec = importlib.util.spec_from_file_location("rf_room_eval", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Stub(BaseHTTPRequestHandler):
    bodies = []

    def log_message(self, *_):  # keep pytest output clean
        pass

    def _send(self, data, length=None):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data) if length is None else length))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/info":
            self._send(json.dumps({"version": "stub-1.7.2"}).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        _Stub.bodies.append((self.path, body))
        image = base64.b64decode(body["image"]["value"])
        if image == b"broken":
            self.send_error(500)
        elif image == b"garbage":
            self._send(b"<html>not json</html>")
        elif image == b"short":
            self._send(b'{"predictions": [', length=4000)
            self.close_connection = True
        elif image == b"nokey":
            self._send(json.dumps({"message": "model not found"}).encode())
        else:
            first, second = ("lying", "standing") if image == b"down" else ("standing", "lying")
            self._send(json.dumps({"time": 0.06, "predictions": [
                {"x": 5.0, "y": 6.0, "width": 7.0, "height": 8.0, "confidence": 0.7, "class": "bed", "class_id": 0},
                {"x": 1.5, "y": 2.5, "width": 3.5, "height": 4.5, "confidence": 0.8744123, "class": first,
                 "class_id": 1, "detection_id": "abc"},
                {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0, "confidence": 0.8712456, "class": second,
                 "class_id": 2}]}).encode())


def tags(name, segment, t_s, camera, lying):
    return {"file": name, "segment": segment, "t_s": t_s, "camera": camera, "pose": "as-tagged",
            "lidar": "as-tagged", "lying": lying}


MANIFEST = [tags("B-094s-c920.jpg", "B", 94, "c920", True), tags("W-300s-c920.jpg", "W", 300, "c920", False),
            tags("F-200s-brio.jpg", "F", 200, "brio", True)]
IMAGES = {"B-094s-c920.jpg": b"down", "W-300s-c920.jpg": b"up", "F-200s-brio.jpg": b"broken"}


def _run(tmp_path, manifest=MANIFEST, images=IMAGES, args=("--confidence", "0.56"), out="out.json", check=True):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(exist_ok=True)
    for name, data in images.items():
        (frames_dir / name).write_bytes(data)
    (frames_dir / "manifest.json").write_text(json.dumps(manifest))
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, "ROBOFLOW_API_KEY": "test-key-not-real"}
    _Stub.bodies.clear()
    cmd = [sys.executable, str(RUNNER), "ws/model--abc", "--frames", str(frames_dir),
           "--url", f"http://127.0.0.1:{port}", *args]
    if out:
        cmd += ["--out", str(tmp_path / out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    finally:
        server.shutdown()
    if check:
        assert proc.returncode == 0, proc.stderr
    written = json.loads((tmp_path / out).read_text()) if out and (tmp_path / out).exists() else None
    return written, proc, [b for _, b in _Stub.bodies], port


def test_the_runners_defaults_are_the_declared_ones():
    mod = _runner_module()
    assert mod.URL == srf.URL == "http://127.0.0.1:9001"
    assert mod.CONFIDENCE == srf.CONF == 0.56


def test_runner_sends_one_request_per_manifest_frame_to_the_inference_route(tmp_path):
    written, _, bodies, port = _run(tmp_path)
    assert len(bodies) == 3 and {path for path, _ in _Stub.bodies} == {"/infer/object_detection"}
    assert all(set(b) == {"model_id", "api_key", "confidence", "disable_active_learning", "image"} for b in bodies)
    assert all(b["disable_active_learning"] is True for b in bodies)
    assert all(b["confidence"] == 0.56 and b["model_id"] == "ws/model--abc" for b in bodies)
    assert [base64.b64decode(b["image"]["value"]) for b in bodies] == [b"down", b"up", b"broken"]
    s = written["summary"]
    assert (s["frames_requested"], s["frames_answered"], s["errors"], s["complete"]) == (3, 2, 1, True)
    assert s["model"] == "ws/model--abc" and s["server_version"] == "stub-1.7.2" and s["limit"] is None
    assert s["url"] == f"http://127.0.0.1:{port}"


def test_the_confidence_sent_without_the_flag_is_the_declared_one(tmp_path):
    written, _, bodies, _ = _run(tmp_path, args=())
    assert all(b["confidence"] == 0.56 for b in bodies) and written["summary"]["confidence"] == 0.56


def test_runner_keeps_every_box_unrounded_and_in_the_order_returned(tmp_path):
    written, _, _, _ = _run(tmp_path)
    assert [r["file"] for r in written["frames"]] == [m["file"] for m in MANIFEST]
    b = written["frames"][0]
    assert (b["segment"], b["camera"], b["t_s"]) == ("B", "c920", 94)
    assert [(p["class"], p["confidence"]) for p in b["predictions"]] == [
        ("bed", 0.7), ("lying", 0.8744123), ("standing", 0.8712456)]
    assert all(set(p) == {"class", "confidence", "x", "y", "width", "height"} for p in b["predictions"])
    assert b["predictions"][1]["x"] == 1.5 and b["predictions"][1]["height"] == 4.5
    assert written["frames"][1]["predictions"][1]["class"] == "standing"


def test_the_summary_pins_the_manifest_and_the_frames_that_were_sent(tmp_path):
    written, _, _, _ = _run(tmp_path)
    s = written["summary"]
    assert s["manifest_md5"] == hashlib.md5(json.dumps(MANIFEST).encode()).hexdigest()
    assert s["frames_sha256"] == hashlib.sha256(b"down" + b"up" + b"broken").hexdigest()


def test_whatever_goes_wrong_with_a_frame_is_a_row_and_the_run_goes_on(tmp_path):
    names = ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"]
    manifest = [tags(n, "B", i, "c920", True) for i, n in enumerate(names)]
    images = {"a.jpg": b"broken", "b.jpg": b"garbage", "c.jpg": b"short", "d.jpg": b"nokey", "f.jpg": b"down"}
    written, _, bodies, _ = _run(tmp_path, manifest=manifest, images=images)    # e.jpg is not on disk
    rows = written["frames"]
    assert [r["file"] for r in rows] == names and len(bodies) == 5
    assert rows[0]["error"] == "HTTP 500"
    assert rows[1]["error"].startswith("JSONDecodeError")
    assert rows[2]["error"].split(":")[0] in ("IncompleteRead", "JSONDecodeError", "RemoteDisconnected")
    assert rows[3]["error"] == "ValueError: no predictions in the response"
    assert rows[4]["error"].startswith("FileNotFoundError")
    assert all(r["predictions"] == [] and "latency_ms" not in r for r in rows[:5])
    assert "error" not in rows[5] and rows[5]["predictions"][1]["class"] == "lying"
    s = written["summary"]
    assert (s["frames_requested"], s["frames_answered"], s["errors"], s["complete"]) == (6, 1, 5, True)


def test_runner_output_carries_no_key_and_no_verdict(tmp_path):
    written, proc, _, _ = _run(tmp_path)
    assert "test-key-not-real" not in json.dumps(written) + proc.stdout + proc.stderr
    assert json.loads(proc.stdout) == written["summary"]
    assert not {"r1", "r2", "verdict", "valid", "per_segment", "lying_rate"} & set(written["summary"])
    allowed = set(MANIFEST[0]) | {"predictions", "latency_ms", "error"}
    assert all(set(r) <= allowed for r in written["frames"])


def test_runner_never_writes_over_a_file(tmp_path):
    first, _, _, _ = _run(tmp_path)
    before = (tmp_path / "out.json").read_bytes()
    _, proc, bodies, _ = _run(tmp_path, images={**IMAGES, "B-094s-c920.jpg": b"up"}, check=False)
    assert proc.returncode != 0 and "is not written over" in proc.stderr
    assert bodies == [] and (tmp_path / "out.json").read_bytes() == before
    assert first["frames"][0]["predictions"][1]["class"] == "lying"


def test_a_limited_run_is_a_smoke_test_with_its_own_file_name(tmp_path):
    _, proc, bodies, _ = _run(tmp_path, args=("--limit", "2"), out=None)
    assert proc.returncode == 0 and len(bodies) == 2
    smoke = tmp_path / "frames" / "room-smoke-ws_model--abc.json"
    assert smoke.exists() and not (tmp_path / "frames" / "room-ws_model--abc.json").exists()
    s = json.loads(smoke.read_text())["summary"]
    assert (s["limit"], s["frames_requested"], s["complete"]) == (2, 2, True)


def test_a_limit_of_zero_is_refused(tmp_path):
    _, proc, bodies, _ = _run(tmp_path, args=("--limit", "0"), check=False)
    assert proc.returncode != 0 and bodies == [] and not (tmp_path / "out.json").exists()


def test_the_scorer_gives_the_runners_three_frame_file_cells_and_no_verdict(tmp_path):
    written, _, _, _ = _run(tmp_path)
    s = score(written["frames"], written["summary"])
    assert not s["valid"] and s["r1"] is None and s["r2"] is None
    assert s["cells"]["B/c920"]["lying"] == 1 and s["cells"]["B/c920"]["bed_boxes"] == 1
    assert s["cells"]["W/c920"]["standing"] == 1 and s["cells"]["F/brio"]["error"] == 1
    why = " | ".join(s["invalid"])
    assert "summary model is 'ws/model--abc'" in why and "3 rows, the manifest has 580" in why
