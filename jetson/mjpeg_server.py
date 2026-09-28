#!/usr/bin/env python3
"""Serve a CompressedImage topic as an MJPEG stream (/, /stream, /snap).

Usage: mjpeg_server.py [topic] [port] [bind]   (defaults: /camera/image_raw/compressed 8081 127.0.0.1)
No dependencies beyond rclpy. One instance per camera.

SECURITY: no authentication. The default bind is the loopback address, so the view is reachable only on the
Jetson itself or through an ssh tunnel (`ssh -L 8081:127.0.0.1:8081 jetson`, then http://127.0.0.1:8081/).
Passing `0.0.0.0` (or setting GUARDIAN_BIND=0.0.0.0) exposes the stream to every interface: trusted LAN only,
and stop it after use (guardian-cams-down.sh).
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage



def resolve_bind(argv, environ) -> str:
    """argv[3] if given, else GUARDIAN_BIND; an empty value in either place means unset (never "" = every interface)."""
    explicit = argv[3] if len(argv) > 3 else ""
    return explicit.strip() or (environ.get("GUARDIAN_BIND") or "").strip() or "127.0.0.1"


TOPIC = sys.argv[1] if len(sys.argv) > 1 else "/camera/image_raw/compressed"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8081
BIND = resolve_bind(sys.argv, os.environ)
latest = {"jpg": None}
cond = threading.Condition()

class Sub(Node):
    def __init__(self):
        super().__init__("mjpeg_server_%d" % PORT)
        self.create_subscription(CompressedImage, TOPIC, self.cb, qos_profile_sensor_data)
    def cb(self, m):
        with cond:
            latest["jpg"] = bytes(m.data)
            cond.notify_all()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path.startswith("/snap"):
            with cond:
                cond.wait(timeout=2)
                jpg = latest["jpg"]
            if not jpg:
                self.send_response(503); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers(); self.wfile.write(jpg); return
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    with cond:
                        cond.wait(timeout=2)
                        jpg = latest["jpg"]
                    if not jpg:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(("<html><head><title>Guardian camera %s</title></head><body style='margin:0;background:#111'>"
                          "<img src='/stream' style='width:100vw;height:auto;display:block'></body></html>" % TOPIC).encode())

def main():
    rclpy.init()
    node = Sub()
    srv = ThreadingHTTPServer((BIND, PORT), H)   # SECURITY: no auth; loopback by default, 0.0.0.0 = trusted LAN only
    print("mjpeg_server: %s on http://%s:%d/ (%s)" % (TOPIC, BIND, PORT,
          "loopback only; use an ssh tunnel" if BIND.startswith("127.") else "EXPOSED on every interface, no auth"),
          flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    rclpy.spin(node)

if __name__ == "__main__":
    main()
