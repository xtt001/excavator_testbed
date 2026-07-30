from __future__ import annotations

from dataclasses import replace
from typing import Any

from testbed.eval.goal_following_effect_gate import (
    CALIBRATION_STAGE_ORDER,
    CalibrationInterval,
    EffectCalibrationEvidence,
    EffectCalibrationSample,
    evaluate_effect_calibration_gate,
)


def _samples(capability: str = "shallow_cut") -> list[EffectCalibrationSample]:
    samples: list[EffectCalibrationSample] = []
    splits = (
        ("train_reset", "train", 14),
        ("calibration_reset", "calibration", 3),
        ("evaluation_reset", "evaluation", 3),
    )
    for reset_group_id, split, count in splits:
        for outcome in ("positive", "negative"):
            for index in range(count):
                sample_id = (
                    f"{capability}-{reset_group_id}-{outcome}-{index}"
                )
                samples.append(
                    EffectCalibrationSample(
                        sample_id=sample_id,
                        capability_class=capability,
                        reset_group_id=reset_group_id,
                        split=split,
                        outcome=outcome,
                        failed=outcome == "negative" and index % 2 == 0,
                        planned_cut={"depth_m": 0.1},
                        executed_cut={"depth_m": 0.09},
                        effect={"removed_volume_m3": 0.04},
                    )
                )
    return samples


def _evidence(
    samples: list[EffectCalibrationSample],
    capability: str = "shallow_cut",
) -> EffectCalibrationEvidence:
    return EffectCalibrationEvidence(
        capability_class=capability,
        retained_sample_ids=tuple(
            sample.sample_id
            for sample in samples
            if sample.capability_class == capability
        ),
        stage_order=CALIBRATION_STAGE_ORDER,
        planned_to_executed_interval=CalibrationInterval(
            lower=-0.02,
            upper=0.02,
            coverage_level=0.95,
            calibrated=True,
        ),
        executed_to_effect_interval=CalibrationInterval(
            lower=-0.01,
            upper=0.03,
            coverage_level=0.95,
            calibrated=True,
        ),
    )


def test_effect_gate_accepts_supported_two_stage_calibration() -> None:
    samples = _samples()
    result = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )

    assert result.passed
    assert result.reasons == ()
    assert result.capabilities[0].positive_count == 20
    assert result.capabilities[0].negative_count == 20
    assert result.capabilities[0].failed_negative_count == 11
    assert result.capabilities[0].reset_group_count == 3
    assert result.capabilities[0].retained_sample_count == 40


def test_effect_gate_fails_closed_when_support_is_too_small() -> None:
    samples = _samples()[:-1]
    result = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )

    assert not result.passed
    assert "shallow_cut:negative_support_below_20" in result.reasons


def test_effect_gate_rejects_reset_group_leakage_between_splits() -> None:
    samples = _samples()
    samples[-1] = replace(
        samples[-1],
        reset_group_id="train_reset",
        split="evaluation",
    )
    result = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )

    assert not result.passed
    assert "reset_group_split_leakage:train_reset" in result.reasons


def test_effect_gate_requires_every_negative_and_failure_to_be_retained() -> None:
    samples = _samples()
    evidence = _evidence(samples)
    dropped_ids = evidence.retained_sample_ids[:-1]
    result = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[replace(evidence, retained_sample_ids=dropped_ids)],
    )

    assert not result.passed
    assert "shallow_cut:sample_retention_mismatch" in result.reasons


def test_effect_gate_requires_ordered_calibrated_intervals() -> None:
    samples = _samples()
    evidence = _evidence(samples)
    wrong_order = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[
            replace(
                evidence,
                stage_order=tuple(reversed(CALIBRATION_STAGE_ORDER)),
            )
        ],
    )
    assert not wrong_order.passed
    assert "shallow_cut:calibration_stage_order_invalid" in wrong_order.reasons

    missing_interval = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[
            replace(evidence, planned_to_executed_interval=None)
        ],
    )
    assert not missing_interval.passed
    assert (
        "shallow_cut:planned_to_executed_interval_missing"
        in missing_interval.reasons
    )


def test_effect_gate_rejects_forbidden_shortcuts_recursively() -> None:
    samples = _samples()
    samples[0] = replace(
        samples[0],
        planned_cut={
            "depth_m": 0.1,
            "metadata": {"hindsight_target_depth_m": 0.09},
        },
    )
    hindsight = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )
    assert not hindsight.passed
    assert "shallow_cut:forbidden_field:hindsight_target_depth_m" in (
        hindsight.reasons
    )

    samples = _samples()
    samples[0] = replace(
        samples[0],
        planned_cut={"fixed_expert_median": 0.12},
    )
    expert_median = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )
    assert not expert_median.passed
    assert "shallow_cut:forbidden_field:fixed_expert_median" in (
        expert_median.reasons
    )

    samples = _samples()
    samples[0] = replace(
        samples[0],
        planned_cut={"temporary_cell_binding": 7},
    )
    temporary_cell = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )
    assert not temporary_cell.passed
    assert "shallow_cut:forbidden_field:temporary_cell_binding" in (
        temporary_cell.reasons
    )


def test_effect_gate_fails_closed_for_malformed_payload_or_interval() -> None:
    samples = _samples()
    malformed_payload: Any = None
    samples[0] = replace(samples[0], planned_cut=malformed_payload)
    malformed = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )
    assert not malformed.passed
    assert "shallow_cut:planned_cut_mapping_invalid" in malformed.reasons

    samples = _samples()
    evidence = _evidence(samples)
    malformed_number: Any = "not-a-number"
    invalid_interval = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[
            replace(
                evidence,
                executed_to_effect_interval=replace(
                    evidence.executed_to_effect_interval,
                    lower=malformed_number,
                ),
            )
        ],
    )
    assert not invalid_interval.passed
    assert (
        "shallow_cut:executed_to_effect_interval_nonfinite"
        in invalid_interval.reasons
    )


def test_effect_gate_requires_strict_bool_for_failed_and_calibrated() -> None:
    samples = _samples()
    malformed_bool: Any = 1
    samples[0] = replace(samples[0], failed=malformed_bool)
    malformed_failed = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[_evidence(samples)],
    )
    assert not malformed_failed.passed
    assert "shallow_cut:failed_type_invalid" in malformed_failed.reasons

    samples = _samples()
    evidence = _evidence(samples)
    malformed_calibrated = evaluate_effect_calibration_gate(
        samples=samples,
        evidence=[
            replace(
                evidence,
                planned_to_executed_interval=replace(
                    evidence.planned_to_executed_interval,
                    calibrated=malformed_bool,
                ),
            )
        ],
    )
    assert not malformed_calibrated.passed
    assert (
        "shallow_cut:planned_to_executed_calibrated_type_invalid"
        in malformed_calibrated.reasons
    )
