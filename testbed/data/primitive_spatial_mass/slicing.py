"""Top-level spatial-mass primitive slice assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np

from testbed.data.primitive_records import PrimitiveRejectRecord, PrimitiveSlice

from .common import *
from .dig import (
    find_spatial_mass_dig_end,
    find_spatial_mass_dig_start,
)
from .dump import (
    find_spatial_mass_dump_end,
    find_spatial_mass_dump_start,
    find_spatial_mass_release_onset,
    spatial_mass_carry_contaminated,
    spatial_mass_carry_qc,
    spatial_mass_dump_qc,
)
from .return_envelope import (
    build_return_start_envelope_token,
    find_spatial_mass_return_entry_ready,
)

def split_spatial_mass_primitive_slices(
    *,
    episode: dict[str, Any],
    source_episode_id: int,
    source_dataset_dir: str | Path,
    raw_cycle_windows: list[tuple[int, int, int, int]],
    pose_realign_steps: Iterable[int] = (),
    return_max_transition_len: int | None = None,
) -> tuple[list[PrimitiveSlice], list[PrimitiveRejectRecord]]:
    """Split a full V2.4/V2.4.5 raw episode using material-cycle ownership."""
    source_dataset_dir = Path(source_dataset_dir)
    windows = spatial_mass_material_windows(
        episode=episode,
        windows=raw_cycle_windows,
    )
    slices: list[PrimitiveSlice] = []
    rejects: list[PrimitiveRejectRecord] = []
    if not windows:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name="cycle",
                reason="missing_material_cycle_windows",
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=-1,
                start_step=0,
                end_step_exclusive=int(len(episode.get("actions", []))),
            )
        )
        return slices, rejects

    realign_steps = tuple(int(step) for step in pose_realign_steps)

    def _reject(
        *,
        primitive_name: str,
        reason: str,
        source_cycle_id: int,
        start: int,
        end: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        rejects.append(
            PrimitiveRejectRecord(
                primitive_name=primitive_name,
                reason=reason,
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(start),
                end_step_exclusive=int(end),
                details=details,
            )
        )

    def _append(
        *,
        primitive_name: str,
        window_name: str,
        source_cycle_id: int,
        start: int,
        end: int,
        source_prev_cycle_id: int | None = None,
        source_next_cycle_id: int | None = None,
        carry_qc: dict[str, Any] | None = None,
        dump_qc: dict[str, Any] | None = None,
        return_qc: dict[str, Any] | None = None,
        overlay: dict[str, np.ndarray] | None = None,
        reject_reason: str = "invalid_spatial_mass_window",
    ) -> None:
        if int(end) <= int(start):
            _reject(
                primitive_name=primitive_name,
                reason=reject_reason,
                source_cycle_id=source_cycle_id,
                start=start,
                end=end,
                details=carry_qc or dump_qc or return_qc,
            )
            return
        slices.append(
            PrimitiveSlice(
                primitive_name=primitive_name,
                window_name=window_name,
                source_episode_id=int(source_episode_id),
                source_cycle_id=int(source_cycle_id),
                start_step=int(start),
                end_step_exclusive=int(end),
                source_dataset_dir=str(source_dataset_dir.resolve()),
                source_prev_cycle_id=source_prev_cycle_id,
                source_next_cycle_id=source_next_cycle_id,
                carry_qc=carry_qc,
                dump_qc=dump_qc,
                return_qc=return_qc,
                v2_step_overlay=overlay,
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            )
        )

    for index, (cycle_id, start, work_end, _realign_end) in enumerate(windows):
        source_cycle_id = int(cycle_id)
        next_start = int(windows[index + 1][1]) if index + 1 < len(windows) else None
        next_work_end = (
            int(windows[index + 1][2]) if index + 1 < len(windows) else None
        )
        work_realign = window_pose_realign_steps(
            realign_steps=realign_steps,
            start_step=start,
            end_step_exclusive=work_end,
        )
        if work_realign:
            details = {
                "realign_steps_in_window": [int(step) for step in work_realign],
                "realign_all_steps": [int(step) for step in realign_steps],
                "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
                "policy": "discard_spatial_mass_work_windows_only",
            }
            for primitive_name in ("dig", "carry", "dump"):
                _reject(
                    primitive_name=primitive_name,
                    reason=POSE_REALIGN_CYCLE_REJECT_REASON,
                    source_cycle_id=source_cycle_id,
                    start=start,
                    end=work_end,
                    details=details,
                )
            continue

        release_onset, release_qc = find_spatial_mass_release_onset(
            episode=episode,
            start=int(start),
            end=int(work_end),
        )
        if release_onset is None:
            for primitive_name in ("carry", "dump"):
                _reject(
                    primitive_name=primitive_name,
                    reason="missing_spatial_mass_release_onset",
                    source_cycle_id=source_cycle_id,
                    start=start,
                    end=work_end,
                    details=release_qc,
                )
            release_onset = int(work_end)

        dig_start, dig_qc = find_spatial_mass_dig_start(
            episode=episode,
            start=int(start),
            end=int(work_end),
        )
        dump_start, dump_start_qc = find_spatial_mass_dump_start(
            episode=episode,
            cycle_start=int(start),
            release_onset=int(release_onset),
        )
        dump_start = min(int(dump_start), int(work_end))
        dump_end, dump_end_qc = find_spatial_mass_dump_end(
            episode=episode,
            search_end=int(work_end),
            release_onset=int(release_onset),
        )
        dump_end = max(int(dump_start) + 1, min(int(dump_end), int(work_end)))
        dig_end, dig_end_qc = find_spatial_mass_dig_end(
            episode=episode,
            start=int(dig_start),
            end=int(dump_start),
        )
        dig_end = max(int(dig_start) + 1, min(int(dig_end), int(dump_start)))
        dig_qc.update(dig_end_qc)
        carry_start = int(dig_end)

        _append(
            primitive_name="dig",
            window_name=SPATIAL_MASS_DIG_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            start=int(dig_start),
            end=int(dig_end),
            dump_qc=dig_qc,
            reject_reason="invalid_spatial_mass_dig_window",
        )

        carry_qc = spatial_mass_carry_qc(
            episode=episode,
            start=int(carry_start),
            end=int(dump_start),
            release_onset=int(release_onset),
        )
        if spatial_mass_carry_contaminated(carry_qc):
            _reject(
                primitive_name="carry",
                reason="carry_deposit_contamination_before_dump",
                source_cycle_id=source_cycle_id,
                start=carry_start,
                end=dump_start,
                details=carry_qc,
            )
        else:
            _append(
                primitive_name="carry",
                window_name=SPATIAL_MASS_CARRY_WINDOW_NAME,
                source_cycle_id=source_cycle_id,
                start=int(carry_start),
                end=int(dump_start),
                carry_qc=carry_qc,
                reject_reason="invalid_spatial_mass_carry_window",
            )

        dump_qc = spatial_mass_dump_qc(
            episode=episode,
            start=int(dump_start),
            end=int(dump_end),
            release_onset=int(release_onset),
            release_qc={**release_qc, **dump_start_qc, **dump_end_qc},
        )
        _append(
            primitive_name="dump",
            window_name=SPATIAL_MASS_DUMP_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            start=int(dump_start),
            end=int(dump_end),
            dump_qc=dump_qc,
            reject_reason="invalid_spatial_mass_dump_window",
        )

        if next_start is None:
            _reject(
                primitive_name="return",
                reason="terminal_return_reject",
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(dump_end),
                details={"policy": "return requires a next material dig start"},
            )
            continue
        return_handoff_step, return_end_qc = find_spatial_mass_return_entry_ready(
            episode=episode,
            start=int(dump_end),
            next_start=int(next_start),
            next_work_end=int(next_work_end if next_work_end is not None else next_start),
        )
        return_end = min(int(len(episode["actions"])), int(return_handoff_step) + 1)
        return_realign = window_pose_realign_steps(
            realign_steps=realign_steps,
            start_step=int(dump_end),
            end_step_exclusive=int(return_end),
        )
        if return_realign:
            _reject(
                primitive_name="return",
                reason=POSE_REALIGN_TRANSITION_REJECT_REASON,
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(return_end),
                details={
                    "realign_steps_in_window": [
                        int(step) for step in return_realign
                    ],
                    "realign_all_steps": [int(step) for step in realign_steps],
                    "realign_metadata_key": POSE_REALIGN_METADATA_KEY,
                    "policy": "discard_return_transition_window",
                    "next_cycle_id": int(windows[index + 1][0]),
                    **return_end_qc,
                },
            )
            continue
        if (
            return_max_transition_len is not None
            and int(return_end) - int(dump_end) > int(return_max_transition_len)
        ):
            _reject(
                primitive_name="return",
                reason="overlong_transition_len",
                source_cycle_id=source_cycle_id,
                start=int(dump_end),
                end=int(return_end),
                details={
                    "window_len": int(return_end) - int(dump_end),
                    "max_transition_len": int(return_max_transition_len),
                    **return_end_qc,
                },
            )
            continue
        token, valid_mask, return_qc = build_return_start_envelope_token(
            episode=episode,
            next_start_step=int(return_handoff_step),
        )
        return_qc.update(return_end_qc)
        return_len = int(return_end) - int(dump_end)
        return_qc.update(
            {
                "return_start_step": int(dump_end),
                "return_end_step_exclusive": int(return_end),
                "return_window_len": int(return_len),
                "return_next_material_cycle_id": int(windows[index + 1][0]),
                "return_next_material_start_step": int(next_start),
                "return_handoff_step": int(return_handoff_step),
                "return_start_envelope_schema": RETURN_START_ENVELOPE_TOKEN_KEY,
            }
        )
        overlay = {
            primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY).rsplit(
                "/", 1
            )[-1]: np.repeat(
                token.reshape(1, -1),
                return_len,
                axis=0,
            ).astype(np.float32),
            primitive_token_dataset_path(RETURN_START_ENVELOPE_VALID_MASK_KEY).rsplit(
                "/", 1
            )[-1]: np.repeat(
                valid_mask.reshape(1, -1),
                return_len,
                axis=0,
            ).astype(np.uint8),
        }
        _append(
            primitive_name="return",
            window_name=SPATIAL_MASS_RETURN_WINDOW_NAME,
            source_cycle_id=source_cycle_id,
            source_prev_cycle_id=source_cycle_id,
            source_next_cycle_id=int(windows[index + 1][0]),
            start=int(dump_end),
            end=int(return_end),
            return_qc=return_qc,
            overlay=overlay,
            reject_reason="invalid_spatial_mass_return_window",
        )

    return slices, rejects

def spatial_mass_material_windows(
    *,
    episode: dict[str, Any],
    windows: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    step = dict(dict(episode.get("v2") or {}).get("step", {}) or {})
    qds = np.asarray(step.get("qualified_dig_start_mask", []), dtype=np.uint8).reshape(-1)
    dump_end = np.asarray(step.get("dump_end_mask", []), dtype=np.uint8).reshape(-1)
    if qds.size <= 0 or not windows:
        return windows
    material_windows: list[tuple[int, int, int, int]] = []
    for cycle_id, start, work_end, realign_end in windows:
        qds_indices = np.flatnonzero(qds.astype(bool))
        qds_indices = qds_indices[(qds_indices >= int(start)) & (qds_indices < int(work_end))]
        if len(qds_indices) <= 1:
            material_windows.append((cycle_id, start, work_end, realign_end))
            continue
        if int(qds_indices[0]) != int(start):
            qds_indices = np.concatenate(
                [np.asarray([int(start)], dtype=np.int64), qds_indices]
            )
        for sub_index, sub_start_value in enumerate(qds_indices):
            sub_start = int(sub_start_value)
            next_start = (
                int(qds_indices[sub_index + 1])
                if sub_index + 1 < len(qds_indices)
                else None
            )
            sub_limit = int(work_end if next_start is None else next_start)
            sub_end = sub_limit
            if dump_end.size:
                dump_candidates = np.flatnonzero(dump_end.astype(bool))
                dump_candidates = dump_candidates[
                    (dump_candidates >= sub_start) & (dump_candidates < sub_limit)
                ]
                if len(dump_candidates) > 0:
                    sub_end = min(sub_limit, int(dump_candidates[0]) + 1)
            if sub_end <= sub_start:
                continue
            sub_realign_end = int(realign_end if next_start is None else next_start)
            material_windows.append((int(cycle_id), sub_start, sub_end, sub_realign_end))
    return sorted(material_windows, key=lambda item: item[1])

__all__ = [
    "split_spatial_mass_primitive_slices",
    "spatial_mass_material_windows",
]
