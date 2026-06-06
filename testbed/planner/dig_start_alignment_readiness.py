"""Pre-dig alignment readiness and handoff gate decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from testbed.planner.dig_start_alignment_context import (
    DigStartAlignmentConfig,
    DigStartAlignmentFacts,
    build_dig_start_alignment_facts,
    build_dig_start_alignment_facts_from_observation_view,
)
from testbed.planner.snapshots import bucket_dig_area_pose_from_obs

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView


@dataclass(frozen=True)
class SurfaceGuardDecision:
    triggered: bool
    surface_depth_m: float


@dataclass(frozen=True)
class AlignmentReadyDecision:
    ready: bool
    hold_count: int
    error: np.ndarray
    qpos_close: bool
    qvel_small: bool
    entry_close: bool
    start_envelope_ready: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_ready: bool


@dataclass(frozen=True)
class TimeoutHandoffDecision:
    ready: bool
    reason: str
    start_envelope_ready: bool
    entry_intent_handoff_ready: bool


@dataclass(frozen=True)
class PreDigAlignTimeoutHandoffRequest:
    should_sample_entry_error: bool
    current_entry_error_m: float

    def facts_with_entry_sampling(
        self,
        *,
        action_dim: int,
        qpos: np.ndarray | list[float] | tuple[float, ...] | None,
        qvel: np.ndarray | list[float] | tuple[float, ...] | None = None,
        entry_error_m: float,
        bucket_pose: tuple[float, float, float] | None = None,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts(
            action_dim=int(action_dim),
            qpos=qpos,
            qvel=qvel,
            entry_error_m=float(entry_error_m),
            bucket_pose=bucket_pose,
        )

    def facts_with_entry_sampling_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        entry_error_m: float,
    ) -> DigStartAlignmentFacts:
        action_dim = int(view.action_dim)
        return self.facts_with_entry_sampling(
            action_dim=action_dim,
            qpos=view.obs.get("qpos", np.zeros(action_dim, dtype=np.float32)),
            qvel=view.obs.get("qvel", np.zeros(action_dim, dtype=np.float32)),
            entry_error_m=float(entry_error_m),
            bucket_pose=bucket_dig_area_pose_from_obs(view.obs),
        )

    def facts_without_entry_sampling(
        self,
        *,
        action_dim: int,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts(
            action_dim=int(action_dim),
            qpos=None,
            qvel=None,
            entry_error_m=float(self.current_entry_error_m),
        )


class DigStartAlignmentReadinessService:
    """Computes pre-dig alignment readiness gates without scheduler state."""

    def surface_guard_triggered(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> SurfaceGuardDecision:
        surface_depth = float(facts.surface_depth_m)
        if not (bool(config.enabled) and bool(config.surface_guard_enabled)):
            return SurfaceGuardDecision(False, surface_depth)
        if (
            np.isfinite(surface_depth)
            and surface_depth > float(config.surface_guard_max_penetration_m)
        ):
            return SurfaceGuardDecision(True, surface_depth)
        if (
            not np.isfinite(surface_depth)
            and bool(config.surface_guard_use_contact_fallback)
            and bool(facts.contact_mask)
        ):
            return SurfaceGuardDecision(True, surface_depth)
        return SurfaceGuardDecision(False, surface_depth)

    def surface_guard_triggered_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        config: DigStartAlignmentConfig,
        entry_error_m: float = float("nan"),
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> SurfaceGuardDecision:
        return self.surface_guard_triggered(
            build_dig_start_alignment_facts_from_observation_view(
                view=view,
                entry_error_m=entry_error_m,
                cycle_index=cycle_index,
                hold_count=hold_count,
            ),
            config,
        )

    def surface_guard_can_handoff(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> bool:
        threshold = config.surface_guard_handoff_entry_error_m
        if threshold is None:
            threshold = config.max_entry_error_m
        if threshold is None:
            threshold = config.start_envelope_max_entry_error_m
        return self.entry_close(facts.entry_error_m, threshold=threshold)

    def surface_guard_can_handoff_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        entry_error_m: float,
        config: DigStartAlignmentConfig,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> bool:
        return self.surface_guard_can_handoff(
            build_dig_start_alignment_facts_from_observation_view(
                view=view,
                entry_error_m=entry_error_m,
                cycle_index=cycle_index,
                hold_count=hold_count,
            ),
            config,
        )

    def ready(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> AlignmentReadyDecision:
        if not bool(config.enabled):
            return AlignmentReadyDecision(
                ready=True,
                hold_count=int(facts.hold_count),
                error=np.zeros(int(config.action_dim), dtype=np.float32),
                qpos_close=True,
                qvel_small=True,
                entry_close=True,
                start_envelope_ready=False,
                entry_close_handoff_ready=False,
                entry_intent_handoff_ready=False,
            )
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(int(config.action_dim))
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(int(config.action_dim))
        target_qpos = np.asarray(
            facts.target_qpos,
            dtype=np.float32,
        ).reshape(int(config.action_dim))
        error = (target_qpos - qpos).astype(np.float32)
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        qpos_tolerance = self._qpos_tolerance(config)
        qpos_close = bool(
            np.all(np.abs(error[controlled]) <= qpos_tolerance[controlled])
            if np.any(controlled)
            else True
        )
        qvel_small = bool(
            np.all(np.abs(qvel[controlled]) <= float(config.qvel_abs_max))
            if np.any(controlled)
            else True
        )
        entry_close = self.entry_close(
            facts.entry_error_m,
            threshold=config.max_entry_error_m,
        )
        start_ready = self.start_envelope_ready(facts, config)
        entry_close_ready = self.entry_close_handoff_ready(
            facts=facts,
            config=config,
            start_envelope_ready=start_ready,
        )
        intent_ready = self.entry_intent_handoff_ready(
            qpos_close=qpos_close,
            qvel_small=qvel_small,
            config=config,
        )
        should_hold = bool(
            entry_close_ready
            or intent_ready
            or (qpos_close and qvel_small and (entry_close or start_ready))
        )
        hold_count = int(facts.hold_count) + 1 if should_hold else 0
        return AlignmentReadyDecision(
            ready=bool(hold_count >= int(config.hold_steps)),
            hold_count=hold_count,
            error=error,
            qpos_close=qpos_close,
            qvel_small=qvel_small,
            entry_close=entry_close,
            start_envelope_ready=start_ready,
            entry_close_handoff_ready=entry_close_ready,
            entry_intent_handoff_ready=intent_ready,
        )

    def ready_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        target_qpos: np.ndarray,
        entry_error_m: float,
        config: DigStartAlignmentConfig,
        qpos: np.ndarray | None = None,
        qvel: np.ndarray | None = None,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> AlignmentReadyDecision:
        return self.ready(
            build_dig_start_alignment_facts_from_observation_view(
                view=view,
                target_qpos=target_qpos,
                entry_error_m=entry_error_m,
                qpos=qpos,
                qvel=qvel,
                cycle_index=cycle_index,
                hold_count=hold_count,
            ),
            config,
        )

    @staticmethod
    def entry_close(entry_error: float, *, threshold: float | None) -> bool:
        if threshold is None:
            return True
        return bool(np.isfinite(entry_error) and float(entry_error) <= float(threshold))

    def entry_close_handoff_ready(
        self,
        *,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
        start_envelope_ready: bool,
    ) -> bool:
        if not bool(config.first_dig_entry_close_handoff):
            return False
        if int(facts.cycle_index) != 0:
            return False
        if bool(config.start_envelope_enabled) and not bool(start_envelope_ready):
            return False
        if not self.entry_close(
            facts.entry_error_m,
            threshold=config.max_entry_error_m,
        ):
            return False
        qvel_abs_max = config.first_dig_entry_close_handoff_qvel_abs_max
        if qvel_abs_max is None:
            qvel_abs_max = config.qvel_abs_max
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        if not np.any(controlled):
            return True
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(int(config.action_dim))
        return bool(np.all(np.abs(qvel[controlled]) <= float(qvel_abs_max)))

    def entry_close_handoff_ready_from_runtime_values(
        self,
        *,
        action_dim: int,
        qvel: np.ndarray | list[float] | tuple[float, ...],
        entry_error_m: float,
        cycle_index: int,
        config: DigStartAlignmentConfig,
        start_envelope_ready: bool,
    ) -> bool:
        return self.entry_close_handoff_ready(
            facts=self.entry_close_handoff_facts(
                action_dim=action_dim,
                qvel=qvel,
                entry_error_m=entry_error_m,
                cycle_index=cycle_index,
            ),
            config=config,
            start_envelope_ready=start_envelope_ready,
        )

    @staticmethod
    def entry_close_handoff_facts(
        *,
        action_dim: int,
        qvel: np.ndarray | list[float] | tuple[float, ...],
        entry_error_m: float,
        cycle_index: int,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts(
            action_dim=int(action_dim),
            qpos=None,
            qvel=qvel,
            entry_error_m=float(entry_error_m),
            cycle_index=int(cycle_index),
        )

    def entry_intent_mode_enabled(self, config: DigStartAlignmentConfig) -> bool:
        if not bool(config.entry_intent_handoff_enabled):
            return False
        intent_dims = config.entry_intent_controlled_dims
        if intent_dims is None:
            return False
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        intent = np.asarray(intent_dims, dtype=bool).reshape(int(config.action_dim))
        return bool(np.any(controlled & intent) and np.any(controlled & ~intent))

    def entry_intent_handoff_ready(
        self,
        *,
        qpos_close: bool,
        qvel_small: bool,
        config: DigStartAlignmentConfig,
    ) -> bool:
        return bool(
            self.entry_intent_mode_enabled(config)
            and bool(qpos_close)
            and bool(qvel_small)
        )

    def timeout_can_handoff(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> TimeoutHandoffDecision:
        threshold = self._timeout_entry_threshold(config)
        if threshold is None:
            return TimeoutHandoffDecision(
                ready=True,
                reason="pre_dig_align_to_dig_timeout_no_entry_gate",
                start_envelope_ready=False,
                entry_intent_handoff_ready=False,
            )
        start_ready = self.start_envelope_ready(facts, config)
        if self.entry_intent_mode_enabled(config):
            return TimeoutHandoffDecision(
                ready=True,
                reason="pre_dig_align_to_dig_timeout_intent_aligned",
                start_envelope_ready=start_ready,
                entry_intent_handoff_ready=True,
            )
        ready = bool(
            self.entry_close(facts.entry_error_m, threshold=threshold) or start_ready
        )
        return TimeoutHandoffDecision(
            ready=ready,
            reason="pre_dig_align_to_dig_timeout_close_enough" if ready else "",
            start_envelope_ready=start_ready,
            entry_intent_handoff_ready=False,
        )

    @staticmethod
    def timeout_handoff_request(
        *,
        current_entry_error_m: float,
        config: DigStartAlignmentConfig,
    ) -> PreDigAlignTimeoutHandoffRequest:
        return PreDigAlignTimeoutHandoffRequest(
            should_sample_entry_error=(
                DigStartAlignmentReadinessService._timeout_entry_threshold(config)
                is not None
            ),
            current_entry_error_m=float(current_entry_error_m),
        )

    def timeout_handoff_decision(
        self,
        *,
        request: PreDigAlignTimeoutHandoffRequest,
        config: DigStartAlignmentConfig,
        action_dim: int,
        view: PlannerObservationView | None = None,
        sampled_entry_error_m: float | None = None,
    ) -> TimeoutHandoffDecision:
        if request.should_sample_entry_error:
            if view is None or sampled_entry_error_m is None:
                raise ValueError(
                    "timeout handoff sampling requires observation view and "
                    "sampled entry error"
                )
            facts = request.facts_with_entry_sampling_from_observation_view(
                view=view,
                entry_error_m=sampled_entry_error_m,
            )
        else:
            facts = request.facts_without_entry_sampling(
                action_dim=int(action_dim),
            )
        return self.timeout_can_handoff(facts, config)

    def start_envelope_ready(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> bool:
        if not bool(config.start_envelope_enabled):
            return False
        if (
            not np.isfinite(facts.entry_error_m)
            or float(facts.entry_error_m)
            > float(config.start_envelope_max_entry_error_m)
        ):
            return False
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(int(config.action_dim))
        start_qpos_min = self._start_qpos_min(config)
        start_qpos_max = self._start_qpos_max(config)
        if not np.all(qpos >= start_qpos_min):
            return False
        if not np.all(qpos <= start_qpos_max):
            return False
        if facts.bucket_pose is None:
            return False
        pose_arr = np.asarray(facts.bucket_pose, dtype=np.float32).reshape(3)
        start_pose_min = self._start_pose_min(config)
        start_pose_max = self._start_pose_max(config)
        return bool(
            np.all(pose_arr >= start_pose_min)
            and np.all(pose_arr <= start_pose_max)
        )

    def start_envelope_ready_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        qpos: np.ndarray | list[float] | tuple[float, ...] | None,
        entry_error_m: float,
        config: DigStartAlignmentConfig,
    ) -> bool:
        return self.start_envelope_ready(
            self.start_envelope_facts_from_observation_view(
                view=view,
                qpos=qpos,
                entry_error_m=entry_error_m,
            ),
            config,
        )

    @staticmethod
    def start_envelope_facts(
        *,
        action_dim: int,
        qpos: np.ndarray | list[float] | tuple[float, ...] | None,
        entry_error_m: float,
        bucket_pose: tuple[float, float, float] | None,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts(
            action_dim=int(action_dim),
            qpos=qpos,
            qvel=None,
            entry_error_m=float(entry_error_m),
            bucket_pose=bucket_pose,
        )

    @staticmethod
    def start_envelope_facts_from_observation_view(
        *,
        view: PlannerObservationView,
        qpos: np.ndarray | list[float] | tuple[float, ...] | None,
        entry_error_m: float,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts(
            action_dim=int(view.action_dim),
            qpos=qpos,
            qvel=None,
            entry_error_m=float(entry_error_m),
            bucket_pose=bucket_dig_area_pose_from_obs(view.obs),
        )

    def _qpos_tolerance(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.qpos_tolerance is None:
            return np.zeros(int(config.action_dim), dtype=np.float32)
        return np.asarray(config.qpos_tolerance, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    @staticmethod
    def _timeout_entry_threshold(config: DigStartAlignmentConfig) -> float | None:
        threshold = config.timeout_accept_entry_error_m
        if threshold is None:
            threshold = config.max_entry_error_m
        return None if threshold is None else float(threshold)

    def _start_qpos_min(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_qpos_min is None:
            return np.full(int(config.action_dim), -np.inf, dtype=np.float32)
        return np.asarray(config.start_qpos_min, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    def _start_qpos_max(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_qpos_max is None:
            return np.full(int(config.action_dim), np.inf, dtype=np.float32)
        return np.asarray(config.start_qpos_max, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    @staticmethod
    def _start_pose_min(config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_pose_min is None:
            return np.full(3, -np.inf, dtype=np.float32)
        return np.asarray(config.start_pose_min, dtype=np.float32).reshape(3)

    @staticmethod
    def _start_pose_max(config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_pose_max is None:
            return np.full(3, np.inf, dtype=np.float32)
        return np.asarray(config.start_pose_max, dtype=np.float32).reshape(3)
