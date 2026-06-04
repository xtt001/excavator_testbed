from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_PAYLOAD_IDX,
    CUT_RELOCATION_SLICE,
    CUT_VALID_IDX,
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    PRIMITIVE_TOKEN_CONTRACT_VERSION,
    RETURN_ENVELOPE_CONTACT_FLAG_IDX,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_START_ENVELOPE_VALID_MASK_KEY,
    RETURN_TARGET_TOKEN_DIM,
    RETURN_TARGET_TOKEN_KEY,
    derive_return_relocate_token,
    primitive_token_dataset_path,
    primitive_token_dim,
    primitive_token_metadata_dim_attrs,
    primitive_token_order,
    validate_primitive_token_shape,
)
from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_DIM as DEPTH_PROFILE_FACADE_DIM,
)
from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_ORDER as DEPTH_PROFILE_FACADE_ORDER,
)
from testbed.data.hdf5_io import write_episode
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM as DIG_CUT_FACADE_DIM,
)
from testbed.data.operator_first_v2_2 import (
    RETURN_START_ENVELOPE_TOKEN_DIM as ENVELOPE_FACADE_DIM,
)
from testbed.data.operator_first_v2_2 import (
    RETURN_TARGET_TOKEN_DIM as RETURN_TARGET_FACADE_DIM,
)
from testbed.data.schema import (
    DS_V2_STEP_DIG_CUT_TOKENS,
    DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
    DS_V2_STEP_RETURN_TARGET_TOKENS,
)


def test_primitive_token_contract_keys_dims_paths_and_facades() -> None:
    assert PRIMITIVE_TOKEN_CONTRACT_VERSION == "v2_4_5_primitive_tokens_v1"
    assert DIG_CUT_TOKEN_DIM == DIG_CUT_FACADE_DIM == 10
    assert RETURN_TARGET_TOKEN_DIM == RETURN_TARGET_FACADE_DIM == 10
    assert RETURN_START_ENVELOPE_TOKEN_DIM == ENVELOPE_FACADE_DIM == 18
    assert DIG_DEPTH_PROFILE_TOKEN_DIM == DEPTH_PROFILE_FACADE_DIM == 12
    assert primitive_token_order(DIG_DEPTH_PROFILE_TOKEN_KEY) == (
        DEPTH_PROFILE_FACADE_ORDER
    )

    assert primitive_token_dataset_path(DIG_CUT_TOKEN_KEY) == DS_V2_STEP_DIG_CUT_TOKENS
    assert (
        primitive_token_dataset_path(DIG_DEPTH_PROFILE_TOKEN_KEY)
        == DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1
    )
    assert (
        primitive_token_dataset_path(RETURN_TARGET_TOKEN_KEY)
        == DS_V2_STEP_RETURN_TARGET_TOKENS
    )
    assert (
        primitive_token_dataset_path(RETURN_RELOCATE_TOKEN_KEY)
        == DS_V2_STEP_RETURN_TARGET_TOKENS
    )
    assert (
        primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY)
        == DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1
    )
    assert (
        primitive_token_dataset_path(RETURN_START_ENVELOPE_VALID_MASK_KEY)
        == DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK
    )


def test_primitive_token_orders_and_return_envelope_indices() -> None:
    for key in (
        DIG_CUT_TOKEN_KEY,
        DIG_DEPTH_PROFILE_TOKEN_KEY,
        RETURN_TARGET_TOKEN_KEY,
        RETURN_RELOCATE_TOKEN_KEY,
        RETURN_START_ENVELOPE_TOKEN_KEY,
        RETURN_START_ENVELOPE_VALID_MASK_KEY,
    ):
        assert len(primitive_token_order(key)) == primitive_token_dim(key)

    envelope_order = primitive_token_order(RETURN_START_ENVELOPE_TOKEN_KEY)
    assert envelope_order[RETURN_ENVELOPE_CONTACT_FLAG_IDX] == "contact_flag"
    assert envelope_order[RETURN_ENVELOPE_QPOS_VALID_IDX] == "qpos_valid"
    assert (
        envelope_order[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]
        == "spatial_depth_valid"
    )
    assert primitive_token_order(DIG_CUT_TOKEN_KEY)[CUT_DEPTH_SEMANTIC_IDX] == (
        "cut_depth_semantic"
    )
    assert primitive_token_order(DIG_CUT_TOKEN_KEY)[CUT_PAYLOAD_IDX] == "payload"
    assert primitive_token_order(DIG_CUT_TOKEN_KEY)[CUT_VALID_IDX] == "valid"


def test_metadata_dim_attrs_cover_current_and_legacy_names() -> None:
    assert primitive_token_metadata_dim_attrs(DIG_CUT_TOKEN_KEY) == (
        "dig_cut_tokens_dim",
        "dig_cut_token_dim",
    )
    assert "return_start_envelope_token_dim" in primitive_token_metadata_dim_attrs(
        RETURN_START_ENVELOPE_TOKEN_KEY
    )
    assert "return_target_token_dim" in primitive_token_metadata_dim_attrs(
        RETURN_RELOCATE_TOKEN_KEY
    )


def test_derive_return_relocate_token_preserves_motion_fields_only() -> None:
    target = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    target[CUT_VALID_IDX] = 1.0
    relocated = derive_return_relocate_token(target)

    np.testing.assert_array_equal(relocated[CUT_RELOCATION_SLICE], target[:7])
    assert float(relocated[CUT_DEPTH_SEMANTIC_IDX]) == 0.0
    assert float(relocated[CUT_PAYLOAD_IDX]) == 0.0
    assert float(relocated[CUT_VALID_IDX]) == 1.0
    assert float(target[CUT_DEPTH_SEMANTIC_IDX]) != 0.0
    assert float(target[CUT_PAYLOAD_IDX]) != 0.0


def test_synthetic_hdf5_token_paths_shapes_and_metadata_attrs(tmp_path: Path) -> None:
    path = tmp_path / "episode_0.hdf5"
    n_steps = 3
    token_payloads = {
        DIG_CUT_TOKEN_KEY: np.zeros((n_steps, DIG_CUT_TOKEN_DIM), dtype=np.float32),
        DIG_DEPTH_PROFILE_TOKEN_KEY: np.zeros(
            (n_steps, DIG_DEPTH_PROFILE_TOKEN_DIM),
            dtype=np.float32,
        ),
        RETURN_TARGET_TOKEN_KEY: np.zeros(
            (n_steps, RETURN_TARGET_TOKEN_DIM),
            dtype=np.float32,
        ),
        RETURN_START_ENVELOPE_TOKEN_KEY: np.zeros(
            (n_steps, RETURN_START_ENVELOPE_TOKEN_DIM),
            dtype=np.float32,
        ),
        RETURN_START_ENVELOPE_VALID_MASK_KEY: np.ones(
            (n_steps, RETURN_START_ENVELOPE_TOKEN_DIM),
            dtype=np.uint8,
        ),
    }
    write_episode(
        path,
        qpos=np.zeros((n_steps, 4), dtype=np.float32),
        qvel=np.zeros((n_steps, 4), dtype=np.float32),
        actions=np.zeros((n_steps, 4), dtype=np.float32),
        metadata={
            "dig_cut_tokens_dim": DIG_CUT_TOKEN_DIM,
            "dig_cut_token_dim": DIG_CUT_TOKEN_DIM,
            "dig_depth_profile_tokens_v1_dim": DIG_DEPTH_PROFILE_TOKEN_DIM,
            "return_target_tokens_dim": RETURN_TARGET_TOKEN_DIM,
            "return_start_envelope_tokens_v1_dim": RETURN_START_ENVELOPE_TOKEN_DIM,
            "return_start_envelope_token_dim": RETURN_START_ENVELOPE_TOKEN_DIM,
        },
        v2={
            "step": {
                key: value
                for key, value in token_payloads.items()
                if key != RETURN_RELOCATE_TOKEN_KEY
            }
        },
    )

    with h5py.File(path, "r") as handle:
        attrs = handle["metadata"].attrs
        for key in (
            DIG_CUT_TOKEN_KEY,
            DIG_DEPTH_PROFILE_TOKEN_KEY,
            RETURN_TARGET_TOKEN_KEY,
            RETURN_START_ENVELOPE_TOKEN_KEY,
            RETURN_START_ENVELOPE_VALID_MASK_KEY,
        ):
            dataset_path = primitive_token_dataset_path(key)
            assert dataset_path in handle
            assert handle[dataset_path].shape[-1] == primitive_token_dim(key)
            assert any(attr in attrs for attr in primitive_token_metadata_dim_attrs(key))


def test_primitive_token_contract_fails_fast_for_unknown_key_and_bad_shape() -> None:
    with pytest.raises(ValueError, match="Unsupported primitive token key"):
        primitive_token_dim("unknown_tokens")
    with pytest.raises(ValueError, match="last dimension"):
        validate_primitive_token_shape(
            RETURN_START_ENVELOPE_TOKEN_KEY,
            np.zeros((2, RETURN_START_ENVELOPE_TOKEN_DIM - 1), dtype=np.float32),
        )
