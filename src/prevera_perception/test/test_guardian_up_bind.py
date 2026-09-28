"""guardian-up.sh binds the bridges the way mjpeg_server.py binds the camera views: loopback unless GUARDIAN_BIND says otherwise."""
import re
import subprocess
from pathlib import Path

UP = Path(__file__).resolve().parents[3] / "jetson" / "guardian-up.sh"


def test_bridges_are_launched_with_the_bind_address():
    text = UP.read_text()
    assert 'BIND="${GUARDIAN_BIND:-127.0.0.1}"' in text
    assert re.search(r'foxglove_bridge_launch\.xml .*address:="\$BIND"', text)
    assert re.search(r'rosbridge_websocket_launch\.xml .*address:="\$BIND"', text)


def test_empty_guardian_bind_means_loopback():
    # the same shell expansion the script uses; an empty value must fall to the default (review M5 for the views)
    out = subprocess.run(["bash", "-c", 'GUARDIAN_BIND=""; BIND="${GUARDIAN_BIND:-127.0.0.1}"; echo "$BIND"'],
                         capture_output=True, text=True).stdout.strip()
    assert out == "127.0.0.1"


def test_script_still_parses():
    assert subprocess.run(["bash", "-n", str(UP)]).returncode == 0
