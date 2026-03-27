# 训练 Setup 记录

本文档记录 Repo A 当前用于 AGX 挖掘任务的训练 setup。

它的目标不是解释协议，而是确保后续做这几件事时有同一份依据：
- 对比不同训练 run 的性能
- 复现实验
- 分析 rollout 失败原因
- 追踪“数据变了”还是“超参数变了”

状态日期：`2026-03-26`

---

## 1. 最终目标

这份文档存在的最终目标，不是单纯记录超参数，而是为了支持后续的失效归因。

如果后面训练出来的 ACT 学不会“挖土 → 旋转 → 倒土”，我们希望最终能明确区分下面几类原因：
- 数据问题：demo 质量差、风格混杂、长度分布异常、关键阶段覆盖不足
- 任务问题：reward / penalty 不合理，success 定义太晚，task logic 对 baseline 过难
- 实验设置问题：split 不稳定、训练轮数不够、chunk size 不合适、eval 条件不一致
- 策略问题：baseline ACT 的 open-loop chunking 不适合当前长时任务
- 接口问题：train-time 和 rollout-time 的 observation / action / reset 语义不一致

所以这里记录 training setup 的目的，是保证之后能回答这类问题，而不是把文档本身写得更大。

---

## 2. 这份文档应该放在哪个仓库

这份文档应该放在 **Repo A / testbed**，不应该放在 `sim-protocol`。

原因：
- `sim-protocol` 负责跨仓共享的协议、schema、常量、评测定义
- 训练超参数、数据目录、checkpoint 规则、AMP 设置、dataloader 设置，都是 testbed 侧实验实现细节
- 后续分析训练效果时，需要把这些信息和 `tb-train / tb-eval` 的产物放在一起管理

因此：
- Repo C 继续记录“线协议与字段定义”
- Repo A 记录“如何训练、如何评测、一次训练 run 具体用了什么配置”

---

## 3. 失效归因框架

后续遇到 baseline 失败时，建议按下面顺序排查。

### 3.1 第一层：先排接口和执行链路

先确认：
- 录制时的 observation / action 定义和 rollout 时一致
- reset 行为一致
- replay 没有明显偏差
- rollout 不是因为接口 bug 提前失真

如果这层没过，训练结果没有分析价值。

### 3.2 第二层：再排数据

重点看：
- demo 是否大多成功
- 是否覆盖完整的“挖土 → 旋转 → 倒土”链路
- 是否存在明显异常动作、异常长度、异常风格
- 训练集和验证集是否稳定

### 3.3 第三层：再排任务与 reward

重点看：
- reward / penalty 是否过 sparse 或过 noisy
- 是否存在强惩罚把 baseline 压死
- good-start / success 规则是否过难
- 是否任务逻辑已经超出 baseline ACT 的可学范围

### 3.4 第四层：最后才看策略与超参

重点看：
- `chunk_size`
- `kl_weight`
- batch size / epoch 数
- temporal aggregation
- 是否需要更频繁 replanning 或 phase-aware 改法

换句话说，training setup 记录的意义是：
- baseline 成功时，知道它是在什么条件下成功的
- baseline 失败时，知道失败更像是数据、任务、接口，还是模型本身

---

## 4. 当前训练配置的权威来源

当前以这些文件为准：
- [testbed/configs/act_agx_v0.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_v0.yaml)：正式训练默认配置
- [testbed/configs/act_agx_smoke.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_smoke.yaml)：最小 smoke 训练配置
- [testbed/policies/act/trainer.py](/home/pingfan/PACT/excavator_testbed/testbed/policies/act/trainer.py)：训练循环真实行为
- [testbed/runtime/_train.py](/home/pingfan/PACT/excavator_testbed/testbed/runtime/_train.py)：配置如何落到 trainer / dataloader

如果 README、实验记录、个人笔记和这些文件冲突，以这里列出的代码与配置文件为准。

---

## 5. 当前默认正式训练 setup

配置文件：
- [testbed/configs/act_agx_v0.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/act_agx_v0.yaml)

### 5.1 数据

- `task.task_name`: `agx_excavation_teleop`
- `task.equipment_model`: `agxunity`
- `task.dataset_dir`: 默认仍是 `data/agx_teleop`
- `task.num_episodes`: `20`
- `task.episode_len`: `1000`
- `task.camera_names`: `["fpv"]`

注意：
- 当前正式训练前，通常需要先把 `dataset_dir` 改到新录制目录，例如 `data/agx_teleop_v1`
- `num_episodes` 也应与该目录里实际可用 episode 数量一致

当前图像记录约束：
- 图像分辨率不是在 Repo A 训练配置里手填的，而是运行时由 Unity `GET_INFO` 返回的 camera descriptor 决定
- 每条 demo 会把实际值写进 HDF5 metadata：
  - `camera_width`
  - `camera_height`
  - `camera_fps`
  - `camera_row_order`
  - `image_format`
- 同一轮 baseline 录制、训练和评测必须保持固定分辨率，不要中途切换
- 已确认高分辨率 FPV 传输会影响 step-ack 实时性：
  - `1920x1060` 级别图像会让 teleop 明显发抖
  - 当前 baseline 应继续使用较低且稳定的固定分辨率

### 5.1.1 当前任务成功规则与录制结束规则

当前任务成功规则：
- success signal: `deposited_mass_in_target_box_kg`
- `mass_thresh`: `100.0 kg`
- `hold_steps`: `25`
- 也就是：

```text
deposited_mass_in_target_box_kg >= 100.0 kg
for 25 consecutive steps
```

当前与任务阶段相关的关键 reward / gating 语义：
- 只有在 DigArea 内满足 good-start，`loading` 才开始给正奖励
- `approaching_target` 依赖载荷和目标接近
- `hard_target_collision_count` 增长时给惩罚

当前 teleop 录制的 episode 结束条件：
- 达到任务 success 时，默认提前结束并保存
- 达到 `task.max_steps` 时结束并保存
- 用户主动 discard / quit 时，不按成功 episode 保存

对应配置来源：
- [testbed/configs/teleop_v0.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v0.yaml)
- [testbed/configs/eval_agx_v0.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/eval_agx_v0.yaml)
- [testbed/tasks/logic/excavator_reward.py](/home/pingfan/PACT/excavator_testbed/testbed/tasks/logic/excavator_reward.py)

### 5.2 模型

- `policy.class`: `ACT`
- `policy.device`: `cuda`
- `chunk_size`: `100`
- `kl_weight`: `10.0`
- `hidden_dim`: `512`
- `dim_feedforward`: `3200`

### 5.3 训练

- `lr`: `1e-5`
- `num_epochs`: `500`
- `batch_size`: `8`
- `seed`: `0`
- `device`: `cuda`
- `num_workers`: `0`
- `prefetch_factor`: `null`
- `persistent_workers`: `false`
- `pin_memory`: `true`
- `split_seed`: `0`
- `train_split_ratio`: `0.8`
- `reuse_split`: `true`
- `split_path`: 默认 `ckpt_dir/train_val_split.yaml`
- `val_every`: `5`
- `save_latest_every`: `10`
- `checkpoint_every`: `100`
- `plot_every`: `100`
- `amp`: `true`
- `amp_dtype`: `auto`
- `ckpt_dir`: `runs/ckpts/agx_excavation_act_v0`

这些设置的意图：
- `num_workers: 0`
  当前 HDF5 数据集在 `__getitem__` 内按 sample 打开文件，多 worker 容易引入明显抖动
- `val_every: 5`
  不是每个 epoch 都跑完整验证，减少纯评估开销
- `save_latest_every: 10`
  避免每个 epoch 都刷一遍 `policy_latest.ckpt`
- `amp: true` + `amp_dtype: auto`
  在 CUDA 上优先尝试 `bf16`，不支持时回退到 `fp16`

---

## 6. trainer 真实行为

当前 trainer 的几个关键点：

- 验证不是固定每个 epoch 都跑
  - 由 `train.val_every` 控制
  - 但首个 epoch 和最后一个 epoch 一定会验证
- `policy_latest.ckpt` 不是固定每个 epoch 都写
  - 由 `train.save_latest_every` 控制
  - 训练结束时还会再写一次最终 `policy_latest.ckpt`
- `policy_epoch_{epoch}_seed_{seed}.ckpt` 由 `train.checkpoint_every` 控制
- 训练曲线图输出由 `train.plot_every` 控制
- 如果启用了 AMP：
  - `amp_dtype=auto` 时，CUDA 优先 `bf16`，否则回退 `fp16`
  - `fp16` 路径会启用 `GradScaler`

相关代码：
- [testbed/policies/act/trainer.py](/home/pingfan/PACT/excavator_testbed/testbed/policies/act/trainer.py)

---

## 7. 一次训练 run 至少要记录什么

后续如果要分析“训练为什么快/慢”“rollout 为什么变好/变差”“baseline 到底为什么没学会”，建议每次 run 至少固定记录下面这些字段。

### 7.1 数据侧

- `dataset_dir`
- `num_episodes`
- 实际可用 episode 数
- `episode_len`
- `camera_names`
- `env_state_order`
- `operator_id`
- `session_id`
- `notes`
- `record_config_path`
- `record_config_yaml`
- 数据录制日期
- 数据对应的 Unity / scene 版本

### 7.2 模型与训练侧

- `chunk_size`
- `kl_weight`
- `hidden_dim`
- `dim_feedforward`
- `lr`
- `batch_size`
- `num_epochs`
- `seed`
- `num_workers`
- `split_seed`
- `train_split_ratio`
- `reuse_split`
- `val_every`
- `save_latest_every`
- `checkpoint_every`
- `amp`
- `amp_dtype`

### 7.3 运行环境

- GPU 型号
- CUDA 版本
- PyTorch 版本
- conda 环境名
- Repo A git commit
- Repo B git commit
- Repo C git commit

### 7.4 输出产物

- `ckpt_dir`
- 最佳 checkpoint 路径
- `dataset_stats.pkl` 路径
- `train_val_split.yaml` 路径
- `resolved_config.yaml` 路径
- `run_metadata.json` 路径
- 训练曲线图路径
- eval 结果目录
- `metrics.json`
- `results.csv`
- `rollout_manifest.json`
- `rollouts/rollout_XXX.jsonl`
- `rollouts/rollout_XXX_summary.json`
- dataset QC 输出目录
- `summary.json`
- `episodes.csv`
- `episode_length_hist.png`
- `action_distribution.png`
- `state_ranges.png`

---

## 8. 推荐的实验记录方式

推荐每次正式训练都额外保存一份 run-level 记录，例如：
- `runs/ckpts/<run_name>/resolved_config.yaml`
- `runs/ckpts/<run_name>/run_notes.md`

当前代码已经会自动写出：
- `runs/ckpts/<run_name>/train_val_split.yaml`
- `runs/ckpts/<run_name>/resolved_config.yaml`
- `runs/ckpts/<run_name>/run_metadata.json`

当前代码在评测与数据侧还会自动写出：
- `runs/eval/<run_name>/results/rollout_manifest.json`
- `runs/eval/<run_name>/results/rollouts/rollout_XXX.jsonl`
- `runs/eval/<run_name>/results/rollouts/rollout_XXX_summary.json`
- `<dataset_dir>/qc/summary.json`
- `<dataset_dir>/qc/episodes.csv`
- `<dataset_dir>/qc/*.png`

其中 dataset QC 对损坏或未完整写完的 `episode_*.hdf5` 会跳过并记 warning，不会因为单个坏文件直接中断整批检查。

当前 eval 运行时默认还会输出 step 进度日志：

```text
rollout 000  step 50 / 1000
```

对应配置：
- `eval.step_log_interval`
- 默认值：`50`
- 设为 `0` 可关闭这类进度输出

其中 `run_metadata.json` 当前已自动包含：
- 启动命令
- 当前 Python / torch / cuda / GPU 信息
- Repo A git commit / branch / dirty 状态
- 本次 run 使用的 split 摘要
- 训练结束后的 `best_epoch` / `best_val_loss`

当前仍未自动写出的内容：
- Repo B / Repo C git commit
- rollout 结果目录回链
- 人工实验备注
- broken demo 排除标记

其中至少包含：
- 本次 run 名称
- 启动命令
- 实际使用的数据目录
- 实际使用的配置快照
- 代码仓库 commit
- 对应的 rollout 评测目录

这样后面才能可靠回答这些问题：
- 这个模型变好，是因为新数据，还是因为 `chunk_size` 改了
- 这个训练变快，是因为 AMP，还是因为验证频率降了
- 这个 rollout 成功率变化，是因为 Unity 场景换了，还是 reward 逻辑换了
- 这个 baseline 学不会，到底更像是数据问题、任务问题、实验设置问题，还是策略本身的问题

---

## 9. 训练前检查清单

正式训练前，建议至少确认：

1. `python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict` 能过
2. 新数据目录里的 episode 是当前 9D `env_state`
3. `task.dataset_dir` 和 `task.num_episodes` 已改到目标数据集
4. `chunk_size` 不大于 episode 实际有效长度
5. `ckpt_dir` 是新的 run 目录，不会覆盖旧实验
6. 如果要做性能对比，保留完整 config 快照和 git commit

---

## 10. 后续建议

如果后面要把训练分析做成更正式的实验体系，下一步建议加：
- 训练结束后自动把 eval 配置与结果目录串起来
- 自动把 Repo B / Repo C git commit 写进 run metadata
- 给 rollout summary 增加更稳定的 failure taxonomy 聚合
- 把 failure taxonomy 和 rollout 日志关联起来，形成可复盘的失败样本库

当前这份文档先解决的是“训练 setup 有统一记录入口”，不是“实验管理系统已经完整实现”。

---

## 11. 2026-03-26 本轮 smoke 验证结论

今天这轮验证，重点不是比较算法性能，而是确认新增的训练/评测/数据记录能力已经真正落地。

### 11.1 已确认工作正常的功能

- 训练侧：
  - `train_val_split.yaml`
  - `resolved_config.yaml`
  - `run_metadata.json`
- 数据侧：
  - `tb-dataset-qc`
  - demo-level metadata
  - 录制成功即结束
- 评测侧：
  - `metrics.json`
  - `results.csv`
  - `rollout_manifest.json`
  - `rollout_XXX.jsonl`
  - `rollout_XXX_summary.json`
  - eval 终端 step progress 输出

### 11.2 这次 smoke 数据与 smoke eval 应该怎么理解

当前真实 smoke 数据目录：
- `data/agx_teleop_fulltest/`

对应 QC 结果：
- `data/agx_teleop_fulltest/qc/summary.json`
- `data/agx_teleop_fulltest/qc/episodes.csv`

这批数据当前的结论是：
- 只有 `2` 条 demo
- 两条都成功、可读、带 9D `env_state`
- timestamps、images、metadata 都正常
- 但 episode 都长达 `1000` 步，存在较长等待段

因此，这批数据适合：
- 验证 `record -> qc -> train -> eval` 新链路
- 做最小 smoke baseline

但不适合：
- 直接当正式 baseline 数据集
- 用来严肃判断 reward / task / policy 谁是主要瓶颈

当前 smoke eval 目录：
- `runs/eval/agx_excavation_smoke_results/`

对应结果：
- `metrics.json`：`2` 个 rollout，`0` success
- `rollout_manifest.json`：逐 rollout summary 正常落盘
- `rollout_XXX.jsonl`：能看到逐步 `reward_phase / env_state / action / task events`

这次 `0 / 2` success 的当前解释是：
- 合理
- 主要因为 demo 数量极小、训练规模极小
- rollout 日志显示策略“没有进入 good dig start”，而不是记录系统或接口系统出了问题

### 11.3 当前必须固定下来的运行时约束

本轮还确认了一个很重要的实验约束：
- AGX teleop / eval 的实时手感对图像分辨率非常敏感

已知现象：
- 传输 `1920x1060` 级别图像时，step-ack 路径会明显变慢，AGX 窗口操作发抖
- 改回较低固定分辨率后，交互恢复正常

因此当前正式 baseline 前必须遵守：
- 录制、训练、评测使用同一套固定图像分辨率
- 不要在一次 baseline 实验中途切换 resolution
- 高分辨率视觉配置不要直接混入当前 live teleop baseline
