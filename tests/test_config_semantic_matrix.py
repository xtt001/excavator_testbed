from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from testbed.contracts.low_dim import (
    SUPPORTED_LOW_DIM_KEYS,
    normalize_low_dim_keys,
    resolve_low_dim_state_dim,
)
from testbed.contracts.primitive_profile import (
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    normalize_cycle_boundary_profile,
    normalize_primitive_boundary_profile,
)
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_KEY,
)
from testbed.runtime._eval import (
    _validate_dig_depth_profile_eval_low_dim,
    _validate_return_start_envelope_eval_low_dim,
)


CONFIG_DIR = Path(__file__).resolve().parents[1] / "testbed" / "configs"


def test_all_yaml_low_dim_keys_resolve_through_current_contract() -> None:
    failures: list[str] = []
    low_dim_field_count = 0
    for path, config in _iter_yaml_configs():
        equipment_model = _equipment_model(config)
        for dotted_path, value in _walk_key_paths(config):
            key_name = dotted_path.rsplit(".", 1)[-1]
            if key_name != "low_dim_keys" and not key_name.endswith("_low_dim_keys"):
                continue
            low_dim_field_count += 1
            if value is None:
                continue
            if not isinstance(value, list):
                failures.append(f"{path.name}:{dotted_path} is not a list")
                continue
            try:
                keys = normalize_low_dim_keys(value)
                resolve_low_dim_state_dim(keys, equipment_model)
            except Exception as exc:  # pragma: no cover - failure message only
                failures.append(f"{path.name}:{dotted_path}: {exc}")

    assert low_dim_field_count > 0
    assert not failures


def test_boundary_profiles_in_configs_use_profile_contract() -> None:
    profile_fields: list[tuple[str, str, str]] = []
    for path, config in _iter_yaml_configs():
        for dotted_path, value in _walk_key_paths(config):
            field = dotted_path.rsplit(".", 1)[-1]
            if field == "boundary_profile":
                profile = normalize_primitive_boundary_profile(value)
                profile_fields.append((path.name, dotted_path, profile))
            if dotted_path == "boundary.profile":
                profile = normalize_cycle_boundary_profile(value)
                profile_fields.append((path.name, dotted_path, profile))

    assert profile_fields
    assert all(
        profile == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
        for filename, _, profile in profile_fields
        if "v2_4_5" in filename
    )


def test_v2_4_5_train_configs_keep_skill_specific_low_dim_contracts() -> None:
    expected = {
        "act_yulong_v2_4_5_process_boundary_qc6_dig_qvel.yaml": [
            "qpos",
            "qvel",
            DIG_CUT_TOKEN_KEY,
        ],
        "act_yulong_v2_4_5_process_boundary_qc6_dig_depth_profile_qvel.yaml": [
            "qpos",
            "qvel",
            DIG_CUT_TOKEN_KEY,
            DIG_DEPTH_PROFILE_TOKEN_KEY,
        ],
        "act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml": [
            "qpos",
            "qvel",
            RETURN_START_ENVELOPE_TOKEN_KEY,
        ],
        "act_yulong_v2_4_5_process_boundary_qc6_carry_qvel.yaml": [
            "qpos",
            "qvel",
        ],
        "act_yulong_v2_4_5_process_boundary_qc6_dump_qvel.yaml": [
            "qpos",
            "qvel",
        ],
        "act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml": [
            "qpos",
            "qvel",
            DIG_CUT_TOKEN_KEY,
        ],
        "act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml": [
            "qpos",
            "qvel",
            RETURN_START_ENVELOPE_TOKEN_KEY,
        ],
        "act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml": [
            "qpos",
            "qvel",
        ],
        "act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml": [
            "qpos",
            "qvel",
        ],
    }

    for filename, low_dim_keys in expected.items():
        config = _load_yaml(CONFIG_DIR / filename)
        assert config["policy"]["low_dim_keys"] == low_dim_keys
        resolve_low_dim_state_dim(low_dim_keys, _equipment_model(config))


def test_v2_4_5_eval_configs_validate_gate_tokens_and_boundary_profile() -> None:
    paths = sorted(CONFIG_DIR.glob("eval_yulong_v2_4_5_qc6_cell_weighted*.yaml"))
    assert paths
    for path in paths:
        config = _load_yaml(path)
        policy_cfg = dict(config["policy"])
        primitive_low_dim_keys = list(policy_cfg.get("primitive_low_dim_keys", ["qpos"]))
        assert config["boundary"]["profile"] == PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
        assert RETURN_START_ENVELOPE_TOKEN_KEY in policy_cfg["return_low_dim_keys"]
        _validate_return_start_envelope_eval_low_dim(
            policy_cfg=policy_cfg,
            switch_cfg=policy_cfg,
            primitive_low_dim_keys=primitive_low_dim_keys,
        )

        dig_depth_profile_cfg = dict(
            policy_cfg.get("dig_cut_planner", {}).get("dig_depth_profile", {}) or {}
        )
        _validate_dig_depth_profile_eval_low_dim(
            policy_cfg=policy_cfg,
            dig_cut_planner_cfg=policy_cfg.get("dig_cut_planner", {}),
            primitive_low_dim_keys=primitive_low_dim_keys,
            first_dig_policy_enabled=bool(policy_cfg.get("first_dig_ckpt_path")),
        )
        if "depth_profile" in path.name:
            assert dig_depth_profile_cfg == {
                "source": "prior_profile",
                "required": True,
                "allow_live_fallback": False,
                "allow_global_fallback": False,
            }
            assert DIG_DEPTH_PROFILE_TOKEN_KEY in policy_cfg["dig_low_dim_keys"]
        else:
            assert DIG_DEPTH_PROFILE_TOKEN_KEY not in policy_cfg["dig_low_dim_keys"]


def test_legacy_and_intermediate_configs_remain_on_supported_low_dim_keys() -> None:
    legacy_or_intermediate = [
        path
        for path, _ in _iter_yaml_configs()
        if "v2_4_5" not in path.name and path.name.startswith(("act_", "eval_"))
    ]
    assert legacy_or_intermediate
    for path in legacy_or_intermediate:
        config = _load_yaml(path)
        for dotted_path, value in _walk_key_paths(config):
            field = dotted_path.rsplit(".", 1)[-1]
            if field != "low_dim_keys" and not field.endswith("_low_dim_keys"):
                continue
            keys = normalize_low_dim_keys(value)
            assert all(key in SUPPORTED_LOW_DIM_KEYS for key in keys)
            if "return_relocate" not in path.name:
                assert RETURN_RELOCATE_TOKEN_KEY not in keys
            if "conditioned_return" not in path.name and "hindsight_goal_return" not in path.name:
                assert RETURN_TARGET_TOKEN_KEY not in keys or "v2_4" in path.name


def _iter_yaml_configs() -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _load_yaml(path)) for path in sorted(CONFIG_DIR.glob("*.yaml"))]


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(payload or {})


def _equipment_model(config: dict[str, Any]) -> str:
    task = dict(config.get("task", {}) or {})
    return str(task.get("equipment_model") or "agxunity")


def _walk_key_paths(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.append((path, child))
            found.extend(_walk_key_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_key_paths(child, f"{prefix}[{index}]"))
    return found
