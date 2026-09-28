"""jetson/f5_device_fit.py measures cost only: it posts to one URL, asks for active learning off, keeps no prediction.

Runs the script as a subprocess against a stub Inference server on a free loopback port. The stub records every
request body, so the test reads what the runner sent, not what it says it sends.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "jetson" / "f5_device_fit.py"


class _Stub(BaseHTTPRequestHandler):
    bodies = []

    def log_message(self, *_):  # keep pytest output clean
        pass

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/info":
            self._send({"version": "stub-1.7.2"})
        elif self.path == "/model/registry":
            self._send({"models": [{"model_id": "ws/model--abc", "model_type": "rfdetr-nas"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        _Stub.bodies.append(body)
        self._send({"time": 0.042, "predictions": [
            {"x": 1, "y": 2, "width": 3, "height": 4, "confidence": 0.9, "class": "lying", "class_id": 1}]})


def _run(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for name in ("a.jpg", "b.jpg"):
        (frames / name).write_bytes(b"\xff\xd8not-really-a-jpeg\xff\xd9")
    (frames / "manifest.json").write_text(json.dumps([{"file": "a.jpg"}, {"file": "b.jpg"}]))
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = tmp_path / "out.json"
    env = {**os.environ, "ROBOFLOW_API_KEY": "test-key-not-real"}
    try:
        proc = subprocess.run([sys.executable, str(SCRIPT), "ws/model--abc", "--frames", str(frames), "--out", str(out),
                               "--url", f"http://127.0.0.1:{port}", "--confidence", "0.75"],
                              capture_output=True, text=True, env=env, timeout=60)
    finally:
        server.shutdown()
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_text()), json.loads(proc.stdout), list(_Stub.bodies)


def test_runner_reports_the_c4_columns_and_answers_every_manifest_frame(tmp_path):
    _Stub.bodies.clear()
    written, printed, bodies = _run(tmp_path)
    s = written["summary"]
    assert s["frames_requested"] == 2 and s["frames_answered"] == 2 and s["errors"] == 0
    for key in ("first_call_s", "latency_ms_median", "latency_ms_p90", "fps_serial", "server_time_ms_median",
                "mem_avail_idle_mb", "mem_avail_min_mb", "server_version"):
        assert s[key] is not None, key
    assert s["server_time_ms_median"] == 42.0
    assert printed["model"] == "ws/model--abc" and printed["confidence"] == 0.75
    # first call + 3 warm-ups + one per frame
    assert len(bodies) == 1 + 3 + 2


def test_every_request_asks_for_active_learning_off_and_carries_the_confidence(tmp_path):
    _Stub.bodies.clear()
    _, _, bodies = _run(tmp_path)
    assert bodies and all(b.get("disable_active_learning") is True for b in bodies)
    assert all(b["confidence"] == 0.75 and b["model_id"] == "ws/model--abc" for b in bodies)


def test_output_keeps_no_prediction_and_no_key(tmp_path):
    _Stub.bodies.clear()
    written, printed, _ = _run(tmp_path)
    text = json.dumps(written) + json.dumps(printed)
    assert "test-key-not-real" not in text
    assert "predictions" not in written and "lying" not in text and '"x"' not in text
    assert written["summary"]["boxes_total"] == 2 and written["summary"]["frames_with_a_box"] == 2
