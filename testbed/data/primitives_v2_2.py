"""V2.2 primitive dataset builders.

The V2.2 splits keep the low-level ACT inputs non-privileged while using
existing V2.1 labels and target geometry for offline segmentation/QC only.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from testbed.data.hdf5_io import episode_id_from_path, list_episodes, read_episode, write_episode
from testbed.data.schema import (
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.transition_v2_1 import extract_transition_slices
from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID


PRIMITIVE_RECORDING_MODE = "primitive_relabel"
PRIMITIVE_VERSION = "v2_2_4primitives"
PRIMITIVE_VERSION_5P = "v2_2_5primitives"
PRIMITIVE_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")

DIG_WINDOW_NAME = "qualified_dig_start_to_before_carry"
CARRY_WINDOW_NAME = "carry_to_before_dump_intent"
DUMP_WINDOW_NAME = "dump_intent_to_dump_end"
RETURN_WINDOW_NAME = "dump_end_to_next_qualified_dig_start"
FIVEP_CARRY_WINDOW_NAME = "carry_to_before_approach_dump"
APPROACH_DUMP_WINDOW_NAME = "approach_dump_to_before_dump_release"
DUMP_RELEASE_WINDOW_NAME = "dump_release_to_dump_end_hold"

BUCKET_QPOS_INDEX = 3
BUCKET_ACTION_INDEX = 3
CARRY_PRE_DUMP_TRIM_STEPS = 120
CARRY_ACTION_HORIZON_STEPS = 100
CARRY_CURL_OUT_ACTIVE_QPOS_MIN = 0.20
CARRY_CURL_OUT_BUCKET_QPOS_MIN = 0.40
CARRY_CURL_OUT_BUCKET_ACTION_MAX = -0.20
CARRY_CURL_OUT_CONTINUE_ACTION_MAX = -0.08
CARRY_CURL_OUT_MIN_STABLE_STEPS = 5
CARRY_CURL_OUT_GUARD_STEPS = 10
CARRY_MIN_WINDOW_LEN = 120
CARRY_MAX_BUCKET_MASS_LOSS_KG = 150.0
CARRY_MAX_HARD_COLLISION_DELTA = 0
DUMP_INTENT_BUCKET_QPOS_MIN = 0.40
DUMP_INTENT_BUCKET_ACTION_MAX = -0.08
DUMP_INTENT_MIN_STABLE_STEPS = 3
DUMP_INTENT_MIN_BUCKET_MASS_KG = 150.0
DUMP_INTENT_MIN_HEIGHT_ABOVE_RIM_M = 0.30
DUMP_QC_FIRST_STEPS = 20
DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M = 0.0
DUMP_QC_NEAR_COLLISION_HORIZONTAL_M = 0.05
DUMP_RELEASE_POST_HOLD_STEPS = 30
APPROACH_DUMP_ACTION_HORIZON_STEPS = 100
APPROACH_DUMP_MIN_WINDOW_LEN = 20
APPROACH_DUMP_MAX_BUCKET_MASS_LOSS_KG = 150.0
APPROACH_DUMP_MAX_HARD_COLLISION_DELTA = 0
DUMP_RELEASE_MIN_WINDOW_LEN = 20


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
    dump_release_step: int | None = None
    dump_end_step: int | None = None

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


@dataclass(frozen=True)
class DumpIntentSearchResult:
    start_step: int | None
    qc: dict[str, Any]
    reject_reason: str | None = None


@dataclass(frozen=True)
class CarryTailTrimResult:
    end_step: int
    qc: dict[str, Any]
    reject_reason: str | None = None


def build_primitive_datasets(
    *,
    workskill_dir: str | Path,
    output_root: str | Path,
    raw_dirs: Iterable[str | Path] | None = None,
    require_return: bool = True,
    return_max_transition_len: int | None = None,
    return_clean_profile: str | None = None,
) -> dict[str, Any]:
    """Build V2.2 `dig/carry/dump/return` sibling datasets.

    `dig/carry/dump` are split from an existing V2.1 workskill dataset.
    `return` is split from full refreshed V2.1 raw datasets with the same
    `dump_end -> next qualified_dig_start` semantics as the transition builder.
    """
    workskill_dir = Path(workskill_dir)
    output_root = Path(output_root)
    raw_dirs_list = [Path(path) for path in (raw_dirs or [])]

    episode_paths = list_episodes(workskill_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {workskill_dir}")
    if require_return and not raw_dirs_list:
        raise ValueError("raw_dirs must be provided when require_return=True.")

    output_root.mkdir(parents=True, exist_ok=True)
    primitive_dirs = {name: output_root / name for name in PRIMITIVE_NAMES}
    for primitive_dir in primitive_dirs.values():
        existing_outputs = list_episodes(primitive_dir) if primitive_dir.exists() else []
        if existing_outputs:
            raise FileExistsError(
                f"Output primitive directory {primitive_dir} already contains episode files. "
                "Use a fresh output root for V2.2 primitive builds."
            )
        primitive_dir.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    rejects: list[PrimitiveRejectRecord] = []
    carry_qc_records: list[dict[str, Any]] = []
    dump_qc_records: list[dict[str, Any]] = []
    window_lengths: dict[str, list[int]] = {name: [] for name in PRIMITIVE_NAMES}
    next_episode_id: dict[str, int] = {name: 0 for name in PRIMITIVE_NAMES}

    for source_path in episode_paths:
        episode = read_episode(source_path)
        primitive_slices, slice_rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=source_path,
            source_dataset_dir=workskill_dir,
        )
        rejects.extend(slice_rejects)
        for primitive_slice in primitive_slices:
            primitive_name = primitive_slice.primitive_name
            output_episode_id = next_episode_id[primitive_name]
            target_path = primitive_dirs[primitive_name] / f"episode_{output_episode_id}.hdf5"
            write_primitive_episode(
                target_path=target_path,
                source_episode=episode,
                source_dataset_dir=workskill_dir,
                primitive_slice=primitive_slice,
                output_episode_id=output_episode_id,
                cycle_id_offset=0,
            )
            next_episode_id[primitive_name] += 1
            counts[primitive_name] += 1
            window_lengths[primitive_name].append(int(primitive_slice.window_len))
            if primitive_name == "carry" and primitive_slice.carry_qc:
                carry_qc_records.append(dict(primitive_slice.carry_qc))
            if primitive_name == "dump" and primitive_slice.dump_qc:
                dump_qc_records.append(dict(primitive_slice.dump_qc))

    if raw_dirs_list:
        for raw_dir in raw_dirs_list:
            raw_episode_paths = list_episodes(raw_dir)
            if not raw_episode_paths:
                raise FileNotFoundError(f"No episode_*.hdf5 files found under {raw_dir}")
            for source_path in raw_episode_paths:
                episode = read_episode(source_path)
                transition_slices, transition_rejects = extract_transition_slices(
                    episode=episode,
                    source_path=source_path,
                    max_transition_len=return_max_transition_len,
                    clean_profile=return_clean_profile,
                )
                for transition_reject in transition_rejects:
                    rejects.append(
                        PrimitiveRejectRecord(
                            primitive_name="return",
                            reason=str(transition_reject.reason),
                            source_dataset_dir=str(raw_dir.resolve()),
                            source_episode_id=int(transition_reject.source_episode_id),
                            source_cycle_id=int(transition_reject.prev_cycle_id),
                            start_step=int(transition_reject.gap_steps),
                            end_step_exclusive=int(transition_reject.window_len),
                        )
                    )
                for transition_slice in transition_slices:
                    primitive_slice = PrimitiveSlice(
                        primitive_name="return",
                        window_name=RETURN_WINDOW_NAME,
                        source_episode_id=int(transition_slice.source_episode_id),
                        source_cycle_id=int(transition_slice.prev_cycle_id),
                        source_prev_cycle_id=int(transition_slice.prev_cycle_id),
                        source_next_cycle_id=int(transition_slice.next_cycle_id),
                        start_step=int(transition_slice.dump_end_step),
                        end_step_exclusive=int(transition_slice.next_start_step) + 1,
                        source_dataset_dir=str(raw_dir.resolve()),
                    )
                    output_episode_id = next_episode_id["return"]
                    target_path = primitive_dirs["return"] / f"episode_{output_episode_id}.hdf5"
                    write_primitive_episode(
                        target_path=target_path,
                        source_episode=episode,
                        source_dataset_dir=raw_dir,
                        primitive_slice=primitive_slice,
                        output_episode_id=output_episode_id,
                        cycle_id_offset=int(transition_slice.prev_cycle_id),
                    )
                    next_episode_id["return"] += 1
                    counts["return"] += 1
                    window_lengths["return"].append(int(primitive_slice.window_len))

    missing = [
        primitive_name
        for primitive_name in PRIMITIVE_NAMES
        if counts[primitive_name] <= 0 and (primitive_name != "return" or require_return)
    ]
    if missing:
        raise RuntimeError(
            "V2.2 primitive build produced empty dataset(s): "
            + ", ".join(missing)
            + ". Refusing to leave an incomplete primitive root."
        )

    summary = _build_summary(
        workskill_dir=workskill_dir,
        raw_dirs=raw_dirs_list,
        output_root=output_root,
        counts=counts,
        window_lengths=window_lengths,
        rejects=rejects,
        return_max_transition_len=return_max_transition_len,
        return_clean_profile=return_clean_profile,
        carry_qc_records=carry_qc_records,
        dump_qc_records=dump_qc_records,
    )
    with open(output_root / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    return summary


def build_primitive_datasets_5p(
    *,
    workskill_dir: str | Path,
    output_root: str | Path,
    raw_dirs: Iterable[str | Path] | None = None,
    require_return: bool = True,
    return_max_transition_len: int | None = None,
    return_clean_profile: str | None = None,
) -> dict[str, Any]:
    """Build V2.2 `dig/carry/approach_dump/dump_release/return` datasets."""
    workskill_dir = Path(workskill_dir)
    output_root = Path(output_root)
    raw_dirs_list = [Path(path) for path in (raw_dirs or [])]

    episode_paths = list_episodes(workskill_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {workskill_dir}")
    if require_return and not raw_dirs_list:
        raise ValueError("raw_dirs must be provided when require_return=True.")

    output_root.mkdir(parents=True, exist_ok=True)
    primitive_dirs = {name: output_root / name for name in PRIMITIVE_NAMES_5P}
    for primitive_dir in primitive_dirs.values():
        existing_outputs = list_episodes(primitive_dir) if primitive_dir.exists() else []
        if existing_outputs:
            raise FileExistsError(
                f"Output primitive directory {primitive_dir} already contains episode files. "
                "Use a fresh output root for V2.2 5-primitive builds."
            )
        primitive_dir.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    rejects: list[PrimitiveRejectRecord] = []
    carry_qc_records: list[dict[str, Any]] = []
    approach_qc_records: list[dict[str, Any]] = []
    dump_qc_records: list[dict[str, Any]] = []
    window_lengths: dict[str, list[int]] = {name: [] for name in PRIMITIVE_NAMES_5P}
    next_episode_id: dict[str, int] = {name: 0 for name in PRIMITIVE_NAMES_5P}

    for source_path in episode_paths:
        episode = read_episode(source_path)
        primitive_slices, slice_rejects = extract_workskill_primitive_slices_5p(
            episode=episode,
            source_path=source_path,
            source_dataset_dir=workskill_dir,
        )
        rejects.extend(slice_rejects)
        for primitive_slice in primitive_slices:
            primitive_name = primitive_slice.primitive_name
            output_episode_id = next_episode_id[primitive_name]
            target_path = primitive_dirs[primitive_name] / f"episode_{output_episode_id}.hdf5"
            write_primitive_episode(
                target_path=target_path,
                source_episode=episode,
                source_dataset_dir=workskill_dir,
                primitive_slice=primitive_slice,
                output_episode_id=output_episode_id,
                cycle_id_offset=0,
                primitive_version=PRIMITIVE_VERSION_5P,
            )
            next_episode_id[primitive_name] += 1
            counts[primitive_name] += 1
            window_lengths[primitive_name].append(int(primitive_slice.window_len))
            if primitive_name == "carry" and primitive_slice.carry_qc:
                carry_qc_records.append(dict(primitive_slice.carry_qc))
            if primitive_name == "approach_dump" and primitive_slice.approach_qc:
                approach_qc_records.append(dict(primitive_slice.approach_qc))
            if primitive_name == "dump_release" and primitive_slice.dump_qc:
                dump_qc_records.append(dict(primitive_slice.dump_qc))

    if raw_dirs_list:
        for raw_dir in raw_dirs_list:
            raw_episode_paths = list_episodes(raw_dir)
            if not raw_episode_paths:
                raise FileNotFoundError(f"No episode_*.hdf5 files found under {raw_dir}")
            for source_path in raw_episode_paths:
                episode = read_episode(source_path)
                transition_slices, transition_rejects = extract_transition_slices(
                    episode=episode,
                    source_path=source_path,
                    max_transition_len=return_max_transition_len,
                    clean_profile=return_clean_profile,
                )
                for transition_reject in transition_rejects:
                    rejects.append(
                        PrimitiveRejectRecord(
                            primitive_name="return",
                            reason=str(transition_reject.reason),
                            source_dataset_dir=str(raw_dir.resolve()),
                            source_episode_id=int(transition_reject.source_episode_id),
                            source_cycle_id=int(transition_reject.prev_cycle_id),
                            start_step=int(transition_reject.gap_steps),
                            end_step_exclusive=int(transition_reject.window_len),
                        )
                    )
                for transition_slice in transition_slices:
                    primitive_slice = PrimitiveSlice(
                        primitive_name="return",
                        window_name=RETURN_WINDOW_NAME,
                        source_episode_id=int(transition_slice.source_episode_id),
                        source_cycle_id=int(transition_slice.prev_cycle_id),
                        source_prev_cycle_id=int(transition_slice.prev_cycle_id),
                        source_next_cycle_id=int(transition_slice.next_cycle_id),
                        start_step=int(transition_slice.dump_end_step),
                        end_step_exclusive=int(transition_slice.next_start_step) + 1,
                        source_dataset_dir=str(raw_dir.resolve()),
                    )
                    output_episode_id = next_episode_id["return"]
                    target_path = primitive_dirs["return"] / f"episode_{output_episode_id}.hdf5"
                    write_primitive_episode(
                        target_path=target_path,
                        source_episode=episode,
                        source_dataset_dir=raw_dir,
                        primitive_slice=primitive_slice,
                        output_episode_id=output_episode_id,
                        cycle_id_offset=int(transition_slice.prev_cycle_id),
                        primitive_version=PRIMITIVE_VERSION_5P,
                    )
                    next_episode_id["return"] += 1
                    counts["return"] += 1
                    window_lengths["return"].append(int(primitive_slice.window_len))

    missing = [
        primitive_name
        for primitive_name in PRIMITIVE_NAMES_5P
        if counts[primitive_name] <= 0 and (primitive_name != "return" or require_return)
    ]
    if missing:
        raise RuntimeError(
            "V2.2 5-primitive build produced empty dataset(s): "
            + ", ".join(missing)
            + ". Refusing to leave an incomplete primitive root."
        )

    summary = _build_summary(
        workskill_dir=workskill_dir,
        raw_dirs=raw_dirs_list,
        output_root=output_root,
        counts=counts,
        window_lengths=window_lengths,
        rejects=rejects,
        return_max_transition_len=return_max_transition_len,
        return_clean_profile=return_clean_profile,
        carry_qc_records=carry_qc_records,
        dump_qc_records=dump_qc_records,
        primitive_version=PRIMITIVE_VERSION_5P,
        primitive_names=PRIMITIVE_NAMES_5P,
        approach_qc_records=approach_qc_records,
    )
    with open(output_root / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    return summary


def extract_workskill_primitive_slices(
    *,
    episode: dict[str, Any],
    source_path: str | Path,
    source_dataset_dir: str | Path,
) -> tuple[list[PrimitiveSlice], list[PrimitiveRejectRecord]]:
    """Split one cropped V2.1 workskill episode into `dig/carry/dump`."""
    source_path = Path(source_path)
    source_dataset_dir = Path(source_dataset_dir)
    source_episode_id = _source_episode_id(episode=episode, source_path=source_path)
    source_cycle_id = _source_cycle_id(episode=episode)
    source_start_offset = _source_start_step_offset(episode=episode)

    v2_step = _require_v2_step(episode=episode, source_path=source_path)
    work_stage_id = np.asarray(v2_step.get("work_stage_id"), dtype=np.int32)
    dump_start_mask = np.asarray(v2_step.get("dump_start_mask", []), dtype=np.uint8)
    n_steps = int(len(episode["actions"]))
    if work_stage_id.shape[0] != n_steps:
        raise ValueError(
            f"Episode {source_path.name} work_stage_id length {work_stage_id.shape[0]} "
            f"does not match action length {n_steps}."
        )

    carry_start = _first_index_where(
        work_stage_id,
        {
            WORK_STAGE_NAME_TO_ID["carry"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
        },
    )
    official_dump_start = _first_dump_start(
        work_stage_id=work_stage_id,
        dump_start_mask=dump_start_mask,
    )
    dump_intent = _find_dump_intent_start(
        episode=episode,
        work_stage_id=work_stage_id,
        official_dump_start=official_dump_start,
    )
    dump_intent_start = dump_intent.start_step

    slices: list[PrimitiveSlice] = []
    rejects: list[PrimitiveRejectRecord] = []

    def _append_or_reject(
        *,
        primitive_name: str,
        window_name: str,
        start: int,
        end: int,
        reason_if_invalid: str = "invalid_window",
        carry_qc: dict[str, Any] | None = None,
        dump_qc: dict[str, Any] | None = None,
    ) -> None:
        if end <= start:
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name=primitive_name,
                    reason=reason_if_invalid,
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + start),
                    end_step_exclusive=int(source_start_offset + end),
                    details=carry_qc if primitive_name == "carry" else dump_qc,
                )
            )
            return
        slices.append(
            PrimitiveSlice(
                primitive_name=primitive_name,
                window_name=window_name,
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(start),
                end_step_exclusive=int(end),
                dump_intent_step=None
                if dump_intent_start is None
                else int(source_start_offset + dump_intent_start),
                official_dump_start_step=None
                if official_dump_start is None
                else int(source_start_offset + official_dump_start),
                source_dataset_dir=str(source_dataset_dir.resolve()),
                carry_qc=carry_qc if primitive_name == "carry" else None,
                dump_qc=dump_qc if primitive_name == "dump" else None,
            )
        )

    if carry_start is None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="dig",
                reason="missing_carry_or_approach_boundary",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset),
                end_step_exclusive=int(source_start_offset + n_steps),
            )
        )
    else:
        _append_or_reject(
            primitive_name="dig",
            window_name=DIG_WINDOW_NAME,
            start=0,
            end=int(carry_start),
        )

    if dump_intent_start is None:
        reason = dump_intent.reject_reason or "missing_safe_dump_intent"
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="carry",
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + (carry_start or 0)),
                end_step_exclusive=int(source_start_offset + n_steps),
                details=dump_intent.qc,
            )
        )
    elif carry_start is None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="carry",
                reason="missing_carry_start",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset),
                end_step_exclusive=int(source_start_offset + dump_intent_start),
            )
        )
    else:
        carry_trim = _trim_carry_end_before_dump_tail(
            episode=episode,
            carry_start=int(carry_start),
            dump_intent_start=int(dump_intent_start),
        )
        if carry_trim.reject_reason is not None:
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name="carry",
                    reason=carry_trim.reject_reason,
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + carry_start),
                    end_step_exclusive=int(source_start_offset + carry_trim.end_step),
                    details=carry_trim.qc,
                )
            )
        else:
            _append_or_reject(
                primitive_name="carry",
                window_name=CARRY_WINDOW_NAME,
                start=int(carry_start),
                end=int(carry_trim.end_step),
                reason_if_invalid="carry_too_short_after_tail_trim",
                carry_qc=carry_trim.qc,
            )

    if dump_intent_start is None:
        reason = dump_intent.reject_reason or "missing_safe_dump_intent"
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="dump",
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset),
                end_step_exclusive=int(source_start_offset + n_steps),
                details=dump_intent.qc,
            )
        )
    else:
        _append_or_reject(
            primitive_name="dump",
            window_name=DUMP_WINDOW_NAME,
            start=int(dump_intent_start),
            end=n_steps,
            dump_qc=dump_intent.qc,
        )

    return slices, rejects


def extract_workskill_primitive_slices_5p(
    *,
    episode: dict[str, Any],
    source_path: str | Path,
    source_dataset_dir: str | Path,
) -> tuple[list[PrimitiveSlice], list[PrimitiveRejectRecord]]:
    """Split one cropped V2.1 workskill episode into 5 V2.2 primitives."""
    source_path = Path(source_path)
    source_dataset_dir = Path(source_dataset_dir)
    source_episode_id = _source_episode_id(episode=episode, source_path=source_path)
    source_cycle_id = _source_cycle_id(episode=episode)
    source_start_offset = _source_start_step_offset(episode=episode)

    v2_step = _require_v2_step(episode=episode, source_path=source_path)
    work_stage_id = np.asarray(v2_step.get("work_stage_id"), dtype=np.int32)
    dump_start_mask = np.asarray(v2_step.get("dump_start_mask", []), dtype=np.uint8)
    dump_end_mask = np.asarray(v2_step.get("dump_end_mask", []), dtype=np.uint8)
    n_steps = int(len(episode["actions"]))
    if work_stage_id.shape[0] != n_steps:
        raise ValueError(
            f"Episode {source_path.name} work_stage_id length {work_stage_id.shape[0]} "
            f"does not match action length {n_steps}."
        )

    carry_start = _first_index_where(work_stage_id, {WORK_STAGE_NAME_TO_ID["carry"]})
    approach_start = _first_index_where(
        work_stage_id,
        {WORK_STAGE_NAME_TO_ID["approach_dump"]},
    )
    official_dump_start = _first_dump_start(
        work_stage_id=work_stage_id,
        dump_start_mask=dump_start_mask,
    )
    dump_release = _find_dump_release_start_5p(
        episode=episode,
        work_stage_id=work_stage_id,
        official_dump_start=official_dump_start,
    )
    dump_release_start = dump_release.start_step
    dump_end_step = _first_dump_end(
        dump_end_mask=dump_end_mask,
        start=0 if dump_release_start is None else int(dump_release_start),
        n_steps=n_steps,
    )
    dump_release_end = (
        n_steps
        if dump_end_step is None
        else min(n_steps, int(dump_end_step) + 1 + DUMP_RELEASE_POST_HOLD_STEPS)
    )

    slices: list[PrimitiveSlice] = []
    rejects: list[PrimitiveRejectRecord] = []

    def _reject(
        *,
        primitive_name: str,
        reason: str,
        start: int,
        end: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name=primitive_name,
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + start),
                end_step_exclusive=int(source_start_offset + end),
                details=details,
            )
        )

    def _append_or_reject(
        *,
        primitive_name: str,
        window_name: str,
        start: int,
        end: int,
        reason_if_invalid: str = "invalid_window",
        carry_qc: dict[str, Any] | None = None,
        approach_qc: dict[str, Any] | None = None,
        dump_qc: dict[str, Any] | None = None,
    ) -> None:
        if end <= start:
            _reject(
                primitive_name=primitive_name,
                reason=reason_if_invalid,
                start=start,
                end=end,
                details=carry_qc or approach_qc or dump_qc,
            )
            return
        slices.append(
            PrimitiveSlice(
                primitive_name=primitive_name,
                window_name=window_name,
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(start),
                end_step_exclusive=int(end),
                dump_intent_step=None
                if dump_release_start is None
                else int(source_start_offset + dump_release_start),
                official_dump_start_step=None
                if official_dump_start is None
                else int(source_start_offset + official_dump_start),
                source_dataset_dir=str(source_dataset_dir.resolve()),
                carry_qc=carry_qc,
                approach_qc=approach_qc,
                dump_qc=dump_qc,
                dump_release_step=None
                if dump_release_start is None
                else int(source_start_offset + dump_release_start),
                dump_end_step=None
                if dump_end_step is None
                else int(source_start_offset + dump_end_step),
            )
        )

    dig_end = carry_start if carry_start is not None else approach_start
    if dig_end is None:
        _reject(
            primitive_name="dig",
            reason="missing_carry_or_approach_boundary",
            start=0,
            end=n_steps,
        )
    else:
        _append_or_reject(
            primitive_name="dig",
            window_name=DIG_WINDOW_NAME,
            start=0,
            end=int(dig_end),
        )

    if carry_start is None:
        _reject(
            primitive_name="carry",
            reason="missing_carry_start",
            start=0,
            end=0 if approach_start is None else int(approach_start),
        )
    elif approach_start is None:
        _reject(
            primitive_name="carry",
            reason="missing_approach_dump_stage",
            start=int(carry_start),
            end=n_steps,
        )
    else:
        carry_qc = _window_tail_qc(
            episode=episode,
            prefix="carry",
            start=int(carry_start),
            end=int(approach_start),
            release_start=dump_release_start,
        )
        if (
            float(carry_qc.get("carry_bucket_mass_loss_kg", 0.0))
            > CARRY_MAX_BUCKET_MASS_LOSS_KG
        ):
            _reject(
                primitive_name="carry",
                reason="carry_mass_loss_before_approach",
                start=int(carry_start),
                end=int(approach_start),
                details=carry_qc,
            )
        elif (
            int(carry_qc.get("carry_hard_collision_delta_count", 0))
            > CARRY_MAX_HARD_COLLISION_DELTA
        ):
            _reject(
                primitive_name="carry",
                reason="carry_hard_collision",
                start=int(carry_start),
                end=int(approach_start),
                details=carry_qc,
            )
        else:
            _append_or_reject(
                primitive_name="carry",
                window_name=FIVEP_CARRY_WINDOW_NAME,
                start=int(carry_start),
                end=int(approach_start),
                carry_qc=carry_qc,
            )

    if approach_start is None:
        _reject(
            primitive_name="approach_dump",
            reason="missing_approach_dump_stage",
            start=0 if carry_start is None else int(carry_start),
            end=n_steps,
        )
    elif dump_release_start is None:
        _reject(
            primitive_name="approach_dump",
            reason=dump_release.reject_reason or "missing_safe_dump_intent",
            start=int(approach_start),
            end=n_steps,
            details=dump_release.qc,
        )
    else:
        approach_qc = _window_tail_qc(
            episode=episode,
            prefix="approach_dump",
            start=int(approach_start),
            end=int(dump_release_start),
            release_start=int(dump_release_start),
        )
        if int(dump_release_start) - int(approach_start) < APPROACH_DUMP_MIN_WINDOW_LEN:
            _reject(
                primitive_name="approach_dump",
                reason="approach_dump_too_short",
                start=int(approach_start),
                end=int(dump_release_start),
                details=approach_qc,
            )
        elif (
            float(approach_qc.get("approach_dump_bucket_mass_loss_kg", 0.0))
            > APPROACH_DUMP_MAX_BUCKET_MASS_LOSS_KG
        ):
            _reject(
                primitive_name="approach_dump",
                reason="approach_dump_mass_loss_before_release",
                start=int(approach_start),
                end=int(dump_release_start),
                details=approach_qc,
            )
        elif (
            int(approach_qc.get("approach_dump_hard_collision_delta_count", 0))
            > APPROACH_DUMP_MAX_HARD_COLLISION_DELTA
        ):
            _reject(
                primitive_name="approach_dump",
                reason="approach_dump_hard_collision",
                start=int(approach_start),
                end=int(dump_release_start),
                details=approach_qc,
            )
        else:
            _append_or_reject(
                primitive_name="approach_dump",
                window_name=APPROACH_DUMP_WINDOW_NAME,
                start=int(approach_start),
                end=int(dump_release_start),
                approach_qc=approach_qc,
            )

    if dump_release_start is None:
        _reject(
            primitive_name="dump_release",
            reason=dump_release.reject_reason or "missing_safe_dump_intent",
            start=0,
            end=n_steps,
            details=dump_release.qc,
        )
    else:
        if dump_release_end - int(dump_release_start) < DUMP_RELEASE_MIN_WINDOW_LEN:
            _reject(
                primitive_name="dump_release",
                reason="dump_release_too_short",
                start=int(dump_release_start),
                end=int(dump_release_end),
                details=dump_release.qc,
            )
        else:
            _append_or_reject(
                primitive_name="dump_release",
                window_name=DUMP_RELEASE_WINDOW_NAME,
                start=int(dump_release_start),
                end=int(dump_release_end),
                dump_qc=dump_release.qc,
            )

    return slices, rejects


def write_primitive_episode(
    *,
    target_path: str | Path,
    source_episode: dict[str, Any],
    source_dataset_dir: str | Path,
    primitive_slice: PrimitiveSlice,
    output_episode_id: int,
    cycle_id_offset: int = 0,
    primitive_version: str = PRIMITIVE_VERSION,
) -> None:
    """Write a cropped primitive HDF5 episode."""
    start = int(primitive_slice.start_step)
    end = int(primitive_slice.end_step_exclusive)
    crop = slice(start, end)
    window_len = end - start
    if window_len <= 0:
        raise ValueError("Primitive slice must contain at least one timestep.")

    source_start_offset = _source_start_step_offset(episode=source_episode)
    absolute_start = int(source_start_offset + start)
    absolute_end_exclusive = int(source_start_offset + end)
    metadata = dict(source_episode.get("metadata", {}))
    metadata.update(
        {
            "episode_id": f"episode_{output_episode_id}",
            "recording_mode": PRIMITIVE_RECORDING_MODE,
            "primitive_version": str(primitive_version),
            "primitive_name": str(primitive_slice.primitive_name),
            "primitive_window": str(primitive_slice.window_name),
            "source_dataset_dir": str(Path(source_dataset_dir).resolve()),
            "source_episode_id": f"episode_{primitive_slice.source_episode_id}",
            "source_cycle_id": int(primitive_slice.source_cycle_id),
            "source_start_step": int(absolute_start),
            "source_end_step_exclusive": int(absolute_end_exclusive),
            "source_window_len": int(window_len),
        }
    )
    if primitive_slice.dump_intent_step is not None:
        metadata["dump_intent_step"] = int(primitive_slice.dump_intent_step)
    if primitive_slice.official_dump_start_step is not None:
        metadata["official_dump_start_step"] = int(primitive_slice.official_dump_start_step)
    if primitive_slice.dump_release_step is not None:
        metadata["dump_release_step"] = int(primitive_slice.dump_release_step)
    if primitive_slice.dump_end_step is not None:
        metadata["dump_end_step"] = int(primitive_slice.dump_end_step)
    if primitive_slice.source_prev_cycle_id is not None:
        metadata["source_prev_cycle_id"] = int(primitive_slice.source_prev_cycle_id)
    if primitive_slice.source_next_cycle_id is not None:
        metadata["source_next_cycle_id"] = int(primitive_slice.source_next_cycle_id)
    for key, value in dict(primitive_slice.carry_qc or {}).items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, (bool, int, float, str)):
            metadata[str(key)] = value
    for key, value in dict(primitive_slice.approach_qc or {}).items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, (bool, int, float, str)):
            metadata[str(key)] = value
    for key, value in dict(primitive_slice.dump_qc or {}).items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, (bool, int, float, str)):
            metadata[str(key)] = value

    images = {
        camera_name: np.asarray(camera_frames[crop])
        for camera_name, camera_frames in dict(source_episode.get("images", {})).items()
    }
    v2_payload = build_primitive_v2_payload(
        source_episode=source_episode,
        crop=crop,
        cycle_id_offset=cycle_id_offset,
        zero_cycle_id=(primitive_slice.primitive_name != "return"),
    )

    write_episode(
        target_path,
        qpos=np.asarray(source_episode["qpos"][crop], dtype=np.float32),
        qvel=np.asarray(source_episode["qvel"][crop], dtype=np.float32),
        actions=np.asarray(source_episode["actions"][crop], dtype=np.float32),
        images=images or None,
        rewards=_slice_optional_array(source_episode.get("rewards"), crop),
        metadata=metadata,
        env_state=_slice_optional_array(source_episode.get("env_state"), crop),
        step_ids=_slice_optional_array(source_episode.get("step_ids"), crop, dtype=np.int64),
        step_ns=_slice_optional_array(source_episode.get("step_ns"), crop, dtype=np.int64),
        action_src_types=_slice_optional_list(source_episode.get("action_src_types"), crop),
        action_src_ids=_slice_optional_list(source_episode.get("action_src_ids"), crop),
        v2=v2_payload,
    )


def build_primitive_v2_payload(
    *,
    source_episode: dict[str, Any],
    crop: slice,
    cycle_id_offset: int = 0,
    zero_cycle_id: bool = True,
) -> dict[str, dict[str, np.ndarray]]:
    v2 = source_episode.get("v2")
    if not v2:
        raise KeyError("Source episode is missing /v2 data.")

    step_payload = {
        key: np.asarray(value[crop])
        for key, value in dict(v2.get("step", {})).items()
    }
    if not step_payload:
        raise KeyError("Source episode /v2/step is empty.")
    if "cycle_id" in step_payload:
        if zero_cycle_id:
            step_payload["cycle_id"] = np.zeros(
                len(step_payload["cycle_id"]),
                dtype=np.int32,
            )
        else:
            step_payload["cycle_id"] = (
                np.asarray(step_payload["cycle_id"], dtype=np.int32) - int(cycle_id_offset)
            ).astype(np.int32)

    return {
        "step": step_payload,
        "cycle": {},
    }


def _trim_carry_end_before_dump_tail(
    *,
    episode: dict[str, Any],
    carry_start: int,
    dump_intent_start: int,
) -> CarryTailTrimResult:
    """Trim carry before dump-tail actions can enter ACT's supervised horizon."""
    carry_start = int(carry_start)
    dump_intent_start = int(dump_intent_start)
    horizon_trim_end = int(dump_intent_start - CARRY_PRE_DUMP_TRIM_STEPS)
    stable_curl_out_onset = _find_stable_carry_curl_out_onset(
        episode=episode,
        start=carry_start,
        end=dump_intent_start,
    )
    curl_trim_end = (
        None
        if stable_curl_out_onset is None
        else int(stable_curl_out_onset - CARRY_CURL_OUT_GUARD_STEPS)
    )
    candidate_ends = [horizon_trim_end]
    if curl_trim_end is not None:
        candidate_ends.append(curl_trim_end)
    carry_end = int(min(candidate_ends))
    qc = _carry_tail_qc(
        episode=episode,
        carry_start=carry_start,
        carry_end=carry_end,
        dump_intent_start=dump_intent_start,
        stable_curl_out_onset=stable_curl_out_onset,
        horizon_trim_end=horizon_trim_end,
        curl_trim_end=curl_trim_end,
    )
    if carry_end - carry_start < CARRY_MIN_WINDOW_LEN:
        return CarryTailTrimResult(
            end_step=carry_end,
            qc=qc,
            reject_reason="carry_too_short_after_tail_trim",
        )
    return CarryTailTrimResult(end_step=carry_end, qc=qc)


def _find_stable_carry_curl_out_onset(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> int | None:
    qpos = np.asarray(episode["qpos"], dtype=np.float32)
    actions = np.asarray(episode["actions"], dtype=np.float32)
    if qpos.ndim != 2 or actions.ndim != 2:
        raise ValueError("qpos/actions must be rank-2 arrays.")
    if qpos.shape[1] <= BUCKET_QPOS_INDEX or actions.shape[1] <= BUCKET_ACTION_INDEX:
        return None
    bucket_qpos = qpos[:, BUCKET_QPOS_INDEX]
    bucket_action = actions[:, BUCKET_ACTION_INDEX]
    strong_action = (
        (bucket_qpos >= CARRY_CURL_OUT_ACTIVE_QPOS_MIN)
        & (bucket_action <= CARRY_CURL_OUT_BUCKET_ACTION_MAX)
    )
    continuing_dump = (
        (bucket_qpos >= CARRY_CURL_OUT_BUCKET_QPOS_MIN)
        & (bucket_action <= CARRY_CURL_OUT_CONTINUE_ACTION_MAX)
    )
    for onset in _stable_true_indices(
        strong_action,
        start=int(start),
        end=int(end),
        min_stable_steps=CARRY_CURL_OUT_MIN_STABLE_STEPS,
    ):
        return int(onset)
    continuing_dump_start = max(int(start), int(end) - CARRY_PRE_DUMP_TRIM_STEPS)
    for onset in _stable_true_indices(
        continuing_dump,
        start=continuing_dump_start,
        end=int(end),
        min_stable_steps=CARRY_CURL_OUT_MIN_STABLE_STEPS,
    ):
        return int(onset)
    return None


def _carry_tail_qc(
    *,
    episode: dict[str, Any],
    carry_start: int,
    carry_end: int,
    dump_intent_start: int,
    stable_curl_out_onset: int | None,
    horizon_trim_end: int,
    curl_trim_end: int | None,
) -> dict[str, Any]:
    qpos = np.asarray(episode["qpos"], dtype=np.float32)
    actions = np.asarray(episode["actions"], dtype=np.float32)
    tail_start = max(int(carry_start), int(carry_end) - CARRY_ACTION_HORIZON_STEPS)
    tail_end = max(tail_start, int(carry_end))
    tail_bucket_action = actions[tail_start:tail_end, BUCKET_ACTION_INDEX]
    tail_bucket_qpos = qpos[tail_start:tail_end, BUCKET_QPOS_INDEX]
    stable_tail_curl = False
    if len(tail_bucket_action) > 0:
        strong_tail = (
            (tail_bucket_qpos >= CARRY_CURL_OUT_ACTIVE_QPOS_MIN)
            & (tail_bucket_action <= CARRY_CURL_OUT_BUCKET_ACTION_MAX)
        )
        stable_tail_curl = any(
            True
            for _ in _stable_true_indices(
                strong_tail,
                start=0,
                end=len(strong_tail),
                min_stable_steps=CARRY_CURL_OUT_MIN_STABLE_STEPS,
            )
        )

    qc: dict[str, Any] = {
        "carry_pre_dump_trim_steps": int(CARRY_PRE_DUMP_TRIM_STEPS),
        "carry_action_horizon_steps": int(CARRY_ACTION_HORIZON_STEPS),
        "carry_curl_out_guard_steps": int(CARRY_CURL_OUT_GUARD_STEPS),
        "carry_start_step": int(carry_start),
        "carry_end_step": int(carry_end),
        "carry_window_len": int(carry_end - carry_start),
        "carry_dump_intent_step": int(dump_intent_start),
        "carry_removed_pre_dump_steps": int(dump_intent_start - carry_end),
        "carry_horizon_trim_end_step": int(horizon_trim_end),
        "carry_curl_trim_end_step": -1 if curl_trim_end is None else int(curl_trim_end),
        "carry_stable_curl_out_onset_step": (
            -1 if stable_curl_out_onset is None else int(stable_curl_out_onset)
        ),
        "carry_tail_start_step": int(tail_start),
        "carry_tail_len": int(tail_end - tail_start),
        "carry_tail_has_stable_strong_curl_out": bool(stable_tail_curl),
    }
    if len(tail_bucket_action) > 0:
        qc.update(
            {
                "carry_tail_bucket_action_min": float(np.min(tail_bucket_action)),
                "carry_tail_bucket_action_median": float(np.median(tail_bucket_action)),
                "carry_tail_bucket_action_max": float(np.max(tail_bucket_action)),
                "carry_tail_bucket_qpos_min": float(np.min(tail_bucket_qpos)),
                "carry_tail_bucket_qpos_median": float(np.median(tail_bucket_qpos)),
                "carry_tail_bucket_qpos_max": float(np.max(tail_bucket_qpos)),
            }
        )

    env_state = _target_geometry_env_state(episode=episode)
    if env_state is not None and carry_start < len(env_state) and carry_end > carry_start:
        mass_start = float(env_state[carry_start, ENV_STATE_MASS_IN_BUCKET_IDX])
        mass_end = float(env_state[carry_end - 1, ENV_STATE_MASS_IN_BUCKET_IDX])
        qc.update(
            {
                "carry_start_bucket_mass_kg": float(mass_start),
                "carry_end_bucket_mass_kg": float(mass_end),
                "carry_bucket_mass_loss_kg": float(max(0.0, mass_start - mass_end)),
            }
        )
    return qc


def _window_tail_qc(
    *,
    episode: dict[str, Any],
    prefix: str,
    start: int,
    end: int,
    release_start: int | None,
) -> dict[str, Any]:
    qpos = np.asarray(episode["qpos"], dtype=np.float32)
    actions = np.asarray(episode["actions"], dtype=np.float32)
    start = int(start)
    end = int(end)
    tail_horizon = (
        APPROACH_DUMP_ACTION_HORIZON_STEPS
        if prefix == "approach_dump"
        else CARRY_ACTION_HORIZON_STEPS
    )
    tail_start = max(start, end - tail_horizon)
    tail_bucket_action = actions[tail_start:end, BUCKET_ACTION_INDEX]
    tail_bucket_qpos = qpos[tail_start:end, BUCKET_QPOS_INDEX]
    stable_tail_curl = False
    stable_tail_release = False
    if len(tail_bucket_action) > 0:
        strong_tail = (
            (tail_bucket_qpos >= CARRY_CURL_OUT_ACTIVE_QPOS_MIN)
            & (tail_bucket_action <= CARRY_CURL_OUT_BUCKET_ACTION_MAX)
        )
        release_tail = (
            (tail_bucket_qpos >= DUMP_INTENT_BUCKET_QPOS_MIN)
            & (tail_bucket_action <= DUMP_INTENT_BUCKET_ACTION_MAX)
        )
        stable_tail_curl = any(
            True
            for _ in _stable_true_indices(
                strong_tail,
                start=0,
                end=len(strong_tail),
                min_stable_steps=CARRY_CURL_OUT_MIN_STABLE_STEPS,
            )
        )
        stable_tail_release = any(
            True
            for _ in _stable_true_indices(
                release_tail,
                start=0,
                end=len(release_tail),
                min_stable_steps=DUMP_INTENT_MIN_STABLE_STEPS,
            )
        )

    qc: dict[str, Any] = {
        f"{prefix}_start_step": int(start),
        f"{prefix}_end_step": int(end),
        f"{prefix}_window_len": int(end - start),
        f"{prefix}_release_start_step": (
            -1 if release_start is None else int(release_start)
        ),
        f"{prefix}_tail_horizon_steps": int(tail_horizon),
        f"{prefix}_tail_start_step": int(tail_start),
        f"{prefix}_tail_len": int(end - tail_start),
        f"{prefix}_tail_has_stable_strong_curl_out": bool(stable_tail_curl),
        f"{prefix}_tail_has_stable_release": bool(stable_tail_release),
    }
    if release_start is not None:
        qc[f"{prefix}_steps_before_release"] = int(release_start - end)
    if len(tail_bucket_action) > 0:
        qc.update(
            {
                f"{prefix}_tail_bucket_action_min": float(np.min(tail_bucket_action)),
                f"{prefix}_tail_bucket_action_median": float(np.median(tail_bucket_action)),
                f"{prefix}_tail_bucket_action_max": float(np.max(tail_bucket_action)),
                f"{prefix}_tail_bucket_qpos_min": float(np.min(tail_bucket_qpos)),
                f"{prefix}_tail_bucket_qpos_median": float(np.median(tail_bucket_qpos)),
                f"{prefix}_tail_bucket_qpos_max": float(np.max(tail_bucket_qpos)),
            }
        )

    env_state = _target_geometry_env_state(episode=episode)
    if env_state is not None and start < len(env_state) and end > start:
        mass_start = float(env_state[start, ENV_STATE_MASS_IN_BUCKET_IDX])
        mass_end = float(env_state[end - 1, ENV_STATE_MASS_IN_BUCKET_IDX])
        hard_collision_delta = int(
            round(
                float(
                    env_state[end - 1, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]
                    - env_state[start, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]
                )
            )
        )
        qc.update(
            {
                f"{prefix}_start_bucket_mass_kg": float(mass_start),
                f"{prefix}_end_bucket_mass_kg": float(mass_end),
                f"{prefix}_bucket_mass_loss_kg": float(max(0.0, mass_start - mass_end)),
                f"{prefix}_hard_collision_delta_count": int(
                    max(0, hard_collision_delta)
                ),
                f"{prefix}_start_horizontal_distance_m": float(
                    env_state[start, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
                ),
                f"{prefix}_end_horizontal_distance_m": float(
                    env_state[end - 1, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
                ),
                f"{prefix}_start_height_above_rim_m": float(
                    env_state[start, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
                ),
                f"{prefix}_end_height_above_rim_m": float(
                    env_state[end - 1, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
                ),
                f"{prefix}_end_clearance_ok": int(
                    env_state[end - 1, ENV_STATE_DUMP_CLEARANCE_OK_IDX] > 0.5
                ),
            }
        )
    return qc


def _find_dump_intent_start(
    *,
    episode: dict[str, Any],
    work_stage_id: np.ndarray,
    official_dump_start: int | None,
) -> DumpIntentSearchResult:
    if official_dump_start is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={},
            reject_reason="missing_official_dump_start",
        )
    approach_id = WORK_STAGE_NAME_TO_ID["approach_dump"]
    approach_indices = np.flatnonzero(work_stage_id == approach_id)
    if len(approach_indices) <= 0:
        return DumpIntentSearchResult(
            start_step=None,
            qc={},
            reject_reason="missing_approach_dump_stage",
        )
    search_start = int(approach_indices[0])
    search_end = max(search_start, int(official_dump_start))
    if search_end <= search_start:
        return DumpIntentSearchResult(
            start_step=None,
            qc={
                "dump_intent_search_start_step": int(search_start),
                "dump_intent_search_end_step": int(search_end),
            },
            reject_reason="empty_pre_dump_approach_window",
        )

    env_state = _target_geometry_env_state(episode=episode)
    if env_state is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={
                "dump_intent_search_start_step": int(search_start),
                "dump_intent_search_end_step": int(search_end),
            },
            reject_reason="missing_target_geometry_for_dump_intent",
        )

    search_mask = _safe_dump_intent_mask(
        episode=episode,
        work_stage_id=work_stage_id,
        env_state=env_state,
    )
    rejected_candidates: list[tuple[int, list[str], dict[str, Any]]] = []
    for onset in _stable_true_indices(
        search_mask,
        start=search_start,
        end=search_end,
        min_stable_steps=DUMP_INTENT_MIN_STABLE_STEPS,
    ):
        qc = _dump_window_qc(
            episode=episode,
            start=int(onset),
            end=len(episode["actions"]),
            official_dump_start=int(official_dump_start),
        )
        reject_reasons = _dump_qc_reject_reasons(qc)
        if not reject_reasons:
            return DumpIntentSearchResult(start_step=int(onset), qc=qc)
        rejected_candidates.append((int(onset), reject_reasons, qc))

    if rejected_candidates:
        onset, reject_reasons, qc = rejected_candidates[0]
        qc = dict(qc)
        qc["dump_intent_rejected_candidate_step"] = int(onset)
        qc["dump_intent_rejected_candidate_count"] = int(len(rejected_candidates))
        qc["dump_intent_reject_reasons"] = ",".join(reject_reasons)
        return DumpIntentSearchResult(
            start_step=None,
            qc=qc,
            reject_reason=str(reject_reasons[0]),
        )

    return DumpIntentSearchResult(
        start_step=None,
        qc={
            "dump_intent_search_start_step": int(search_start),
            "dump_intent_search_end_step": int(search_end),
            "dump_intent_safe_candidate_count": 0,
        },
        reject_reason="missing_safe_dump_intent",
    )


def _find_dump_release_start_5p(
    *,
    episode: dict[str, Any],
    work_stage_id: np.ndarray,
    official_dump_start: int | None,
) -> DumpIntentSearchResult:
    """Find the 5p release boundary from the first safe release intent.

    The mass-based dump_start label is too late for skill ownership: ACT can
    learn release actions before the material counter changes. 5p therefore
    assigns stable, safe pre-release curl-out to dump_release, while keeping
    earlier mixed swing/curl approach motion in approach_dump.
    """
    release_intent = _find_dump_intent_start(
        episode=episode,
        work_stage_id=work_stage_id,
        official_dump_start=official_dump_start,
    )
    if release_intent.start_step is None:
        return release_intent
    qc = dict(release_intent.qc)
    qc["dump_release_uses_safe_intent_start"] = True
    qc["dump_release_uses_official_dump_start"] = bool(
        official_dump_start is not None
        and int(release_intent.start_step) == int(official_dump_start)
    )
    return DumpIntentSearchResult(
        start_step=int(release_intent.start_step),
        qc=qc,
        reject_reason=release_intent.reject_reason,
    )


def _safe_dump_intent_mask(
    *,
    episode: dict[str, Any],
    work_stage_id: np.ndarray,
    env_state: np.ndarray,
) -> np.ndarray:
    qpos = np.asarray(episode["qpos"], dtype=np.float32)
    actions = np.asarray(episode["actions"], dtype=np.float32)
    if qpos.ndim != 2 or actions.ndim != 2:
        raise ValueError("qpos/actions must be rank-2 arrays.")
    if qpos.shape[1] <= BUCKET_QPOS_INDEX or actions.shape[1] <= BUCKET_ACTION_INDEX:
        return np.zeros(len(actions), dtype=bool)
    approach_id = WORK_STAGE_NAME_TO_ID["approach_dump"]
    return (
        (work_stage_id == approach_id)
        & (qpos[:, BUCKET_QPOS_INDEX] >= DUMP_INTENT_BUCKET_QPOS_MIN)
        & (actions[:, BUCKET_ACTION_INDEX] <= DUMP_INTENT_BUCKET_ACTION_MAX)
        & (env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] >= DUMP_INTENT_MIN_BUCKET_MASS_KG)
        & (
            env_state[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
            >= DUMP_INTENT_MIN_HEIGHT_ABOVE_RIM_M
        )
        & (env_state[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX] > 0.5)
    )


def _stable_true_indices(
    mask: np.ndarray,
    *,
    start: int,
    end: int,
    min_stable_steps: int,
) -> Iterable[int]:
    mask_arr = np.asarray(mask, dtype=bool)
    start = max(0, int(start))
    end = min(int(end), len(mask_arr))
    min_stable_steps = max(1, int(min_stable_steps))
    for index in range(start, end):
        stable_end = min(index + min_stable_steps, end)
        if stable_end - index < min_stable_steps:
            return
        if bool(np.all(mask_arr[index:stable_end])):
            yield int(index)


def _target_geometry_env_state(*, episode: dict[str, Any]) -> np.ndarray | None:
    env_state = episode.get("env_state")
    if env_state is None:
        return None
    arr = np.asarray(env_state, dtype=np.float32)
    if arr.ndim != 2:
        return None
    required_indices = (
        ENV_STATE_MASS_IN_BUCKET_IDX,
        ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
        ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    )
    if any(index >= arr.shape[1] for index in required_indices):
        return None
    if not np.all(np.isfinite(arr[:, list(required_indices)])):
        return None
    return arr


def _dump_window_qc(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
    official_dump_start: int,
) -> dict[str, Any]:
    env_state = _target_geometry_env_state(episode=episode)
    if env_state is None:
        return {"dump_qc_missing_target_geometry": True}
    start = max(0, int(start))
    end = min(int(end), len(env_state))
    first_end = min(end, start + DUMP_QC_FIRST_STEPS)
    window = env_state[start:end]
    first_window = env_state[start:first_end]
    heights = window[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
    first_heights = first_window[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
    clearance = window[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX]
    first_clearance = first_window[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX]
    horizontal = window[:, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
    over_footprint = window[:, ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX]
    collisions = window[:, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]
    near_collision_mask = (heights < 0.0) & (
        (over_footprint > 0.5)
        | (horizontal <= DUMP_QC_NEAR_COLLISION_HORIZONTAL_M)
        | (clearance <= 0.5)
    )
    clearance_loss_indices = np.flatnonzero(first_clearance <= 0.5)
    near_collision_indices = np.flatnonzero(near_collision_mask)
    hard_collision_delta = 0
    if len(collisions) > 0:
        hard_collision_delta = int(round(float(np.max(collisions) - collisions[0])))
    return {
        "dump_qc_first_steps": int(DUMP_QC_FIRST_STEPS),
        "dump_qc_intent_start_step": int(start),
        "dump_qc_official_dump_start_step": int(official_dump_start),
        "dump_intent_steps_before_official": int(official_dump_start - start),
        "dump_window_len": int(end - start),
        "dump_start_height_above_rim_m": float(
            env_state[start, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
        ),
        "dump_start_horizontal_distance_m": float(
            env_state[start, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
        ),
        "dump_start_clearance_ok": int(
            env_state[start, ENV_STATE_DUMP_CLEARANCE_OK_IDX] > 0.5
        ),
        "dump_first20_min_height_above_rim_m": float(np.min(first_heights)),
        "dump_first20_clearance_loss_step": int(
            -1 if len(clearance_loss_indices) == 0 else clearance_loss_indices[0]
        ),
        "dump_min_height_above_rim_m": float(np.min(heights)),
        "dump_clearance_loss_step": int(
            -1
            if not np.any(clearance <= 0.5)
            else int(np.flatnonzero(clearance <= 0.5)[0])
        ),
        "dump_hard_collision_delta_count": int(max(0, hard_collision_delta)),
        "dump_near_collision_count": int(np.count_nonzero(near_collision_mask)),
        "dump_near_collision_first_step": int(
            -1 if len(near_collision_indices) == 0 else near_collision_indices[0]
        ),
    }


def _dump_qc_reject_reasons(qc: dict[str, Any]) -> list[str]:
    if bool(qc.get("dump_qc_missing_target_geometry", False)):
        return ["missing_target_geometry_for_dump_qc"]
    reasons: list[str] = []
    if (
        float(qc.get("dump_first20_min_height_above_rim_m", 0.0))
        < DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M
    ):
        reasons.append("dump_first20_height_below_rim")
    if int(qc.get("dump_first20_clearance_loss_step", -1)) >= 0:
        reasons.append("dump_first20_clearance_lost")
    if int(qc.get("dump_hard_collision_delta_count", 0)) > 0:
        reasons.append("dump_hard_collision")
    return reasons


def _first_dump_start(
    *,
    work_stage_id: np.ndarray,
    dump_start_mask: np.ndarray,
) -> int | None:
    if dump_start_mask.size:
        dump_indices = np.flatnonzero(np.asarray(dump_start_mask, dtype=bool))
        if len(dump_indices) > 0:
            return int(dump_indices[0])
    dump_stage_indices = np.flatnonzero(work_stage_id == WORK_STAGE_NAME_TO_ID["dump"])
    if len(dump_stage_indices) > 0:
        return int(dump_stage_indices[0])
    return None


def _first_dump_end(
    *,
    dump_end_mask: np.ndarray,
    start: int,
    n_steps: int,
) -> int | None:
    if dump_end_mask.size:
        dump_indices = np.flatnonzero(np.asarray(dump_end_mask, dtype=bool))
        dump_indices = dump_indices[dump_indices >= int(start)]
        if len(dump_indices) > 0:
            return int(dump_indices[0])
    return int(n_steps - 1) if n_steps > 0 else None


def _first_index_where(values: np.ndarray, accepted: set[int]) -> int | None:
    accepted_arr = np.asarray(sorted(accepted), dtype=np.int32)
    mask = np.isin(np.asarray(values, dtype=np.int32), accepted_arr)
    indices = np.flatnonzero(mask)
    return None if len(indices) == 0 else int(indices[0])


def _require_v2_step(*, episode: dict[str, Any], source_path: Path) -> dict[str, Any]:
    v2 = episode.get("v2")
    if not v2 or not dict(v2.get("step", {})):
        raise KeyError(
            f"Episode {source_path.name} is missing /v2/step labels. "
            "Run the V2.1 relabel/build pipeline first."
        )
    step = dict(v2.get("step", {}))
    if "work_stage_id" not in step:
        raise KeyError(f"Episode {source_path.name} is missing /v2/step/work_stage_id.")
    return step


def _source_episode_id(*, episode: dict[str, Any], source_path: Path) -> int:
    metadata = dict(episode.get("metadata", {}))
    value = metadata.get("source_episode_id")
    if value is not None:
        text = value.decode() if isinstance(value, bytes) else str(value)
        if text.startswith("episode_"):
            return int(text.split("_", 1)[1])
        return int(text)
    return episode_id_from_path(source_path)


def _source_cycle_id(*, episode: dict[str, Any]) -> int:
    metadata = dict(episode.get("metadata", {}))
    value = metadata.get("source_cycle_id", 0)
    return int(value)


def _source_start_step_offset(*, episode: dict[str, Any]) -> int:
    metadata = dict(episode.get("metadata", {}))
    return int(metadata.get("source_start_step", 0))


def _slice_optional_array(
    value: Any,
    crop: slice,
    *,
    dtype: np.dtype | None = np.float32,
) -> np.ndarray | None:
    if value is None:
        return None
    arr = np.asarray(value[crop])
    if dtype is not None:
        arr = arr.astype(dtype)
    return arr


def _slice_optional_list(value: list[str] | None, crop: slice) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value[crop]]


def _build_summary(
    *,
    workskill_dir: Path,
    raw_dirs: list[Path],
    output_root: Path,
    counts: Counter[str],
    window_lengths: dict[str, list[int]],
    rejects: list[PrimitiveRejectRecord],
    return_max_transition_len: int | None,
    return_clean_profile: str | None,
    carry_qc_records: list[dict[str, Any]],
    dump_qc_records: list[dict[str, Any]],
    primitive_version: str = PRIMITIVE_VERSION,
    primitive_names: tuple[str, ...] = PRIMITIVE_NAMES,
    approach_qc_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reject_counts = Counter(
        f"{record.primitive_name}:{record.reason}" for record in rejects
    )
    primitive_summary = {}
    for primitive_name in primitive_names:
        lengths = [int(value) for value in window_lengths.get(primitive_name, [])]
        primitive_summary[primitive_name] = {
            "episode_count": int(counts[primitive_name]),
            "min_len": None if not lengths else int(min(lengths)),
            "median_len": None if not lengths else float(np.median(lengths)),
            "max_len": None if not lengths else int(max(lengths)),
        }
    return {
        "primitive_version": str(primitive_version),
        "workskill_dir": str(workskill_dir.resolve()),
        "raw_dirs": [str(path.resolve()) for path in raw_dirs],
        "output_root": str(output_root.resolve()),
        "primitive_names": list(primitive_names),
        "primitives": primitive_summary,
        "dump_intent_config": {
            "bucket_qpos_min": float(DUMP_INTENT_BUCKET_QPOS_MIN),
            "bucket_action_max": float(DUMP_INTENT_BUCKET_ACTION_MAX),
            "min_stable_steps": int(DUMP_INTENT_MIN_STABLE_STEPS),
            "min_bucket_mass_kg": float(DUMP_INTENT_MIN_BUCKET_MASS_KG),
            "min_height_above_rim_m": float(DUMP_INTENT_MIN_HEIGHT_ABOVE_RIM_M),
            "official_dump_start_fallback": False,
        },
        "carry_tail_config": {
            "pre_dump_trim_steps": int(CARRY_PRE_DUMP_TRIM_STEPS),
            "action_horizon_steps": int(CARRY_ACTION_HORIZON_STEPS),
            "extra_buffer_steps": int(CARRY_PRE_DUMP_TRIM_STEPS - CARRY_ACTION_HORIZON_STEPS),
            "curl_out_active_qpos_min": float(CARRY_CURL_OUT_ACTIVE_QPOS_MIN),
            "curl_out_bucket_qpos_min": float(CARRY_CURL_OUT_BUCKET_QPOS_MIN),
            "curl_out_bucket_action_max": float(CARRY_CURL_OUT_BUCKET_ACTION_MAX),
            "curl_out_continue_action_max": float(CARRY_CURL_OUT_CONTINUE_ACTION_MAX),
            "curl_out_min_stable_steps": int(CARRY_CURL_OUT_MIN_STABLE_STEPS),
            "curl_out_guard_steps": int(CARRY_CURL_OUT_GUARD_STEPS),
            "min_window_len": int(CARRY_MIN_WINDOW_LEN),
        },
        "carry_qc": _build_carry_qc_summary(carry_qc_records),
        "approach_dump_qc": _build_approach_dump_qc_summary(
            list(approach_qc_records or [])
        ),
        "dump_qc": _build_dump_qc_summary(dump_qc_records),
        "return_max_transition_len": return_max_transition_len,
        "return_clean_profile": return_clean_profile,
        "reject_counts": dict(sorted(reject_counts.items())),
        "rejects": [
            {
                "primitive_name": record.primitive_name,
                "reason": record.reason,
                "source_dataset_dir": record.source_dataset_dir,
                "source_episode_id": int(record.source_episode_id),
                "source_cycle_id": int(record.source_cycle_id),
                "start_step": int(record.start_step),
                "end_step_exclusive": int(record.end_step_exclusive),
                "details": _json_safe_dict(record.details or {}),
            }
            for record in rejects
        ],
    }


def _build_carry_qc_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted_window_count": int(len(records)),
        "trimmed_window_len": _numeric_stats(records, "carry_window_len"),
        "removed_pre_dump_steps": _numeric_stats(records, "carry_removed_pre_dump_steps"),
        "stable_curl_out_onset_step": _numeric_stats(
            records,
            "carry_stable_curl_out_onset_step",
            ignore_negative=True,
        ),
        "tail_bucket_action_min": _numeric_stats(records, "carry_tail_bucket_action_min"),
        "tail_bucket_action_median": _numeric_stats(
            records,
            "carry_tail_bucket_action_median",
        ),
        "tail_bucket_qpos_max": _numeric_stats(records, "carry_tail_bucket_qpos_max"),
        "bucket_mass_loss_kg": _numeric_stats(records, "carry_bucket_mass_loss_kg"),
        "tail_stable_strong_curl_out_count": int(
            sum(bool(record.get("carry_tail_has_stable_strong_curl_out", False)) for record in records)
        ),
    }


def _build_approach_dump_qc_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted_window_count": int(len(records)),
        "window_len": _numeric_stats(records, "approach_dump_window_len"),
        "tail_horizon_steps": int(APPROACH_DUMP_ACTION_HORIZON_STEPS),
        "steps_before_release": _numeric_stats(
            records,
            "approach_dump_steps_before_release",
        ),
        "start_horizontal_distance_m": _numeric_stats(
            records,
            "approach_dump_start_horizontal_distance_m",
        ),
        "end_horizontal_distance_m": _numeric_stats(
            records,
            "approach_dump_end_horizontal_distance_m",
        ),
        "end_height_above_rim_m": _numeric_stats(
            records,
            "approach_dump_end_height_above_rim_m",
        ),
        "bucket_mass_loss_kg": _numeric_stats(
            records,
            "approach_dump_bucket_mass_loss_kg",
        ),
        "tail_stable_strong_curl_out_count": int(
            sum(
                bool(record.get("approach_dump_tail_has_stable_strong_curl_out", False))
                for record in records
            )
        ),
        "tail_stable_release_count": int(
            sum(
                bool(record.get("approach_dump_tail_has_stable_release", False))
                for record in records
            )
        ),
    }


def _build_dump_qc_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted_window_count": int(len(records)),
        "first_steps": int(DUMP_QC_FIRST_STEPS),
        "reject_thresholds": {
            "first20_min_height_above_rim_m": float(
                DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M
            ),
            "first20_clearance_must_stay_ok": True,
            "hard_collision_delta_count": 0,
        },
        "start_height_above_rim_m": _numeric_stats(
            records,
            "dump_start_height_above_rim_m",
        ),
        "start_horizontal_distance_m": _numeric_stats(
            records,
            "dump_start_horizontal_distance_m",
        ),
        "first20_min_height_above_rim_m": _numeric_stats(
            records,
            "dump_first20_min_height_above_rim_m",
        ),
        "full_min_height_above_rim_m": _numeric_stats(
            records,
            "dump_min_height_above_rim_m",
        ),
        "steps_before_official_dump_start": _numeric_stats(
            records,
            "dump_intent_steps_before_official",
        ),
        "first20_height_below_rim_count": int(
            sum(
                float(record.get("dump_first20_min_height_above_rim_m", 0.0))
                < DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M
                for record in records
            )
        ),
        "first20_clearance_loss_count": int(
            sum(int(record.get("dump_first20_clearance_loss_step", -1)) >= 0 for record in records)
        ),
        "hard_collision_window_count": int(
            sum(int(record.get("dump_hard_collision_delta_count", 0)) > 0 for record in records)
        ),
        "near_collision_window_count": int(
            sum(int(record.get("dump_near_collision_count", 0)) > 0 for record in records)
        ),
    }


def _numeric_stats(
    records: list[dict[str, Any]],
    key: str,
    *,
    ignore_negative: bool = False,
) -> dict[str, float | int | None]:
    values = [
        float(record[key])
        for record in records
        if key in record
        and np.isfinite(float(record[key]))
        and (not ignore_negative or float(record[key]) >= 0.0)
    ]
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": int(len(values)),
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
    }


def _json_safe_dict(values: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not np.isfinite(value):
            continue
        if isinstance(value, (bool, int, float, str)):
            safe[str(key)] = value
    return safe
