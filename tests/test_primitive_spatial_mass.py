from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_DEPTH_CENTER_IDX,
    RETURN_ENVELOPE_DEPTH_MAX_IDX,
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_QPOS_CENTER_SLICE,
    RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_QVEL_ABS_MAX_IDX,
    RETURN_ENVELOPE_SHORT_NORM_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_START_ENVELOPE_VALID_MASK_KEY,
    primitive_token_dataset_path,
)
from testbed.data.primitive_spatial_mass import (
    SPATIAL_MASS_CARRY_WINDOW_NAME,
    SPATIAL_MASS_DIG_WINDOW_NAME,
    SPATIAL_MASS_DUMP_WINDOW_NAME,
    SPATIAL_MASS_RETURN_WINDOW_NAME,
    build_return_start_envelope_token,
    find_spatial_mass_dig_end,
    find_spatial_mass_dig_start,
    find_spatial_mass_dump_end,
    find_spatial_mass_dump_start,
    find_spatial_mass_return_entry_ready,
    split_spatial_mass_primitive_slices,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)


def test_dig_start_uses_first_contact_or_depth_and_missing_env_fallback() -> None:
    episode = _episode(24)
    env = episode["env_state"]
    env[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[5, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0

    step, qc = find_spatial_mass_dig_start(episode=episode, start=0, end=20)

    assert step == 5
    assert qc["dig_start_source"] == "first_dig_contact_or_depth"
    fallback_step, fallback_qc = find_spatial_mass_dig_start(
        episode={"actions": np.zeros((12, 4), dtype=np.float32)},
        start=3,
        end=10,
    )
    assert fallback_step == 3
    assert fallback_qc["dig_start_source"] == "cycle_start_missing_env_state"


def test_dig_end_detects_mass_plateau_departure_and_search_end_fallback() -> None:
    episode = _episode(48)
    env = episode["env_state"]
    env[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0
    env[:, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0
    env[:, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.02
    env[:12, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(0.0, 20.0, 12)
    env[12:, ENV_STATE_MASS_IN_BUCKET_IDX] = 20.0
    env[16:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.20
    env[16:, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 0.0
    env[16:, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.0

    step, qc = find_spatial_mass_dig_end(episode=episode, start=0, end=40)

    assert step == 16
    assert qc["dig_end_source"] == "mass_plateau_and_dig_area_departure"

    no_departure = _episode(30)
    no_departure["env_state"][:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    no_departure["env_state"][:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0
    step, qc = find_spatial_mass_dig_end(episode=no_departure, start=0, end=24)
    assert step == 24
    assert qc["dig_end_source"] == "search_end_no_confirmed_departure"


def test_dump_start_committed_band_and_late_pre_release_fallback() -> None:
    committed = _episode(80)
    env = committed["env_state"]
    _seed_dump_geometry(env)
    env[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.20
    env[30:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.08
    env[30:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.70
    env[30:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 1.00

    step, qc = find_spatial_mass_dump_start(
        episode=committed,
        cycle_start=0,
        release_onset=55,
    )

    assert step == 30
    assert qc["dump_start_source"] == "dump_area_committed_aiming_band"

    late = _episode(80)
    env = late["env_state"]
    _seed_dump_geometry(env)
    env[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.20
    env[50:56, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.28
    env[50:56, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.70
    env[50:56, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 1.00

    step, qc = find_spatial_mass_dump_start(
        episode=late,
        cycle_start=0,
        release_onset=55,
    )

    assert step == 50
    assert qc["dump_start_source"] == "late_pre_release_aiming_fallback"


def test_dump_end_detects_residual_plateau_and_post_release_cap() -> None:
    episode = _episode(100)
    env = episode["env_state"]
    env[:, ENV_STATE_MASS_IN_BUCKET_IDX] = 50.0
    env[10:35, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(50.0, 0.0, 25)
    env[35:, ENV_STATE_MASS_IN_BUCKET_IDX] = 0.0
    env[10:35, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = np.linspace(0.0, 60.0, 25)
    env[35:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 60.0

    step, qc = find_spatial_mass_dump_end(
        episode=episode,
        search_end=90,
        release_onset=10,
    )

    assert step >= 60
    assert qc["dump_end_source"] == "residual_mass_deposit_plateau"

    capped = _episode(700)
    capped["env_state"][:, ENV_STATE_MASS_IN_BUCKET_IDX] = 100.0
    step, qc = find_spatial_mass_dump_end(
        episode=capped,
        search_end=650,
        release_onset=2,
    )
    assert step == 482
    assert qc["dump_end_source"] == "post_release_cap_fallback"


def test_return_entry_ready_selects_first_ready_or_next_start_fallback() -> None:
    episode = _episode(140)
    env = episode["env_state"]
    env[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 10.0
    env[52, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0

    step, qc = find_spatial_mass_return_entry_ready(
        episode=episode,
        start=30,
        next_start=80,
        next_work_end=120,
    )

    assert step == 52
    assert qc["return_end_source"] == "first_next_dig_entry_ready"

    fallback = _episode(140)
    fallback["env_state"][:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    fallback["env_state"][:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 10.0
    step, qc = find_spatial_mass_return_entry_ready(
        episode=fallback,
        start=30,
        next_start=80,
        next_work_end=120,
    )
    assert step == 80
    assert qc["return_end_source"] == "fallback_next_material_start"


def test_return_start_envelope_token_full_geometry_and_qpos_only_fallback() -> None:
    episode = _episode(80)
    env = episode["env_state"]
    env[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 0.0
    env[20, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[20, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.35
    env[20, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.50
    env[20, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.12
    episode["qpos"][:, :4] = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    episode["qvel"][:, :4] = 0.25

    token, valid_mask, qc = build_return_start_envelope_token(
        episode=episode,
        next_start_step=20,
    )

    assert token.shape == (RETURN_START_ENVELOPE_TOKEN_DIM,)
    assert valid_mask.shape == token.shape
    assert qc["return_start_envelope_selected_source"] == "first_geometry_available_in_window"
    assert token[RETURN_ENVELOPE_LONG_NORM_IDX] == pytest.approx(0.35)
    assert token[RETURN_ENVELOPE_SHORT_NORM_IDX] == pytest.approx(0.50)
    assert token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] == pytest.approx(0.12)
    assert token[RETURN_ENVELOPE_QPOS_VALID_IDX] == 1.0
    assert token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] == 1.0
    assert valid_mask[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] == 1

    qpos_only = {
        "actions": np.zeros((40, 4), dtype=np.float32),
        "qpos": np.ones((40, 4), dtype=np.float32),
        "qvel": np.ones((40, 4), dtype=np.float32) * 0.1,
    }
    token, valid_mask, qc = build_return_start_envelope_token(
        episode=qpos_only,
        next_start_step=5,
    )
    assert qc["return_start_envelope_selected_source"] == "missing_env_state"
    assert token[RETURN_ENVELOPE_QPOS_VALID_IDX] == 1.0
    assert token[RETURN_ENVELOPE_DEPTH_MAX_IDX] == pytest.approx(0.08)
    assert np.all(valid_mask[RETURN_ENVELOPE_QPOS_CENTER_SLICE] == 1)
    assert np.all(valid_mask[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] == 1)


def test_split_spatial_mass_two_cycle_overlay_and_window_names() -> None:
    episode = _episode(240)
    env = episode["env_state"]
    _seed_cycle(env, start=0, release=50, handoff=90)
    _seed_cycle(env, start=100, release=160, handoff=190)
    episode["qpos"][:, :4] = np.asarray([0.2, 0.3, 0.4, 0.5], dtype=np.float32)
    episode["qvel"][:, :4] = 0.1
    raw_windows = [(0, 0, 80, 80), (1, 100, 210, 210)]

    slices, rejects = split_spatial_mass_primitive_slices(
        episode=episode,
        source_episode_id=3,
        source_dataset_dir=".",
        raw_cycle_windows=raw_windows,
        pose_realign_steps=(),
        return_max_transition_len=512,
    )

    assert [item.primitive_name for item in slices] == [
        "dig",
        "carry",
        "dump",
        "return",
        "dig",
        "carry",
        "dump",
    ]
    assert [item.window_name for item in slices[:4]] == [
        SPATIAL_MASS_DIG_WINDOW_NAME,
        SPATIAL_MASS_CARRY_WINDOW_NAME,
        SPATIAL_MASS_DUMP_WINDOW_NAME,
        SPATIAL_MASS_RETURN_WINDOW_NAME,
    ]
    assert any(
        item.primitive_name == "return" and item.reason == "terminal_return_reject"
        for item in rejects
    )
    return_slice = next(item for item in slices if item.primitive_name == "return")
    assert return_slice.v2_step_overlay is not None
    envelope_key = primitive_token_dataset_path(
        RETURN_START_ENVELOPE_TOKEN_KEY
    ).rsplit("/", 1)[-1]
    mask_key = primitive_token_dataset_path(
        RETURN_START_ENVELOPE_VALID_MASK_KEY
    ).rsplit("/", 1)[-1]
    assert return_slice.v2_step_overlay[envelope_key].shape[-1] == (
        RETURN_START_ENVELOPE_TOKEN_DIM
    )
    assert return_slice.v2_step_overlay[mask_key].shape == (
        return_slice.v2_step_overlay[envelope_key].shape
    )


def _episode(length: int) -> dict:
    env_state = np.zeros((length, 64), dtype=np.float32)
    env_state[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env_state[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 10.0
    return {
        "actions": np.zeros((length, 4), dtype=np.float32),
        "qpos": np.zeros((length, 4), dtype=np.float32),
        "qvel": np.zeros((length, 4), dtype=np.float32),
        "env_state": env_state,
        "v2": {"step": {}},
    }


def _seed_dump_geometry(env: np.ndarray) -> None:
    env[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.70
    env[:, ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 0.0
    env[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 3.0
    env[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 3.0


def _seed_cycle(env: np.ndarray, *, start: int, release: int, handoff: int) -> None:
    env[start:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[start:release, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0
    env[start : start + 6, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0
    env[start : start + 6, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.02
    env[start : start + 16, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(
        0.0,
        50.0,
        16,
        dtype=np.float32,
    )
    env[start + 16 : release, ENV_STATE_MASS_IN_BUCKET_IDX] = 50.0
    env[start + 22 : release, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.2
    env[start + 22 : release, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 0.0
    env[start + 22 : release, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.0
    _seed_dump_geometry(env[start: release + 1])
    env[start: release + 1, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.2
    env[release - 20 : release + 1, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.08
    env[release - 20 : release + 1, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.70
    env[release - 20 : release + 1, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 1.00
    env[release : release + 10, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(
        50.0,
        0.0,
        10,
        dtype=np.float32,
    )
    env[release + 10 :, ENV_STATE_MASS_IN_BUCKET_IDX] = 0.0
    env[release : release + 10, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = (
        np.linspace(0.0, 60.0, 10, dtype=np.float32)
    )
    env[release + 10 :, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 60.0
    env[handoff, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0
    env[handoff, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.35
    env[handoff, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.50
    env[handoff, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.02
