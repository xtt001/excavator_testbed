# 配置文件索引

本文档说明 `testbed/configs/` 下所有 YAML 的角色、入口命令和建议使用场景。

如果你只想知道今天应该用哪几个文件，先看下面这张表：

| 目标 | 推荐配置 | 说明 |
|---|---|---|
| 当前业务 baseline 录制 | `testbed/configs/teleop_v1.yaml` | 当前正式 rerecord 数据入口，输出到 `data/agx_teleop_v1/` |
| 当前业务 baseline 训练 | `testbed/configs/act_agx_v1.yaml` | 当前默认 ACT 训练入口 |
| 当前业务 baseline 评测 | `testbed/configs/eval_agx_v1.yaml` | 当前默认 live eval 入口 |
| 历史 fulltest 基线 | `testbed/configs/act_agx_fulltest.yaml` + `testbed/configs/eval_agx_fulltest.yaml` | 保留为 `qpos` 历史对照 |
| `qpos + qvel` 对照 | `testbed/configs/act_agx_fulltest_qvel.yaml` + `testbed/configs/eval_agx_fulltest_qvel.yaml` | 当前输入消融对照线 |
| smoke 验证 | `testbed/configs/act_agx_smoke.yaml` + `testbed/configs/eval_agx_smoke.yaml` | 只用来验证 train/eval 链路 |

## 1. 文件族怎么区分

仓库里的 YAML 可以按入口命令分成五组：

| 文件前缀 | 入口命令 | 作用 |
|---|---|---|
| `teleop_*.yaml` | `tb-record-teleop`、`tb-replay` | 录制和回放配置 |
| `act_agx_*.yaml` | `tb-train` | AGX 挖掘机 ACT 训练配置 |
| `eval_agx_*.yaml` | `tb-eval` | AGX 挖掘机 live eval 配置 |
| `act_v0.yaml` / `eval_v0.yaml` / `task_v0.yaml` | `tb-train`、`tb-eval`、`tb-record` | 早期 MuJoCo transfer-cube 验证链路 |
| `agx_v0.yaml` | 手动参考 | AGX 连接参数和向量维度说明 |

一个实用判断规则是：

- 看到 `teleop_`，优先想到数据采集和 replay QA。
- 看到 `act_agx_`，优先想到训练数据版本、输入维度和 checkpoint 目录。
- 看到 `eval_agx_`，优先想到 success 口径、reward override 和 rollout 输出目录。

## 2. AGX 录制与回放配置

| 文件 | 入口 | 当前角色 | 关键差异 |
|---|---|---|---|
| `teleop_v1.yaml` | `tb-record-teleop`、`tb-replay` | 当前业务 baseline | 录到 `data/agx_teleop_v1/`；录制 success 使用 `dump_complete_final_hold`；要求 `300 kg` retained mass、`bucket <= 100 kg`、`hold 25` 步；成功后继续录 `50` 步尾段 |
| `teleop_v0.yaml` | `tb-record-teleop`、`tb-replay` | legacy 录制配置 | 输出到 `data/agx_teleop/`；录制 success 阈值较宽松，`mass_thresh = 100 kg`；适合兼容旧数据和早期流程 |

这两份文件都包含四类字段：

| 配置块 | 作用 |
|---|---|
| `agx` | Unity 连接参数、reset 行为 |
| `teleop` | 输入设备、录制条数、操作员元数据、摇杆映射 |
| `task` | 数据目录、步长、相机、控制频率 |
| `success` / `reward` | 录制期的结束判定和任务奖励参数 |

## 3. AGX ACT 训练配置

| 文件 | 入口 | 当前角色 | 关键差异 |
|---|---|---|---|
| `act_agx_v1.yaml` | `tb-train` | 当前业务 baseline | `data/agx_teleop_v1/`，`30` 条 demo，`num_epochs = 2000`，`batch_size = 4`，checkpoint 写到 `runs/ckpts/agx_excavation_act_v1/` |
| `act_agx_fulltest.yaml` | `tb-train` | 历史 `qpos` 基线 | `data/agx_teleop_fulltest/`，`20` 条 demo，`num_epochs = 500`，作为 `fulltest(qpos)` 对照 |
| `act_agx_fulltest_qvel.yaml` | `tb-train` | 当前输入消融对照 | 与 `act_agx_fulltest.yaml` 使用同一批数据和超参；额外设置 `policy.low_dim_keys = [qpos, qvel]` |
| `act_agx_smoke.yaml` | `tb-train` | smoke 配置 | 只跑 `5` 条 demo、`5` 个 epoch，用来验证 train/eval 链路 |
| `act_agx_v0.yaml` | `tb-train` | legacy AGX 训练配置 | 指向 `data/agx_teleop/`，保留早期默认值；适合复现旧 run，今天不作为默认入口 |

这些训练配置的共同结构是：

| 配置块 | 作用 |
|---|---|
| `task` | 数据集路径、episode 数、相机名、设备模型 |
| `policy` | 模型类型和低维输入定义，当前主线使用 `ACT` |
| `train` | 学习率、epoch、batch size、split 和 checkpoint 策略 |
| `eval` | 训练完成后的默认 ckpt / 输出目录，主要用于补全 run 信息 |

其中最容易看错的字段有三个：

| 字段 | 解释 |
|---|---|
| `task.dataset_dir` | 训练读哪一批 demo，先看这个字段就能判断是 `v1`、`fulltest` 还是 `v0` |
| `policy.low_dim_keys` | 控制 ACT 低维输入，默认只有 `qpos`；只有 `act_agx_fulltest_qvel.yaml` 扩成 `qpos + qvel` |
| `train.ckpt_dir` | 决定 checkpoint、`run_metadata.json`、`resolved_config.yaml` 的落盘目录 |

## 4. AGX Live Eval 配置

| 文件 | 入口 | 当前角色 | 关键差异 |
|---|---|---|---|
| `eval_agx_v1.yaml` | `tb-eval` | 当前业务 baseline | 对应 `runs/ckpts/agx_excavation_act_v1/`；主 success 口径是 `dump_complete_final_hold` |
| `eval_agx_fulltest.yaml` | `tb-eval` | 历史 `qpos` 基线 | 对应 `fulltest(qpos)` checkpoint 和结果目录 |
| `eval_agx_fulltest_qvel.yaml` | `tb-eval` | 当前输入消融对照 | 对应 `fulltest(qpos+qvel)` checkpoint；`policy.low_dim_keys = [qpos, qvel]` |
| `eval_agx_smoke.yaml` | `tb-eval` | smoke 配置 | `num_rollouts = 2`，结果目录单独隔离，适合快速检查 live rollout |
| `eval_agx_v0.yaml` | `tb-eval` | legacy AGX eval 配置 | 早期默认 eval 入口，保留给旧 checkpoint 和旧结果复现 |

这些评测配置的重点在三块：

| 配置块 | 作用 |
|---|---|
| `eval` | rollout 次数、视频和结果落盘目录、step log 间隔 |
| `success` | live eval 的成功口径；当前主线使用 `dump_complete_final_hold` |
| `reward` | rollout 期间的 reward override，和训练数据本身无关 |

如果只想快速读懂一份 `eval_agx_*.yaml`，优先看下面这几个字段：

| 字段 | 解释 |
|---|---|
| `eval.ckpt_dir` / `policy.ckpt_path` | 评测哪个 checkpoint |
| `eval.results_dir` | rollout 汇总和 `metrics.json` 输出到哪里 |
| `success.mode` | 成功口径类型 |
| `success.mass_thresh` / `residual_bucket_mass_thresh` / `hold_steps` | `dump_complete_final_hold` 和 `strict_dump_complete` 的主阈值 |
| `success.strict_max_failures` | strict 口径下的阻断条件 |

## 5. 辅助和 legacy 配置

| 文件 | 当前角色 | 说明 |
|---|---|---|
| `agx_v0.yaml` | 手动参考 | 只保留 AGX 连接参数、向量维度和 `env_state` 索引说明。今天的主线命令更常直接从 `teleop_*.yaml` 或 `eval_agx_*.yaml` 读这些字段。 |
| `task_v0.yaml` | legacy MuJoCo 录制配置 | 供 `tb-record` 走 transfer-cube 验证链路，和当前 AGX 主线无关。 |
| `act_v0.yaml` | legacy MuJoCo 训练配置 | 供 `tb-train` 在 transfer-cube 数据上验证 ACT 训练。 |
| `eval_v0.yaml` | legacy MuJoCo 评测配置 | 供 `tb-eval` 在 transfer-cube 任务上做离线验证。 |

这几份文件还保留在仓库里，是因为它们仍然对下面两件事有价值：

- 保留最早打通训练栈时的最小可运行样例。
- 在 AGX 链路出问题时，提供一个和 Unity 无关的对照入口。

## 6. 什么时候该改哪份文件

| 你想做的事 | 应该改哪里 |
|---|---|
| 重录新一批正式 demo | `teleop_v1.yaml` |
| 调整当前 ACT baseline 的 epoch、batch size、checkpoint 目录 | `act_agx_v1.yaml` |
| 新开一个 `qvel`、`task-state` 或其他输入消融 | 复制 `act_agx_fulltest_qvel.yaml` 或 `act_agx_v1.yaml` 新建一份对照配置 |
| 调整 live eval 的成功口径 | 对应的 `eval_agx_*.yaml` |
| 复现旧实验 | 对应保留的 `*_v0.yaml` 或 `*_fulltest.yaml` |

## 7. 当前建议

今天如果你要继续业务主线，默认用下面三份：

- `testbed/configs/teleop_v1.yaml`
- `testbed/configs/act_agx_v1.yaml`
- `testbed/configs/eval_agx_v1.yaml`

今天如果你要做输入消融或历史对照，优先从下面两份开始：

- `testbed/configs/act_agx_fulltest_qvel.yaml`
- `testbed/configs/eval_agx_fulltest_qvel.yaml`
