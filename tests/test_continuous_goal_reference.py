from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from testbed.data.continuous_goal_qpos_paths import (
    PATH_PROGRESS,
    qpos_path_sha256,
)
from testbed.data.schema import ENV_STATE_ORDER_V2_3
from testbed.data.terrain_signature import build_terrain_signature_v1
from testbed.eval.continuous_goal_uncertainty_sweep import (
    REQUIRED_WITNESS_KEYS,
    evaluate_continuous_goal_uncertainty_sweep,
)
from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCutGoal,
)
from testbed.planner.primitive.coverage.continuous_goal_reference import (
    CONTINUOUS_GOAL_QPOS_PREDICTOR_V2_MISSING,
    predict_continuous_goal_reference,
)


def _goal() -> ContinuousCutGoal:
    return ContinuousCutGoal.create(
        target_cell_id=2,
        entry_xz_m=(0.2, 0.4),
        exit_xz_m=(0.5, 0.8),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent={"kind": "remove_soil", "target_mass_kg": 45.0},
        terrain_signature={"schema": "terrain_signature_v1"},
    )


def _terrain():
    return build_terrain_signature_v1(
        {name: float(index) / 100.0 for index, name in enumerate(ENV_STATE_ORDER_V2_3)}
    )


def _expected_lineage() -> dict[str, str]:
    return {
        "normalization_sha256": "a" * 64,
        "checkpoint_sha256": "b" * 64,
        "calibration_sha256": "c" * 64,
        "predictor_code_sha256": "d" * 64,
    }


@dataclass(frozen=True)
class _Prediction:
    status: str
    blockers: tuple[str, ...]
    support_status: str
    ood_score: float
    path_progress: np.ndarray
    qpos_path: np.ndarray
    qpos_abs_error_bound: np.ndarray
    coverage_level: float
    normalization_lineage_sha256: str
    checkpoint_lineage_sha256: str
    calibration_lineage_sha256: str
    goal_lineage_sha256: str
    predictor_code_lineage_sha256: str
    path_lineage_sha256: str
    input_lineage_sha256: str

    @property
    def inference_allowed(self) -> bool:
        return self.status == "passed" and not self.blockers


class _Predictor:
    def __init__(self, *, blocked: bool = False, path_sha_drift: bool = False):
        self.blocked = blocked
        self.path_sha_drift = path_sha_drift
        self.received = None

    def predict(self, sweep_input, *, expected_lineage=None):
        self.received = (sweep_input, expected_lineage)
        qpos_path = np.tile(
            np.asarray(sweep_input.handoff_qpos, dtype=np.float64),
            (64, 1),
        )
        if self.blocked:
            return _Prediction(
                status="blocked",
                blockers=("ood",),
                support_status="ood",
                ood_score=2.0,
                path_progress=PATH_PROGRESS,
                qpos_path=qpos_path,
                qpos_abs_error_bound=np.full((64, 4), 0.01),
                coverage_level=0.95,
                normalization_lineage_sha256="a" * 64,
                checkpoint_lineage_sha256="b" * 64,
                calibration_lineage_sha256="c" * 64,
                goal_lineage_sha256=sweep_input.goal_sha256,
                predictor_code_lineage_sha256="d" * 64,
                path_lineage_sha256=qpos_path_sha256(qpos_path),
                input_lineage_sha256=sweep_input.input_sha256,
            )
        return _Prediction(
            status="passed",
            blockers=(),
            support_status="supported",
            ood_score=0.1,
            path_progress=PATH_PROGRESS,
            qpos_path=qpos_path,
            qpos_abs_error_bound=np.full((64, 4), 0.01),
            coverage_level=0.95,
            normalization_lineage_sha256="a" * 64,
            checkpoint_lineage_sha256="b" * 64,
            calibration_lineage_sha256="c" * 64,
            goal_lineage_sha256=sweep_input.goal_sha256,
            predictor_code_lineage_sha256="d" * 64,
            path_lineage_sha256=(
                "e" * 64 if self.path_sha_drift else qpos_path_sha256(qpos_path)
            ),
            input_lineage_sha256=sweep_input.input_sha256,
        )


def test_v2_reference_builds_complete_input_and_preserves_uncertainty() -> None:
    predictor = _Predictor()
    live = {
        "qpos": [0.1, 0.2, 0.3, 0.4],
        "qvel": [0.0, 0.01, 0.02, 0.03],
    }

    result = predict_continuous_goal_reference(
        predictor=predictor,
        live_handoff_state=live,
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage=_expected_lineage(),
    )

    assert result.status == "passed"
    assert result.inference_allowed
    assert result.reference is not None
    assert result.reference.qpos_path.shape == (64, 4)
    assert result.reference.qpos_abs_error_bound.shape == (64, 4)
    assert result.reference.coverage_level == 0.95
    assert result.reference.qpos_path[0] == pytest.approx(live["qpos"])
    assert result.reference.path_progress.tolist() == PATH_PROGRESS.tolist()
    request, lineage = predictor.received
    assert request.schema == "continuous_goal_worktool_sweep_input_v2"
    assert request.terrain_signature.shape == (89,)
    assert request.continuous_goal["goal_id"] == _goal().goal_id
    assert lineage == _expected_lineage()


def test_v2_reference_blocks_missing_provider_or_predictor_ood() -> None:
    kwargs = {
        "live_handoff_state": {
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        "goal": _goal(),
        "terrain_signature": _terrain(),
        "expected_lineage": _expected_lineage(),
    }
    missing = predict_continuous_goal_reference(predictor=None, **kwargs)
    assert missing.status == "blocked"
    assert missing.blocker == CONTINUOUS_GOAL_QPOS_PREDICTOR_V2_MISSING
    assert not missing.inference_allowed

    ood = predict_continuous_goal_reference(
        predictor=_Predictor(blocked=True),
        **kwargs,
    )
    assert ood.status == "blocked"
    assert ood.blocker == "predictor_blocked:ood"
    assert not ood.inference_allowed


def test_v2_reference_fails_closed_on_output_lineage_drift() -> None:
    result = predict_continuous_goal_reference(
        predictor=_Predictor(path_sha_drift=True),
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage=_expected_lineage(),
    )

    assert result.status == "blocked"
    assert result.blocker == "predictor_output_invalid:path_lineage_mismatch"
    assert not result.inference_allowed


def test_v2_reference_rejects_malformed_expected_lineage_without_calling_live() -> None:
    result = predict_continuous_goal_reference(
        predictor=_Predictor(),
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage="not-a-mapping",  # type: ignore[arg-type]
    )

    assert result.status == "blocked"
    assert result.blocker == "expected_lineage_invalid"
    assert not result.inference_allowed


@pytest.mark.parametrize(
    "lineage",
    [
        None,
        {},
        {"checkpoint_sha256": "b" * 64},
        {
            **_expected_lineage(),
            "goal_sha256": "e" * 64,
        },
    ],
)
def test_v2_reference_requires_exact_static_lineage_inventory(lineage) -> None:
    result = predict_continuous_goal_reference(
        predictor=_Predictor(),
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage=lineage,
    )

    assert result.status == "blocked"
    assert result.blocker == "expected_lineage_incomplete"
    assert not result.inference_allowed


def test_v2_reference_fails_closed_on_malformed_prediction_contract() -> None:
    class MalformedPredictor:
        def predict(self, _sweep_input, *, expected_lineage=None):
            del expected_lineage

            class MalformedPrediction:
                status = "passed"
                inference_allowed = True
                blockers = None

            return MalformedPrediction()

    result = predict_continuous_goal_reference(
        predictor=MalformedPredictor(),
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage=_expected_lineage(),
    )

    assert result.status == "blocked"
    assert result.blocker == "predictor_output_contract_invalid"
    assert not result.inference_allowed


def test_validated_reference_feeds_the_independent_uncertainty_sweep() -> None:
    result = predict_continuous_goal_reference(
        predictor=_Predictor(),
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.01, 0.02, 0.03],
        },
        goal=_goal(),
        terrain_signature=_terrain(),
        expected_lineage=_expected_lineage(),
    )
    assert result.reference is not None

    sweep = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=result.reference.qpos_path,
        qpos_abs_error_bound=result.reference.qpos_abs_error_bound,
        witness_callback=lambda _qpos, _context: {
            key: 0.31 for key in REQUIRED_WITNESS_KEYS
        },
    )

    assert sweep.passed
    assert sweep.conservative_clearance_m == pytest.approx(0.25)
