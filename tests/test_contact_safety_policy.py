from __future__ import annotations

import pytest

from testbed.planner.box_emptying.contact_safety_policy import (
    CONTACT_SAFETY_ALLOW,
    CONTACT_SAFETY_HARD_FAIL,
    CONTACT_SAFETY_NO_CONTACT,
    ContactSafetyPolicy,
    ContactSafetyPolicyInputs,
)


def _evaluate(**overrides: object):
    values: dict[str, object] = {
        "contact_active": True,
        "components": ("bucket",),
        "forces_n": (1000.0, 1200.0),
        "telemetry_valid": True,
        "hard_bottom_violation": False,
        "stuck": False,
        "timed_out": False,
    }
    values.update(overrides)
    return ContactSafetyPolicy(high_force_n=100_000.0).evaluate(
        ContactSafetyPolicyInputs(**values)
    )


def test_no_contact_is_neutral() -> None:
    result = _evaluate(contact_active=False, components=(), forces_n=())

    assert result.kind == CONTACT_SAFETY_NO_CONTACT
    assert result.allowed is True
    assert result.hard_failure is False


def test_finite_bucket_only_contact_is_allowed() -> None:
    result = _evaluate()

    assert result.kind == CONTACT_SAFETY_ALLOW
    assert result.reason == "finite_bucket_only_contact"
    assert result.allowed is True
    assert result.hard_failure is False


@pytest.mark.parametrize("component", ["boom", "stick", "other", "unknown"])
def test_non_bucket_or_unknown_component_is_a_hard_failure(
    component: str,
) -> None:
    result = _evaluate(components=(component,))

    assert result.kind == CONTACT_SAFETY_HARD_FAIL
    assert result.reason == "forbidden_or_unknown_contact_component"
    assert result.allowed is False
    assert result.hard_failure is True


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"forces_n": (float("nan"),)}, "nonfinite_contact_telemetry"),
        ({"forces_n": (float("inf"),)}, "nonfinite_contact_telemetry"),
        ({"telemetry_valid": False}, "invalid_contact_telemetry"),
        ({"forces_n": (-1.0,)}, "invalid_contact_telemetry"),
        ({"forces_n": (100_000.0,)}, "high_force_contact"),
        ({"hard_bottom_violation": True}, "hard_bottom_violation"),
        ({"stuck": True}, "stuck"),
        ({"timed_out": True}, "timeout"),
    ],
)
def test_unsafe_contact_conditions_remain_hard_failures(
    overrides: dict[str, object],
    reason: str,
) -> None:
    result = _evaluate(**overrides)

    assert result.kind == CONTACT_SAFETY_HARD_FAIL
    assert result.reason == reason
    assert result.hard_failure is True


def test_policy_threshold_must_be_finite_positive_and_at_most_hard_limit() -> None:
    for invalid in (float("nan"), 0.0, -1.0, 100_001.0):
        with pytest.raises(ValueError, match="high_force_n"):
            ContactSafetyPolicy(high_force_n=invalid)

