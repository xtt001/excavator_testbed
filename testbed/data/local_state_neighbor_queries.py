"""Bounded exact local-neighbour computations for offline data contracts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

LOCAL_STATE_QUERY_ENGINE = "numpy_blocked_exact_normalized_l2_cpu_v1"
LOCAL_STATE_QUERY_BLOCK_SIZE = 128
LOCAL_STATE_REFERENCE_BLOCK_SIZE = 8192
_NORMAL_IQR = 1.3489795003921634
_NORMAL_MAD = 0.6744897501960817
_RELATIVE_SCALE_FLOOR = 1.0e-6


class LocalStateNeighborQueryError(ValueError):
    pass


@dataclass(frozen=True)
class RobustTrainScale:
    centre: np.ndarray
    scale: np.ndarray
    methods: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "centre": [float(value) for value in self.centre],
            "scale": [float(value) for value in self.scale],
            "methods": list(self.methods),
            "definition": "median centre; IQR/1.3489795003921634; MAD/0.6744897501960817 fallback; relative 1e-6 floor",
        }


@dataclass(frozen=True)
class LocalStateNeighborQuery:
    indices: np.ndarray
    distances: np.ndarray


@dataclass(frozen=True)
class LocalActionCoherence:
    total_score: float
    axis_scores: np.ndarray
    centre: np.ndarray


def robust_train_scale(values: np.ndarray | Sequence[Sequence[float]]) -> RobustTrainScale:
    """Build median/IQR, MAD, then relative-epsilon scales from train only."""

    matrix = _finite_matrix(values)
    centre = np.median(matrix, axis=0)
    q25, q75 = linear_quantile(matrix, (0.25, 0.75), axis=0)
    iqr_scale = (q75 - q25) / _NORMAL_IQR
    mad_scale = np.median(np.abs(matrix - centre.reshape(1, -1)), axis=0) / _NORMAL_MAD
    floor = np.maximum(np.abs(centre), 1.0) * _RELATIVE_SCALE_FLOOR
    scale = np.empty(matrix.shape[1], dtype=np.float64)
    methods: list[str] = []
    for index in range(matrix.shape[1]):
        if np.isfinite(iqr_scale[index]) and iqr_scale[index] > floor[index]:
            scale[index], method = iqr_scale[index], "iqr_over_normal_iqr"
        elif np.isfinite(mad_scale[index]) and mad_scale[index] > floor[index]:
            scale[index], method = mad_scale[index], "mad_over_normal_mad"
        else:
            scale[index], method = floor[index], "relative_epsilon_floor"
        methods.append(method)
    if not np.isfinite(scale).all() or np.any(scale <= 0.0):
        raise LocalStateNeighborQueryError("robust train scale is invalid")
    return RobustTrainScale(_freeze(centre), _freeze(scale), tuple(methods))


def normalise_by_train_scale(values: np.ndarray, scale: RobustTrainScale) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != scale.scale.size:
        raise LocalStateNeighborQueryError("feature dimension does not match robust scale")
    return (matrix - scale.centre.reshape(1, -1)) / scale.scale.reshape(1, -1)


def source_stratified_indices(
    source_episode_ids: Sequence[int] | np.ndarray,
    *,
    max_rows_per_source: int,
) -> np.ndarray:
    """Choose each source's full set or evenly-spaced first-to-last positions."""

    if max_rows_per_source < 1:
        raise LocalStateNeighborQueryError("max_rows_per_source must be positive")
    source_ids = np.asarray(source_episode_ids, dtype=np.int64).reshape(-1)
    grouped: dict[int, list[int]] = defaultdict(list)
    for index, source_id in enumerate(source_ids.tolist()):
        if source_id < 0:
            raise LocalStateNeighborQueryError("source episode id must be non-negative")
        grouped[int(source_id)].append(index)
    selected: list[int] = []
    for source_id in sorted(grouped):
        members = np.asarray(grouped[source_id], dtype=np.int64)
        if members.size <= max_rows_per_source:
            selected.extend(int(value) for value in members)
        else:
            positions = np.linspace(0, members.size - 1, num=max_rows_per_source, dtype=np.int64)
            selected.extend(int(value) for value in members[positions])
    return np.asarray(selected, dtype=np.int64)


def query_neighbors_excluding_query_source(
    *,
    reference_features: np.ndarray,
    query_features: np.ndarray,
    query_source_episode_ids: np.ndarray,
    reference_source_episode_ids: np.ndarray,
    k_neighbors: int,
) -> LocalStateNeighborQuery:
    """Exact k-NN grouped by optional query source; -1 means no exclusion."""

    reference = _finite_matrix(reference_features)
    query = _finite_matrix(query_features, expected_dim=reference.shape[1])
    query_sources = np.asarray(query_source_episode_ids, dtype=np.int64).reshape(-1)
    reference_sources = np.asarray(reference_source_episode_ids, dtype=np.int64).reshape(-1)
    if query_sources.shape != (query.shape[0],) or reference_sources.shape != (reference.shape[0],):
        raise LocalStateNeighborQueryError("source ids do not match feature rows")
    if k_neighbors < 1:
        raise LocalStateNeighborQueryError("k_neighbors must be positive")
    indices = np.full((query.shape[0], k_neighbors), -1, dtype=np.int64)
    distances = np.full((query.shape[0], k_neighbors), np.inf, dtype=np.float64)
    groups: dict[int | None, list[int]] = defaultdict(list)
    for index, source_id in enumerate(query_sources.tolist()):
        groups[None if source_id < 0 else int(source_id)].append(index)
    for source_id, member_indices in groups.items():
        reference_indices = (
            np.arange(reference.shape[0], dtype=np.int64)
            if source_id is None
            else np.flatnonzero(reference_sources != source_id)
        )
        if reference_indices.size < k_neighbors:
            continue
        member = np.asarray(member_indices, dtype=np.int64)
        local_indices, local_distances = blocked_exact_neighbors(
            reference_features=reference[reference_indices],
            query_features=query[member],
            k_neighbors=k_neighbors,
        )
        indices[member] = reference_indices[local_indices]
        distances[member] = local_distances
    return LocalStateNeighborQuery(_freeze(indices), _freeze(distances))


def blocked_exact_neighbors(
    *,
    reference_features: np.ndarray,
    query_features: np.ndarray,
    k_neighbors: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Exact L2 neighbours with memory bounded by query/reference block sizes."""

    reference = _finite_matrix(reference_features)
    query = _finite_matrix(query_features, expected_dim=reference.shape[1])
    if reference.shape[0] < k_neighbors:
        raise LocalStateNeighborQueryError("reference population is smaller than required k")
    result_indices = np.empty((query.shape[0], k_neighbors), dtype=np.int64)
    result_distances = np.empty((query.shape[0], k_neighbors), dtype=np.float64)
    reference_norm = np.einsum("ij,ij->i", reference, reference)
    for q_start in range(0, query.shape[0], LOCAL_STATE_QUERY_BLOCK_SIZE):
        q_stop = min(q_start + LOCAL_STATE_QUERY_BLOCK_SIZE, query.shape[0])
        q_block = query[q_start:q_stop]
        q_norm = np.einsum("ij,ij->i", q_block, q_block)
        best_squared = np.full((q_block.shape[0], k_neighbors), np.inf)
        best_indices = np.full((q_block.shape[0], k_neighbors), -1, dtype=np.int64)
        for r_start in range(0, reference.shape[0], LOCAL_STATE_REFERENCE_BLOCK_SIZE):
            r_stop = min(r_start + LOCAL_STATE_REFERENCE_BLOCK_SIZE, reference.shape[0])
            squared = q_norm[:, None] + reference_norm[None, r_start:r_stop] - 2.0 * (q_block @ reference[r_start:r_stop].T)
            np.maximum(squared, 0.0, out=squared)
            candidate_squared = np.concatenate((best_squared, squared), axis=1)
            candidate_indices = np.concatenate((best_indices, np.broadcast_to(np.arange(r_start, r_stop, dtype=np.int64), squared.shape)), axis=1)
            selected = np.argpartition(candidate_squared, kth=k_neighbors - 1, axis=1)[:, :k_neighbors]
            best_squared = np.take_along_axis(candidate_squared, selected, axis=1)
            best_indices = np.take_along_axis(candidate_indices, selected, axis=1)
        order = np.argsort(best_squared, axis=1, kind="stable")
        result_indices[q_start:q_stop] = np.take_along_axis(best_indices, order, axis=1)
        result_distances[q_start:q_stop] = np.sqrt(np.take_along_axis(best_squared, order, axis=1))
    return result_indices, result_distances


def local_action_coherence(actions: np.ndarray, scale: RobustTrainScale) -> LocalActionCoherence:
    """Return componentwise-median action centre plus robust axis/total spread."""

    matrix = np.asarray(actions, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != scale.scale.size:
        return LocalActionCoherence(float("inf"), np.full(scale.scale.size, np.inf), np.full(scale.scale.size, np.nan))
    centre = np.median(matrix, axis=0)
    normalised = (matrix - centre.reshape(1, -1)) / scale.scale.reshape(1, -1)
    return LocalActionCoherence(
        float(np.max(np.sqrt(np.sum(normalised * normalised, axis=1)))),
        np.max(np.abs(normalised), axis=0),
        centre,
    )


def linear_quantile(
    values: np.ndarray,
    quantile: float | Sequence[float],
    *,
    axis: int | None = None,
) -> np.ndarray:
    try:
        return np.quantile(values, quantile, axis=axis, method="linear")
    except TypeError:  # NumPy < 1.22
        return np.quantile(values, quantile, axis=axis, interpolation="linear")


def _finite_matrix(values: np.ndarray | Sequence[Sequence[float]], expected_dim: int | None = None) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or (expected_dim is not None and matrix.shape[1] != expected_dim):
        raise LocalStateNeighborQueryError("neighbour feature matrices have incompatible shape")
    if matrix.shape[0] < 1 or not np.isfinite(matrix).all():
        raise LocalStateNeighborQueryError("neighbour feature matrix must be non-empty and finite")
    return matrix


def _freeze(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values).copy()
    result.setflags(write=False)
    return result
