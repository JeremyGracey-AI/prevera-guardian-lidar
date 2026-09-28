"""tools/roboflow/time_on_floor_workflow.json stays a well-formed Workflow with the inputs its README documents.

No API call: the file is checked structurally (every `$steps.` and `$inputs.` reference resolves, the documented
inputs and outputs exist, the down classes cover the three datasets of the 2026-09-28 fine-tune plan). The
semantic validation against the block manifests was done with Roboflow's validator on 2026-09-28 and is repeated
by hand whenever a block version changes.
"""
import json
import re
from pathlib import Path

SPEC = Path(__file__).resolve().parents[3] / "tools" / "roboflow" / "time_on_floor_workflow.json"
REF = re.compile(r"^\$(inputs|steps)\.([A-Za-z_0-9\-]+)(?:\.([A-Za-z_*0-9\-]+))?$")


def _refs(obj):
    if isinstance(obj, str) and obj.startswith("$"):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _refs(v)


def test_workflow_spec_is_well_formed():
    spec = json.loads(SPEC.read_text())
    assert spec["version"] == "1.0"
    inputs = {i["name"] for i in spec["inputs"]}
    steps = {s["name"] for s in spec["steps"]}
    assert {"image", "model_id", "confidence", "down_classes", "floor_zone", "warn_after_s"} <= inputs
    assert {"detector", "down_only", "tracker", "time_on_floor", "down_too_long"} <= steps
    for ref in _refs(spec):
        m = REF.match(ref)
        assert m, f"malformed selector {ref!r}"
        kind, name = m.group(1), m.group(2)
        assert name in (inputs if kind == "inputs" else steps), f"{ref!r} does not resolve"
    outputs = {o["name"] for o in spec["outputs"]}
    assert {"detections", "down_on_floor", "warn", "visualization"} <= outputs


def test_down_classes_cover_the_three_plan_datasets():
    spec = json.loads(SPEC.read_text())
    down = {i["name"]: i for i in spec["inputs"]}["down_classes"]["default_value"]
    # arm A: lying; arm B (URFD): fall; arm C (lying3): lying
    assert "lying" in down and "fall" in down
    assert all(isinstance(c, str) and c == c.strip() for c in down)


def test_warn_threshold_matches_the_lidar_sustained_rule():
    spec = json.loads(SPEC.read_text())
    warn = {i["name"]: i for i in spec["inputs"]}["warn_after_s"]["default_value"]
    assert warn == 4.0, "keep warn_after_s equal to fall.sustained_down_s (4.0 s) or update the README"


# --- review finding I3: the timer must only ever see down poses, on tracks that die when the person gets up ---
def _steps():
    spec = json.loads(SPEC.read_text())
    return spec, {s["name"]: s for s in spec["steps"]}, {i["name"]: i for i in spec["inputs"]}


def test_timer_is_fed_by_a_tracker_that_only_sees_down_poses():
    spec, steps, _ = _steps()
    timer = steps["time_on_floor"]
    feeder = steps[timer["detections"].split(".")[1]]
    assert feeder["type"].startswith("roboflow_core/trackers_bytetrack@"), "time_in_zone needs tracker ids"
    assert feeder["detections"] == "$steps.down_only.predictions", "the tracker must run AFTER the down-class filter"
    assert steps["down_only"]["predictions"] == "$steps.detector.predictions"
    assert not any(s["type"].startswith("roboflow_core/track_class_lock") for s in spec["steps"]), \
        "a class lock delays and holds the clock; it is not part of this workflow"


def test_one_confidence_input_sets_every_threshold_that_gates_a_track():
    _, steps, _ = _steps()
    tracker = steps["tracker"]
    assert tracker["track_activation_threshold"] == "$inputs.confidence"
    assert tracker["high_conf_det_threshold"] == "$inputs.confidence"
    assert tracker["lost_track_buffer"] <= 10, "a dead track must not carry its clock into the next lie-down"
    assert steps["detector"]["confidence"] == "$inputs.confidence"


def test_defaults_name_a_real_model_and_only_classes_the_plan_datasets_have():
    _, _, inputs = _steps()
    assert inputs["model_id"]["default_value"] == "jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--00ba18"
    assert set(inputs["down_classes"]["default_value"]) == {"lying", "fall"}
