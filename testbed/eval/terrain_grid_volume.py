"""Provenance-explicit volume integration over compact terrain grids."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


VOLUME_LABEL_STATUS = "derived_grid_integral"
DIRECT_VOLUME_STATUS = "unavailable_no_sensor"
MIN_VALID_SAMPLE_FRACTION = 0.5


def compute_grid_volume_change(
    *,
    start_removed_depth_m: Sequence[float],
    end_removed_depth_m: Sequence[float],
    cell_area_m2: float | Sequence[float],
    valid_mask: Sequence[float],
) -> dict[str, Any]:
    start = np.asarray(start_removed_depth_m, dtype=np.float64).reshape(-1)
    end = np.asarray(end_removed_depth_m, dtype=np.float64).reshape(-1)
    valid = (
        np.asarray(valid_mask, dtype=np.float64).reshape(-1)
        >= MIN_VALID_SAMPLE_FRACTION
    )
    if start.shape != end.shape or start.shape != valid.shape:
        raise ValueError("start/end/valid terrain arrays must share one shape.")
    if not np.isfinite(start).all() or not np.isfinite(end).all():
        raise ValueError("Terrain depth arrays must be finite.")
    area = np.asarray(cell_area_m2, dtype=np.float64)
    if area.ndim == 0:
        area = np.full(start.shape, float(area), dtype=np.float64)
    else:
        area = area.reshape(-1)
    if area.shape != start.shape or not np.isfinite(area).all() or np.any(area <= 0.0):
        raise ValueError("cell_area_m2 must be positive and match the terrain grid.")

    signed = end - start
    removed = np.where(valid, np.maximum(signed, 0.0) * area, 0.0)
    refill = np.where(valid, np.maximum(-signed, 0.0) * area, 0.0)
    return {
        "signed_depth_delta_m": signed.tolist(),
        "removed_volume_by_cell_m3": removed.tolist(),
        "refill_volume_by_cell_m3": refill.tolist(),
        "removed_volume_m3": float(np.sum(removed)),
        "refill_volume_m3": float(np.sum(refill)),
        "volume_label_status": VOLUME_LABEL_STATUS,
        "direct_volume_status": DIRECT_VOLUME_STATUS,
    }


__all__ = [
    "DIRECT_VOLUME_STATUS",
    "MIN_VALID_SAMPLE_FRACTION",
    "VOLUME_LABEL_STATUS",
    "compute_grid_volume_change",
]
