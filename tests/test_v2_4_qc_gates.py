from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import h5py
import numpy as np

from testbed.cli.build_v2_4_hindsight_pipeline import (
    DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG,
    DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC,
    DEFAULT_DEPTH_SOURCE_MIN_FRACTION,
    DEFAULT_DEPTH_TOKEN_MAX_SATURATION,
    DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC,
    DEFAULT_DEPTH_TOKEN_MIN_P90_P10,
    DEFAULT_DUMP_MAX_LEN,
    DEFAULT_DUMP_MAX_P95_LEN,
    DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS,
    DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC,
    DEFAULT_REQUIRED_DEPTH_SOURCE,
    DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION,
    DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO,
    DEFAULT_RETURN_MAX_TRANSITION_LEN,
    DEFAULT_RETURN_MIN_DIG_RATIO,
    V2_4_5_BOUNDARY_PROFILE,
    _run_pre_materialize_qc,
)
from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_START_ENVELOPE_VALID_MASK_KEY,
    primitive_token_dataset_path,
)
from testbed.pipeline.v2_4_qc_gates import (
    PrimitiveVdsQCGateConfig,
    build_feedback_gate_payload,
    build_primitive_vds_qc_gate,
)


def test_primitive_vds_qc_gate_passes_valid_synthetic_root(tmp_path: Path) -> None:
    root = _write_valid_primitive_root(tmp_path / "primitive_vds")
    config = PrimitiveVdsQCGateConfig(boundary_profile=V2_4_5_BOUNDARY_PROFILE)

    payload = build_primitive_vds_qc_gate(root, config=config)

    assert payload["passed"] is True
    assert payload["failed_checks"] == []
    assert payload["primitives"]["dig"]["episode_count"] == 4
    assert payload["primitives"]["carry"]["episode_count"] == 1
    assert payload["primitives"]["dump"]["episode_count"] == 1
    assert payload["primitives"]["return"]["episode_count"] == 3
    assert payload["primitives"]["dig"]["gold_required_depth_source_fraction"] == 1.0
    assert payload["primitives"]["dig"]["gold_token_depth_dim7_stats"]["count"] == 4
    assert payload["primitives"]["return"]["return_start_envelope_episode_valid_fraction"] == 1.0
    assert payload["feedback_gate"]["gate"] == "gate1_primitive_vds_numeric_qc"
    assert payload["feedback_gate"]["decision"] == "continue"


def test_primitive_vds_qc_gate_skip_payload_preserves_legacy_shape(
    tmp_path: Path,
) -> None:
    payload = build_primitive_vds_qc_gate(
        tmp_path / "missing",
        config=PrimitiveVdsQCGateConfig(skip_pre_materialize_qc=True),
    )

    assert payload == {
        "root": str(tmp_path / "missing"),
        "passed": True,
        "skipped": True,
        "reason": "--skip-pre-materialize-qc",
    }


def test_primitive_vds_qc_gate_reports_numeric_failures(tmp_path: Path) -> None:
    root = _write_bad_primitive_root(tmp_path / "primitive_vds_bad")
    config = PrimitiveVdsQCGateConfig(
        boundary_profile=V2_4_5_BOUNDARY_PROFILE,
        dump_max_len=2,
        dump_max_p95_len=2,
        carry_max_deposit_delta_kg=1.0,
        carry_max_deposit_to_payload_loss_frac=0.1,
        dump_max_pre_release_lead_steps=1,
        return_max_transition_len=2,
    )

    payload = build_primitive_vds_qc_gate(root, config=config)

    assert payload["passed"] is False
    failed = "\n".join(payload["failed_checks"])
    assert "gold reliable depth source fraction 0.0000 < 0.9500" in failed
    assert "gold depth token saturation 1.0000 > 0.0200" in failed
    assert "gold depth token p90-p10 spread 0.0000 < 0.0500" in failed
    assert "dump max length 10 > 2" in failed
    assert "dump pre-release lead max 5 > 1" in failed
    assert "carry deposit contamination count 1 > 0" in failed
    assert "missing return_start_envelope_valid_mask in return episodes" in failed
    assert "return/dig episode ratio 0.2500 < 0.7500" in failed
    assert "return max length 10 > 2" in failed
    assert payload["feedback_gate"]["decision"] == "pause"
    assert payload["feedback_gate"]["review_required"] is True


def test_cli_pre_materialize_qc_facade_matches_pipeline_gate(
    tmp_path: Path,
) -> None:
    root = _write_valid_primitive_root(tmp_path / "primitive_vds")
    args = _default_qc_args()

    facade_payload = _run_pre_materialize_qc(root, args=args)
    direct_payload = build_primitive_vds_qc_gate(
        root,
        config=PrimitiveVdsQCGateConfig.from_namespace(args),
    )

    assert _without_written_at(facade_payload) == _without_written_at(direct_payload)


def test_feedback_gate_payload_preserves_pipeline_gate_fields() -> None:
    payload = build_feedback_gate_payload(
        gate="unit_gate",
        passed=False,
        failed_checks=["bad"],
        current_result={"x": 1},
        next_step="fix_it",
    )

    assert payload["gate"] == "unit_gate"
    assert payload["status"] == "pause"
    assert payload["passed"] is False
    assert payload["current_result"] == {"x": 1}
    assert payload["deviation_from_expected"] == ["bad"]
    assert payload["decision"] == "pause"
    assert payload["next_step"] == "fix_it"
    assert payload["review_required"] is True
    assert isinstance(payload["written_at"], str)


def _default_qc_args(**overrides) -> argparse.Namespace:
    values = {
        "skip_pre_materialize_qc": False,
        "depth_token_max_saturation": DEFAULT_DEPTH_TOKEN_MAX_SATURATION,
        "depth_token_min_p90_p10": DEFAULT_DEPTH_TOKEN_MIN_P90_P10,
        "depth_token_min_nonzero_frac": DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC,
        "depth_source_min_fraction": DEFAULT_DEPTH_SOURCE_MIN_FRACTION,
        "required_depth_outcome_source": DEFAULT_REQUIRED_DEPTH_SOURCE,
        "return_max_transition_len": DEFAULT_RETURN_MAX_TRANSITION_LEN,
        "return_min_dig_ratio": DEFAULT_RETURN_MIN_DIG_RATIO,
        "return_max_overlong_reject_ratio": DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO,
        "dump_max_len": DEFAULT_DUMP_MAX_LEN,
        "dump_max_p95_len": DEFAULT_DUMP_MAX_P95_LEN,
        "dump_max_transition_mode_frac": DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC,
        "carry_max_deposit_delta_kg": DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG,
        "carry_max_deposit_to_payload_loss_frac": (
            DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
        ),
        "dump_max_pre_release_lead_steps": DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS,
        "return_envelope_min_valid_fraction": (
            DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION
        ),
        "boundary_profile": V2_4_5_BOUNDARY_PROFILE,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _write_valid_primitive_root(root: Path) -> Path:
    for index, depth in enumerate((0.10, 0.20, 0.30, 0.40)):
        _write_dig_episode(
            root / "dig" / f"episode_{index}.hdf5",
            depth=depth,
            source=DEFAULT_REQUIRED_DEPTH_SOURCE,
            tier="gold",
        )
    _write_carry_episode(root / "carry" / "episode_0.hdf5", delta=1.0, ratio=0.01)
    _write_dump_episode(root / "dump" / "episode_0.hdf5", length=8, pre_release_lead=1)
    for index in range(3):
        _write_return_episode(
            root / "return" / f"episode_{index}.hdf5",
            length=8,
            include_envelope=True,
        )
    root.mkdir(parents=True, exist_ok=True)
    (root / "summary.json").write_text(json.dumps({"reject_counts": {}}), encoding="utf-8")
    return root


def _write_bad_primitive_root(root: Path) -> Path:
    for index in range(4):
        _write_dig_episode(
            root / "dig" / f"episode_{index}.hdf5",
            depth=1.0,
            source="legacy_fallback",
            tier="gold",
        )
    _write_carry_episode(root / "carry" / "episode_0.hdf5", delta=10.0, ratio=0.5)
    _write_dump_episode(root / "dump" / "episode_0.hdf5", length=10, pre_release_lead=5)
    _write_return_episode(
        root / "return" / "episode_0.hdf5",
        length=10,
        include_envelope=False,
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "summary.json").write_text(json.dumps({"reject_counts": {}}), encoding="utf-8")
    return root


def _write_dig_episode(path: Path, *, depth: float, source: str, tier: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        _write_actions(handle, length=8)
        metadata = handle.create_group("metadata")
        metadata.attrs["training_tier"] = tier
        metadata.attrs["operator_cut_depth_source"] = source
        metadata.attrs["dig_cut_token_contract_version"] = "unit"
        metadata.attrs["dig_cut_depth_scale_m"] = 1.0
        step = handle.require_group("v2/step")
        token = np.zeros((1, 10), dtype=np.float32)
        token[0, 7] = float(depth)
        step.create_dataset("dig_cut_tokens", data=token)
        step.create_dataset("dig_outcome_targets", data=token)
        cycle = handle.require_group("v2/cycle")
        cycle.create_dataset(
            "actual_removed_depth_delta_grid",
            data=np.asarray([[float(depth), 0.0]], dtype=np.float32),
        )


def _write_carry_episode(path: Path, *, delta: float, ratio: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        _write_actions(handle, length=8)
        metadata = handle.create_group("metadata")
        metadata.attrs["carry_deposit_delta_kg"] = float(delta)
        metadata.attrs["carry_deposit_to_payload_loss_frac"] = float(ratio)


def _write_dump_episode(path: Path, *, length: int, pre_release_lead: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        _write_actions(handle, length=length)
        metadata = handle.create_group("metadata")
        metadata.attrs["dump_pre_release_lead_steps"] = int(pre_release_lead)


def _write_return_episode(path: Path, *, length: int, include_envelope: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        _write_actions(handle, length=length)
        metadata = handle.create_group("metadata")
        metadata.attrs["training_tier"] = "gold"
        if include_envelope:
            step = handle.require_group("v2/step")
            token = np.zeros((length, 18), dtype=np.float32)
            token[:, RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
            mask = np.ones((length, 18), dtype=np.float32)
            step.create_dataset(
                Path(primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY)).name,
                data=token,
            )
            step.create_dataset(
                Path(
                    primitive_token_dataset_path(
                        RETURN_START_ENVELOPE_VALID_MASK_KEY
                    )
                ).name,
                data=mask,
            )


def _write_actions(handle: h5py.File, *, length: int) -> None:
    handle.create_dataset("actions", data=np.zeros((length, 4), dtype=np.float32))


def _without_written_at(payload: dict) -> dict:
    cleaned = deepcopy(payload)
    if "feedback_gate" in cleaned:
        cleaned["feedback_gate"]["written_at"] = "<time>"
    return cleaned
