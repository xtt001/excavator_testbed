"""Shared primitive split record types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PrimitiveSlice:
    primitive_name: str
    window_name: str
    source_episode_id: int
    source_cycle_id: int
    start_step: int
    end_step_exclusive: int
    dump_intent_step: int | None = None
    official_dump_start_step: int | None = None
    source_dataset_dir: str | None = None
    source_prev_cycle_id: int | None = None
    source_next_cycle_id: int | None = None
    carry_qc: dict[str, Any] | None = None
    approach_qc: dict[str, Any] | None = None
    dump_qc: dict[str, Any] | None = None
    return_qc: dict[str, Any] | None = None
    v2_step_overlay: dict[str, np.ndarray] | None = None
    dump_release_step: int | None = None
    dump_end_step: int | None = None
    boundary_profile: str | None = None

    @property
    def window_len(self) -> int:
        return int(self.end_step_exclusive - self.start_step)


@dataclass(frozen=True)
class PrimitiveRejectRecord:
    primitive_name: str
    reason: str
    source_dataset_dir: str
    source_episode_id: int
    source_cycle_id: int
    start_step: int
    end_step_exclusive: int
    details: dict[str, Any] | None = None
