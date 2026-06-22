"""Primitive skill switch lifecycle sequencing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PrimitiveSkillLifecyclePorts:
    """Shell-owned state ports used by primitive skill lifecycle service."""

    current_skill_name: Callable[[], str]
    set_skill_name: Callable[[str], None]
    set_switch_reason: Callable[[str], None]
    reset_active_policy: Callable[[], None]
    clear_dig_cut_plan: Callable[[], None]
    set_dump_ready_hold_count: Callable[[int], None]
    set_dump_done_hold_count: Callable[[int], None]
    set_return_step_count: Callable[[int], None]
    set_return_next_dig_event_seen: Callable[[bool], None]
    set_pre_dig_align_step_count: Callable[[int], None]
    set_pre_dig_align_hold_count: Callable[[int], None]
    set_pre_dig_align_entry_close_handoff_ready: Callable[[bool], None]
    set_pre_dig_align_entry_intent_handoff_ready: Callable[[bool], None]
    set_pre_dig_align_timeout_handoff_reason: Callable[[str], None]
    set_pre_dig_align_surface_guard_triggered: Callable[[bool], None]
    set_coverage_current_payload_gain_kg: Callable[[float], None]
    set_dig_step_count: Callable[[int], None]
    set_dig_best_mass_kg: Callable[[float], None]
    set_dig_mass_plateau_count: Callable[[int], None]
    set_dig_to_carry_reason: Callable[[str], None]
    pre_dig_align_skill_name: str = "pre_dig_align"


@dataclass(frozen=True)
class PrimitiveSkillLifecycleService:
    """Own 4P primitive skill switch lifecycle ordering."""

    ports: PrimitiveSkillLifecyclePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveSkillLifecyclePorts,
    ) -> "PrimitiveSkillLifecycleService":
        return cls(ports=ports)

    def set_skill(self, skill_name: str, reason: str) -> None:
        ports = self.ports
        target_skill = str(skill_name)
        if target_skill == str(ports.current_skill_name()):
            return

        ports.set_skill_name(target_skill)
        ports.set_switch_reason(str(reason))
        if target_skill != str(ports.pre_dig_align_skill_name):
            ports.reset_active_policy()

        if target_skill == "carry":
            ports.set_dump_ready_hold_count(0)
        elif target_skill == "dump":
            ports.set_dump_done_hold_count(0)
        elif target_skill == "return":
            ports.set_return_step_count(0)
            ports.set_return_next_dig_event_seen(False)
        elif target_skill == str(ports.pre_dig_align_skill_name):
            self._reset_pre_dig_align()
        elif target_skill == "dig":
            self._reset_dig()

        if target_skill not in {"dig", str(ports.pre_dig_align_skill_name)}:
            ports.clear_dig_cut_plan()

    def _reset_pre_dig_align(self) -> None:
        ports = self.ports
        ports.set_pre_dig_align_step_count(0)
        ports.set_pre_dig_align_hold_count(0)
        ports.set_pre_dig_align_entry_close_handoff_ready(False)
        ports.set_pre_dig_align_entry_intent_handoff_ready(False)
        ports.set_pre_dig_align_timeout_handoff_reason("")
        ports.set_pre_dig_align_surface_guard_triggered(False)

    def _reset_dig(self) -> None:
        ports = self.ports
        ports.set_return_next_dig_event_seen(False)
        ports.set_dump_ready_hold_count(0)
        ports.set_dump_done_hold_count(0)
        ports.set_coverage_current_payload_gain_kg(0.0)
        ports.set_dig_step_count(0)
        ports.set_dig_best_mass_kg(0.0)
        ports.set_dig_mass_plateau_count(0)
        ports.set_dig_to_carry_reason("")


__all__ = [
    "PrimitiveSkillLifecyclePorts",
    "PrimitiveSkillLifecycleService",
]
