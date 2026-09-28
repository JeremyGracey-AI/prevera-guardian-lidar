"""DBSCAN clustering of LIDAR foreground points with shape features.

Each cluster is characterized by centroid, point count, and the ratio
of its major to minor PCA axis. The axis ratio is the single strongest
2D-LIDAR signal for "upright cylinder" (standing person, ratio near 1)
vs "elongated silhouette" (fallen person, ratio large).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import DBSCAN


@dataclass(frozen=True)
class ClusterConfig:
    eps_m: float
    min_samples: int
    min_points_per_cluster: int


@dataclass(frozen=True)
class Cluster:
    centroid: np.ndarray        # shape (2,)
    point_count: int
    major_axis_m: float
    minor_axis_m: float

    @property
    def elongation(self) -> float:
        if self.minor_axis_m < 1e-3:
            return float("inf")
        return self.major_axis_m / self.minor_axis_m


def cluster_points(points: np.ndarray, config: ClusterConfig) -> list[Cluster]:
    """Cluster Nx2 points with DBSCAN and extract shape features."""
    if points.shape[0] < config.min_samples:
        return []

    labels = DBSCAN(eps=config.eps_m, min_samples=config.min_samples).fit_predict(points)
    clusters: list[Cluster] = []
    for label in np.unique(labels):
        if label == -1:
            continue
        member = points[labels == label]
        if member.shape[0] < config.min_points_per_cluster:
            continue
        clusters.append(_build_cluster(member))
    return clusters


def _build_cluster(member_points: np.ndarray) -> Cluster:
    centroid = member_points.mean(axis=0)
    centered = member_points - centroid
    if centered.shape[0] < 2:
        return Cluster(centroid=centroid, point_count=1, major_axis_m=0.0, minor_axis_m=0.0)

    # Principal axes via eigendecomposition of 2x2 covariance.
    # Axis lengths = actual spread along each axis (max projection - min projection),
    # which corresponds to the real spatial extent visible to the LIDAR.
    cov = np.cov(centered.T)
    _, eigenvectors = np.linalg.eigh(cov)  # columns are eigenvectors, ascending eigenvalues
    projections = centered @ eigenvectors  # Nx2 (minor_axis, major_axis)
    minor = float(projections[:, 0].max() - projections[:, 0].min())
    major = float(projections[:, 1].max() - projections[:, 1].min())
    return Cluster(
        centroid=centroid,
        point_count=int(member_points.shape[0]),
        major_axis_m=major,
        minor_axis_m=minor,
    )
