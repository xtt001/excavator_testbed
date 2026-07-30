from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.eval.act_regression_diagnosis import (
    ActRegressionDiagnosisError,
    build_act_regression_module_diagnosis,
    write_act_regression_module_diagnosis,
)


def _repeat(
    repeat_id: str,
    *,
    initial_state_valid: bool = True,
    wall: bool = False,
    timeout: bool = False,
    envelope_ready: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "repeat_id": repeat_id,
        "initial_state_valid": initial_state_valid,
    }
    if initial_state_valid:
        result.update(
            {
                "wall_contact_count": int(wall),
                "timeout_count": int(timeout),
                "envelope_ready": envelope_ready,
            }
        )
    return result


def _group(
    condition_id: str,
    *,
    wall_count: int,
    timeout_count: int = 0,
    envelope_ready_count: int = 0,
) -> list[dict[str, object]]:
    return [
        _repeat(
            f"{condition_id.lower()}-{index}",
            wall=index < wall_count,
            timeout=index < timeout_count,
            envelope_ready=index < envelope_ready_count,
        )
        for index in range(3)
    ]


def _conditions(
    *,
    f0_wall: int = 2,
    d1_wall: int = 3,
    d1_envelope: int = 0,
    c1_wall: int = 3,
    c1_timeout: int = 0,
    c1_envelope: int = 0,
    dc1_wall: int = 3,
    dc1_envelope: int = 0,
) -> dict[str, list[dict[str, object]]]:
    return {
        "F0": _group("F0", wall_count=f0_wall),
        "D1": _group(
            "D1",
            wall_count=d1_wall,
            envelope_ready_count=d1_envelope,
        ),
        "C1": _group(
            "C1",
            wall_count=c1_wall,
            timeout_count=c1_timeout,
            envelope_ready_count=c1_envelope,
        ),
        "DC1": _group(
            "DC1",
            wall_count=dc1_wall,
            envelope_ready_count=dc1_envelope,
        ),
    }


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        (
            {"d1_wall": 0, "d1_envelope": 2},
            "planned_depth_primary",
        ),
        (
            {"c1_wall": 0, "c1_envelope": 2},
            "corridor_geometry_primary",
        ),
        (
            {
                "d1_wall": 0,
                "d1_envelope": 2,
                "c1_wall": 0,
                "c1_envelope": 2,
            },
            "multiple_primary",
        ),
        (
            {"dc1_wall": 0, "dc1_envelope": 2},
            "depth_corridor_interaction",
        ),
        (
            {"c1_wall": 0, "c1_timeout": 3},
            "corridor_wall_cause_with_envelope_bottleneck",
        ),
        (
            {
                "c1_wall": 0,
                "c1_timeout": 3,
                "dc1_wall": 0,
                "dc1_envelope": 3,
            },
            "corridor_wall_cause_with_envelope_bottleneck",
        ),
        (
            {"f0_wall": 3},
            "all_variants_wall_requires_policy_or_upstream_diagnosis",
        ),
        (
            {"f0_wall": 1, "d1_wall": 0, "d1_envelope": 3},
            "fixed_plan_not_reproduced",
        ),
    ],
)
def test_classifier_applies_locked_four_condition_rules(
    updates: dict[str, int],
    expected: str,
) -> None:
    result = build_act_regression_module_diagnosis(
        experiment_id="strict18-a0-module-isolation",
        conditions=_conditions(**updates),
    )

    assert result["schema"] == "act_regression_module_diagnosis_v1"
    assert result["status"] == "classified"
    assert result["root_cause_classification"]["category"] == expected
    assert result["f0_reproducibility"]["wall_contact_repeat_count"] >= (
        2 if expected != "fixed_plan_not_reproduced" else 0
    )
    assert result["f0_reproducibility"]["native_a0_control_required"] is (
        expected == "fixed_plan_not_reproduced"
    )


def test_invalid_initial_state_attempts_are_counted_but_not_classified() -> None:
    conditions = _conditions(d1_wall=0, d1_envelope=2)
    conditions["F0"].insert(
        0,
        _repeat("f0-invalid", initial_state_valid=False),
    )

    result = build_act_regression_module_diagnosis(
        experiment_id="invalid-attempt-accounting",
        conditions=conditions,
    )

    assert result["status"] == "classified"
    assert result["initial_state_validity"] == {
        "attempted_repeat_count": 13,
        "valid_repeat_count": 12,
        "invalid_repeat_count": 1,
        "required_valid_repeat_count": 12,
        "by_condition": {
            "F0": {
                "attempted_repeat_count": 4,
                "valid_repeat_count": 3,
                "invalid_repeat_count": 1,
            },
            "D1": {
                "attempted_repeat_count": 3,
                "valid_repeat_count": 3,
                "invalid_repeat_count": 0,
            },
            "C1": {
                "attempted_repeat_count": 3,
                "valid_repeat_count": 3,
                "invalid_repeat_count": 0,
            },
            "DC1": {
                "attempted_repeat_count": 3,
                "valid_repeat_count": 3,
                "invalid_repeat_count": 0,
            },
        },
    }
    assert result["conditions"]["F0"]["wall_contact_repeat_count"] == 2
    assert result["root_cause_classification"]["category"] == (
        "planned_depth_primary"
    )


def test_classifier_refuses_to_decide_without_exactly_three_valid_repeats() -> None:
    conditions = _conditions()
    conditions["DC1"][-1]["initial_state_valid"] = False

    result = build_act_regression_module_diagnosis(
        experiment_id="incomplete-condition",
        conditions=conditions,
    )

    assert result["status"] == "incomplete_valid_repeats"
    assert result["root_cause_classification"] == {
        "category": "not_classified",
        "primary_modules": [],
        "native_a0_control_required": False,
    }
    assert result["validation_errors"] == [
        "DC1:exactly_3_valid_repeats_required:got_2"
    ]
    assert result["initial_state_validity"]["invalid_repeat_count"] == 1


def test_classifier_preserves_live_probe_safety_evidence() -> None:
    conditions = _conditions(c1_wall=0, c1_envelope=3)
    conditions["C1"][0].update(
        {
            "bottom_contact_count": 0,
            "stuck_count": 0,
            "trigger_kind": "envelope_ready",
            "neutral_acknowledged": True,
            "terminal_requested": True,
            "zero_action_after_trigger": True,
            "artifact": {"run_dir": "/tmp/c1"},
        }
    )

    result = build_act_regression_module_diagnosis(
        experiment_id="preserve-live-evidence",
        conditions=conditions,
    )

    repeat = result["conditions"]["C1"]["repeats"][0]
    assert repeat["trigger_kind"] == "envelope_ready"
    assert repeat["neutral_acknowledged"] is True
    assert repeat["terminal_requested"] is True
    assert repeat["zero_action_after_trigger"] is True
    assert repeat["artifact"] == {"run_dir": "/tmp/c1"}


def test_writer_is_no_overwrite_and_preserves_machine_readable_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "diagnosis.json"
    result = write_act_regression_module_diagnosis(
        experiment_id="diagnostic-write",
        conditions=_conditions(dc1_wall=0, dc1_envelope=3),
        output_path=output_path,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == result
    with pytest.raises(FileExistsError, match="already exists"):
        write_act_regression_module_diagnosis(
            experiment_id="diagnostic-write",
            conditions=_conditions(),
            output_path=output_path,
        )


def test_classifier_rejects_missing_condition_or_duplicate_repeat_id() -> None:
    conditions = _conditions()
    del conditions["DC1"]
    with pytest.raises(
        ActRegressionDiagnosisError,
        match="condition_ids_must_be_exactly",
    ):
        build_act_regression_module_diagnosis(
            experiment_id="missing-condition",
            conditions=conditions,
        )

    conditions = _conditions()
    conditions["D1"][1]["repeat_id"] = conditions["D1"][0]["repeat_id"]
    with pytest.raises(
        ActRegressionDiagnosisError,
        match="duplicate_repeat_id",
    ):
        build_act_regression_module_diagnosis(
            experiment_id="duplicate-repeat",
            conditions=conditions,
        )
