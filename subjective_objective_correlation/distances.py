"""Shared vector distances and frame-level dynamic time warping.

Sequences passed to DTW have shape (frames, features). Jensen–Shannon
uses natural logarithms, matching scipy's default.
"""

import numpy as np
from scipy.spatial.distance import jensenshannon


def cosine_similarity(reference, candidate):
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    reference_norm = np.linalg.norm(reference)
    candidate_norm = np.linalg.norm(candidate)
    if reference_norm == 0 or candidate_norm == 0:
        return float(reference_norm == candidate_norm)
    return float(np.clip(np.dot(reference, candidate) / (reference_norm * candidate_norm), -1, 1))


def cosine_distance(reference, candidate):
    return 1.0 - cosine_similarity(reference, candidate)


def jensen_shannon_distance(reference, candidate):
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if (not np.isfinite(reference).all() or not np.isfinite(candidate).all()
            or np.any(reference < 0) or np.any(candidate < 0)
            or reference.sum() <= 0 or candidate.sum() <= 0):
        raise ValueError("Jensen–Shannon distance requires nonnegative vectors with positive mass.")
    return float(jensenshannon(reference, candidate))


def manhattan_distance(reference, candidate):
    return float(np.abs(np.asarray(reference) - np.asarray(candidate)).sum())


def rmse_distance(reference, candidate):
    return float(np.sqrt(np.mean((np.asarray(reference) - np.asarray(candidate)) ** 2)))


DISTANCE_METRICS = {
    "cosine": cosine_distance,
    "jensenshannon": jensen_shannon_distance,
    "manhattan": manhattan_distance,
    "rmse": rmse_distance,
}


def dtw_alignment(reference, candidate, metric="cosine"):
    """Return normalized DTW distance, local cost matrix, and alignment path."""
    from dtw import dtw

    reference, candidate = np.asarray(reference), np.asarray(candidate)
    if (reference.ndim != 2 or candidate.ndim != 2
            or len(reference) == 0 or len(candidate) == 0
            or reference.shape[1] != candidate.shape[1]):
        raise ValueError("DTW requires nonempty (frames, features) arrays with matching feature dimensions.")
    if not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("DTW features must be finite.")
    distance_function = DISTANCE_METRICS[metric] if isinstance(metric, str) else metric
    distance, cost, _, path = dtw(reference, candidate, dist=distance_function)
    # Some dtw versions return floating-point indices for single-frame inputs.
    path = tuple(np.asarray(indices, dtype=np.intp) for indices in path)
    return float(distance / len(path[0])), cost, path


def aggregate_frame_distances(path, costs, reference_count, candidate_count):
    """Average path costs per frame on each original time axis."""
    reference_indices, candidate_indices = map(np.asarray, path)
    costs = np.asarray(costs)
    def aggregate(indices, count):
        return np.bincount(indices, weights=costs, minlength=count) / np.bincount(indices, minlength=count)
    return aggregate(reference_indices, reference_count), aggregate(candidate_indices, candidate_count)


def dtw_frame_distances(reference, candidate, metric="cosine"):
    distance, cost, path = dtw_alignment(reference, candidate, metric)
    reference_values, candidate_values = aggregate_frame_distances(
        path, cost[path[0], path[1]], len(reference), len(candidate)
    )
    return distance, reference_values, candidate_values
