# Excavator Testbed (Repo A — Python)

用于 AGXUnity 挖掘机任务的 Python 侧数据、训练、评测仓库。

Repo A 负责：
- AGX step-ack socket 客户端与 `AGXSimBackend`
- teleop 录制到 HDF5
- 录制回放与 QA
- 离线 ACT 训练
- live policy rollout 评测
- 基于 Unity 导出 `env_state` 的任务奖励与成功判定

三仓结构：
- Repo A — 本仓库：Python testbed
- Repo B — `AGXUnity_Excavator`：Unity / C# 场景与桥接
- Repo C — `sim-protocol`：共享协议、schema、常量、评测定义

---

## 当前状态

状态日期：`2026-06-01`

| 组件 | 实现状态 | 当前验证状态 |
|---|---|---|
| AGX 二进制 step-ack 协议客户端 | 已实现 | 已在本地 Unity 上通过 live strict smoke |
| `AGXSimBackend` | 已实现 | `GET_INFO / RESET / STEP / reward tracker` 最小 live 链路已打通 |
| HDF5 schema v1.1 | 已实现 | 支持 `timestamps`、`action_source`、`fpv`、`env_state` |
| 当前 AGX 任务协议 | 已实现 | 当前目标协议是 `env_state (9,)`，含 DigArea 与 hard collision 字段 |
| `tb-record-teleop` | 已实现 | 已按 `teleop_v1` 重录 `30` 条正式 success demo，落盘到 `data/agx_teleop_v1/` |
| `tb-replay` | 已实现 | 支持单文件或整个目录批量回放；`fulltest` 已验证，`v1` 仍建议补一轮正式 batch QA |
| `tb-dataset-videos` | 已实现 | 从 HDF5 离线导出 MP4 视频（无需连 AGX） |
| `tb-build-real-one-dig-v1` | 已实现 | 将真机 `episode_13..21` 裁剪成 real one-dig 训练窗口，并把 JPEG FPV 解码成 raw RGB |
| `tb-offline-real-one-dig-eval` | 已实现 | 在真实 FPV/qpos/qvel 上只预测不下发，输出 expert vs policy 视频、曲线和指标 |
| `tb-train` / ACT trainer | 已实现 | 已完成 `fulltest(qpos)`、`fulltest(qpos+qvel)` 与 `v1(qpos)` 三条训练线 |
| `tb-eval` | 已实现 | 已完成正式 live eval；当前最好结果是 `v1(qpos)` 在主口径下 `10/10` 成功 |
| rollout timestep logs | 已实现 | `tb-eval` 现可写 `rollout_XXX.jsonl / summary / manifest` |
| `tb-dataset-qc` | 已实现 | 可写 `summary.json / episodes.csv / QC plots` |
| demo-level metadata | 已实现 | `tb-record-teleop` 支持 `operator_id / session_id / notes / config snapshot` |
| MuJoCo backend | 保留 | 仅作 legacy / 对照，不是当前主路径 |

当前重点：
- 冻结 `data/agx_teleop_v1`、`act_agx_v1.yaml`、`eval_agx_v1.yaml` 作为当前业务 baseline
- 补一次 `v1` 数据集的正式 `tb-replay` QA，把数据闭环补完整
- 围绕 `strict_dump_complete` 和 `spill_before_target` 做 failure analysis，决定下一轮该改数据还是改输入
- real one-dig 分支只使用 v1 one-dig 语义：`tb-build-real-one-dig-v1` 生成 `data/real_one_dig_v1_windows/`；下一步主线是 real-domain 训练、offline imitation eval 和 shadow 验证，不再把 Unity real2sim replay 作为第一轮训练或评测依据

---

## 概念框架

```text
                           Repo B: Unity / AGX 场景
                    (物理、场景对象、HUD、step-ack server)
                                      │
                                      │ GET_INFO / RESET / STEP
                                      ▼
                    testbed/backends/agx/protocol.py + AGXSimBackend
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
   testbed/actions/            testbed/tasks/logic/          testbed/data/
 (joystick / keyboard)     (reward, success, phase)   (record, replay, HDF5, dataset, QC)
          │                           │                           │
          └──────────────┬────────────┴────────────┬──────────────┘
                         │                         │
                         ▼                         ▼
                 testbed/policies/            testbed/eval/
              (ACT, dummy, future plugins)  (rollout, metrics, video)
                         │                         │
                         └──────────────┬──────────┘
                                        ▼
                                CLI / Runner 层
      tb-record-teleop / tb-replay / tb-dataset-videos / tb-dataset-qc / tb-train / tb-eval
      tb-build-real-one-dig-v1 / tb-offline-real-one-dig-eval
                                        │
                                        ▼
                     testbed/configs/ + docs/training_setup.md
                  (训练 setup、实验记录规则、运行参数，不改核心接口)
```

这个框架里真正的插件边界是：
- `backends/`：环境接入层
- `actions/`：teleop 输入层
- `policies/`：策略层
- `eval/`：评测层

而训练 setup、split、run metadata、实验记录这些内容，应该放在：
- `testbed/configs/`
- [testbed/configs/README.md](/home/pingfan/PACT/excavator_testbed/testbed/configs/README.md)
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)
- `runs/...` 下的产物与元数据

也就是说，它们属于“实验管理层”，不是“核心接口层”。

如果你想快速弄清楚每个 YAML 的角色、入口命令和当前推荐用法，直接看 [testbed/configs/README.md](/home/pingfan/PACT/excavator_testbed/testbed/configs/README.md)。

---

## Real One-Dig Offline Imitation

真机 one-dig v1 不使用 V2 planner、primitive、phase label、boundary label 或 token。源数据固定为移动硬盘 `/media/pingfan/EXTERNAL_USB/real_teleop_v1` 中的成功 `episode_13..21`。

```bash
tb-build-real-one-dig-v1 \
  --source-dir /media/pingfan/EXTERNAL_USB/real_teleop_v1 \
  --output-dir data/real_one_dig_v1_windows

tb-train --config testbed/configs/act_real_one_dig_v1_smoke.yaml

tb-train --config testbed/configs/act_real_one_dig_v1_train.yaml

tb-train --config testbed/configs/act_real_one_dig_v1_ep8_overfit.yaml
tb-train --config testbed/configs/act_real_one_dig_v1_ep8_zero_latent_overfit.yaml
tb-train --config testbed/configs/act_real_one_dig_v1_ep8_zero_latent_dense_overfit.yaml
tb-train --config testbed/configs/act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml
tb-train --config testbed/configs/act_real_one_dig_v1_all9_overfit.yaml

tb-offline-real-one-dig-eval \
  --config testbed/configs/act_real_one_dig_v1_train.yaml \
  --output-dir runs/eval/real_one_dig_v1_offline_train
```

converter 默认把源 `episode_13..21` 重映射成 `episode_0..8`，裁剪掉开头静止段和 go-home 自动回中段，保留 `qpos(rad)`、`qvel(rad/s)`、`action`、`raw_action`、`commanded_action` 与 timestamps，并把 JPEG FPV 写成 `/observations/images/fpv` raw RGB。

本轮 real2sim replay 尝试留下的结论：

- 坐标 gap：真机 swing 以左侧限位为 `0`、中心约 `2.2 rad`；boom/stick/bucket 是相对水平面的绝对角；Unity 侧是 normalized actuator pose。已用首帧 real qpos realign、swing invert、relative joint mapping 和 offset 做过初始姿态对齐。
- 执行 gap：同一 normalized `action` 在真机控制器、负载、摩擦、液压/电机响应和 AGX target-speed controller 下产生的关节速度不同。axis scale、deadband、bucket invert 这类 replay adapter 只适合诊断，不应改写真实标签。
- 时间 gap：真机窗口、训练样本和评测样本以记录的 step index / `timestamps/step_ns` 为准；Unity live 展示受 step-ack 通信、采图和写盘影响，容易表现成慢放，不能直接作为 imitation 质量判断。
- 当前决策：第一轮不再追求高保真 Unity replay，也不把 replay 后的 sim 数据作为主要训练依据。学习效果判断转向 real-domain offline imitation eval。

下一步主线是 offline imitation eval：在 `data/real_one_dig_v1_windows/` 上训练或加载 real one-dig policy，然后在 9 条真实记录上只预测不下发，逐帧对齐可视化：

- 当前真实 FPV frame。
- 专家 `action`，以及诊断用 `commanded_action`、`raw_action`。
- 模型输出 `policy_action`。
- 四轴 action trace、误差曲线和按时间对齐的 overlay video。

这个评测直接回答“同一个真实 FPV 下，专家想怎么动，模型想怎么动”，更适合判断 imitation learning 是否学会 one-dig 行为；通过 offline shadow 后，再进入 live shadow 和低幅度 guarded 真机测试。

当前真机测试候选 checkpoint、temporal aggregation 评测口径和上线安全流程见 [docs/real_one_dig_real_machine_test_plan.md](/home/pingfan/PACT/excavator_testbed/docs/real_one_dig_real_machine_test_plan.md)。

`*_overfit.yaml` 最初用于诊断：如果单条或 9 条同 train/val 都贴不住专家动作，先查训练接口、action normalization、chunk size、loss 和采样。当前阶段不要求泛化，只要求 9 条成功 demo 的动作模仿，因此 `act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml` 产出的 checkpoint 可作为第一版 live shadow / 低幅度 guarded 真机测试候选；单条 `episode_8` overfit 配置仍只作诊断。ACT 默认 train/val 使用 teacher-forced CVAE latent，而 eval/inference 使用 zero latent；`*_zero_latent*_overfit.yaml` 用来让训练目标和真实推理路径一致。`train.sample_repeats` 会让每条 episode 每个 epoch 采多个随机 chunk，用于更可靠的 overfit 诊断。

注意：移动硬盘中的 raw real-world 数据不修改。`raw_action` 和 `commanded_action` 只做诊断与安全对照，训练主标签仍然是转换窗口中的 `action`。

---

## 当前任务定义

当前主任务：`agx_excavation_teleop`

任务范围：
- 固定工位 / stationary digging
- 4 维机械臂动作，不含行走底盘
- DigArea good-start 门控
- target hard collision 监控

动作向量：

```text
[swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]
```

观测：
- `qpos (4,)`：`[swing, boom, stick, bucket]`，归一化位置
- `qvel (4,)`：`[swing, boom, stick, bucket]`，速度
- `images["fpv"]`：`(H, W, 3)`，`uint8`
- `env_state (9,)`：

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

奖励 / 成功语义：
- `loading`：只有满足 DigArea good-start 后才开始给正向装载奖励
- `approaching_target`：载荷存在时，朝目标接近给奖励
- `depositing`：目标 retained mass 开始增长时给奖励
- `hard_target_collision`：`target_hard_collision_count` 在本步增加时给固定惩罚
- `success`：`deposited_mass_in_target_box_kg >= 100 kg` 且连续保持 `25` 步

兼容性：
- Repo A 仍可读取旧 `5D/7D env_state` 数据
- 但旧数据只用于兼容或离线 smoke，不应再作为当前任务的标准训练集

---

## Quick Start

### 1. 安装

```bash
conda activate aloha
pip install -e ".[dev]"
```

### 2. 先验证 live 协议

```bash
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict
```

这一步必须先过。

如果这里在 `GET_INFO` 超时：
- 不要继续跑 `tb-record-teleop`
- 不要继续跑 `tb-eval`
- 先回到 Repo B / Unity 修 step-ack 响应

### 3. 录制新的 9D 数据

建议不要直接覆盖旧样本目录，先写到新目录：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 20 \
  --operator-id alice \
  --session-id baseline-v1 \
  --notes "first rerecord batch with 300kg retained-mass stop" \
  --output-dir data/agx_teleop_v1
```

当前 `tb-record-teleop` 默认会在两种情况下结束并保存当前 episode：
- 达到任务 success
- 达到 `task.max_steps`

当前推荐录制配置是 [testbed/configs/teleop_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v1.yaml)：
- 输出目录默认写到 `data/agx_teleop_v1`
- 录制期 success 切到 `dump_complete_final_hold`
- `deposited_mass_in_target_box_kg >= 300kg`
- `mass_in_bucket_kg <= 100kg`
- 连续保持 `25` 步
- 成功后再继续录制 `50` 步尾段，保留 dump 后半段和收尾动作

键盘 fallback：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input keyboard \
  --num-episodes 1 \
  --output-dir data/agx_teleop_v1
```

### 4. 回放 QA

```bash
# 单个 episode（需要连 AGX）
tb-replay \
  --episode data/agx_teleop_v1/episode_0.hdf5 \
  --config testbed/configs/teleop_v1.yaml \
  --save-video

# 批量回放整个目录（需要连 AGX）
tb-replay \
  --episode data/agx_teleop_v1/ \
  --config testbed/configs/teleop_v1.yaml \
  --save-video
```

### 4.1 数据质检

```bash
tb-dataset-qc \
  --dataset-dir data/agx_teleop_v1
```

如果目录里混有损坏或未完整写完的 `episode_*.hdf5`，`tb-dataset-qc` 现在会跳过这些文件，并把它们记录到 `summary.json` 里的 `unreadable_episode_ids` / `unreadable_episode_errors`。

### 4.2 离线导出视频

从 HDF5 中直接导出 FPV 视频，不需要连接 AGX：

```bash
# 导出整个目录（默认输出到 <dataset_dir>/videos/）
tb-dataset-videos data/agx_teleop_v1/

# 指定输出目录
tb-dataset-videos data/agx_teleop_v1/ -o runs/videos/v1

# 只导出特定 episode
tb-dataset-videos data/agx_teleop_v1/ --indices 0 3 5 10

# 单个 episode
tb-dataset-videos data/agx_teleop_v1/episode_0.hdf5
```

### 5. 训练

当前业务 baseline 直接使用 [testbed/configs/act_agx_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_v1.yaml)。

```bash
tb-train --config testbed/configs/act_agx_v1.yaml
```

这份配置默认对应：
- 数据集 `data/agx_teleop_v1`
- `30` 条 rerecord success demo
- `qpos` 输入
- `dump_complete_final_hold` 主口径

当前训练器还内置了几项提速设置：
- `num_workers: 0`，避免 HDF5 多 worker 抖动
- `val_every: 5`，不是每个 epoch 都跑完整验证
- `save_latest_every: 10`，不是每个 epoch 都刷一次 latest checkpoint
- `amp: true` + `amp_dtype: auto`，在 CUDA 上自动选 `bf16/fp16`

当前训练器也已经支持“成功即提前结束”的变长 demo：
- 归一化统计会按所有 episode 的时间维拼接计算
- DataLoader 会按配置里的 `task.episode_len` 统一 pad action / `is_pad`
- 所以像 `data/agx_teleop_fulltest` 和 `data/agx_teleop_v1` 这种 success-truncated 数据，都可以直接训练

如果你要复现第一轮 `fulltest(qpos)` 基线，可以直接用：

```bash
tb-train --config testbed/configs/act_agx_fulltest.yaml
```

如果你要复现 `fulltest` 上的 `qpos+qvel` 对照实验，可以直接用：

```bash
tb-train --config testbed/configs/act_agx_fulltest_qvel.yaml
```

训练启动后，当前会自动在 `ckpt_dir` 下写出：
- `train_val_split.yaml`
- `resolved_config.yaml`
- `run_metadata.json`

其中：
- `train_val_split.yaml` 用来冻结 train/val episode split
- `resolved_config.yaml` 记录本次 run 的实际训练配置
- `run_metadata.json` 记录命令、环境、Repo A git 信息和训练结果摘要

快速 smoke：

```bash
tb-train \
  --config testbed/configs/act_agx_smoke.yaml \
  --epochs 5
```

### 6. 评测

```bash
tb-eval --config testbed/configs/eval_agx_smoke.yaml
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

如果你当前训练的是
`testbed/configs/act_agx_fulltest.yaml`
这条 baseline，对应直接评测：

```bash
tb-eval --config testbed/configs/eval_agx_fulltest.yaml
```

如果你训练的是新的 `teleop_v1` / `act_agx_v1` 这批数据，对应直接评测：

```bash
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

如果你训练的是 `qpos+qvel` 对照版本，对应评测配置是：

```bash
tb-eval --config testbed/configs/eval_agx_fulltest_qvel.yaml
```

`tb-eval` 是 live rollout 命令，需要 Unity 在目标 host/port 上正确响应 step-ack。
当前评测目录除 `metrics.json / results.csv / videos/` 外，还会额外写出：
- `rollout_manifest.json`
- `rollouts/rollout_XXX.jsonl`
- `rollouts/rollout_XXX_summary.json`
- `eval_run_metadata.json`
- `eval_resolved_config.yaml`

当前 AGX eval 现在会同时记录五套 success 口径：
- `legacy_any`：历史口径，只要 rollout 中任意时刻曾满足 mission success
- `final_hold`：episode 结束时仍满足 retained-mass hold 条件
- `strict_final_hold`：在 `final_hold` 基础上，还要求指定失败项计数不超过阈值
- `dump_complete_final_hold`：推荐主口径，episode 结束时既要保住足够多的 retained mass，也要把 bucket 余土降到阈值以下
- `strict_dump_complete`：在 `dump_complete_final_hold` 基础上，再要求指定失败项计数不超过阈值

当前推荐配置默认把主 success mode 设为 `dump_complete_final_hold`，并使用：
- `mass_thresh = 300.0 kg`
- `residual_bucket_mass_thresh = 100.0 kg`
- `hold_steps = 25`
- strict 默认阻断项：
  - `hard_target_collision = 0`
  - `spill_before_target = 0`

也就是说：
- `metrics.json` / `results.csv` 里的主 `success_rate` 现在对应 `dump_complete_final_hold`
- `rollout_manifest.json` 里会额外保留
  `legacy_success / final_hold_success / strict_final_hold_success / dump_complete_final_hold_success / strict_dump_complete_success`

当前 `tb-eval` 还会在终端里输出 rollout 进度，默认类似：

```text
  rollout 000  step 50 / 1000
```

这个频率可通过 `eval.step_log_interval` 调整，默认是 `50`。

### 6.1 实验记录

训练 run 现在会自动写：
- `train_val_split.yaml`
- `resolved_config.yaml`
- `run_metadata.json`

评测 run 现在会自动写：
- `eval_resolved_config.yaml`
- `eval_run_metadata.json`
- `metrics.json`
- `results.csv`
- `rollout_manifest.json`

如果你要把某一轮 train + eval + dataset QC 汇总成可比较的实验记录，再运行：

```bash
tb-experiment-record \
  --train-ckpt-dir runs/ckpts/agx_excavation_act_v1 \
  --eval-results-dir runs/eval/agx_excavation_act_v1/results \
  --notes "rerecord v1 baseline on 30 success demos"
```

它会写出：
- `runs/experiments/<experiment_name>/experiment_record.json`
- `runs/experiments/<experiment_name>/experiment_record.md`
- `runs/experiments/experiment_registry.csv`

---

## 数据目录说明

当前工作区里的 `data/agx_teleop/` 不是“当前新任务的标准数据集”。

它目前的用途更接近：
- 旧样本兼容性检查
- 离线 smoke 训练
- 数据 schema 向后兼容验证

已知现状：
- 这个目录里的现有示例 episode 仍然是旧 `env_state` 版本
- 不是当前 DigArea / collision / 9D 任务的正式训练数据

因此，当前推荐流程是：
- 新数据录到 `data/agx_teleop_v1/` 或其他新目录
- 在训练配置中显式切换 `dataset_dir`
- 等新数据稳定后，再决定是否替换默认目录

---

## 当前剩余补齐清单

下面这些是当前最值得补的事项，按优先级排序：

1. 给 `data/agx_teleop_v1/` 补一轮正式 `tb-replay` QA  
   现在训练、评测和 QC 都已经跑过，唯一还缺的是针对正式 `v1` 数据集的回放一致性证据。

2. 把 `strict_dump_complete` 下的失败模式整理出来  
   `v1(qpos)` 已经在主口径下 `10/10` 成功，当前真正卡住的是严格口径下的 `spill_before_target`。

3. 明确 `qvel` 在后续主线里的位置  
   当前 `qvel` 对照已经在 `fulltest` 上给出正向结果，下一步需要判断它是继续作为对照线保留，还是迁移到 `v1` 数据集上继续验证。

这些补齐项不会破坏 testbed 的 clean plug-support 结构，只要遵守一个原则：
- 不把实验记录逻辑硬塞进 `Policy` / `Backend` 的抽象接口
- 把它们放在 config、runtime metadata、data tooling、eval output 这些外围层

换句话说：
- “环境怎么接” 仍然归 `backends/`
- “策略怎么插” 仍然归 `policies/`
- “实验怎么记录与分析” 归 `configs/ + docs/ + runs/`

---

## 推荐验证顺序

```bash
conda activate aloha

# 1) 协议检查
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict

# 2) 录制或复查 v1 数据
tb-record-teleop --config testbed/configs/teleop_v1.yaml --input joystick --num-episodes 1 --output-dir data/agx_teleop_v1

# 3) 离线导出视频 + 数据质检
tb-dataset-videos data/agx_teleop_v1/
tb-dataset-qc --dataset-dir data/agx_teleop_v1

# 3b) 可选：通过 AGX 批量回放 QA（需要连 AGX）
tb-replay --episode data/agx_teleop_v1/ --config testbed/configs/teleop_v1.yaml --save-video

# 4) 训练当前业务 baseline
tb-train --config testbed/configs/act_agx_v1.yaml

# 5) live eval
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

---

## 与 Unity 联调

编辑 [testbed/configs/teleop_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v1.yaml)：

```yaml
agx:
  host: "192.168.x.x"
  port: 5057
  reset_terrain: true
  reset_pose: true
```

当前 reset 预期：
- `reset_pose: true`
- `reset_terrain: true`

Unity 侧需要保证：
- `GET_INFO` 能及时返回
- `RESET` 后第一帧可被 Python 同步取回
- terrain reset 与 episode reset 只走一条清晰路径

---

## 文档入口

当前权威文档：
- 本 README：仓库说明、当前状态、quick start
- [docs/current_status_and_plan.md](/home/pingfan/PACT/excavator_testbed/docs/current_status_and_plan.md)：详细的“已开发内容 / 当前 smoke 验证结果 / 下一步计划 / 为什么要补失效归因能力”
- [docs/training_setup.md](/home/pingfan/PACT/excavator_testbed/docs/training_setup.md)：训练配置字段、实验记录项、失效归因时应保留的证据链

保留文档：
- `docs/技术可行性评估与顶层架构设计.md`：技术路线与顶层架构评估
- `docs/工程机械_土堆颗粒模拟调研.md`：土体 / 颗粒模拟调研

---

## Repo Layout

```text
testbed/
  backends/
    agx/                  AGX 协议与 backend
    mujoco/               legacy MuJoCo backend
  actions/                joystick / keyboard action source
  data/                   HDF5 schema, IO, recorder, dataset
  eval/                   eval suite, metrics, video, task defs
  policies/               ACT, dummy, diffusion stub
  runtime/                runner, train/eval helpers
  configs/                teleop/train/eval configs
  cli/                    tb-record-teleop, tb-replay, tb-dataset-videos, tb-dataset-qc, tb-train, tb-eval, tb-experiment-record

docs/
  current_status_and_plan.md
  技术可行性评估与顶层架构设计.md
  工程机械_土堆颗粒模拟调研.md
```

常用产物路径：
- `data/agx_teleop_v1/episode_N.hdf5`：当前推荐的新任务录制目录
- `runs/ckpts/agx_excavation_act_smoke/`：smoke checkpoint
- `runs/ckpts/agx_excavation_act_v0/`：主训练 checkpoint
- `runs/eval/...`：评测结果与视频

---

## HDF5 Schema v1.1

```text
episode_N.hdf5
├── metadata/
├── observations/
│   ├── qpos            (T, 4) float32
│   ├── qvel            (T, 4) float32
│   ├── env_state       (T, M) float32
│   └── images/fpv      (T, H, W, 3) uint8
├── action              (T, 4) float32
├── rewards             (T,) float32
├── timestamps/
│   ├── step_id         (T,) int64
│   └── step_ns         (T,) int64
└── action_source/
    ├── type            (T,) str
    └── id              (T,) str
```

schema 规则：
- add-only
- 不重命名旧字段
- 新必需字段才 bump version

当前 HDF5 里“实际记录”的内容可以分成 4 类：

1. 训练主数据
- `observations/qpos`
- `observations/images/<camera>`
- `action`

2. 任务分析与回放辅助
- `observations/qvel`
- `observations/env_state`
- `rewards`
- `timestamps/step_id`
- `timestamps/step_ns`
- `action_source/type`
- `action_source/id`

3. 录制上下文 metadata
- `task_name`
- `param_version`
- `timestamp`
- `seed`
- `protocol_version`
- `control_hz`
- `dt`
- `action_semantics`
- `camera_names`
- `image_format`
- `camera_width`
- `camera_height`
- `camera_fps`
- `camera_row_order`
- `action_order`
- `qpos_order`
- `qvel_order`
- `env_state_order`

4. demo-level metadata
- `episode_id`
- `operator_id`
- `session_id`
- `notes`
- `teleop_input`
- `record_config_path`
- `record_config_yaml`
- joystick / keyboard 录制参数快照

一个关键点：
- 当前 ACT 模仿学习训练 **不会** 直接把 `rewards`、`env_state`、`task_success` 当作监督信号
- 当前 ACT data loader 实际吃的是：
  - `qpos`
  - `images`
  - `action`
- `qvel / env_state / rewards / timestamps / metadata` 目前主要用于：
  - replay
  - dataset QC
  - rollout analysis
  - failure diagnosis
  - experiment record

这里还要明确一点：
- 当前默认 baseline 里 ACT 的低维输入仍然只是 `qpos`
- 这不代表 ACT “天然只能吃 position”
- 在当前代码结构下，可以把低维 `robot_state` 扩成：
  - `concat(qpos, qvel)`
  - 或 `concat(qpos, qvel, selected_env_state)`
- 但这属于新的输入定义实验，需要同时改：
  - dataset
  - normalization stats
  - adapter 推理入口
  - model `state_dim`
- 当前仓库已经落了一条独立的 `qpos+qvel` 实验路径：
  - [testbed/configs/act_agx_fulltest_qvel.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_fulltest_qvel.yaml)
  - [testbed/configs/eval_agx_fulltest_qvel.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/eval_agx_fulltest_qvel.yaml)
- 因为它会改变 checkpoint 兼容性和 baseline 可比性，当前仍建议把 `qvel` 版本当成独立对照实验，而不要覆盖 `qpos` baseline

因此，**单独修改 eval success 口径，不会让旧 HDF5 数据立刻失效**。

但要注意一个例外：
- `tb-record-teleop` 如果开启 `stop_on_success: true`
- episode 会在当时录制所使用的 backend `task_success` 首次满足后提前结束

这意味着：
- 如果只是把 success 逻辑从旧 eval 口径改成更严格的
  `dump_complete_final_hold / strict_dump_complete`
  - 旧 demo 仍然可以继续训练
  - 第一反应应该先重训、重评测
- 如果你后来认为“旧 demo 经常在较宽松 success 下过早截断，没有保留足够稳定、足够干净的 dump 后半段”
  - 那时才值得重新录制一批更符合新目标语义的数据

更细的字段定义以 [schema.py](/home/pingfan/PACT/excavator_testbed/testbed/data/schema.py) 和 [hdf5_io.py](/home/pingfan/PACT/excavator_testbed/testbed/data/hdf5_io.py) 为准。

---

## 扩展

新增 policy：
- 在 `testbed/policies/<name>/adapter.py` 下实现并注册到 `PolicyRegistry`

新增 backend：
- 实现 `testbed.backends.base.SimBackend`
- 在 eval/runtime 工厂处接入

---

## Legacy

原始 PACT 代码保留在 `legacy/`，不再作为当前 AGX 主路径继续扩展。
