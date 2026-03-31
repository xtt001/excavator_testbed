# 当前状态与下一步计划

本文档是 Repo A 当前阶段的详细说明。

适用范围：
- 了解这个仓库现在到底做到了哪里
- 了解最新 AGX 挖掘任务已经接入了哪些字段和语义
- 了解当前最小 live 闭环已经验证到了哪一步
- 了解接下来应该优先做什么

状态日期：`2026-03-27`

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
| `tb-record-teleop` | 已完成 | 已用 joystick 在 `data/agx_teleop_fulltest/` 录到 2 个新 9D success episode |
| `tb-eval` | 已完成 | 已完成 2 个 live rollout smoke，并写出 `metrics.json / results.csv / rollout logs` |
| `tb-train` | 已完成 | 已在新录制的 9D smoke 数据上完成 1 epoch 训练 |
| 训练 run metadata | 已完成 | 已实测写出 `train_val_split.yaml / resolved_config.yaml / run_metadata.json` |
| rollout eval logs | 已完成 | 已在 `runs/eval/agx_excavation_smoke_results/` 实测写出 `rollout_XXX.jsonl / summary / manifest` |
| `tb-dataset-qc` | 已完成 | 已在 `data/agx_teleop_fulltest/qc/` 实测写出 `summary.json / episodes.csv / plots` |
| demo-level metadata | 已完成 | 已在 `data/agx_teleop_fulltest/qc/episodes.csv` 实测看到 `operator_id / session_id` 回读 |
| CUDA 训练环境 | 可用 | 已检测到可用 GPU |
| 旧样本兼容读取 | 可用 | 已确认可读取旧 HDF5 |

结论：
- 最小 live pipeline 已经打通
- 当前问题不再是“协议不通”，而是“正式数据与正式配置已经切到新基线，接下来要提高成功定义与结果归因质量”

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

当前已经生成的实验记录：
- `runs/experiments/agx_fulltest_round1/`
- `runs/experiments/agx_v0_round0/`

这意味着后续每一轮 baseline 都可以按同一格式登记：
- 用的是什么数据
- 最优 epoch / val loss 是多少
- eval 用的是什么 success 口径
- 成功率、平均回报、平均 spill / collision 次数是多少

---

## 5. 当前数据状态

当前工作区内的 `data/agx_teleop/` 仍然是旧样本目录。

它的问题不是“不能读”，而是“不是当前新任务的正式数据基线”：
- 其中已有 episode 仍然是旧 `env_state` 版本
- 不能代表最新 DigArea / collision / 9D 任务语义

因此当前正确做法不是继续默认使用这批数据，而是：
- 重新录制一个新目录
- 例如：`data/agx_teleop_v1/`
- 然后把训练配置显式指向这个新目录

---

## 6. 当前主要待办

当前已经没有“协议级卡死”的阻塞，剩下的是把第一轮正式 baseline 变成可对比、可解释、可迭代的实验流程。

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

当前最优先的后续工作不是盲目继续堆数据，而是：
- 用新的 `dump_complete_final_hold / strict_dump_complete` 口径重跑 baseline eval
- 让 `experiment_registry.csv` 里真正形成多轮可比较记录
- 再根据对比结果决定下一步更该补数据、调 reward/task，还是动 policy

当前 2026-03-27 这轮分析之后，下一步优先级已经进一步收敛为：
- 先做 `ACT(qpos)` vs `ACT(qpos+qvel)` 对照实验
- 暂不把 reward 优化当成当前 BC 提升的主路径
- 也暂不直接上更大的上层决策模型

原因：
- 当前 ACT 实现真实输入是 `images + qpos`
- 当前 `qvel / env_state / reward` 都不进入 ACT loss
- 现有失败模式高度怀疑与末端速度控制有关
- 因此先加 `qvel`，比先改 reward 更有可能提升 dump phase

建议的工程做法：
- 在独立实验分支中完成 `qvel` 输入改造
- 不直接覆盖当前 `qpos` baseline
- 让新的 checkpoint、config、experiment record 单独命名，便于横向比较

### 待办 1：默认数据目录仍是旧样本

现状：
- `data/agx_teleop` 仍是旧 episode
- 默认训练配置仍指向这个目录

影响：
- 即使 `tb-train` 能跑，也只是离线 smoke
- 不能把训练结果解释为“基于新任务数据的模型”

### 待办 2：新数据上的 replay QA 还没补

现状：
- 本轮已完成 `record -> qc -> train -> eval` smoke
- 但还没对新 `data/agx_teleop_v1_smoke` 再跑一遍 `tb-replay`

影响：
- 还缺一次“新任务数据回放一致性”的明确确认

### 待办 3：smoke 配置还是临时文件

现状：
- 本轮为了快速验证，用了临时 smoke 配置来缩短 episode 和对齐 `chunk_size`

影响：
- 这些配置还没整理成仓库内正式追踪的 config 文件

### 待办 4：还缺基于正式数据的失败归因闭环

现状：
- 训练 run metadata、rollout logs、dataset QC、demo metadata 已经到位
- 但这些能力目前主要在 smoke 数据和单测层面完成了验证

影响：
- 现在已经具备 baseline 失败归因所需的外围证据链
- 下一步重点不再是“补工具入口”，而是“用正式数据和正式 rollout 真的跑起来”
- 也就是先把 “工具是否可用” 的问题收口，再进入 “baseline 为什么学不会” 的问题

---

## 7. 推荐下一步计划

### 阶段 0：补 replay QA

目标：
- 对新 9D 数据补一次回放一致性检查

最小验收：
- `tb-replay` 在新数据上不报错
- 输出一条可接受的 QA diff

### 阶段 1：录制正式数据

目标：
- 产出当前 9D 任务语义的正式 teleop 数据集

最小验收：
- 使用独立目录，例如 `data/agx_teleop_v1/`
- episode 数量达到正式训练所需规模

### 阶段 2：切换正式训练基线

目标：
- 把正式训练配置切到新数据目录

最小验收：
- `act_agx_v0.yaml` 指向新目录
- 训练结果不再依赖旧 `data/agx_teleop`

### 阶段 3：扩大 live eval

目标：
- 从 `1` 个 smoke rollout 扩大到正式评测规模

最小验收：
- `tb-eval` 多 rollout 稳定完成
- 结果目录持续生成 `metrics.json / results.csv`

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
