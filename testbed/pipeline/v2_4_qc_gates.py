"""V2.4 primitive-VDS numeric QC gates used by the hindsight pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import math
import time

import h5py
import numpy as np

from testbed.contracts.primitive_profile import (
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)
from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_START_ENVELOPE_VALID_MASK_KEY,
    primitive_token_dataset_path,
)


DEFAULT_RETURN_MAX_TRANSITION_LEN = 512
DEFAULT_DEPTH_TOKEN_MAX_SATURATION = 0.02
DEFAULT_DEPTH_TOKEN_MIN_P90_P10 = 0.05
DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC = 0.90
DEFAULT_DEPTH_SOURCE_MIN_FRACTION = 0.95
DEFAULT_REQUIRED_DEPTH_SOURCE = "env_state_surface_penetration"
DEFAULT_RETURN_MIN_DIG_RATIO = 0.75
DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO = 0.10
DEFAULT_DUMP_MAX_LEN = 768
DEFAULT_DUMP_MAX_P95_LEN = 640
DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC = 0.0
DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG = 5.0
DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC = 0.10
DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS = 120
DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION = 0.95


@dataclass(frozen=True)
class PrimitiveVdsQCGateConfig:
    skip_pre_materialize_qc: bool = False
    depth_token_max_saturation: float = DEFAULT_DEPTH_TOKEN_MAX_SATURATION
    depth_token_min_p90_p10: float = DEFAULT_DEPTH_TOKEN_MIN_P90_P10
    depth_token_min_nonzero_frac: float = DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC
    depth_source_min_fraction: float = DEFAULT_DEPTH_SOURCE_MIN_FRACTION
    required_depth_outcome_source: str = DEFAULT_REQUIRED_DEPTH_SOURCE
    return_max_transition_len: int | None = DEFAULT_RETURN_MAX_TRANSITION_LEN
    return_min_dig_ratio: float = DEFAULT_RETURN_MIN_DIG_RATIO
    return_max_overlong_reject_ratio: float = DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO
    dump_max_len: int = DEFAULT_DUMP_MAX_LEN
    dump_max_p95_len: int = DEFAULT_DUMP_MAX_P95_LEN
    dump_max_transition_mode_frac: float = DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC
    carry_max_deposit_delta_kg: float = DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG
    carry_max_deposit_to_payload_loss_frac: float = (
        DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
    )
    dump_max_pre_release_lead_steps: int = DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS
    return_envelope_min_valid_fraction: float = (
        DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION
    )
    boundary_profile: str = PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK

    @classmethod
    def from_namespace(cls, args: Any) -> "PrimitiveVdsQCGateConfig":
        return cls(
            skip_pre_materialize_qc=bool(
                getattr(args, "skip_pre_materialize_qc", False)
            ),
            depth_token_max_saturation=float(args.depth_token_max_saturation),
            depth_token_min_p90_p10=float(args.depth_token_min_p90_p10),
            depth_token_min_nonzero_frac=float(args.depth_token_min_nonzero_frac),
            depth_source_min_fraction=float(args.depth_source_min_fraction),
            required_depth_outcome_source=str(args.required_depth_outcome_source),
            return_max_transition_len=(
                None
                if args.return_max_transition_len is None
                else int(args.return_max_transition_len)
            ),
            return_min_dig_ratio=float(args.return_min_dig_ratio),
            return_max_overlong_reject_ratio=float(
                args.return_max_overlong_reject_ratio
            ),
            dump_max_len=int(args.dump_max_len),
            dump_max_p95_len=int(args.dump_max_p95_len),
            dump_max_transition_mode_frac=float(args.dump_max_transition_mode_frac),
            carry_max_deposit_delta_kg=float(args.carry_max_deposit_delta_kg),
            carry_max_deposit_to_payload_loss_frac=float(
                args.carry_max_deposit_to_payload_loss_frac
            ),
            dump_max_pre_release_lead_steps=int(args.dump_max_pre_release_lead_steps),
            return_envelope_min_valid_fraction=float(
                args.return_envelope_min_valid_fraction
            ),
            boundary_profile=str(args.boundary_profile),
        )


def build_primitive_vds_qc_gate(
    primitive_vds_root: Path,
    *,
    config: PrimitiveVdsQCGateConfig,
) -> dict[str, Any]:
    primitive_vds_root = Path(primitive_vds_root)
    if bool(config.skip_pre_materialize_qc):
        return {
            "root": str(primitive_vds_root),
            "passed": True,
            "skipped": True,
            "reason": "--skip-pre-materialize-qc",
        }

    payload: dict[str, Any] = {
        "root": str(primitive_vds_root),
        "passed": True,
        "failed_checks": [],
        "thresholds": {
            "depth_token_max_saturation": float(config.depth_token_max_saturation),
            "depth_token_min_p90_p10": float(config.depth_token_min_p90_p10),
            "depth_token_min_nonzero_frac": float(
                config.depth_token_min_nonzero_frac
            ),
            "depth_source_min_fraction": float(config.depth_source_min_fraction),
            "required_depth_outcome_source": str(
                config.required_depth_outcome_source
            ),
            "return_max_transition_len": (
                None
                if config.return_max_transition_len is None
                else int(config.return_max_transition_len)
            ),
            "return_min_dig_ratio": float(config.return_min_dig_ratio),
            "return_max_overlong_reject_ratio": float(
                config.return_max_overlong_reject_ratio
            ),
            "dump_max_len": int(config.dump_max_len),
            "dump_max_p95_len": int(config.dump_max_p95_len),
            "dump_max_transition_mode_frac": float(
                config.dump_max_transition_mode_frac
            ),
            "carry_max_deposit_delta_kg": float(config.carry_max_deposit_delta_kg),
            "carry_max_deposit_to_payload_loss_frac": float(
                config.carry_max_deposit_to_payload_loss_frac
            ),
            "dump_max_pre_release_lead_steps": int(
                config.dump_max_pre_release_lead_steps
            ),
            "return_envelope_min_valid_fraction": float(
                config.return_envelope_min_valid_fraction
            ),
        },
        "primitives": {},
    }

    def fail(message: str) -> None:
        payload["passed"] = False
        payload["failed_checks"].append(message)

    for primitive in ("dig", "carry", "dump", "return"):
        episodes = _episode_files(primitive_vds_root / primitive)
        payload["primitives"][primitive] = {"episode_count": len(episodes)}
    if payload["primitives"]["dig"]["episode_count"] <= 0:
        fail("no dig primitive episodes")
    if payload["primitives"]["dump"]["episode_count"] <= 0:
        fail("no dump primitive episodes")
    if payload["primitives"]["return"]["episode_count"] <= 0:
        fail("no return primitive episodes")

    _append_dig_qc(payload, primitive_vds_root, config, fail)
    _append_dump_qc(payload, primitive_vds_root, config, fail)
    _append_carry_qc(payload, primitive_vds_root, config, fail)
    _append_return_qc(payload, primitive_vds_root, config, fail)

    payload["feedback_gate"] = build_feedback_gate_payload(
        gate="gate1_primitive_vds_numeric_qc",
        passed=bool(payload.get("passed", False)),
        failed_checks=list(payload.get("failed_checks", []) or []),
        current_result={
            "root": str(primitive_vds_root),
            "primitives": payload.get("primitives", {}),
            "thresholds": payload.get("thresholds", {}),
        },
        next_step=(
            "continue_to_gate2_boundary_visual_review"
            if bool(payload.get("passed", False))
            else "pause_before_materialize_and_fix_builder_or_thresholds"
        ),
    )
    return payload


def build_feedback_gate_payload(
    *,
    gate: str,
    passed: bool,
    failed_checks: list[Any],
    current_result: dict[str, Any],
    next_step: str,
) -> dict[str, Any]:
    failed = [str(item) for item in failed_checks]
    return {
        "gate": str(gate),
        "status": "pass" if bool(passed) else "pause",
        "passed": bool(passed),
        "current_result": current_result,
        "deviation_from_expected": failed,
        "decision": "continue" if bool(passed) else "pause",
        "next_step": str(next_step),
        "review_required": not bool(passed),
        "written_at": _now(),
    }


def _append_dig_qc(
    payload: dict[str, Any],
    primitive_vds_root: Path,
    config: PrimitiveVdsQCGateConfig,
    fail,
) -> None:
    dig_depth_tokens: list[float] = []
    dig_depth_outcomes: list[float] = []
    dig_raw_depth_m: list[float] = []
    gold_depth_tokens: list[float] = []
    gold_depth_outcomes: list[float] = []
    gold_raw_depth_m: list[float] = []
    source_counts: dict[str, int] = {}
    gold_source_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    contract_versions: dict[str, int] = {}
    depth_scales: dict[str, int] = {}

    for path in _episode_files(primitive_vds_root / "dig"):
        with h5py.File(path, "r") as handle:
            tier = _h5_training_tier(handle)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            source = _h5_depth_source(handle)
            source_counts[source] = source_counts.get(source, 0) + 1
            if tier == "gold":
                gold_source_counts[source] = gold_source_counts.get(source, 0) + 1

            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            contract = _h5_text(metadata.get("dig_cut_token_contract_version", ""))
            if contract:
                contract_versions[contract] = contract_versions.get(contract, 0) + 1
            if "dig_cut_depth_scale_m" in metadata:
                scale = f"{float(metadata['dig_cut_depth_scale_m']):.6g}"
                depth_scales[scale] = depth_scales.get(scale, 0) + 1

            token_depth = _h5_step_value(handle, "v2/step/dig_cut_tokens", col=7)
            if token_depth is not None:
                dig_depth_tokens.append(token_depth)
                if tier == "gold":
                    gold_depth_tokens.append(token_depth)
            outcome_depth = _h5_step_value(
                handle,
                "v2/step/dig_outcome_targets",
                col=7,
            )
            if outcome_depth is not None:
                dig_depth_outcomes.append(outcome_depth)
                if tier == "gold":
                    gold_depth_outcomes.append(outcome_depth)
            raw_depth = _h5_cycle_depth_m(handle)
            if raw_depth is not None:
                dig_raw_depth_m.append(raw_depth)
                if tier == "gold":
                    gold_raw_depth_m.append(raw_depth)

    dig_payload = payload["primitives"]["dig"]
    dig_payload["training_tier_counts"] = tier_counts
    dig_payload["dig_cut_depth_source_counts"] = source_counts
    dig_payload["gold_dig_cut_depth_source_counts"] = gold_source_counts
    dig_payload["depth_outcome_source_counts"] = source_counts
    dig_payload["gold_depth_outcome_source_counts"] = gold_source_counts
    dig_payload["dig_cut_token_contract_versions"] = contract_versions
    dig_payload["dig_cut_depth_scales_m"] = depth_scales
    dig_payload["token_depth_dim7_stats"] = _numeric_stats(dig_depth_tokens)
    dig_payload["gold_token_depth_dim7_stats"] = _numeric_stats(gold_depth_tokens)
    dig_payload["outcome_depth_dim7_stats"] = _numeric_stats(dig_depth_outcomes)
    dig_payload["gold_outcome_depth_dim7_stats"] = _numeric_stats(gold_depth_outcomes)
    dig_payload["raw_removed_depth_max_delta_m_stats"] = _numeric_stats(dig_raw_depth_m)
    dig_payload["gold_raw_removed_depth_max_delta_m_stats"] = _numeric_stats(
        gold_raw_depth_m
    )

    gold_count = int(sum(gold_source_counts.values()))
    reliable_gold = int(
        gold_source_counts.get(str(config.required_depth_outcome_source), 0)
    )
    source_fraction = float(reliable_gold / gold_count) if gold_count > 0 else 0.0
    dig_payload["gold_required_depth_source_fraction"] = source_fraction
    if gold_count <= 0:
        fail("no gold dig episodes for token/depth QC")
    elif source_fraction < float(config.depth_source_min_fraction):
        fail(
            "gold reliable depth source fraction "
            f"{source_fraction:.4f} < {float(config.depth_source_min_fraction):.4f}"
        )

    gold_stats = dig_payload["gold_token_depth_dim7_stats"]
    if gold_stats is None:
        fail("missing gold dig depth tokens")
    else:
        saturation = float(gold_stats["saturation_ge_0_999"])
        spread = float(gold_stats["p90"] - gold_stats["p10"])
        nonzero = float(gold_stats["nonzero_gt_1e_6"])
        if saturation > float(config.depth_token_max_saturation):
            fail(
                "gold depth token saturation "
                f"{saturation:.4f} > {float(config.depth_token_max_saturation):.4f}"
            )
        if spread < float(config.depth_token_min_p90_p10):
            fail(
                "gold depth token p90-p10 spread "
                f"{spread:.4f} < {float(config.depth_token_min_p90_p10):.4f}"
            )
        if nonzero < float(config.depth_token_min_nonzero_frac):
            fail(
                "gold depth token nonzero fraction "
                f"{nonzero:.4f} < {float(config.depth_token_min_nonzero_frac):.4f}"
            )


def _append_dump_qc(
    payload: dict[str, Any],
    primitive_vds_root: Path,
    config: PrimitiveVdsQCGateConfig,
    fail,
) -> None:
    from testbed.data.v2_1 import PHASE_NAME_TO_ID
    from testbed.planner.boundary_detector import MODE_TRANSITION

    transition_phase_ids = {
        int(PHASE_NAME_TO_ID["transition_corridor"]),
        int(PHASE_NAME_TO_ID["transition_wait_next_dig"]),
    }
    dump_lengths: list[int] = []
    dump_transition_fracs: list[float] = []
    for path in _episode_files(primitive_vds_root / "dump"):
        with h5py.File(path, "r") as handle:
            length = _h5_action_len(handle)
            dump_lengths.append(length)
            transition_mask = np.zeros(length, dtype=bool)
            mode_id = _h5_1d_array(handle, "v2/step/mode_id")
            if mode_id is not None and mode_id.size == length:
                transition_mask |= mode_id.astype(np.int64) == int(MODE_TRANSITION)
            phase_id = _h5_1d_array(handle, "v2/step/phase_id")
            if phase_id is not None and phase_id.size == length:
                transition_mask |= np.isin(
                    phase_id.astype(np.int64),
                    np.asarray(sorted(transition_phase_ids), dtype=np.int64),
                )
            dump_transition_fracs.append(
                float(np.mean(transition_mask)) if length > 0 else 0.0
            )
    dump_payload = payload["primitives"]["dump"]
    dump_payload["length_stats"] = _numeric_stats(dump_lengths)
    dump_payload["transition_mode_or_phase_frac_stats"] = _numeric_stats(
        dump_transition_fracs
    )
    dump_payload["transition_contaminated_episode_count"] = int(
        sum(value > 0.0 for value in dump_transition_fracs)
    )
    dump_stats = dump_payload["length_stats"]
    if dump_stats is not None:
        dump_max = int(dump_stats["max"])
        dump_p95 = float(dump_stats["p95"])
        if dump_max > int(config.dump_max_len):
            fail(f"dump max length {dump_max} > {int(config.dump_max_len)}")
        if dump_p95 > float(config.dump_max_p95_len):
            fail(
                "dump p95 length "
                f"{dump_p95:.1f} > {float(config.dump_max_p95_len):.1f}"
            )
    dump_transition_stats = dump_payload["transition_mode_or_phase_frac_stats"]
    if dump_transition_stats is not None:
        dump_transition_max = float(dump_transition_stats["max"])
        if dump_transition_max > float(config.dump_max_transition_mode_frac):
            fail(
                "dump transition-mode/phase fraction "
                f"{dump_transition_max:.4f} > "
                f"{float(config.dump_max_transition_mode_frac):.4f}"
            )

    dump_leads: list[float] = []
    for path in _episode_files(primitive_vds_root / "dump"):
        with h5py.File(path, "r") as handle:
            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            if "dump_pre_release_lead_steps" in metadata:
                dump_leads.append(float(metadata["dump_pre_release_lead_steps"]))
    dump_payload["pre_release_lead_steps_stats"] = _numeric_stats(dump_leads)
    if dump_leads and max(dump_leads) > int(config.dump_max_pre_release_lead_steps):
        fail(
            "dump pre-release lead max "
            f"{max(dump_leads):.0f} > {int(config.dump_max_pre_release_lead_steps)}"
        )


def _append_carry_qc(
    payload: dict[str, Any],
    primitive_vds_root: Path,
    config: PrimitiveVdsQCGateConfig,
    fail,
) -> None:
    carry_deposit_delta: list[float] = []
    carry_deposit_ratio: list[float] = []
    for path in _episode_files(primitive_vds_root / "carry"):
        with h5py.File(path, "r") as handle:
            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            if "carry_deposit_delta_kg" in metadata:
                carry_deposit_delta.append(float(metadata["carry_deposit_delta_kg"]))
            if "carry_deposit_to_payload_loss_frac" in metadata:
                carry_deposit_ratio.append(
                    float(metadata["carry_deposit_to_payload_loss_frac"])
                )
    carry_payload = payload["primitives"]["carry"]
    carry_payload["deposit_delta_kg_stats"] = _numeric_stats(carry_deposit_delta)
    carry_payload["deposit_to_payload_loss_frac_stats"] = _numeric_stats(
        carry_deposit_ratio
    )
    carry_bad_count = 0
    for delta, ratio in zip(carry_deposit_delta, carry_deposit_ratio):
        if (
            float(delta) > float(config.carry_max_deposit_delta_kg)
            and float(ratio) > float(config.carry_max_deposit_to_payload_loss_frac)
        ):
            carry_bad_count += 1
    carry_payload["deposit_contaminated_episode_count"] = int(carry_bad_count)
    if carry_bad_count > 0:
        fail(f"carry deposit contamination count {carry_bad_count} > 0")


def _append_return_qc(
    payload: dict[str, Any],
    primitive_vds_root: Path,
    config: PrimitiveVdsQCGateConfig,
    fail,
) -> None:
    return_lengths: list[int] = []
    return_tiers: dict[str, int] = {}
    return_envelope_valid: list[float] = []
    return_envelope_full_mask_valid: list[float] = []
    for path in _episode_files(primitive_vds_root / "return"):
        with h5py.File(path, "r") as handle:
            return_lengths.append(_h5_action_len(handle))
            tier = _h5_training_tier(handle)
            return_tiers[tier] = return_tiers.get(tier, 0) + 1
            token = _h5_1d_or_2d_array(
                handle,
                primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY),
            )
            mask = _h5_1d_or_2d_array(
                handle,
                primitive_token_dataset_path(RETURN_START_ENVELOPE_VALID_MASK_KEY),
            )
            if token is not None and token.size > 0:
                token_arr = np.asarray(token, dtype=np.float32)
                if (
                    token_arr.ndim == 2
                    and token_arr.shape[1] > RETURN_ENVELOPE_QPOS_VALID_IDX
                ):
                    return_envelope_valid.append(
                        float(
                            np.mean(
                                token_arr[:, RETURN_ENVELOPE_QPOS_VALID_IDX] > 0.5
                            )
                        )
                    )
                elif (
                    token_arr.ndim == 1
                    and token_arr.shape[0] > RETURN_ENVELOPE_QPOS_VALID_IDX
                ):
                    return_envelope_valid.append(
                        float(token_arr[RETURN_ENVELOPE_QPOS_VALID_IDX] > 0.5)
                    )
            if mask is not None and mask.size > 0:
                mask_arr = np.asarray(mask)
                return_envelope_full_mask_valid.append(float(np.mean(mask_arr > 0.5)))
                if token is None:
                    if (
                        mask_arr.ndim == 2
                        and mask_arr.shape[1] > RETURN_ENVELOPE_QPOS_VALID_IDX
                    ):
                        return_envelope_valid.append(
                            float(
                                np.mean(
                                    mask_arr[:, RETURN_ENVELOPE_QPOS_VALID_IDX] > 0.5
                                )
                            )
                        )
                    elif (
                        mask_arr.ndim == 1
                        and mask_arr.shape[0] > RETURN_ENVELOPE_QPOS_VALID_IDX
                    ):
                        return_envelope_valid.append(
                            float(mask_arr[RETURN_ENVELOPE_QPOS_VALID_IDX] > 0.5)
                        )
    return_payload = payload["primitives"]["return"]
    return_payload["length_stats"] = _numeric_stats(return_lengths)
    return_payload["training_tier_counts"] = return_tiers
    return_payload["return_start_envelope_valid_fraction_stats"] = _numeric_stats(
        return_envelope_valid
    )
    return_payload["return_start_envelope_full_mask_fraction_stats"] = _numeric_stats(
        return_envelope_full_mask_valid
    )
    if return_envelope_valid:
        valid_fraction = float(np.mean(np.asarray(return_envelope_valid) >= 1.0))
        return_payload["return_start_envelope_episode_valid_fraction"] = valid_fraction
        if valid_fraction < float(config.return_envelope_min_valid_fraction):
            fail(
                "return envelope valid episode fraction "
                f"{valid_fraction:.4f} < {float(config.return_envelope_min_valid_fraction):.4f}"
            )
    elif str(config.boundary_profile) == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS:
        fail("missing return_start_envelope_valid_mask in return episodes")
    dig_count = int(payload["primitives"]["dig"]["episode_count"])
    return_count = int(return_payload["episode_count"])
    return_ratio = float(return_count / dig_count) if dig_count > 0 else 0.0
    return_payload["return_to_dig_episode_ratio"] = return_ratio
    if dig_count > 0 and return_ratio < float(config.return_min_dig_ratio):
        fail(
            "return/dig episode ratio "
            f"{return_ratio:.4f} < {float(config.return_min_dig_ratio):.4f}"
        )
    if return_lengths and config.return_max_transition_len is not None:
        max_len = int(max(return_lengths))
        limit = int(config.return_max_transition_len)
        return_payload["max_len"] = max_len
        if max_len > limit:
            fail(f"return max length {max_len} > {limit}")

    summary_path = primitive_vds_root / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reject_counts = dict(summary.get("reject_counts", {}) or {})
        return_payload["reject_counts"] = {
            key: int(value)
            for key, value in reject_counts.items()
            if str(key).startswith("return:")
        }
        overlong = int(reject_counts.get("return:overlong_transition_len", 0))
        pose_realign = int(
            reject_counts.get("return:return_window_contains_pose_realign", 0)
        )
        candidate_count = int(return_count + overlong + pose_realign)
        overlong_ratio = (
            float(overlong / candidate_count) if candidate_count > 0 else 0.0
        )
        return_payload["return_candidate_count"] = candidate_count
        return_payload["overlong_reject_ratio"] = overlong_ratio
        if overlong_ratio > float(config.return_max_overlong_reject_ratio):
            fail(
                "return overlong reject ratio "
                f"{overlong_ratio:.4f} > "
                f"{float(config.return_max_overlong_reject_ratio):.4f}"
            )
    else:
        return_payload["summary_json"] = "missing"


def _episode_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        path.glob("episode_*.hdf5"),
        key=lambda item: int(item.stem.split("_")[-1]),
    )


def _h5_training_tier(handle: Any) -> str:
    metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
    tier = _h5_text(metadata.get("training_tier", ""))
    if tier:
        return tier
    if "v2/cycle/training_tier" in handle:
        data = handle["v2/cycle/training_tier"]
        if data.shape[0] > 0:
            return _h5_text(data[0])
    return ""


def _h5_depth_source(handle: Any) -> str:
    metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
    source = _h5_text(metadata.get("operator_cut_depth_source", ""))
    if source:
        return source
    source = _h5_text(metadata.get("depth_outcome_source", ""))
    if source:
        return source
    if "v2/cycle/operator_cut_depth_source" in handle:
        data = handle["v2/cycle/operator_cut_depth_source"]
        if data.shape[0] > 0:
            return _h5_text(data[0])
    if "v2/cycle/depth_outcome_source" in handle:
        data = handle["v2/cycle/depth_outcome_source"]
        if data.shape[0] > 0:
            return _h5_text(data[0])
    return ""


def _h5_step_value(handle: Any, dataset_path: str, *, col: int) -> float | None:
    if dataset_path not in handle:
        return None
    data = handle[dataset_path]
    if data.ndim != 2 or data.shape[0] <= 0 or data.shape[1] <= col:
        return None
    value = float(data[0, col])
    return value if _finite(value) else None


def _h5_cycle_depth_m(handle: Any) -> float | None:
    if "v2/cycle/actual_removed_depth_delta_grid" not in handle:
        return None
    data = handle["v2/cycle/actual_removed_depth_delta_grid"]
    if data.shape[0] <= 0:
        return None
    value = float(np.max(np.asarray(data[0], dtype=np.float32)))
    return value if _finite(value) else None


def _h5_action_len(handle: Any) -> int:
    if "actions" in handle:
        return int(handle["actions"].shape[0])
    if "action" in handle:
        return int(handle["action"].shape[0])
    if "observations/qpos" in handle:
        return int(handle["observations/qpos"].shape[0])
    raise KeyError("episode is missing actions/action/observations/qpos")


def _h5_1d_array(handle: Any, dataset_path: str) -> Any | None:
    if dataset_path not in handle:
        return None
    data = np.asarray(handle[dataset_path])
    if data.ndim <= 0:
        return None
    return data.reshape(-1)


def _h5_1d_or_2d_array(handle: Any, dataset_path: str) -> Any | None:
    if dataset_path not in handle:
        return None
    data = np.asarray(handle[dataset_path])
    if data.ndim <= 0:
        return None
    return data


def _h5_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return _h5_text(value.item())
        except ValueError:
            pass
    return str(value)


def _numeric_stats(values: Iterable[float | int]) -> dict[str, Any] | None:
    arr = np.asarray(list(values), dtype=np.float32).reshape(-1)
    if arr.size <= 0:
        return None
    finite = arr[np.isfinite(arr)]
    if finite.size <= 0:
        return None
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p50": float(np.percentile(finite, 50)),
        "p90": float(np.percentile(finite, 90)),
        "p95": float(np.percentile(finite, 95)),
        "p98": float(np.percentile(finite, 98)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "saturation_ge_0_999": float(np.mean(finite >= 0.999)),
        "nonzero_gt_1e_6": float(np.mean(np.abs(finite) > 1.0e-6)),
    }


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
