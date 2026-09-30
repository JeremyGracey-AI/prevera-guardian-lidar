"""Room-frame plan of 2026-09-29: the runner keeps what the model said, the scorer decides validity and applies the bars.

Two files under test. jetson/rf_room_eval.py runs as a subprocess against a stub Inference server on a free
loopback port, and the stub records every request body, so the test reads what the runner sent. The scorer,
tools/bag_analysis/score_room_frames.py, is imported and fed frames built here from the manifest's layout (file
names and tags, which the plan publishes): no result of the real run is in this file, and the bars are written
as the plan declares them (docs/field-tests/2026-09-29-room-frames-plan.md).
"""
import base64
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
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

CAMERAS = ("c920", "brio")
LAYOUT = (("A", 28, 35), ("B", 94, 33), ("C", 157, 34), ("D", 238, 35), ("E", 302, 33), ("F", 370, 30),
          ("W", 430, 90))                       # segment, first second, frames: the manifest, camera by camera


def box(cls, conf):
    return {"class": cls, "confidence": conf, "x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}


def room(b=(33, 33), f=(30, 30), w=(0, 0)):
    """The 580 manifest rows in manifest order. (c920, brio) frames read lying in B, F and W, counted from the
    start of the segment; the rest of those segments read standing; A, C, D and E all read lying."""
    lying = {"B": dict(zip(CAMERAS, b)), "F": dict(zip(CAMERAS, f)), "W": dict(zip(CAMERAS, w))}
    return [{"file": f"{seg}-{start + i:03d}s-{cam}.jpg", "segment": seg, "camera": cam, "t_s": start + i,
             "predictions": [box("lying" if i < lying.get(seg, {}).get(cam, n) else "standing", 0.9)]}
            for cam in CAMERAS for seg, start, n in LAYOUT for i in range(n)]


def at(run, name):
    return next(r for r in run if r["file"] == name)


def declared_summary(frames_, **changes):
    s = {"model": srf.MODEL, "confidence": 0.56, "url": "http://127.0.0.1:9001", "server_version": "1.7.2",
         "complete": True, "frames_requested": 580, "frames_answered": 580, "errors": 0,
         "manifest_md5": srf.MANIFEST_MD5, "frames_sha256": srf.FRAMES_SHA256,
         "rows_sha256": srf.rows_digest(frames_)}
    s.update(changes)
    return s


def scored(frames_, **changes):
    return score(frames_, declared_summary(frames_, **changes))


# ---- what is declared

def test_the_declared_model_and_threshold_are_the_ones_the_platform_recorded():
    children = json.loads(NAS_RUN.read_text())["platform_recommended_children"]
    child = next(c for c in children if c["model_id"] == srf.MODEL)
    assert child["f1ConfThresh"] == srf.CONF == 0.56
    assert srf.URL == "http://127.0.0.1:9001" and srf.SERVER == "1.7.2"


def test_the_declared_frames_are_the_manifests():
    assert srf.EXPECTED == {seg: n for seg, _, n in LAYOUT}
    assert srf.FRAMES == 580 == len(room()) and srf.CAMERAS == list(CAMERAS)
    assert srf.names_digest(room()) == srf.FILES_SHA256 \
        == "34ff824c94479bcc64d8a9f7217c6497346c8ed22a04b62b4ac09cb70d43dfc0"
    assert srf.MANIFEST_MD5 == "9da67efcc98c6ffd2bbbeb4fb1d82d1d"
    assert srf.FRAMES_SHA256 == "a6d168682234a74af0a01c3c790baf1961e3795a4a0d060d7aa428d2b27d6cc7"


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
    s = scored(room())
    assert s["valid"] and s["invalid"] == [] and s["frames"] == 580


def test_both_bars_pass_when_one_camera_carries_b_and_f_and_walking_is_not_read_lying():
    s = scored(room(b=(27, 0), f=(24, 0), w=(4, 90)))
    assert s["r1"]["pass"] and s["r1"]["carried_by"] == ["c920"]
    assert s["r2"]["pass"] and (s["r2"]["lying"], s["r2"]["n"]) == (4, 90)
    assert s["cells"]["B/c920"]["lying"] == 27 and s["cells"]["B/c920"]["n"] == 33
    # the floor camera read every walking frame as lying: R2 does not see it, the report does
    assert s["cells"]["W/brio"]["lying"] == 90


def test_r1_needs_the_same_camera_in_b_and_in_f():
    s = scored(room(b=(33, 0), f=(0, 30)))
    assert s["valid"] and not s["r1"]["pass"] and s["r1"]["carried_by"] == []
    # the looser reading (a camera per segment) is reported beside the verdict, and is not the verdict
    assert s["r1"]["per_segment_reading"] is True


def test_r1_fails_one_frame_under_the_bar():
    assert not scored(room(b=(26, 26), f=(30, 30)))["r1"]["pass"]
    assert not scored(room(b=(33, 33), f=(23, 23)))["r1"]["pass"]


def test_r2_is_the_counter_camera_only():
    assert scored(room(w=(0, 90)))["r2"]["pass"]
    assert not scored(room(w=(5, 0)))["r2"]["pass"]


def test_a_tie_counts_against_the_bar_on_both_sides():
    tie = [box("lying", 0.8), box("standing", 0.8)]
    run = room(b=(26, 26), w=(4, 4))
    for cam in CAMERAS:
        at(run, f"B-126s-{cam}.jpg")["predictions"] = tie        # 26 lying + 1 tie: not 27
        at(run, f"W-519s-{cam}.jpg")["predictions"] = tie        # 4 lying + 1 tie: counted as 5
    s = scored(run)
    assert s["valid"]
    assert s["cells"]["B/c920"]["tie"] == 1 and not s["r1"]["pass"]
    assert (s["r2"]["lying"], s["r2"]["tie"]) == (4, 1) and not s["r2"]["pass"]
    assert "r1 B/c920 read tie: B-126s-c920.jpg" in s["failing"]
    assert "r2 W/c920 read tie: W-519s-c920.jpg" in s["failing"]


def test_the_other_lying_segments_are_reported_with_no_verdict():
    s = scored(room())
    for seg in ("A", "C", "D", "E"):
        for cam in CAMERAS:
            assert s["cells"][f"{seg}/{cam}"]["lying"] == s["cells"][f"{seg}/{cam}"]["n"]
    assert "r3" not in s


def test_failing_frames_are_named():
    s = scored(room(b=(32, 33), f=(30, 30), w=(1, 0)))
    assert "r1 B/c920 read standing: B-126s-c920.jpg" in s["failing"]
    assert "r2 W/c920 read lying: W-430s-c920.jpg" in s["failing"]
    assert not [line for line in s["failing"] if line.startswith("r2 W/brio")]


def test_bed_boxes_are_counted_per_cell_at_the_declared_confidence():
    run = room()
    run[0]["predictions"] += [box("bed", 0.9), box("bed", 0.55)]
    assert scored(run)["cells"]["A/c920"]["bed_boxes"] == 1


# ---- a run that is not the declared run gets no verdict, and shows no reading

def invalid(frames_, summary=None):
    s = score(frames_, summary)
    assert not s["valid"] and s["r1"] is None and s["r2"] is None and s["failing"] == []
    assert all(set(c) == {"n", "error"} for c in s["cells"].values())
    return " | ".join(s["invalid"])


def test_a_server_that_stops_answering_is_not_a_pass():
    run = room()
    for r in run[200:]:                                   # A to F on c920 answered, everything after failed
        r["predictions"], r["error"] = [], "URLError"
    why = invalid(run, declared_summary(run, frames_answered=200, errors=380))
    assert "380 request errors, first: W-430s-c920.jpg" in why
    assert score(run)["cells"]["W/c920"] == {"n": 90, "error": 90}


def test_one_request_error_is_enough_even_when_the_summary_hides_it():
    run = room()
    run[5]["predictions"], run[5]["error"] = [], "HTTP 500"
    assert "1 request errors, first: A-033s-c920.jpg" in invalid(run, declared_summary(run))


def test_a_row_with_an_error_is_never_read_from_its_predictions():
    run = room()
    run[0]["error"] = "HTTP 500"                          # predictions left in place on purpose
    assert score(run)["cells"]["A/c920"] == {"n": 35, "error": 1}


def test_a_file_that_is_not_the_whole_manifest_gets_no_verdict():
    three = [at(room(), n) for n in ("B-094s-c920.jpg", "F-370s-c920.jpg", "W-430s-c920.jpg")]
    assert "3 rows, the manifest has 580" in invalid(three, declared_summary(three))
    trimmed = [r for r in room() if not (r["segment"] == "B" and r["camera"] == "c920" and r["t_s"] >= 99)]
    assert "B/c920 has 5 rows, declared 33" in invalid(trimmed, declared_summary(trimmed))
    twice = room() + [room()[0]]
    assert "file twice: A-028s-c920.jpg" in invalid(twice, declared_summary(twice))


def test_rows_under_other_names_or_in_another_order_get_no_verdict():
    renamed = room()
    for i, r in enumerate(renamed):
        r["file"] = f"x{i}.jpg"
    assert "not the manifest's files in the manifest's order" in invalid(renamed, declared_summary(renamed))
    swapped = room()
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert "not the manifest's files in the manifest's order" in invalid(swapped, declared_summary(swapped))


def test_a_camera_or_segment_the_plan_does_not_name_gets_no_verdict():
    run = room(w=(90, 0))
    for r in run:
        if r["segment"] == "W" and r["camera"] == "c920" and r["t_s"] >= 433:
            r["camera"] = "C920"
    why = invalid(run, declared_summary(run))
    assert "unexpected group W/C920: 87 rows" in why and "W/c920 has 3 rows, declared 90" in why


def test_a_class_name_outside_the_four_means_the_harness_does_not_match_the_model():
    run = room()
    for r in run:
        for p in r["predictions"]:
            p["class"] = p["class"].capitalize()
    why = invalid(run, declared_summary(run))
    assert "class names outside the declared four" in why and "'Lying' x" in why and "'Standing' x" in why


def test_a_prediction_without_a_confidence_is_a_defect_and_not_a_crash():
    run = room()
    run[0]["predictions"] = [{"class": "lying", "confidence": None, "x": 1, "y": 2, "width": 3, "height": 4}]
    assert "1 predictions without a class or a confidence, first in: A-028s-c920.jpg" \
        in invalid(run, declared_summary(run))


@pytest.mark.parametrize("field, value", [
    ("model", "jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--00ba18"),
    ("confidence", 0.9),
    ("confidence", 0.4),
    ("url", "http://192.0.2.1:9001"),
    ("url", "http://localhost:9001"),
    ("server_version", "1.7.3"),
    ("complete", False),
    ("complete", 1),
    ("frames_requested", 579),
    ("frames_requested", 580.0),
    ("frames_answered", 579),
    ("errors", 1),
    ("errors", False),
    ("manifest_md5", "0" * 32),
    ("frames_sha256", "0" * 64),
])
def test_a_summary_that_is_not_the_declared_run_gets_no_verdict(field, value):
    run = room()
    assert f"summary {field} is {value!r}" in invalid(run, declared_summary(run, **{field: value}))


def test_a_summary_that_leaves_a_field_out_gets_no_verdict():
    run = room()
    s = declared_summary(run)
    del s["frames_sha256"], s["url"], s["rows_sha256"]
    why = invalid(run, s)
    assert "summary frames_sha256 is 'missing'" in why and "summary url is 'missing'" in why
    assert "rows_sha256 is not the digest of the rows" in why


def test_a_row_edited_after_the_run_shows():
    run = room(w=(5, 0))
    summary = declared_summary(run)
    at(run, "W-434s-c920.jpg")["predictions"] = [box("standing", 0.9)]      # 5 lying made 4, by hand
    assert "rows_sha256 is not the digest of the rows" in invalid(run, summary)


# ---- the scorer's command line

def _cli(tmp_path, frames_, summary, text=None):
    path = tmp_path / "room.json"
    path.write_text(text if text is not None else json.dumps({"summary": summary, "frames": frames_}))
    return subprocess.run([sys.executable, str(SCORER), str(path)], capture_output=True, text=True, timeout=60)


def test_the_printed_r1_verdict_is_the_same_camera_reading(tmp_path):
    run = room(b=(33, 0), f=(0, 30), w=(5, 0))
    proc = _cli(tmp_path, run, declared_summary(run))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    r1, r2 = [line for line in proc.stdout.splitlines() if line.startswith(("R1 ", "R2 "))]
    assert ": FAIL" in r1 and "carried by no camera" in r1 and "a camera per segment would clear it" in r1
    assert ": FAIL" in r2 and "5 lying + 0 tie of 90" in r2


def test_a_passing_run_prints_pass_twice_and_exits_zero(tmp_path):
    run = room(w=(4, 0))
    proc = _cli(tmp_path, run, declared_summary(run))
    assert proc.returncode == 0
    assert proc.stdout.count(": PASS") == 2 and "INVALID" not in proc.stdout
    assert [line for line in proc.stdout.splitlines() if line.startswith("B/c920")]


def test_an_invalid_run_prints_its_reasons_and_nothing_a_verdict_could_be_read_from(tmp_path):
    run = room(b=(26, 26), w=(9, 9))
    proc = _cli(tmp_path, run, declared_summary(run, confidence=0.9))
    assert proc.returncode == 2
    assert "INVALID RUN: no verdict" in proc.stdout and "summary confidence is 0.9, declared 0.56" in proc.stdout
    body = proc.stdout.split("INVALID RUN", 1)[0] + proc.stdout
    assert "PASS" not in body and "FAIL" not in body
    assert not [line for line in proc.stdout.splitlines() if line[:2] in ("R1", "R2") or "/c920" in line
                or "/brio" in line or "lying" in line]


def test_a_file_that_is_not_json_is_an_invalid_run(tmp_path):
    for text in ('{"summary": {"model": ', "", '{"frames": []}', "[]"):
        proc = _cli(tmp_path, None, None, text=text)
        assert proc.returncode == 2 and "INVALID RUN" in proc.stdout and "Traceback" not in proc.stderr, text


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
            self._send(json.dumps({"message": "model not found " + "x" * 400}).encode())
        else:
            if image == b"slow":
                time.sleep(0.25)
            first, second = ("lying", "standing") if image in (b"down", b"slow") else ("standing", "lying")
            self._send(json.dumps({"time": 0.06, "predictions": [
                {"x": 5.0, "y": 6.0, "width": 7.0, "height": 8.0, "confidence": 0.7, "class": "bed", "class_id": 0},
                {"x": 1.5, "y": 2.5, "width": 3.5, "height": 4.5, "confidence": 0.8744123, "class": first,
                 "class_id": 1, "detection_id": "abc"},
                {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0, "confidence": 0.8712456, "class": second,
                 "class_id": 2}]}).encode())


class _Quiet(HTTPServer):
    def handle_error(self, *_):  # a runner killed mid-request breaks the pipe; that is the test, not a failure
        pass


def tags(name, segment, t_s, camera, lying):
    return {"file": name, "segment": segment, "t_s": t_s, "camera": camera, "pose": "as-tagged",
            "lidar": "as-tagged", "lying": lying}


MANIFEST = [tags("B-094s-c920.jpg", "B", 94, "c920", True), tags("W-430s-c920.jpg", "W", 430, "c920", False),
            tags("F-370s-brio.jpg", "F", 370, "brio", True)]
IMAGES = {"B-094s-c920.jpg": b"down", "W-430s-c920.jpg": b"up", "F-370s-brio.jpg": b"broken"}


def _stage(tmp_path, manifest, images):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(exist_ok=True)
    for name, data in images.items():
        (frames_dir / name).write_bytes(data)
    (frames_dir / "manifest.json").write_text(json.dumps(manifest))
    server = _Quiet(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Stub.bodies.clear()
    cmd = [sys.executable, str(RUNNER), "ws/model--abc", "--frames", str(frames_dir),
           "--url", f"http://127.0.0.1:{server.server_address[1]}"]
    return server, cmd, {**os.environ, "ROBOFLOW_API_KEY": "test-key-not-real"}


def _run(tmp_path, manifest=MANIFEST, images=IMAGES, args=("--confidence", "0.56"), out="out.json", check=True,
         env=None):
    server, cmd, base_env = _stage(tmp_path, manifest, images)
    cmd += list(args) + (["--out", str(tmp_path / out)] if out else [])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env={**base_env, **(env or {})}, timeout=60)
    finally:
        server.shutdown()
    if check:
        assert proc.returncode == 0, proc.stderr
    written = json.loads((tmp_path / out).read_text()) if out and (tmp_path / out).exists() else None
    return written, proc, [b for _, b in _Stub.bodies], server.server_address[1]


def test_the_runners_defaults_are_the_declared_ones():
    mod = _runner_module()
    assert mod.URL == srf.URL == "http://127.0.0.1:9001"
    assert mod.CONFIDENCE == srf.CONF == 0.56
    rows = room()[:3]
    assert mod.rows_digest(rows) == srf.rows_digest(rows)


def test_runner_sends_one_request_per_manifest_frame_to_the_inference_route(tmp_path):
    written, _, bodies, port = _run(tmp_path)
    assert len(bodies) == 3 and {path for path, _ in _Stub.bodies} == {"/infer/object_detection"}
    assert all(set(b) == {"model_id", "api_key", "confidence", "disable_active_learning", "image"} for b in bodies)
    assert all(b["disable_active_learning"] is True for b in bodies)
    assert all(b["confidence"] == 0.56 and b["model_id"] == "ws/model--abc" for b in bodies)
    assert [base64.b64decode(b["image"]["value"]) for b in bodies] == [b"down", b"up", b"broken"]
    s = written["summary"]
    assert (s["frames_requested"], s["frames_answered"], s["errors"], s["complete"]) == (3, 2, 1, True)
    assert s["model"] == "ws/model--abc" and s["server_version"] == "stub-1.7.2"
    assert s["url"] == f"http://127.0.0.1:{port}" and "limit" not in s


def test_the_confidence_sent_without_the_flag_is_the_declared_one(tmp_path):
    written, _, bodies, _ = _run(tmp_path, args=())
    assert all(b["confidence"] == 0.56 for b in bodies) and written["summary"]["confidence"] == 0.56


def test_a_proxy_in_the_environment_is_not_used(tmp_path):
    dead = "http://127.0.0.1:9"                           # the discard port: nothing answers there
    written, _, bodies, _ = _run(tmp_path, env={"http_proxy": dead, "HTTP_PROXY": dead, "all_proxy": dead,
                                                "ALL_PROXY": dead, "no_proxy": "", "NO_PROXY": ""})
    assert len(bodies) == 3 and written["summary"]["frames_answered"] == 2


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


def test_the_summary_pins_the_manifest_the_frames_and_the_rows(tmp_path):
    written, _, _, _ = _run(tmp_path)
    s = written["summary"]
    assert s["manifest_md5"] == hashlib.md5(json.dumps(MANIFEST).encode()).hexdigest()
    assert s["frames_sha256"] == hashlib.sha256(b"down" + b"up" + b"broken").hexdigest()
    assert s["rows_sha256"] == srf.rows_digest(written["frames"])


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
    assert all(r["predictions"] == [] and "latency_ms" not in r and len(r["error"]) <= 120 for r in rows[:5])
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


def test_an_output_that_cannot_be_created_stops_the_run_before_the_first_request(tmp_path):
    _, proc, bodies, _ = _run(tmp_path, out="no-such-directory/out.json", check=False)
    assert proc.returncode != 0 and "cannot be created" in proc.stderr and "Traceback" not in proc.stderr
    assert bodies == []


def test_the_default_output_is_named_after_the_model_and_there_is_no_smoke_mode(tmp_path):
    _, proc, bodies, _ = _run(tmp_path, out=None)
    assert proc.returncode == 0 and len(bodies) == 3
    assert (tmp_path / "frames" / "room-ws_model--abc.json").exists()
    _, proc, bodies, _ = _run(tmp_path, args=("--limit", "2"), out="limited.json", check=False)
    assert proc.returncode == 2 and "unrecognized arguments" in proc.stderr
    assert bodies == [] and not (tmp_path / "limited.json").exists()


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_an_interrupted_run_leaves_its_rows_and_says_it_is_not_complete(tmp_path, sig):
    names = [f"s{i:02d}.jpg" for i in range(40)]
    server, cmd, env = _stage(tmp_path, [tags(n, "W", i, "c920", False) for i, n in enumerate(names)],
                              {n: b"slow" for n in names})
    out = tmp_path / "out.json"
    proc = subprocess.Popen(cmd + ["--out", str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        deadline = time.time() + 30
        while len(_Stub.bodies) < 3 and time.time() < deadline:
            time.sleep(0.05)
        proc.send_signal(sig)
        proc.communicate(timeout=30)
    finally:
        proc.kill()
        server.shutdown()
    assert proc.returncode != 0
    written = json.loads(out.read_text())
    s, rows = written["summary"], written["frames"]
    assert s["complete"] is False and s["frames_requested"] == 40 and 1 <= len(rows) < 40
    assert [r["file"] for r in rows] == names[:len(rows)] and all("error" not in r for r in rows)
    assert s["rows_sha256"] == srf.rows_digest(rows)


def test_the_scorer_gives_the_runners_three_frame_file_no_verdict_and_no_reading(tmp_path):
    written, _, _, _ = _run(tmp_path)
    s = score(written["frames"], written["summary"])
    assert not s["valid"] and s["r1"] is None and s["r2"] is None
    assert s["cells"]["B/c920"] == {"n": 1, "error": 0} and s["cells"]["F/brio"] == {"n": 1, "error": 1}
    why = " | ".join(s["invalid"])
    assert "summary model is 'ws/model--abc'" in why and "3 rows, the manifest has 580" in why
    assert "summary server_version is 'stub-1.7.2'" in why and "1 request errors" in why
