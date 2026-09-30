"""Exercise the maintained clients against real loopback servers, using fake credentials only."""
import json
import os
import subprocess
import sys
import threading
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from inference_http import request_json, validate_base_url

JETSON = Path(__file__).resolve().parents[3] / "jetson"
RUNNERS = ("f5_device_fit.py", "rf_room_eval.py")
KEY = "fake-inference-key-must-not-be-logged"


@contextmanager
def inference_server(mode="ok", redirect_code=302, redirect_path="/infer/object_detection", redirect_location=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requests.append((self.command, self.path, raw))
            posts = sum(method == "POST" for method, _, _ in requests)
            if mode == "bad-status" and self.command == "POST":
                self.wfile.write(("invalid status " + KEY + "\r\n\r\n").encode())
                return
            fail = ((mode == "error-info" and self.path == "/info")
                    or (mode == "error-first" and posts == 1)
                    or (mode == "error-warmup" and posts == 2))
            if fail:
                # Both the reason phrase and body are untrusted, and may echo a request.
                self.send_response(500, "echoed " + KEY)
                data = json.dumps({"api_key": KEY, "request": raw.decode()}).encode()
            elif mode == "redirect" and self.path == redirect_path:
                self.send_response(redirect_code)
                self.send_header("Location", redirect_location or "/unexpected?api_key=" + KEY)
                data = b""
            else:
                self.send_response(200)
                if self.path == "/info":
                    data = b'{"version": "stub-1.7.2"}'
                elif self.path == "/model/registry":
                    data = b'{"models": []}'
                elif mode == "bad-encoding":
                    data = b'\xff' + KEY.encode()
                else:
                    data = b'{"time": 0.01, "predictions": []}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = respond
        do_POST = respond

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_client(tmp_path, runner, url, env=None):
    (tmp_path / "one.jpg").write_bytes(b"synthetic-frame")
    (tmp_path / "manifest.json").write_text(json.dumps([{"file": "one.jpg"}]))
    output = tmp_path / "result.json"
    proc = subprocess.run(
        [sys.executable, str(JETSON / runner), "ws/test-model", "--url", url,
         "--frames", str(tmp_path), "--out", str(output)],
        env={**os.environ, "ROBOFLOW_API_KEY": KEY, **(env or {})},
        capture_output=True, text=True, timeout=20,
    )
    written = output.read_text() if output.exists() else ""
    return proc, written


@pytest.mark.parametrize("runner", RUNNERS)
@pytest.mark.parametrize("url", [
    "http://example.invalid:9001", "http://192.0.2.1:9001", "http://0.0.0.0:9001",
    "http://localhost:9001", "http://127.1:9001", "http://2130706433:9001",
    "file:///tmp/inference", "http://[::]:9001", "http://[::ffff:127.0.0.1]:9001",
    "http://127.0.0.1:9001/path", "http://127.0.0.1:9001?key=" + KEY,
    "http://user:" + KEY + "@127.0.0.1:9001", "http://127.0.0.1:70000",
    "http://127.0.0.1:0", "http://127.0.0.1:", "http://[::1%25lo0]:9001",
    "http://127.0.0.1:9001#" + KEY, "http://127.0.0.1:9001\n",
])
def test_invalid_destination_fails_before_frame_io(tmp_path, runner, url):
    # No frame directory: the old clients fail on file I/O rather than URL validation.
    proc = subprocess.run(
        [sys.executable, str(JETSON / runner), "ws/model", "--url", url,
         "--frames", str(tmp_path / "missing")],
        env={**os.environ, "ROBOFLOW_API_KEY": KEY}, capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 2
    assert "literal loopback" in proc.stderr
    assert KEY not in proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr and not list(tmp_path.iterdir())


@pytest.mark.parametrize("runner", RUNNERS)
def test_proxy_environment_never_receives_a_request(tmp_path, runner):
    with inference_server() as (url, requests), inference_server() as (proxy, intercepted):
        env = {name: proxy for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                                       "all_proxy", "ALL_PROXY")}
        env.update(no_proxy="", NO_PROXY="")
        proc, written = run_client(tmp_path, runner, url, env)
    assert proc.returncode == 0, proc.stderr
    assert requests and not intercepted
    assert json.loads(written)["summary"]["frames_answered"] == 1
    assert KEY not in proc.stdout + proc.stderr + written


@pytest.mark.parametrize("runner", RUNNERS)
def test_redirects_never_reach_the_target(tmp_path, runner):
    with inference_server("redirect") as (url, requests):
        proc, written = run_client(tmp_path, runner, url)
    assert not any(path.startswith("/unexpected") for _, path, _ in requests)
    assert KEY not in proc.stdout + proc.stderr + written
    if runner == "f5_device_fit.py":
        assert proc.returncode != 0 and "HTTP 302" in proc.stderr
    else:
        assert json.loads(written)["frames"][0]["error"] == "HTTP 302"


@pytest.mark.parametrize("runner,mode", [
    ("f5_device_fit.py", "error-info"), ("f5_device_fit.py", "error-first"),
    ("f5_device_fit.py", "error-warmup"), ("rf_room_eval.py", "error-info"),
    ("rf_room_eval.py", "error-first"),
])
def test_server_errors_cannot_echo_credentials(tmp_path, runner, mode):
    with inference_server(mode) as (url, _):
        proc, written = run_client(tmp_path, runner, url)
    assert KEY not in proc.stdout + proc.stderr + written
    assert "HTTP 500" in proc.stderr + written
    if runner == "f5_device_fit.py" or mode == "error-info":
        assert proc.returncode != 0
    else:
        assert json.loads(written)["frames"][0]["error"] == "HTTP 500"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:9001", "https://127.0.0.2:9443", "http://[::1]:9001",
    "https://[0:0:0:0:0:0:0:1]", "http://127.0.0.1:12345/",
])
def test_literal_loopback_origins_are_accepted(url):
    assert validate_base_url(url) == url.rstrip("/")


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("data,path", [(None, "/info"), (b'{"api_key":"fake"}', "/infer/object_detection")])
def test_get_and_post_redirects_are_rejected(code, data, path):
    with inference_server("redirect", redirect_code=code, redirect_path=path) as (url, requests):
        with pytest.raises(urllib.error.HTTPError) as raised:
            request_json(path, data=data, url=url)
    assert raised.value.code == code
    assert len(requests) == 1 and requests[0][1] == path
    assert KEY not in str(raised.value)


@pytest.mark.parametrize("runner", RUNNERS)
@pytest.mark.parametrize("mode,category", [("bad-status", "BadStatusLine"), ("bad-encoding", "UnicodeDecodeError")])
def test_malformed_responses_do_not_leak_content(tmp_path, runner, mode, category):
    with inference_server(mode) as (url, _):
        proc, written = run_client(tmp_path, runner, url)
    assert KEY not in proc.stdout + proc.stderr + written
    assert category in proc.stderr + written
    if runner == "f5_device_fit.py":
        assert proc.returncode != 0
    else:
        assert json.loads(written)["frames"][0]["error"].startswith(category + ":")


@pytest.mark.parametrize("path", ["@example.invalid/", "//example.invalid/", "https://example.invalid/"])
def test_endpoint_cannot_replace_validated_origin(path):
    with pytest.raises(ValueError, match="absolute path"):
        request_json(path)


@pytest.mark.parametrize("runner", RUNNERS)
def test_malformed_redirect_location_is_not_parsed_or_logged(tmp_path, runner):
    with inference_server("redirect", redirect_path="/info", redirect_location=f"http://[{KEY}]") as (url, requests):
        proc, written = run_client(tmp_path, runner, url)
    assert KEY not in proc.stdout + proc.stderr + written
    assert proc.returncode != 0 and "HTTP 302" in proc.stderr
    assert "Traceback" not in proc.stderr and len(requests) == 1
