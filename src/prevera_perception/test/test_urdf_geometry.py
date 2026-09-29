"""sentinel.urdf.xacro puts the laser at lidar_mount_height and draws a mast only when there is room for one."""
import xml.dom.minidom
from pathlib import Path

import pytest

xacro = pytest.importorskip("xacro")
ROOT = Path(__file__).resolve().parents[3]
URDF = ROOT / "src" / "prevera_description" / "urdf" / "sentinel.urdf.xacro"
LAUNCH = ROOT / "src" / "prevera_description" / "launch" / "state_publisher.launch.py"


def _expand(height=None):
    mappings = {"lidar_mount_height": str(height)} if height is not None else {}
    doc = xacro.process_file(str(URDF), mappings=mappings)
    return xml.dom.minidom.parseString(doc.toxml())


def _joints(dom):
    out = {}
    for j in dom.getElementsByTagName("joint"):
        parent = j.getElementsByTagName("parent")[0].getAttribute("link")
        child = j.getElementsByTagName("child")[0].getAttribute("link")
        z = float(j.getElementsByTagName("origin")[0].getAttribute("xyz").split()[2])
        out[child] = (parent, z)
    return out


def _laser_height(dom):
    joints, link, z = _joints(dom), "laser", 0.0
    while link != "base_link":
        link, dz = joints[link]
        z += dz
    return z


def _links(dom):
    return {l.getAttribute("name") for l in dom.getElementsByTagName("link")}


@pytest.mark.parametrize("height", [None, 0.02, 0.65, 0.01])
def test_laser_sits_at_lidar_mount_height(height):
    assert abs(_laser_height(_expand(height)) - (0.02 if height is None else height)) < 1e-9


def test_mast_only_when_the_housing_would_float():
    assert "lidar_mast" not in _links(_expand(0.02))
    assert "lidar_mast" not in _links(_expand(0.01))
    dom = _expand(0.65)
    assert "lidar_mast" in _links(dom)
    mast = [l for l in dom.getElementsByTagName("link") if l.getAttribute("name") == "lidar_mast"][0]
    length = float(mast.getElementsByTagName("cylinder")[0].getAttribute("length"))
    assert abs(length - (0.65 - 0.041 / 2 - 0.005)) < 1e-9, "mast from the top of the base plate to the housing"


def test_launch_file_exposes_the_argument():
    text = LAUNCH.read_text()
    assert '"lidar_mount_height"' in text and "lidar_mount_height:=" in text


def test_launch_file_passes_the_urdf_as_a_string_parameter():
    """launch_ros on Humble sniffs a bare Command value with yaml.safe_load; the URDF's header comment (a colon
    followed by a space) makes that raise TypeError, so the value must be declared a string (review I4)."""
    import yaml
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(_expand().toxml())
    text = LAUNCH.read_text()
    assert "ParameterValue(" in text and "value_type=str" in text
    assert "from launch_ros.parameter_descriptions import ParameterValue" in text
