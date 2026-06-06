"""Dig depth-profile token source selection for primitive planning."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_DIR_X_IDX,
    CUT_DIR_Z_IDX,
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    CUT_EXIT_X_IDX,
    CUT_EXIT_Z_IDX,
    CUT_LENGTH_IDX,
    CUT_PAYLOAD_IDX,
    CUT_VALID_IDX,
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    validate_primitive_token_shape,
)
from testbed.data.dig_depth_profile_v2_4 import (
    build_dig_depth_profile_token_from_plan,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
)
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX


@dataclass(frozen=True)
class DigDepthProfileConfig:
    source: str = "live_plan"
    required: bool = False
    allow_live_fallback: bool = True
    allow_global_fallback: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "allow_live_fallback", bool(self.allow_live_fallback))
        object.__setattr__(
            self,
            "allow_global_fallback",
            bool(self.allow_global_fallback),
        )


DIG_DEPTH_PROFILE_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("source", "dig_depth_profile_source"),
    ("required", "dig_depth_profile_required"),
    ("allow_live_fallback", "dig_depth_profile_allow_live_fallback"),
    ("allow_global_fallback", "dig_depth_profile_allow_global_fallback"),
)


@dataclass(frozen=True)
class DigDepthProfileBuildRequest:
    cell_id: int
    raw_fields: dict[str, float | int]
    env_state: Any
    config: DigDepthProfileConfig = field(default_factory=DigDepthProfileConfig)
    dig_cut_prior: dict[str, Any] | None = None
    state_exemplar_profile_token: Any | None = None


@dataclass(frozen=True)
class DigDepthProfileState:
    token: np.ndarray
    source: str
    fallback_reason: str = ""


@dataclass(frozen=True)
class DigDepthProfileTokenResult:
    token: np.ndarray
    source: str
    fallback_reason: str


@dataclass(frozen=True)
class DigDepthProfileObservationTokenResult:
    token: np.ndarray


@dataclass(frozen=True)
class DigDepthProfileRuntimeState:
    tokens: np.ndarray
    token_injected: bool
    token_source: str
    fallback_reason: str


@dataclass(frozen=True)
class DigDepthProfileRuntimeStatusState:
    token_injected: bool
    token_source: str
    fallback_reason: str
    tokens: np.ndarray


DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("token_injected", "_dig_depth_profile_token_injected"),
    ("token_source", "_dig_depth_profile_token_source"),
    ("fallback_reason", "_dig_depth_profile_fallback_reason"),
    ("tokens", "_dig_depth_profile_tokens"),
)


@dataclass(frozen=True)
class DigDepthProfileRuntimeStatusSnapshot:
    source: str
    required: bool
    token_injected: bool
    token_source: str
    fallback_reason: str
    tokens: np.ndarray


def build_dig_depth_profile_config_from_mapping(
    values: Mapping[str, Any],
) -> DigDepthProfileConfig:
    return DigDepthProfileConfig(
        source=values["source"],
        required=values["required"],
        allow_live_fallback=values["allow_live_fallback"],
        allow_global_fallback=values["allow_global_fallback"],
    )


def build_dig_depth_profile_runtime_status_state_from_mapping(
    values: Mapping[str, Any],
) -> DigDepthProfileRuntimeStatusState:
    return DigDepthProfileRuntimeStatusState(
        token_injected=bool(values["token_injected"]),
        token_source=str(values["token_source"]),
        fallback_reason=str(values["fallback_reason"]),
        tokens=values["tokens"],
    )


@dataclass(frozen=True)
class DigDepthProfileInputFacts:
    cycle_index: int
    pending_cycle_id: int = -1
    pending_corridor_id: int = -1
    pending_raw_fields: dict[str, float | int] | None = None
    pending_corridor_cell_id: int | None = None
    active_corridor_raw_fields: dict[str, float | int] | None = None
    active_corridor_cell_id: int | None = None
    live_raw_fields: dict[str, float | int] | None = None
    current_dig_cut_tokens: Any | None = None
    env_state: Any | None = None


@dataclass(frozen=True)
class DigDepthProfileInputSourceFacts:
    cycle_index: int
    pending_cycle_id: int = -1
    pending_corridor_id: int = -1
    pending_raw_fields: dict[str, float | int] | None = None
    pending_corridor_cell_id: int | None = None
    active_corridor_raw_fields: dict[str, float | int] | None = None
    active_corridor_cell_id: int | None = None
    live_raw_fields: dict[str, float | int] | None = None
    current_dig_cut_tokens: Any | None = None
    env_state: Any | None = None
    include_env_state: bool = False


@dataclass(frozen=True)
class DigDepthProfileInputSourcePlan:
    cycle_index: int
    pending_cycle_id: int
    pending_corridor_id: int
    pending_raw_fields: dict[str, float | int] | None
    pending_corridor_cell_id: int | None
    active_corridor_raw_fields: dict[str, float | int] | None
    active_corridor_cell_id: int | None
    sample_pending_corridor: bool
    sample_active_corridor: bool
    sample_active_raw_fields: bool
    sample_active_corridor_cell_id: bool
    sample_live_raw_fields: bool
    sample_env_state: bool


@dataclass(frozen=True)
class DigDepthProfileInputSourceCallbacks:
    pending_corridor_cell_id: Callable[[int], int | None]
    active_corridor: Callable[[], Any | None]
    active_corridor_raw_fields: Callable[[Any], dict[str, float | int]]
    active_corridor_cell_id: Callable[[Any], int]
    live_raw_fields: Callable[[], dict[str, float | int]]
    env_state: Callable[[], Any]


def build_dig_depth_profile_input_facts(
    sources: DigDepthProfileInputSourceFacts,
) -> DigDepthProfileInputFacts:
    pending_cycle_matches = int(sources.pending_cycle_id) == int(
        sources.cycle_index
    )
    pending_corridor_id = int(sources.pending_corridor_id)
    pending_raw_fields = (
        sources.pending_raw_fields
        if sources.pending_raw_fields is not None and pending_cycle_matches
        else None
    )
    pending_corridor_cell_id = (
        sources.pending_corridor_cell_id
        if pending_corridor_id >= 0
        and pending_cycle_matches
        and sources.pending_corridor_cell_id is not None
        else None
    )
    active_corridor_raw_fields = (
        sources.active_corridor_raw_fields
        if pending_raw_fields is None
        else None
    )
    active_corridor_cell_id = (
        sources.active_corridor_cell_id
        if pending_corridor_cell_id is None
        else None
    )
    live_raw_fields = (
        sources.live_raw_fields
        if pending_raw_fields is None and active_corridor_raw_fields is None
        else None
    )
    env_state = (
        sources.env_state
        if bool(sources.include_env_state)
        or (
            pending_corridor_cell_id is None
            and active_corridor_cell_id is None
        )
        else None
    )
    return DigDepthProfileInputFacts(
        cycle_index=int(sources.cycle_index),
        pending_cycle_id=int(sources.pending_cycle_id),
        pending_corridor_id=pending_corridor_id,
        pending_raw_fields=pending_raw_fields,
        pending_corridor_cell_id=pending_corridor_cell_id,
        active_corridor_raw_fields=active_corridor_raw_fields,
        active_corridor_cell_id=active_corridor_cell_id,
        live_raw_fields=live_raw_fields,
        current_dig_cut_tokens=sources.current_dig_cut_tokens,
        env_state=env_state,
    )


class DigDepthProfileMissingPriorError(ValueError):
    def __init__(self, *, cell_id: int, reason: str) -> None:
        super().__init__(
            "dig_depth_profile.source='prior_profile' requires a matching "
            f"dig_depth_profile prior for cell {int(cell_id)}; {reason}"
        )
        self.cell_id = int(cell_id)
        self.reason = str(reason)


class DigDepthProfileService:
    """Builds dig depth-profile tokens without owning planner state."""

    @staticmethod
    def initial_runtime_state() -> DigDepthProfileRuntimeState:
        return DigDepthProfileRuntimeState(
            tokens=np.zeros(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
            token_injected=False,
            token_source="none",
            fallback_reason="",
        )

    @staticmethod
    def runtime_status_snapshot(
        *,
        config: DigDepthProfileConfig,
        state: DigDepthProfileRuntimeStatusState,
    ) -> DigDepthProfileRuntimeStatusSnapshot:
        return DigDepthProfileRuntimeStatusSnapshot(
            source=str(config.source),
            required=bool(config.required),
            token_injected=bool(state.token_injected),
            token_source=str(state.token_source),
            fallback_reason=str(state.fallback_reason),
            tokens=np.asarray(state.tokens, dtype=np.float32).copy(),
        )

    @staticmethod
    def runtime_status_snapshot_from_mappings(
        *,
        config_values: Mapping[str, Any],
        state_values: Mapping[str, Any],
    ) -> DigDepthProfileRuntimeStatusSnapshot:
        return DigDepthProfileService.runtime_status_snapshot(
            config=build_dig_depth_profile_config_from_mapping(config_values),
            state=build_dig_depth_profile_runtime_status_state_from_mapping(
                state_values
            ),
        )

    @staticmethod
    def token_result(state: DigDepthProfileState) -> DigDepthProfileTokenResult:
        return DigDepthProfileTokenResult(
            token=np.asarray(state.token, dtype=np.float32),
            source=str(state.source),
            fallback_reason=str(state.fallback_reason),
        )

    @staticmethod
    def observation_token_result(
        tokens: Any,
    ) -> DigDepthProfileObservationTokenResult:
        return DigDepthProfileObservationTokenResult(token=np.asarray(tokens).copy())

    @staticmethod
    def input_source_plan(
        *,
        cycle_index: int,
        pending_cycle_id: int = -1,
        pending_corridor_id: int = -1,
        pending_raw_fields: dict[str, float | int] | None = None,
        pending_corridor_cell_id: int | None = None,
        active_corridor_raw_fields: dict[str, float | int] | None = None,
        active_corridor_cell_id: int | None = None,
        pending_corridor_sampled: bool = False,
        active_corridor_sampled: bool = False,
        active_corridor_present: bool = False,
        include_env_state: bool = False,
    ) -> DigDepthProfileInputSourcePlan:
        pending_cycle_matches = int(pending_cycle_id) == int(cycle_index)
        normalized_pending_corridor_id = int(pending_corridor_id)
        current_pending_raw_fields = (
            pending_raw_fields
            if pending_raw_fields is not None and pending_cycle_matches
            else None
        )
        current_pending_corridor_cell_id = (
            int(pending_corridor_cell_id)
            if normalized_pending_corridor_id >= 0
            and pending_cycle_matches
            and pending_corridor_cell_id is not None
            else None
        )
        sample_pending_corridor = (
            normalized_pending_corridor_id >= 0
            and pending_cycle_matches
            and current_pending_corridor_cell_id is None
            and not bool(pending_corridor_sampled)
        )
        sample_active_corridor = (
            current_pending_raw_fields is None
            or current_pending_corridor_cell_id is None
        ) and not bool(active_corridor_sampled)
        sample_active_raw_fields = (
            bool(active_corridor_sampled)
            and bool(active_corridor_present)
            and current_pending_raw_fields is None
            and active_corridor_raw_fields is None
        )
        sample_active_corridor_cell_id = (
            bool(active_corridor_sampled)
            and bool(active_corridor_present)
            and current_pending_corridor_cell_id is None
            and active_corridor_cell_id is None
        )
        sample_live_raw_fields = (
            current_pending_raw_fields is None
            and bool(active_corridor_sampled)
            and active_corridor_raw_fields is None
        )
        sample_env_state = bool(include_env_state) or (
            current_pending_corridor_cell_id is None
            and bool(active_corridor_sampled)
            and active_corridor_cell_id is None
        )
        return DigDepthProfileInputSourcePlan(
            cycle_index=int(cycle_index),
            pending_cycle_id=int(pending_cycle_id),
            pending_corridor_id=normalized_pending_corridor_id,
            pending_raw_fields=current_pending_raw_fields,
            pending_corridor_cell_id=current_pending_corridor_cell_id,
            active_corridor_raw_fields=active_corridor_raw_fields,
            active_corridor_cell_id=active_corridor_cell_id,
            sample_pending_corridor=sample_pending_corridor,
            sample_active_corridor=sample_active_corridor,
            sample_active_raw_fields=sample_active_raw_fields,
            sample_active_corridor_cell_id=sample_active_corridor_cell_id,
            sample_live_raw_fields=sample_live_raw_fields,
            sample_env_state=sample_env_state,
        )

    @staticmethod
    def input_facts_from_source_callbacks(
        *,
        cycle_index: int,
        pending_cycle_id: int = -1,
        pending_corridor_id: int = -1,
        pending_raw_fields: dict[str, float | int] | None = None,
        current_dig_cut_tokens: Any | None = None,
        include_env_state: bool = False,
        callbacks: DigDepthProfileInputSourceCallbacks,
    ) -> DigDepthProfileInputFacts:
        pending_corridor_id = int(pending_corridor_id)
        plan = DigDepthProfileService.input_source_plan(
            cycle_index=int(cycle_index),
            pending_cycle_id=int(pending_cycle_id),
            pending_corridor_id=pending_corridor_id,
            pending_raw_fields=pending_raw_fields,
            include_env_state=bool(include_env_state),
        )
        pending_corridor_cell_id = plan.pending_corridor_cell_id
        if plan.sample_pending_corridor:
            pending_corridor_cell_id = callbacks.pending_corridor_cell_id(
                pending_corridor_id
            )

        active_raw_fields = None
        active_corridor_cell_id = None
        active_corridor = None
        plan = DigDepthProfileService.input_source_plan(
            cycle_index=int(cycle_index),
            pending_cycle_id=int(pending_cycle_id),
            pending_corridor_id=pending_corridor_id,
            pending_raw_fields=plan.pending_raw_fields,
            pending_corridor_cell_id=pending_corridor_cell_id,
            pending_corridor_sampled=True,
            include_env_state=bool(include_env_state),
        )
        if plan.sample_active_corridor:
            active_corridor = callbacks.active_corridor()
        if active_corridor is not None:
            plan = DigDepthProfileService.input_source_plan(
                cycle_index=int(cycle_index),
                pending_cycle_id=int(pending_cycle_id),
                pending_corridor_id=pending_corridor_id,
                pending_raw_fields=plan.pending_raw_fields,
                pending_corridor_cell_id=pending_corridor_cell_id,
                pending_corridor_sampled=True,
                active_corridor_sampled=True,
                active_corridor_present=True,
                include_env_state=bool(include_env_state),
            )
            if plan.sample_active_raw_fields:
                active_raw_fields = callbacks.active_corridor_raw_fields(
                    active_corridor
                )
            if plan.sample_active_corridor_cell_id:
                active_corridor_cell_id = callbacks.active_corridor_cell_id(
                    active_corridor
                )

        plan = DigDepthProfileService.input_source_plan(
            cycle_index=int(cycle_index),
            pending_cycle_id=int(pending_cycle_id),
            pending_corridor_id=pending_corridor_id,
            pending_raw_fields=plan.pending_raw_fields,
            pending_corridor_cell_id=pending_corridor_cell_id,
            active_corridor_raw_fields=active_raw_fields,
            active_corridor_cell_id=active_corridor_cell_id,
            pending_corridor_sampled=True,
            active_corridor_sampled=True,
            include_env_state=bool(include_env_state),
        )
        live_raw_fields = None
        if plan.sample_live_raw_fields:
            live_raw_fields = callbacks.live_raw_fields()
        env_state = None
        if plan.sample_env_state:
            env_state = callbacks.env_state()

        return DigDepthProfileService.input_facts(
            DigDepthProfileInputSourceFacts(
                cycle_index=int(cycle_index),
                pending_cycle_id=int(pending_cycle_id),
                pending_corridor_id=pending_corridor_id,
                pending_raw_fields=plan.pending_raw_fields,
                pending_corridor_cell_id=pending_corridor_cell_id,
                active_corridor_raw_fields=active_raw_fields,
                active_corridor_cell_id=active_corridor_cell_id,
                live_raw_fields=live_raw_fields,
                current_dig_cut_tokens=current_dig_cut_tokens,
                env_state=env_state,
                include_env_state=bool(include_env_state),
            )
        )

    @staticmethod
    def input_facts(
        sources: DigDepthProfileInputSourceFacts,
    ) -> DigDepthProfileInputFacts:
        return build_dig_depth_profile_input_facts(sources)

    @staticmethod
    def resolve_raw_fields(
        facts: DigDepthProfileInputFacts,
    ) -> dict[str, float | int]:
        if (
            facts.pending_raw_fields is not None
            and int(facts.pending_cycle_id) == int(facts.cycle_index)
        ):
            return dict(facts.pending_raw_fields)
        if facts.active_corridor_raw_fields is not None:
            return dict(facts.active_corridor_raw_fields)

        raw_fields = dict(facts.live_raw_fields or {})
        if facts.current_dig_cut_tokens is None:
            return raw_fields
        token = np.asarray(facts.current_dig_cut_tokens, dtype=np.float32).reshape(-1)
        if token.size < DIG_CUT_TOKEN_DIM:
            return raw_fields
        raw_fields.update(
            {
                "operator_entry_x_m": float(token[CUT_ENTRY_X_IDX])
                * DIG_CUT_POSITION_SCALE_M,
                "operator_entry_z_m": float(token[CUT_ENTRY_Z_IDX])
                * DIG_CUT_POSITION_SCALE_M,
                "operator_exit_x_m": float(token[CUT_EXIT_X_IDX])
                * DIG_CUT_POSITION_SCALE_M,
                "operator_exit_z_m": float(token[CUT_EXIT_Z_IDX])
                * DIG_CUT_POSITION_SCALE_M,
                "operator_cut_direction_x": float(token[CUT_DIR_X_IDX]),
                "operator_cut_direction_z": float(token[CUT_DIR_Z_IDX]),
                "operator_cut_length_m": float(token[CUT_LENGTH_IDX])
                * DIG_CUT_LENGTH_SCALE_M,
                "operator_cut_depth_peak_m": float(token[CUT_DEPTH_SEMANTIC_IDX])
                * DIG_CUT_DEPTH_SCALE_M,
                "operator_cut_payload_gain_kg": float(token[CUT_PAYLOAD_IDX])
                * DIG_CUT_PAYLOAD_SCALE_KG,
                "operator_cut_valid": int(float(token[CUT_VALID_IDX]) > 0.5),
            }
        )
        return raw_fields

    @staticmethod
    def resolve_cell_id(facts: DigDepthProfileInputFacts) -> int:
        if (
            int(facts.pending_corridor_id) >= 0
            and int(facts.pending_cycle_id) == int(facts.cycle_index)
            and facts.pending_corridor_cell_id is not None
        ):
            return int(facts.pending_corridor_cell_id)
        if facts.active_corridor_cell_id is not None:
            return int(facts.active_corridor_cell_id)
        if facts.env_state is not None:
            env_state = np.asarray(facts.env_state, dtype=np.float32).reshape(-1)
            if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
                value = float(env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])
                if np.isfinite(value):
                    return int(max(0, min(5, round(value))))
        return 0

    def build_token(
        self,
        request: DigDepthProfileBuildRequest,
    ) -> DigDepthProfileState:
        source = str(request.config.source)
        if source == "prior_profile":
            if request.state_exemplar_profile_token is not None:
                token = np.asarray(
                    request.state_exemplar_profile_token,
                    dtype=np.float32,
                )
                return DigDepthProfileState(
                    token=token,
                    source="qc6_state_conditioned_exemplar",
                    fallback_reason="",
                )
            token, prior_source, reason = self.prior_token(
                request.dig_cut_prior,
                cell_id=int(request.cell_id),
                allow_global_fallback=bool(request.config.allow_global_fallback),
            )
            if token is not None:
                return DigDepthProfileState(
                    token=token.astype(np.float32),
                    source=prior_source,
                    fallback_reason="",
                )
            if (
                bool(request.config.required)
                or not bool(request.config.allow_live_fallback)
            ):
                raise DigDepthProfileMissingPriorError(
                    cell_id=int(request.cell_id),
                    reason=reason,
                )
            return DigDepthProfileState(
                token=self.build_live_token(request),
                source="fallback_live_plan",
                fallback_reason=reason,
            )
        if source != "live_plan":
            raise ValueError(
                "Unsupported dig_depth_profile.source "
                f"{source!r}; expected 'live_plan' or 'prior_profile'."
            )
        return DigDepthProfileState(
            token=self.build_live_token(request),
            source="live_plan",
            fallback_reason="",
        )

    def build_token_from_input_facts(
        self,
        facts: DigDepthProfileInputFacts,
        *,
        config: DigDepthProfileConfig,
        dig_cut_prior: dict[str, Any] | None = None,
        state_exemplar_profile_token: Any | None = None,
    ) -> DigDepthProfileState:
        return self.build_token(
            DigDepthProfileBuildRequest(
                cell_id=self.resolve_cell_id(facts),
                raw_fields=self.resolve_raw_fields(facts),
                env_state=facts.env_state,
                config=config,
                dig_cut_prior=dig_cut_prior,
                state_exemplar_profile_token=state_exemplar_profile_token,
            )
        )

    @staticmethod
    def build_live_token(request: DigDepthProfileBuildRequest) -> np.ndarray:
        return build_dig_depth_profile_token_from_plan(
            raw_fields=request.raw_fields,
            cell_id=int(request.cell_id),
            env_state=request.env_state,
            effective_deposit_delta_kg=float(
                request.raw_fields.get(
                    "operator_effective_deposit_delta_kg",
                    request.raw_fields.get("operator_cut_payload_gain_kg", 0.0),
                )
            ),
        )

    def prior_token(
        self,
        dig_cut_prior: dict[str, Any] | None,
        *,
        cell_id: int,
        allow_global_fallback: bool,
    ) -> tuple[np.ndarray | None, str, str]:
        mapping, source, reason = self.prior_mapping(
            dig_cut_prior,
            cell_id=cell_id,
            allow_global_fallback=allow_global_fallback,
        )
        if mapping is None:
            return None, source, reason
        token = self.token_from_prior_mapping(mapping)
        if token is None:
            return None, source, f"{source} prior has no token_median/token field"
        if source == "cell":
            return token, f"qc6_dig_depth_profile_cell_{int(cell_id)}", ""
        return token, "qc6_dig_depth_profile_global", ""

    @staticmethod
    def prior_mapping(
        dig_cut_prior: dict[str, Any] | None,
        *,
        cell_id: int,
        allow_global_fallback: bool,
    ) -> tuple[dict[str, object] | None, str, str]:
        if not dig_cut_prior:
            return None, "missing_dig_cut_prior", "missing dig_cut_prior"
        cells = dig_cut_prior.get("dig_depth_profile_cells", [])
        if isinstance(cells, list):
            for item in cells:
                if not isinstance(item, dict):
                    continue
                cell = dict(item)
                if int(cell.get("cell_id", -999999)) == int(cell_id):
                    return cell, "cell", ""
        if bool(allow_global_fallback):
            global_prior = dig_cut_prior.get("dig_depth_profile_global")
            if isinstance(global_prior, dict):
                return dict(global_prior), "global", ""
        return (
            None,
            "missing_dig_depth_profile_prior",
            f"missing dig_depth_profile_cells entry for cell {int(cell_id)}",
        )

    @staticmethod
    def token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        for key in ("token_median", "token", "median"):
            if key not in mapping:
                continue
            token = np.asarray(mapping[key], dtype=np.float32).reshape(-1)
            try:
                token = validate_primitive_token_shape(
                    DIG_DEPTH_PROFILE_TOKEN_KEY,
                    token,
                    allow_sequence=False,
                ).reshape(-1)
            except ValueError as exc:
                raise ValueError(
                    "dig_depth_profile prior token must have "
                    f"{DIG_DEPTH_PROFILE_TOKEN_DIM} values, got {token.shape[0]}"
                ) from exc
            if not np.all(np.isfinite(token)):
                raise ValueError("dig_depth_profile prior token contains non-finite values")
            return token.copy()
        return None
