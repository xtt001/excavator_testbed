"""Return start-envelope prior and gate-prior context helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    validate_primitive_token_shape,
)


class ReturnStartEnvelopePriorConfig(Protocol):
    gate_enabled: bool
    use_cell_prior: bool
    min_source_count: int
    min_source_fraction: float


@dataclass(frozen=True)
class ReturnStartEnvelopeGatePriorContext:
    token_has_bounds: bool = False
    cell_id: int | None = None
    prior_mapping: dict[str, object] | None = None
    lower: np.ndarray | None = None
    upper: np.ndarray | None = None


def return_start_envelope_token_has_gate_bounds(
    token: Any,
    config: ReturnStartEnvelopePriorConfig,
) -> bool:
    if not bool(config.gate_enabled):
        return False
    token_arr = np.asarray(token, dtype=np.float32).reshape(-1)
    if token_arr.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
        return False
    return not (
        float(token_arr[RETURN_ENVELOPE_QPOS_VALID_IDX]) <= 0.5
        and float(token_arr[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]) <= 0.5
    )


def return_start_envelope_gate_prior_context(
    *,
    token: Any,
    dig_cut_prior: dict[str, Any] | None,
    config: ReturnStartEnvelopePriorConfig,
    cell_id: int | None,
) -> ReturnStartEnvelopeGatePriorContext:
    token_has_bounds = return_start_envelope_token_has_gate_bounds(token, config)
    if not token_has_bounds:
        return ReturnStartEnvelopeGatePriorContext(
            token_has_bounds=False,
            cell_id=cell_id,
        )
    mapping, _ = return_start_envelope_prior_mapping(
        dig_cut_prior,
        config=config,
        cell_id=cell_id,
    )
    lower, upper = return_start_envelope_prior_bounds(mapping)
    return ReturnStartEnvelopeGatePriorContext(
        token_has_bounds=True,
        cell_id=cell_id,
        prior_mapping=mapping,
        lower=lower,
        upper=upper,
    )


def return_start_envelope_prior_mapping(
    dig_cut_prior: dict[str, Any] | None,
    *,
    config: ReturnStartEnvelopePriorConfig,
    cell_id: int | None,
) -> tuple[dict[str, object] | None, str]:
    if not dig_cut_prior:
        return None, "missing_dig_cut_prior"
    cells = dig_cut_prior.get("return_start_envelope_cells", [])
    if config.use_cell_prior and cell_id is not None and isinstance(cells, list):
        for cell in cells:
            cell_dict = dict(cell)
            if int(cell_dict.get("cell_id", -999999)) == int(cell_id):
                source_count = int(cell_dict.get("source_count", 0) or 0)
                source_fraction = float(cell_dict.get("source_fraction", 0.0) or 0.0)
                if (
                    source_count >= config.min_source_count
                    and source_fraction >= config.min_source_fraction
                ):
                    return cell_dict, "cell"
                break
    global_prior = dig_cut_prior.get("return_start_envelope_global")
    if isinstance(global_prior, dict):
        if config.use_cell_prior and cell_id is not None and isinstance(cells, list):
            return dict(global_prior), "global_low_support_cell"
        return dict(global_prior), "global"
    return None, "missing_return_start_envelope_prior"


def return_start_envelope_prior_token(
    mapping: dict[str, object] | None,
    *,
    source: str,
    cell_id: int | None,
) -> tuple[np.ndarray | None, str]:
    if mapping is not None:
        token = return_start_envelope_token_from_prior_mapping(mapping)
        if token is not None:
            if cell_id is not None and source == "cell":
                return token, f"qc6_return_start_envelope_cell_{int(cell_id)}"
            if cell_id is not None and source == "global_low_support_cell":
                return (
                    token,
                    f"qc6_return_start_envelope_global_low_support_cell_{int(cell_id)}",
                )
            return token, "qc6_return_start_envelope_global"
    return None, "missing_return_start_envelope_prior"


def return_start_envelope_prior_bounds(
    mapping: dict[str, object] | None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if mapping is None:
        return None, None
    if "token_p05" not in mapping or "token_p95" not in mapping:
        return None, None
    lower = np.asarray(mapping["token_p05"], dtype=np.float32).reshape(-1)
    upper = np.asarray(mapping["token_p95"], dtype=np.float32).reshape(-1)
    if (
        lower.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM
        or upper.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM
    ):
        return None, None
    return lower.copy(), upper.copy()


def return_start_envelope_token_from_prior_mapping(
    mapping: dict[str, object],
) -> np.ndarray | None:
    for key in ("token_median", "token", "median"):
        if key not in mapping:
            continue
        token = np.asarray(mapping[key], dtype=np.float32).reshape(-1)
        try:
            token = validate_primitive_token_shape(
                RETURN_START_ENVELOPE_TOKEN_KEY,
                token,
                allow_sequence=False,
            ).reshape(-1)
        except ValueError as exc:
            raise ValueError(
                "return_start_envelope prior token must have "
                f"{RETURN_START_ENVELOPE_TOKEN_DIM} values, got {token.shape[0]}"
            ) from exc
        return token.copy()
    return None
