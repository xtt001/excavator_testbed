from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.planner.primitive.effects.carry_start_envelope import (
    CARRY_START_ENVELOPE_FEATURE_ORDER,
    CarryStartEnvelopeGate,
    CarryStartEnvelopeGateConfig,
)
from testbed.planner.primitive.facts.capabilities import DigTransitionStatus


def _artifact(path: Path, *, train_sources: list[int] | None = None) -> str:
    payload = {
        "schema": "carry_start_envelope_v1",
        "feature_order": list(CARRY_START_ENVELOPE_FEATURE_ORDER),
        "feature_sources": [
            {"dataset": "synthetic", "index": index}
            for index in range(len(CARRY_START_ENVELOPE_FEATURE_ORDER))
        ],
        "sample_count": 374,
        "percentiles": {
            "p01": [-1.0] * len(CARRY_START_ENVELOPE_FEATURE_ORDER),
            "p50": [0.0] * len(CARRY_START_ENVELOPE_FEATURE_ORDER),
            "p99": [1.0] * len(CARRY_START_ENVELOPE_FEATURE_ORDER),
        },
        "source_lineage": {
            "partition": "train",
            "split_path": "/strict18/splits/carry_train.txt",
            "split_policy": "source_episode_grouped",
            "dataset_dir": "/strict18/primitives_copy/carry",
            "train_primitive_episode_ids": list(range(374)),
            "train_source_episode_ids": train_sources
            or [3, 6, 7, 8, 9, 13, 16, 19, 23, 24, 25, 27, 28, 29, 30, 32],
            "validation_source_episode_ids": [33, 34],
            "source_episode_id_by_primitive_episode_id": {},
        },
        "split_sha256": "0" * 64,
        "input_sha256_contract": "test",
        "input_sha256": "1" * 64,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _obs(*, qpos0: float = 0.0) -> dict[str, object]:
    env_state = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    return {
        "qpos": np.asarray([qpos0, 0.0, 0.0, 0.0], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
    }


def _status(*, step: int = 10, ready: bool = True) -> DigTransitionStatus:
    return DigTransitionStatus(
        dig_step_count=step,
        mass_in_bucket_kg=45.0,
        min_distance_to_dig_area_m=0.0,
        transition_mass_in_bucket_kg=45.0,
        transition_min_distance_to_dig_area_m=0.0,
        distance_ready=True,
        semantic_boundary_profile_active=True,
        coverage_terminal_stop_requested=False,
        dig_complete_boundary=False,
        dig_complete_boundary_low_payload=False,
        dig_bad_replan_ready=False,
        dig_exit_guard_ready=False,
        dig_mass_plateau_ready=False,
        dig_to_carry_ready=ready,
        dig_to_carry_reason="semantic_material_loaded" if ready else "",
    )


def _gate(tmp_path: Path, **overrides: object) -> CarryStartEnvelopeGate:
    path = tmp_path / "carry_start_envelope.json"
    digest = _artifact(path)
    values = {
        "enabled": True,
        "artifact_path": str(path),
        "artifact_sha256": digest,
        "hold_steps": 3,
        "max_dig_steps": 500,
    }
    values.update(overrides)
    return CarryStartEnvelopeGate.from_config(
        CarryStartEnvelopeGateConfig(**values)
    )


def test_base_handoff_requires_three_consecutive_envelope_steps(
    tmp_path: Path,
) -> None:
    gate = _gate(tmp_path)

    first = gate.apply(_obs(), _status(step=10))
    second = gate.apply(_obs(), _status(step=11))
    third = gate.apply(_obs(), _status(step=12))

    assert first.dig_to_carry_ready is False
    assert second.dig_to_carry_ready is False
    assert third.dig_to_carry_ready is True
    assert third.dig_to_carry_reason == "semantic_material_loaded"
    debug = gate.debug_fields()
    assert debug["carry_start_base_ready"] is True
    assert debug["carry_start_envelope_ready"] is True
    assert debug["carry_start_envelope_hold_count"] == 3
    assert debug["carry_start_envelope_violations"] == []
    assert debug["carry_start_envelope_artifact_sha256"] != ""


def test_any_feature_violation_resets_hold_and_is_reported(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.apply(_obs(), _status(step=1))
    gate.apply(_obs(), _status(step=2))

    blocked = gate.apply(_obs(qpos0=1.01), _status(step=3))

    assert blocked.dig_to_carry_ready is False
    debug = gate.debug_fields()
    assert debug["carry_start_envelope_hold_count"] == 0
    assert debug["carry_start_envelope_ready"] is False
    assert debug["carry_start_envelope_violations"] == ["qpos[0]:above_p99"]


def test_low_payload_boundary_remains_visible_while_carry_ready_is_gated(
    tmp_path: Path,
) -> None:
    gate = _gate(tmp_path)
    status = replace(
        _status(step=1),
        dig_complete_boundary=True,
        dig_complete_boundary_low_payload=True,
        dig_to_carry_reason="dig_complete_boundary",
    )

    gated = gate.apply(_obs(), status)

    assert gated.dig_complete_boundary_low_payload is True
    assert gated.dig_to_carry_ready is False


def test_500_step_envelope_timeout_latches_without_hidden_handoff(
    tmp_path: Path,
) -> None:
    gate = _gate(tmp_path)

    gated = gate.apply(_obs(qpos0=2.0), _status(step=500))

    assert gated.dig_to_carry_ready is False
    assert gate.timeout_requested() is True
    assert gate.debug_fields()["carry_start_envelope_timeout"] is True


def test_gate_reset_clears_hold_timeout_and_diagnostics(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.apply(_obs(qpos0=2.0), _status(step=500))

    gate.reset()

    assert gate.timeout_requested() is False
    debug = gate.debug_fields()
    assert debug["carry_start_envelope_hold_count"] == 0
    assert debug["carry_start_envelope_timeout"] is False


def test_loader_rejects_sha_mismatch_and_validation_source_leakage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.json"
    _artifact(path)
    with pytest.raises(ValueError, match="sha256"):
        CarryStartEnvelopeGate.from_config(
            CarryStartEnvelopeGateConfig(
                enabled=True,
                artifact_path=str(path),
                artifact_sha256="f" * 64,
            )
        )

    _artifact(path, train_sources=[3, 33])
    with pytest.raises(ValueError, match="validation_source"):
        CarryStartEnvelopeGate.from_config(
            CarryStartEnvelopeGateConfig(
                enabled=True,
                artifact_path=str(path),
                artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
