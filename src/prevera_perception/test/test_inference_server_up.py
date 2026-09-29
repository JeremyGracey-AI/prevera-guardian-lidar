"""jetson/inference-server-up.sh is the DR-11 container command, versioned, with every privacy flag on it.

The 09-27 and 09-28 documents recorded this command from shell history and `docker inspect`; from now on the
script is the record, and this test keeps its flags from drifting.
"""
import re
import subprocess
from pathlib import Path

UP = Path(__file__).resolve().parents[3] / "jetson" / "inference-server-up.sh"


def _docker_run_line():
    text = UP.read_text()
    m = re.search(r"docker run .*?roboflow/roboflow-inference-server-jetson-6\.2\.0:latest", text, re.S)
    assert m, "one docker run line ending in the Jetson 6.2.0 image"
    return " ".join(m.group(0).split())


def test_every_privacy_and_hardening_flag_is_on_the_command():
    line = _docker_run_line()
    for flag in ("--read-only", "-p 127.0.0.1:9001:9001", "--env-file ~/.roboflow.env",
                 "-e ACTIVE_LEARNING_ENABLED=False", "-e TELEMETRY_OPT_OUT=True", "-e METRICS_ENABLED=False",
                 "-e TRITON_CACHE_DIR=/tmp/triton-cache", "-e MAX_ACTIVE_MODELS=2",
                 "--security-opt=no-new-privileges", "--cap-drop=ALL", "--cap-add=NET_BIND_SERVICE",
                 "--volume /opt/nvme/inference-cache:/tmp:rw", "--runtime nvidia", "--name inference-server"):
        assert flag in line, flag


def test_no_key_and_no_wide_bind():
    text = UP.read_text()
    assert not re.search(r"rf_[A-Za-z0-9]{20,}", text) and "api_key=" not in text.lower()
    assert "0.0.0.0:9001" not in text


def test_script_parses_and_prints_the_inspect_check():
    assert subprocess.run(["bash", "-n", str(UP)]).returncode == 0
    text = UP.read_text()
    assert "docker inspect inference-server" in text and "METRICS_ENABLED" in text
