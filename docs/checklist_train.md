# 当前训练与评测检查清单

状态日期：2026-06-30
适用范围：Repo A 仿真库当前 V2.4 / V2.4.5 数据、训练、离线审核、eval / rollout review。每次新实验都应重新勾选，不要把旧勾选当作长期事实。

## 0. 先确认本次任务

- [ ] 本次是数据重建 / QC，而不是直接训练。
- [ ] 本次是训练某个 primitive policy。
- [ ] 本次是训练后 policy audit。
- [ ] 本次是 eval / rollout review。
- [ ] 本次是 root-cause audit。
- [ ] 已写清 run id、目标 primitive、数据版本、config、预期验证标准。

## 1. 读取当前信源

- [ ] 已查看 `docs/training_setup.md`，确认当前训练 runbook。
- [ ] 已查看 `docs/data_processing_hdf5_qc_contract.md`，确认数据、VDS、primitive、Gate 合同。
- [ ] 已查看 `testbed/configs/README.md`，确认 config 是当前入口还是 legacy 入口。
- [ ] 已查看 `docs/planner_to_act_conceptual_contract.md`，确认 planner / ACT 的分工边界。
- [ ] 如涉及 LLM / planner prework，已查看 `docs/llm_planner_prework.md`。

## 2. 数据与字段

- [ ] 原始数据 root 存在，外部路径可访问。
- [ ] primitive root 或 materialized copy root 存在，路径写入实验记录。
- [ ] `/observations/qpos` 形状、频率、时间轴正常。
- [ ] `/observations/qvel` 形状、频率、时间轴正常。
- [ ] `/observations/env_state` 符合当前 schema；不要沿用旧 9D 假设。
- [ ] `/action` 和 observation 时间轴对齐。
- [ ] 训练所需 camera images 存在且能解码。
- [ ] `/v2/*` 字段存在，phase / event / metadata 能被 QC 读取。
- [ ] 对 dig：`dig_cut_tokens`、`dig_outcome_targets`、valid mask 存在。
- [ ] 对 depth-profile 诊断：`dig_depth_profile_tokens_v1` 存在且分桶合理。
- [ ] 对 return：`return_start_envelope_tokens_v1`、`return_outcome_targets`、valid mask 存在。
- [ ] 对 carry / dump：所需 phase boundary、target、mask 字段存在。
- [ ] 没有把 silver / rejected 样本静默混入 gold 训练。

## 3. QC 与 Gate

### Gate 1：pre-materialize QC

- [ ] 已运行 raw / primitive 层 QC。
- [ ] `04_pre_materialize_qc.json` 或等价 summary 已保存。
- [ ] blocking issue 为 0，或已写明豁免理由。
- [ ] reject stats 可解释，没有异常集中在某个 episode / phase / bucket state。
- [ ] source lineage 明确，能从训练样本追回原始 episode。

### Gate 2：人工视觉审阅

- [ ] 已运行 `tb-audit-primitive-boundaries` 或等价 boundary audit。
- [ ] `summary.json` 已保存。
- [ ] `boundary_audit.csv` 已保存。
- [ ] `videos/` 可打开。
- [ ] `contact_sheets/index.html` 已人工查看。
- [ ] `contact_sheets_clean_gold/index.html` 已人工查看。
- [ ] 已重点检查 phase 起止帧、空斗/浅挖、提前 return、错误 dump、handoff 姿态。
- [ ] 人工审阅结论已记录；只有完成此项后才允许使用 `--ack-feedback-gates`。

### Gate 1b：materialized-copy QC

- [ ] 已 materialize VDS / primitive copy。
- [ ] materialized copy 中 image 数据是可读实体，不是断链引用。
- [ ] materialized copy 的字段、mask、episode 数和 Gate 1 结果一致。
- [ ] 训练 config 指向 materialized copy，而不是误指旧 root。

## 4. 训练 config

- [ ] config 名称与目标 primitive 一致。
- [ ] config 不是 legacy V1 / V2.1 入口，除非本次明确是历史复现。
- [ ] `dataset_dir` / `data_root` 指向本次数据版本。
- [ ] `ckpt_dir` / output dir 是新目录，不会覆盖旧实验。
- [ ] `low_dim_keys` 与当前合同一致。
- [ ] `supervision_keys` 与当前 primitive 一致。
- [ ] 对 dig：确认是否使用普通 `dig_cut_tokens` 还是 depth-profile 诊断 config。
- [ ] 对 return：确认 envelope / relocate token 版本。
- [ ] 对 carry / dump：确认当前 first-version 监督足够支撑本次目标。
- [ ] `training_tier=gold` 或等价过滤已启用。
- [ ] 如使用 silver，config 和实验记录都显式说明。
- [ ] batch size、num steps、AMP、seed、camera list 与当前机器资源匹配。
- [ ] resolved config 会被保存。

## 5. 训练执行

- [ ] 启动命令记录完整，例如 `tb-train --config testbed/configs/<act_config>.yaml`。
- [ ] Git commit / dirty status 已记录。
- [ ] 训练日志路径已记录。
- [ ] best checkpoint 路径已记录。
- [ ] loss、outcome head、token / target 相关指标没有明显异常。
- [ ] 若训练中断，已记录中断原因和可恢复 checkpoint。
- [ ] 若清理中间 checkpoint，已先确认不需要排查训练过程。

## 6. Policy audit：eval 前必须做

- [ ] dig policy 已运行 `tb-audit-dig-ckpt --output <audit_dir>/dig_ckpt_audit.json` 或等价离线审核。
- [ ] 浅挖 / 深度问题已运行 `tb-audit-dig-depth-semantics --output <audit_dir>/dig_depth_semantics_audit.json` 或等价审核。
- [ ] return policy 已运行 `tb-audit-return-ckpt --output <audit_dir>/return_ckpt_audit.json` 或等价离线审核。
- [ ] 已运行 `tb-policy-audit-manifest --output <audit_dir>/policy_audit_manifest.json ...` 汇总现有 audit JSON。
- [ ] `policy_audit_manifest.json` 中 `overall_status=ready_for_rollout_eval`，或已记录缺失 audit / schema mismatch 的豁免理由。
- [ ] 已检查 token 改变时 action / outcome 是否有响应，不只是 loss 下降。
- [ ] 已检查 policy 是否跟随 expert 关键动作段，而不是输出平均轨迹。
- [ ] 离线审核异常时，不进入 live eval，先回到数据或训练问题。

## 7. Eval / rollout 配置

- [ ] eval config 指向本次 checkpoint。
- [ ] eval config 的 boundary profile、coverage strategy、terrain / material 设定已记录。
- [ ] `3cycle_smoke` 只作为冒烟，不作为稳定结论。
- [ ] `15cycle_probe` / `30cycle_probe` 是 probe，结论需配合 rollout review。
- [ ] 输出目录是新目录，不覆盖旧视频和 summary。
- [ ] eval 所需随机种子、起始地形、cell weighting / prior 已记录。
- [ ] 如果 planner / LLM 参与，prework 输入和 planner 输出都已保存。

## 8. Rollout review

- [ ] 已运行 `tb-rollout-review --results-dir <eval_results_dir>`。
- [ ] `<eval_results_dir>/rollout_review.json` 已保存，或显式 `--output` 路径已记录。
- [ ] `rollout_review.json` 中 `overall_status`、`evidence_gaps`、`root_cause_hints` 已写入实验结论。
- [ ] `llm_candidate_ranking_ready` 只有在 policy audit 和 rollout quality 都干净、coverage trace 指向 candidate ranking 问题时才视为 true。
- [ ] 已看 summary，不只看成功率。
- [ ] 已看视频或 contact sheet。
- [ ] 已比较 planned vs actual 的 dig entry、exit、depth、payload。
- [ ] 已检查 dig->return handoff 的姿态、bucket 高度、payload。
- [ ] 已检查 return->carry、carry->dump、dump->dig 的 phase handoff。
- [ ] 已检查 `coverage_decision_trace`：选点、跳点、重复点、fallback 是否合理。
- [ ] 已记录 terminal reason：成功、timeout、safety stop、empty bucket、wrong phase 等。
- [ ] 如果失败模式集中，已触发 root-cause audit，而不是直接重训。

## 9. Root-cause audit 触发条件

- [ ] policy audit 正常但 live rollout 异常：检查 observation/action scaling、temporal aggregation、handoff。
- [ ] dig 浅挖：检查 `dig_cut_tokens`、depth-profile token、实际 depth / payload 对齐。
- [ ] return 异常：检查 return envelope token、dig 后起点分布、bucket state。
- [ ] carry / dump 异常：检查 phase boundary、bucket loaded state、dump target。
- [ ] coverage 异常：检查 planner 候选点、cell prior、跳点逻辑和 terminal reason。
- [ ] 数据问题明确时，回到 Gate 1 / Gate 2，不用训练掩盖数据错误。

## 10. 记录与沉淀

- [ ] 实验记录包含数据 root、materialized copy root、config、checkpoint、Gate、audit、eval 输出路径。
- [ ] 结论区分：数据问题、policy 问题、planner 问题、sim/control 问题。
- [ ] 如果发现合同变化，已更新 `docs/data_processing_hdf5_qc_contract.md` 或相关源文档。
- [ ] 如果发现 config 状态变化，已更新 `testbed/configs/README.md`。
- [ ] 如果只是一次实验产物，放到 archive / runs 索引，不写进长期 runbook。

## 11. Legacy 只读区

以下内容只在复现旧实验时检查：

- [ ] `act_agx_v1*` / `eval_agx_v1*` 是否仍能被当前代码加载。
- [ ] 旧 `episode_len=1000` 是否仍适合该历史实验。
- [ ] 旧 `qpos only` / 9D `env_state` 假设是否只是历史记录。
- [ ] 旧 `dump_complete_final_hold`、`success_rate=100%` 等结论没有被用于当前 V2.4.5 结果。

新训练默认不要从本区复制配置或结论。
