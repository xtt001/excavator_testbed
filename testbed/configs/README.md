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
| real-domain one-dig smoke | `testbed/configs/act_real_one_dig_v1_smoke.yaml` | 快速验证真实 FPV + real `qpos/qvel` 训练链路 |
| real-domain one-dig train | `testbed/configs/act_real_one_dig_v1_train.yaml` | 第一轮较长 real-domain 训练，用于 offline imitation eval / shadow |
| real-domain one-dig overfit probes | `testbed/configs/act_real_one_dig_v1_ep8_overfit.yaml` / `act_real_one_dig_v1_ep8_zero_latent_overfit.yaml` / `act_real_one_dig_v1_ep8_zero_latent_dense_overfit.yaml` / `act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml` / `act_real_one_dig_v1_all9_overfit.yaml` | 诊断模型是否能记住单条或全部 9 条真实 demo；当前不要求泛化时，all9 zero-latent dense checkpoint 可作为 shadow / guarded 真机测试候选 |

## 1. 文件族怎么区分

仓库里的 YAML 可以按入口命令分成五组：

| 文件前缀 | 入口命令 | 作用 |
|---|---|---|
| `teleop_*.yaml` | `tb-record-teleop`、`tb-replay` | 录制和回放配置 |
| `act_agx_*.yaml` | `tb-train` | AGX 挖掘机 ACT 训练配置 |
| `act_real_*.yaml` | `tb-train`、`tb-offline-real-one-dig-eval` | 真机录制数据的 real-domain ACT 训练和离线评测配置 |
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
| `act_real_one_dig_v1_smoke.yaml` | `tb-train` | real-domain smoke | 指向 `data/real_one_dig_v1_windows/`；5 epoch 快速检查真实 FPV + real `qpos(rad)` + `qvel(rad/s)` 训练链路 |
| `act_real_one_dig_v1_train.yaml` | `tb-train` | real-domain train | 同一数据入口；100 epoch，checkpoint 频率更疏，作为第一轮 offline shadow/eval 候选 |
| `act_real_one_dig_v1_ep8_overfit.yaml` | `tb-train` | diagnostic overfit | 只用 converted `episode_8`，`chunk_size=25`，用于验证模型/数据接口是否能记住一条成功 one-dig |
| `act_real_one_dig_v1_ep8_zero_latent_overfit.yaml` | `tb-train` | diagnostic overfit | 只用 converted `episode_8`，训练时也使用 inference 的 zero-latent 路径，避免 teacher-forced CVAE val loss 掩盖推理时动作塌缩 |
| `act_real_one_dig_v1_ep8_zero_latent_dense_overfit.yaml` | `tb-train` | diagnostic overfit | 在 zero-latent 基础上使用 `sample_repeats`，让每个 epoch 从同一条 episode 采多个随机 chunk，检查完整轨迹能否被记住 |
| `act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml` | `tb-train` | imitation candidate | 9 条 real one-dig 同时作为 train/val，使用 zero-latent + `sample_repeats`；当前可作为第一版 live shadow / 低幅度 guarded 真机测试候选 |
| `act_real_one_dig_v1_all9_overfit.yaml` | `tb-train` | diagnostic overfit | 9 条 real one-dig 同时作为 train/val，`chunk_size=25`，用于判断当前数据是否可被模型记住 |
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

### 3.1 Real One-Dig 数据入口和离线评测

真机 one-dig v1 不经过 V2 planner、primitive、phase label 或 token。数据入口和顺序是：

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

`tb-build-real-one-dig-v1` 默认只取源 `episode_13..21`，并重映射成训练友好的 `episode_0..8`。每条输出在 metadata 中保留 `source_episode_id`、`source_episode_index`、裁剪窗口和原始单位。裁剪规则为 `first_nonzero(raw_action)-25` 到 `first_nonzero(go_home_commanded_action)-25`，并把 `/observations/encoded_images/fpv` JPEG 解码成 `/observations/images/fpv` raw RGB。

`tb-offline-real-one-dig-eval` 读取同一份 real-domain 配置和 checkpoint，在真实 FPV/qpos/qvel 上只预测、不下发，逐帧比较专家 `action` 和模型 `policy_action`。每条 episode 输出 overlay MP4、四轴 action 曲线、metrics JSON 和 actions CSV；汇总输出 `summary.csv`、`summary.json` 与 `offline_eval_resolved_config.yaml`。

本轮 real2sim replay 已确认两个主要 gap：位置需要做零点、方向、范围和绝对角/相对关节角映射；命令执行还受真机底层控制器、负载、摩擦和 AGX target-speed controller 影响。第一轮不再用 replay 后的 sim 数据训练或评测，先判断真实数据上 imitation learning 是否能学到 FPV 到 action 的映射。

`*_overfit.yaml` 最初是诊断配置：如果单条 episode 或全部 9 条都不能把专家 action 曲线贴住，应先查 action normalization、chunk size、loss 和采样方式。当前阶段不要求泛化，只要求 9 条成功 demo 的动作模仿，因此 `act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml` 对应 checkpoint 可作为第一版 live shadow / 低幅度 guarded 真机测试候选；单条 episode overfit 配置仍只作诊断。ACT 默认训练/val 使用 teacher-forced CVAE latent，而 eval/inference 使用 zero latent；`*_zero_latent*_overfit.yaml` 专门让训练也走 zero-latent 路径，用来判断真实推理链路能否记住专家动作。`train.sample_repeats` 会把同一批 episode 在一个 epoch 内重复采样多次，避免每条 episode 每个 epoch 只有一个随机 chunk。

raw real-world 数据不修改。`raw_action` 和 `commanded_action` 只用于诊断 joystick 偏移和底层命令差异，训练主标签仍是转换窗口中的 `action`。

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
