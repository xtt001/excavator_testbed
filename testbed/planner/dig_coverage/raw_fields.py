"""Coverage raw-field helpers."""

from __future__ import annotations

from .models import *


class CoverageRawFieldsMixin:
    def raw_fields_in_prior_range(
        self,
        raw_fields: dict[str, float | int],
    ) -> bool:
        if not self.dig_cut_prior:
            return False
        fields = dict(self.dig_cut_prior.get("fields", {}))
        mapping = {
            "operator_entry_x_m": "entry_x_m",
            "operator_entry_z_m": "entry_z_m",
            "operator_exit_x_m": "exit_x_m",
            "operator_exit_z_m": "exit_z_m",
            "operator_cut_direction_x": "cut_direction_x",
            "operator_cut_direction_z": "cut_direction_z",
            "operator_cut_length_m": "cut_length_m",
            "operator_cut_depth_peak_m": "cut_depth_peak_m",
            "operator_cut_payload_gain_kg": "payload_gain_kg",
        }
        for raw_name, prior_name in mapping.items():
            value = float(raw_fields.get(raw_name, np.nan))
            lo = self._prior_percentile(fields, prior_name, "p10")
            hi = self._prior_percentile(fields, prior_name, "p90")
            if not np.isfinite(value) or value < lo - 1.0e-6 or value > hi + 1.0e-6:
                return False
        return True

    def _coverage_raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        facts: CoverageObservationFacts | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        if facts is not None:
            state_plan = self._coverage_state_conditioned_plan(
                corridor,
                facts,
                update_state=update_state,
            )
            if state_plan is not None:
                return dict(state_plan["raw_fields"])
        fields = dict(self.dig_cut_prior.get("fields", {}))
        entry_x = self._clamp_to_prior(fields, "entry_x_m", corridor.entry_x_m)
        entry_z = self._clamp_to_prior(fields, "entry_z_m", corridor.entry_z_m)
        exit_x = self._clamp_to_prior(fields, "exit_x_m", corridor.exit_x_m)
        exit_z = self._clamp_to_prior(fields, "exit_z_m", corridor.exit_z_m)
        delta_x = exit_x - entry_x
        delta_z = exit_z - entry_z
        length = float(np.hypot(delta_x, delta_z))
        if length <= 1.0e-6:
            dir_x = self._prior_percentile(
                fields,
                "cut_direction_x",
                self.coverage_cut_direction_percentile,
            )
            dir_z = self._prior_percentile(
                fields,
                "cut_direction_z",
                self.coverage_cut_direction_percentile,
            )
            length = self._prior_percentile(
                fields,
                "cut_length_m",
                self.coverage_cut_length_percentile,
            )
        else:
            dir_x = delta_x / length
            dir_z = delta_z / length
        return {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(
                self._clamp_to_prior(fields, "cut_direction_x", dir_x)
            ),
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": float(
                self._clamp_to_prior(fields, "cut_direction_z", dir_z)
            ),
            "operator_cut_length_m": float(
                self._clamp_to_prior(fields, "cut_length_m", length)
            ),
            "operator_cut_depth_peak_m": float(
                self._clamp_to_prior(
                    fields,
                    "cut_depth_peak_m",
                    float(corridor.cut_depth_peak_m)
                    if np.isfinite(corridor.cut_depth_peak_m)
                    else self._prior_percentile(
                        fields,
                        "cut_depth_peak_m",
                        self.coverage_cut_depth_percentile,
                    ),
                )
            ),
            "operator_cut_payload_gain_kg": float(
                self._clamp_to_prior(
                    fields,
                    "payload_gain_kg",
                    float(corridor.payload_gain_kg)
                    if np.isfinite(corridor.payload_gain_kg)
                    else self._prior_percentile(
                        fields,
                        "payload_gain_kg",
                        self.coverage_payload_percentile,
                    ),
                )
            ),
            "operator_effective_deposit_delta_kg": float(
                self._clamp_to_prior(
                    fields,
                    "effective_deposit_delta_kg",
                    float(corridor.effective_deposit_delta_kg)
                    if np.isfinite(corridor.effective_deposit_delta_kg)
                    else self._prior_percentile(
                        fields,
                        "effective_deposit_delta_kg",
                        "p50",
                    ),
                )
            ),
            "operator_cut_valid": 1,
        }
