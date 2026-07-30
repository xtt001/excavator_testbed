"""Load replay-candidate cycles while preserving full causal episode prefixes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py

from testbed.backends.agx.protocol import (
    CONTROL_COMPATIBILITY_PROFILES,
    PRODUCTION_CONTROL_PROFILE,
    RECORDING_PRE_FIX_CONTROL_PROFILE,
)

POST_FIX_RAW_SELECTION_PROFILE = "post_fix_raw"
CALIBRATED_MIXED_SELECTION_PROFILE = "calibrated_mixed_current_equivalent"
STRICT_REPLAY_EVIDENCE_PROFILE = "strict_replay_v1"
CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE = (
    "replay_corrected_partial_salvage_v1"
)
REPLAY_EVIDENCE_PROFILES = (
    STRICT_REPLAY_EVIDENCE_PROFILE,
    CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE,
)


@dataclass(frozen=True)
class ReplaySelectionProfile:
    """Closed allowlist and metadata contract for replay source selection."""

    name: str
    approved_source_root: Path
    allowed_controller_epochs: tuple[str, ...]
    expected_episode_ids: tuple[int, ...] | None = None
    required_action_contract: str | None = None
    required_raw_source_root: Path | None = None
    required_clean_source_root: Path | None = None


@dataclass(frozen=True)
class ReplayEpisodeSelection:
    source_episode_id: str
    source_path: Path
    start_step: int
    end_step_exclusive: int
    cycle_ids: tuple[int, ...]


def load_replay_selection(
    manifest_path: str | Path,
    *,
    approved_source_root: str | Path | None = None,
    required_epoch: str = "post_fix_candidate",
    included_episode_ids: tuple[str, ...] | None = None,
    selection_profile: ReplaySelectionProfile | str | None = None,
) -> list[ReplayEpisodeSelection]:
    path = Path(manifest_path)
    rows = _load_cycle_rows(path)
    profile = resolve_replay_selection_profile(selection_profile)
    if profile is not None:
        approved = Path(profile.approved_source_root).expanduser().resolve()
        allowed_epochs = set(profile.allowed_controller_epochs)
    else:
        if approved_source_root is None:
            raise ValueError(
                "approved_source_root is required without a selection profile."
            )
        approved = Path(approved_source_root).expanduser().resolve()
        allowed_epochs = {str(required_epoch)} if required_epoch else set()
    included = (
        None
        if included_episode_ids is None
        else {str(value) for value in included_episode_ids}
    )
    grouped: dict[tuple[str, Path], dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"cycles[{index}] must be an object.")
        if not bool(raw.get("replay_candidate", False)):
            continue
        epoch = str(raw.get("controller_epoch", ""))
        if allowed_epochs and epoch not in allowed_epochs:
            continue
        source = Path(str(raw.get("source_path", ""))).expanduser().resolve()
        try:
            source.relative_to(approved)
        except ValueError as exc:
            raise ValueError(
                f"Replay source is outside approved source root: {source}"
            ) from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        episode_id = str(raw.get("source_episode_id", "")).strip()
        if not episode_id:
            raise ValueError(f"cycles[{index}].source_episode_id is required.")
        episode_number = _episode_number(episode_id)
        if (
            profile is not None
            and profile.expected_episode_ids is not None
            and episode_number not in set(profile.expected_episode_ids)
        ):
            raise ValueError(
                f"Replay episode {episode_id} is outside fixed episode inventory "
                f"for selection profile {profile.name}."
            )
        if source.name != f"episode_{episode_number}.hdf5":
            raise ValueError(
                f"Replay source filename does not match source_episode_id: {source}"
            )
        if profile is not None:
            _validate_profile_source(source, profile=profile)
        if included is not None and episode_id not in included:
            continue
        cycle_id = int(raw["cycle_id"])
        end = int(raw["end_step_exclusive"])
        if end <= 0:
            raise ValueError(f"cycles[{index}].end_step_exclusive must be positive.")
        key = (episode_id, source)
        entry = grouped.setdefault(key, {"end": 0, "cycle_ids": []})
        entry["end"] = max(int(entry["end"]), end)
        entry["cycle_ids"].append(cycle_id)

    selections = [
        ReplayEpisodeSelection(
            source_episode_id=episode_id,
            source_path=source,
            start_step=0,
            end_step_exclusive=int(entry["end"]),
            cycle_ids=tuple(sorted(set(int(value) for value in entry["cycle_ids"]))),
        )
        for (episode_id, source), entry in grouped.items()
    ]
    selections.sort(key=lambda item: _episode_sort_key(item.source_episode_id))
    return selections


def resolve_replay_selection_profile(
    value: ReplaySelectionProfile | str | None,
) -> ReplaySelectionProfile | None:
    if value is None:
        return None
    if isinstance(value, ReplaySelectionProfile):
        return value
    name = str(value).strip()
    if name == POST_FIX_RAW_SELECTION_PROFILE:
        from testbed.data.terrain_cycle_cleaning import APPROVED_TERRAIN_DATASET_ROOT

        return ReplaySelectionProfile(
            name=name,
            approved_source_root=APPROVED_TERRAIN_DATASET_ROOT,
            allowed_controller_epochs=("post_fix_candidate",),
        )
    if name == CALIBRATED_MIXED_SELECTION_PROFILE:
        from testbed.data.action_contract_calibration import (
            APPROVED_CLEAN_DATASET_ROOT,
            CURRENT_EQUIVALENT_ACTION_CONTRACT,
            DEFAULT_CALIBRATED_OUTPUT_ROOT,
            POST_REFERENCE_EPISODE_IDS,
            PRE_CALIBRATION_EPISODE_IDS,
        )
        from testbed.data.terrain_cycle_cleaning import APPROVED_TERRAIN_DATASET_ROOT

        return ReplaySelectionProfile(
            name=name,
            approved_source_root=(
                DEFAULT_CALIBRATED_OUTPUT_ROOT / "mixed_current_equivalent_vds"
            ),
            allowed_controller_epochs=(
                "pre_fix_candidate",
                "post_fix_candidate",
            ),
            expected_episode_ids=(
                *PRE_CALIBRATION_EPISODE_IDS,
                *POST_REFERENCE_EPISODE_IDS,
            ),
            required_action_contract=CURRENT_EQUIVALENT_ACTION_CONTRACT,
            required_raw_source_root=APPROVED_TERRAIN_DATASET_ROOT,
            required_clean_source_root=APPROVED_CLEAN_DATASET_ROOT,
        )
    raise ValueError(f"Unknown replay selection profile: {name}")


def validate_control_compatibility_selection(
    *,
    control_profile: str | None,
    selection_profile: str,
    selections: Sequence[ReplayEpisodeSelection],
) -> list[str]:
    """Keep recording-era execution semantics inside the fixed pre source pool."""

    profile = (
        PRODUCTION_CONTROL_PROFILE
        if control_profile in (None, "")
        else str(control_profile)
    )
    if profile not in CONTROL_COMPATIBILITY_PROFILES:
        return [f"Unknown replay control compatibility profile: {profile}"]
    if profile == PRODUCTION_CONTROL_PROFILE:
        return []
    if selection_profile != CALIBRATED_MIXED_SELECTION_PROFILE:
        return [
            f"{RECORDING_PRE_FIX_CONTROL_PROFILE} requires "
            f"--selection-profile {CALIBRATED_MIXED_SELECTION_PROFILE}."
        ]

    from testbed.data.action_contract_calibration import (
        PRE_CALIBRATION_EPISODE_IDS,
    )

    allowed = set(PRE_CALIBRATION_EPISODE_IDS)
    outside = [
        item.source_episode_id
        for item in selections
        if _episode_number(item.source_episode_id) not in allowed
    ]
    if outside:
        return [
            f"{RECORDING_PRE_FIX_CONTROL_PROFILE} is limited to the fixed "
            f"pre-calibration source pool; rejected {sorted(outside)}."
        ]
    return []


def validate_replay_evidence_profile(
    *,
    evidence_profile: str,
    selection_manifest_present: bool,
    selection_profile: str,
    realign_on_qpos_error: bool,
    selected_episode_count: int,
    record_output_present: bool,
    diagnostic_log_present: bool,
    gold_cycle_samples_present: bool = True,
    realign_axis: str | None = None,
    realign_error_threshold: float | None = None,
    realign_hold_steps: int | None = None,
    realign_min_steps_between: int | None = None,
    realign_burn_in_steps: int | None = None,
    realign_max_count: int | None = None,
) -> list[str]:
    """Keep pose-corrected replay explicit and outside strict evidence."""

    profile = str(evidence_profile)
    if profile not in REPLAY_EVIDENCE_PROFILES:
        return [f"Unknown replay evidence profile: {profile}"]
    if profile == STRICT_REPLAY_EVIDENCE_PROFILE:
        if selection_manifest_present and realign_on_qpos_error:
            return [
                "--selection-manifest forbids pose realignment under strict replay evidence."
            ]
        return []
    errors: list[str] = []
    if not selection_manifest_present:
        errors.append("Corrected partial salvage requires --selection-manifest.")
    if selection_profile != CALIBRATED_MIXED_SELECTION_PROFILE:
        errors.append(
            "Corrected partial salvage requires calibrated_mixed_current_equivalent."
        )
    if not realign_on_qpos_error:
        errors.append("Corrected partial salvage requires --realign-on-qpos-error.")
    if int(selected_episode_count) != 1:
        errors.append("Corrected partial salvage requires exactly one selected episode.")
    if not record_output_present:
        errors.append("Corrected partial salvage requires --record-output-dir.")
    if not diagnostic_log_present:
        errors.append("Corrected partial salvage requires --diagnostic-log.")
    if not gold_cycle_samples_present:
        errors.append("Corrected partial salvage requires the three-target sidecar.")
    expected_realign = {
        "axis": (str(realign_axis), "all"),
        "threshold": (realign_error_threshold, 0.04),
        "hold steps": (realign_hold_steps, 3),
        "minimum step gap": (realign_min_steps_between, 200),
        "burn-in steps": (realign_burn_in_steps, 15),
        "maximum count": (realign_max_count, 20),
    }
    for label, (actual, expected) in expected_realign.items():
        if actual != expected:
            errors.append(
                f"Corrected partial salvage realign {label} must be {expected!r}."
            )
    return errors


def _validate_profile_source(
    source: Path,
    *,
    profile: ReplaySelectionProfile,
) -> None:
    if profile.required_action_contract is None and (
        profile.required_raw_source_root is None
        and profile.required_clean_source_root is None
    ):
        return
    try:
        with h5py.File(source, "r") as handle:
            metadata = handle["metadata"].attrs
            if profile.required_action_contract is not None:
                actual = str(metadata.get("action_contract", ""))
                if actual != profile.required_action_contract:
                    raise ValueError(
                        f"Replay source action contract {actual!r} does not match "
                        f"{profile.required_action_contract!r}: {source}"
                    )
            if profile.required_raw_source_root is not None:
                _validate_metadata_path(
                    metadata.get("raw_source_realpath", ""),
                    approved_root=profile.required_raw_source_root,
                    label="raw source",
                    source=source,
                )
            if profile.required_clean_source_root is not None:
                _validate_metadata_path(
                    metadata.get("vds_source_abs_path", ""),
                    approved_root=profile.required_clean_source_root,
                    label="clean source",
                    source=source,
                )
    except OSError as exc:
        raise ValueError(
            f"Replay source is not a readable HDF5 file: {source}"
        ) from exc


def _validate_metadata_path(
    value: Any,
    *,
    approved_root: Path,
    label: str,
    source: Path,
) -> None:
    path = Path(str(value)).expanduser().resolve()
    approved = Path(approved_root).expanduser().resolve()
    try:
        path.relative_to(approved)
    except ValueError as exc:
        raise ValueError(
            f"Replay {label} lineage escapes approved root for {source}: {path}"
        ) from exc
    if not path.is_file():
        raise FileNotFoundError(path)


def _load_cycle_rows(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("cycles", [])
        else:
            raise ValueError(
                "Replay selection manifest must be a JSON object/list or JSONL."
            )
    if not isinstance(rows, list):
        raise ValueError("Replay selection manifest cycles must be a list.")
    return rows


def _episode_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value.rsplit("_", 1)[1]), value
    except (IndexError, ValueError):
        return 10**9, value


def _episode_number(value: str) -> int:
    try:
        return int(str(value).rsplit("_", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Invalid source episode id: {value!r}") from exc


__all__ = [
    "CALIBRATED_MIXED_SELECTION_PROFILE",
    "CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE",
    "POST_FIX_RAW_SELECTION_PROFILE",
    "REPLAY_EVIDENCE_PROFILES",
    "ReplayEpisodeSelection",
    "ReplaySelectionProfile",
    "load_replay_selection",
    "resolve_replay_selection_profile",
    "validate_control_compatibility_selection",
    "validate_replay_evidence_profile",
]
