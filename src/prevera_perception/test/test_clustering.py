"""Unit tests for shape-feature extraction from clustered LIDAR points."""

import numpy as np
import pytest

from prevera_perception.clustering import ClusterConfig, cluster_points


CONFIG = ClusterConfig(eps_m=0.2, min_samples=3, min_points_per_cluster=5)


def test_empty_input_returns_empty():
    assert cluster_points(np.empty((0, 2), dtype=np.float32), CONFIG) == []


def test_standing_person_has_low_elongation():
    # Tight 15 cm cluster = upright body slice.
    rng = np.random.default_rng(0)
    points = rng.normal(loc=[2.0, 0.0], scale=0.04, size=(40, 2)).astype(np.float32)

    clusters = cluster_points(points, CONFIG)
    assert len(clusters) == 1
    assert clusters[0].elongation < 2.5
    assert clusters[0].major_axis_m < 0.5


def test_fallen_person_has_high_elongation():
    # 1.7 m long, 0.25 m wide cluster aligned with X axis.
    rng = np.random.default_rng(1)
    xs = rng.uniform(-0.85, 0.85, size=200)
    ys = rng.normal(0.0, 0.06, size=200)
    points = np.stack([xs + 2.5, ys], axis=1).astype(np.float32)

    clusters = cluster_points(points, CONFIG)
    assert len(clusters) >= 1
    largest = max(clusters, key=lambda c: c.point_count)
    assert largest.elongation > 3.0
    assert largest.major_axis_m > 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
