"""V2.2 primitive dataset builders.

The V2.2 splits keep the low-level ACT inputs non-privileged while using
existing V2.1 labels and target geometry for offline segmentation/QC only.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from testbed.data.hdf5_io import episode_id_from_path, list_episodes, read_episode, write_episode
from testbed.data.schema import (
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.transition_v2_1 import extract_transition_slices
from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID
from testbed.data.vds import (
    PRIMITIVE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    STORAGE_MODE_MANIFEST,
    STORAGE_MODE_VDS,
    write_lineage_json,
    write_vds_episode,
)


PRIMITIVE_RECORDING_MODE = "primitive_relabel"
PRIMITIVE_VERSION = "v2_2_4primitives"
PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass_4primitives"
PRIMITIVE_VERSION_5P = "v2_2_5primitives"
PRIMITIVE_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")
PRIMITIVE_BOUNDARY_PROFILE_DEFAULT = "v2_2_middle_handoff"
PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK = "v2_2_effect_release_fallback"
PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass"
PRIMITIVE_BOUNDARY_PROFILES = (
    PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)

DIG_WINDOW_NAME = "qualified_dig_start_to_before_carry"
CARRY_WINDOW_NAME = "carry_to_before_dump_ownership"
DUMP_WINDOW_NAME = "dump_approach_to_dump_end"
RETURN_WINDOW_NAME = "dump_end_to_next_qualified_dig_start"
SPATIAL_MASS_DIG_WINDOW_NAME = "material_cycle_dig_contact_depth_payload_gain"
SPATIAL_MASS_CARRY_WINDOW_NAME = "loaded_transport_to_pre_release"
SPATIAL_MASS_DUMP_WINDOW_NAME = "dump_area_committed_release_deposit"
SPATIAL_MASS_RETURN_WINDOW_NAME = "dump_end_to_next_dig_start_envelope"
FIVEP_CARRY_WINDOW_NAME = "carry_to_before_approach_dump"
APPROACH_DUMP_WINDOW_NAME = "approach_dump_to_before_dump_release"
DUMP_RELEASE_WINDOW_NAME = "dump_release_to_dump_end_hold"
POSE_REALIGN_METADATA_KEY = "replay_pose_realign_steps"
POSE_REALIGN_CYCLE_REJECT_REASON = "cycle_contains_pose_realign"
POSE_REALIGN_TRANSITION_REJECT_REASON = "return_window_contains_pose_realign"

BUCKET_QPOS_INDEX = 3
BUCKET_ACTION_INDEX = 3
CARRY_ACTION_HORIZON_STEPS = 100
CARRY_CURL_OUT_LOOKBACK_STEPS = 120
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
DUMP_INTENT_MIN_HEIGHT_ABOVE_RIM_M = 0.20
DUMP_INTENT_MAX_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_M = 0.45
DUMP_QC_FIRST_STEPS = 20
DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M = -0.08
DUMP_QC_NEAR_COLLISION_HORIZONTAL_M = 0.05
GOOD_DUMP_MIN_BUCKET_MASS_LOSS_KG = 80.0
GOOD_DUMP_MIN_DEPOSIT_DELTA_KG = 80.0
GOOD_DUMP_MIN_DEPOSITED_FRACTION_OF_BUCKET_LOSS = 0.50
GOOD_DUMP_MAX_HARD_COLLISION_DELTA = 0
DUMP_RELEASE_POST_HOLD_STEPS = 30
SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS = 120
SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M = 0.35
SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M = 0.30
SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS = 20
SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M = 0.08
SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M = 0.12
SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M = -0.40
SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M = 2.10
SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M = 0.30
SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M = 2.30
SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M = 0.20
SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M = 0.12
SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M = 0.45
SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS = 15
SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG = 15.0
SPATIAL_MASS_DUMP_END_PLATEAU_STEPS = DUMP_RELEASE_POST_HOLD_STEPS
SPATIAL_MASS_DUMP_END_MASS_RANGE_TOL_KG = 2.0
SPATIAL_MASS_DUMP_END_DEPOSIT_GAIN_TOL_KG = 2.0
SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS = 480
SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG = 0.35
SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION = 0.90
SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG = 3.0
SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG = 2.0
SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS = 8
SPATIAL_MASS_DIG_EXIT_HOLD_STEPS = 3
SPATIAL_MASS_DIG_EXIT_MIN_DISTANCE_M = 0.08
SPATIAL_MASS_DIG_EXIT_MAX_DEPTH_M = 0.02
SPATIAL_MASS_DIG_BOX_LONG_ABS_MAX = 1.05
SPATIAL_MASS_DIG_BOX_SHORT_MIN = -0.15
SPATIAL_MASS_DIG_BOX_SHORT_MAX = 1.15
RETURN_START_ENVELOPE_WINDOW_STEPS = 40
SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG = 5.0
SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC = 0.10
APPROACH_DUMP_ACTION_HORIZON_STEPS = 100
APPROACH_DUMP_MIN_WINDOW_LEN = 20
APPROACH_DUMP_MAX_BUCKET_MASS_LOSS_KG = 150.0
APPROACH_DUMP_MAX_HARD_COLLISION_DELTA = 0
DUMP_RELEASE_MIN_WINDOW_LEN = 20
PRIMITIVE_CYCLE_METADATA_KEYS = (
    "cycle_success",
    "dig_success",
    "carry_success",
    "dump_success",
    "return_required",
    "return_success",
    "stage_success",
    "stage_success_flags",
    "stage_failure_reason_code",
    "payload_gain_kg",
    "carry_loss_before_dump_kg",
    "dump_deposited_fraction",
    "residual_bucket_mass_after_dump_kg",
    "deposit_delta_kg",
    "peak_bucket_depth_m",
    "collision_count_delta",
    "selected_cell_id",
    "actual_accepted_start_cell_id",
    "actual_bite_cell_id",
    "actual_removal_cell_id",
    "cell_entry_geometry_available",
    "cell_entry_planner_ok",
    "cell_entry_target_cell_match",
    "cell_entry_audit_reason_code",
    "cell_entry_audit_risk_flags",
    "cycle_effective_deposit_delta_kg",
    "legacy_dump_end_deposit_delta_kg",
    "dump_window_deposit_delta_kg",
    "operator_entry_step",
    "operator_exit_step",
    "operator_entry_x_m",
    "operator_entry_y_m",
    "operator_entry_z_m",
    "operator_exit_x_m",
    "operator_exit_y_m",
    "operator_exit_z_m",
    "operator_cut_direction_x",
    "operator_cut_direction_y",
    "operator_cut_direction_z",
    "operator_cut_length_m",
    "operator_cut_depth_peak_m",
    "operator_cut_payload_gain_kg",
    "operator_cut_valid",
    "next_operator_entry_step",
    "next_operator_entry_x_m",
    "next_operator_entry_y_m",
    "next_operator_entry_z_m",
    "next_operator_exit_step",
    "next_operator_exit_x_m",
    "next_operator_exit_y_m",
    "next_operator_exit_z_m",
    "next_operator_cut_direction_x",
    "next_operator_cut_direction_y",
    "next_operator_cut_direction_z",
    "next_operator_cut_length_m",
    "next_operator_cut_depth_peak_m",
    "next_operator_cut_payload_gain_kg",
    "next_operator_cut_valid",
    "return_entry_delta_x_m",
    "return_entry_delta_y_m",
    "return_entry_delta_z_m",
    "return_entry_delta_norm_m",
    "return_target_source",
    "training_tier",
    "dominant_removed_depth_cell_id",
    "depth_outcome_source",
    "dig_outcome_payload_gain_kg",
    "dig_outcome_effective_deposit_delta_kg",
    "return_outcome_entry_delta_norm_m",
    "handoff_outcome_source",
)


def _normalise_boundary_profile(profile: str | None) -> str:
    if profile in (None, ""):
        return PRIMITIVE_BOUNDARY_PROFILE_DEFAULT
    value = str(profile).strip()
    if value not in PRIMITIVE_BOUNDARY_PROFILES:
        raise ValueError(
            f"Unsupported V2.2 primitive boundary profile {profile!r}. "
            f"Expected one of {', '.join(PRIMITIVE_BOUNDARY_PROFILES)}."
        )
    return value


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


@dataclass(frozen=True)
class DumpIntentSearchResult:
    start_step: int | None
    qc: dict[str, Any]
    reject_reason: str | None = None


def build_primitive_datasets(
    *,
    workskill_dir: str | Path | None = None,
    output_root: str | Path,
    raw_dirs: Iterable[str | Path] | None = None,
    require_return: bool = True,
    return_max_transition_len: int | None = None,
    return_clean_profile: str | None = None,
    boundary_profile: str = PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    storage_mode: str = STORAGE_MODE_COPY,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build V2.2 `dig/carry/dump/return` sibling datasets.

    In copy mode, `dig/carry/dump` keep the legacy input contract and are split
    from an existing V2.1 workskill dataset. In vds/manifest mode, the builder
    can split directly from Cell Entry enriched raw episodes by passing only
    `raw_dirs`, avoiding a copied workskill root. `return` still uses the full
    raw `dump_end -> next qualified_dig_start` transition semantics.
    """
    workskill_dir = None if workskill_dir is None else Path(workskill_dir)
    output_root = Path(output_root)
    raw_dirs_list = [Path(path) for path in (raw_dirs or [])]
    boundary_profile = _normalise_boundary_profile(boundary_profile)
    storage_mode = str(storage_mode).strip().lower()
    if storage_mode not in PRIMITIVE_STORAGE_MODES:
        raise ValueError(
            f"Unsupported storage_mode {storage_mode!r}. "
            f"Expected one of {', '.join(PRIMITIVE_STORAGE_MODES)}."
        )

    use_raw_direct_workskill = workskill_dir is None
    if use_raw_direct_workskill and not raw_dirs_list:
        raise ValueError("Either workskill_dir or raw_dirs must be provided.")
    episode_paths = [] if workskill_dir is None else list_episodes(workskill_dir)
    if workskill_dir is not None and not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {workskill_dir}")
    if require_return and not raw_dirs_list:
        raise ValueError("raw_dirs must be provided when require_return=True.")

    if output_root.exists() and any(output_root.rglob("episode_*.hdf5")):
        if not overwrite:
            raise FileExistsError(
                f"Output root {output_root} already contains episode files. "
                "Use --overwrite only when intentionally replacing a builder output."
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    primitive_dirs = {name: output_root / name for name in PRIMITIVE_NAMES}
    primitive_version_for_output = (
        PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS
        if boundary_profile == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
        else PRIMITIVE_VERSION
    )
    if storage_mode != STORAGE_MODE_MANIFEST:
        for primitive_dir in primitive_dirs.values():
            primitive_dir.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    rejects: list[PrimitiveRejectRecord] = []
    carry_qc_records: list[dict[str, Any]] = []
    dump_qc_records: list[dict[str, Any]] = []
    return_qc_records: list[dict[str, Any]] = []
    training_tier_counts: Counter[str] = Counter()
    window_lengths: dict[str, list[int]] = {name: [] for name in PRIMITIVE_NAMES}
    next_episode_id: dict[str, int] = {name: 0 for name in PRIMITIVE_NAMES}
    window_manifest: list[dict[str, Any]] = []

    def _consume_slice(
        *,
        source_episode: dict[str, Any],
        source_path: Path,
        source_dataset_dir: Path,
        primitive_slice: PrimitiveSlice,
        vds_base_step: int,
        cycle_id_offset: int = 0,
    ) -> None:
        primitive_name = primitive_slice.primitive_name
        output_episode_id = next_episode_id[primitive_name]
        target_path = primitive_dirs[primitive_name] / f"episode_{output_episode_id}.hdf5"
        manifest_entry = _primitive_window_manifest_entry(
            primitive_slice=primitive_slice,
            source_episode=source_episode,
            source_path=source_path,
            target_path=target_path,
            output_episode_id=output_episode_id,
        )
        window_manifest.append(manifest_entry)
        tier = str(manifest_entry.get("training_tier", "silver"))
        training_tier_counts[f"{primitive_name}:{tier}"] += 1
        if storage_mode == STORAGE_MODE_MANIFEST:
            next_episode_id[primitive_name] += 1
            counts[primitive_name] += 1
        elif storage_mode == STORAGE_MODE_VDS:
            write_primitive_episode_vds(
                target_path=target_path,
                source_hdf5_path=source_path,
                source_episode=source_episode,
                source_dataset_dir=source_dataset_dir,
                primitive_slice=primitive_slice,
                output_episode_id=output_episode_id,
                cycle_id_offset=cycle_id_offset,
                vds_base_step=vds_base_step,
                primitive_version=primitive_version_for_output,
            )
            next_episode_id[primitive_name] += 1
            counts[primitive_name] += 1
        else:
            write_primitive_episode(
                target_path=target_path,
                source_episode=source_episode,
                source_dataset_dir=source_dataset_dir,
                primitive_slice=primitive_slice,
                output_episode_id=output_episode_id,
                cycle_id_offset=cycle_id_offset,
                primitive_version=primitive_version_for_output,
            )
            next_episode_id[primitive_name] += 1
            counts[primitive_name] += 1
        window_lengths[primitive_name].append(int(primitive_slice.window_len))
        if primitive_name == "carry" and primitive_slice.carry_qc:
            carry_qc_records.append(dict(primitive_slice.carry_qc))
        if primitive_name == "dump" and primitive_slice.dump_qc:
            dump_qc_records.append(dict(primitive_slice.dump_qc))
        if primitive_name == "return" and primitive_slice.return_qc:
            return_qc_records.append(dict(primitive_slice.return_qc))

    if workskill_dir is not None:
        for source_path in episode_paths:
            episode = read_episode(
                source_path,
                load_images=(storage_mode == STORAGE_MODE_COPY),
            )
            primitive_slices, slice_rejects = extract_workskill_primitive_slices(
                episode=episode,
                source_path=source_path,
                source_dataset_dir=workskill_dir,
                boundary_profile=boundary_profile,
            )
            rejects.extend(slice_rejects)
            for primitive_slice in primitive_slices:
                _consume_slice(
                    source_episode=episode,
                    source_path=source_path,
                    source_dataset_dir=workskill_dir,
                    primitive_slice=primitive_slice,
                    vds_base_step=0,
                    cycle_id_offset=0,
                )
    elif (
        boundary_profile == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
        and storage_mode in {STORAGE_MODE_COPY, STORAGE_MODE_VDS, STORAGE_MODE_MANIFEST}
    ):
        for raw_dir in raw_dirs_list:
            for raw_source in list_episodes(raw_dir):
                raw_episode = read_episode(
                    raw_source,
                    load_images=(storage_mode == STORAGE_MODE_COPY),
                )
                primitive_slices, slice_rejects = (
                    extract_spatial_mass_primitive_slices_from_raw(
                        episode=raw_episode,
                        source_path=raw_source,
                        source_dataset_dir=raw_dir,
                        return_max_transition_len=return_max_transition_len,
                    )
                )
                rejects.extend(slice_rejects)
                for primitive_slice in primitive_slices:
                    cycle_id_offset = (
                        int(primitive_slice.source_prev_cycle_id)
                        if primitive_slice.primitive_name == "return"
                        and primitive_slice.source_prev_cycle_id is not None
                        else 0
                    )
                    _consume_slice(
                        source_episode=raw_episode,
                        source_path=raw_source,
                        source_dataset_dir=raw_dir,
                        primitive_slice=primitive_slice,
                        vds_base_step=0,
                        cycle_id_offset=cycle_id_offset,
                    )
    elif storage_mode in {STORAGE_MODE_COPY, STORAGE_MODE_VDS, STORAGE_MODE_MANIFEST}:
        for raw_dir in raw_dirs_list:
            for raw_source in list_episodes(raw_dir):
                raw_episode = read_episode(
                    raw_source,
                    load_images=(storage_mode == STORAGE_MODE_COPY),
                )
                for workskill_episode in _iter_cycle_workskill_episodes_from_raw(
                    episode=raw_episode,
                    source_path=raw_source,
                    source_dataset_dir=raw_dir,
                    rejects=rejects,
                ):
                    primitive_slices, slice_rejects = extract_workskill_primitive_slices(
                        episode=workskill_episode["episode"],
                        source_path=workskill_episode["source_path"],
                        source_dataset_dir=raw_dir,
                        boundary_profile=boundary_profile,
                    )
                    rejects.extend(slice_rejects)
                    for primitive_slice in primitive_slices:
                        _consume_slice(
                            source_episode=workskill_episode["episode"],
                            source_path=raw_source,
                            source_dataset_dir=raw_dir,
                            primitive_slice=primitive_slice,
                            vds_base_step=int(workskill_episode["source_start_step"]),
                            cycle_id_offset=0,
                        )

    if (
        raw_dirs_list
        and require_return
        and boundary_profile != PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    ):
        for raw_dir in raw_dirs_list:
            raw_episode_paths = list_episodes(raw_dir)
            if not raw_episode_paths:
                raise FileNotFoundError(f"No episode_*.hdf5 files found under {raw_dir}")
            for source_path in raw_episode_paths:
                episode = read_episode(
                    source_path,
                    load_images=(storage_mode == STORAGE_MODE_COPY),
                )
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
                    realign_reject = _transition_pose_realign_reject(
                        episode=episode,
                        source_path=source_path,
                        source_dataset_dir=raw_dir,
                        transition_slice=transition_slice,
                    )
                    if realign_reject is not None:
                        rejects.append(realign_reject)
                        continue
                    return_target_reject = _return_target_reject_reason(
                        episode=episode,
                        source_cycle_id=int(transition_slice.prev_cycle_id),
                    )
                    if return_target_reject is not None:
                        rejects.append(
                            PrimitiveRejectRecord(
                                primitive_name="return",
                                reason=return_target_reject,
                                source_dataset_dir=str(raw_dir.resolve()),
                                source_episode_id=int(transition_slice.source_episode_id),
                                source_cycle_id=int(transition_slice.prev_cycle_id),
                                start_step=int(transition_slice.dump_end_step),
                                end_step_exclusive=int(transition_slice.next_start_step) + 1,
                            )
                        )
                        continue
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
                        boundary_profile=boundary_profile,
                    )
                    _consume_slice(
                        source_episode=episode,
                        source_path=source_path,
                        source_dataset_dir=raw_dir,
                        primitive_slice=primitive_slice,
                        vds_base_step=0,
                        cycle_id_offset=int(transition_slice.prev_cycle_id),
                    )

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

    with open(output_root / "window_manifest.json", "w") as f:
        json.dump(_jsonable(window_manifest), f, indent=2, sort_keys=True)
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
        return_qc_records=return_qc_records,
        training_tier_counts=training_tier_counts,
        primitive_version=primitive_version_for_output,
        boundary_profile=boundary_profile,
        storage_mode=storage_mode,
        window_manifest_path=output_root / "window_manifest.json",
    )
    with open(output_root / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    source_roots = []
    if workskill_dir is not None:
        source_roots.append(workskill_dir)
    source_roots.extend(raw_dirs_list)
    write_lineage_json(
        output_root,
        builder="tb-build-primitives-v2_2",
        storage_mode=storage_mode,
        source_roots=source_roots,
        input_dataset_ids=[Path(path).name for path in source_roots],
        schema_versions={
            "hdf5": "1.1",
            "primitive": primitive_version_for_output,
        },
        extra={
            "primitive_names": list(PRIMITIVE_NAMES),
            "boundary_profile": boundary_profile,
            "source_mode": (
                "cell_entry_enriched_raw_direct"
                if use_raw_direct_workskill
                else "legacy_workskill_plus_raw_return"
            ),
        },
    )
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
                    realign_reject = _transition_pose_realign_reject(
                        episode=episode,
                        source_path=source_path,
                        source_dataset_dir=raw_dir,
                        transition_slice=transition_slice,
                    )
                    if realign_reject is not None:
                        rejects.append(realign_reject)
                        continue
                    return_target_reject = _return_target_reject_reason(
                        episode=episode,
                        source_cycle_id=int(transition_slice.prev_cycle_id),
                    )
                    if return_target_reject is not None:
                        rejects.append(
                            PrimitiveRejectRecord(
                                primitive_name="return",
                                reason=return_target_reject,
                                source_dataset_dir=str(raw_dir.resolve()),
                                source_episode_id=int(transition_slice.source_episode_id),
                                source_cycle_id=int(transition_slice.prev_cycle_id),
                                start_step=int(transition_slice.dump_end_step),
                                end_step_exclusive=int(transition_slice.next_start_step) + 1,
                            )
                        )
                        continue
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
    boundary_profile: str = PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
) -> tuple[list[PrimitiveSlice], list[PrimitiveRejectRecord]]:
    """Split one cropped V2.1 workskill episode into `dig/carry/dump`."""
    source_path = Path(source_path)
    source_dataset_dir = Path(source_dataset_dir)
    boundary_profile = _normalise_boundary_profile(boundary_profile)
    allow_effect_release_fallback = (
        boundary_profile == PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK
    )
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
    approach_start = _first_index_where(
        work_stage_id,
        {WORK_STAGE_NAME_TO_ID["approach_dump"]},
    )
    official_dump_start = _first_dump_start(
        work_stage_id=work_stage_id,
        dump_start_mask=dump_start_mask,
    )
    pre_approach_curl_out_onset = None
    if carry_start is not None and approach_start is not None:
        pre_approach_curl_out_onset = _find_stable_carry_curl_out_onset(
            episode=episode,
            start=int(carry_start),
            end=int(approach_start),
        )
    elif (
        allow_effect_release_fallback
        and carry_start is not None
        and official_dump_start is not None
    ):
        pre_approach_curl_out_onset = _find_stable_release_onset(
            episode=episode,
            start=int(carry_start),
            end=int(official_dump_start),
        )
    if approach_start is not None:
        dump_ownership_start = int(approach_start)
        dump_ownership_boundary_source = "approach_dump_stage"
    elif allow_effect_release_fallback and pre_approach_curl_out_onset is not None:
        dump_ownership_start = int(pre_approach_curl_out_onset)
        dump_ownership_boundary_source = "effect_release_onset_no_approach_stage"
    else:
        dump_ownership_start = None
        dump_ownership_boundary_source = None
    dump_intent = _find_dump_intent_start(
        episode=episode,
        work_stage_id=work_stage_id,
        official_dump_start=official_dump_start,
    )
    dump_intent_start = dump_intent.start_step
    quality_ownership_start = (
        pre_approach_curl_out_onset
        if pre_approach_curl_out_onset is not None
        else dump_ownership_start
        if dump_ownership_start is not None
        else official_dump_start
    )
    quality_release_marker = (
        pre_approach_curl_out_onset
        if pre_approach_curl_out_onset is not None
        else dump_intent_start
        if dump_intent_start is not None
        else official_dump_start
    )
    good_dump_acceptance = _find_good_dump_acceptance(
        episode=episode,
        start=quality_ownership_start,
        release_marker=quality_release_marker,
        official_dump_start=official_dump_start,
    )
    use_quality_acceptance = bool(
        good_dump_acceptance.start_step is not None
        and (
            dump_intent_start is None
            or pre_approach_curl_out_onset is not None
            or dump_ownership_start is None
        )
    )
    effective_dump_intent_start = (
        int(good_dump_acceptance.start_step)
        if use_quality_acceptance
        else dump_intent_start
    )
    effective_dump_ownership_start = dump_ownership_start
    effective_dump_ownership_boundary_source = dump_ownership_boundary_source
    if use_quality_acceptance:
        if pre_approach_curl_out_onset is not None:
            effective_dump_ownership_start = int(pre_approach_curl_out_onset)
            effective_dump_ownership_boundary_source = (
                "pre_approach_stable_curl_out_good_dump"
            )
        elif dump_ownership_start is not None:
            effective_dump_ownership_start = int(dump_ownership_start)
            effective_dump_ownership_boundary_source = (
                "approach_dump_stage_good_dump_quality"
            )
        elif quality_ownership_start is not None:
            effective_dump_ownership_start = int(quality_ownership_start)
            effective_dump_ownership_boundary_source = "good_dump_release_marker"
    pre_approach_release_details = {
        "pre_approach_stable_curl_out_onset_step": int(
            -1 if pre_approach_curl_out_onset is None else pre_approach_curl_out_onset
        ),
        "approach_dump_stage_step": int(-1 if approach_start is None else approach_start),
        "boundary_rule": str(boundary_profile),
        "good_dump_quality_acceptance": bool(use_quality_acceptance),
    }
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
                if effective_dump_intent_start is None
                else int(source_start_offset + effective_dump_intent_start),
                official_dump_start_step=None
                if official_dump_start is None
                else int(source_start_offset + official_dump_start),
                source_dataset_dir=str(source_dataset_dir.resolve()),
                carry_qc=carry_qc if primitive_name == "carry" else None,
                dump_qc=dump_qc if primitive_name == "dump" else None,
                boundary_profile=boundary_profile,
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

    if effective_dump_ownership_start is None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="carry",
                reason="missing_dump_ownership_boundary",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + (carry_start or 0)),
                end_step_exclusive=int(source_start_offset + n_steps),
            )
        )
    elif effective_dump_intent_start is None:
        reason = (
            dump_intent.reject_reason
            or good_dump_acceptance.reject_reason
            or "missing_good_dump_or_safe_intent"
        )
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="carry",
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + (carry_start or 0)),
                end_step_exclusive=int(source_start_offset + n_steps),
                details=dump_intent.qc or good_dump_acceptance.qc,
            )
        )
    elif pre_approach_curl_out_onset is not None and not use_quality_acceptance:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="carry",
                reason="carry_release_before_approach_dump_stage",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + (carry_start or 0)),
                end_step_exclusive=int(source_start_offset + dump_ownership_start),
                details=pre_approach_release_details,
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
                end_step_exclusive=int(source_start_offset + effective_dump_intent_start),
            )
        )
    else:
        carry_qc = _window_tail_qc(
            episode=episode,
            prefix="carry",
            start=int(carry_start),
            end=int(effective_dump_ownership_start),
            release_start=int(effective_dump_intent_start),
        )
        carry_qc.update(
            {
                "carry_dump_ownership_start_step": int(effective_dump_ownership_start),
                "carry_dump_ownership_boundary_source": str(
                    effective_dump_ownership_boundary_source
                ),
                "carry_dump_ownership_approach_stage_step": (
                    -1 if approach_start is None else int(approach_start)
                ),
                "carry_dump_ownership_stable_curl_out_onset_step": (
                    -1
                    if pre_approach_curl_out_onset is None
                    else int(pre_approach_curl_out_onset)
                ),
                "carry_dump_approach_steps_before_intent": int(
                    int(effective_dump_intent_start) - int(effective_dump_ownership_start)
                ),
                "carry_dump_ownership_requires_dump_area_geometry": True,
                "carry_dump_acceptance_mode": (
                    "good_dump_quality" if use_quality_acceptance else "safe_intent"
                ),
            }
        )
        if int(effective_dump_ownership_start) - int(carry_start) < CARRY_MIN_WINDOW_LEN:
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name="carry",
                    reason="carry_too_short_before_dump_ownership",
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + carry_start),
                    end_step_exclusive=int(source_start_offset + effective_dump_ownership_start),
                    details=carry_qc,
                )
            )
        elif bool(carry_qc.get("carry_tail_has_stable_release", False)):
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name="carry",
                    reason="carry_tail_has_release_before_dump_ownership",
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + carry_start),
                    end_step_exclusive=int(source_start_offset + effective_dump_ownership_start),
                    details=carry_qc,
                )
            )
        elif (
            float(carry_qc.get("carry_bucket_mass_loss_kg", 0.0))
            > CARRY_MAX_BUCKET_MASS_LOSS_KG
        ):
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name="carry",
                    reason="carry_mass_loss_before_dump_ownership",
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + carry_start),
                    end_step_exclusive=int(source_start_offset + effective_dump_ownership_start),
                    details=carry_qc,
                )
            )
        elif (
            int(carry_qc.get("carry_hard_collision_delta_count", 0))
            > CARRY_MAX_HARD_COLLISION_DELTA
        ):
            rejects.append(
                PrimitiveRejectRecord(
                    primitive_name="carry",
                    reason="carry_hard_collision_before_dump_ownership",
                    source_dataset_dir=str(source_dataset_dir.resolve()),
                    source_episode_id=int(source_episode_id),
                    source_cycle_id=int(source_cycle_id),
                    start_step=int(source_start_offset + carry_start),
                    end_step_exclusive=int(source_start_offset + effective_dump_ownership_start),
                    details=carry_qc,
                )
            )
        else:
            _append_or_reject(
                primitive_name="carry",
                window_name=CARRY_WINDOW_NAME,
                start=int(carry_start),
                end=int(effective_dump_ownership_start),
                reason_if_invalid="carry_too_short_before_dump_ownership",
                carry_qc=carry_qc,
            )

    if effective_dump_ownership_start is None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="dump",
                reason="missing_dump_ownership_boundary",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset),
                end_step_exclusive=int(source_start_offset + n_steps),
            )
        )
    elif effective_dump_intent_start is None:
        reason = (
            dump_intent.reject_reason
            or good_dump_acceptance.reject_reason
            or "missing_good_dump_or_safe_intent"
        )
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="dump",
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset),
                end_step_exclusive=int(source_start_offset + n_steps),
                details=dump_intent.qc or good_dump_acceptance.qc,
            )
        )
    elif pre_approach_curl_out_onset is not None and not use_quality_acceptance:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="dump",
                reason="release_before_approach_dump_stage",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(source_start_offset + pre_approach_curl_out_onset),
                end_step_exclusive=int(source_start_offset + n_steps),
                details=pre_approach_release_details,
            )
        )
    else:
        dump_qc = dict(
            good_dump_acceptance.qc if use_quality_acceptance else dump_intent.qc
        )
        dump_qc.update(
            {
                "dump_ownership_start_step": int(effective_dump_ownership_start),
                "dump_ownership_window_len": int(
                    n_steps - int(effective_dump_ownership_start)
                ),
                "dump_ownership_boundary_source": str(
                    effective_dump_ownership_boundary_source
                ),
                "dump_ownership_approach_stage_step": (
                    -1 if approach_start is None else int(approach_start)
                ),
                "dump_ownership_stable_curl_out_onset_step": (
                    -1
                    if pre_approach_curl_out_onset is None
                    else int(pre_approach_curl_out_onset)
                ),
                "dump_approach_steps_before_intent": int(
                    int(effective_dump_intent_start) - int(effective_dump_ownership_start)
                ),
                "dump_ownership_requires_dump_area_geometry": True,
                "dump_acceptance_mode": (
                    "good_dump_quality" if use_quality_acceptance else "safe_intent"
                ),
            }
        )
        _append_or_reject(
            primitive_name="dump",
            window_name=DUMP_WINDOW_NAME,
            start=int(effective_dump_ownership_start),
            end=n_steps,
            dump_qc=dump_qc,
        )

    return slices, rejects


def extract_spatial_mass_primitive_slices_from_raw(
    *,
    episode: dict[str, Any],
    source_path: str | Path,
    source_dataset_dir: str | Path,
    return_max_transition_len: int | None = None,
) -> tuple[list[PrimitiveSlice], list[PrimitiveRejectRecord]]:
    """Split a full V2.4/V2.4.5 raw episode using material-cycle ownership."""
    source_path = Path(source_path)
    source_dataset_dir = Path(source_dataset_dir)
    source_episode_id = _source_episode_id(episode=episode, source_path=source_path)
    windows = _spatial_mass_material_windows(
        episode=episode,
        windows=_raw_cycle_windows(episode=episode),
    )
    slices: list[PrimitiveSlice] = []
    rejects: list[PrimitiveRejectRecord] = []
    if not windows:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="cycle",
                reason="missing_material_cycle_windows",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=-1,
                start_step=0,
                end_step_exclusive=int(len(episode.get("actions", []))),
            )
        )
        return slices, rejects

    realign_steps = _metadata_pose_realign_steps(episode=episode)

    def _reject(
        *,
        primitive_name: str,
        reason: str,
        source_cycle_id: int,
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
                start_step=int(start),
                end_step_exclusive=int(end),
                details=details,
            )
        )

    def _append(
        *,
        primitive_name: str,
        window_name: str,
        source_cycle_id: int,
        start: int,
        end: int,
        source_prev_cycle_id: int | None = None,
        source_next_cycle_id: int | None = None,
        carry_qc: dict[str, Any] | None = None,
        dump_qc: dict[str, Any] | None = None,
        return_qc: dict[str, Any] | None = None,
        overlay: dict[str, np.ndarray] | None = None,
        reject_reason: str = "invalid_spatial_mass_window",
    ) -> None:
        if int(end) <= int(start):
            _reject(
                primitive_name=primitive_name,
                reason=reject_reason,
                source_cycle_id=source_cycle_id,
                start=start,
                end=end,
                details=carry_qc or dump_qc or return_qc,
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
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_prev_cycle_id=source_prev_cycle_id,
                source_next_cycle_id=source_next_cycle_id,
                carry_qc=carry_qc,
                dump_qc=dump_qc,
                return_qc=return_qc,
                v2_step_overlay=overlay,
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            )
        )

    for index, (cycle_id, start, work_end, _realign_end) in enumerate(windows):
        source_cycle_id = int(cycle_id)
        next_start = int(windows[index + 1][1]) if index + 1 < len(windows) else None
        work_realign = _window_pose_realign_steps(
            realign_steps=realign_steps,
            start_step=start,
            end_step_exclusive=work_end,
        )
        if work_realign:
            details = {
                "realign_steps_in_window": [int(step) for step in work_realign],
                "realign_all_steps": [int(step) for step in realign_steps],
                "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
                "policy": "discard_spatial_mass_work_windows_only",
            }
            for primitive_name in ("dig", "carry", "dump"):
                _reject(
                    primitive_name=primitive_name,
                    reason=POSE_REALIGN_CYCLE_REJECT_REASON,
                    source_cycle_id=source_cycle_id,
                    start=start,
                    end=work_end,
                    details=details,
                )
            continue

        release_onset, release_qc = _find_spatial_mass_release_onset(
            episode=episode,
            start=int(start),
            end=int(work_end),
        )
        if release_onset is None:
            for primitive_name in ("carry", "dump"):
                _reject(
                    primitive_name=primitive_name,
                    reason="missing_spatial_mass_release_onset",
                    source_cycle_id=source_cycle_id,
                    start=start,
                    end=work_end,
                    details=release_qc,
                )
            release_onset = int(work_end)

        dig_start, dig_qc = _find_spatial_mass_dig_start(
            episode=episode,
            start=int(start),
            end=int(work_end),
        )
        dump_start, dump_start_qc = _find_spatial_mass_dump_start(
            episode=episode,
            cycle_start=int(start),
            release_onset=int(release_onset),
        )
        dump_start = min(int(dump_start), int(work_end))
        dump_end, dump_end_qc = _find_spatial_mass_dump_end(
            episode=episode,
            search_end=int(work_end),
            release_onset=int(release_onset),
        )
        dump_end = max(int(dump_start) + 1, min(int(dump_end), int(work_end)))
        dig_end, dig_end_qc = _find_spatial_mass_dig_end(
            episode=episode,
            start=int(dig_start),
            end=int(dump_start),
        )
        dig_end = max(int(dig_start) + 1, min(int(dig_end), int(dump_start)))
        dig_qc.update(dig_end_qc)
        carry_start = int(dig_end)

        _append(
            primitive_name="dig",
            window_name=SPATIAL_MASS_DIG_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            start=int(dig_start),
            end=int(dig_end),
            dump_qc=dig_qc,
            reject_reason="invalid_spatial_mass_dig_window",
        )

        carry_qc = _spatial_mass_carry_qc(
            episode=episode,
            start=int(carry_start),
            end=int(dump_start),
            release_onset=int(release_onset),
        )
        if _spatial_mass_carry_contaminated(carry_qc):
            _reject(
                primitive_name="carry",
                reason="carry_deposit_contamination_before_dump",
                source_cycle_id=source_cycle_id,
                start=carry_start,
                end=dump_start,
                details=carry_qc,
            )
        else:
            _append(
                primitive_name="carry",
                window_name=SPATIAL_MASS_CARRY_WINDOW_NAME,
                source_cycle_id=source_cycle_id,
                start=int(carry_start),
                end=int(dump_start),
                carry_qc=carry_qc,
                reject_reason="invalid_spatial_mass_carry_window",
            )

        dump_qc = _spatial_mass_dump_qc(
            episode=episode,
            start=int(dump_start),
            end=int(dump_end),
            release_onset=int(release_onset),
            release_qc={**release_qc, **dump_start_qc, **dump_end_qc},
        )
        _append(
            primitive_name="dump",
            window_name=SPATIAL_MASS_DUMP_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            start=int(dump_start),
            end=int(dump_end),
            dump_qc=dump_qc,
            reject_reason="invalid_spatial_mass_dump_window",
        )

        if next_start is None:
            _reject(
                primitive_name="return",
                reason="terminal_return_reject",
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(dump_end),
                details={"policy": "return requires a next material dig start"},
            )
            continue
        return_end = min(int(len(episode["actions"])), int(next_start) + 1)
        return_realign = _window_pose_realign_steps(
            realign_steps=realign_steps,
            start_step=int(dump_end),
            end_step_exclusive=int(next_start),
        )
        if return_realign:
            _reject(
                primitive_name="return",
                reason=POSE_REALIGN_TRANSITION_REJECT_REASON,
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(next_start),
                details={
                    "realign_steps_in_window": [
                        int(step) for step in return_realign
                    ],
                    "realign_all_steps": [int(step) for step in realign_steps],
                    "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
                    "policy": "discard_return_transition_window",
                    "next_cycle_id": int(windows[index + 1][0]),
                },
            )
            continue
        if (
            return_max_transition_len is not None
            and int(return_end) - int(dump_end) > int(return_max_transition_len)
        ):
            _reject(
                primitive_name="return",
                reason="overlong_transition_len",
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(return_end),
                details={
                    "window_len": int(return_end) - int(dump_end),
                    "max_transition_len": int(return_max_transition_len),
                },
            )
            continue
        token, valid_mask, return_qc = _build_return_start_envelope_token(
            episode=episode,
            next_start_step=int(next_start),
        )
        return_len = int(return_end) - int(dump_end)
        return_qc.update(
            {
                "return_start_step": int(dump_end),
                "return_end_step_exclusive": int(return_end),
                "return_window_len": int(return_len),
                "return_next_material_cycle_id": int(windows[index + 1][0]),
                "return_start_envelope_schema": "return_start_envelope_tokens_v1",
            }
        )
        overlay = {
            DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1.rsplit("/", 1)[-1]: np.repeat(
                token.reshape(1, -1),
                return_len,
                axis=0,
            ).astype(np.float32),
            DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK.rsplit("/", 1)[-1]: np.repeat(
                valid_mask.reshape(1, -1),
                return_len,
                axis=0,
            ).astype(np.uint8),
        }
        _append(
            primitive_name="return",
            window_name=SPATIAL_MASS_RETURN_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            source_prev_cycle_id=source_cycle_id,
            source_next_cycle_id=int(windows[index + 1][0]),
            start=int(dump_end),
            end=int(return_end),
            return_qc=return_qc,
            overlay=overlay,
            reject_reason="invalid_spatial_mass_return_window",
        )

    return slices, rejects


def _find_spatial_mass_dig_start(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int, dict[str, Any]]:
    env_state = _env_state_or_none(episode)
    if env_state is None:
        return int(start), {
            "dig_start_step": int(start),
            "dig_start_source": "cycle_start_missing_env_state",
        }
    search_start = max(0, int(start))
    search_end = min(int(end), len(env_state))
    if search_end <= search_start:
        return int(start), {"dig_start_step": int(start), "dig_start_source": "empty_window"}
    geometry = _optional_env_col(
        env_state,
        ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
        default=1.0,
    )
    contact = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        default=0.0,
    )
    depth = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        default=float("nan"),
    )
    if not np.any(np.isfinite(depth)):
        depth = _optional_env_col(
            env_state,
            8,
            default=0.0,
        )
    mask = (
        (geometry > 0.5)
        & ((contact > 0.5) | (np.nan_to_num(depth, nan=0.0) > 0.005))
    )
    indices = np.flatnonzero(mask[search_start:search_end])
    if len(indices) <= 0:
        return int(start), {
            "dig_start_step": int(start),
            "dig_start_source": "cycle_start_no_contact_depth_match",
        }
    dig_start = int(search_start + indices[0])
    return dig_start, {
        "dig_start_step": int(dig_start),
        "dig_start_source": "first_dig_contact_or_depth",
        "dig_start_depth_m": float(np.nan_to_num(depth[dig_start], nan=0.0)),
        "dig_start_contact_mask": int(contact[dig_start] > 0.5),
    }


def _spatial_mass_material_windows(
    *,
    episode: dict[str, Any],
    windows: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    step = dict(dict(episode.get("v2") or {}).get("step", {}) or {})
    qds = np.asarray(step.get("qualified_dig_start_mask", []), dtype=np.uint8).reshape(-1)
    dump_end = np.asarray(step.get("dump_end_mask", []), dtype=np.uint8).reshape(-1)
    if qds.size <= 0 or not windows:
        return windows
    material_windows: list[tuple[int, int, int, int]] = []
    for cycle_id, start, work_end, realign_end in windows:
        qds_indices = np.flatnonzero(qds.astype(bool))
        qds_indices = qds_indices[(qds_indices >= int(start)) & (qds_indices < int(work_end))]
        if len(qds_indices) <= 1:
            material_windows.append((cycle_id, start, work_end, realign_end))
            continue
        if int(qds_indices[0]) != int(start):
            qds_indices = np.concatenate(
                [np.asarray([int(start)], dtype=np.int64), qds_indices]
            )
        for sub_index, sub_start_value in enumerate(qds_indices):
            sub_start = int(sub_start_value)
            next_start = (
                int(qds_indices[sub_index + 1])
                if sub_index + 1 < len(qds_indices)
                else None
            )
            sub_limit = int(work_end if next_start is None else next_start)
            sub_end = sub_limit
            if dump_end.size:
                dump_candidates = np.flatnonzero(dump_end.astype(bool))
                dump_candidates = dump_candidates[
                    (dump_candidates >= sub_start) & (dump_candidates < sub_limit)
                ]
                if len(dump_candidates) > 0:
                    sub_end = min(sub_limit, int(dump_candidates[0]) + 1)
            if sub_end <= sub_start:
                continue
            sub_realign_end = int(realign_end if next_start is None else next_start)
            material_windows.append((int(cycle_id), sub_start, sub_end, sub_realign_end))
    return sorted(material_windows, key=lambda item: item[1])


def _find_spatial_mass_dig_end(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int, dict[str, Any]]:
    start = int(start)
    end = int(end)
    qc: dict[str, Any] = {
        "dig_end_search_start_step": int(start),
        "dig_end_search_end_step": int(end),
        "dig_end_source": "fallback_search_end",
        "dig_mass_gain_eps_kg": float(SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG),
        "dig_peak_gain_fraction": float(SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION),
        "dig_near_peak_tol_kg": float(SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG),
        "dig_future_gain_tol_kg": float(SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG),
        "dig_mass_plateau_steps": int(SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS),
        "dig_exit_hold_steps": int(SPATIAL_MASS_DIG_EXIT_HOLD_STEPS),
    }
    if end <= start + 1:
        qc["dig_end_selected_step"] = int(end)
        qc["dig_end_source"] = "empty_search_window"
        return int(end), qc

    env_state = _env_state_or_none(episode)
    if env_state is None:
        selected = int(min(end, start + 120))
        qc["dig_end_selected_step"] = int(selected)
        qc["dig_end_source"] = "fallback_missing_env_state"
        return selected, qc

    n_steps = int(env_state.shape[0])
    search_start = max(0, min(start, n_steps - 1))
    search_end = max(search_start + 1, min(end, n_steps))
    mass = _optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    departed = _spatial_mass_dig_area_departed_mask(env_state)

    mass_delta = np.diff(mass, prepend=mass[0])
    growth_indices = np.flatnonzero(
        mass_delta[search_start + 1 : search_end] >= SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG
    )
    if len(growth_indices) > 0:
        last_growth = int(search_start + 1 + growth_indices[-1])
        first_growth = int(search_start + 1 + growth_indices[0])
    else:
        last_growth = int(search_start)
        first_growth = -1
    start_mass = float(mass[search_start])
    peak_mass = float(np.nanmax(mass[search_start:search_end]))
    total_gain = float(max(0.0, peak_mass - start_mass))
    near_peak_tolerance = max(
        float(SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG),
        total_gain * (1.0 - float(SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION)),
    )
    future_gain_tolerance = max(
        float(SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG),
        total_gain * 0.03,
    )
    qc.update(
        {
            "dig_first_mass_growth_step": int(first_growth),
            "dig_last_mass_growth_step": int(last_growth),
            "dig_start_bucket_mass_kg": start_mass,
            "dig_peak_bucket_mass_kg": peak_mass,
            "dig_total_mass_gain_kg": total_gain,
            "dig_near_peak_tolerance_kg": float(near_peak_tolerance),
            "dig_future_gain_tolerance_kg": float(future_gain_tolerance),
        }
    )

    hold = max(1, int(SPATIAL_MASS_DIG_EXIT_HOLD_STEPS))
    plateau_steps = max(0, int(SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS))
    candidate_start = search_start + 1
    latest_candidate = max(candidate_start, search_end - hold)
    for idx in range(candidate_start, latest_candidate + 1):
        exit_window = departed[idx : idx + hold]
        if len(exit_window) < hold or not bool(np.all(exit_window)):
            continue
        past_peak = float(np.nanmax(mass[search_start : idx + 1]))
        if total_gain > SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG and past_peak < (
            peak_mass - near_peak_tolerance
        ):
            continue
        plateau_end = min(search_end, idx + plateau_steps + 1)
        future_peak = float(np.nanmax(mass[idx:plateau_end])) if plateau_end > idx else float(mass[idx])
        future_gain = float(max(0.0, future_peak - float(mass[idx])))
        if future_gain > future_gain_tolerance:
            continue
        qc.update(
            {
                "dig_end_source": "mass_plateau_and_dig_area_departure",
                "dig_end_selected_step": int(idx),
                "dig_end_departure_hold_end_step": int(idx + hold),
                "dig_end_past_peak_bucket_mass_kg": float(past_peak),
                "dig_end_future_gain_kg": float(future_gain),
                "dig_end_mass_at_start_kg": start_mass,
                "dig_end_mass_at_selected_kg": float(mass[idx]),
            }
        )
        return int(idx), qc

    selected = int(search_end)
    qc.update(
        {
            "dig_end_source": "search_end_no_confirmed_departure",
            "dig_end_selected_step": int(selected),
            "dig_end_departed_fraction_after_growth": float(
                np.mean(departed[candidate_start:search_end])
                if search_end > candidate_start
                else 0.0
            ),
        }
    )
    return selected, qc


def _spatial_mass_dig_area_departed_mask(env_state: np.ndarray) -> np.ndarray:
    geometry = _optional_env_col(
        env_state,
        ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
        default=1.0,
    )
    contact = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        default=0.0,
    )
    depth = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        default=float("nan"),
    )
    if not np.any(np.isfinite(depth)):
        depth = _optional_env_col(env_state, 8, default=0.0)
    min_distance = _optional_env_col(
        env_state,
        ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
        default=float("nan"),
    )
    long_norm = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
        default=float("nan"),
    )
    short_norm = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
        default=float("nan"),
    )
    finite_norm = np.isfinite(long_norm) & np.isfinite(short_norm)
    inside_norm_box = (
        (geometry > 0.5)
        & finite_norm
        & (np.abs(long_norm) <= SPATIAL_MASS_DIG_BOX_LONG_ABS_MAX)
        & (short_norm >= SPATIAL_MASS_DIG_BOX_SHORT_MIN)
        & (short_norm <= SPATIAL_MASS_DIG_BOX_SHORT_MAX)
    )
    finite_distance = np.isfinite(min_distance)
    outside_by_distance = finite_distance & (
        min_distance > SPATIAL_MASS_DIG_EXIT_MIN_DISTANCE_M
    )
    outside_by_norm = finite_norm & (~inside_norm_box)
    outside_spatial = outside_by_norm | outside_by_distance
    no_contact_depth = (
        (contact <= 0.5)
        & (np.nan_to_num(depth, nan=0.0) <= SPATIAL_MASS_DIG_EXIT_MAX_DEPTH_M)
    )
    return np.asarray(outside_spatial & no_contact_depth, dtype=bool)


def _find_spatial_mass_release_onset(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int | None, dict[str, Any]]:
    start = max(0, int(start))
    end = min(int(end), int(len(episode.get("actions", []))))
    env_state = _env_state_or_none(episode)
    if env_state is not None and end > start + 1:
        mass = _optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
        deposit = np.zeros(len(env_state), dtype=np.float32)
        for col in (
            ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
            ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
            ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
        ):
            if col < env_state.shape[1]:
                deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
        outside = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            default=0.0,
        )
        over = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
            default=0.0,
        )
        for idx in range(start + 1, end):
            mass_drop = float(max(0.0, mass[idx - 1] - mass[idx]))
            deposit_gain = float(max(0.0, deposit[idx] - deposit[idx - 1]))
            near_dump_area = bool(outside[idx] <= 0.45 or over[idx] > 0.5)
            if near_dump_area and (mass_drop >= 0.5 or deposit_gain >= 0.5):
                return int(idx), {
                    "release_onset_step": int(idx),
                    "release_onset_source": "instant_mass_or_deposit_delta",
                    "release_instant_mass_drop_kg": mass_drop,
                    "release_instant_deposit_gain_kg": deposit_gain,
                    "release_dump_area_outside_distance_m": float(outside[idx]),
                }

    step = dict(dict(episode.get("v2") or {}).get("step", {}) or {})
    dump_start_mask = np.asarray(step.get("dump_start_mask", []), dtype=np.uint8)
    if dump_start_mask.size:
        candidates = np.flatnonzero(dump_start_mask.astype(bool))
        candidates = candidates[(candidates >= start) & (candidates < end)]
        if len(candidates) > 0:
            idx = int(candidates[0])
            return idx, {
                "release_onset_step": int(idx),
                "release_onset_source": "dump_start_mask_fallback",
            }
    work_stage_id = np.asarray(step.get("work_stage_id", []), dtype=np.int32)
    if work_stage_id.size:
        candidates = np.flatnonzero(work_stage_id == WORK_STAGE_NAME_TO_ID["dump"])
        candidates = candidates[(candidates >= start) & (candidates < end)]
        if len(candidates) > 0:
            idx = int(candidates[0])
            return idx, {
                "release_onset_step": int(idx),
                "release_onset_source": "dump_stage_fallback",
            }
    return None, {
        "release_onset_step": -1,
        "release_onset_source": "missing",
    }


def _find_spatial_mass_dump_start(
    *,
    episode: dict[str, Any],
    cycle_start: int,
    release_onset: int,
) -> tuple[int, dict[str, Any]]:
    release_i = max(0, int(release_onset))
    lead_start = max(
        int(cycle_start),
        release_i - int(SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS),
    )
    qc: dict[str, Any] = {
        "dump_start_lead_cap_candidate_step": int(lead_start),
        "dump_start_max_outside_distance_m": float(
            SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M
        ),
        "dump_start_stable_outside_distance_m": float(
            SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M
        ),
        "dump_start_stable_window_steps": int(
            SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS
        ),
        "dump_start_outside_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M
        ),
        "dump_start_total_approach_tol_m": float(
            SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M
        ),
        "dump_start_relative_x_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M
        ),
        "dump_start_relative_z_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M
        ),
        "dump_start_relative_x_min_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
        ),
        "dump_start_relative_x_max_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
        ),
        "dump_start_relative_z_min_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
        ),
        "dump_start_relative_z_max_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
        ),
        "dump_start_min_height_above_rim_m": float(
            SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
        ),
        "dump_start_source": "release_lead_cap",
    }
    env_state = _env_state_or_none(episode)
    if env_state is None or env_state.shape[0] <= lead_start:
        qc["dump_start_source"] = "release_lead_cap_missing_env_state"
        return int(lead_start), qc
    end_i = min(int(release_i), int(env_state.shape[0] - 1))
    if end_i < lead_start:
        return int(lead_start), qc
    outside = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
        default=float("inf"),
    )
    over = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        default=0.0,
    )
    relative_x = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
        default=float("nan"),
    )
    relative_z = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
        default=float("nan"),
    )
    height_above_rim = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        default=float("nan"),
    )
    clearance = _optional_env_col(
        env_state,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        default=0.0,
    )
    has_relative_geometry = bool(
        env_state.shape[1] > ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX
    )
    selected = int(lead_start)
    release_outside = float(outside[end_i])
    for idx in range(int(lead_start), int(end_i) + 1):
        outside_value = float(outside[idx])
        over_value = float(over[idx])
        height_value = float(height_above_rim[idx])
        near_dump_area = (
            np.isfinite(outside_value)
            and outside_value <= SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M
        ) or over_value > 0.5
        height_ok = (
            not np.isfinite(height_value)
            or height_value >= SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
        )
        if not near_dump_area or not height_ok:
            continue
        window_end = min(
            int(end_i) + 1,
            int(idx) + int(SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS),
        )
        outside_window = outside[int(idx) : window_end]
        finite_window = outside_window[np.isfinite(outside_window)]
        outside_range = (
            float(np.max(finite_window) - np.min(finite_window))
            if len(finite_window) > 0
            else float("inf")
        )
        total_approach = (
            abs(outside_value - release_outside)
            if np.isfinite(outside_value) and np.isfinite(release_outside)
            else 0.0 if over_value > 0.5 else float("inf")
        )
        relative_x_value = float(relative_x[idx])
        relative_z_value = float(relative_z[idx])
        relative_corridor_ok = (
            not has_relative_geometry
            or (
                np.isfinite(relative_x_value)
                and np.isfinite(relative_z_value)
                and SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
                <= relative_x_value
                <= SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
                and SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
                <= relative_z_value
                <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
            )
        )
        relative_x_window = relative_x[int(idx) : window_end]
        relative_z_window = relative_z[int(idx) : window_end]
        relative_x_range = (
            _finite_range(relative_x_window)
            if has_relative_geometry
            else 0.0
        )
        relative_z_range = (
            _finite_range(relative_z_window)
            if has_relative_geometry
            else 0.0
        )
        if (
            outside_range <= SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M
            and total_approach <= SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M
            and relative_corridor_ok
            and relative_x_range <= SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M
            and relative_z_range <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M
        ):
            selected = int(idx)
            qc["dump_start_source"] = "dump_area_committed_aiming_band"
            qc["dump_start_selected_outside_range_m"] = float(outside_range)
            qc["dump_start_selected_total_approach_m"] = float(total_approach)
            qc["dump_start_selected_relative_x_range_m"] = float(relative_x_range)
            qc["dump_start_selected_relative_z_range_m"] = float(relative_z_range)
            break
    else:
        candidates: list[int] = []
        for idx in range(int(lead_start), int(end_i) + 1):
            outside_value = float(outside[idx])
            over_value = float(over[idx])
            height_value = float(height_above_rim[idx])
            height_ok = (
                not np.isfinite(height_value)
                or height_value >= SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
            )
            relative_corridor_ok = (
                not has_relative_geometry
                or (
                    np.isfinite(float(relative_x[idx]))
                    and np.isfinite(float(relative_z[idx]))
                    and SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
                    <= float(relative_x[idx])
                    <= SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
                    and SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
                    <= float(relative_z[idx])
                    <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
                )
            )
            if height_ok and relative_corridor_ok and (
                np.isfinite(outside_value)
                and outside_value <= SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M
                or over_value > 0.5
            ):
                candidates.append(int(idx))
        if candidates:
            fallback_floor = int(end_i) - int(
                SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS
            )
            late_candidates = [idx for idx in candidates if idx >= fallback_floor]
            selected = int(late_candidates[0] if late_candidates else candidates[-1])
            qc["dump_start_source"] = "late_pre_release_aiming_fallback"
            qc["dump_start_fallback_pre_release_steps"] = int(
                SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS
            )
        else:
            selected = int(end_i)
            qc["dump_start_source"] = "release_onset_no_aiming_candidate"
    qc["dump_start_selected_step"] = int(selected)
    qc["dump_start_selected_outside_distance_m"] = float(
        np.nan_to_num(outside[selected], nan=float("nan"), posinf=float("inf"))
    )
    qc["dump_start_release_outside_distance_m"] = float(
        np.nan_to_num(release_outside, nan=float("nan"), posinf=float("inf"))
    )
    qc["dump_start_selected_relative_x_m"] = float(
        np.nan_to_num(relative_x[selected], nan=float("nan"))
    )
    qc["dump_start_selected_relative_z_m"] = float(
        np.nan_to_num(relative_z[selected], nan=float("nan"))
    )
    qc["dump_start_release_relative_x_m"] = float(
        np.nan_to_num(relative_x[end_i], nan=float("nan"))
    )
    qc["dump_start_release_relative_z_m"] = float(
        np.nan_to_num(relative_z[end_i], nan=float("nan"))
    )
    qc["dump_start_selected_height_above_rim_m"] = float(
        np.nan_to_num(height_above_rim[selected], nan=float("nan"))
    )
    qc["dump_start_selected_over_target_footprint"] = int(over[selected] > 0.5)
    qc["dump_start_selected_clearance_ok"] = int(clearance[selected] > 0.5)
    return int(selected), qc


def _find_spatial_mass_dump_end(
    *,
    episode: dict[str, Any],
    search_end: int,
    release_onset: int,
) -> tuple[int, dict[str, Any]]:
    work_end = int(search_end)
    release_i = max(0, int(release_onset))
    qc: dict[str, Any] = {
        "dump_legacy_work_end_step": int(work_end),
        "dump_end_source": "legacy_work_end",
        "dump_end_residual_bucket_mass_kg": float(
            SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG
        ),
        "dump_end_plateau_steps": int(SPATIAL_MASS_DUMP_END_PLATEAU_STEPS),
    }
    env_state = _env_state_or_none(episode)
    if env_state is None or work_end <= release_i + 1:
        qc["dump_end_source"] = "legacy_work_end_missing_env_state"
        return int(work_end), qc

    n_steps = int(env_state.shape[0])
    end_i = min(max(0, work_end - 1), n_steps - 1)
    release_i = min(release_i, end_i)
    mass = _optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = _spatial_mass_deposit_trace(env_state)
    release_mass = max(0.0, float(mass[release_i]))
    residual_limit = max(
        5.0,
        min(
            float(SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG),
            release_mass * 0.35,
        ),
    )
    hold = max(1, int(SPATIAL_MASS_DUMP_END_PLATEAU_STEPS))
    search_limit_exclusive = min(
        end_i + 1,
        release_i + int(SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS),
    )
    latest_plateau_start = max(release_i + 1, search_limit_exclusive - hold)
    low_mass_candidates: list[int] = []
    for idx in range(release_i + 1, latest_plateau_start + 1):
        if float(mass[idx]) > residual_limit:
            continue
        low_mass_candidates.append(int(idx))
        plateau_end = int(idx) + hold
        mass_window = mass[idx:plateau_end]
        deposit_window = deposit[idx:plateau_end]
        mass_range = float(np.nanmax(mass_window) - np.nanmin(mass_window))
        deposit_gain = float(max(0.0, deposit_window[-1] - deposit_window[0]))
        if (
            mass_range <= SPATIAL_MASS_DUMP_END_MASS_RANGE_TOL_KG
            and deposit_gain <= SPATIAL_MASS_DUMP_END_DEPOSIT_GAIN_TOL_KG
        ):
            qc.update(
                {
                    "dump_end_source": "residual_mass_deposit_plateau",
                    "dump_end_selected_step": int(plateau_end),
                    "dump_end_low_mass_step": int(idx),
                    "dump_end_residual_limit_kg": float(residual_limit),
                    "dump_end_plateau_mass_range_kg": mass_range,
                    "dump_end_plateau_deposit_gain_kg": deposit_gain,
                }
            )
            return int(plateau_end), qc

    if low_mass_candidates:
        selected = min(end_i + 1, int(low_mass_candidates[0]) + hold)
        qc.update(
            {
                "dump_end_source": "residual_mass_post_hold_fallback",
                "dump_end_selected_step": int(selected),
                "dump_end_low_mass_step": int(low_mass_candidates[0]),
                "dump_end_residual_limit_kg": float(residual_limit),
            }
        )
        return int(selected), qc

    capped = min(end_i + 1, release_i + int(SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS))
    if capped < work_end:
        qc.update(
            {
                "dump_end_source": "post_release_cap_fallback",
                "dump_end_selected_step": int(capped),
                "dump_end_post_release_cap_steps": int(
                    SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS
                ),
            }
        )
        return int(capped), qc
    qc["dump_end_selected_step"] = int(work_end)
    return int(work_end), qc


def _spatial_mass_deposit_trace(env_state: np.ndarray) -> np.ndarray:
    deposit = np.zeros(len(env_state), dtype=np.float32)
    for col in (
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ):
        if col < env_state.shape[1]:
            deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
    return deposit


def _spatial_mass_carry_qc(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
    release_onset: int,
) -> dict[str, Any]:
    qc = {
        "carry_start_step": int(start),
        "carry_end_step": int(end),
        "carry_window_len": int(end) - int(start),
        "carry_release_onset_step": int(release_onset),
        "carry_steps_before_release": int(release_onset) - int(end),
    }
    env_state = _env_state_or_none(episode)
    if env_state is None or int(end) <= int(start):
        qc["carry_qc_missing_env_state"] = True
        return qc
    start_i = max(0, min(int(start), len(env_state) - 1))
    end_i = max(start_i, min(int(end) - 1, len(env_state) - 1))
    mass = _optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = np.zeros(len(env_state), dtype=np.float32)
    for col in (
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ):
        if col < env_state.shape[1]:
            deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
    mass_loss = float(max(0.0, mass[start_i] - mass[end_i]))
    deposit_delta = float(max(0.0, deposit[end_i] - deposit[start_i]))
    ratio = float(0.0 if mass_loss <= 1.0e-6 else deposit_delta / mass_loss)
    qc.update(
        {
            "carry_start_bucket_mass_kg": float(mass[start_i]),
            "carry_end_bucket_mass_kg": float(mass[end_i]),
            "carry_bucket_mass_loss_kg": mass_loss,
            "carry_deposit_delta_kg": deposit_delta,
            "carry_deposit_to_payload_loss_frac": ratio,
            "carry_max_deposit_delta_kg": float(SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG),
            "carry_max_deposit_to_payload_loss_frac": float(
                SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
            ),
        }
    )
    return qc


def _spatial_mass_carry_contaminated(qc: dict[str, Any]) -> bool:
    deposit_delta = float(qc.get("carry_deposit_delta_kg", 0.0))
    ratio = float(qc.get("carry_deposit_to_payload_loss_frac", 0.0))
    return bool(
        deposit_delta > SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG
        and ratio > SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
    )


def _spatial_mass_dump_qc(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
    release_onset: int,
    release_qc: dict[str, Any],
) -> dict[str, Any]:
    qc = dict(release_qc)
    qc.update(
        {
            "dump_start_step": int(start),
            "dump_end_step": int(end),
            "dump_window_len": int(end) - int(start),
            "dump_release_onset_step": int(release_onset),
            "dump_pre_release_lead_steps": int(release_onset) - int(start),
            "dump_pre_release_lead_cap_steps": int(
                SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS
            ),
        }
    )
    env_state = _env_state_or_none(episode)
    if env_state is None or int(end) <= int(start):
        qc["dump_qc_missing_env_state"] = True
        return qc
    start_i = max(0, min(int(start), len(env_state) - 1))
    end_i = max(start_i, min(int(end) - 1, len(env_state) - 1))
    release_i = max(start_i, min(int(release_onset), end_i))
    mass = _optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = np.zeros(len(env_state), dtype=np.float32)
    for col in (
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ):
        if col < env_state.shape[1]:
            deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
    window_mass_loss = float(max(0.0, mass[start_i] - mass[end_i]))
    release_mass_loss = float(max(0.0, mass[release_i] - mass[end_i]))
    deposit_delta = float(max(0.0, deposit[end_i] - deposit[start_i]))
    outside = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
        default=float("nan"),
    )
    relative_x = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
        default=float("nan"),
    )
    relative_z = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
        default=float("nan"),
    )
    height_above_rim = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        default=float("nan"),
    )
    over = _optional_env_col(
        env_state,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        default=0.0,
    )
    clearance = _optional_env_col(
        env_state,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        default=0.0,
    )
    qc.update(
        {
            "dump_window_mass_loss_kg": window_mass_loss,
            "dump_release_mass_loss_kg": release_mass_loss,
            "dump_deposit_delta_kg": deposit_delta,
            "dump_release_deposit_fraction": float(
                0.0 if release_mass_loss <= 1.0e-6 else deposit_delta / release_mass_loss
            ),
            "dump_start_dump_area_footprint_outside_distance_m": float(
                np.nan_to_num(outside[start_i], nan=float("nan"))
            ),
            "dump_release_dump_area_footprint_outside_distance_m": float(
                np.nan_to_num(outside[release_i], nan=float("nan"))
            ),
            "dump_start_dump_area_relative_x_m": float(
                np.nan_to_num(relative_x[start_i], nan=float("nan"))
            ),
            "dump_start_dump_area_relative_z_m": float(
                np.nan_to_num(relative_z[start_i], nan=float("nan"))
            ),
            "dump_release_dump_area_relative_x_m": float(
                np.nan_to_num(relative_x[release_i], nan=float("nan"))
            ),
            "dump_release_dump_area_relative_z_m": float(
                np.nan_to_num(relative_z[release_i], nan=float("nan"))
            ),
            "dump_start_height_above_rim_m": float(
                np.nan_to_num(height_above_rim[start_i], nan=float("nan"))
            ),
            "dump_start_over_target_footprint": int(over[start_i] > 0.5),
            "dump_start_clearance_ok": int(clearance[start_i] > 0.5),
        }
    )
    return qc


def _build_return_start_envelope_token(
    *,
    episode: dict[str, Any],
    next_start_step: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    valid_mask = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.uint8)
    qpos = np.asarray(episode.get("qpos", []), dtype=np.float32)
    qvel = np.asarray(episode.get("qvel", []), dtype=np.float32)
    env_state = _env_state_or_none(episode)
    next_start = int(next_start_step)
    qpos_valid = (
        qpos.ndim == 2
        and qpos.shape[0] > next_start
        and qpos.shape[1] >= 4
        and np.all(np.isfinite(qpos[next_start, :4]))
    )
    window_end = min(
        qpos.shape[0] if qpos.ndim == 2 else next_start,
        next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
    )
    qvel_valid = False
    if qpos_valid:
        qpos_window = qpos[next_start:window_end, :4]
        qpos_center = qpos[next_start, :4]
        if qpos_window.shape[0] > 1:
            half_width = 0.5 * (
                np.percentile(qpos_window, 90, axis=0)
                - np.percentile(qpos_window, 10, axis=0)
            )
        else:
            half_width = np.zeros(4, dtype=np.float32)
        half_width = np.clip(np.maximum(half_width, 0.02), 0.02, 0.35)
        token[7:11] = qpos_center.astype(np.float32)
        token[11:15] = half_width.astype(np.float32)
        valid_mask[7:15] = 1
        if qvel.ndim == 2 and qvel.shape[0] > next_start:
            qvel_window = qvel[
                next_start : min(
                    qvel.shape[0],
                    next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
                ),
                :4,
            ]
            qvel_valid = bool(qvel_window.size and np.all(np.isfinite(qvel_window)))
            token[15] = float(np.max(np.abs(qvel_window))) if qvel_valid else 0.0
            if qvel_valid:
                valid_mask[15] = 1
    selected_env_step: int | None = None
    selected_env_source = "missing_env_state"
    geometry_available = False
    if env_state is not None and env_state.shape[0] > next_start:
        geometry = _optional_env_col(
            env_state,
            ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
            default=0.0,
        )
        long_norm = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
            default=0.0,
        )
        short_norm = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
            default=0.0,
        )
        depth = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
            default=0.0,
        )
        contact = _optional_env_col(
            env_state,
            ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
            default=0.0,
        )
        env_window_end = min(
            env_state.shape[0],
            next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
        )
        candidate_indices = np.arange(next_start, env_window_end, dtype=np.int32)
        finite_spatial = (
            np.isfinite(long_norm[candidate_indices])
            & np.isfinite(short_norm[candidate_indices])
            & np.isfinite(depth[candidate_indices])
        )
        geometry_candidates = candidate_indices[
            finite_spatial & (geometry[candidate_indices] > 0.5)
        ]
        finite_candidates = candidate_indices[finite_spatial]
        if len(geometry_candidates) > 0:
            selected_env_step = int(geometry_candidates[0])
            selected_env_source = "first_geometry_available_in_window"
            geometry_available = True
        elif len(finite_candidates) > 0:
            selected_env_step = int(finite_candidates[0])
            selected_env_source = "first_finite_spatial_in_window"
            geometry_available = bool(geometry[selected_env_step] > 0.5)

    if selected_env_step is not None:
        token[0] = float(long_norm[selected_env_step])
        token[1] = float(short_norm[selected_env_step])
        token[2] = float(max(0.0, depth[selected_env_step]))
        token[3] = 0.20
        token[4] = float(max(0.0, token[2] - 0.08))
        token[5] = float(token[2] + 0.08)
        token[6] = float(contact[selected_env_step] > 0.5)
        valid_mask[0:7] = 1
        valid_mask[17] = 1
        token[17] = 1.0
    elif qpos_valid:
        token[3] = 0.20
        token[5] = 0.08
        valid_mask[3] = 1
        valid_mask[5] = 1
        valid_mask[17] = 1
        token[17] = 1.0
    token[16] = float(qpos_valid)
    if qpos_valid:
        valid_mask[16] = 1
    qc = {
        "return_start_envelope_valid": bool(token[16] > 0.5),
        "return_start_envelope_selected_step": (
            -1 if selected_env_step is None else int(selected_env_step)
        ),
        "return_start_envelope_selected_offset": (
            -1 if selected_env_step is None else int(selected_env_step) - int(next_start)
        ),
        "return_start_envelope_selected_source": selected_env_source,
        "return_start_envelope_geometry_available": bool(geometry_available),
        "return_start_envelope_window_steps": int(RETURN_START_ENVELOPE_WINDOW_STEPS),
        "return_start_envelope_valid_dim_count": int(np.sum(valid_mask > 0)),
        "return_start_envelope_long_norm": float(token[0]),
        "return_start_envelope_short_norm": float(token[1]),
        "return_start_envelope_depth_center_m": float(token[2]),
        "return_start_envelope_qpos_half_width_max": float(np.max(token[11:15])),
        "return_start_envelope_qvel_abs_max": float(token[15]),
    }
    return token, valid_mask, qc


def _env_state_or_none(episode: dict[str, Any]) -> np.ndarray | None:
    value = episode.get("env_state")
    if value is None:
        return None
    arr = np.asarray(value, dtype=np.float32)
    if arr.ndim != 2:
        return None
    return arr


def _optional_env_col(
    env_state: np.ndarray,
    index: int,
    *,
    default: float,
) -> np.ndarray:
    if int(index) < env_state.shape[1]:
        return np.asarray(env_state[:, int(index)], dtype=np.float32)
    return np.full(env_state.shape[0], float(default), dtype=np.float32)


def _finite_range(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if len(finite) <= 0:
        return float("inf")
    return float(np.max(finite) - np.min(finite))


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
    v2_payload = build_primitive_v2_payload(
        source_episode=source_episode,
        crop=crop,
        cycle_id_offset=cycle_id_offset,
        zero_cycle_id=(primitive_slice.primitive_name != "return"),
        source_cycle_id=int(primitive_slice.source_cycle_id),
    )
    _merge_primitive_step_overlay(v2_payload=v2_payload, primitive_slice=primitive_slice)
    metadata = _build_primitive_metadata(
        source_episode=source_episode,
        source_dataset_dir=source_dataset_dir,
        primitive_slice=primitive_slice,
        output_episode_id=output_episode_id,
        primitive_version=primitive_version,
        absolute_start=absolute_start,
        absolute_end_exclusive=absolute_end_exclusive,
        window_len=window_len,
        v2_payload=v2_payload,
    )

    images = {
        camera_name: np.asarray(camera_frames[crop])
        for camera_name, camera_frames in dict(source_episode.get("images", {})).items()
    }

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


def write_primitive_episode_vds(
    *,
    target_path: str | Path,
    source_hdf5_path: str | Path,
    source_episode: dict[str, Any],
    source_dataset_dir: str | Path,
    primitive_slice: PrimitiveSlice,
    output_episode_id: int,
    cycle_id_offset: int = 0,
    primitive_version: str = PRIMITIVE_VERSION,
    vds_base_step: int = 0,
) -> None:
    """Write a primitive episode as a VDS crop of a source HDF5 episode."""
    start = int(primitive_slice.start_step)
    end = int(primitive_slice.end_step_exclusive)
    crop = slice(start, end)
    window_len = end - start
    if window_len <= 0:
        raise ValueError("Primitive slice must contain at least one timestep.")

    source_start_offset = _source_start_step_offset(episode=source_episode)
    absolute_start = int(source_start_offset + start)
    absolute_end_exclusive = int(source_start_offset + end)
    vds_start = int(vds_base_step + start)
    vds_end = int(vds_base_step + end)
    v2_payload = build_primitive_v2_payload(
        source_episode=source_episode,
        crop=crop,
        cycle_id_offset=cycle_id_offset,
        zero_cycle_id=(primitive_slice.primitive_name != "return"),
        source_cycle_id=int(primitive_slice.source_cycle_id),
    )
    _merge_primitive_step_overlay(v2_payload=v2_payload, primitive_slice=primitive_slice)
    metadata = _build_primitive_metadata(
        source_episode=source_episode,
        source_dataset_dir=source_dataset_dir,
        primitive_slice=primitive_slice,
        output_episode_id=output_episode_id,
        primitive_version=primitive_version,
        absolute_start=absolute_start,
        absolute_end_exclusive=absolute_end_exclusive,
        window_len=window_len,
        v2_payload=v2_payload,
    )
    metadata.update(
        {
            "primitive_storage_mode": STORAGE_MODE_VDS,
            "source_episode_path": str(Path(source_hdf5_path).resolve()),
            "source_start_step": int(absolute_start),
            "source_end_step_exclusive": int(absolute_end_exclusive),
        }
    )
    step_overlay = {}
    if "cycle_id" in dict(v2_payload.get("step", {})):
        step_overlay["cycle_id"] = np.asarray(v2_payload["step"]["cycle_id"])
    for key in dict(primitive_slice.v2_step_overlay or {}):
        if key in dict(v2_payload.get("step", {})):
            step_overlay[str(key)] = np.asarray(v2_payload["step"][key])
    write_vds_episode(
        target_path,
        source_path=source_hdf5_path,
        crop=slice(vds_start, vds_end),
        metadata=metadata,
        v2_step_overlay=step_overlay,
        v2_cycle_payload=dict(v2_payload.get("cycle", {}) or {}),
        action_src_types=_slice_optional_list(source_episode.get("action_src_types"), crop),
        action_src_ids=_slice_optional_list(source_episode.get("action_src_ids"), crop),
    )


def _build_primitive_metadata(
    *,
    source_episode: dict[str, Any],
    source_dataset_dir: str | Path,
    primitive_slice: PrimitiveSlice,
    output_episode_id: int,
    primitive_version: str,
    absolute_start: int,
    absolute_end_exclusive: int,
    window_len: int,
    v2_payload: dict[str, dict[str, np.ndarray]],
) -> dict[str, Any]:
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
    metadata.update(_cycle_metadata_attrs(v2_payload.get("cycle", {})))
    if primitive_slice.dump_intent_step is not None:
        metadata["dump_intent_step"] = int(primitive_slice.dump_intent_step)
    if primitive_slice.official_dump_start_step is not None:
        metadata["official_dump_start_step"] = int(primitive_slice.official_dump_start_step)
    if primitive_slice.dump_release_step is not None:
        metadata["dump_release_step"] = int(primitive_slice.dump_release_step)
    if primitive_slice.dump_end_step is not None:
        metadata["dump_end_step"] = int(primitive_slice.dump_end_step)
    if primitive_slice.boundary_profile is not None:
        metadata["primitive_boundary_profile"] = str(primitive_slice.boundary_profile)
    if primitive_slice.source_prev_cycle_id is not None:
        metadata["source_prev_cycle_id"] = int(primitive_slice.source_prev_cycle_id)
    if primitive_slice.source_next_cycle_id is not None:
        metadata["source_next_cycle_id"] = int(primitive_slice.source_next_cycle_id)
    for qc in (
        dict(primitive_slice.carry_qc or {}),
        dict(primitive_slice.approach_qc or {}),
        dict(primitive_slice.dump_qc or {}),
        dict(primitive_slice.return_qc or {}),
    ):
        for key, value in qc.items():
            if isinstance(value, np.generic):
                value = value.item()
            if isinstance(value, (bool, int, float, str)):
                metadata[str(key)] = value
    return metadata


def _merge_primitive_step_overlay(
    *,
    v2_payload: dict[str, dict[str, np.ndarray]],
    primitive_slice: PrimitiveSlice,
) -> None:
    overlay = dict(primitive_slice.v2_step_overlay or {})
    if not overlay:
        return
    step_payload = v2_payload.setdefault("step", {})
    window_len = int(primitive_slice.window_len)
    for key, value in overlay.items():
        arr = np.asarray(value)
        if arr.shape[0] != window_len:
            raise ValueError(
                f"Primitive step overlay {key!r} length {arr.shape[0]} does not "
                f"match window length {window_len}."
            )
        step_payload[str(key)] = np.asarray(arr).copy()


def build_primitive_v2_payload(
    *,
    source_episode: dict[str, Any],
    crop: slice,
    cycle_id_offset: int = 0,
    zero_cycle_id: bool = True,
    source_cycle_id: int | None = None,
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
    cycle_payload = _select_primitive_cycle_payload(
        source_episode=source_episode,
        source_cycle_id=source_cycle_id,
        cycle_id_offset=cycle_id_offset,
        zero_cycle_id=zero_cycle_id,
    )

    return {
        "step": step_payload,
        "cycle": cycle_payload,
    }


def _select_primitive_cycle_payload(
    *,
    source_episode: dict[str, Any],
    source_cycle_id: int | None,
    cycle_id_offset: int,
    zero_cycle_id: bool,
) -> dict[str, np.ndarray]:
    v2 = source_episode.get("v2") or {}
    cycle_data = dict(v2.get("cycle", {}) or {})
    if not cycle_data:
        return {}

    first_len = min(
        (len(np.asarray(value)) for value in cycle_data.values() if np.asarray(value).ndim > 0),
        default=0,
    )
    if first_len <= 0:
        return {}

    index = 0
    if source_cycle_id is not None and "cycle_id" in cycle_data:
        cycle_ids = np.asarray(cycle_data["cycle_id"]).reshape(-1)
        matches = np.flatnonzero(cycle_ids.astype(np.int64) == int(source_cycle_id))
        if len(matches) > 0:
            index = int(matches[0])
    elif source_cycle_id is not None and 0 <= int(source_cycle_id) < first_len:
        index = int(source_cycle_id)
    if index >= first_len:
        index = 0

    payload: dict[str, np.ndarray] = {}
    for key, value in cycle_data.items():
        arr = np.asarray(value)
        if arr.ndim <= 0 or arr.shape[0] <= index:
            continue
        selected = np.asarray(arr[index : index + 1]).copy()
        if key == "cycle_id":
            if zero_cycle_id:
                selected = np.zeros(1, dtype=np.int32)
            else:
                selected = (
                    np.asarray(selected, dtype=np.int32) - int(cycle_id_offset)
                ).astype(np.int32)
        payload[str(key)] = selected
    return payload


def _cycle_metadata_attrs(cycle_payload: dict[str, np.ndarray]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key in PRIMITIVE_CYCLE_METADATA_KEYS:
        if key not in cycle_payload:
            continue
        arr = np.asarray(cycle_payload[key])
        if arr.size <= 0:
            continue
        value = arr.reshape(-1)[0]
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, (bool, int, float, str)):
            attrs[key] = value
    return attrs


def _return_target_reject_reason(
    *,
    episode: dict[str, Any],
    source_cycle_id: int,
) -> str | None:
    """Reject conditioned-return windows whose next dig target is unavailable.

    Legacy datasets do not have operator-first return target fields, so they keep
    the old transition behavior. When the fields are present, the return
    primitive is only useful for conditioned training if it points to a concrete
    next operator cut.
    """

    cycle_payload = _select_primitive_cycle_payload(
        source_episode=episode,
        source_cycle_id=int(source_cycle_id),
        cycle_id_offset=0,
        zero_cycle_id=False,
    )
    if "return_target_source" not in cycle_payload:
        return None
    cycle_attrs = _cycle_metadata_attrs(cycle_payload)
    source = str(cycle_attrs.get("return_target_source", "")).strip()
    if source != "operator_next_entry":
        return f"return_target_unavailable:{source or 'missing'}"
    if "next_operator_cut_valid" in cycle_attrs:
        try:
            if int(cycle_attrs["next_operator_cut_valid"]) != 1:
                return "return_target_unavailable:invalid_next_cut"
        except (TypeError, ValueError):
            return "return_target_unavailable:invalid_next_cut"
    return None


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
    continuing_dump_start = max(int(start), int(end) - CARRY_CURL_OUT_LOOKBACK_STEPS)
    for onset in _stable_true_indices(
        continuing_dump,
        start=continuing_dump_start,
        end=int(end),
        min_stable_steps=CARRY_CURL_OUT_MIN_STABLE_STEPS,
    ):
        return int(onset)
    return None


def _find_stable_release_onset(
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
    release_mask = (
        (qpos[:, BUCKET_QPOS_INDEX] >= DUMP_INTENT_BUCKET_QPOS_MIN)
        & (actions[:, BUCKET_ACTION_INDEX] <= DUMP_INTENT_BUCKET_ACTION_MAX)
    )
    for onset in _stable_true_indices(
        release_mask,
        start=int(start),
        end=int(end),
        min_stable_steps=DUMP_INTENT_MIN_STABLE_STEPS,
    ):
        return int(onset)
    return _find_stable_carry_curl_out_onset(
        episode=episode,
        start=int(start),
        end=int(end),
    )


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

    env_state = _target_geometry_env_state(
        episode=episode,
        require_dump_area_geometry=True,
    )
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
        if ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX < env_state.shape[1]:
            qc.update(
                {
                    f"{prefix}_start_dump_area_relative_x_m": float(
                        env_state[start, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
                    ),
                    f"{prefix}_start_dump_area_relative_z_m": float(
                        env_state[start, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
                    ),
                    f"{prefix}_start_dump_area_footprint_outside_distance_m": float(
                        env_state[
                            start,
                            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
                        ]
                    ),
                    f"{prefix}_end_dump_area_relative_x_m": float(
                        env_state[end - 1, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
                    ),
                    f"{prefix}_end_dump_area_relative_z_m": float(
                        env_state[end - 1, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
                    ),
                    f"{prefix}_end_dump_area_footprint_outside_distance_m": float(
                        env_state[
                            end - 1,
                            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
                        ]
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

    env_state = _target_geometry_env_state(
        episode=episode,
        require_dump_area_geometry=True,
    )
    if env_state is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={
                "dump_intent_search_start_step": int(search_start),
                "dump_intent_search_end_step": int(search_end),
                "dump_intent_requires_dump_area_geometry": True,
            },
            reject_reason="missing_dump_area_geometry_for_dump_intent",
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
            "dump_intent_requires_dump_area_geometry": True,
            "dump_intent_max_dump_area_footprint_outside_distance_m": float(
                DUMP_INTENT_MAX_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_M
            ),
        },
        reject_reason="missing_safe_dump_intent",
    )


def _find_good_dump_acceptance(
    *,
    episode: dict[str, Any],
    start: int | None,
    release_marker: int | None,
    official_dump_start: int | None,
) -> DumpIntentSearchResult:
    """Accept robust human dump entrances when the whole dump is good.

    Strict safe-intent matching is useful for clean ownership labels, but it is
    too narrow for human teleop: some no-crash, successful dumps enter release
    without matching one exact pre-release geometry/action pattern. This helper
    keeps those windows if the final dump quality is good, while still marking
    them as quality-accepted rather than strict safe-intent examples.
    """
    if start is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={},
            reject_reason="missing_good_dump_quality_start",
        )
    if release_marker is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={},
            reject_reason="missing_good_dump_release_marker",
        )
    if _target_geometry_env_state(episode=episode, require_dump_area_geometry=True) is None:
        return DumpIntentSearchResult(
            start_step=None,
            qc={"dump_quality_missing_target_geometry": True},
            reject_reason="missing_target_geometry_for_good_dump_quality",
        )
    release_marker = int(release_marker)
    official_marker = int(official_dump_start) if official_dump_start is not None else release_marker
    dump_qc = _dump_window_qc(
        episode=episode,
        start=release_marker,
        end=len(episode["actions"]),
        official_dump_start=official_marker,
    )
    quality_qc = _good_dump_quality_qc(
        episode=episode,
        start=int(start),
        release_marker=release_marker,
        end=len(episode["actions"]),
    )
    qc = dict(dump_qc)
    qc.update(quality_qc)
    reject_reasons = _good_dump_quality_reject_reasons(qc)
    if reject_reasons:
        qc["dump_quality_reject_reasons"] = ",".join(reject_reasons)
        return DumpIntentSearchResult(
            start_step=None,
            qc=qc,
            reject_reason=str(reject_reasons[0]),
        )
    qc["dump_acceptance_mode"] = "good_dump_quality"
    return DumpIntentSearchResult(start_step=release_marker, qc=qc)


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
        & (
            env_state[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            <= DUMP_INTENT_MAX_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_M
        )
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


def _target_geometry_env_state(
    *,
    episode: dict[str, Any],
    require_dump_area_geometry: bool = False,
) -> np.ndarray | None:
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
    if require_dump_area_geometry:
        required_indices = required_indices + (
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
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
    env_state = _target_geometry_env_state(episode=episode, require_dump_area_geometry=True)
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
    dump_area_outside = window[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
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
        "dump_intent_max_dump_area_footprint_outside_distance_m": float(
            DUMP_INTENT_MAX_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_M
        ),
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
        "dump_start_dump_area_relative_x_m": float(
            env_state[start, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
        ),
        "dump_start_dump_area_relative_z_m": float(
            env_state[start, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
        ),
        "dump_start_dump_area_footprint_outside_distance_m": float(
            env_state[start, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
        ),
        "dump_min_dump_area_footprint_outside_distance_m": float(np.min(dump_area_outside)),
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


def _good_dump_quality_qc(
    *,
    episode: dict[str, Any],
    start: int,
    release_marker: int,
    end: int,
) -> dict[str, Any]:
    env_state = _target_geometry_env_state(episode=episode, require_dump_area_geometry=True)
    if env_state is None:
        return {"dump_quality_missing_target_geometry": True}
    start = max(0, int(start))
    release_marker = max(start, int(release_marker))
    end = min(int(end), len(env_state))
    if end <= start:
        return {
            "dump_quality_start_step": int(start),
            "dump_quality_release_marker_step": int(release_marker),
            "dump_quality_invalid_window": True,
        }
    window = env_state[start:end]
    release_window = env_state[release_marker:end]
    if len(release_window) <= 0:
        release_window = window

    mass_start = float(np.max(window[:, ENV_STATE_MASS_IN_BUCKET_IDX]))
    mass_end = float(env_state[end - 1, ENV_STATE_MASS_IN_BUCKET_IDX])
    bucket_mass_loss = float(max(0.0, mass_start - mass_end))
    deposited_start = float(env_state[start, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX])
    deposited_end = float(
        np.max(window[:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX])
    )
    deposit_delta = float(max(0.0, deposited_end - deposited_start))
    deposited_fraction = float(
        0.0 if bucket_mass_loss <= 1e-6 else deposit_delta / bucket_mass_loss
    )
    hard_collision_delta = int(
        round(
            float(
                np.max(window[:, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX])
                - window[0, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]
            )
        )
    )

    cycle_qc = _single_cycle_quality_qc(episode)
    cycle_success = int(cycle_qc.get("dump_quality_cycle_success", 0))
    metadata_success = int(dict(episode.get("metadata", {})).get("success", 0))
    cycle_collision_delta = int(
        cycle_qc.get("dump_quality_cycle_collision_delta_count", 0)
    )
    cycle_deposit_delta = float(cycle_qc.get("dump_quality_cycle_deposit_delta_kg", 0.0))
    hard_collision_delta = max(0, hard_collision_delta, cycle_collision_delta)
    deposit_delta_for_accept = float(max(deposit_delta, cycle_deposit_delta))
    fraction_for_accept = float(
        0.0
        if bucket_mass_loss <= 1e-6
        else deposit_delta_for_accept / bucket_mass_loss
    )
    good_by_cycle_success = bool(cycle_success > 0 and hard_collision_delta <= 0)
    good_by_mass_fraction = bool(
        bucket_mass_loss >= GOOD_DUMP_MIN_BUCKET_MASS_LOSS_KG
        and deposit_delta_for_accept >= GOOD_DUMP_MIN_DEPOSIT_DELTA_KG
        and fraction_for_accept >= GOOD_DUMP_MIN_DEPOSITED_FRACTION_OF_BUCKET_LOSS
    )
    good_by_metadata = bool(
        metadata_success > 0
        and deposit_delta_for_accept >= GOOD_DUMP_MIN_DEPOSIT_DELTA_KG
        and hard_collision_delta <= 0
    )
    acceptance_source = "none"
    if good_by_cycle_success:
        acceptance_source = "cycle_success"
    elif good_by_mass_fraction:
        acceptance_source = "mass_fraction"
    elif good_by_metadata:
        acceptance_source = "metadata_success"

    qc = {
        "dump_quality_start_step": int(start),
        "dump_quality_release_marker_step": int(release_marker),
        "dump_quality_window_len": int(end - start),
        "dump_quality_start_bucket_mass_kg": float(mass_start),
        "dump_quality_end_bucket_mass_kg": float(mass_end),
        "dump_quality_bucket_mass_loss_kg": float(bucket_mass_loss),
        "dump_quality_deposit_delta_kg": float(deposit_delta),
        "dump_quality_deposit_delta_for_accept_kg": float(deposit_delta_for_accept),
        "dump_quality_deposited_fraction_of_bucket_loss": float(deposited_fraction),
        "dump_quality_fraction_for_accept": float(fraction_for_accept),
        "dump_quality_hard_collision_delta_count": int(hard_collision_delta),
        "dump_quality_good_by_cycle_success": bool(good_by_cycle_success),
        "dump_quality_good_by_mass_fraction": bool(good_by_mass_fraction),
        "dump_quality_good_by_metadata": bool(good_by_metadata),
        "dump_quality_good_dump": bool(
            hard_collision_delta <= GOOD_DUMP_MAX_HARD_COLLISION_DELTA
            and (good_by_cycle_success or good_by_mass_fraction or good_by_metadata)
        ),
        "dump_quality_acceptance_source": acceptance_source,
        "dump_quality_min_bucket_mass_loss_kg": float(GOOD_DUMP_MIN_BUCKET_MASS_LOSS_KG),
        "dump_quality_min_deposit_delta_kg": float(GOOD_DUMP_MIN_DEPOSIT_DELTA_KG),
        "dump_quality_min_deposited_fraction_of_bucket_loss": float(
            GOOD_DUMP_MIN_DEPOSITED_FRACTION_OF_BUCKET_LOSS
        ),
        "dump_quality_release_min_height_above_rim_m": float(
            np.min(release_window[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX])
        ),
        "dump_quality_release_min_dump_area_footprint_outside_distance_m": float(
            np.min(
                release_window[
                    :,
                    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
                ]
            )
        ),
    }
    qc.update(cycle_qc)
    return qc


def _single_cycle_quality_qc(episode: dict[str, Any]) -> dict[str, Any]:
    cycle = dict(dict(episode.get("v2", {})).get("cycle", {}))
    if not cycle:
        return {}
    qc: dict[str, Any] = {}
    if "cycle_success" in cycle and len(cycle["cycle_success"]) > 0:
        qc["dump_quality_cycle_success"] = int(np.asarray(cycle["cycle_success"])[0])
    if "deposit_delta_kg" in cycle and len(cycle["deposit_delta_kg"]) > 0:
        qc["dump_quality_cycle_deposit_delta_kg"] = float(
            np.asarray(cycle["deposit_delta_kg"], dtype=np.float32)[0]
        )
    if "collision_count_delta" in cycle and len(cycle["collision_count_delta"]) > 0:
        qc["dump_quality_cycle_collision_delta_count"] = int(
            np.asarray(cycle["collision_count_delta"], dtype=np.int32)[0]
        )
    return qc


def _good_dump_quality_reject_reasons(qc: dict[str, Any]) -> list[str]:
    if bool(qc.get("dump_qc_missing_target_geometry", False)) or bool(
        qc.get("dump_quality_missing_target_geometry", False)
    ):
        return ["missing_target_geometry_for_good_dump_quality"]
    if bool(qc.get("dump_quality_invalid_window", False)):
        return ["invalid_good_dump_quality_window"]
    reasons: list[str] = []
    if (
        int(qc.get("dump_quality_hard_collision_delta_count", 0))
        > GOOD_DUMP_MAX_HARD_COLLISION_DELTA
    ):
        reasons.append("dump_quality_hard_collision")
    if not bool(qc.get("dump_quality_good_dump", False)):
        reasons.append("dump_quality_not_good_dump")
    return reasons


def _dump_qc_reject_reasons(qc: dict[str, Any]) -> list[str]:
    if bool(qc.get("dump_qc_missing_target_geometry", False)):
        return ["missing_target_geometry_for_dump_qc"]
    reasons: list[str] = []
    if (
        float(qc.get("dump_first20_min_height_above_rim_m", 0.0))
        < DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M
    ):
        reasons.append("dump_first20_height_below_rim")
    if (
        int(qc.get("dump_first20_clearance_loss_step", -1)) >= 0
        and float(qc.get("dump_first20_min_height_above_rim_m", 0.0))
        < DUMP_QC_MIN_FIRST_HEIGHT_ABOVE_RIM_M
    ):
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


def _iter_cycle_workskill_episodes_from_raw(
    *,
    episode: dict[str, Any],
    source_path: Path,
    source_dataset_dir: Path,
    rejects: list[PrimitiveRejectRecord] | None = None,
) -> list[dict[str, Any]]:
    windows = _raw_cycle_windows(episode=episode)
    if not windows:
        raise ValueError(
            f"Episode {source_path.name} has no usable V2 cycle windows for "
            "direct primitive splitting."
        )
    results: list[dict[str, Any]] = []
    source_episode_id = _source_episode_id(episode=episode, source_path=source_path)
    realign_steps = _metadata_pose_realign_steps(episode=episode)
    for cycle_id, start, end, realign_end in windows:
        overlap = _window_pose_realign_steps(
            realign_steps=realign_steps,
            start_step=start,
            end_step_exclusive=realign_end,
        )
        if overlap:
            if rejects is not None:
                rejects.append(
                    PrimitiveRejectRecord(
                        primitive_name="cycle",
                        reason=POSE_REALIGN_CYCLE_REJECT_REASON,
                        source_dataset_dir=str(source_dataset_dir.resolve()),
                        source_episode_id=int(source_episode_id),
                        source_cycle_id=int(cycle_id),
                        start_step=int(start),
                        end_step_exclusive=int(realign_end),
                        details={
                            "realign_steps_in_window": [int(step) for step in overlap],
                            "realign_all_steps": [
                                int(step) for step in realign_steps
                            ],
                            "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
                            "work_end_step_exclusive": int(end),
                            "realign_reject_end_step_exclusive": int(realign_end),
                            "policy": "discard_full_cycle_including_return",
                        },
                    )
                )
            continue
        cropped = _crop_episode_for_workskill_view(
            episode=episode,
            source_episode_id=source_episode_id,
            source_cycle_id=cycle_id,
            start=start,
            end=end,
            source_dataset_dir=source_dataset_dir,
            source_path=source_path,
        )
        results.append(
            {
                "episode": cropped,
                "source_path": source_path,
                "source_start_step": int(start),
                "source_end_step_exclusive": int(end),
                "source_cycle_id": int(cycle_id),
            }
        )
    return results


def _metadata_pose_realign_steps(*, episode: dict[str, Any]) -> tuple[int, ...]:
    metadata = dict(episode.get("metadata", {}) or {})
    raw_value = metadata.get(POSE_REALIGN_METADATA_KEY)
    if raw_value is None:
        return ()
    values: list[int] = []

    def _append_one(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        if isinstance(item, np.bytes_):
            item = item.astype(str)
        if isinstance(item, str):
            for part in item.replace(";", ",").split(","):
                text = part.strip()
                if not text:
                    continue
                values.append(int(float(text)))
            return
        if np.isscalar(item):
            values.append(int(item))
            return
        for nested in np.asarray(item).reshape(-1):
            _append_one(nested)

    _append_one(raw_value)
    return tuple(sorted({int(step) for step in values if int(step) >= 0}))


def _window_pose_realign_steps(
    *,
    realign_steps: tuple[int, ...],
    start_step: int,
    end_step_exclusive: int,
) -> tuple[int, ...]:
    start = int(start_step)
    end = int(end_step_exclusive)
    if end <= start or not realign_steps:
        return ()
    return tuple(int(step) for step in realign_steps if start <= int(step) < end)


def _transition_pose_realign_reject(
    *,
    episode: dict[str, Any],
    source_path: Path,
    source_dataset_dir: Path,
    transition_slice: Any,
) -> PrimitiveRejectRecord | None:
    start = int(transition_slice.dump_end_step)
    end = int(transition_slice.next_start_step)
    realign_steps = _metadata_pose_realign_steps(episode=episode)
    overlap = _window_pose_realign_steps(
        realign_steps=realign_steps,
        start_step=start,
        end_step_exclusive=end,
    )
    if not overlap:
        return None
    return PrimitiveRejectRecord(
        primitive_name="return",
        reason=POSE_REALIGN_TRANSITION_REJECT_REASON,
        source_dataset_dir=str(source_dataset_dir.resolve()),
        source_episode_id=_source_episode_id(episode=episode, source_path=source_path),
        source_cycle_id=int(transition_slice.prev_cycle_id),
        start_step=start,
        end_step_exclusive=end,
        details={
            "realign_steps_in_window": [int(step) for step in overlap],
            "realign_all_steps": [int(step) for step in realign_steps],
            "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
            "policy": "discard_return_transition_window",
            "next_cycle_id": int(transition_slice.next_cycle_id),
        },
    )


def _raw_cycle_windows(episode: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    """Return raw cycle windows for work crops plus full-cycle realign rejection.

    The work-skill crop ends at dump_end because dig/carry/dump must not swallow
    the return transition. Realign rejection is stricter: a cycle is unusable if
    the forced pose correction happens anywhere from dig start until return
    completion. The reject window is half-open at the next qualified-dig-start so
    a correction exactly on the next cycle's QDS belongs to that next cycle only.
    """

    actions = np.asarray(episode["actions"])
    n_steps = int(actions.shape[0])
    v2 = dict(episode.get("v2") or {})
    cycle = dict(v2.get("cycle", {}) or {})
    if "start_step" in cycle and ("end_step" in cycle or "dump_end_step" in cycle):
        starts = np.asarray(cycle["start_step"], dtype=np.int32).reshape(-1)
        dump_ends = (
            np.asarray(cycle["dump_end_step"], dtype=np.int32).reshape(-1)
            if "dump_end_step" in cycle
            else None
        )
        fallback_ends = (
            np.asarray(cycle["end_step"], dtype=np.int32).reshape(-1)
            if "end_step" in cycle
            else None
        )
        cycle_ids = np.asarray(
            cycle.get("cycle_id", np.arange(len(starts))), dtype=np.int32
        ).reshape(-1)
        windows: list[tuple[int, int, int, int]] = []
        for index, start_value in enumerate(starts):
            start = int(start_value)
            if start < 0 or start >= n_steps:
                continue
            work_end_inclusive: int | None = None
            if dump_ends is not None and index < len(dump_ends):
                candidate = int(dump_ends[index])
                if candidate >= start:
                    work_end_inclusive = candidate
            if (
                work_end_inclusive is None
                and dump_ends is None
                and fallback_ends is not None
                and index < len(fallback_ends)
            ):
                candidate = int(fallback_ends[index])
                if candidate >= start:
                    work_end_inclusive = candidate
            if work_end_inclusive is None:
                continue
            end = min(n_steps, work_end_inclusive + 1)
            if end <= start:
                continue
            realign_end = end
            if fallback_ends is not None and index < len(fallback_ends):
                candidate = int(fallback_ends[index])
                if candidate >= start:
                    realign_end = min(n_steps, max(realign_end, candidate))
            if index + 1 < len(starts):
                next_start = int(starts[index + 1])
                if next_start > start:
                    realign_end = min(n_steps, max(realign_end, next_start))
            cycle_id = int(cycle_ids[index]) if index < len(cycle_ids) else index
            windows.append((cycle_id, start, end, realign_end))
        if windows:
            return sorted(windows, key=lambda item: item[1])

    step = dict(v2.get("step", {}) or {})
    if "cycle_id" not in step:
        return []
    cycle_ids = np.asarray(step["cycle_id"], dtype=np.int32).reshape(-1)
    windows = []
    for cycle_id in sorted(int(item) for item in np.unique(cycle_ids) if int(item) >= 0):
        indices = np.flatnonzero(cycle_ids == cycle_id)
        if indices.size <= 0:
            continue
        start = int(indices[0])
        end = int(indices[-1]) + 1
        if end > start:
            windows.append((int(cycle_id), start, min(n_steps, end), min(n_steps, end)))
    return windows


def _crop_episode_for_workskill_view(
    *,
    episode: dict[str, Any],
    source_episode_id: int,
    source_cycle_id: int,
    start: int,
    end: int,
    source_dataset_dir: Path,
    source_path: Path,
) -> dict[str, Any]:
    crop = slice(int(start), int(end))
    metadata = dict(episode.get("metadata", {}) or {})
    metadata.update(
        {
            "recording_mode": "cell_entry_enriched_raw_cycle_view",
            "source_dataset_dir": str(source_dataset_dir.resolve()),
            "source_episode_path": str(source_path.resolve()),
            "source_episode_id": f"episode_{int(source_episode_id)}",
            "source_cycle_id": int(source_cycle_id),
            "source_start_step": int(start),
            "source_end_step_exclusive": int(end),
        }
    )
    v2 = dict(episode.get("v2") or {})
    step = {
        str(key): np.asarray(value[crop])
        for key, value in dict(v2.get("step", {}) or {}).items()
    }
    cycle = _select_cycle_payload_for_raw_window(
        cycle=dict(v2.get("cycle", {}) or {}),
        source_cycle_id=source_cycle_id,
        start_step=start,
    )
    images = {
        camera_name: np.asarray(camera_frames[crop])
        for camera_name, camera_frames in dict(episode.get("images", {})).items()
    }
    return {
        "qpos": np.asarray(episode["qpos"][crop], dtype=np.float32),
        "qvel": np.asarray(episode["qvel"][crop], dtype=np.float32),
        "actions": np.asarray(episode["actions"][crop], dtype=np.float32),
        "images": images,
        "rewards": _slice_optional_array(episode.get("rewards"), crop),
        "env_state": _slice_optional_array(episode.get("env_state"), crop),
        "step_ids": _slice_optional_array(episode.get("step_ids"), crop, dtype=np.int64),
        "step_ns": _slice_optional_array(episode.get("step_ns"), crop, dtype=np.int64),
        "action_src_types": _slice_optional_list(episode.get("action_src_types"), crop),
        "action_src_ids": _slice_optional_list(episode.get("action_src_ids"), crop),
        "v2": {"step": step, "cycle": cycle},
        "metadata": metadata,
    }


def _select_cycle_payload_for_raw_window(
    *,
    cycle: dict[str, Any],
    source_cycle_id: int,
    start_step: int,
) -> dict[str, np.ndarray]:
    if not cycle:
        return {}
    first_len = min(
        (len(np.asarray(value)) for value in cycle.values() if np.asarray(value).ndim > 0),
        default=0,
    )
    if first_len <= 0:
        return {}
    index = 0
    if "cycle_id" in cycle:
        cycle_ids = np.asarray(cycle["cycle_id"]).reshape(-1)
        matches = np.flatnonzero(cycle_ids.astype(np.int64) == int(source_cycle_id))
        if len(matches) > 0:
            index = int(matches[0])
    if "start_step" in cycle and index == 0:
        starts = np.asarray(cycle["start_step"]).reshape(-1)
        matches = np.flatnonzero(starts.astype(np.int64) == int(start_step))
        if len(matches) > 0:
            index = int(matches[0])
    payload: dict[str, np.ndarray] = {}
    for key, value in cycle.items():
        arr = np.asarray(value)
        if arr.ndim <= 0 or arr.shape[0] <= index:
            continue
        payload[str(key)] = np.asarray(arr[index : index + 1]).copy()
    return payload


def _primitive_window_manifest_entry(
    *,
    primitive_slice: PrimitiveSlice,
    source_episode: dict[str, Any],
    source_path: Path,
    target_path: Path,
    output_episode_id: int,
) -> dict[str, Any]:
    source_start_offset = _source_start_step_offset(episode=source_episode)
    start = int(source_start_offset + primitive_slice.start_step)
    end = int(source_start_offset + primitive_slice.end_step_exclusive)
    cycle_payload = _select_primitive_cycle_payload(
        source_episode=source_episode,
        source_cycle_id=int(primitive_slice.source_cycle_id),
        cycle_id_offset=0,
        zero_cycle_id=False,
    )
    cycle_attrs = _cycle_metadata_attrs(cycle_payload)
    return {
        "primitive_name": str(primitive_slice.primitive_name),
        "primitive_episode_id": int(output_episode_id),
        "primitive_window": str(primitive_slice.window_name),
        "source_episode_path": str(source_path.resolve()),
        "source_episode_id": f"episode_{primitive_slice.source_episode_id}",
        "source_cycle_id": int(primitive_slice.source_cycle_id),
        "source_start_step": int(start),
        "source_end_step_exclusive": int(end),
        "source_window_len": int(end - start),
        "output_episode_path": str(target_path),
        "boundary_profile": str(primitive_slice.boundary_profile or ""),
        "training_tier": str(cycle_attrs.get("training_tier", "silver")),
        "cycle_effective_deposit_delta_kg": cycle_attrs.get(
            "cycle_effective_deposit_delta_kg"
        ),
        "operator_cut_payload_gain_kg": cycle_attrs.get(
            "operator_cut_payload_gain_kg"
        ),
        "return_target_source": str(cycle_attrs.get("return_target_source", "")),
        "return_entry_delta_norm_m": cycle_attrs.get("return_entry_delta_norm_m"),
        "next_operator_entry_x_m": cycle_attrs.get("next_operator_entry_x_m"),
        "next_operator_entry_z_m": cycle_attrs.get("next_operator_entry_z_m"),
        "next_operator_exit_x_m": cycle_attrs.get("next_operator_exit_x_m"),
        "next_operator_exit_z_m": cycle_attrs.get("next_operator_exit_z_m"),
        "next_operator_cut_length_m": cycle_attrs.get("next_operator_cut_length_m"),
        "next_operator_cut_payload_gain_kg": cycle_attrs.get(
            "next_operator_cut_payload_gain_kg"
        ),
        "carry_qc": _json_safe_dict(dict(primitive_slice.carry_qc or {})),
        "dump_qc": _json_safe_dict(dict(primitive_slice.dump_qc or {})),
        "return_qc": _json_safe_dict(dict(primitive_slice.return_qc or {})),
        "v2_step_overlay_keys": sorted(
            str(key) for key in dict(primitive_slice.v2_step_overlay or {})
        ),
    }


def _build_summary(
    *,
    workskill_dir: Path | None,
    raw_dirs: list[Path],
    output_root: Path,
    counts: Counter[str],
    window_lengths: dict[str, list[int]],
    rejects: list[PrimitiveRejectRecord],
    return_max_transition_len: int | None,
    return_clean_profile: str | None,
    carry_qc_records: list[dict[str, Any]],
    dump_qc_records: list[dict[str, Any]],
    return_qc_records: list[dict[str, Any]] | None = None,
    training_tier_counts: Counter[str] | None = None,
    primitive_version: str = PRIMITIVE_VERSION,
    primitive_names: tuple[str, ...] = PRIMITIVE_NAMES,
    approach_qc_records: list[dict[str, Any]] | None = None,
    boundary_profile: str = PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    storage_mode: str = STORAGE_MODE_COPY,
    window_manifest_path: Path | None = None,
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
        "boundary_profile": str(boundary_profile),
        "storage_mode": str(storage_mode),
        "workskill_dir": (
            None if workskill_dir is None else str(workskill_dir.resolve())
        ),
        "raw_dirs": [str(path.resolve()) for path in raw_dirs],
        "output_root": str(output_root.resolve()),
        "window_manifest_path": (
            None if window_manifest_path is None else str(window_manifest_path)
        ),
        "primitive_names": list(primitive_names),
        "primitives": primitive_summary,
        "dump_intent_config": {
            "bucket_qpos_min": float(DUMP_INTENT_BUCKET_QPOS_MIN),
            "bucket_action_max": float(DUMP_INTENT_BUCKET_ACTION_MAX),
            "min_stable_steps": int(DUMP_INTENT_MIN_STABLE_STEPS),
            "min_bucket_mass_kg": float(DUMP_INTENT_MIN_BUCKET_MASS_KG),
            "min_height_above_rim_m": float(DUMP_INTENT_MIN_HEIGHT_ABOVE_RIM_M),
            "max_dump_area_footprint_outside_distance_m": float(
                DUMP_INTENT_MAX_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_M
            ),
            "requires_dump_area_geometry": True,
            "official_dump_start_fallback": False,
            "good_dump_quality_acceptance": True,
        },
        "good_dump_quality_acceptance_config": {
            "min_bucket_mass_loss_kg": float(GOOD_DUMP_MIN_BUCKET_MASS_LOSS_KG),
            "min_deposit_delta_kg": float(GOOD_DUMP_MIN_DEPOSIT_DELTA_KG),
            "min_deposited_fraction_of_bucket_loss": float(
                GOOD_DUMP_MIN_DEPOSITED_FRACTION_OF_BUCKET_LOSS
            ),
            "max_hard_collision_delta": int(GOOD_DUMP_MAX_HARD_COLLISION_DELTA),
            "accepts_cycle_success": True,
            "purpose": "allow no-crash, good-dump human entrances that miss the strict safe-intent pattern",
        },
        "dump_ownership_config": {
            "dump_window": DUMP_WINDOW_NAME,
            "carry_window": CARRY_WINDOW_NAME,
            "boundary_rule": "first approach_dump stage",
            "raw_direct_cycle_end_policy": (
                "prefer dump_end_step for dig/carry/dump crops; end_step may point "
                "to next qualified_dig_start and belongs to return"
            ),
            "raw_direct_realign_reject_policy": (
                "discard the full logical cycle from dig start through return "
                "completion when replay_pose_realign_steps overlaps"
            ),
            "pre_approach_release_policy": "shift boundary into dump if final dump quality is good; otherwise reject",
            "effect_release_fallback_enabled": bool(
                boundary_profile == PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK
            ),
            "carry_action_horizon_steps": int(CARRY_ACTION_HORIZON_STEPS),
            "curl_out_lookback_steps": int(CARRY_CURL_OUT_LOOKBACK_STEPS),
            "dump_owns": "target approach, alignment, release, and post-dump hold",
            "carry_owns": "safe loaded transport before target approach/alignment",
        },
        "carry_tail_config": {
            "action_horizon_steps": int(CARRY_ACTION_HORIZON_STEPS),
            "curl_out_lookback_steps": int(CARRY_CURL_OUT_LOOKBACK_STEPS),
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
        "return_qc": _build_return_qc_summary(list(return_qc_records or [])),
        "training_tier_counts": dict(
            sorted(dict(training_tier_counts or {}).items())
        ),
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
        "window_len": _numeric_stats(records, "carry_window_len"),
        "steps_before_release": _numeric_stats(records, "carry_steps_before_release"),
        "ownership_stable_curl_out_onset_step": _numeric_stats(
            records,
            "carry_dump_ownership_stable_curl_out_onset_step",
            ignore_negative=True,
        ),
        "ownership_boundary_source_counts": dict(
            sorted(
                Counter(
                    str(record.get("carry_dump_ownership_boundary_source", "unknown"))
                    for record in records
                ).items()
            )
        ),
        "acceptance_mode_counts": dict(
            sorted(
                Counter(
                    str(record.get("carry_dump_acceptance_mode", "safe_intent"))
                    for record in records
                ).items()
            )
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
        "tail_stable_release_count": int(
            sum(bool(record.get("carry_tail_has_stable_release", False)) for record in records)
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
            "first20_clearance_loss_rejected_only_below_height_tolerance": True,
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
        "start_dump_area_footprint_outside_distance_m": _numeric_stats(
            records,
            "dump_start_dump_area_footprint_outside_distance_m",
        ),
        "min_dump_area_footprint_outside_distance_m": _numeric_stats(
            records,
            "dump_min_dump_area_footprint_outside_distance_m",
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
        "acceptance_mode_counts": dict(
            sorted(
                Counter(
                    str(record.get("dump_acceptance_mode", "safe_intent"))
                    for record in records
                ).items()
            )
        ),
        "quality_acceptance_source_counts": dict(
            sorted(
                Counter(
                    str(record.get("dump_quality_acceptance_source", "strict_safe_intent"))
                    for record in records
                ).items()
            )
        ),
        "quality_deposit_delta_for_accept_kg": _numeric_stats(
            records,
            "dump_quality_deposit_delta_for_accept_kg",
        ),
        "quality_deposited_fraction_of_bucket_loss": _numeric_stats(
            records,
            "dump_quality_fraction_for_accept",
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


def _build_return_qc_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted_window_count": int(len(records)),
        "window_len": _numeric_stats(records, "return_window_len"),
        "envelope_valid_count": int(
            sum(bool(record.get("return_start_envelope_valid", False)) for record in records)
        ),
        "envelope_long_norm": _numeric_stats(
            records,
            "return_start_envelope_long_norm",
        ),
        "envelope_short_norm": _numeric_stats(
            records,
            "return_start_envelope_short_norm",
        ),
        "envelope_depth_center_m": _numeric_stats(
            records,
            "return_start_envelope_depth_center_m",
        ),
        "endpoint_qpos_half_width_max": _numeric_stats(
            records,
            "return_start_envelope_qpos_half_width_max",
        ),
        "terminal_reject_policy": "return requires a next material dig start",
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
        value = _jsonable(value)
        if isinstance(value, float) and not np.isfinite(value):
            continue
        if isinstance(value, (bool, int, float, str, list, dict)) or value is None:
            safe[str(key)] = value
    return safe


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
