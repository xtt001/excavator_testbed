"""Bootstrap compatibility gates and scripted qpos action helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.planner.dig_start_alignment import pd_servo_action


@dataclass(frozen=True)
class BootstrapConfig:
    action_dim: int
    end_mode: str
    end_min_bucket_mass_kg: float
    end_min_distance_to_dig_area_m: float
    scripted_target_qpos: np.ndarray | None = None
    scripted_kp: float = 2.0
    scripted_kd: float = 0.25
    scripted_action_clip: float | np.ndarray | list[float] | tuple[float, ...] = 0.35
    scripted_action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None
    scripted_qpos_tolerance: float = 0.02
    scripted_qvel_abs_max: float = 0.08
    scripted_hold_steps: int = 5
    scripted_max_steps: int = 240


@dataclass(frozen=True)
class BootstrapFacts:
    qpos: np.ndarray
    qvel: np.ndarray
    mass_in_bucket_kg: float = 0.0
    min_distance_to_dig_area_m: float = 0.0
    qualified_dig_start: bool = False
    step_count: int = 0
    hold_count: int = 0
    bootstrap_policy_present: bool = False


@dataclass(frozen=True)
class BootstrapTargetDecision:
    ready: bool
    hold_count: int


@dataclass(frozen=True)
class BootstrapEndDecision:
    should_end: bool
    hold_count: int
    timeout_increment: bool = False


class BootstrapService:
    """Evaluates legacy bootstrap compatibility gates without planner state."""

    @staticmethod
    def scripted_enabled(config: BootstrapConfig) -> bool:
        return bool(
            str(config.end_mode) == "scripted_qpos"
            and config.scripted_target_qpos is not None
        )

    def should_end(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> BootstrapEndDecision:
        if self.scripted_enabled(config):
            target = self.scripted_target_reached(facts, config)
            if target.ready:
                return BootstrapEndDecision(
                    should_end=True,
                    hold_count=target.hold_count,
                )
            timed_out = int(facts.step_count) >= int(config.scripted_max_steps)
            return BootstrapEndDecision(
                should_end=timed_out,
                hold_count=target.hold_count,
                timeout_increment=timed_out,
            )

        if not bool(facts.bootstrap_policy_present):
            return BootstrapEndDecision(
                should_end=False,
                hold_count=int(facts.hold_count),
            )

        mode = str(config.end_mode)
        if mode == "first_qualified_dig_start":
            return BootstrapEndDecision(
                should_end=bool(facts.qualified_dig_start),
                hold_count=int(facts.hold_count),
            )
        if mode == "loaded_and_clear":
            return BootstrapEndDecision(
                should_end=bool(
                    float(facts.mass_in_bucket_kg)
                    >= float(config.end_min_bucket_mass_kg)
                    and float(facts.min_distance_to_dig_area_m)
                    >= float(config.end_min_distance_to_dig_area_m)
                ),
                hold_count=int(facts.hold_count),
            )
        if mode == "disabled":
            return BootstrapEndDecision(
                should_end=False,
                hold_count=int(facts.hold_count),
            )
        raise ValueError(f"Unsupported bootstrap_end_mode {mode!r}.")

    def scripted_target_reached(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> BootstrapTargetDecision:
        if config.scripted_target_qpos is None:
            return BootstrapTargetDecision(
                ready=False,
                hold_count=int(facts.hold_count),
            )
        action_dim = int(config.action_dim)
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(action_dim)
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(action_dim)
        target_qpos = np.asarray(
            config.scripted_target_qpos,
            dtype=np.float32,
        ).reshape(action_dim)
        qpos_close = bool(
            np.all(np.abs(qpos - target_qpos) <= float(config.scripted_qpos_tolerance))
        )
        qvel_small = bool(np.all(np.abs(qvel) <= float(config.scripted_qvel_abs_max)))
        hold_count = int(facts.hold_count) + 1 if qpos_close and qvel_small else 0
        return BootstrapTargetDecision(
            ready=bool(hold_count >= int(config.scripted_hold_steps)),
            hold_count=hold_count,
        )

    def scripted_action(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> np.ndarray:
        if config.scripted_target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        action_dim = int(config.action_dim)
        return pd_servo_action(
            qpos=np.asarray(facts.qpos, dtype=np.float32).reshape(action_dim),
            qvel=np.asarray(facts.qvel, dtype=np.float32).reshape(action_dim),
            target_qpos=np.asarray(
                config.scripted_target_qpos,
                dtype=np.float32,
            ).reshape(action_dim),
            kp=float(config.scripted_kp),
            kd=float(config.scripted_kd),
            action_clip=config.scripted_action_clip,
            action_signs=config.scripted_action_signs,
        )
