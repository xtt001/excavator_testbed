from __future__ import annotations

from pathlib import Path

import pytest

from scripts.planner_architecture_doc_guard import (
    EXPECTED_DOCS,
    PlannerDocGuardError,
    check_architecture_contract,
    check_changed_docs,
    check_doc_inventory,
    check_strict18_goal_following_contract,
)

_STRICT18_BASE_ROADMAP_LINES = (
    "当前唯一授权的实现任务是**阶段 A.3：Dig 数值支持范围异常的对齐与覆盖审计**。",
    "ACT 直接输出 4D action",
    "`exact-tuple` 与现有 continuous qpos predictor 是 `diagnostic_legacy`。",
    "teacher_forced_recorded_observation",
    "promotion_eligible=false",
    "阶段 B",
    "阶段 C",
    "阶段 D",
    "阶段 E",
    "阶段 F",
)

_STRICT18_FORMAL_RULE_LINES = (
    "strict-train p01-p99",
    "artifact_invalid",
    "baseline_tolerance_axis = max(1e-6, 10 * max_abs(baseline_replica_A - baseline_replica_B))",
    "replica_noise_cap_axis = max(1e-6, 0.005 * abs(action_std_axis))",
    "这里没有相对误差项",
    "response_threshold_axis = max(baseline_tolerance_axis, 0.05 * abs(action_std_axis))",
    "active-frame fraction < 0.80",
    "any OOS -> OOS",
    "not_identifiable_in_teacher_forced_replay",
)

_STRICT18_SUPPORT_CONTRACT_V2_LINES = (
    "阶段 A.1：独立支持范围合同审计（`support_contract_v2`）",
    "`support_contract_v1` 必须保留为历史基线",
    "不得用阶段 A target audit 调参",
    "source-disjoint",
    "`axis_p01_p99_v1`",
    "`axis_p0005_p9995_v2`",
    "`joint_regularized_mahalanobis_p99_v2`",
    "validation_normal_coverage >= 0.99",
    "synthetic_obvious_ood_rejection >= 0.99",
    "`support_contract_not_selected`",
    "时间对齐或字段语义错误",
    "`plots/return_<segment-id>.svg`",
    "安全阈值和 timeout 一律不变",
    "Return 可用已选择的 v2 重跑，而 Dig 保持 v1",
    "不得要求每个 primitive 都选择 v2 后才允许",
    "primitive-scoped 的 no-overwrite 阶段 A v2 审计根",
    "它不以顶层 `completed`",
)

_STRICT18_FOLLOWUP_AUDIT_LINES = (
    "阶段 A.2：Return 响应稳定性原因审计与 Dig 联合支持合同独立验证",
    "`return:898-1043:bb329f176aba`",
    "`return:3959-4161:4afcef2eee82`",
    "固定的 0.80",
    "不得降低 0.80 门槛",
    "token 归一化",
    "图像、`qpos`、`qvel` 的历史窗口",
    "temporal aggregation",
    "source-disjoint",
    "不得根据 target 结果临时调参",
    "Dig 保持 v1",
    "完整、no-overwrite 的阶段 A 重跑",
    "`act_goal_condition_sensitivity_v3/`",
    "v3 本身不进入阶段 B",
)

_STRICT18_DIG_JOINT_SUPPORT_FAMILY_LINES = (
    "`dig_joint_regularized_mahalanobis_p99_v1`",
    "`dig_joint_regularized_mahalanobis_p995_v1`",
    "`dig_joint_regularized_mahalanobis_p999_v1`",
    "`dig_joint_regularized_mahalanobis_p9995_v1`",
    "`dig_joint_regularized_mahalanobis_p9999_v1`",
    "`max(trace(covariance) / D * 1e-6, 1e-12)`",
    "`linear` 分位数",
    "validation_v1_edge_coverage >= 0.99",
    "`synthetic_obvious_ood_rejection` 降序",
    "A.1 的 `support_contract_v2` 候选 family 不同",
)

_STRICT18_DIG_OUTLIER_AUDIT_LINES = (
    "阶段 A.3：Dig 数值支持范围异常的对齐与覆盖审计",
    "`dig:1044-1083:37a4b7afda73`",
    "`axis_p01_p99_v1`",
    "`dig_support_outlier_audit_v1/`",
    "action 使用前一帧 observation",
    "`boom_speed`",
    "`not_inferred`",
    "`action_loss_mask=1`",
    "不得参与任何候选拟合、分位数、距离",
    "`repair_data_contract_then_rerun_stage_a`",
    "保持 v1",
    "runtime 对该 Return→Dig handoff 拒绝或停止",
)


def _strict18_roadmap_text(
    *,
    include_formal_rules: bool = True,
    include_support_contract_v2: bool = True,
    include_followup_audit: bool = True,
    include_dig_joint_support_family: bool = True,
    include_dig_outlier_audit: bool = True,
) -> str:
    lines = list(_STRICT18_BASE_ROADMAP_LINES)
    if include_formal_rules:
        lines.extend(_STRICT18_FORMAL_RULE_LINES)
    if include_support_contract_v2:
        lines.extend(_STRICT18_SUPPORT_CONTRACT_V2_LINES)
    if include_followup_audit:
        lines.extend(_STRICT18_FOLLOWUP_AUDIT_LINES)
    if include_dig_joint_support_family:
        lines.extend(_STRICT18_DIG_JOINT_SUPPORT_FAMILY_LINES)
    if include_dig_outlier_audit:
        lines.extend(_STRICT18_DIG_OUTLIER_AUDIT_LINES)
    return "\n".join(lines)


def _strict18_conceptual_contract_text() -> str:
    return (
        "teacher-forced recorded-observation 下的动作变化，只证明 ACT 读取条件；"
        "不等于 Unity 闭环成功或 production proof。\n"
        "`support_contract_v1` 是已发布阶段 A 工件的历史基线，必须保留。\n"
        "它不改变\n"
        "Planner 的目标语义、ACT 输入责任、scheduler/handoff 决策或 production/default runtime。\n"
        "Return 的支持证据冒充 Dig 的支持证据。\n"
    )


def _write(path: Path, text: str = "# Doc\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_doc_inventory_accepts_curated_yulong_plus_v2_5_set(tmp_path: Path) -> None:
    for relative_path in EXPECTED_DOCS:
        _write(tmp_path / relative_path)

    check_doc_inventory(tmp_path)


def test_doc_inventory_rejects_unexpected_docs(tmp_path: Path) -> None:
    for relative_path in EXPECTED_DOCS:
        _write(tmp_path / relative_path)
    _write(tmp_path / "docs/current_status_and_plan.md")

    with pytest.raises(PlannerDocGuardError, match="unexpected"):
        check_doc_inventory(tmp_path)


def test_changed_docs_guard_allows_deleting_removed_docs(tmp_path: Path) -> None:
    check_changed_docs(["docs/current_status_and_plan.md"], root=tmp_path)


def test_changed_docs_guard_blocks_recreating_removed_docs(tmp_path: Path) -> None:
    _write(tmp_path / "docs/current_status_and_plan.md")

    with pytest.raises(PlannerDocGuardError, match="unexpected docs"):
        check_changed_docs(["docs/current_status_and_plan.md"], root=tmp_path)


def test_repository_planner_documentation_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]

    check_doc_inventory(root)
    check_architecture_contract(root)


def test_pre_commit_config_wires_doc_inventory_guard() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "planner-doc-inventory-guard" in config
    assert "planner-architecture-doc-contract" in config
    assert "--check-changed-docs" in config
    assert "--check-doc-inventory" in config
    assert "planner-refactor-plan-contract" not in config


def test_git_hooks_pre_commit_fallback_runs_doc_inventory_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    hook = (root / ".githooks/pre-commit").read_text(encoding="utf-8")

    assert "scripts/planner_architecture_doc_guard.py --check-changed-docs" in hook
    assert "scripts/planner_architecture_doc_guard.py --check-architecture-contract" in hook
    assert "scripts/planner_architecture_doc_guard.py --check-doc-inventory" in hook
    assert "--check-plan-contract" not in hook


def test_readme_points_to_curated_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")

    for needle in (
        "docs/strict18_goal_following_roadmap.md",
        "docs/planner_to_act_conceptual_contract.md",
        "docs/planner_current_architecture.md",
        "docs/planner_scheduling_backend_design.md",
        "docs/planner_decision_backend_contract.md",
        "docs/data_processing_hdf5_qc_contract.md",
        "docs/primitive_phase_boundaries.md",
    ):
        assert needle in readme

    assert "docs/current_status_and_plan.md" not in readme
    assert "docs/v2_2_4primitives/phase_boundaries.md" not in readme
    assert "docs/v2_5_design_sketch/" not in readme


def test_strict18_goal_following_contract_requires_current_stage_a_support_anchors(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_rejects_missing_formal_rules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(include_formal_rules=False),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="artifact_invalid"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_rejects_missing_evidence_boundary(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(),
    )
    _write(tmp_path / "docs/planner_to_act_conceptual_contract.md", "# Contract\n")

    with pytest.raises(PlannerDocGuardError, match="teacher-forced"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_rejects_missing_support_audit_rules(
    tmp_path: Path,
) -> None:
    roadmap = _strict18_roadmap_text().replace(
        "`joint_regularized_mahalanobis_p99_v2`\n",
        "",
    )
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        roadmap,
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="joint_regularized_mahalanobis_p99_v2"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_requires_primitive_scoped_v2_replay(
    tmp_path: Path,
) -> None:
    roadmap = _strict18_roadmap_text().replace(
        "primitive-scoped 的 no-overwrite 阶段 A v2 审计根\n",
        "",
    )
    _write(tmp_path / "docs/strict18_goal_following_roadmap.md", roadmap)
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="primitive-scoped"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_requires_followup_audit_rules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(include_followup_audit=False),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="阶段 A.2"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_requires_dig_joint_support_family(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(include_dig_joint_support_family=False),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="dig_joint_regularized"):
        check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_requires_dig_outlier_audit_rules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        _strict18_roadmap_text(include_dig_outlier_audit=False),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        _strict18_conceptual_contract_text(),
    )

    with pytest.raises(PlannerDocGuardError, match="dig:1044"):
        check_strict18_goal_following_contract(tmp_path)
