from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

YULONG_DOCS = frozenset(
    {
        "docs/checklist_train.md",
        "docs/data_processing_hdf5_qc_contract.md",
        "docs/dig_act_executor_and_trajectory_planning_exploration_20260822_20260828.md",
        "docs/dig_token_swap_effect_consistency_v1.md",
        "docs/dig_short_trajectory_conditioned_act_development_plan.md",
        "docs/goal_following_mainline_implementation_manifest_20260731.json",
        "docs/goal_following_mainline_handoff_20260731.md",
        "docs/strict18_realtime_goal_following_handoff_prompt_20260820.md",
        "docs/strict18_goal_following_roadmap.md",
        "docs/Strict-18_指哪挖哪技术框架与探索总结.md",
        "docs/large_scene_simulation_training_requirements.md",
        "docs/llm_planner_closed_loop_terrain_conclusion.md",
        "docs/llm_planner_prework.md",
        "docs/oracle_terrain_residual_baseline_report.md",
        "docs/oracle_terrain_residual_main_thread_restart_prompt.md",
        "docs/oracle_terrain_residual_planner_v0_plan.md",
        "docs/oracle_terrain_residual_planner_closed_loop_profile.md",
        "docs/oracle_terrain_residual_planner_closed_loop_log.md",
        "docs/oracle_terrain_residual_planner_phase0a_prompt.md",
        "docs/planner_to_act_conceptual_contract.md",
        "docs/primitive_phase_boundaries.md",
        "docs/project_history_v1_to_now.md",
        "docs/terrain_residual_pre_goal_following_freeze_manifest_20260731.json",
        "docs/training_setup.md",
        "docs/v1_to_v2_3_exploration_path.md",
        "docs/v2_1_failure_retrospective.md",
        "docs/v2_2_pro_operator_data_collection_plan.md",
        "docs/v2_4_5_spatial_mass_ownership.md",
        "docs/v2_4plan.md",
    }
)

REFACTOR_DOCS = frozenset(
    {
        "docs/planner_current_architecture.md",
        "docs/planner_decision_backend_contract.md",
        "docs/planner_scheduling_backend_design.md",
        "docs/planner_primitive_interface_standard.md",
        "docs/v2_5_rollout_issue_record_2026_06_30.md",
    }
)

EXPECTED_DOCS = frozenset(YULONG_DOCS | REFACTOR_DOCS)

REMOVED_DOC_FRAGMENTS = (
    "docs/planner_current_code_architecture_plan.md",
    "docs/planner_baseline_architecture_map.md",
    "docs/planner_rollout_evidence_refactor_plan.md",
    "docs/planner_rollout_evidence_refactor_log.md",
    "docs/planner_evidence_trace_tool.md",
    "docs/planner_evidence_reports",
    "docs/prompts/planner_rollout_evidence_goal_prompt.md",
    "docs/refactor_history/planner",
    "docs/codex/skills",
    "docs/current_status_and_plan.md",
    "docs/v2_1_plan",
    "docs/v2_2_4primitives",
    "docs/v2_5_design_sketch",
)

STRICT18_ROADMAP_ANCHORS = (
    "当前授权路线已切换为**阶段 B → C → D：Dig 单铲位置 A/B 土体效果验证**。",
    "Return 实现、实验记录与失效原因现已冻结为历史材料",
    "`diagnostic_only=true`、`promotion_eligible=false`",
    "`actuation_diagnostics_v1`",
    "隐藏土体一致性未证明",
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

STRICT18_FOLLOWUP_AUDIT_ANCHORS = (
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

STRICT18_DIG_JOINT_SUPPORT_FAMILY_ANCHORS = (
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

STRICT18_DIG_OUTLIER_AUDIT_ANCHORS = (
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

STRICT18_DIG_LOCAL_STATE_SUPPORT_ANCHORS = (
    "阶段 A.4：Dig 局部完整状态支持合同验证",
    "`dig_local_complete_state_k8_sources2_v1`",
    "`dig_local_complete_state_k16_sources2_v1`",
    "`dig_local_complete_state_k32_sources3_v1`",
    "IQR/1.3489795003921634",
    "MAD/0.6744897501960817",
    "每个 strict-train source 最多固定均匀抽取 128 个 calibration query",
    "同 source 行必须\n从参考集排除",
    "邻居 action 到分量中位数",
    "validation_normal_coverage >= 0.99",
    "目标 OOS 段、其分类、动作、",
    "完整邻居 action/provenance 只在已选择候选后的独立 target",
    "不能直接成为 runtime 通用放行",
)

STRICT18_RETURN_TEMPORAL_DISPATCH_ANCHORS = (
    "`return_temporal_dispatch_forensics_v2/`",
    "阶段 A.5：Return temporal dispatch 合同验证",
    "`legacy_100_oldest_first_decay_0p01`",
    "`newest_first_100_decay_0p01`",
    "`newest_first_max_age_20_decay_0p01`",
    "`latest_current_chunk_diagnostic`",
    "每个 source 最多 8 个稳定段",
    "`fixed_16_source_balanced_held_validation_segments_only`",
    "max(1e-6, 0.05 * strict_train_action_scale)",
    "每个 pair 和聚合都必须达到 80%",
    "严格提升 legacy 的聚合目标响应",
    "opt-in shadow candidate",
    "不能直接替换默认聚合策略",
)

STRICT18_BOUNDED_RETURN_CLOSED_LOOP_ANCHORS = (
    "阶段 A.6：受限 Return 闭环因果诊断",
    "`bounded_return_closed_loop_causal_diagnostic_v1`",
    "用户单独授权的 action-driving Return-only 诊断",
    "`16-arm/no-retry`",
    "`F1` = `return:898-1043:bb329f176aba`",
    "`N1` = `return:3453-3664:bb329f176aba`",
    "`F2` = `return:3959-4161:4afcef2eee82`",
    "`N2` = `return:4437-4633:4afcef2eee82`",
    "`original` / `alternate` × legacy / latest-current-chunk",
    "`latest_current_chunk_diagnostic` 只作因果诊断对照",
    "`newest_first_100_decay_0p01` 和 `newest_first_max_age_20_decay_0p01` 不得复活",
    "每个 arm 的硬上限为 420 个 STEP",
    "只观测 Return→Dig handoff",
    "zero action → neutral acknowledgement",
    "不得进入 Dig、Carry 或 Dump",
    "完整 `qpos + qvel` fixture",
    "`qvel_applied=true`",
    "`preflight_blocked`",
    "不得以 qpos-only、zero-qvel surrogate 冒充原始入口",
    "可观测地形状态、scene SHA、runtime build、四相机顺序和输入 SHA",
    "107D 可观测地形指纹只能用于复核，不能代替隐藏土壤状态的恢复证据",
    "完整地形快照恢复，或可验证的确定性 soil seed 恢复",
    "实际施加动作、逐轴限位干预的原子遥测",
    "尚未接入正式 Return handoff evaluator",
    "`soil_seed_status=not_supported`",
    "`scenario_id` 当前只解析、不选择场景",
    "铲斗轨迹、目标包络命中、轨迹分离起点、动作抖动/跳变/边界、碰撞与安全停止",
    "不修改 production/default runtime、安全阈值或 timeout",
)

STRICT18_CONCEPTUAL_CONTRACT_ANCHORS = (
    "teacher-forced recorded-observation 下的动作变化，只证明 ACT 读取条件；"
    "不等于 Unity 闭环成功或 production proof。",
    "`support_contract_v1` 是已发布阶段 A 工件的历史基线，必须保留。",
    "它不改变\nPlanner 的目标语义、ACT 输入责任、scheduler/handoff 决策或 production/default runtime。",
    "Return 的支持证据冒充 Dig 的支持证据。",
    "A.6 是用户单独授权的 action-driving Return-only 闭环因果诊断。",
    "完整 qpos + qvel fixture 未实际应用时必须 preflight_blocked。",
    "107D 可观测指纹也不能替代完整\n土壤快照或确定性 soil seed",
    "latest-current-chunk 只作因果对照，不构成默认派发或 production 晋级证据。",
)

STRICT18_PHASE_A_FORMAL_RULE_ANCHORS = (
    "artifact_invalid",
    "strict-train p01-p99",
    "baseline_tolerance_axis = max(1e-6, 10 * max_abs(baseline_replica_A - baseline_replica_B))",
    "replica_noise_cap_axis = max(1e-6, 0.005 * abs(action_std_axis))",
    "这里没有相对误差项",
    "response_threshold_axis = max(baseline_tolerance_axis, 0.05 * abs(action_std_axis))",
    "active-frame fraction < 0.80",
    "any OOS -> OOS",
    "not_identifiable_in_teacher_forced_replay",
)

STRICT18_SUPPORT_CONTRACT_V2_ANCHORS = (
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
    "Dig 保持 v1",
    "不得要求每个 primitive 都选择 v2 后才允许",
    "primitive-scoped 的 no-overwrite 阶段 A v2 审计根",
    "它不以顶层 `completed`",
)


class PlannerDocGuardError(RuntimeError):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PlannerDocGuardError(f"missing required file: {path}") from exc


def _require(text: str, needle: str, *, path: Path) -> None:
    if needle not in text:
        raise PlannerDocGuardError(f"{path} must mention {needle!r}")


def _docs_files(root: Path) -> set[str]:
    docs_root = root / "docs"
    if not docs_root.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in docs_root.rglob("*")
        if path.is_file()
    }


def check_doc_inventory(root: str | Path = ".") -> None:
    root_path = Path(root)
    actual = _docs_files(root_path)
    missing = sorted(EXPECTED_DOCS - actual)
    unexpected = sorted(actual - EXPECTED_DOCS)
    if missing or unexpected:
        parts: list[str] = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if unexpected:
            parts.append("unexpected: " + ", ".join(unexpected))
        raise PlannerDocGuardError("docs inventory mismatch; " + " | ".join(parts))


def check_changed_docs(
    paths: Iterable[str | Path] | None = None,
    *,
    root: str | Path = ".",
) -> None:
    root_path = Path(root)
    changed = [Path(path).as_posix() for path in paths or []]
    unexpected_existing = sorted(
        path
        for path in changed
        if path.startswith("docs/")
        and path not in EXPECTED_DOCS
        and (root_path / path).exists()
    )
    if unexpected_existing:
        raise PlannerDocGuardError(
            "unexpected docs must not be recreated: "
            + ", ".join(unexpected_existing)
        )


def check_strict18_goal_following_contract(root: str | Path = ".") -> None:
    root_path = Path(root)
    roadmap_path = root_path / "docs/strict18_goal_following_roadmap.md"
    conceptual_contract_path = root_path / "docs/planner_to_act_conceptual_contract.md"

    roadmap = _read(roadmap_path)
    conceptual_contract = _read(conceptual_contract_path)
    for needle in STRICT18_ROADMAP_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_PHASE_A_FORMAL_RULE_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_SUPPORT_CONTRACT_V2_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_FOLLOWUP_AUDIT_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_DIG_JOINT_SUPPORT_FAMILY_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_DIG_OUTLIER_AUDIT_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_DIG_LOCAL_STATE_SUPPORT_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_RETURN_TEMPORAL_DISPATCH_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_BOUNDED_RETURN_CLOSED_LOOP_ANCHORS:
        _require(roadmap, needle, path=roadmap_path)
    for needle in STRICT18_CONCEPTUAL_CONTRACT_ANCHORS:
        _require(conceptual_contract, needle, path=conceptual_contract_path)


def check_architecture_contract(root: str | Path = ".") -> None:
    root_path = Path(root)
    architecture_path = root_path / "docs/planner_current_architecture.md"
    decision_backend_path = root_path / "docs/planner_decision_backend_contract.md"
    scheduling_path = root_path / "docs/planner_scheduling_backend_design.md"
    interface_path = root_path / "docs/planner_primitive_interface_standard.md"
    rollout_path = root_path / "docs/v2_5_rollout_issue_record_2026_06_30.md"

    architecture = _read(architecture_path)
    decision_backend = _read(decision_backend_path)
    scheduling = _read(scheduling_path)
    interface = _read(interface_path)
    rollout = _read(rollout_path)

    for needle in (
        "active current planner architecture entry point",
        "default legacy FSM backendified with focused services",
        "behavior-tree shadow backend",
        "DecisionTraceRecord",
        "backend-neutral decision platform",
    ):
        _require(architecture, needle, path=architecture_path)

    for needle in (
        "active decision-backend architecture and extension contract",
        "default legacy FSM backendified with focused services",
        "DecisionTraceRecord",
        "DecisionProposalValidator",
        "behavior_tree_shadow",
        "LLM Or VLM Planner Integration Rules",
        "legacy_fsm",
    ):
        _require(decision_backend, needle, path=decision_backend_path)

    for needle in (
        "active design guide for future scheduling/decision backends",
        "PrimitiveDecisionRuntime",
        "behavior_tree_shadow",
        "VLM payload",
        "Design documents are not production import contracts",
    ):
        _require(scheduling, needle, path=scheduling_path)

    for needle in (
        "active interface target and implementation standard",
        "default legacy FSM backendified with focused services",
        "docs/planner_decision_backend_contract.md",
        "docs/v2_5_rollout_issue_record_2026_06_30.md",
    ):
        _require(interface, needle, path=interface_path)

    for needle in (
        "V2.5 Rollout",
        "aggregate TX24",
        "success=true",
        "completed_dump_count=10",
    ):
        _require(rollout, needle, path=rollout_path)

    for path in (architecture_path, decision_backend_path, scheduling_path, interface_path):
        text = _read(path)
        for removed in REMOVED_DOC_FRAGMENTS:
            if removed in text:
                raise PlannerDocGuardError(
                    f"{path} points at removed documentation: {removed}"
                )

    check_strict18_goal_following_contract(root_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the curated YuLong + V2.5 planner documentation set."
    )
    parser.add_argument(
        "--check-doc-inventory",
        action="store_true",
        help="Validate that docs/ contains only the curated documentation set.",
    )
    parser.add_argument(
        "--check-changed-docs",
        action="store_true",
        help="Reject recreated docs outside the curated set.",
    )
    parser.add_argument(
        "--check-architecture-contract",
        action="store_true",
        help="Validate current planner architecture and V2.5 documentation anchors.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root for documentation checks.",
    )
    parser.add_argument("paths", nargs="*", help="Changed paths from pre-commit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not (
        args.check_doc_inventory
        or args.check_changed_docs
        or args.check_architecture_contract
    ):
        parser.error("select at least one check")
    try:
        if args.check_changed_docs:
            check_changed_docs(args.paths, root=args.root)
        if args.check_doc_inventory:
            check_doc_inventory(args.root)
        if args.check_architecture_contract:
            check_architecture_contract(args.root)
    except PlannerDocGuardError as exc:
        print(f"planner-doc-guard: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
