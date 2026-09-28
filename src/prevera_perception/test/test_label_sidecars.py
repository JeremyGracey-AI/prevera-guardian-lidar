"""The step-9 label sidecars in docs/field-tests/labels/ stay loadable by `replay_detector.py --compare-labels`.

Every published sidecar must pass `validate_labels` against its own bag length (`duration_s`), carry either an
`empty` segment or the `no_empty_segment` flag with a reason, and say who confirmed it (or that nobody has yet).
"""
import json
from pathlib import Path

import pytest

import replay_detector as rd

LABELS_DIR = Path(__file__).resolve().parents[3] / "docs" / "field-tests" / "labels"
FILES = sorted(LABELS_DIR.glob("*.json"))


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_sidecar_validates_against_its_bag_length(path):
    labels = json.loads(path.read_text())
    assert labels["bag"] == path.stem
    assert labels["time_base"] == "header_stamp_rel"
    segs = rd.validate_labels(labels, death_gap_t_end_s=labels["duration_s"])
    assert segs, "a sidecar with no segments scores nothing"
    for a, b in zip(segs, segs[1:]):
        assert a["t1"] <= b["t0"], f"segments overlap or are out of order: {a} / {b}"
    assert all(s["t1"] <= labels["duration_s"] for s in segs)
    if labels.get("no_empty_segment"):
        assert labels["no_empty_segment_reason"].strip()
    assert "confirmed_by" in labels, "say who confirmed the bounds, or null for a draft"
    if labels["confirmed_by"] is None:
        assert "DRAFT" in labels["status"], "an unconfirmed sidecar must be marked as a draft in its status"


def test_at_least_the_two_09_27_bags_have_sidecars():
    names = {p.stem for p in FILES}
    assert {"floor-trials-1", "grid-stations-1"} <= names
