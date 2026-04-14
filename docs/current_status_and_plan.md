# 当前状态与下一步计划

本文档是 Repo A 当前阶段的详细说明。

适用范围：
- 了解这个仓库现在到底做到了哪里
- 了解最新 AGX 挖掘任务已经接入了哪些字段和语义
- 了解当前最小 live 闭环已经验证到了哪一步
- 了解接下来应该优先做什么

状态日期：`2026-04-14`

---

## 1. 项目定位

`excavator_testbed` 是 AGXUnity 挖掘机任务的 Python 侧 testbed。

它负责四类事情：
- live 仿真交互：通过 step-ack socket 与 Unity 通信
- 数据生产：teleop 录制、回放 QA、HDF5 落盘
- 模型训练：离线 ACT 训练
- 模型评测：live rollout、成功率统计、视频与结果输出

这个仓库不负责：
- Unity 场景搭建
- AGX 物理对象与 HUD 可视化
- 协议常量的共享定义维护

这三部分分别在 Repo B 和 Repo C。

当前阶段还要额外记住一个目标：
- 我们补训练 setup、metadata、analysis tooling，不是为了把系统做复杂
- 而是为了在 baseline ACT 学不会技能时，能区分问题更可能来自数据、reward / task、实验设置、策略本身，还是接口实现

这决定了后面文档和工具应该优先服务“失效归因”，而不是优先堆更多功能。

---

## 2. 当前已经开发完成的内容

### 2.1 Python <-> Unity 协议侧

已完成：
- `GET_INFO / RESET / STEP` 二进制协议客户端
- `AGXSimBackend`
- step-id 对齐
- FPV 图像解码
- `env_state` 接收与本地 reward tracker 对接

对应代码：
- [testbed/backends/agx/protocol.py](/home/pingfan/PACT/excavator_testbed/testbed/backends/agx/protocol.py)
- [testbed/backends/agx/backend.py](/home/pingfan/PACT/excavator_testbed/testbed/backends/agx/backend.py)

### 2.2 数据管线

已完成：
- `EpisodeRecorder`
- HDF5 schema v1.1
- `tb-record-teleop`
- `tb-replay`
- `tb-dataset-qc`
- `EpisodeDataset`
- demo-level metadata (`episode_id / operator_id / session_id / notes / config snapshot`)

对应代码：
- [testbed/data/recorder.py](/home/pingfan/PACT/excavator_testbed/testbed/data/recorder.py)
- [testbed/data/hdf5_io.py](/home/pingfan/PACT/excavator_testbed/testbed/data/hdf5_io.py)
- [testbed/data/schema.py](/home/pingfan/PACT/excavator_testbed/testbed/data/schema.py)

### 2.3 训练与评测

已完成：
- ACT adapter / trainer
- `tb-train`
- `tb-eval`
- AGX 任务评测套件
- 训练 run 的 frozen split / resolved config / run metadata 自动落盘
- eval 逐 timestep rollout 日志与 summary / manifest 输出
- AGX eval 多口径 success 判定（`legacy_any / final_hold / strict_final_hold / dump_complete_final_hold / strict_dump_complete`）
- `tb-experiment-record` 与 `experiment_registry.csv`

对应代码：
- [testbed/policies/act/adapter.py](/home/pingfan/PACT/excavator_testbed/testbed/policies/act/adapter.py)
- [testbed/policies/act/trainer.py](/home/pingfan/PACT/excavator_testbed/testbed/policies/act/trainer.py)
- [testbed/eval/suite.py](/home/pingfan/PACT/excavator_testbed/testbed/eval/suite.py)
- [testbed/runtime/_train.py](/home/pingfan/PACT/excavator_testbed/testbed/runtime/_train.py)
- [testbed/runtime/run_metadata.py](/home/pingfan/PACT/excavator_testbed/testbed/runtime/run_metadata.py)

### 2.4 当前任务逻辑

已完成接入的任务逻辑：
- DigArea good-start 门控
- target hard collision 处罚
- retained mass success rule
- 对旧 `5D/7D env_state` 的兼容回退

对应代码：
- [testbed/tasks/logic/excavator_reward.py](/home/pingfan/PACT/excavator_testbed/testbed/tasks/logic/excavator_reward.py)

---

## 3. 当前任务的最新语义

当前主任务：`agx_excavation_teleop`

### 3.1 Action

```text
[swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]
```

### 3.2 Observation

`qpos`：

```text
[swing, boom, stick, bucket]
```

`qvel`：

```text
[swing, boom, stick, bucket]
```

`env_state (9,)`：

```text
[
  mass_in_bucket_kg,
  excavated_mass_kg,
  mass_in_target_box_kg,
  deposited_mass_in_target_box_kg,
  min_distance_to_target_m,
  target_hard_collision_count,
  target_contact_max_normal_force_n,
  min_distance_to_dig_area_m,
  bucket_depth_below_dig_area_plane_m
]
```

### 3.3 Reward / Success

关键语义：
- 只有在 DigArea 内满足 good-start，`loading` 才开始给正奖励
- `approaching_target` 依赖载荷和目标接近
- `target_hard_collision_count` 增长时给惩罚
- `success` 以 `deposited_mass_in_target_box_kg` retained mass 为准

默认成功条件：

```text
deposited_mass_in_target_box_kg >= 100.0 kg
for 25 consecutive steps
```

---

## 4. 当前真实验证状态

下面这张表区分“代码已经写完”和“当前环境里已经实跑确认”。

| 项目 | 实现情况 | 当前验证情况 |
|---|---|---|
| 协议客户端 | 已完成 | `agx_smoke.py --strict` 已通过 |
| `AGXSimBackend` | 已完成 | live `GET_INFO / RESET / STEP` 已通过 |
| `tb-record-teleop` | 已完成 | 已按 `teleop_v1` 在 `data/agx_teleop_v1/` 录到 `30` 条正式 success demo |
| `tb-eval` | 已完成 | 已完成 `fulltest(qpos)`、`fulltest(qpos+qvel)` 与 `v1(qpos)` 三轮正式评测 |
| `tb-train` | 已完成 | 已完成 `fulltest(qpos)`、`fulltest(qpos+qvel)` 与 `v1(qpos)` 三轮正式训练 |
| 训练 run metadata | 已完成 | 已实测写出 `train_val_split.yaml / resolved_config.yaml / run_metadata.json` |
| rollout eval logs | 已完成 | 已在 `runs/eval/agx_excavation_smoke_results/` 实测写出 `rollout_XXX.jsonl / summary / manifest` |
| `tb-dataset-qc` | 已完成 | 已在 `data/agx_teleop_fulltest/` 与 `data/agx_teleop_v1/` 实测写出 QC 摘要 |
| demo-level metadata | 已完成 | 已在 `data/agx_teleop_v1/qc/episodes.csv` 实测看到 `operator_id / session_id` 回读 |
| CUDA 训练环境 | 可用 | 已检测到可用 GPU |
| 旧样本兼容读取 | 可用 | 已确认可读取旧 HDF5 |

结论：
- 最小 live pipeline 早已打通，当前业务 baseline 已经迁移到 `data/agx_teleop_v1/`
- 这条分支的重点不再是“能不能学会任务”，而是“如何冻结 v1 基线，并解释严格口径下为什么仍然失败”

本轮 smoke 产物：
- 数据：`data/agx_teleop_v1_smoke/episode_0.hdf5`、`episode_1.hdf5`
- checkpoint：`runs/ckpts/agx_pipeline_smoke_live_temp/`
- 评测结果：`runs/eval/agx_pipeline_smoke_live_temp/results/`

### 4.1 2026-03-26 本轮结论

今天这轮工作的目标，不是证明 “ACT 已经学会任务”，而是验证新增的外围实验管理功能是否已经可用。

当前可以明确确认已经工作的内容：
- 训练 run 侧：
  - frozen `train/val split`
  - `resolved_config.yaml`
  - `run_metadata.json`
- 评测侧：
  - `metrics.json`
  - `results.csv`
  - `rollout_manifest.json`
  - `rollout_XXX.jsonl`
  - `rollout_XXX_summary.json`
- 数据侧：
  - `tb-dataset-qc`
  - demo-level metadata
  - 录制成功即结束
  - eval 终端 step progress 输出

本轮真实产物里，最能说明“功能已经通”的文件是：
- `data/agx_teleop_fulltest/qc/summary.json`
- `data/agx_teleop_fulltest/qc/episodes.csv`
- `runs/eval/agx_excavation_smoke_results/metrics.json`
- `runs/eval/agx_excavation_smoke_results/rollout_manifest.json`

其中：
- `data/agx_teleop_fulltest/qc/summary.json` 说明当前 2 条新录 demo 都可读、带 9D `env_state`、带 timestamps、无 NaN/shape mismatch
- `data/agx_teleop_fulltest/qc/episodes.csv` 说明 `operator_id / session_id` 已经真实写入并能被工具读回
- `runs/eval/agx_excavation_smoke_results/metrics.json` 与 `rollout_manifest.json` 说明 rollout 侧聚合结果与逐条日志都已正常落盘

对 smoke eval 结果的当前判断也已经比较清楚：
- `0 / 2` success 在当前条件下是合理的
- 当前只用了 `2` 条 demo，且 smoke 训练规模很小
- rollout 日志显示失败模式是“全程没有进入 good dig start”，不是“接口坏了”或“日志系统坏了”

另外，本轮还确认了一个重要运行时约束：
- AGX 窗口发抖的主因不是今天新加的 logging / QC / metadata
- 根因是 step-ack 路径里传了过高的图像分辨率
- `1920x1060` 级别图像会明显拖慢 live teleop
- 改回较低固定分辨率后，录制和交互恢复正常

### 4.2 2026-03-27 首轮 fulltest baseline

当前已经完成第一轮正式 baseline：
- 数据集：`data/agx_teleop_fulltest/`
- 训练配置：`testbed/configs/act_agx_fulltest.yaml`
- 评测配置：`testbed/configs/eval_agx_fulltest.yaml`

当前结果判断：
- 训练本身已经稳定收敛，说明新数据集足以让 ACT 学到任务骨架
- 首轮评测视频可见策略能挖、能运，但 dump 质量仍然明显不足
- 当前更准确的判断是：模型并不是“后半段完全没学到”，而是“后半段学到了动作模式，但学偏了”
- 一个直接信号是：policy 会模仿 teleop 中用于减速/纠偏的反向拨杆动作，而不是理解“为什么此刻需要减速”

本轮新增并已落地的能力：
- AGX eval 现在支持五套 success 口径：
  - `legacy_any`
  - `final_hold`
  - `strict_final_hold`
  - `dump_complete_final_hold`
  - `strict_dump_complete`
- 当前推荐主口径是 `dump_complete_final_hold`
- 默认阈值：
  - `mass_thresh = 300.0 kg`
  - `residual_bucket_mass_thresh = 100.0 kg`
  - `hold_steps = 25`
- `strict_dump_complete` 会在 dump-complete final hold 的基础上，再检查 `spill_before_target` / `hard_target_collision` 等失败计数上限
- train + eval + dataset QC 现在可以汇总成实验记录：
  - `runs/experiments/<name>/experiment_record.json`
  - `runs/experiments/<name>/experiment_record.md`
  - `runs/experiments/experiment_registry.csv`

### 4.3 2026-03-31 fulltest `qpos+qvel` 对照

当前已经完成第一轮 `qpos+qvel` 对照实验：
- 数据集：`data/agx_teleop_fulltest/`
- 训练配置：`testbed/configs/act_agx_fulltest_qvel.yaml`
- 评测配置：`testbed/configs/eval_agx_fulltest_qvel.yaml`

这轮结果给出了一个清楚结论：
- `qvel` 确实提升了末段控制质量
- 主口径 `dump_complete_final_hold` 成功率从 `30%` 提升到 `60%`
- `hard_target_collision` 平均次数从 `5.3` 降到 `0.2`
- `unsafe_target_distance` 平均次数从 `66.4` 降到 `22.2`

这说明前一轮对失败模式的判断基本成立：
- 问题并不只在“任务太难”
- 速度状态对 dump phase 的稳定性有直接帮助
- `qvel` 值得保留为正式对照线

### 4.4 2026-04-02 rerecord `v1` baseline

当前已经完成第一轮 `v1` rerecord baseline：
- 数据集：`data/agx_teleop_v1/`
- 训练配置：`testbed/configs/act_agx_v1.yaml`
- 评测配置：`testbed/configs/eval_agx_v1.yaml`

这轮结果把业务基线往前推了一大步：
- 数据集规模提升到 `30` 条 success demo
- 数据集 QC 为 `100%` success、无缺图、无 NaN、无 shape mismatch
- 主口径 `dump_complete_final_hold` 下达到 `10 / 10` success
- 最优 `val loss = 0.1007`

同时也明确留下了下一层问题：
- `strict_dump_complete` 仍然是 `0%`
- 主要失败项仍然是 `spill_before_target`
- 这意味着当前 baseline 已经会完成任务，但还没有达到严格口径下的完成质量

当前已经生成的实验记录：
- `runs/experiments/agx_fulltest_round1/`
- `runs/experiments/agx_v0_round0/`
- `runs/experiments/agx_fulltest_round2_dumpcomplete/`
- `runs/experiments/agx_fulltest_qvel_round1/`
- `runs/experiments/agx_v1_round1/`

这意味着后续每一轮 baseline 都可以按同一格式登记：
- 用的是什么数据
- 最优 epoch / val loss 是多少
- eval 用的是什么 success 口径
- 成功率、平均回报、平均 spill / collision 次数是多少

---

## 5. 当前数据状态

当前工作区里可以把数据分成三层理解：

- `data/agx_teleop/`
  旧兼容样本目录，只用于回归检查、schema 兼容和离线 smoke，不再代表当前业务基线。

- `data/agx_teleop_fulltest/`
  第一轮正式 baseline 数据集，主要用于保留 `qpos` 与 `qpos+qvel` 的可比较对照。

- `data/agx_teleop_v1/`
  当前更接近业务主线的 rerecord 数据集。它对应新的录制结束规则、`dump_complete_final_hold` 录制语义和更完整的 dump 尾段。

因此，这条分支当前最合理的默认理解是：
- `v1` 是业务 baseline
- `fulltest` 是对照与归因数据
- `agx_teleop` 是 legacy 兼容目录

---

## 6. 当前主要待办

当前已经没有“协议级卡死”的阻塞，剩下的是把 `v1` baseline 变成可冻结、可解释、可扩展的默认工作流。

这里要注意一个架构原则：
- 训练 setup、split、run metadata、分析日志都应该补
- 但它们应该补在 `configs/`、`docs/`、`runs/`、`data tooling`、`eval output`
- 不应该反向污染 `Policy` / `Backend` 的抽象边界

也就是说，接下来要补的是“实验管理能力”，不是“推翻 testbed 的插件式结构”

这里的“实验管理能力”最终是为了回答这些问题：
- baseline 学不会，是不是数据不够好
- 是不是 reward / penalty 或 task logic 让问题过难
- 是不是 split、训练轮数、chunk size、eval 条件不合适
- 还是 rollout 链路本身就和训练假设不一致

当前最优先的后续工作已经收敛成三件事：
- 先把 `v1` baseline 作为默认工作口径写清楚
- 补齐 `v1` 数据集的 replay QA，让录制、QC、训练、评测、回放形成完整闭环
- 围绕 `strict_dump_complete` 和 `spill_before_target` 做 failure analysis，再决定下一轮应该改数据、改输入还是改任务语义

当前对 `qvel` 的定位也已经比 3 月底更明确：
- `qvel` 对照已经完成，不再是“下一步待跑”的假设
- 它是一个已验证有效的比较分支
- 下一步需要回答的是：要不要把它迁移到 `v1` 数据集继续验证，而不是继续停留在 `fulltest`

### 待办 1：补 `v1` 数据集的 replay QA

现状：
- `data/agx_teleop_v1/` 已经完成 QC、训练和评测
- 但还缺一次面向正式数据集的 batch replay 证据

影响：
- 当前闭环里唯一还没有明确落盘的是 action→observation 的重放一致性

### 待办 2：把默认基线口径从“fulltest 历史基线”切到“v1 业务基线”

现状：
- 代码和配置已经支持 `v1`
- 部分文档仍然把 `fulltest` 写成默认训练入口

影响：
- 新成员容易把“历史对照线”和“当前默认工作线”混在一起

### 待办 3：做严格口径下的失败归因

现状：
- `dump_complete_final_hold` 已经通过
- `strict_dump_complete` 仍然是 `0%`

影响：
- 目前最需要解释的是完成质量，而不是可学习性

---

## 7. 推荐下一步计划

### 阶段 0：整理默认入口

目标：
- 让 README、训练说明和默认命令都清楚指向 `teleop_v1 / act_agx_v1 / eval_agx_v1`

最小验收：
- 新成员按 README 运行时，拿到的是 `v1` 业务基线而不是旧目录

### 阶段 1：补 replay QA

目标：
- 对 `data/agx_teleop_v1/` 补一次正式批量回放

最小验收：
- `tb-replay` 批量运行稳定
- 输出一组可接受的 qpos diff 汇总

### 阶段 2：收紧 failure analysis

目标：
- 从“会不会做任务”转向“为什么过不了 strict 口径”

最小验收：
- 明确 `spill_before_target` 的主要触发阶段
- 形成下一轮实验假设

### 阶段 3：决定 qvel 的去留

目标：
- 判断 `qvel` 是继续保留为 fulltest 对照，还是迁移到 `v1` 上继续验证

最小验收：
- 给出分支角色和实验角色的清晰边界

---

## 8. 文档权威性说明

当前建议这样理解文档层级：

第一层：
- [README.md](/home/pingfan/PACT/excavator_testbed/README.md)

用途：
- 仓库入口
- quick start
- 当前状态摘要

第二层：
- [docs/current_status_and_plan.md](/home/pingfan/PACT/excavator_testbed/docs/current_status_and_plan.md)
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)

用途：
- 当前实现细节
- 当前待办
- 推荐下一步计划
- 训练配置字段、实验记录方式、性能分析时需要保留的元数据

研究/历史文档：
- `docs/技术可行性评估与顶层架构设计.md`
- `docs/工程机械_土堆颗粒模拟调研.md`

这些可以保留，但不再作为“当前实现说明”的权威来源。
