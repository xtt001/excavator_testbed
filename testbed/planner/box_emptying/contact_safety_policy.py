"""Component-aware contact safety policy for mainline execution."""

from __future__ import annotations

import math
from dataclasses import dataclass

CONTACT_SAFETY_NO_CONTACT = "no_contact"
CONTACT_SAFETY_ALLOW = "allow"
CONTACT_SAFETY_HARD_FAIL = "hard_fail"
CONTACT_HARD_FORCE_LIMIT_N = 100_000.0


@dataclass(frozen=True)
class ContactSafetyPolicyInputs:
    """Normalized contact facts evaluated independently of planner state."""

    contact_active: bool
    components: tuple[str, ...]
    forces_n: tuple[float, ...]
    telemetry_valid: bool
    hard_bottom_violation: bool
    stuck: bool
    timed_out: bool


@dataclass(frozen=True)
class ContactSafetyPolicyResult:
    kind: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.kind in {
            CONTACT_SAFETY_NO_CONTACT,
            CONTACT_SAFETY_ALLOW,
        }

    @property
    def hard_failure(self) -> bool:
        return self.kind == CONTACT_SAFETY_HARD_FAIL


@dataclass(frozen=True)
class ContactSafetyPolicy:
    """Allow ordinary finite bucket contact while preserving hard failures."""

    high_force_n: float = CONTACT_HARD_FORCE_LIMIT_N

    def __post_init__(self) -> None:
        threshold = float(self.high_force_n)
        if (
            not math.isfinite(threshold)
            or threshold <= 0.0
            or threshold > CONTACT_HARD_FORCE_LIMIT_N
        ):
            raise ValueError(
                "high_force_n must be finite, positive, and at most 100000"
            )
        object.__setattr__(self, "high_force_n", threshold)

    def evaluate(
        self,
        inputs: ContactSafetyPolicyInputs,
    ) -> ContactSafetyPolicyResult:
        if inputs.hard_bottom_violation:
            return self._hard_fail("hard_bottom_violation")
        if inputs.stuck:
            return self._hard_fail("stuck")
        if inputs.timed_out:
            return self._hard_fail("timeout")
        if not inputs.telemetry_valid:
            return self._hard_fail("invalid_contact_telemetry")
        if not inputs.contact_active:
            return ContactSafetyPolicyResult(
                kind=CONTACT_SAFETY_NO_CONTACT,
                reason="no_contact",
            )

        components = tuple(
            str(component).strip().lower()
            for component in inputs.components
        )
        if not components or any(
            component != "bucket" for component in components
        ):
            return self._hard_fail(
                "forbidden_or_unknown_contact_component"
            )

        forces = tuple(float(force) for force in inputs.forces_n)
        if not forces:
            return self._hard_fail("invalid_contact_telemetry")
        if any(not math.isfinite(force) for force in forces):
            return self._hard_fail("nonfinite_contact_telemetry")
        if any(force < 0.0 for force in forces):
            return self._hard_fail("invalid_contact_telemetry")
        if any(force >= self.high_force_n for force in forces):
            return self._hard_fail("high_force_contact")

        return ContactSafetyPolicyResult(
            kind=CONTACT_SAFETY_ALLOW,
            reason="finite_bucket_only_contact",
        )

    @staticmethod
    def _hard_fail(reason: str) -> ContactSafetyPolicyResult:
        return ContactSafetyPolicyResult(
            kind=CONTACT_SAFETY_HARD_FAIL,
            reason=reason,
        )


__all__ = [
    "CONTACT_HARD_FORCE_LIMIT_N",
    "CONTACT_SAFETY_ALLOW",
    "CONTACT_SAFETY_HARD_FAIL",
    "CONTACT_SAFETY_NO_CONTACT",
    "ContactSafetyPolicy",
    "ContactSafetyPolicyInputs",
    "ContactSafetyPolicyResult",
]
