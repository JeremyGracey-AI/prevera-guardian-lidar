"""jetson/mjpeg_server.py binds the loopback address unless told otherwise (review finding M5).

The script needs rclpy at import time, which this suite does not have; the ROS modules are stubbed so the bind
resolution can be exercised as the script computes it. An empty GUARDIAN_BIND must not fall through to
"" (which ThreadingHTTPServer treats as every interface).
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "jetson" / "mjpeg_server.py"


@pytest.fixture
def mjpeg(monkeypatch):
    rclpy = types.ModuleType("rclpy")
    rclpy.init = lambda *a, **k: None
    rclpy.spin = lambda *a, **k: None
    node = types.ModuleType("rclpy.node")

    class Node:
        def __init__(self, *a, **k):
            pass

        def create_subscription(self, *a, **k):
            return None

    node.Node = Node
    qos = types.ModuleType("rclpy.qos")
    qos.qos_profile_sensor_data = object()
    sensor_msgs = types.ModuleType("sensor_msgs")
    msg = types.ModuleType("sensor_msgs.msg")
    msg.CompressedImage = object
    for name, mod in (("rclpy", rclpy), ("rclpy.node", node), ("rclpy.qos", qos),
                      ("sensor_msgs", sensor_msgs), ("sensor_msgs.msg", msg)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(sys, "argv", ["mjpeg_server.py"])
    spec = importlib.util.spec_from_file_location("mjpeg_server_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_bind_is_loopback(mjpeg):
    assert mjpeg.resolve_bind(["mjpeg_server.py"], {}) == "127.0.0.1"


def test_empty_guardian_bind_is_treated_as_unset(mjpeg):
    assert mjpeg.resolve_bind(["mjpeg_server.py"], {"GUARDIAN_BIND": ""}) == "127.0.0.1"
    assert mjpeg.resolve_bind(["mjpeg_server.py", "/t", "8081", ""], {}) == "127.0.0.1"


def test_explicit_bind_wins_over_environment(mjpeg):
    assert mjpeg.resolve_bind(["mjpeg_server.py", "/t", "8081", "0.0.0.0"], {"GUARDIAN_BIND": "10.0.0.5"}) == "0.0.0.0"
    assert mjpeg.resolve_bind(["mjpeg_server.py"], {"GUARDIAN_BIND": "0.0.0.0"}) == "0.0.0.0"
