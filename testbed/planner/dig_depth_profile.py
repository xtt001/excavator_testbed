"""Dig depth-profile token source selection for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    validate_primitive_token_shape,
)
from testbed.data.dig_depth_profile_v2_4 import (
    build_dig_depth_profile_token_from_plan,
)


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
