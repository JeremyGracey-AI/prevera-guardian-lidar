"""Keypoint scorer (tools/bag_analysis/rfdetr_keypoints.py) under plan v2: the person rule by name.

Plan v2 (docs/field-tests/2026-09-28-rfdetr-keypoints-plan-v2.md) changes one thing in the 2026-09-27 keypoint
plan: an instance is a person when its `class_name` is 'person', not when its `class_id` is 0, and validity gains a
package probe (definition 9, c1 to c3). These tests run the scorer on a synthetic results file shaped like the real
one (210 frames, every instance `class_id` 1 / 'person', which is what the 2026-09-28 run returned). No frame, no
model and no field data is involved. They pin down:

  * the default is byte-for-byte v1: `is_person` is `class_id == 0`, and the v1 verdict on such a run is still
    RUN INVALID with K1-K3 not scored;
  * under v2, validity refuses to score without the probe (c3), or with a probe whose person id disagrees (c3),
    or when the instances carry two class ids (c2), or when one is not named 'person' (c1);
  * with a consistent probe, v2 runs the schema check and K1-K3 and leaves the v1 files untouched.
"""
import json
from pathlib import Path

import pytest

import rfdetr_keypoints as kp

CAMS = ["c920", "brio"]
PER_CAM = {"A": 12, "B": 33, "F": 30, "W": 30}          # the plan's selection: 210 frames


def _keypoints(vertical: bool, conf: float = 0.9):
    """17 COCO keypoints in a plausible order: head < shoulders < hips < knees < ankles along the body axis."""
    ys = {"head": 100.0, "shoulders": 200.0, "hips": 350.0, "knees": 450.0, "ankles": 550.0}
    pts = []
    for j, name in enumerate(kp.COCO17):
        group = next(g for g, idx in kp.GROUPS.items() if j in idx) if any(j in idx for idx in kp.GROUPS.values()) \
            else "arms"
        along = ys.get(group, 300.0) + (j % 2) * 3.0
        across = 640.0 + (j % 3) * 4.0
        x, y = (across, along) if vertical else (along, 360.0 + (j % 3) * 4.0)
        pts.append([name, x, y, conf])
    return pts


def _instance(class_id: int, class_name, vertical: bool, det: float = 0.8):
    return {"xyxy": [100.0, 50.0, 700.0, 600.0], "detection_confidence": det, "class_id": class_id,
            "class_name": class_name, "keypoints": _keypoints(vertical),
            "covariance": None, "cov_sqrt_trace_px": None}


def _results(class_id: int = 1, class_name="person"):
    frames, order = [], 0
    for seg, n in PER_CAM.items():
        for i in range(n):
            for cam in CAMS:
                frames.append({"file": f"{seg}/{cam}-{i:03d}.jpg", "segment": seg, "camera": cam, "t_s": 1000 + i,
                               "pose": "standing" if seg == "W" else "lying", "lidar": "n/a", "lying": seg != "W",
                               "image_size": [1280, 720], "predict_s": 0.14, "run_order": order,
                               "instances": [_instance(class_id, class_name, vertical=(seg == "W"))]})
                order += 1
    meta = {"keypoint_names": list(kp.COCO17), "torch_num_threads": 4, "raw_pass": {"run": False},
            "validity": {"a_md5_ok": True, "b_no_partial_load_warning": True,
                         "c_all_instances_person_class0": False, "c_violation_count": len(frames), "valid": False}}
    return {"meta": meta, "frames": frames}


def _write(tmp_path: Path, results: dict, probe_person_ids=None):
    (tmp_path / kp.RESULTS_NAME).write_text(json.dumps(results))
    if probe_person_ids is not None:
        mappings = [{"source": "test", "type": "dict", "size": 2, "sample": {}, "person_ids": probe_person_ids}]
        (tmp_path / kp.PROBE_NAME).write_text(json.dumps({"mappings": mappings, "probed_utc": "t"}))


@pytest.fixture(autouse=True)
def _plan_v1_default():
    kp.PLAN = "v1"
    yield
    kp.PLAN = "v1"


def _args(tmp_path: Path):
    class A:
        frames_dir = tmp_path
    return A()


def test_default_is_v1_and_v1_stays_invalid(tmp_path, monkeypatch, capsys):
    _write(tmp_path, _results())
    assert kp.PLAN == "v1"
    assert kp.is_person({"class_id": 0, "class_name": "person"})
    assert not kp.is_person({"class_id": 1, "class_name": "person"})
    monkeypatch.setattr(kp, "_draw", lambda *a, **k: None)
    assert kp.cmd_score(_args(tmp_path)) == 5
    report = json.loads((tmp_path / kp.SCORE_NAME).read_text())
    assert report["verdict"].startswith("RUN INVALID (definition 9)")
    assert report["plan"] == kp.PLAN_FILE and report["plan_commit"] == kp.PLAN_COMMIT
    assert not (tmp_path / kp.SCORE_NAME_V2).exists()


def test_v2_refuses_without_probe(tmp_path, capsys):
    _write(tmp_path, _results())
    kp.PLAN = "v2"
    assert kp.cmd_check(_args(tmp_path)) == 5
    chk = json.loads((tmp_path / kp.CHECK_NAME_V2).read_text())
    assert chk["verdict"].startswith("RUN INVALID (definition 9, v2)")
    v = chk["validity"]
    assert v["c1_all_instances_named_person"] and v["c2_single_class_id"] and v["c2_class_id"] == 1
    assert v["c3_probe_found"] is False and v["c3_ok"] is False and "probe-classes" in v["c3_reason"]
    assert kp.cmd_score(_args(tmp_path)) == 5


def test_v2_refuses_when_package_disagrees(tmp_path, capsys):
    _write(tmp_path, _results(), probe_person_ids=[0])
    kp.PLAN = "v2"
    assert kp.cmd_score(_args(tmp_path)) == 5
    v = json.loads((tmp_path / kp.SCORE_NAME_V2).read_text())["validity"]
    assert v["c3_ok"] is False and "!= observed 1" in v["c3_reason"]


def test_v2_refuses_two_class_ids_or_a_non_person(tmp_path, capsys):
    r = _results()
    r["frames"][0]["instances"][0]["class_id"] = 2
    _write(tmp_path, r, probe_person_ids=[1])
    kp.PLAN = "v2"
    assert kp.cmd_score(_args(tmp_path)) == 5
    v = json.loads((tmp_path / kp.SCORE_NAME_V2).read_text())["validity"]
    assert v["c2_single_class_id"] is False and v["c2_class_ids_observed"] == [1, 2]

    r = _results()
    r["frames"][5]["instances"][0]["class_name"] = "dog"
    _write(tmp_path, r, probe_person_ids=[1])
    assert kp.cmd_score(_args(tmp_path)) == 5
    v = json.loads((tmp_path / kp.SCORE_NAME_V2).read_text())["validity"]
    assert v["c1_all_instances_named_person"] is False and v["c1_violation_count"] == 1


def test_v2_scores_with_a_consistent_probe(tmp_path, monkeypatch, capsys):
    _write(tmp_path, _results(), probe_person_ids=[1])
    kp.PLAN = "v2"
    monkeypatch.setattr(kp, "_draw", lambda *a, **k: None)     # no PIL, no pixels
    assert kp.cmd_check(_args(tmp_path)) == 0
    chk = json.loads((tmp_path / kp.CHECK_NAME_V2).read_text())
    assert chk["verdict"] == "pass" and chk["instance_rule"] == "class_name == 'person'"
    assert chk["validity"]["valid"] and chk["validity"]["c3_reason"].startswith("package maps 'person' to 1")
    assert kp.cmd_score(_args(tmp_path)) == 0
    rep = json.loads((tmp_path / kp.SCORE_NAME_V2).read_text())
    assert rep["plan"] == kp.PLAN_V2_FILE and rep["plan_commit"] == kp.PLAN_V2_COMMIT
    assert rep["K1"]["verdict"] == "PASS" and rep["K1"]["segments"]["B"]["best"] == "33/33"
    assert rep["K2"]["verdict"] == "PASS"
    assert rep["K2"]["A_brio"]["median_angle_deg"] >= kp.K2_A_MIN_DEG
    assert rep["K2"]["W_brio"]["median_angle_deg"] <= kp.K2_W_MAX_DEG
    # v1 files are never written by a v2 run
    assert not (tmp_path / kp.CHECK_NAME).exists() and not (tmp_path / kp.SCORE_NAME).exists()


def test_v2_probe_with_no_mapping_rests_on_c1_c2(tmp_path, monkeypatch, capsys):
    _write(tmp_path, _results())
    (tmp_path / kp.PROBE_NAME).write_text(json.dumps({"mappings": [{"source": "x", "error": "AttributeError"}],
                                                      "probed_utc": "t"}))
    kp.PLAN = "v2"
    monkeypatch.setattr(kp, "_draw", lambda *a, **k: None)
    assert kp.cmd_check(_args(tmp_path)) == 0
    v = json.loads((tmp_path / kp.CHECK_NAME_V2).read_text())["validity"]
    assert v["valid"] and v["c3_package_mapping_exposed"] is False


def test_mapping_person_ids_accepts_the_three_shapes():
    assert kp._mapping_person_ids({1: "person", 2: "bicycle"}) == [1]
    assert kp._mapping_person_ids({"person": 1, "bicycle": 2}) == [1]
    assert kp._mapping_person_ids(["__background__", "person"]) == [1]
    assert kp._mapping_person_ids({"a": "b"}) == []
