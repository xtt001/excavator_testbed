from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from testbed.cli.build_v2_4_hindsight_pipeline import (
    DEFAULT_BOUNDARY_PROFILE,
    DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG,
    DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC,
    DEFAULT_DEPTH_SOURCE_MIN_FRACTION,
    DEFAULT_DEPTH_TOKEN_MAX_SATURATION,
    DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC,
    DEFAULT_DEPTH_TOKEN_MIN_P90_P10,
    DEFAULT_DUMP_MAX_LEN,
    DEFAULT_DUMP_MAX_P95_LEN,
    DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS,
    DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC,
    DEFAULT_REQUIRED_DEPTH_SOURCE,
    DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION,
    DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO,
    DEFAULT_RETURN_MAX_TRANSITION_LEN,
    DEFAULT_RETURN_MIN_DIG_RATIO,
    V2_4_5_BOUNDARY_PROFILE,
    PipelinePaths,
    _run_pre_materialize_qc,
    _write_manifest,
)
from testbed.contracts.primitive_profile import (
    PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    PRIMITIVE_BOUNDARY_PROFILES as CONTRACT_PRIMITIVE_BOUNDARY_PROFILES,
    PRIMITIVE_PROFILE_CONTRACT_VERSION,
    PRIMITIVE_VERSION as CONTRACT_PRIMITIVE_VERSION,
    PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS as CONTRACT_SPATIAL_MASS_VERSION,
    is_v2_4_5_spatial_mass_profile,
    normalize_primitive_boundary_profile,
    primitive_version_for_boundary_profile,
)
from testbed.data.primitives_v2_2 import (
    PRIMITIVE_BOUNDARY_PROFILE_DEFAULT as BUILDER_DEFAULT_PROFILE,
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK as BUILDER_EFFECT_PROFILE,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS as BUILDER_SPATIAL_PROFILE,
    PRIMITIVE_BOUNDARY_PROFILES as BUILDER_PRIMITIVE_BOUNDARY_PROFILES,
    PRIMITIVE_VERSION as BUILDER_PRIMITIVE_VERSION,
    PRIMITIVE_VERSION_V2_4_5_SPATIAL_MASS as BUILDER_SPATIAL_MASS_VERSION,
    _normalise_boundary_profile,
)
from testbed.pipeline.v2_4_qc_gates import (
    PrimitiveVdsQCGateConfig,
    build_primitive_vds_qc_gate,
)


def test_primitive_profile_contract_is_shared_by_builder_and_pipeline() -> None:
    assert PRIMITIVE_PROFILE_CONTRACT_VERSION == "v2_4_5_primitive_profile_v1"
    assert BUILDER_DEFAULT_PROFILE == PRIMITIVE_BOUNDARY_PROFILE_DEFAULT
    assert BUILDER_EFFECT_PROFILE == PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK
    assert BUILDER_SPATIAL_PROFILE == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    assert DEFAULT_BOUNDARY_PROFILE == PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK
    assert V2_4_5_BOUNDARY_PROFILE == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    assert tuple(BUILDER_PRIMITIVE_BOUNDARY_PROFILES) == (
        CONTRACT_PRIMITIVE_BOUNDARY_PROFILES
    )
    assert BUILDER_PRIMITIVE_VERSION == CONTRACT_PRIMITIVE_VERSION
    assert BUILDER_SPATIAL_MASS_VERSION == CONTRACT_SPATIAL_MASS_VERSION


def test_primitive_profile_contract_maps_versions_and_preserves_errors() -> None:
    assert (
        primitive_version_for_boundary_profile(
            PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
        )
        == CONTRACT_SPATIAL_MASS_VERSION
    )
    assert (
        primitive_version_for_boundary_profile(PRIMITIVE_BOUNDARY_PROFILE_DEFAULT)
        == CONTRACT_PRIMITIVE_VERSION
    )
    assert (
        primitive_version_for_boundary_profile(
            PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK
        )
        == CONTRACT_PRIMITIVE_VERSION
    )
    assert normalize_primitive_boundary_profile(None) == PRIMITIVE_BOUNDARY_PROFILE_DEFAULT
    assert _normalise_boundary_profile("") == PRIMITIVE_BOUNDARY_PROFILE_DEFAULT
    assert is_v2_4_5_spatial_mass_profile(
        PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )

    with pytest.raises(ValueError, match="Unsupported V2.2 primitive boundary profile"):
        normalize_primitive_boundary_profile("unknown_profile")
    with pytest.raises(ValueError, match="Unsupported V2.2 primitive boundary profile"):
        _normalise_boundary_profile("unknown_profile")


def test_v2_4_pipeline_manifest_records_semantic_contract_fields(
    tmp_path: Path,
) -> None:
    paths = PipelinePaths(
        job_dir=tmp_path / "job",
        logs_dir=tmp_path / "job" / "logs",
        relabeled_root=tmp_path / "relabeled",
        operator_root=tmp_path / "operator",
        hindsight_root=tmp_path / "hindsight",
        primitive_vds_root=tmp_path / "primitive_vds",
        primitive_copy_root=tmp_path / "primitive_copy",
    )
    args = argparse.Namespace(
        raw_dir=tmp_path / "raw",
        relabeled_dir=None,
        operator_dir=None,
        boundary_profile=V2_4_5_BOUNDARY_PROFILE,
        dig_train_config=Path("testbed/configs/act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml"),
        return_train_config=Path(
            "testbed/configs/act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml"
        ),
        carry_train_config=Path("testbed/configs/act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml"),
        dump_train_config=Path("testbed/configs/act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml"),
        dry_run=True,
        detach=False,
    )
    stages = [
        (
            "04_primitive_vds",
            [
                "tb-build-primitives-v2_2",
                "--boundary-profile",
                V2_4_5_BOUNDARY_PROFILE,
                "--output-dir",
                str(paths.primitive_vds_root),
            ],
            paths.primitive_vds_root,
            "primitive_vds",
        ),
        (
            "08_train_return",
            [
                "tb-train",
                "--config",
                str(args.return_train_config),
            ],
            None,
            None,
        ),
    ]
    manifest_path = paths.job_dir / "manifest.json"

    _write_manifest(
        manifest_path,
        args=args,
        tag="unit_contract",
        paths=paths,
        stages=stages,
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["tag"] == "unit_contract"
    assert payload["args"]["boundary_profile"] == V2_4_5_BOUNDARY_PROFILE
    assert payload["args"]["dry_run"] is True
    assert payload["args"]["return_train_config"].endswith(
        "act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml"
    )
    assert payload["paths"]["primitive_copy_root"] == str(paths.primitive_copy_root)
    assert payload["stages"][0]["name"] == "04_primitive_vds"
    assert "--boundary-profile" in payload["stages"][0]["command"]
    assert V2_4_5_BOUNDARY_PROFILE in payload["stages"][0]["command"]
    assert payload["stages"][1]["command"][-1].endswith(
        "act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml"
    )


def test_pipeline_pre_materialize_qc_facade_matches_gate_skip(
    tmp_path: Path,
) -> None:
    args = argparse.Namespace(
        skip_pre_materialize_qc=True,
        depth_token_max_saturation=DEFAULT_DEPTH_TOKEN_MAX_SATURATION,
        depth_token_min_p90_p10=DEFAULT_DEPTH_TOKEN_MIN_P90_P10,
        depth_token_min_nonzero_frac=DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC,
        depth_source_min_fraction=DEFAULT_DEPTH_SOURCE_MIN_FRACTION,
        required_depth_outcome_source=DEFAULT_REQUIRED_DEPTH_SOURCE,
        return_max_transition_len=DEFAULT_RETURN_MAX_TRANSITION_LEN,
        return_min_dig_ratio=DEFAULT_RETURN_MIN_DIG_RATIO,
        return_max_overlong_reject_ratio=DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO,
        dump_max_len=DEFAULT_DUMP_MAX_LEN,
        dump_max_p95_len=DEFAULT_DUMP_MAX_P95_LEN,
        dump_max_transition_mode_frac=DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC,
        carry_max_deposit_delta_kg=DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG,
        carry_max_deposit_to_payload_loss_frac=(
            DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
        ),
        dump_max_pre_release_lead_steps=DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS,
        return_envelope_min_valid_fraction=DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION,
        boundary_profile=V2_4_5_BOUNDARY_PROFILE,
    )
    root = tmp_path / "primitive_vds"

    assert _run_pre_materialize_qc(root, args=args) == build_primitive_vds_qc_gate(
        root,
        config=PrimitiveVdsQCGateConfig.from_namespace(args),
    )
