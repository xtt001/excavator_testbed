# 训练与评测 Runbook

状态日期：2026-07-30
适用范围：Repo A 仿真库当前 V2.4 / V2.4.5 训练、评测、离线审核流程。V1、V2.1 和早期 V2.2 内容只作为历史对照，不再作为默认训练依据。

> 当前执行链：
> `exact diagnostic → contact audit/A-B → Unity wall+FactoryFloor diagnostic`
> `→ contact-budget freeze`
> `→ continuous predictor → E0/G1/W1 → bounded live`
> `→ conditional 1×10`。
> 当前 contact audit/A-B 是 diagnostic、non-promotable 证据阶段，不写训练
> HDF5。它只允许 18 个 expert source 各一次完整 recorded-action replay 和
> `episode_168` 的 6 次 paired A/B，以及随后明确授权的 seed-2 单次 B2
> diagnostic，以及随后明确授权的单次 seed-1000 observe-only multi-shovel
> diagnostic 和 Unity-only wall+FactoryFloor root-cause 重跑；在人工冻结
> contact budget 前继续禁止
> qpos predictor、E0/G1/W1 live、functional rollout 和 1×10。

## 2026-07-30 Unity-only Wall+FactoryFloor Diagnostic

最终可解释证据：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  unity_contact_observe_only_multicycle_diagnostic_v7/
```

这不是训练或 formal functional 1×10，也没有写 HDF5。`v2/v4` 的早期高力
attempt 由 `-nographics` Null renderer 驱动，四路 ACT 图像冻结，故
117.7kN 不得用于数据或 production contact 推断。Unity 现在在支持图像而
graphics device 为 Null 时用
`recording_camera_graphics_device_unavailable` 拒绝 GET_INFO/capture；
camera source 也纳入运行 manifest lineage。外部 live-camera host 不得使用
`-nographics`。

`v5` 真实 GPU run 因 visual preflight 额外 RESET 只作旁证；`v6` 是 FMOD
native crash。最终 `v7` 只有一个 RESET，与 frozen A0 reset 的 qpos/qvel、
bucket-tip、terrain depth、remaining mass 差值全部为 0。它运行 3771 steps，
完成 7 dumps，最终由既有 timeout hard stop，而不是高力或 stuck 终止。

| shovel（1-based） | dump | wall | FactoryFloor | motion |
| ---: | --- | --- | --- | --- |
| 1–5 | yes | none | none | N/A |
| 6 | yes | bucket×`Dig_ZMin_Board`, `0.02s`, peak/RMS `68.353/68.353kN`, impulse `1367.065N·s` | none | below threshold |
| 7 | yes | bucket×`Dig_ZMin_Board`, `3.98s`, peak/RMS `31.971/30.718kN`, impulse `122248.148N·s` | bucket×`FactoryFloor`, `3.20s`, peak/RMS `61.433/56.799kN`, impulse unsupported by v1 | yes |

所有 contact 都是 bucket-only、有限且 `<100kN`；无 boom/stick/other、数据
异常、高力或 stuck。原 report 保持冻结，修正后的 append-only
`run/report_reanalysis_v2.json` 为 `passed/timeout`，只修复 post-step contact
与下一行独立 timeout 的 evidence ownership。该诊断不改变 production
hard-bottom/contact contract，也不解锁 predictor、E0/G1/W1、bounded live
或 1×10。

## 2026-07-30 Observe-only Multi-shovel Diagnostic

这是一条单独授权、current-code、non-promotable 的真实 closed-loop 诊断：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_observe_only_multicycle_diagnostic_v2/
```

它使用历史 7-dump Strict-18 resolved config、fresh seed-1000 reset、同一四个
checkpoint 和 planner prior，但不从历史 cycle 8 续跑。manifest 额外锁定四份
`dataset_stats.pkl`、ACT loader/eval runtime 与当前 contact/report code。
唯一普通接触语义变化是：bucket-only、所有力有限且严格 `<100kN` 的 wall
contact 全部 record-only，不限 session、duration、region 或 wall；这些 tick
不得 neutral、ACT reset、replan 或 block corridor。hard-bottom、
boom/stick/other、数据异常、`>=100kN`、stuck 与 timeout 仍 fail closed。

唯一 attempt、无重试的实际结果：

| shovel index（0-based） | dump | wall contact | component / wall | sessions / ticks / duration | normal peak / RMS | normal impulse | motion during contact |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 0 | yes | no | — | — | — | — | N/A |
| 1 | yes | yes | bucket / `Dig_ZMin_Board` | `12 / 21 / 0.42s` | `73924.76 / 43681.23N` | `15555.178944N·s` | yes |
| 2 | yes | no | — | — | — | — | N/A |
| 3 | yes | no | — | — | — | — | N/A |
| 4 | yes | no | — | — | — | — | N/A |
| 5 | yes | no | — | — | — | — | N/A |
| 6 | no | no | — | — | — | — | N/A |

report index 1（第二铲）的 tangential peak/RMS 为
`438.448975/258.499294N`，total peak/RMS
为 `73919.875/43680.374292N`。RMS 是 contact tick 上 pair maximum 的 RMS；
每铲 total normal impulse 使用 Unity session cumulative impulse 差分，
component×wall impulse 仅是 `step peak normal × dt` proxy。运动证据使用
“接触前一 post-step pose + 连续 contact-positive post-step poses”，不会把
离开接触后的帧算入。

运行完成 6 次 dump、开始第 7 铲，并在 step 3293 以
`hard_bottom_depth_budget_guard_clearance_depth_increase` 经 neutral ack
安全终止。21 个允许接触 tick 的 neutral、ACT reset、replan、corridor block
均为 0；reset fairness 完全通过，process return code 为 0，未写 HDF5。
因此 wall contact 不是本次终止原因，但单次运行既未达到 10 dump，也未超过
历史 7-dump 结果，不能据此冻结 production region/budget。所有 predictor/live/
1×10 gate 继续为 false。

## 2026-07-30 Seed-2 Session-Gap Diagnostic B2

B2 是独立、create-new、non-promotable 的真实 one-cycle closed-loop 证明：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_session_gap_diagnostic_b2_v1/
```

它只运行 seed 2 一次，不重试；没有写 HDF5。与原 seed-2 B 相比，唯一安全语义
变量是 `wall_contact_session_end_clear_ticks: 2`：单个 `20ms` clear
observation 仍属于同一个 logical session，连续两个 clear observations 才结束
session。reset、目标、checkpoint、ACT、window/aggregation、timeout 与全部 hard
threshold 均由 manifest/source SHA 锁定。

唯一 attempt 的 physical contact 为 step `625` 和 `627..689`，中间只有 step
`626` 一个 clear tick；两段都只有 bucket × `Dig_ZMin_Board`，peak force 均约
`40kN`。Python 合并为一个 logical session 后，contact 在 carry 前结束，运行
进入 carry 并完成 dump；hard violation 为空，reset fairness 对 expected state
及原 seed-2 B 均通过。报告 outcome 为
`single_clear_tick_split_supported`。

该结果只能说明原 seed-2 B 的 repeat-session 终止由单帧断档切分触发。原
6-attempt A/B classification 仍为 `inconclusive`；不得据此生成训练数据、修改
production contact contract、实现 predictor，或执行 E0/G1/W1、bounded live、
1×10。下一步仍是人工冻结 bucket region 与 force/duration/impulse budget。

## 2026-07-29 Contact Semantics Audit/A-B

唯一允许的输出 root 为：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_semantics_recovery_v1/
```

原始 89D expert 数据没有 typed wall-contact sidecar；其中 generic collision
为 0 只能报告为“字段不足”，不能证明未碰墙。几何审计覆盖
`374 train + 59 validation = 433` 条 split-authorized dig qpos path；完整
recorded-action replay 覆盖 16 个 train source 和 2 个 validation source，
每个 source 仅一次、不重试。validation 只作 holdout，不参与选择 production
region 或预算。

paired A/B 固定顺序为 `0:A → 0:B → 1:B → 1:A → 2:A → 2:B`。A 首次接触
zero→neutral→terminal；B 只记录并放行首次连续 bucket-only、same-wall、
finite `<100 kN` session。所有 boom/stick/other、NaN/高力、第二 session、
hard-bottom、stuck 和 timeout 仍 fail closed。旧 bounded-stop wrapper 必须
关闭，且每次 attempt 在启动 Unity 前写 no-overwrite marker。
Unity force/impulse 字段的 JSON `null` 只按 non-finite high-force 处理；
wall typed-positive 但 canonical sidecar 缺失仍按 lineage invalid 终止，
不能降级为无接触 tick。

本阶段已经实际执行完成并暂停，结果必须按证据类型分开：

- 离线 geometry audit：`374 train + 59 validation = 433` 条路径全部完成，
  `clear=4484 / near_wall=548 / contact_or_overlap=164`；shadow rig inert，
  最大逐子段证明 `0.009990016m <= 0.01m`。
- recorded-action replay：16 个 train + 2 个 validation source 均只运行一次；
  source collection 为 `passed`，但 train `379/379`、holdout `61/61` window
  均为 `invalid`，所以 production inference window 为 `0`。
- paired A/B：6 次真实 one-cycle diagnostic 均只运行一次，三对 reset
  fairness 全部有效。B 的 seed 0/1 进入 carry 并完成 dump，seed 2 因
  `wall_contact_repeat_session` 硬停止，故 B 为 `2/3`。

最终 classification 为 `inconclusive`，没有 production contact budget 可从
这些证据中推出。初版 A/B collection 的 provenance/prefix 后处理 bug 保留在原
artifact；修复后使用：

```bash
python -m testbed.cli.wall_contact_ab_runner reextract \
  --schedule <immutable-original-schedule.json> \
  --output-dir <fresh-reanalysis-dir>
```

该命令只读原始 rollout/summary/attempt marker，输出必须包含
`reanalysis_only=true` 和 `executed_attempt_count=0`。当前可信复算报告位于
`wall_contact_semantics_recovery_v1/reanalysis_v4/report/`；它没有运行新
attempt，也没有写训练 HDF5。现在等待人工冻结 bucket region 与
force/duration/impulse budget；此前所有后续 gate 仍为 false。

## 2026-07-29 Goal-conditioned Recovery Offline Preflight

唯一 no-overwrite 输出为：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  goal_conditioned_runtime_recovery_v1/
    experiment_manifest.json
    configs/{E0_expert_goal,G1_planner_continuous_goal,W1_internal_wall_safe_goal}.yaml
    goals/*.json
    offline/*.json
    evidence/{offline_evidence_matrix,offline_causal_decision}.json
    offline_preflight_report.md
```

重建命令（只允许使用 fresh `--output-root`）：

```bash
python -m testbed.cli.goal_conditioned_recovery_experiment build-preflight \
  --base-config testbed/configs/eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml \
  --condition-set runs/jobs/goal_conditioned_runtime_recovery_v1/condition_set.json \
  --output-root <fresh-goal-conditioned-root>
```

该 CLI 没有 live 子命令。只有三份 offline record、predictor lineage、Unity
effective clearance 全部通过后，才可按 E0→G1→W1 各运行一次；只有三次 live
均通过后，`build-functional-config` 才允许生成单次 G1 A0 1×10。不得把
offline record 写成 closed-loop evidence。

> 当前 live gate：phase-specific start-transition shadow-FK 实测未支持修改
> production 合同。`episode_171` 的 handoff + expert-dig effective clearance
> 为 `0.225414m < 0.24m`，且旧 start bound 低估而非高估 worktool endpoint
> displacement。五状态 production preflight 仍为 `0/5`，
> `bounded_live_allowed=false`。没有启动 bounded/1x10，也没有写入训练 HDF5、
> 补录或重训数据。

## 2026-07-28 Start-transition Shadow-FK Diagnosis

生成 phase-specific recorded-qpos request 和最终诊断：

```bash
python -m testbed.cli.build_coverage_start_transition_diagnosis prepare \
  --execution-library <strict_train_coverage_execution_library_v1_1.json> \
  --return-transition-artifact <strict_train_coverage_return_transition_library_v1.json> \
  --production-preflight <coverage_execution_production_preflight_v2.json> \
  --cycle0-source-episode <full_episode_repaired_vds/episode_6.hdf5> \
  --post-return-source-episode <full_episode_repaired_vds/episode_24.hdf5> \
  --frozen-cycle0-rollout <functional-rollout episode_0.hdf5> \
  --frozen-cycle0-observation-step 137 \
  --post-return-dig-end-step 2423 \
  --output-dir <fresh-measurement-input-dir>

python -m testbed.cli.build_coverage_start_transition_diagnosis finalize \
  --measurement-input <worktool_transition_sweep_input_v1.json> \
  --unity-measurement <worktool_transition_sweep_measurement_v1.json> \
  --output-dir <fresh-diagnosis-dir>
```

Unity 侧使用
`CodexWorktoolTrajectoryMeasurementUtility.RunFromCommandLine`，但 input schema
必须是 append-only `worktool_transition_sweep_input_v1`；旧 trajectory calibration
schema 仍保持严格 `3 expert + 5 ACT`。新输出必须包含每条 path 的完整
boom/stick/bucket × 四墙 witness，缺一即 Python finalize 失败。

当前冻结证据：

```text
input SHA:       8ed2bad464e084650329e0d1ced759117d46f25ff0519d7aa145dfac7c9b33b0
Unity output:    b79867287bda71b48e1514a77261eb7498054992998b5ac9fa1a07087ab44d1a
diagnosis SHA:   f8637752408a129b5ec562b33ba75c68647c929a86f18daa5a908cf94e931d4a
```

结果是 `start_bound_contract_change_allowed=false` 和
`bounded_live_allowed=false`。不得把 source episode 6 的安全专家初始化写成
current-runtime alignment 证明，也不得因 handoff transition 自身净距
`0.320002m` 安全而忽略随后 expert dig 的 `0.285414m` 最小净距。当前 runbook
不提供 live 命令。只有 paired handoff tail 与 planner bound 共享相同端点，其
实测 cover displacement 为 `0.092744m > 0.075173m`；cycle-0 source preamble
起点不同，必须标记 `planner_bound_endpoint_match=false`。需要新合同获批并使
五状态 production preflight 全通过后才能恢复 bounded。

## 2026-07-28 Calibrated Production Preflight v2

先生成 no-overwrite calibrated bounded config，再运行 offline preflight：

```bash
python -m testbed.cli.build_coverage_execution_gate_preflight \
  --resolved-config <worktool_margin_calibrated_transfer_v1/configs/bounded_transfer_v1.yaml> \
  --functional-results-dir <functional_10cycle_a0_wall_safe_1x10_v1/results> \
  --bounded-results-dir <act_goal_execution_contract_recovery_v1/bounded_one_dig_pose_stable_v2/results> \
  --tuple-start-alignment-artifact <tuple_start_alignment_diagnosis_v1/diagnosis/tuple_start_alignment_diagnosis_v1.json> \
  --output-dir <fresh-no-overwrite-preflight-dir>
```

该入口固定重放 cycle-0、三条 frozen return-start 和 step 2987 hard-bottom replan，
并从 resolved config 读取 `hard_clearance_m=0.24`。它不启动 Unity、不执行 ACT，
每个 case 保留 374 条 production candidate trace。当前正式 artifact 位于：

```text
.../worktool_margin_calibrated_transfer_v1/
  production_preflight_v2_1/
    coverage_execution_production_preflight_v2.json
```

结果是五个状态 `0/5` 通过。cycle-0 在 278 条 2D reject 后，96 条全部被
live-start 3D bound 拒绝；三条 post-return 只有 `9/9/14` 条到达 3D 门，最优
effective clearance 均为 `0.150241m`；step 2987 在 depleted/2D/start 门已经全拒绝。
因此不得执行已经生成的 bounded config。只有新的单因素 start-transition 实测提供
证据并使同一 production preflight 全部通过后，才允许 `tb-eval`。不得用旧 v1
preflight、nominal `19/374` 或关闭任一 gate 绕过。

## 2026-07-28 Expert/ACT Tracking Calibration

运行入口：

```bash
tb-measure-worktool-tracking-calibration collect --help
tb-measure-worktool-tracking-calibration recommend --help
```

固定证据 root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  expert_act_tracking_calibration_v1/
    live_measurement.json
    trajectory_measurement_input.json
    trajectory_geometry_measurement.json
    wall_clearance_margin_recommendation_v2.json
    planner_contract_impact_v1.json
```

`collect` 是 diagnostic-only：每个 trial 重放 source episode 24 的 `0:899`
prefix，再对 `episode_168` 的 151-step target 执行 expert continuation 或 frozen
dig ACT。repeat 数锁定为 expert 3、ACT 5；必须使用 107D typed contact、A0
四相机和 `window=100 / legacy_oldest_first`，每次最终 zero action + neutral ack。
它只写 JSON/qpos path，不写 trainable HDF5。

Unity trajectory measurement 对采集 qpos 使用已通过 `2mm/0.2deg` fixture 的
shadow FK 和完整 boom/stick/bucket convex cover。实测：

```text
expert min clearance: 0.286671 .. 0.295515 m, 0/3 contacts
ACT min clearance:    0.244541 .. 0.252072 m, 0/5 contacts
ACT 3D P95/P99:       0.493919 / 0.529946 m
clearance-loss max:   0.043838 m
```

完整 3D P95/P99 仅作为 capability diagnostic；因其包含沿轨迹位移与旋转，不得
直接写入墙法向 margin。当前中央 3D runtime 值为：

```yaml
hard_clearance_m: 0.24
act_tracking_margin_m: 0.05
pose_interpolation_bound_m: 0.01
```

推荐 artifact SHA256：
`1a2164c345b60fdae6c211b2152fd3d22246282615857edea6785a90283e025e`。
这些值只替换 3D final gate；2D prefilter 仍为 hard `0.30m`、soft `0.45m`。
margin 改变后不得直接启动正式 1x10。先用同一 execution/sweep/return-transition
SHA 重新生成 production preflight，确认所有 gate 的交集仍有 candidate，再执行
bounded live。

## 2026-07-28 Tuple-start / gold-return artifact 与离线门

当前 actual-tuple eval 还必须绑定：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/qc/
  strict_train_coverage_return_transition_library_v1.json
```

其 SHA256 为
`65952a2932a1d1373a74b825eb4d79c24d43224ca3e2449abcd7515395ab1e86`。
builder 只接受官方 return train split 的 358 条 gold return；validation 33/34、
silver、partial 和 salvage 出现即失败。它生成 353 个可用于 post-return 的精确配对，
并固定 `episode_168 -> return episode_158`。

生成命令入口为：

```bash
tb-build-coverage-return-transitions --help
tb-build-tuple-start-alignment-diagnosis --help
```

eval 配置必须把该 artifact 绑定到
`dig_cut_planner.coverage.actual_tuple_execution_library.start_reachability`，
并同时保留 execution library 与 Unity 3D sweep 的 SHA。缺少任一 artifact、profile
或 SHA 漂移均 fail closed。post-return selection 先过 paired-start RMS/L-infinity
门；return ACT 使用配对 gold return 的原始 18D token，不允许 cell prior/relocate
改写；最终 handoff 使用 live qpos 重做 3D gate。

最新旧值 diagnosis 位于
`.../tuple_start_alignment_diagnosis_v1/diagnosis/`，属于 frozen replay +
teacher-forced contract proof，不是 bounded live。它证明旧错误 handoff 不再被接纳，
且记录了校准前 `0.15/0.01/0.30m` 合同全拒绝。margin 已由后续实测替换；该旧
preflight 不得冒充新合同结果。当前仍不得跳过新 production preflight 直接启动
bounded live、1x10、重训或 effect-model。

## 2026-07-28 Unity 3D worktool sweep 生成与运行门

生成产物位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  unity_3d_worktool_sweep_v1/
    strict_train_coverage_pose_paths_v1.json
    worktool_shadow_fk_calibration_v1_1.json
    coverage_worktool_sweep_library_v1_1.json
    episode_168_frozen_start_preflight_v1/
    production_replan_preflight_v1/
```

固定 SHA：

```text
execution library: b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614
pose library:      cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2
sweep library:     e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21
```

pose library 只允许 16 个 strict-train sources 和 374 个 materialized dig
primitives，路径覆盖全部有效 dig supervision、token peak 与 extraction tail。
Unity exporter 使用 `YuLong_norm.json`、当前 constraint frames 和 active
boom/stick/bucket collision shapes 生成 conservative convex-cover lower bound。
5 个隔离 native AGX fixture 的 link position/rotation error 均通过
`0.002m/0.2deg` 门；该 fixture 不移动 online rig。

Python runtime 的精确配置为：

```yaml
worktool_sweep_3d:
  enabled: true
  profile: unity_kinematic_convex_cover_worktool_sweep_v1
  hard_clearance_m: 0.24
  act_tracking_margin_m: 0.05
  pose_interpolation_bound_m: 0.01
  artifact_path: <coverage_worktool_sweep_library_v1_1.json>
  artifact_sha256: e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21
  execution_library_sha256: b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614
  pose_library_sha256: cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2
  missing_contract: fail_closed
```

`effective_clearance = sampled clearance - 0.01m - 0.05m - live-start
displacement bound`。3D 只做硬过滤，不提供 penalty；缺 geometry/qpos/SHA 时
fail closed。2D wall gate 仍是预过滤。所有候选失败时，runtime 不调用 ACT，必须
zero-action→neutral-ack→terminal。107D env-state 和 step-ack protocol 不变。

以下是 margin 校准前的历史结果：

1. `episode_168` frozen-start preflight：3/3 rejected，passed；
2. production initial replay：278 个 2D reject + 96 个 3D reject，无候选；
3. production step-2987 replay：219 个 outcome depleted + 128 个 2D reject +
   27 个 3D reject，无候选；
4. `bounded_live_allowed=false`，当时不得运行下面生成的 diagnostic config：

```text
.../unity_3d_worktool_sweep_v1/configs/bounded_one_dig_3d_wall_safe_v1.yaml
```

旧 artifact 保留不覆盖。新合同的 frozen-library nominal prefilter 从 0 条增加到
19 条，但尚未重放 live-start/reachability 等全部 gate。只有新 production replay
先出现合法真实 tuple，才可运行 3 个 bounded reset；3/3
通过后才可生成并运行唯一一次正式 1x10。当前不得启动重训、effect model、
planned-cut、A1/A2、3x10 或 30% freeze。

## 0. strict-18 box-emptying 当前训练入口

本轮唯一训练数据根为：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/
  full_episode_repaired_vds/
  primitives_vds/
  primitives_copy/
  splits/
  qc/
```

该 root 由当前 strict manifest no-overwrite 重建，不重跑 Unity，也不读取
partial/layered salvage。allowlist 为 episode
`3,6,7,8,9,13,16,19,23,24,25,27,28,29,30,32,33,34`；33/34 是 validation，
其余 16 条是 train。source episode 不允许跨 split；primitive HDF5 必须是实体文件而
非 VDS，并保留 `source_episode_id`。

当前数据 gate 已通过：18/18 episodes、307,785 steps、293,463 个有效 action-loss
steps；四相机 JPEG、qpos/qvel、goal tokens、action/loss mask 都可加载。primitive
gold windows 为 dig/carry/dump 各 433，return 416。batch 4 的 train/val loader、
`(B,4,3,288,512)` 图像、token 维度以及 bf16 AMP forward/backward/optimizer preflight
均通过；本结论是 data/replay QC，不是 Unity live 证据。机器可读报告位于：

```text
.../qc/data_readiness.json
.../qc/batch4_gradient_preflight.json
.../qc/executed_cut_silver_manifest_predump_support_v1.json
```

正式四模型配置为：

```text
testbed/configs/act_yulong_strict_replay18_four_camera_dig_qvel.yaml
testbed/configs/act_yulong_strict_replay18_four_camera_return_envelope_qvel.yaml
testbed/configs/act_yulong_strict_replay18_four_camera_carry_qvel.yaml
testbed/configs/act_yulong_strict_replay18_four_camera_dump_qvel.yaml
```

相机顺序固定为 `stick_up, stick_down, eye_left, eye_right`。四模型均 random init、
500 epochs、lr `1e-5`、batch 4、AMP、seed 0、无 resume；训练顺序必须是
dig -> return -> carry -> dump。每一阶段只有 `run_metadata.status=completed` 且存在
`policy_best.ckpt` 才能进入下一阶段。dig 消费 `dig_cut_tokens`，return 消费
`return_start_envelope_tokens_v1`，carry/dump 只消费图像与 qpos/qvel；dig/return
auxiliary outcome 不得作为 effect-model label。

四个正式 run 现已全部完成，checkpoint 根为：

```text
/data/pingfan/excavator_testbed_runs/ckpts/yulong_strict18_terrain_residual_v0/
  dig/policy_best.ckpt
  return/policy_best.ckpt
  carry/policy_best.ckpt
  dump/policy_best.ckpt
```

“训练完成”只表示四个 `run_metadata.status=completed` 和 checkpoint 可 strict-load，
不表示闭环冻结通过。真实 freeze 使用
`testbed/configs/eval_yulong_strict18_four_camera_4p_10cycle_freeze.yaml`，并以
`tb-build-act-unity-validation` 生成的
`act_unity_closed_loop_validation_v1` 为准。CLI 的 legacy success、单次 dump success
或短程 smoke 不得替代 target-cycle gate。

当前状态正式定义为 **系统级十铲功能回归**。旧 aggregate-TX24 已由
`testbed/configs/baselines/yulong_aggregate_tx24_functional_10cycle_v1.json` 锁定为
10 次 qualified dig、10 次 dump、9 次中间 return handoff 的功能基线；它的 source
rollout 实测是 64D，且没有 typed wall/bottom，因此不是当前安全证明。strict-18 新
ACT 的跟手尚未评价完，已先失去稳定十铲能力。

runtime 修复和 gate 代码已经就位：

- same-skill `restart_skill()` 无条件 reset ACT，并清空 temporal/chunk 历史；
- hard-bottom 两次 neutral ack、token/plan invalidation、scripted clearance 和
  exhausted-cell exclusion；
- 374 个 strict train carry 首帧构成的 `carry_start_envelope_v1`，连续 3 步 gate，
  SHA256 `ab8e13ac8ff4565a9faf13264c96071289b8a92e3ddcf2baaced0918920b621a`；
- 独立 `act_functional_10cycle_validation_v1`、hard-bottom probe、
  `functional_baseline_only` bundle 和 A0/A1/A2 promotion contract。

actual-tuple execution contract 也已完成离线与 bounded-live 验证。library 位于：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/qc/
  strict_train_coverage_execution_library_v1_1.json
```

它只读取 16 个 strict-train source 的 374 个 dig primitive；selector 固定真实 tuple
`K=1`，分离 outcome/corridor/physical/return 四类 ID，并把示范 extraction tail
纳入 hard-bottom budget。step 2987 production replay 正确选择
`episode_168` / source episode 24，禁止 synthetic coordinate median。

bounded live 的首次 attempt 因 Unity bucket-tip measurement-box 角点切换产生单帧
pose 跳变，已作为 invalid diagnostic 保留。exact-tuple eval 变体增加首次计划
3-frame pose-stability gate 后，3 个独立 reset 都执行同一真实 `episode_168`
target；二维 wall clearance 均为 `0.373659m`，却全部由 bucket 接触
`Dig_ZMin_Board`，force 约 `38.5–39.3kN`。typed bottom/stuck/timeout 为 0，三次
zero-action/neutral-ack/terminal 均通过。

强 gate 和根因报告：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_goal_execution_contract_recovery_v1/
    bounded_one_dig_pose_stable_v2/
      validation_v2/act_actual_tuple_bounded_one_dig_validation_v1.json
    root_cause_report_v4/manifest.json
```

可重复生成 root-cause report：

```bash
python -m testbed.cli.build_coverage_worktool_wall_diagnosis \
  --bounded-validation <bounded-root>/validation_v2/act_actual_tuple_bounded_one_dig_validation_v1.json \
  --output-dir <fresh-no-overwrite-root-cause-report>
```

该命令重新校验 frozen JSONL size/SHA，只做诊断，不改 config 或 planner。当前
classification 为 `bucket_3d_swept_envelope_incomplete_primary`；formal 1x10、
3x10、functional bundle、cut-then-extract 重训、effect-model、planned-cut、
A1/A2 和 30% freeze 均保持关闭。

下一次 live 前必须先完成 Unity 3D worktool preflight：完整 oriented bucket、
boom/stick 与 serialized walls 的最小净距查询，同时覆盖 planned path 和
execution-deviation envelope；缺 geometry 时 fail closed。`episode_168` 必须先被
查询拒绝或独立证明安全。不得降低现有 `0.30m` hard clearance。

coverage wall-safety 也已实现。它只在当前 A0 config 启用，使用
`conservative_2d_worktool_swept_footprint_v1`、`0.70m` worktool width、
`0.30m` hard clearance 和 `0.45m` soft clearance；其他 legacy config 默认关闭。
该二维包络不等于精确 Unity 3D 未来轨迹预测。正式运行前必须先生成且审核：

```bash
python -m testbed.cli.build_coverage_wall_safety_preflight \
  --config testbed/configs/eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml \
  --env-state-hdf5 <existing-107d-hdf5> \
  --unity-scene /home/pingfan/AGXUnityE85ExcavatorSim/Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity \
  --output-dir <fresh-no-overwrite-preflight-root>
```

当前正式 preflight 已通过，cell 0/1 hard reject，cell 2–5 near-wall 且可选：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  coverage_wall_safety_preflight_v1/
```

随后完成的正式 A0 window-100 run 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a0_wall_safe_1x10_v1/
```

该 run 消除了原 wall 事故：typed wall mask/force/session 均为 0，stuck/timeout 为
0，已执行 cut 的最小二维净距为 `0.3209796224m`。但它只完成 5 次完整
dig/carry/dump/return；第 6 铲 dig 在 step 2975 hard-bottom，完整完成两次 neutral
ack、ACT restart、clearance 和 replan 后，因为 `no_wall_safe_corridor` 在 step
2989 terminal。强 validator 拒绝为：

```text
cycle_inventory_not_0_through_9:actual=[0, 1, 2, 3, 4, 5]
```

没有生成 passing validation artifact。eval CLI 的物料 `success=1.0` 不能覆盖该
结论。原 live artifact 已冻结且不修改、不重跑。最初观察到的 hard-bottom
bookkeeping 错误现已修复：`contact_kind` 明确区分 wall/hard-bottom，wall 只拥有
blocked corridor，hard-bottom 只拥有实际 physical cell，且 neutral ack 前不修改
coverage state。

但是新的 cycle-6 离线归因证明 bookkeeping 不是唯一 root cause。机器可读证据位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_hard_bottom_cycle6_diagnosis_v1/
```

第六铲 planned depth 为 `0.364648m`，0.70m worktool swept cells `[3,5]` 的最小
hard-bottom clearance 为 `0.078700m`，高于既有 `0.02m` margin；actual peak
penetration 达 `0.502483m`，比 plan 深 `0.137835m`，接触时 bucket-tip clearance
只有 `0.006493m`。因此主因锁定为 `act_execution_capability_primary`。logical
outcome cell 4 与 center-line physical cell 5 不同，另有
`data_scene_cell_semantic_mismatch`。

production replan 从 step 2987 的真实 observation 和状态重放。只移除错误 wall
depletion 时 corridor 4 可选；正确把 actual cell 5 depth-exhausted 后，corridor 4
的 swept cells `[3,5]` 与之相交并被硬过滤，最终仍是
`no_wall_safe_corridor`。因此不得为了重进 live 而放宽 footprint 或复用 logical
outcome cell。

M0/E1/W1 离线对照只使用 strict train；E1 lineage 为 primitive `episode_354` /
source episode 32，nearest-expert index 含 76,469 个有效 train steps，validation
33/34 与 partial/salvage 排除。基础 manifest 先把无法证明独立 buffer 的 action 栏
显式设为 `blocked`，没有合成输出；后续 no-overwrite `policy_replay_v1` 为三个目标
分别加载同一 checkpoint、reset 独立 temporal state，并用 A0 window 100 重放。
M0 aggregate 与记录 actual action 逐帧完全一致；M0/E1/W1 aggregate 与
nearest-expert 的 sign agreement 分别为 `0.49375/0.48750/0.68750`。该对照仍是
teacher-forced：E1/W1 使用 M0 recorded observations，没有反事实 resimulation，
不是闭环证明。由于执行、几何和 checkpoint action 证据给出唯一且不冲突的主因，
bounded one-dig probe 未触发；fresh A0 1x10 gate 关闭，Unity 未启动。最新组合报告
为 `root_cause_report_v2.json`。

以下 2026-07-23 A0 是 wall-safety 修复前的历史失败对照：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a0_postguard_1x10_v1/
```

只完成 1 次 dump；第 2 铲 dig 在 step 672 首次 wall contact，neutral/ack 后 return
在 step 1094 timeout。功能 validator 拒绝为
`cycle_inventory_not_0_through_9:actual=[0, 1]`，没有生成 passing artifact。
hard-bottom 独立 probe、A0 3x10 和 functional bundle 均未通过或未启动。
wall 时 payload 为 36.71kg，但 carry base/envelope 均为 false；gate 正确没有提前
handoff。实际状态仍显著偏离 carry-start train envelope（bucket qpos 0.237 <
p01 0.719，plane depth 0.532m > p99 0.277m），说明当前 dig 在形成专家 carry-start
姿态前已经触墙，随后 return 也未能回到 start envelope。

经一次性授权完成了不具升级资格的 A1 window-20 诊断：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a1_window20_diagnostic_1x10_v1/
```

resolved config 差异审计确认唯一行为因素是
`temporal_agg_window: 100 -> 20`；weight order 仍为
`legacy_oldest_first`，decay 仍为 0.01，其余 checkpoint、planner 和 gate 不变。
A1 将第二铲首次 wall 从 dig 后第 40 步推迟到第 60 步，payload 36.71→52.37kg，
plane depth 0.537→0.517m，bucket qpos 0.243→0.296；但仍未进入 carry envelope。
neutral ack 后立即形成第二次 wall session，step 710 terminal，仍只有 1 次 dump。
平均 entry error 改善 6.79%，但 exit error、depth absolute error 和完整 cycle
deposit fraction 分别恶化 30.91%、4.39% 和 18.32%。validator 仍拒绝
`actual=[0, 1]`，不生成 passing artifact。A0 config 已按原 SHA256
`9d3d4d7bacff11395b7f2b26921566e2cca511deae54207f5c0b71c3b7138af9`
恢复；A1 淘汰，A2 不启动。

因此 effect-model、planned-cut calibration、30% remaining-mass freeze gate 的执行、
重训和新增数据继续暂停；30% 正式标准本身不变。已有 439 个 leakage-safe
executed-cut silver samples 只保留为待用 corpus，不启动正式 ensemble 训练。只有先
另立 ACT execution/conditioning 单因素修复，并分离 logical outcome label 与 physical
safety geometry，再重新通过 offline gate，才允许生成 fresh preflight 和唯一一次新
A0 1x10。恢复 1x10、再通过 3x10 后，才允许做单因素 temporal A/B；最终接受版本仍需
重新通过原 30% formal freeze，之后才恢复 effect/planned-cut 路线。当前 live rollout
使用 append-only `agx_env_state_v2_4_107`；strict-18 训练数据继续按 89D 前缀读取。

以下 live 入口当前仅作合同记录，**live gate 关闭期间禁止执行**：

```bash
tb-eval \
  --config testbed/configs/eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml

python -m testbed.cli.build_act_functional_10cycle_validation \
  --results-dir <fresh-no-overwrite-run-root>/results \
  --output-dir <fresh-no-overwrite-run-root>/validation \
  --expected-rollout-count 1
```

checked-in A0 config 已固定本轮 no-overwrite root。只有 ACT/conditioning 和
logical/physical safety geometry 两项后续修复获批并通过离线 gate，才能复制成新的、
明确命名的 no-overwrite config/root；不能覆盖当前失败 artifact，也不能仅用 CLI
`--output-dir` 隐藏 config lineage 变化。

1x10 通过前不得运行 3x10。一次性 A1 diagnostic 例外已经结束且淘汰，不构成
promotion precedent，也不解锁 A2。3x10 通过后才允许调用
`python -m testbed.cli.build_act_functional_baseline_bundle`；该 bundle 的
`release_scope` 固定不解锁 formal freeze、effect-model 或 planned-cut。

训练管线还有一个独立的复现性问题：`load_data()` 当前把所有 filtered
`available_episode_ids` 传给 normalization stats，而不是只传 `train_ids`，所以 saved
stats 包含 source episode 33/34 validation rows。live 使用的确是 checkpoint 自带的正确
stats 文件，因此这不是本轮碰撞的直接解释；但正式重训前必须改为 train-only stats，
并重新生成 checkpoint/validation evidence，不能把受污染的 val loss 作为最终模型选择
证据。

strict-18 的 action target contract 都已统一到 current-controller target speeds
`[0.7,0.1,0.1,0.2]`，但 Replay observation dynamics 混有 `production` 与
`recording_pre_fix_v1` compatibility profile。carry train episode 数为 211 / 163，
return 为 203 / 155；部署 live 是 production。该 provenance 混合应通过受控 profile
A/B 隔离，不能先验认定需要丢弃数据，也不能静默视作同域。

## 1. 当前信源

训练前先以这些文件为准：

- 数据、VDS、primitive、QC 和 Gate 合同：`docs/data_processing_hdf5_qc_contract.md`
- planner / ACT 行为边界：`docs/planner_to_act_conceptual_contract.md`
- config 入口和历史/当前状态：`testbed/configs/README.md`
- LLM planner 前地形闭环方向：`docs/llm_planner_closed_loop_terrain_conclusion.md`
- 代码事实：`testbed/data/*`、`testbed/train/*`、`testbed/evaluation/*`、`testbed/pipeline/*`

如果本文和上述信源冲突，以上述信源和当前代码为准，并更新本文。

## 2. 当前训练心智模型

现在的训练闭环不再是“拿 HDF5 直接训练 ACT”。默认链路是：

```text
raw full-cycle / replay refreshed root
  -> tb-dataset-qc
  -> tb-label-v2_1
  -> tb-build-operator-first-v2_2
  -> tb-build-hindsight-goal-v2_4
  -> tb-build-primitives-v2_2 --boundary-profile v2_4_5_spatial_mass
  -> Gate 1: pre-materialize QC
  -> Gate 2: tb-audit-primitive-boundaries + contact sheet / manual review
  -> tb-materialize-vds
  -> Gate 1b: materialized-copy QC
  -> tb-train
  -> policy audit / policy audit manifest
  -> tb-eval
  -> rollout review / root-cause audit
```

定位问题时按四层拆开：

1. 数据 QC：raw、VDS、materialized copy、字段、mask、primitive boundary、reject 统计。
2. Policy audit：训练后、eval 前，对 checkpoint 做离线行为审核。
3. Policy audit manifest：eval 前汇总已有离线 audit JSON，生成证据清单。
4. Rollout review：eval 后看 planned vs actual、handoff、coverage trace、terminal reason。
5. Root-cause audit：只有前面证据指出明确症状后，再追 live observation/action scaling、temporal aggregation、控制切换等。

### 2.1 检查类型命名

长期文档中统一使用这些名称，不再依赖临时计划文件：

| 名称 | 阶段 | 作用 |
| --- | --- | --- |
| `data QC` | 训练前 | 检查数据质量，包括 raw / VDS / materialized copy、字段、mask、primitive 边界和 reject 统计。 |
| `policy audit` | 训练后、eval 前 | 检查 checkpoint 在 recorded stream 上是否已经不跟 token 或不跟专家。 |
| `policy audit manifest` | eval 前 | 汇总已有离线 audit JSON；缺失项只能标为 `missing`，不能伪造通过。 |
| `rollout review` | eval 后 | 检查真实闭环表现，包括 planned vs actual、handoff、coverage trace 和 terminal reason。 |
| `root-cause audit` | rollout review 发现明确症状后 | 定位问题来自 policy、token 语义、handoff、live scaling、planner belief 还是数据/QC 回流。 |

## 3. 当前数据合同

### 3.1 HDF5 / VDS 基本字段

当前 YuLong / V2.4.5 体系里，低维状态不再按旧 9D 假设理解。常用字段包括：

- `/observations/qpos`
- `/observations/qvel`
- `/observations/env_state`：2026-07-17 readonly raw 是 64D；当前 Unity
  `agx-sim/v2` replay/runtime 合同为 append-only 89D。具体顺序以 schema / QC 合同为准。
- `/action`
- `/observations/images/<camera_name>`
- `/v2/*`：阶段、事件、token、outcome target、valid mask 等训练/审核字段。

训练配置只应显式消费当前 primitive 需要的字段，不应把全量 env_state 当作默认 policy 输入。

### 3.2 清洗数据的 ACT mask 合同

`train.action_loss_mask_scope` 有两个显式值：

- `loss_only`：兼容旧行为。已有 `/v2/step/action_loss_mask` 只屏蔽 future action loss；
  sample start 和 normalization stats 仍按旧数据范围计算。
- `loss_sampling_stats`：2026-07-17 clean VDS 的必选值。sample start、action/proprio
  normalization stats 和 future action loss 都只使用 mask 为 `1` 的 timestep。

`loss_sampling_stats` 下，episode 缺少 mask、mask 长度不匹配、值不为 `0/1`，或没有任何
合法采样点时必须失败；不得回退到全 `1`。clean builder 输出两个互不混用的 data overlay：

- `<clean-root>/training_configs/post_fix_default_data.yaml`：默认训练池；只指向
  `post_fix_default_vds`。
- `<clean-root>/training_configs/pre_fix_salvage_ablation_data.yaml`：默认关闭的
  salvage/ablation 池；只指向 `pre_fix_salvage_vds`。

它们只拥有 dataset root、controller epoch filter、mask scope 和 lineage；policy 架构、
primitive、checkpoint 与 blind-test 切分仍由具体训练实验 config 显式决定。

14 条前期完整数据不再要求永久隔离。先运行：

```bash
tb-build-action-calibrated-dataset
```

它把 early/intermediate controller 的 normalized speed command 转成 current-controller
等效 command，生成独立 no-overwrite root：

```text
/data/pingfan/excavator_testbed_data/
yulong_v2_2_pro_full_task_four_camera_jpeg_20260717_cycle_action_calibrated_v2
```

训练侧使用
`training_configs/mixed_current_equivalent_data.yaml` 作为 data overlay。该 overlay：

- 指向 14 条 calibrated-pre + 10 条 identity-post 的统一 VDS；
- 要求 `action_contract=yulong_current_equivalent_normalized_speed_v2`；
- 强制 `action_loss_mask_scope=loss_sampling_stats`；
- 复用 `recommended_post_holdout_split.yaml`，validation 只保留 current-controller
  episode，不用 pre 数据美化验证分数。

这个 mixed overlay 当前仍是 `default_enabled: false` 的训练候选。第一次实验至少保留三条
同 seed 对照：post-only、未经校准的 naive mixed（只作风险对照）、calibrated mixed。
离线 action loss 只能验证标签拟合；是否影响挖坑完成度、过冲、碰撞和周期效率，必须由
当前 Unity 的真实 closed-loop 对照决定。未经 current-controller replay 的旧周期 effect
label 也不能因为 action 已校准而自动升级为 current effect gold。

注意：旧 `..._cycle_action_calibrated_v1` 把 `episode_3..17` 的 boom 录制档位误写为
`0.05`；接触前 replay 和 free-motion response audit 都支持实际为 `0.07`。v1 保留只读
诊断，不得进入训练或 replay；v2 使用 `0..2` early、`3..17` early-boom-tuned、
`18..20` intermediate、`21..35` current 四段合同。

校准 mixed 数据需要补齐 current Unity 字段时，使用：

```bash
# 只读检查 24 条、409692 个有效 action、Unity 89D 合同和磁盘预算
tb-build-terrain-replay-dataset --preflight-only

# 首次创建固定 no-overwrite root；可先停在三条代表性 smoke
tb-build-terrain-replay-dataset --stop-after-smokes

# 合同完全一致时继续其余 episode
tb-build-terrain-replay-dataset --resume

# 仅在 smoke 已被证实为“技术全通过、纯语义耗尽”后，继续评估其余 source
tb-build-terrain-replay-dataset --resume --continue-after-smoke-semantic-failure
```

三条代表性 smoke 中任一条在 5 次内没有单次语义通过时，builder 会保留已选数据与全部轻量
诊断，写 `halted_representative_smoke_failure`，并在正式 batch 前停止。这与 64D 回退、相机
缺失或协议错误触发的 `halted_hard_contract_error` 是两个不同状态；前者不能通过重试命令
静默变成可训练的 partial 数据集。显式 continuation 只用于完成其余 source 的可用性统计：
它会保留 smoke failure provenance，不改变 5 次上限或单次语义门；不足 24/24 时生成的
partial 配置继续保持禁用，不能作为默认训练池。

该 builder 对每个 source 最多尝试 5 次并选择第一个通过单次语义门的完整 realization，输出
`selected_full_hdf5`、三 target terrain sidecar，以及 replay-native 的
`labels -> operator-first -> hindsight -> clean` VDS 链。它不会把 source 与 replay 当成
48 条数据；最终仍是同一组 24 个 source identity。推荐 split 固定让 `episode_33/34`
只进入 validation，其余 22 条进入 train，配置位于
`training_configs/selected_replay_22train_2val.yaml`。

训练必须读取 `selected_replay_clean_vds` 中收紧后的 `action_loss_mask`，并保持
`action_loss_mask_scope=loss_sampling_stats`。只有 completion report 为
`complete_24_of_24` 时该 overlay 才允许 `default_enabled: true`；partial 结果可以保留和
审计，但不得静默成为默认池。所有这些字段仍是
`replay_derived_selected_pass / not_gold`，不是 planner closed-loop 或 direct-volume gold。

### 3.3 当前 primitive 输入与监督

| Primitive / family | 默认低维输入 | 监督 / head | 状态 |
| --- | --- | --- | --- |
| dig V2.4 hindsight-goal | `qpos + qvel + dig_cut_tokens` | `dig_outcome_targets` | 当前可用 |
| dig V2.4.5 spatial-mass | `qpos + qvel + dig_cut_tokens` | `dig_outcome_targets` | 当前主线 |
| dig depth-profile 诊断 | `qpos + qvel + dig_cut_tokens + dig_depth_profile_tokens_v1` | `dig_outcome_targets` | 深度语义/浅挖诊断用 |
| return envelope | `qpos + qvel + return_start_envelope_tokens_v1` | `return_outcome_targets` | 当前可用 |
| return relocate / 后续变体 | `qpos + qvel + return_*_tokens` | `return_outcome_targets` | 以 config 为准 |
| carry / dump V2.4.5 | `qpos + qvel` | 当前 first-version 监督 | 可训练但需审核 |

关键判断：

- `dig_cut_tokens` 目前仍是深度控制的主要间接入口。
- `dig_depth_profile_tokens_v1` 是深度轨迹监督/语义诊断方向，不等价于已经完成 depth closed-loop。
- return 的起点/包络 token 是为减少从 dig 到 return 的分布断裂，不应和旧 9D env_state 混为一谈。

## 4. 当前 config 家族

以 `testbed/configs/README.md` 为索引，常用入口如下。

| 场景 | 代表 config | 用途 |
| --- | --- | --- |
| V2.4.5 spatial-mass dig | `act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml` | 当前 dig 主线训练 |
| V2.4.5 spatial-mass return | `act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml` | 当前 return 主线训练 |
| V2.4.5 spatial-mass carry | `act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml` | carry first-version |
| V2.4.5 spatial-mass dump | `act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml` | dump first-version |
| QC6 process-boundary dig | `act_yulong_v2_4_5_process_boundary_qc6_dig_qvel.yaml` | qc6 accepted split 正式训练入口 |
| QC6 process-boundary return | `act_yulong_v2_4_5_process_boundary_qc6_return_envelope_qvel.yaml` | qc6 accepted split 正式训练入口 |
| Depth-profile 诊断 | `act_yulong_v2_4_5_process_boundary_qc6_dig_depth_profile_qvel.yaml` | 深度 token / trajectory 诊断 |
| V2.4 hindsight-goal | `act_yulong_v2_4_hindsight_goal_*_qvel.yaml` | V2.4 对照/过渡 |
| V2.2 pro teleop | `teleop_yulong_v2_2_pro_pilot.yaml`、`teleop_yulong_v2_2_pro_full_task.yaml` | 新环境手动采集 |

历史入口：

- `act_agx_v1*`、`eval_agx_v1*`、早期 `v2_1*` 只用于复现实验或对照，不再作为新训练默认选择。
- 早期 `episode_len=1000`、`qpos only`、`9D env_state`、`dump_complete_final_hold` 等写法，不能直接迁移到 V2.4.5。

## 5. 训练前 Gate

训练前必须完成三类检查。

### 5.1 Gate 1：pre-materialize QC

确认 primitive root 上的字段、mask、episode、phase、boundary、reject 统计没有 blocking issue。典型产物包括：

- `04_pre_materialize_qc.json`
- primitive summary / reject stats
- source lineage / metadata

### 5.2 Gate 2：人工视觉审阅

V2.4.5 的 Gate 2 不是形式动作。训练前需要看 boundary audit 的视频和 contact sheet，尤其是：

- phase boundary 是否切在正确动作段。
- dig / return / carry / dump 的起止帧是否符合 planner/ACT 合同。
- clean-gold 集合是否真的干净。
- 是否存在系统性浅挖、空斗、提前 return、错误 dump 等模式。

典型产物：

- `summary.json`
- `boundary_audit.csv`
- `videos/`
- `contact_sheets/index.html`
- `contact_sheets_clean_gold/index.html`

只有完成审阅后，才应在后续命令中使用 `--ack-feedback-gates`。

### 5.3 Gate 1b：materialized-copy QC

VDS materialize 后，要对 materialized copy 再做一次字段和样本检查。训练默认使用 materialized primitive copy，而不是隐式依赖原始 VDS。

默认训练 tier 是 `training_tier=gold`。如果要引入 silver，必须在 config 和实验记录里显式说明。

## 6. 训练运行记录

每次训练至少记录这些信息：

- 原始数据 root、primitive root、materialized copy root。
- 使用的 config、resolved config、`low_dim_keys`、`supervision_keys`。
- checkpoint 输出目录、best checkpoint 路径、训练日志路径。
- Git commit / dirty status。
- Gate 1、Gate 2、Gate 1b 产物路径。
- 是否使用 `--ack-feedback-gates`，以及人工审阅结论。
- 是否只用 gold tier，或显式混入 silver。
- 训练后 policy audit、eval rollout、rollout review 的输出目录。

建议 run id 包含：

```text
<primitive>_<dataset-tag>_<contract-tag>_<date-or-short-hash>
```

示例：

```text
dig_qc6_depth_profile_20260622
return_qc6_envelope_20260622
```

## 7. 训练与审核命令

命令以当前 config 为准，下面只记录意图。

```bash
RUN_ID=<run_id>
AUDIT_DIR=runs/audit/${RUN_ID}

# 训练
tb-train --config testbed/configs/<act_config>.yaml

# dig checkpoint 离线审核
tb-audit-dig-ckpt \
  --config testbed/configs/<dig_act_config>.yaml \
  --ckpt <dig_checkpoint> \
  --output "${AUDIT_DIR}/dig_ckpt_audit.json"

# dig 深度语义审核
tb-audit-dig-depth-semantics \
  --dataset-dir <dig_dataset_dir> \
  --output "${AUDIT_DIR}/dig_depth_semantics_audit.json"

# return checkpoint 离线审核
tb-audit-return-ckpt \
  --config testbed/configs/<return_act_config>.yaml \
  --ckpt <return_checkpoint> \
  --output "${AUDIT_DIR}/return_ckpt_audit.json"

# eval 前证据清单
tb-policy-audit-manifest \
  --output "${AUDIT_DIR}/policy_audit_manifest.json" \
  --dig-ckpt-audit "${AUDIT_DIR}/dig_ckpt_audit.json" \
  --dig-depth-audit "${AUDIT_DIR}/dig_depth_semantics_audit.json" \
  --return-ckpt-audit "${AUDIT_DIR}/return_ckpt_audit.json"

# 评测 / rollout
tb-eval --config testbed/configs/<eval_config>.yaml

# eval 后 rollout review，默认写入 <eval_results_dir>/rollout_review.json
tb-rollout-review --results-dir <eval_results_dir>
```

`policy_audit_manifest.json` 只汇总已有 audit JSON，不替代 `tb-audit-dig-ckpt`、`tb-audit-dig-depth-semantics`、`tb-audit-return-ckpt`。缺少某类 audit 或 schema 不匹配时必须保留为 evidence gap。

如果 return config 同时使用 `return_start_envelope_tokens_v1` 和 `return_relocate_tokens_v1`，`tb-audit-return-ckpt` 会读取 recorded stream 中的 return-relocate token；受控 token 变体仍主要用于检查 return-start envelope 对动作的影响。

浅挖类问题优先看：

- dig token / depth-profile 分桶是否被 policy 区分。
- 目标 depth、实际 depth、payload、mass outcome 是否一致。
- checkpoint 离线正常但 live rollout 异常时，再查 observation scaling、action scaling、handoff 和 temporal aggregation。

return 类问题优先看：

- return 起点 envelope token 是否有效。
- dig->return handoff 时的姿态、bucket height、payload 是否落在训练分布内。
- return policy 是否能按 envelope 做起步，而不是复用旧固定轨迹。

## 8. Eval 与 rollout review

当前 eval 不只看“有没有完成若干 cycle”。每次 rollout review 至少检查：

- dig planned vs actual：entry、exit、dig depth、payload。
- carry / dump transport quality：deposited fraction、low deposit、残留或漏料等质量指标。
- `return -> dig` handoff readiness：是否回到下一铲 entry 附近，能否交接给 dig。
- `coverage_decision_trace`：选点、跳点、重复点、fallback 是否合理。
- terminal reason：成功、timeout、safety stop、empty bucket、wrong phase 等。
- 视频 / contact sheet：是否存在肉眼可见但指标没捕获的问题。

标准产物路径：

```text
<eval_results_dir>/rollout_review.json
```

`rollout_review.json` 的顶层字段包括 `schema_version`、`source_results_dir`、`overall_status`、`evidence_gaps`、`rollout_reviews`、`root_cause_hints`、`llm_candidate_ranking_ready`。该报告只做诊断，不改变 eval success 语义。

每个 rollout review 还会输出 `terrain_residual` 诊断块。该块只读取 per-rollout jsonl
中最新可用的 compact dig-area `env_state` 快照，使用 `testbed.data.schema` 中的
grid count、removed-depth、target-depth 和 valid-mask 下标计算：

- `removed_depth_grid_m`、`target_depth_grid_m`、`residual_depth_grid_m = target - removed`。
- valid cell 上的 positive residual、overdig、target/removed depth sum 和
  `target_removed_completion_ratio = sum(min(removed, target)) / target_depth_sum_m`。
- `snapshot_row_index`、`grid_shape`、`cell_count`、`valid_cell_count` 和明确的 source
  provenance。
- `residual_convergence_curve`：按 per-rollout jsonl 中连续 `dig` 段取该段最后一个可用
  compact grid 快照，记录 `dig_segment_index`、`snapshot_row_index`、positive residual、
  overdig、target/removed depth sum、completion ratio 和 valid cell count。该曲线是
  dig-segment 诊断证据，不声明官方 cycle id 语义。
- `residual_convergence_summary`：只从 `residual_convergence_curve` 派生，报告起止
  dig-segment 点数、positive residual / overdig / completion ratio 的起点、终点和
  delta，并给出诊断性 `diagnostic_trend`。该 trend 只概括已观察 dig-segment 证据，
  不作为 eval pass/fail、planner success 或官方收敛语义。

当前记录没有 cell size、origin、timestamp、frame transform、height/elevation grid 或
confidence grid，报告必须把这些字段标为 `missing`，不能从现有 jsonl 推断。该 residual
块、convergence curve 和 convergence summary 都是离线诊断和 baseline 投影，不改变
planner、gate、checkpoint、token 或 eval success 语义。由于 cell size 仍缺失，
positive residual、overdig、target/removed 仍是 depth sum，不是物理体积。

T1-like rectangular shallow-pit 目标网格当前只提供显式参数生成器
`testbed.eval.terrain_target_grid.build_rectangular_target_grid()`，用于后续离线 target-shape
诊断。调用方必须显式传入 grid shape、valid mask、半开 row/col 矩形边界和 target depth；
该工具按 row-major 顺序生成 `target_depth_grid_m` 与 `target_region_mask`，并报告
`valid_cell_count`、`target_cell_count`、`target_depth_sum_m`、`validation_errors` 以及
缺失的 cell size / origin / timestamp / frame transform / height/elevation / confidence
provenance。矩形若选中 invalid cell 会被拒绝为 `invalid_target_region_mask`，不会静默把
invalid cell 当作 target cell。该工具不声明官方 T1 默认尺寸、默认深度、cell size、物理面积、
world-frame 或 eval success 语义，也不接入 production planner/gate。

显式目标坑形 residual metric 当前由
`testbed.eval.terrain_target_metrics.build_target_residual_metrics()` 单独计算。调用方必须显式传入
observed `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask` 和 `valid_mask`；
该工具只比较 row-major depth grid，报告 target 内 positive residual、overdig、target/removed
depth sum、target completion ratio、target 外 valid cells 的 removed-depth sum，以及
`residual_depth_grid_m = target_depth_grid_m - removed_depth_grid_m`。输入长度不一致、depth
非有限或为负、mask 非有限、target mask 选中 invalid cell 时会返回具体 validation status 和
`validation_errors`，不会抛出常规规格错误，也不会静默把 invalid cell 当作 target cell。该 metric
还会在 valid target cells 内报告 threshold-free depth-error 诊断：
`target_residual_depth_rmse_m`、`target_residual_depth_mae_m` 和
`target_residual_depth_abs_max_m`。如果没有 target cell，这些字段保留为 `null`，不能解释成
零误差或成功。该 metric 还会输出 `target_shape_overlap_diagnostics`，作为 threshold-free
shape-overlap 诊断：

- `raw_target_overlap` 严格比较 valid target cells 与 valid removed-active cells
  (`removed_depth_grid_m > 0.0`) 的交并比，并报告 target 外 valid cells 的 removed-depth
  sum，作为不加容差的对照口径。
- `one_cell_dilated_target_overlap` 在调用方显式传入有效 `grid_shape` 时，用 row-major
  Chebyshev / 8-neighbor 一格膨胀 target mask，再报告 dilated target cell count、valid-cell
  count、saturation ratio、intersection / union / IoU 和 dilated target 外 removed-depth
  sum。saturation ratio 用来暴露小 grid 上膨胀 mask 是否已经覆盖大部分或全部 valid cells。
- `meter_tolerance_profiles` 固定包含 `narrow_0_30m` (`0.30m`) 和 `bucket_0_50m`
  (`0.50m`) 两个诊断 profile。当前 rollout records 没有 cell size，因此 profile 会明确标记
  `cell_size_missing`，不会推断 meter-derived IoU；只有调用方显式提供 `cell_size_m` 时才按
  `ceil(tolerance_m / cell_size_m)` 的保守规则换算 cell radius 并计算同类 overlap 字段。

这些 overlap / tolerance 字段仍是离线诊断，不提供 pass/fail、planner success、eval success、
官方 T1 默认值、protected-area band、物理体积、官方 cycle id 或 runtime gate 语义。

latest-snapshot rollout projection 当前由
`testbed.eval.terrain_target_projection.build_latest_target_residual_projection()` 组合上述两个
owner：它从显式传入的 rollout records 中读取最新可用 compact-grid `env_state` removed-depth
和 valid-mask 快照，再用显式矩形 target spec 生成 target grid，并调用
`build_target_residual_metrics()` 计算 target-shape residual。输出包含 `snapshot_row_index`、
observed / target spec grid shape、observed removed-depth grid、valid mask、`target_grid` 和
`target_residual_metrics`。没有可用 snapshot 时返回 `missing_snapshot`；target spec 或 metric
验证失败时透传对应 validation status。该 helper 只用于离线投影，不写 review artifact、不改变
`rollout_review.json` schema、不声明官方 T1 默认值，也不改变 eval success 或 production planner/gate
语义。

target-shape residual convergence 当前由
`testbed.eval.terrain_target_projection.build_target_residual_convergence_projection()` 生成。它使用同一类显式
矩形 target spec，并按 per-rollout records 中连续 `dig` 段取该段最后一个可用 compact-grid
snapshot，逐点调用 `build_target_residual_metrics()`，输出 dig-segment curve 和 summary。summary
只报告点数、起止值与 delta：target positive residual、target overdig、target removed completion
ratio、outside-target removed-depth sum，以及诊断性 trend。该 curve 是 dig-segment evidence，
不声明官方 cycle id；trend 不作为 planner success、eval pass/fail、bucket-aware tolerance 或
boundary-protected shape success 语义。

显式目标坑形 baseline report 当前由
`testbed.eval.terrain_target_report.build_explicit_target_residual_baseline_report()` 生成。它只组合
`build_latest_target_residual_projection()` 与
`build_target_residual_convergence_projection()` 的已有输出，不重新实现 target-grid 或 target
residual 公式。调用方必须显式传入 rollout records、grid shape、半开 row/col 矩形边界和 target
depth；输出包含 `target_spec`、`latest_projection`、`convergence_projection` 和从嵌套 projection
字段复制出的 `diagnostic_summary`。report `status` 仅表示诊断证据完整性：latest 与 convergence
都为 `present` 时为 `present`；两者共享同一 validation / missing status 时透传该 status；否则为
`partial` 并在 summary 中保留各 projection status。该 helper 默认不写 report artifact、不接入
`rollout_review.json` schema、不定义官方 T1 默认值，也不改变 planner、gate、eval success 或物理体积
语义。当前 run 的显式非官方 baseline packet 记录在
`docs/oracle_terrain_residual_baseline_report.md`。

shape guard shadow audit 当前由
`testbed.eval.terrain_shape_guard_shadow.build_shape_guard_shadow_audit()` 生成。它只读取
baseline report 中已有的 `latest_projection.target_residual_metrics` 和
`convergence_projection.summary` 字段，不重新实现 target-grid、residual metric、projection 或
report 公式。输出是 shadow-only review surface，包含 `low_payload_shape_guard_stop`、
`overdig_guard_stop`、`depth_budget_exhausted` 和
`outside_protected_removed_increased` 四个事件记录。每个事件只报告
`triggered`、`not_triggered`、`not_evaluated` 或 `invalid_input`，并带有证据字段和稳定
reason；top-level summary 只列出 triggered / not-evaluated event names 和 validation
errors。所有阈值和 payload/cycle-efficiency 约束都必须由调用方显式传入：target overdig max、
target positive residual max、outside-target removed-depth delta max，以及 latest/min payload
fraction。缺少显式阈值、payload 输入或 report 嵌套证据时，该事件必须是
`not_evaluated`；非法数值输入返回 `invalid_input`，不抛出常规诊断规格错误。该 helper 不推断
payload、不提供默认阈值、不写 run artifact、不接入 `rollout_review.json` schema，也不改变
production planner/gate/policy/runtime、eval pass/fail、planner success、official T1 default 或
物理体积语义。

offline discrete candidate generation 当前由
`testbed.eval.terrain_candidate_generation.build_discrete_cut_candidates()` 生成。它只读取显式
row-major `residual_depth_grid_m`、`target_region_mask`、`valid_mask` 和 `grid_shape`，从
valid target cells 中 `residual_depth_grid_m > 0.0` 的 anchor 生成离线候选。调用方必须显式传入
`direction_options`、`depth_fraction_options`、`min_candidate_count` 和 `max_candidate_count`；
候选排序固定为 row-major positive residual anchor、direction option 顺序、depth fraction option
顺序。每个候选包含 `candidate_id`、anchor cell / row / col、direction、depth fraction、
anchor positive residual depth、candidate depth 和 `offline_only=true`。`candidate_depth_m` 只等于
anchor positive residual depth 乘以 depth fraction，不推断 bucket 物理 footprint 或官方 depth cap。

该 helper 输出 `positive_residual_coverage`、candidate count、untruncated candidate count、
validation errors 和 cell size / origin / timestamp / frame transform / height/elevation /
confidence provenance status。`present` 只表示按显式选项生成了候选且数量落在显式 min/max 内；
`candidate_count_below_min`、`candidate_count_above_max`、`no_positive_residual_cells` 和
`invalid_*` 状态只用于离线诊断。该候选集不是 heuristic effect model scoring，不接
production planner，不写 run artifact，不定义官方候选数量、官方方向集、官方 depth fraction、
eval pass/fail 或 planner success 语义。缺少 cell size 时不做物理 footprint、meter-derived
tolerance、boundary 或体积推断。

offline candidate constraint evidence 当前由
`testbed.eval.terrain_candidate_evidence.build_candidate_constraint_evidence()` 标注。它读取
`build_discrete_cut_candidates()` 的候选列表，以及显式 `target_region_mask`、`valid_mask`、
`grid_shape`、`max_candidate_depth_m`、`protected_boundary_cell_radius` 和可选
`return_origin_cell_index`。该 helper 不生成新候选、不排序、不打分，只按候选输入顺序输出
`evidence_records` 和 `constraint_summary`。

每条 evidence 记录使用 row-major grid-cell proxy footprint，而不是物理 bucket footprint：
`row_forward` / `row_reverse` / `col_forward` / `col_reverse` 分别表示 anchor cell 加相邻同
row/col cell；相邻 cell 出网格时记录 `clipped_by_grid_boundary=true` 和 off-grid neighbor，
不会虚构 footprint。每条记录同时给出 target / outside-target footprint cells、valid / invalid
footprint cells、显式 Chebyshev cell-radius 保护区内外 cells、`candidate_depth_m <=
max_candidate_depth_m` 的 depth-budget evidence，以及可选的 Manhattan row-major
`return_alignment_cost_proxy`。如果没有显式 return origin，该 proxy 为 `not_evaluated`。

top-level 状态包括 `present`、`no_candidates`、`invalid_candidates`、`invalid_grid_shape`、
`invalid_grid_lengths`、`invalid_mask_values`、`invalid_depth_budget`、
`invalid_boundary_radius` 和 `invalid_return_origin`。`constraint_summary` 汇总候选数、
grid footprint proxy 名称、保护半径、保护区 cell count / saturation ratio、depth-budget 超出数、
grid-boundary clipped 数、outside-target / outside-protected candidate 数，以及 return proxy
min/max。所有 budget、boundary radius 和 return origin 都是调用方显式输入；该 helper 不定义官方
depth budget、boundary tolerance、bucket footprint、physical volume、cell-size inference、top-k、
pass/fail、eval success 或 production planner 语义。

offline heuristic candidate scoring 当前由
`testbed.eval.terrain_candidate_scoring.build_candidate_heuristic_scores()` 生成。它只读取
`build_candidate_constraint_evidence()` 输出的 `evidence_records` 和调用方显式传入的 `weights`。
必需权重 key 为 `candidate_depth_reward`、`target_footprint_cell_reward`、
`outside_target_footprint_cell_penalty`、`outside_protected_boundary_cell_penalty`、
`depth_budget_exceeded_penalty`、`grid_boundary_clipped_penalty` 和
`return_alignment_distance_penalty`。这些权重只属于本次离线诊断调用；repo 不定义默认权重或官方权重。

score record 按 evidence 输入顺序保留。每条记录输出 candidate depth reward、target footprint
reward、outside-target penalty、outside-protected penalty、depth-budget exceeded penalty、
grid-boundary clipped penalty 和 return-alignment distance penalty 的组件值，并把组件求和成
`total_score`。return proxy 缺失时该组件为 `not_evaluated` 且贡献 `0.0`，不会推断 return cost。
`ranking` 只按 total score 降序、再按原输入顺序给出 deterministic diagnostic ranking；它不包含
selected/top-k/action 字段，也不接入 production planner。top-level 状态包括 `present`、
`no_evidence_records`、`invalid_evidence_records` 和 `invalid_weights`，并保留 calibrated effect
model、payload model、physical bucket footprint、cell size 和 official weight 的 missing provenance。
该 helper 是 heuristic score evidence，不是 calibrated effect/capability model，不写 run artifact，不改变
`rollout_review.json` schema，不定义 pass/fail、eval success、planner success、official candidate
defaults 或 production behavior。

offline geometric swept-footprint effect evidence 当前由
`testbed.eval.terrain_candidate_effect_model.build_geometric_swept_footprint_effect()` 生成。它读取单个
offline candidate、显式 `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask`、
`valid_mask`、`grid_shape`、`cell_size_m`、`bucket_width_m`、`bucket_length_m`，以及可选
`penetration_depth_m`。所有几何量都必须由调用方显式传入；当前 run 记录缺少 cell size 和
bucket geometry 时不得推断。

该 helper 的 footprint model 明确命名为
`centerline_rectangular_swept_footprint_approximation`，不是 calibrated bucket physics。它把 anchor
cell center 作为起点，按 `row_forward` / `row_reverse` / `col_forward` / `col_reverse` 的 row-major
方向，用 `cell_size_m` 将 cell center 距离转换成米；valid cell center 在 `[0, bucket_length_m]`
的前向区间内且横向距离不超过 `bucket_width_m / 2` 时进入 footprint。若请求的中心线矩形范围越过
grid 边界，则记录 `footprint_clipped_by_grid_boundary=true`，但不虚构 grid 外 cell。

expected delta patch 是 row-major `expected_delta_depth_grid_m`，footprint cell 上的 delta 等于
`penetration_depth_m`；缺少显式 penetration 时使用 candidate 的 `candidate_depth_m`，并把来源记录为
`candidate_depth_m`。输出使用 `cell_size_m ** 2` 计算
`expected_removed_volume_m3`、`target_removed_volume_m3`、`outside_target_removed_volume_m3` 和
`overdig_volume_delta_m3`，同时保留 depth-sum 口径。overdig delta 只比较 expected removal 前后相对
`target_depth_grid_m` 的 overdig 变化。top-level 状态包括 `present`、`invalid_candidate`、
`invalid_grid_shape`、`invalid_grid_lengths`、`invalid_mask_values`、`invalid_depth_values`、
`invalid_geometry` 和 `no_valid_footprint_cells`。该 helper 是 offline effect evidence，不接
production planner，不写 run artifact，不定义官方 cell size、bucket geometry、penetration depth、
payload proxy、calibrated effect/capability model、top-k、pass/fail、eval success 或 planner success
语义。

offline entry/exit swept-footprint effect evidence 的公共入口为
`testbed.eval.terrain_candidate_effect_model.build_entry_exit_swept_footprint_effect()`；具体实现放在 focused
owner `testbed.eval.terrain_candidate_entry_exit_effect`，避免把 entry/exit 线段算法继续堆入几何
effect facade。它读取单个
offline candidate、显式 `removed_depth_grid_m`、`target_depth_grid_m`、`target_region_mask`、
`valid_mask`、`grid_shape`、`cell_size_m`、`bucket_width_m`、`entry_cell_index`、
`exit_cell_index` 和 `target_penetration_depth_m`。entry / exit cell 必须是 row-major grid 内的
valid cell，且两者不能相同；这些入口、出口、宽度和 penetration 都是调用方输入，不从 current run
或配置推断。

该 helper 的 path model 明确命名为 `entry_exit_centerline_segment_approximation`，不是 calibrated
bucket physics。candidate direction 会作为 evidence 保留，但 swept centerline 使用显式 entry cell
center 到 exit cell center 的线段；cell center 在线段投影范围内且到线段的垂直距离不超过
`bucket_width_m / 2` 时进入 footprint。输出包含 `entry_exit_path`、target / outside-target /
valid / invalid footprint cells、row-major `expected_delta_depth_grid_m`、以及与 Phase 4A 相同口径的
expected / target / outside-target / overdig depth-sum 和 volume summary。top-level 状态包括
`present`、`invalid_candidate`、`invalid_grid_shape`、`invalid_grid_lengths`、
`invalid_mask_values`、`invalid_depth_values`、`invalid_geometry`、`invalid_entry_exit` 和
`no_valid_footprint_cells`。该 helper 只提供 offline entry/exit expected-delta evidence；它不定义
entry/exit default、official geometry、ACT capability、action selection、top-k、pass/fail、eval
success、planner success 或 production planner/gate/policy/runtime 语义。

offline candidate effect summary / payload proxy evidence 当前由
`testbed.eval.terrain_candidate_effect_summary.build_candidate_effect_summary()` 生成。它只读取 Phase 4A
effect records 和调用方显式传入的 `payload_capacity_m3`；该 capacity 是本次离线诊断输入，不写入
config，不作为官方 bucket payload、bucket geometry、material density 或 fill model 默认值。

summary record 按 effect record 输入顺序保留，包含 candidate id、effect status、expected removed
volume、target removed volume、outside-target removed volume、overdig volume delta、footprint cell
count、grid-boundary clipped flag、`payload_proxy_volume_m3 = min(expected_removed_volume_m3,
payload_capacity_m3)` 和 `payload_proxy_fraction`。当 expected removed volume 大于 0 时，还报告
outside-target volume fraction 和 overdig volume fraction；分母为 0 时这些 fraction 为 `None`，不虚构
比值。aggregate summary 汇总 payload proxy volume/fraction 的 min/max/mean、expected / target /
outside-target / overdig volume totals，以及 max payload proxy、max outside-target volume 和 max
overdig volume 的诊断 candidate id。

`diagnostic_rankings` 只提供 evidence-only 排序：payload proxy volume 降序、outside-target volume
降序、overdig volume 降序，tie-break 使用原输入顺序。该 ranking 不包含 selected/top-k/action 字段，
不接 production planner。top-level 状态包括 `present`、`no_effect_records`、
`invalid_effect_records` 和 `invalid_payload_capacity`，并保留 calibrated payload model、material
density、cycle time、bucket fill model 和 production integration 的 missing / not-integrated provenance。
该 helper 不定义 payload/capacity default、material density、cycle-time semantics、pass/fail、eval
success、planner success、top-k action selection 或 calibrated effect/capability model。

gold-sample calibration inventory / schema evidence 当前由
`testbed.eval.terrain_calibration_inventory.build_gold_sample_calibration_inventory()` 生成。它是
offline-only inventory helper，不训练 calibrated effect model，也不训练 capability model。调用方必须显式传入
`source_paths`、`required_fields` 和 `episode_split_key_candidates`；repo 不定义官方 gold-sample schema、
官方 required fields、官方 split keys、label 语义、payload capacity 或 material-density 默认值。

该 helper 只检查调用方给出的显式文件或目录；目录会在该显式 root 下递归枚举文件，不扫描整个 repo 或整个
`runs`。当前支持 JSONL object records 和 JSON list-of-object records；JSON metadata dict 会作为
metadata document 报告，但不会被当作 calibration records；不支持的文件后缀会计入 unsupported source，
解析错误保留在 source-level `parser_errors`，不会让整个 inventory 失败。一个 usable calibration record
必须同时包含全部显式 `required_fields`，并至少包含一个显式 split-key candidate。

输出包含 source/support/record/usable record counts、per-source summaries、required-field presence /
missing counts、split-key detection / distinct group counts、validation errors 和 missing provenance。top-level
状态包括 `present`、`no_sources`、`invalid_source_paths`、`invalid_required_fields`、
`invalid_split_keys` 和 `no_supported_sources`。如果支持源能解析但没有 usable records，状态仍为
`present`，并用 `usable_record_count=0`、missing-field counts 和 split evidence 暴露 gap。该 helper
不拟合模型、不虚构 labels、不声明 pass/fail、eval success、planner success、episode split 官方语义或
production integration。

同一 inventory 输出还包含 `observed_field_catalog` 和 `schema_gap_summary`。`observed_field_catalog`
只统计支持源中 JSON/JSONL object record 的原始 top-level field presence counts，并按 field 名稳定排序；
metadata document、unsupported source 和 parser error 不会被解释成 calibration schema。`schema_gap_summary`
只基于调用方显式传入的 `required_fields` 与 `episode_split_key_candidates` 汇总 gap：哪些 required
fields 在全部 records 中缺失、部分存在或全部存在，哪些 split-key candidates 出现或完全缺失，以及
这些事实对 `usable_record_count` 的影响。该 catalog/gap summary 不做 alias inference，不把 `label`、
`source_id`、`mass_in_bucket_kg` 或其他 telemetry field 自动映射成 success、payload 或 episode split 语义；
如需语义映射，必须在后续切片用显式 schema 决策单独定义。

explicit calibration record extraction / mapping feasibility evidence 当前由
`testbed.eval.terrain_calibration_extraction.build_explicit_calibration_record_extraction()` 生成。
它是 offline-only extraction helper，不训练 calibrated effect model，也不定义官方样本 schema。调用方必须显式传入
`source_paths`、`field_mapping`、`required_output_fields` 和
`episode_split_key_candidates`。`field_mapping` 是 caller-provided explicit raw-field mapping：
输出字段名指向原始 observed field 名；helper 只按这份 mapping 抽取字段，不做 alias inference，不把
`label`、`source_id`、`mass_in_bucket_kg`、`excavated_mass_kg` 或其他 telemetry fields 自动解释为
success、payload、split key、pass/fail、eval success 或 planner success。

该 helper 使用与 inventory 相同的显式 source-path 边界：只检查调用方给出的文件或目录，目录只在该显式 root
下递归枚举文件，不扫描整个 repo 或整个 `runs`。当前支持 JSONL object records 和 JSON list-of-object
records；JSON metadata dict 会作为 metadata document 报告，不作为 extracted records；unsupported source
和 parser error 都保留为 source-level facts。输出包含 mapping summary、extracted record count、
usable extracted record count、missing output-field summary、split summary、bounded sample record shape evidence、
validation errors 和 missing provenance。一个 usable extracted record 必须同时包含全部显式
`required_output_fields`，并至少包含一个显式 split-key candidate。top-level 状态包括 `present`、
`no_sources`、`invalid_source_paths`、`invalid_field_mapping`、`invalid_required_output_fields`、
`invalid_split_keys`、`no_supported_sources` 和 `no_records`。如果后续需要把 provisional telemetry mapping
提升为 calibration schema，必须单独确认字段语义、label 语义、split 语义和 compatibility policy。

offline residual planner baseline comparison 当前由
`testbed.eval.terrain_residual_baseline_comparison.build_residual_planner_baseline_comparison()` 生成。
它是 heuristic-only / offline-only evidence scaffold，不启动新 rollout，不写 run artifact，不接入 production
planner，也不定义官方 target success、pass/fail、eval success 或 planner success。调用方必须显式传入内存中的
current planner evidence、target residual report `diagnostic_summary`、Phase 3 candidate generation / constraint / scoring
evidence、Phase 4 effect summary evidence，以及 Phase 5 calibrated branch availability evidence。

该 helper 固定输出三条 branch summary：`current_planner_baseline`、`heuristic_residual_pipeline` 和
`calibrated_residual_pipeline`。current branch 只记录当前 rollout / target residual facts，并把 target
success 标为 `not_claimed`。heuristic branch 只汇总 candidate count、positive residual coverage、
constraint summary、diagnostic score ranking 和 effect-summary volume / payload-proxy evidence；它不输出
runtime selection、top-k action 或闭环优劣证明。calibrated branch 在 Phase 5 evidence 显示
`usable_record_count=0` 且 `usable_extracted_record_count=0` 时必须保持 `not_evaluated`，reason 为
`blocked_by_missing_gold_samples`，不能从 telemetry fallback 发明 calibrated model。

top-level status 包括 `present`、`invalid_current_planner_evidence`、`invalid_heuristic_evidence` 和
`invalid_calibrated_evidence`。`comparison_limits` 明确记录 `closed_loop_resimulation_status=not_run`、
counterfactual cycle count / cycle time 不可用、production integration 未接入、official success semantics 未定义、
calibrated-model fallback 未发明。完整 Phase 6 闭环 baseline comparison 仍需要真正的 A/B/C 多铲仿真证据。

offline closed-loop experiment manifest / artifact contract 当前由
`testbed.eval.terrain_residual_closed_loop_manifest.build_closed_loop_experiment_manifest()` 生成。
它是 eval-only manifest helper，用于把 Phase 6D 的 closed-loop simulation design 固化成可验证的
manifest shape；它不运行 simulation，不创建 run root，不写 `runs` artifact，不接入 production planner、
rollout-review schema 或 runtime action selection。

调用方必须显式传入 future `results_root`、target spec、A/B/C branch definitions、cycle budget、
stop conditions、expected metric names、expected artifact files 和 protected evidence roots。target spec 必须
包含 `grid_shape`、row / col bounds、`target_depth_m` 和 official / non-official marker；artifact files
必须是相对路径，不能是绝对路径或包含 `..` 的 escaping path。helper 会固定 branch order 为
`current_planner_baseline`、`heuristic_residual_pipeline`、`calibrated_residual_pipeline`：A branch 为
current planner baseline，B branch 为 heuristic residual pipeline 且保持 `runtime_integration_status=not_integrated`，
C branch 在没有 explicit calibration availability 时保持 `not_evaluated`，reason 为
`blocked_by_missing_gold_samples`。

manifest 输出包含 schema/source/status/offline_only、normalized branches、artifact layout、no-overwrite
validation、target spec、cycle budget、stop-condition summary、metric names、validation errors、non-goal statuses
和 provenance statuses。no-overwrite validation 会在 proposed results root 等于或嵌套在 protected evidence
root 下时返回 `protected_evidence_root_overlap`，防止覆盖既有 current-run evidence。top-level status 包括
`present`、`invalid_target_spec`、`invalid_branch_definitions`、`invalid_artifact_layout`、
`protected_evidence_root_overlap`、`invalid_cycle_budget`、`invalid_stop_conditions`、`invalid_metric_names`
和 `invalid_protected_evidence_roots`。该合同不输出 selected candidate、top-k、runtime action、pass/fail、
eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

offline branch run plan / executable cut-intent boundary contract 当前由
`testbed.eval.terrain_residual_closed_loop_branch_plan.build_closed_loop_branch_run_plan()` 生成。
它是 eval-only dry-run helper，用于把 Phase 6E-A manifest 和调用方显式 branch inputs 转成 A/B/C
per-branch run plan records；它不运行 A/B/C，不执行 cuts，不创建 branch output files，不写 `runs` artifact，
不接 production planner / rollout-review schema，也不输出 runtime action semantics。

调用方必须显式传入 `experiment_manifest`、`branch_inputs` 和 `cut_intent_contract`。manifest 必须来自
Phase 6E-A 形状：status `present`、固定 branch order、artifact layout 不写文件、no-overwrite validation
为 `present`。branch inputs 必须包含 `current_planner_baseline`、`heuristic_residual_pipeline` 和
`calibrated_residual_pipeline`。B branch 只记录 heuristic residual pipeline input readiness 与
cut-intent boundary status，并继续保持 `runtime_integration_status=not_integrated`。

cut-intent boundary 是 future runner contract only。它只列出 future executable cut intent 需要的字段，例如
`candidate_id`、anchor cell / row / col、direction、`candidate_depth_m`、score/rank provenance、
effect/evidence provenance、target spec provenance 和 safety/stop-condition provenance。它不携带实际 selected
candidate，不选择 top-k，不生成 runtime action，不声明 production readiness。C branch 在没有 explicit
calibration availability 时继续保持 `not_evaluated` / `blocked_by_missing_gold_samples`，不能从 telemetry
fallback 发明 calibrated model。top-level status 包括 `present`、`invalid_manifest`、`invalid_branch_inputs`
和 `invalid_cut_intent_contract`。

offline heuristic residual cut-intent generation 当前由
`testbed.eval.terrain_residual_cut_intent.build_heuristic_residual_cut_intent()` 生成。
它是 eval-only evidence helper，用于把 Phase 6E-B branch run plan、Phase 3 candidate generation /
constraint evidence / heuristic scoring 和 Phase 4 effect summary 转成一个 future harness 可消费的 B branch
cut-intent evidence record。它不运行 simulation，不创建 branch output files，不写 `runs` artifact，不接
production planner / rollout-review schema，也不生成 production runtime action。

调用方必须显式传入 `branch_run_plan`、`candidate_generation`、`candidate_evidence`、
`candidate_scoring`、`candidate_effect_summary`、`target_spec` 和 `selection_policy`。当前唯一实现的
selection policy 是 `score_ranking_first`：helper 读取 diagnostic offline scoring ranking 的第一名，
并在 candidate generation、constraint evidence 和 effect summary records 中逐项 cross-check 同一个
candidate id。通过后输出一个 `cut_intent`，包含 `cut_intent_candidate_id`、anchor cell / row / col、
direction、`candidate_depth_m`、score/rank provenance、effect evidence provenance、target spec provenance、
safety / stop-condition provenance status、`runner_input_status=ready_for_eval_harness`，以及
`production_runtime_action=False`。

该 helper 可以在 eval-only 范围内产生一个 selected cut-intent evidence，因为这是 future runner 输入的
核心缺口；但它仍不输出 top-k list、command-space controls、pass/fail、eval success、planner success、
official defaults、official thresholds 或 calibrated fallback。top-level status 包括 `present`、
`invalid_branch_run_plan`、`invalid_selection_policy`、`invalid_candidate_scoring`、
`invalid_candidate_generation`、`invalid_candidate_evidence`、`invalid_candidate_effect_summary` 和
`invalid_target_spec`。provenance statuses 显式标记 branch plan、candidate generation / evidence /
scoring / effect summary 和 target spec 都来自调用方显式输入，artifact write / runner execution 仍为
not written / not run。

offline predicted residual update / one-cut counterfactual 当前由
`testbed.eval.terrain_residual_cut_update.build_predicted_residual_update()` 生成。
它是 eval-only evidence helper，用于把一个 Phase 6E-C cut intent 与匹配的 Phase 4 effect delta patch
应用到显式 current removed-depth grid，并通过
`testbed.eval.terrain_target_metrics.build_target_residual_metrics()` 重新计算 before / after target residual
metrics。它不运行真实 simulation，不创建 branch output files，不写 `runs` artifact，也不接入 production
planner / rollout-review schema。

调用方必须显式传入 `cut_intent`、matching `effect_record`、`removed_depth_grid_m`、
`target_depth_grid_m`、`target_region_mask`、`valid_mask`、`grid_shape`，以及可选 `cell_size_m`。helper
验证 cut intent 为 `runner_input_status=ready_for_eval_harness` 且 `production_runtime_action=False`，
验证 effect record status 为 `present`、candidate id 匹配、`expected_delta_depth_grid_m` 与 grid 长度一致，
然后计算 `predicted_removed_depth_grid_m = removed_depth_grid_m + expected_delta_depth_grid_m`。不做物理仿真、
bucket clipping 或 runtime command 生成。

输出包含 schema/source/status/offline_only、`cut_intent_candidate_id`、before metrics、after metrics、
delta summary、predicted removed-depth grid、validation errors、non-goal statuses 和 provenance statuses。
delta summary 至少记录 target positive residual delta、target overdig delta、outside-target removed-depth delta、
target completion ratio delta 和 expected delta depth sum；只有在调用方显式提供 `cell_size_m` 时才记录 volume
deltas。top-level status 包括 `present`、`invalid_cut_intent`、`invalid_effect_record`、
`candidate_effect_mismatch`、`invalid_grid_lengths`、`invalid_grid_shape`、`invalid_depth_values`、
`invalid_mask_values`、`invalid_cell_size` 和 `invalid_metric_inputs`。该 helper 仍不声明 pass/fail、
eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

offline predicted B-branch rollout loop 当前由
`testbed.eval.terrain_residual_predicted_rollout.build_predicted_residual_rollout()` 生成。
它是 eval-only evidence helper，用于在内存中重复执行 B branch heuristic residual pipeline：
target residual metrics -> discrete candidate generation -> constraint evidence -> heuristic scoring ->
geometric effect model -> effect summary -> heuristic cut intent -> predicted residual update。它实际迭代
`predicted_removed_depth_grid_m`，但不运行真实 simulation，不创建 branch output files，不写 `runs`
artifact，也不接入 production planner / rollout-review schema 或 command-space control。
输入解析、option provenance 和结果结构由
`testbed.eval.terrain_residual_predicted_rollout_contract` 承担，以保持 rollout 编排 owner 聚焦且低于
仓库 large-file threshold；公开 helper 和行为契约仍在
`build_predicted_residual_rollout()`。

调用方必须显式传入 `branch_run_plan`、initial removed-depth grid、target depth grid、target-region mask、
valid mask、grid shape、target spec、cycle budget、candidate generation options、candidate constraint options、
scoring weights、effect geometry、payload capacity 和 selection policy。当前 selection policy 仍只支持
`score_ranking_first`，cycle budget 必须显式提供 finite positive `max_cycles`；helper 不定义官方 target、
threshold、payload、geometry 或 stop-condition 默认值。

输出包含 schema/source/status/offline_only、step count、stop reason、initial metrics、final metrics、
per-step records、final predicted removed-depth grid、aggregate delta summary、validation errors、non-goal
statuses 和 provenance statuses。每个 step record 记录 step index、`cut_intent_candidate_id`、candidate /
evidence / scoring / effect / intent / update statuses、before / after target positive residual、overdig、
outside-target removed depth、completion ratio，以及 expected delta depth / volume。stop reason 包括
`max_cycles_reached`、`zero_target_positive_residual`、`no_positive_residual_cells` 和
`no_valid_candidate_path`；这些都是 diagnostic stop reasons，不是 pass/fail、eval success 或 planner success
语义。

offline predicted A/B residual comparison 当前由
`testbed.eval.terrain_residual_baseline_comparison.build_predicted_residual_ab_comparison()` 生成。
它是 Phase 6E-F eval-only comparison helper，用于把 current planner A 的真实 current-run residual
evidence 与 Phase 6E-E predicted B rollout counterfactual 放进同一个显式离线输出。它不运行 simulation，
不创建 branch output files，不写 `runs` artifact，不接入 production planner / rollout-review schema，也不把
effect-model counterfactual 解释成真实 closed-loop 结果。

调用方必须显式传入 `current_planner_evidence`、`target_residual_report`、`predicted_b_rollout` 和
`calibrated_branch_evidence`。输出固定三条 branch：A branch `evidence_type=current_rollout_evidence`，
只记录 current rollout / target residual facts 并保持 target success `not_claimed`；B branch
`evidence_type=predicted_counterfactual`，记录 predicted rollout step count、stop reason、selected
eval-only cut-intent candidate ids、initial / final positive residual、completion ratio、overdig、
outside-target removed depth，以及 aggregate expected delta depth / volume；C branch 在 Phase 5/6 evidence
显示没有 usable gold samples 时继续保持 `not_evaluated` / `blocked_by_missing_gold_samples`。

top-level status 包括 `present`、`invalid_current_planner_evidence`、`invalid_predicted_rollout_evidence` 和
`invalid_calibrated_evidence`。`comparison_limits` 明确记录 A 为 current rollout evidence，B 为 predicted
counterfactual，B real simulation `not_run`、production integration `not_integrated`、official success semantics
/ official threshold `not_defined`、calibrated-model fallback `not_invented`。该 helper 不输出 pass/fail、
eval success、planner success、production readiness、command-space controls、official thresholds 或 calibrated fallback。

Phase 6F-A 的 predicted A/B artifact materialization 由
`testbed.eval.terrain_residual_ab_artifact_writer.write_predicted_residual_ab_artifacts()` 负责。
该 helper 不重新计算 planner 证据；调用方必须显式传入已经构建好的 `experiment_manifest`、
`branch_run_plan`、`predicted_b_rollout`、`predicted_ab_comparison`、`source_rollout_path`、`results_root`
和 `protected_evidence_roots`。它只做 eval-only JSON artifact 写入，把 Phase 6E-F 的 in-memory
comparison 物化到新的非覆盖 results root。

写入前会验证 results root 位于当前 repo 内、不是 protected evidence root 本身或其子路径、且写入前不存在；
也会验证 manifest / branch plan / predicted rollout / predicted A-B comparison 的 required status。输出
固定写入 `eval_run_metadata.json`、`experiment_manifest.json`、`branch_run_plan.json`、
`predicted_b_rollout.json`、`residual_cut_intent_runtime_source.json`、
`branch_comparison_report.json` 和 `rollout_manifest.json`。所有 JSON 文件使用
deterministic sorted-key formatting 并以 newline 结束，便于后续 diff / manifest 检查。

writer status 包括 `present`、`invalid_results_root`、`protected_evidence_root_overlap`、
`results_root_already_exists`、`invalid_evidence` 和 `write_failed`。该 writer 不运行 simulation、不创建
production runtime action、不输出 command-space controls、不定义 pass/fail、eval success、planner success、
official defaults / thresholds、production readiness 或 calibrated fallback。

Phase 6F-B 的 predicted A/B artifact pipeline 当前由
`testbed.eval.terrain_residual_ab_artifact_pipeline.build_and_write_predicted_residual_ab_artifacts()`
负责。该 helper 是 eval-only orchestration owner：它从显式 `source_rollout_path` 读取 rollout JSONL，
用显式 target spec / cycle budget / candidate options / scoring weights / effect geometry / payload capacity
重建 current target residual report、Phase 6E-A manifest、Phase 6E-B branch plan、Phase 6E-E predicted
B rollout、Phase 6G-E residual cut-intent runtime source、Phase 6E-F predicted A/B comparison，然后调用
Phase 6F-A writer 物化 artifact。

调用方必须显式传入 `results_root`、`protected_evidence_roots` 和
`residual_cut_intent_runtime_source_inputs`。runtime source inputs 必须包含 `cell_centers_m`、
`direction_vectors`、`bucket_length_m` 和 `payload_kg`；pipeline 不从 effect geometry、payload capacity、
当前 `runs`、env vars 或默认配置推断这些 runtime adapter 输入。pipeline 会保留 writer 的 no-overwrite
边界：如果 proposed results root 等于或嵌套在 protected evidence root 下，manifest / writer 链会返回
`protected_evidence_root_overlap`，不会创建 artifact。输出包含 schema/source/status/offline_only、
source record count、nested statuses、artifact summary、branch statuses、predicted B rollout summary、
comparison delta summary、validation errors、non-goal statuses 和 provenance statuses。

pipeline status 包括 `present`、`invalid_source_rollout`、`invalid_target_spec`、
`invalid_pipeline_options`、`invalid_runtime_source_inputs`、`protected_evidence_root_overlap`、
`results_root_already_exists` 以及下游 evidence / writer 的具体 validation status。该 pipeline 会创建新的 eval results artifact root，但仍不运行真实 simulation、
不创建 production runtime action、不输出 command-space controls、不定义 pass/fail、eval success、
planner success、official defaults / thresholds、production readiness 或 calibrated fallback。

Phase 6F-C 的 runner-facing CLI entrypoint 是 `tb-terrain-residual-ab-artifacts`，实现位于
`testbed.cli.terrain_residual_ab_artifact_pipeline`。CLI 是 pipeline 的薄入口：调用方必须通过
`--request-json` 传入一个 JSON object，字段与
`build_and_write_predicted_residual_ab_artifacts()` 的显式输入一致，包括
`residual_cut_intent_runtime_source_inputs`；CLI 不提供 official target、threshold、geometry、payload、
runtime source adapter 输入或 scoring 默认值。`--output-json` 可选，用于保存 top-level pipeline
result；未提供时结果写到 stdout。

CLI 返回码只表达入口执行状态：pipeline status 为 `present` 时返回 `0`，request JSON 无效时返回 `2`，
其他 pipeline validation status 返回 `1`。这些返回码不是 eval pass/fail、planner success 或 production
readiness 语义。CLI 仍只运行 eval-only predicted counterfactual pipeline；它不运行 simulation、不接
production planner / rollout-review schema，也不生成 runtime action。

Phase 6G-A 的 residual eval run command plan 当前由
`testbed.eval.terrain_residual_eval_run_plan.build_residual_eval_run_plan()` 负责。
该 helper 是 eval-only run-plan owner：它接收 current baseline `eval_run_metadata`、Phase 6F predicted
A/B artifact summary、future planned results root、protected evidence roots、residual runtime
integration availability，以及默认关闭的显式 residual runtime planner mode / residual cut-intent token
adapter / residual cut-intent source provider availability evidence。
它不读取隐式全局配置、不启动 `tb-eval`、不创建 run root、不写 artifact。

输出包含 schema/source/status/offline_only、固定 A/B/C branch order、per-branch command plan、
artifact input summary、no-overwrite validation、validation errors、non-goal statuses 和 provenance statuses。
A branch 会从 current baseline `argv` 还原 `tb-eval` 命令，并把 `--output-dir` 改写到新的
`<planned_results_root>/current_planner_baseline`。B branch 在 residual runtime integration 不可用时保持
`not_runnable`，并默认记录四个直接 blocker：missing residual runtime planner mode、missing cut-intent to
dig-cut token adapter、missing residual cut-intent source provider、missing simulated branch execution artifacts。
Phase 6G-B 之后，如果调用方显式证明
`residual_cut_intent_token_adapter_available=True`，B branch 仍保持 `not_runnable`，但 adapter blocker 会被移除，
剩余 blocker 为 missing residual runtime planner mode、missing residual cut-intent source provider 和
missing simulated branch execution artifacts。Phase 6G-C
之后，如果调用方同时显式证明 `residual_runtime_planner_mode_available=True` 和
`residual_cut_intent_token_adapter_available=True`，B branch 仍保持 `not_runnable`，但 runtime-mode / adapter
blockers 都会被移除，剩余 blocker 为 missing residual cut-intent source provider 和
missing simulated branch execution artifacts。Phase 6G-D 之后，如果调用方也显式证明
`residual_cut_intent_source_provider_available=True`，B branch 仍保持 `not_runnable`，但 source-provider blocker
会被移除，剩余 blocker 为 missing simulated branch execution artifacts。C branch 在无 usable gold samples 时继续
`not_evaluated` / `blocked_by_missing_gold_samples`。

run-plan status 包括 `present`、`invalid_current_eval_metadata`、`invalid_predicted_ab_artifacts`、
`invalid_residual_runtime_integration`、`invalid_planned_results_root` 和
`protected_evidence_root_overlap`。如果调用方声明 residual runtime integration available，则必须显式提供
B branch argv；该 helper 不发明 planner mode、config override、command-space controls、official thresholds、
pass/fail、eval success、planner success、production readiness 或 calibrated fallback。

Phase 6G-B 的 residual cut-intent dig-cut token adapter 当前由
`testbed.planner.primitive.token.residual_cut_intent.build_residual_cut_intent_dig_cut_token()` 负责。
该 helper 是 offline primitive token adapter owner：它接收 Phase 6E-C eval-only cut intent 或 nested
`cut_intent` record、显式 `cell_centers_m`、显式 `direction_vectors`、`bucket_length_m` 和 `payload_kg`，
输出现有 primitive planner dig-cut raw fields 和 `dig_cut_tokens` plain list。`cell_centers_m` 支持
integer/string cell id 到 `{x_m, z_m}` 或 two-item sequence 的映射；`direction_vectors` 只按 cut-intent
direction 查找 two-item x/z vector 并归一化。

Adapter 使用 `testbed.data.operator_first_v2_2` 的 dig-cut token dimension / scale constants，并通过
`DigCutTokenPlanner.plan_from_raw_fields()` 生成现有 token order：entry x/z、exit x/z、direction x/z、
length、depth、payload、valid。`payload_kg` 同时写入 `operator_cut_payload_gain_kg` 和
`operator_effective_deposit_delta_kg`；`operator_entry_y_m` / `operator_exit_y_m` 固定为 `0.0` 是 offline
adapter convention，不是 official geometry。该 helper 不推断 grid-to-world axes、不定义 official geometry、
不新增 planner mode、不运行 simulation、不写 `runs` artifact，也不生成 production runtime action。

Phase 6G-C 的 residual cut-intent runtime planner mode 当前由
`testbed.planner.primitive.token.dig_planning.PrimitiveDigTokenPlanningService` 负责。
该 mode 只通过显式 `residual_cut_intent_plan_provider(obs)` 消费 caller-provided
`DigCutTokenPlan` 或 existing dig-cut raw-fields tuple，并复用现有 `apply_dig_cut_token_plan()` 写入
dig-cut token state。`PrimitiveTokenPlanningRuntimePorts` 只传递这个 provider；默认 provider 为 `None`。
如果 provider 缺失、返回 no plan 或抛错，只有 `dig_cut_planner_fallback_mode=conservative_pose` 时才使用现有
conservative fallback，否则抛出错误。`dig_cut_planner.mode=residual_cut_intent` 已被 config validation 接受，
但不是默认值；该 mode 不读取全局文件、env vars、`runs` artifacts 或隐藏状态，不运行 simulation，不写
branch output files，不改 eval YAML/default config/production planner decisions/rollout-review schema/CLI entrypoint，
也不定义 command-space controls、official thresholds、pass/fail、eval success、planner success 或 calibrated fallback。

Phase 6G-D 的 residual cut-intent runtime source provider 当前由
`testbed.planner.primitive.token.residual_cut_intent_source.build_residual_cut_intent_plan_provider_from_source_path()`
负责。该 helper 只在调用方显式提供 `dig_cut_planner.residual_cut_intent_source_path` 时读取一个 JSON source；
空 path 返回 `None`，不会扫描当前 `runs`、环境变量、默认配置或隐藏全局状态。source contract 为
`residual_cut_intent_runtime_source_v1` / `explicit_residual_cut_intent_runtime_source`，必须显式列出
cycle-indexed plans；每个 plan 可以包装 Phase 6G-B adapter output，并提供 `dig_cut_tokens`、`raw_fields`、
plan `source` 和可选 `fallback_reason`。provider 通过当前 primitive cycle index 做确定性 exact-cycle lookup；
missing file、invalid JSON、invalid plan status、invalid token/raw-field shape、duplicate cycle 或 missing cycle 都以
`ResidualCutIntentPlanSourceError` 明确暴露。

`PrimitivePlannerACTPolicy` 只保存 optional `residual_cut_intent_source_path` 并把它焊接到
`PrimitiveTokenPlanningRuntimePorts.residual_cut_intent_plan_provider`；默认值仍为空，`dig_cut_planner.mode` 默认仍为
`conservative_pose`。该 source provider 不运行 simulation、不创建 `runs` artifact、不写 branch output files、
不改 eval YAML/default config/production planner decisions/rollout-review schema/CLI entrypoint，也不定义
command-space controls、official thresholds、pass/fail、eval success、planner success 或 calibrated fallback。

Phase 6G-E 的 residual cut-intent runtime source artifact materialization 当前由
`testbed.eval.terrain_residual_cut_intent_runtime_source.build_residual_cut_intent_runtime_source()` 与
Phase 6F writer/pipeline 共同负责。predicted rollout per-step records 保留 nested eval-only `cut_intent`
record；runtime source builder 将该 record 与显式 `cell_centers_m`、`direction_vectors`、`bucket_length_m`、
`payload_kg` 传入 Phase 6G-B adapter，生成 cycle-indexed `plans`。写出的 source JSON 使用
`residual_cut_intent_runtime_source_v1` / `explicit_residual_cut_intent_runtime_source` 常量，可由
`build_residual_cut_intent_plan_provider_from_source_path()` 读取。

如果 `residual_cut_intent_runtime_source_inputs` 缺失或无法让 adapter 构造 present plan，pipeline 返回
`invalid_runtime_source_inputs`，CLI request 缺字段时返回 `invalid_request`；这些失败都会在 writer 前停止，
不会创建 results root。该 materialization 仍是 eval-only artifact 生成：不运行 `tb-eval` 或 simulation，
不生成 production runtime action，不定义 command-space controls、official thresholds、pass/fail、eval success、
planner success、production readiness 或 calibrated fallback。

Phase 6G-F 的 B-branch runner-facing eval request 当前由
`testbed.eval.terrain_residual_b_branch_eval_request.write_residual_b_branch_eval_request()`
负责。该 helper 是 eval request artifact owner：它读取显式 `current_eval_metadata`、Phase 6G-E
`predicted_ab_artifact_root`、`runtime_source_path`、fresh `request_root`、fresh `planned_results_root`
和 `protected_evidence_roots`，然后写出真实 `tb-eval` 可消费的 B branch config/argv/request artifacts。
CLI entrypoint 是 `tb-terrain-residual-b-branch-request`，只读取 `--request-json`，可选
`--output-json` 写出 top-level request result。

request writer 不改任何 checked-in eval YAML/default config。它从 current eval config 复制一份 request-local
`heuristic_residual_pipeline_eval_config.yaml`，并只在该 artifact config 内显式设置：
`dig_cut_planner.enabled=true`、`dig_cut_planner.mode=residual_cut_intent`、
`dig_cut_planner.residual_cut_intent_source_path=<runtime_source_path>`、
`dig_cut_planner.fallback_mode=raise`、`dig_cut_planner.hold_token_until_skill_exit=false` 和
`dig_cut_planner.prior_path=""`。这些值让 B branch 使用 explicit source provider，避免缺 source 时静默回落到
conservative pose，也避免 residual source path 仍依赖 legacy prior。

request root 固定写入 `heuristic_residual_pipeline_eval_config.yaml`、
`heuristic_residual_pipeline_invocation.json` 和 `residual_eval_run_plan.json`。`residual_eval_run_plan.json`
中的 B branch argv 指向 request-local config，并把 `--output-dir` 改写到
`<planned_results_root>/heuristic_residual_pipeline`；planned branch output root 只作为 expected output
记录，request writer 不创建它。该 helper 的 no-overwrite guard 会拒绝 pre-existing request root、
pre-existing planned results root，以及 request/planned root 与 protected evidence root 的 same-or-nested overlap。

Current-run Phase 6G-F smoke facts：fresh predicted artifact root
`runs/eval/oracle_terrain_residual_phase6g_f_predicted_ab_with_source_20260702/results`
写出 7 个 files，并包含 status `present` 的 `residual_cut_intent_runtime_source.json`；runtime source
plan count 为 `1`，candidate id 为 `cut_candidate_000009`。B request root
`runs/eval/oracle_terrain_residual_phase6g_f_b_branch_request_20260702` 写出 3 个 request files，
CLI result 后该 root file count 为 `4`。planned full root
`runs/eval/oracle_terrain_residual_phase6g_f_real_ab_20260702` 没有被 request writer 创建；protected
current results file count stayed `10 -> 10`。

一次最小真实 B-branch smoke 使用 generated config、fresh smoke output root、
`--target-cycle-gate 1` 和 `--no-video` 启动 `tb-eval`。runner 成功加载 residual mode/source，并执行到
primitive runtime 请求 cycle `1`，随后因 source 只有 cycle `0` plan 而失败：
`ResidualCutIntentPlanSourceError: residual_cut_intent source missing plan for cycle_index 1`。
该 smoke 只留下 partial branch artifacts：
`runs/eval/oracle_terrain_residual_phase6g_f_real_b_smoke_20260702/heuristic_residual_pipeline/results/eval_resolved_config.yaml`、
`eval_run_metadata.json(status=failed)` 和 `rollouts/rollout_000.partial.jsonl`。这不是 eval success 或
planner success；它把剩余 blocker 缩小为 runtime source cycle coverage / runner stop-timing contract。

Phase 6G-G 将该 blocker 缩小为 request/eval stop-timing contract：failed smoke 的
`--target-cycle-gate 1` 只覆盖 gate 数值，generated config 仍继承
`eval.target_cycle_gate_terminal_hold_steps=100`，所以第一个 dump 结束后 runner 继续 terminal hold，
下一 tick 请求 primitive cycle `1`，而 Phase 6G-E source 只显式覆盖 cycle `0`。

B-branch request writer 现在只在 request-local `heuristic_residual_pipeline_eval_config.yaml` 中额外显式设置
`eval.target_cycle_gate_terminal_hold_steps=0`，并在 request result 的 `runtime_config` 记录
`eval.target_cycle_gate_terminal_hold_steps: 0`。该合同不改变 checked-in eval YAML/default config，
不改 `tb-eval` CLI，不改 provider exact lookup，也不引入 hidden fallback、last-plan reuse 或 source
cycle 扩展。

Fresh Phase 6G-G smoke facts：predicted source root
`runs/eval/oracle_terrain_residual_phase6g_g_predicted_ab_with_source_20260702/results`
写出 7 个 predicted artifacts，runtime source status `present`，plan count `1`，cycle coverage `[0]`。
B request root `runs/eval/oracle_terrain_residual_phase6g_g_b_branch_request_20260702`
写出 3 个 request files；generated config 中 `target_cycle_gate_terminal_hold_steps: 0`。真实 bounded
B smoke root
`runs/eval/oracle_terrain_residual_phase6g_g_real_b_smoke_20260702/heuristic_residual_pipeline/results`
status `completed`、error `null`，`target_cycle_gate_success_rate=1.0`，rollout stop reason
`target_cycle_gate_reached`。这只是 bounded smoke stop-timing evidence，不是 official eval success、
planner success、pass/fail、production readiness 或 calibrated fallback。

Phase 6G-H 的 same-gate real A/B bounded smoke comparison 当前由
`testbed.eval.terrain_residual_real_ab_smoke_comparison.write_current_planner_bounded_smoke_request()`
和 `write_real_ab_bounded_smoke_comparison()` 负责。A request helper 读取显式 current eval metadata，
复制 current planner eval config 到 request artifact，并只在该 artifact config 内设置
`eval.target_cycle_gate=1`、`eval.target_cycle_gate_terminal_hold_steps=0` 和 `eval.save_video=false`；
它保留 current planner `dig_cut_planner.mode=operator_prior_sweep_belief`，不改变 checked-in
eval YAML/default config。comparison helper 只读取真实 `tb-eval` result roots 的
`eval_run_metadata.json`、`eval_resolved_config.yaml`、`metrics.json`、`rollout_manifest.json`、
`rollouts/rollout_000_summary.json` 和 rollout jsonl line count，不使用 predicted B evidence 代替真实 B
execution artifacts。

Current-run Phase 6G-H smoke facts：fresh comparison root
`runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702`
初始不存在。A request root
`runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/current_planner_baseline_request`
写出 request-local config、invocation 和 request result。A smoke 使用 generated config、
`--target-cycle-gate 1`、`--no-video` 和 fresh output root
`runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/real_smoke_runs/current_planner_baseline`
运行 `tb-eval`，exit code `0`；A metadata status `completed`、error `null`，
`target_cycle_gate_success_rate=1.0`，stop reason `target_cycle_gate_reached`，rollout line count `736`。
B branch 没有重跑，复用 completed Phase 6G-G root
`runs/eval/oracle_terrain_residual_phase6g_g_real_b_smoke_20260702/heuristic_residual_pipeline/results`；
B metadata status `completed`、error `null`，`target_cycle_gate_success_rate=1.0`，stop reason
`target_cycle_gate_reached`，rollout line count `708`，config 使用
`dig_cut_planner.mode=residual_cut_intent` 和显式 runtime source path。

Durable comparison artifact
`runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/real_ab_bounded_smoke_comparison.json`
status `present`，branch order 为 `current_planner_baseline`、`heuristic_residual_pipeline`、
`calibrated_residual_pipeline`；C 继续 `not_evaluated` / `blocked_by_missing_gold_samples`。该 artifact
明确标注 `evidence_scope=bounded_one_cycle_smoke`、`full_phase6_success_claim=not_claimed`、
`official_pass_fail_status=not_defined`、`production_readiness_status=not_claimed` 和
`calibrated_fallback_status=not_invented`。Protected current evidence root file count stayed `10 -> 10`。

Phase 6G-I 的 smallest multi-cycle probe 将 explicit gate 提到 `target_cycle_gate=2` 前，先要求
B-branch runtime source 显式覆盖 runner 会请求的 primitive cycle plans。B request writer / CLI 现在支持
request-local optional `target_cycle_gate`：当该字段存在时，它会在写 request root 之前检查
`residual_cut_intent_runtime_source.json` 是否覆盖 cycles `[0, target_cycle_gate)`；覆盖不足时返回
`invalid_runtime_source`，不创建 request root 或 planned results root。覆盖足够时，writer 只在 request-local
config 和 argv 中写入 `eval.target_cycle_gate=<target_cycle_gate>`，不改变 checked-in eval YAML/default config。

Current-run Phase 6G-I coverage facts：fresh predicted probe root
`runs/eval/oracle_terrain_residual_phase6g_i_multicycle_coverage_probe_20260702/results`
写出 7 个 predicted artifacts；`predicted_b_rollout.json` status `present`、step count `1`、stop reason
`zero_target_positive_residual`；`residual_cut_intent_runtime_source.json` status `present`、plan count `1`、
cycle coverage `[0]`、candidate id `cut_candidate_000009`。Fresh B request input root
`runs/eval/oracle_terrain_residual_phase6g_i_b_branch_request_inputs_20260702` 写出 request/result files `2`；
request CLI for `target_cycle_gate=2` returned `invalid_runtime_source` with validation error
`runtime source missing required cycle plans for target_cycle_gate 2: [1]`。

Planner recovery facts：the original predicted source cleared target positive residual in one predicted step. `max_candidate_depth_m`
is constraint/scoring evidence rather than a hard generator cap, so the recovery used explicit
`depth_fraction_options=[0.1]`, `min_candidate_count=1`, and `max_cycles=3` under the same explicit non-official target
spec. Fresh source root `runs/eval/oracle_terrain_residual_phase6g_i_fraction_010_depth025_min1_20260702/results`
produced `predicted_b_rollout.json` status `present`, step count `3`, stop reason `max_cycles_reached`, and runtime
source cycle coverage `[0, 1, 2]` with candidate id `cut_candidate_000003`。With that source, gate-2 B request root
`runs/eval/oracle_terrain_residual_phase6g_i_gate2_b_branch_request_20260702` was written, and real A/B bounded smoke
roots were written under `runs/eval/oracle_terrain_residual_phase6g_i_gate2_real_ab_20260702/`.

Corrected comparison artifact
`runs/eval/oracle_terrain_residual_phase6g_i_gate2_real_ab_20260702/real_ab_gate2_bounded_smoke_comparison.json`
has status `present`, validation errors `[]`, and `evidence_scope=bounded_multi_cycle_smoke`。A/current reached
`target_cycle_gate=2` with `target_cycle_gate_success_rate=1.0`, `target_cycle_completed_dump_count=2`, stop reason
`target_cycle_gate_reached`, and rollout line count `1383`。B/residual runtime completed but did not meet the gate:
`target_cycle_gate_success_rate=0.0`, `target_cycle_completed_dump_count=0`, empty gate stop reason, and rollout line
count `921`。C remains `not_evaluated` / `blocked_by_missing_gold_samples`; no hidden fallback, last-plan reuse,
source repetition, official pass/fail, eval success, planner success, production readiness, command-space controls,
or calibrated fallback is claimed.

Phase 6G-J root-cause review inspected the gate-2 result roots read-only. B did consume residual dig-cut tokens from
the explicit runtime source (`dig_cut_token_source=explicit_residual_cut_intent_dig_cut_token`, source status
`present`, plan count `3`, cycles `[0, 1, 2]`) and had a physical dump event (`dump_start_mask=1`,
`dump_end_mask=1`). The gate count still stayed zero because the eval summary used `coverage_completed_dump_count=0`;
coverage effect runtime currently covers `operator_prior_coverage` / `operator_prior_sweep_belief`, while B runs
`dig_cut_planner.mode=residual_cut_intent`. The first behavioral divergence after B's dump is handoff-related: A
enters return and reaches the next qualified dig start, but B switches directly from dump to dig with
`return_target_token_source=fallback_zero`, remains in `cycle_id=0`, and then fails the next dig with
`dig_failed_bad_dig_low_payload`. The next implementation slice should therefore target an explicit residual
return-target / cycle-handoff contract after dump, or a narrowly justified count fix if fresh evidence proves the
count is wrong; it must not introduce hidden fallback, source repetition, official pass/fail, eval success, planner
success, production readiness, command-space controls, or calibrated fallback.

Phase 6G-K implements the core handoff contract instead of changing the gate count. Residual return-target planning is
owned by `testbed.planner.primitive.token.return_planning.PrimitiveReturnTokenPlanningService`: when
`dig_cut_planner.mode=residual_cut_intent`, it consumes only an explicit
`residual_cut_intent_return_target_plan_provider` and derives return target tokens from that plan through existing
return-target prefix semantics, such as `conditioned_return_explicit_residual_cut_intent_dig_cut_token`. The policy
shell builds this provider from the same request-local `dig_cut_planner.residual_cut_intent_source_path` as the active
dig provider, but with `cycle_index + 1` lookup so return prepares the next dig while active dig remains exact current
cycle. Missing provider/source still follows the existing error/fallback-zero diagnostic path; there is no hidden
fallback, last-plan reuse, source repetition, checked-in eval YAML/default config change, official pass/fail,
planner-success, production-readiness, command-space-control, or calibrated-fallback claim.

Phase 6G-L keeps the return-start envelope and dig-cut token contracts distinct while fixing residual envelope prior
selection. When a residual return-target plan comes from explicit request-local raw fields, return planning now maps
that next-dig entry to the nearest existing coverage corridor; the existing corridor-to-cell mapping then selects
`return_start_envelope_cells`. If no coverage prior/corridors exist, the previous live-current-observation envelope
fallback remains diagnostic behavior. A fresh B smoke using only a request-local config restore of
`testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json` confirmed the source changed to
`qc6_return_start_envelope_cell_2+relocate_spatial_linear+relocate_qpos_linear`; the transition still timed out with
`completed_transition_count=0` because entry-close never became true (`min return_to_dig_entry_error_m ~= 0.781m`
against `0.55m`) and the envelope gate still failed plane-depth/qpos checks.

Phase 6G-P isolated that blocker from residual source token geometry. A mixed-source B smoke kept cycle `0` on the
original residual active-dig plan so the rollout reached carry, dump, and return, while cycles `1` / `2` used
corridor-conditioned next-cycle return target / relocate tokens. Return still timed out with
`completed_transition_count=0`, `transition_timeout_count=1`, `entry_close_count=0`, and `envelope_ready_count=0`.
The closest entry row remained just outside the entry gate (`return_to_dig_entry_error_m ~= 0.572m`) and still failed
contact, depth, and qpos checks. This makes the next training/eval question a return ACT trajectory and dump-exit
state comparison against the working 2026-06-16 handoff, not another residual-source coordinate variant by default.

Phase 6G-Q compared the residual B return trajectory against the working 2026-06-16 handoff. The diagnostic cleared
source fallback, near-origin return tokens, and handoff reporting as the first blocker for 6G-P: all analyzed 6G-P
return rows used nonzero corridor-conditioned return target / relocate tokens and a QC6 cell-0 return-start envelope.
The persistent failures were `local_depth_m`, `plane_depth_m`, `dig_contact`, and `qpos_3`; in contrast, the working
transition row reached `return_to_dig_entry_error_m ~= 0.099m`, `return_to_dig_start_envelope_error=0.0`, contact
true, and no failed checks. The next training/eval question is therefore whether the selected cell-0 envelope target
is compatible with residual B dump-exit terrain/contact state, not whether another residual-source coordinate variant
can improve the return token.

Phase 6G-R narrowed that question to the prior artifact used for the return-start envelope. The 6G-P checked-in prior
`yulong_removed_depth_dig_cut_prior_v3` selected cell `0` consistently, but its target required local/plane depth and
contact that the residual B dump-exit and return trajectory never reached. The known working run used the existing
surface-depth prior artifact from
`runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/`, with explicit shallow local-depth stats and a
plane-depth p05 of `0.0`. The next smoke should be a request-local prior-path counterfactual only; do not treat it as
a checked-in default promotion.

Phase 6G-S ran that request-local prior-path counterfactual. The generated config under
`runs/eval/oracle_terrain_residual_phase6g_s_surface_prior_counterfactual_20260703_r1/` changed only
`policy.dig_cut_planner.prior_path`, preserving the 6G-P mixed source, `target_cycle_gate=2`, terminal hold `0`,
residual mode, fallback policy, and return-start envelope gate settings. The B smoke root
`runs/eval/oracle_terrain_residual_phase6g_s_real_b_smoke_20260703_r1/heuristic_residual_pipeline/results`
completed with `target_cycle_gate_success_rate=1.0`, `target_cycle_completed_dump_count=2`,
`completed_transition_count=1`, and `transition_timeout_count=0`. The completed handoff selected
`qc6_return_start_envelope_cell_1+relocate_spatial_linear+relocate_qpos_linear` and passed local-depth,
plane-depth, contact, and qpos checks. This supports a prior-artifact compatibility blocker, but it is not a
checked-in prior/default promotion.

Phase 6G-T reran a fresh bounded gate-2 A/B smoke with the surface-prior B config. Both A and B reached the bounded
gate with terminal hold `0`; C remained `not_evaluated` / `blocked_by_missing_gold_samples`. The explicit target
residual projection showed a small B improvement over A (`target_positive_residual_depth_sum_m` delta
`-0.000311200623`, completion ratio delta `+0.000622401246`, outside-target removed depth delta
`-0.016043230891`, target overdig delta `0.0`). That residual projection improvement has an execution-quality caveat:
B deposited fraction and depth command tracking were worse than A in the same smoke. Treat 6G-T as bounded evidence
for the residual path and prior compatibility, not as full Phase 6 success or production readiness.

Phase 6G-U adds `testbed.eval.terrain_cycle_quality_report` as the focused owner
for per-cycle residual / payload / deposit / handoff / execution-quality
diagnostics. The owner consumes explicit rollout artifacts
(`rollout_000.jsonl` and `rollout_000_summary.json`) plus either a
caller-provided target spec or an official target id, and writes no-overwrite
JSON reports. It preserves planned/actual entry and exit coordinates plus depth
target / peak / error fields from the rollout summary, and it can attach
official v0 pass/fail output when an A-baseline quality summary is supplied.

Request-local default T1/T2 assumptions were materialized under
`runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/` for
posthoc projection on the existing gate-2 A/B rollouts. T1 uses rows `[0, 2)`,
cols `[0, 2)`, depth `0.25m`; T2 uses rows `[0, 3)`, cols `[0, 1)`, depth
`0.25m`. The comparison artifact
`phase6_request_local_default_t1_t2_ab_comparison.json` records that B is worse
than A on T1 positive residual (`+0.015732030268`) but slightly better on T2
positive residual (`-0.000311200623`), while remaining worse on deposit /
payload quality for both.

The follow-up target-specific Phase 6G-U B reruns generated request-local T1/T2
runtime sources with the same mixed-source isolation pattern as 6G-P: cycle `0`
from the near-origin active-dig source and cycles `1` / `2` from the
corridor-conditioned source. Both B reruns preserved the 6G-T surface-depth
prior and reached gate 2. The target-specific comparison artifact
`runs/eval/oracle_terrain_residual_phase6g_u_target_specific_t1_t2_ab_20260703/phase6g_u_target_specific_t1_t2_ab_comparison.json`
shows that the posthoc T2 B advantage does not survive source regeneration:
target-specific B is worse than A on latest positive residual for both T1
(`+0.013392139722`) and T2 (`+0.000310925942`), and remains worse on deposited
fraction, payload, and depth-command tracking. This is still request-local
diagnostic evidence only; it does not define official T1/T2 defaults or
production readiness.

Current official Phase 6 v0 eval semantics are centralized in
`testbed.eval.terrain_residual_contract`. Official T1 is
`t1_large_shallow_rectangular_pit_default`: compact `grid[3,2]`, rows
`[0,2)`, cols `[0,2)`, depth `0.25m`. Official T2 is
`t2_long_shallow_trench_default`: compact `grid[3,2]`, rows `[0,3)`, cols
`[0,1)`, depth `0.25m`. The conservative profile
`not_worse_than_current_A_gate2_baseline` anchors B/C to the same-run A gate-2
baseline: gate reached, at least two completed dumps, zero transition timeouts,
and no worse target residual, overdig, outside-target removal, deposited
fraction, or depth absolute error than A.

The request-local official pass/fail artifact
`runs/eval/oracle_terrain_residual_phase6_official_v0_pass_fail_20260703/official_t1_t2_a_baseline_pass_fail_comparison.json`
records A passing both targets and target-specific B failing both targets on
target positive residual, deposited fraction, and depth absolute error. This is
bounded gate-2 smoke evidence; it is not a checked-in default config change,
planner gate change, prior promotion, or production readiness claim.

The follow-up depth-execution diagnostic root
`runs/eval/oracle_terrain_residual_phase6_depth_execution_diagnostic_20260703`
aligns each completed B cycle's residual cut intent with actual execution and
dump-exit evidence. T1 and T2 each have `depth_overshoot_cycle_count=2` across
two completed cycles. T1 mean depth peak minus intent is `0.223569767456m`; T2
mean depth peak minus intent is `0.245077269058m`. Both runs still reached
gate 2 with zero transition timeouts, so the next training/eval question is ACT
depth response and dump-exit state under shallow residual intents, not return
reachability.

`testbed.eval.terrain_residual_execution_diagnostic` also provides the
request-local official-v0 failure packet builder/writer. That packet only
summarizes existing official pass/fail, depth-execution diagnostic,
cycle-quality, and runtime-source artifacts. It must keep
`planner_behavior_change_status=not_made`,
`production_readiness_status=not_claimed`, and
`calibrated_branch_status=blocked_pending_gold_replay_samples`; it is not a
planner default, gate, or production-readiness promotion. The current generated
packet is
`runs/eval/oracle_terrain_residual_phase6_official_v0_failure_packet_20260707/official_v0_failure_packet.json`.

Gold cycle sample output is now formalized by
`testbed.eval.terrain_gold_cycle_samples`. It writes one
`terrain_gold_cycle_sample_v1` JSONL record per completed cycle and requires at
least one split key (`episode_id` or `rollout_id`). The required payload label
is `payload_mass_kg`. A true closed-loop cycle-quality-derived record includes
start/end removed-depth grids, target-depth grid, target-region/valid masks,
target residual metrics, payload peak, effective deposited mass, deposited
fraction, depth target/peak/error, planned/actual entry and exit fields,
success, transition, and gate fields. Current v2 replay derives volume from the
89D grid geometry and signed removed-depth delta: positive delta contributes to
`removed_volume_m3`, negative delta is recorded separately as
`refill_volume_m3`, and neither is direct sensor gold. Records must retain
`volume_label_status=derived_grid_integral` and
`direct_volume_status=unavailable_no_sensor`.

Replay outputs stay split by purpose: diagnostic JSONL is for qpos/env_state
quality review, while replay cycle JSONL is open-loop/replay-derived evidence.
Replay records use `evidence_kind=replay_derived_open_loop`; planned cut,
planned/actual entry/exit, gate, transition, and planner actual-response fields
remain absent with `missing_not_generated_by_replay` status. Only a real planner
closed-loop run may fill those fields or be used as closed-loop calibration
evidence. `tb-replay` only provides thin request-local flags and validation for
`--gold-cycle-samples-jsonl`,
`--gold-cycle-samples-target-id`, and
`--gold-cycle-samples-low-payload-kg`; it does not own sample semantics. The
selection-manifest path replays a clean episode's full causal prefix without
mask skipping, post-tail, or pose realign. No training or calibrated C-branch
availability may be claimed from replay alone.

Current-Unity replay relabel variance is intentionally a separate silver track,
implemented by `testbed.eval.terrain_replay_relabel_stats` and the thin CLI
`tb-terrain-replay-relabel-stats`. It consumes multiple repeat replay candidate
JSONL files for the same readonly source episode and writes
`terrain_replay_relabel_stats_v2` plus
`terrain_replay_relabel_cycle_sample_v2`. Replayed boundaries are first matched
monotonically to source boundaries within the semantic gate tolerance; grouping
then uses `(source_episode_id, target_id, source_cycle_id)`, rather than assuming
that replay-local cycle indices remain identical after contact. The report keeps
payload/deposit and removed-depth variance, post-contact qpos error, exception,
realign, repeat count, tier, `recommended_weight`, and `label_usage`. Tier A is
usable fine relabel, tier B is uncertainty-weighted weak relabel, and tier C is
coarse/diagnostic-only. Post-contact qpos error is diagnostic and does not by
itself demote an otherwise stable terrain-effect label. Exceptions and pose
realign still force tier C. These records use
`training_source=current_unity_replay_relabel` and `gold_status=not_gold`; they
must not be mixed into strict Phase 5 gold calibration or used to claim
calibrated C-branch readiness.

The five-repeat pilot gate is `terrain_replay_pilot_gate_v2`. It separates
three decisions:

- ACT supervision remains governed by source cleaning and
  `action_loss_mask`; replay does not reject it because of post-contact
  trajectory divergence.
- Episode replay usability requires process integrity, pre-contact qpos error
  `<= 0.02`, stable grid geometry, target-cell valid fraction `>= 0.5`, at
  least four of five semantic repeats, at least 85% source-cycle completion,
  and final T1/T2 terrain completion/shape within the documented source-relative
  tolerances.
- Per-cycle effect relabeling uses only matched A/B records. C records are
  masked for effect calibration, but the A/B fraction is reported rather than
  used as an episode-level hard gate.

Cycle boundaries need not be exactly identical. They are matched in order to
the readonly source episode within `+-1 s`; unmatched cycles simply cannot
produce source-aligned effect labels. The gate reports global/post-contact qpos
error for diagnosis, but only error before the first qualified dig/soil contact
is an acceptance condition. This gate remains replay-derived open-loop
evidence, not real planner closed-loop evidence.

After all episode gates are written, the thin
`tb-terrain-replay-batch-assessment` CLI combines them with the immutable
selection manifest and the full `cycle_eligibility.jsonl`. Its report keeps
three counts separate: source-clean ACT
cycles, episode-semantic Replay cycles, and A/B effect-relabel cycles. Effect
counts are reported at two strengths: `process_stable` keeps source-aligned A/B
cycles when Replay transport/process checks pass, while `strict` additionally
requires the whole episode semantic gate to pass. This prevents a clean local
effect label from being silently discarded while still keeping it out of the
strict whole-task evidence pool.

The fixed seven-episode salvage run is owned by the thin
`tb-salvage-terrain-replay-dataset` CLI. Its strict view,
`combined_strict_clean_vds`, contains the immutable parent 17 plus only newly
strict-passing source identities. It remains `default_enabled: false` until all
24 fixed identities are strict. The separate `layered_salvage_clean_vds` may
substitute at most one deterministic local candidate for an exhausted source;
its config is always `partial_replay_salvage_ablation_only` and
`default_enabled: false`.

Partial supervision is deliberately narrower than episode acceptance. Its
`action_loss_mask` is the intersection of the calibrated source mask,
replay-native QC mask, and local-cycle mask. Corrected attempts use the explicit
`replay_corrected_partial_salvage_v1` evidence profile; any qpos realign and its
guarded cycle/transition are masked, and corrected evidence can never enter the
strict manifest. Their HDF5 step ids are causal source-action indices, while raw
Unity backend ids remain diagnostic-only across realign RPC boundaries. All
resulting HDF5s remain replay-derived, `not_gold`, and
retain missing planner fields. Training/validation splits stay keyed by source
identity, with `episode_33/34` as validation, so parent and replay variants can
never leak across splits or be counted twice.

depth 诊断必须区分三种口径：

- `depth_tracking.dig_local_surface`：正式 command-depth 跟手口径，来自 jsonl 连续
  `dig` 段的 `env_state[31] bucket_depth_below_local_surface_m` 峰值，目标来自
  `dig_cut_tokens[7] * 0.8`。
- `depth_tracking.summary_plane_depth` / `planned_actual_cycles.depth_peak_m`：历史
  summary plane-depth 诊断，来自 `env_state[8] bucket_depth_below_dig_area_plane_m`，
  且窗口可覆盖 `qds -> dump_end`，不能直接当作 command-depth 跟手结论。
- `depth_tracking.expert_p95_overshoot`：相对专家 p95 的超出量，用于判断是否离开专家
  支持范围，不等同于 target depth error。

handoff 诊断优先读取 per-rollout jsonl 中已完成的 `return -> dig`
transition。已经 terminal-stop 后停在 `return` 的不完整段会记录为 ignored，并保留
原始 summary snapshot，避免把终止后的残留 return 帧误判成真实 handoff 失败。

`3cycle_smoke` 用于快速冒烟；`15cycle_probe` / `30cycle_probe` 是 probe，不应直接写成已经完成稳定长程闭环。

## 9. 清理与保留

训练产物通常只长期保留：

- best checkpoint
- resolved config / metadata
- train log summary
- Gate / audit / rollout review 证据
- 必要视频或 contact sheet 索引

可用清理工具：

```bash
tb-cleanup-training-artifacts --ckpt-dir <ckpt_dir> --delete
```

如果正在排查训练过程，不要急着清理中间 checkpoint；必要时使用 `--no-cleanup-after-train`。

## 10. 历史基线说明

旧 V1 / V2.1 文档里关于 `act_agx_v1`、9D `env_state`、`episode_len=1000`、`qpos only`、`dump_complete_final_hold`、`success_rate=100%` 等内容，只能用于解释当时实验，不再代表当前系统状态。

如果需要复现旧结果，应把它标为 legacy experiment，并同时记录当前代码是否仍支持对应 config。不要把旧成功结论迁移到 V2.4.5 spatial-mass / qc6 / depth-profile 训练上。
