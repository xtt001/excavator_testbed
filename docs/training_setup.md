# 训练 Setup 记录

本文档是 Repo A 所有训练与评测实验的参考基准。

目标：
- 对比不同 run 的性能时有统一依据
- 复现实验时能确认完整上下文
- 分析 rollout 失败时知道从哪一层开始排查
- 追踪"数据变了"还是"超参数变了"还是"eval 口径变了"

状态日期：`2026-04-14`

---

## 1. 失效归因框架

训练出来的 ACT 学不会任务时，建议按下面顺序排查，不要跳层。

### 第一层：接口与执行链路

先确认：
- 录制时的 observation / action 定义和 rollout 时一致
- reset 行为一致
- replay 没有明显偏差
- rollout 不是因为接口 bug 提前失真

如果这层没过，训练结果没有分析价值。

### 第二层：数据

重点看：
- demo 是否大多成功
- 是否覆盖完整的"挖土 → 旋转 → 倒土"链路
- 是否存在明显异常动作、异常长度、异常风格
- 训练集和验证集是否稳定

### 第三层：任务与 reward

重点看：
- reward / penalty 是否过 sparse 或过 noisy
- 是否存在强惩罚把 baseline 压死
- good-start / success 规则是否过难
- 是否任务逻辑已经超出 baseline ACT 的可学范围

### 第四层：策略与超参

重点看：
- `chunk_size`
- `kl_weight`
- batch size / epoch 数
- temporal aggregation
- 是否需要更频繁 replanning 或 phase-aware 改法

---

## 2. 配置权威来源

如果 README、实验记录、个人笔记和这些文件冲突，以配置文件与代码为准。

| 用途 | 文件 |
|---|---|
| 当前业务 baseline 训练 | `testbed/configs/act_agx_v1.yaml` |
| 当前业务 baseline 评测 | `testbed/configs/eval_agx_v1.yaml` |
| fulltest baseline（qpos）| `testbed/configs/act_agx_fulltest.yaml` |
| fulltest 对照（qpos+qvel）| `testbed/configs/act_agx_fulltest_qvel.yaml` |
| smoke 训练 | `testbed/configs/act_agx_smoke.yaml` |
| legacy 默认训练配置 | `testbed/configs/act_agx_v0.yaml` |
| fulltest eval（qpos）| `testbed/configs/eval_agx_fulltest.yaml` |
| fulltest eval（qpos+qvel）| `testbed/configs/eval_agx_fulltest_qvel.yaml` |
| 全部 YAML 文件索引 | `testbed/configs/README.md` |
| 训练循环真实行为 | `testbed/policies/act/trainer.py` |
| 配置如何落到 trainer | `testbed/runtime/_train.py` |

---

## 3. 当前训练配置参考

### 3.1 数据

当前业务 baseline 默认使用 rerecord `v1` 数据集；`fulltest` 保留为历史基线与 `qvel` 对照。

| 字段 | v1 baseline 默认值 | 说明 |
|---|---|---|
| `task.task_name` | `agx_excavation_teleop` | |
| `task.equipment_model` | `agxunity` | |
| `task.dataset_dir` | `data/agx_teleop_v1` | 当前业务主线默认目录 |
| `task.num_episodes` | `30` | 需与目录内实际 episode 数一致 |
| `task.episode_len` | `1000` | |
| `task.camera_names` | `["fpv"]` | |

图像分辨率不在训练配置里手填，由 Unity `GET_INFO` 返回，写入每条 HDF5 的 metadata。同一轮 baseline 录制、训练、评测必须使用固定分辨率，不要中途切换。已知 `1920×1060` 级别会让 live teleop 发抖，当前 baseline 保持较低固定分辨率。

#### ACT 实际用了哪些 HDF5 字段

当前 ACT BC 训练直接使用：
- `observations/qpos`
- `observations/images/<camera>`
- `action`

**不进入** ACT loss 的字段（仅用于 replay、QC、rollout 诊断、failure analysis）：
- `qvel`、`env_state`、`rewards`、`task_success`、`timestamps`

`qpos + qvel` 对照实验路径已就位（`act_agx_fulltest_qvel.yaml`），当前仍保留在 `fulltest` 线上，和 `v1(qpos)` baseline 是独立 checkpoint，不共用。

### 3.2 模型

| 字段 | 值 |
|---|---|
| `policy.class` | `ACT` |
| `policy.device` | `cuda` |
| `chunk_size` | `100` |
| `kl_weight` | `10.0` |
| `hidden_dim` | `512` |
| `dim_feedforward` | `3200` |

### 3.3 训练超参

| 字段 | v1 baseline 值 | 说明 |
|---|---|---|
| `lr` | `1e-5` | |
| `num_epochs` | `2000` | 当前业务 baseline 采用长训练周期 |
| `batch_size` | `4` | `30` 条 demo 下较稳妥 |
| `seed` | `0` | |
| `device` | `cuda` | |
| `num_workers` | `0` | HDF5 按 sample 开文件，多 worker 容易抖 |
| `split_seed` | `0` | |
| `train_split_ratio` | `0.8` | |
| `reuse_split` | `true` | |
| `val_every` | `5` | |
| `save_latest_every` | `10` | |
| `checkpoint_every` | `50` | |
| `plot_every` | `50` | |
| `amp` | `true` | |
| `amp_dtype` | `auto` | CUDA 优先 bf16，否则回退 fp16 |
| `ckpt_dir` | `runs/ckpts/agx_excavation_act_v1` | 每次新 run 用新目录 |

### 3.4 eval 成功口径

当前推荐主口径：`dump_complete_final_hold`

| 口径 | 语义 |
|---|---|
| `legacy_any` | rollout 中任意时刻触发过 task_success 即记成功 |
| `final_hold` | 结束时 `deposited_mass >= mass_thresh`，连续 hold_steps |
| `strict_final_hold` | 在 final_hold 基础上，再要求 failure counts 不超阈值 |
| `dump_complete_final_hold` | 结束时 deposited_mass + bucket 已基本倒空，连续 hold_steps |
| `strict_dump_complete` | 在 dump_complete_final_hold 基础上加 strict failure count 限制 |

推荐默认阈值：
- `mass_thresh = 300.0 kg`
- `residual_bucket_mass_thresh = 100.0 kg`
- `hold_steps = 25`
- strict 阻断：`hard_target_collision: 0`、`spill_before_target: 0`

### 3.5 录制结束规则

`tb-record-teleop` 的 `stop_on_success: true` 使用 backend 每步返回的 `task_success`，即录制期用的是 backend 录制时的 mission success 语义，和后续 `tb-eval` 选哪种 success mode 是两回事。

当前 teleop 录制期 success 规则（`deposited_mass_in_target_box_kg >= 100.0 kg` 持续 25 步）比 eval 推荐口径（300 kg）宽松，但这不会让旧 demo 失效——先重训/重评测，再决定要不要重录。

当前建议重录时优先使用 [testbed/configs/teleop_v1.yaml](/home/pingfan/PACT/excavator_testbed/testbed/configs/teleop_v1.yaml)：
- `dataset_dir = data/agx_teleop_v1`
- `success.mode = dump_complete_final_hold`
- `success.mass_thresh = 300.0 kg`
- `success.residual_bucket_mass_thresh = 100.0 kg`
- `success.hold_steps = 25`
- `teleop.post_success_tail_steps = 50`

这份 `v1` 配置现在会在 recorder/backend 中使用完整的 dump-complete 录制逻辑：
- target retained mass 达到 `300kg`
- bucket residual mass 降到 `100kg` 以下
- 连续保持 `25` 步
- 然后再录 `50` 步尾段

这样录下来的 demo 会包含更完整的 dump 后半段，而不是在刚达到 `100kg` retained mass 时立刻截断。

### 3.6 数据验证与视频导出工具

录制完成后有两种方式检查数据：

**离线导出视频**（不需要 AGX，推荐优先使用）：
```bash
# 导出整个目录的 FPV 视频
tb-dataset-videos data/agx_teleop_v1/

# 指定输出目录
tb-dataset-videos data/agx_teleop_v1/ -o runs/videos/v1

# 只导出特定 episode
tb-dataset-videos data/agx_teleop_v1/ --indices 0 3 5 10
```

视频默认输出到 `<dataset_dir>/videos/`，文件名与 episode 对应（如 `episode_0.mp4`）。

**AGX 回放 QA**（需要连 AGX，用于验证动作重放一致性）：
```bash
# 批量回放整个目录
tb-replay --episode data/agx_teleop_v1/ --config testbed/configs/teleop_v1.yaml --save-video

# 单个 episode
tb-replay --episode data/agx_teleop_v1/episode_0.hdf5 --config testbed/configs/teleop_v1.yaml

# 重放旧 action 序列并重新记录当前 Unity observation/env_state
tb-replay \
  --episode data/agx_teleop_v1/episode_0.hdf5 \
  --config testbed/configs/teleop_v1.yaml \
  --record-output-dir data/agx_teleop_v1_replayed_current

# replay 逐 step 诊断：定位 qpos/swing 跳变、碰撞和接触触发点
tb-replay \
  --episode data/agx_teleop_v1/episode_0.hdf5 \
  --config testbed/configs/teleop_v1.yaml \
  --diagnostic-log runs/diagnostics/episode_0_replay_diagnostics.jsonl \
  --diagnostic-every 1
```

`tb-replay` 支持单文件或目录输入。批量回放时会自动按 episode 编号排序，共享同一个 backend 连接，最后输出 qpos diff 汇总表。加上 `--record-output-dir` 后，会把 source episode 的 actions 在当前 Unity 后端里重新执行并写成新的 HDF5，可用于 Unity 侧 `env_state` 或相机观测变更后的数据刷新。

刷新写新 HDF5 时，`tb-replay` 会默认读取 config 里的
`teleop.post_success_tail_steps`，当前 V2.1 是 `50` 步，并在 source
actions 后追加 zero-action hold tail。这个 tail 保留 terminal dump 后的
plateau / `dump_end` 观测；可用 `--post-tail-steps <N>` 临时覆盖。刷新
replay 会跳过 source episode 里的旧 image dataset，只读取 actions/qpos/metadata，
并把当前 Unity 后端返回的新图像写入输出 HDF5。

需要查 swing 或 AGX 碰撞导致的 replay 漂移时，加
`--diagnostic-log <path.jsonl>`。JSONL 会记录每步 action、source/replay
qpos/qvel、qpos 误差、bucket 相对 DigArea 坐标、contact/collision、
removed-depth 和 bucket mass delta 等关键量；`tb-replay-diagnostics --input
<path-or-dir> --top 20` 可快速汇总首个/最大的 qpos error、qpos jump、碰撞和
接触 step。

旧 YuLong 原始数据如果包含已修复、随机且无法原样复现的 actuator pose 跳变，刷新
removed-depth 时可在 replay 期间启用对齐，而不是事后改旧 HDF5：
`--realign-on-qpos-error --realign-axis all --realign-error-threshold 0.04`。
该模式会在持续 qpos 偏差后通过 Unity `REALIGN_POSE` 协议把当前仿真 4D
qpos 拉回 source，并继续用当前 Unity 重写 image/env_state/depth；诊断 JSONL
会写 `pose_realign` 事件。`swing` 模式只保留作窄范围调试。

两者区别：`tb-dataset-videos` 直接读 HDF5 中已存储的图片帧，速度快且无需 AGX；`tb-replay` 重新通过 AGX 执行动作序列，用于验证 action→observation 的可重放性。

---

## 4. 实验命名规范

### 4.1 基本原则

- 实验名应编码"模型变体"和"数据版本"，**不**编码 eval 口径
- eval 口径是评测参数，记在实验记录的 `success_mode` 字段里，不进入目录名
- 同一 checkpoint 用不同 eval 口径重跑，**不是**新实验，用 `--name` 参数重用原实验名并追加 notes

### 4.2 推荐命名格式

```
<任务>_<模型变体>_<数据版本>
```

示例：

| 场景 | 推荐名称 |
|---|---|
| 当前业务 baseline（rerecord `v1`） | `agx_act_qpos_v1` |
| qpos baseline，fulltest 数据第 1 轮 | `agx_act_qpos_fulltest_v1` |
| qpos+qvel 对照，同一批数据 | `agx_act_qpos_qvel_fulltest_v1` |
| 加 mass_in_bucket conditioning | `agx_act_qpos_qvel_taskstate_fulltest_v1` |
| 新一批 rerecord 数据，重跑业务 baseline | `agx_act_qpos_v2` |

### 4.3 checkpoint 目录命名

`ckpt_dir` 建议与实验名一致：
```
runs/ckpts/agx_act_qpos_fulltest_v1/
runs/ckpts/agx_act_qpos_qvel_fulltest_v1/
```

不要用 `agx_excavation_act_fulltest` 这类泛化名称——它不包含模型变体信息，多个 run 会互相覆盖。

---

## 5. 一次实验应该记录什么

### 5.1 数据侧

| 字段 | 记录方式 |
|---|---|
| `dataset_dir` | `[自动]` run_metadata.json |
| `num_episodes` | `[自动]` run_metadata.json |
| 实际可用 episode 数 | `[自动]` run_metadata.json |
| `episode_len` | `[自动]` resolved_config.yaml |
| `camera_names` | `[自动]` resolved_config.yaml |
| `env_state_order` | `[自动]` HDF5 metadata |
| `operator_id` / `session_id` | `[自动]` HDF5 metadata + qc/episodes.csv |
| 数据录制日期 | `[手动]` 在 `--notes` 里说明 |
| 对应的 Unity / scene 版本 | `[手动]` 在 `--notes` 里说明 |

### 5.2 模型与训练侧

| 字段 | 记录方式 |
|---|---|
| `chunk_size`、`kl_weight`、`hidden_dim`、`dim_feedforward` | `[自动]` resolved_config.yaml |
| `lr`、`batch_size`、`num_epochs`、`seed` | `[自动]` resolved_config.yaml |
| `split_seed`、`train_split_ratio` | `[自动]` resolved_config.yaml |
| `val_every`、`save_latest_every`、`checkpoint_every` | `[自动]` resolved_config.yaml |
| `amp`、`amp_dtype` | `[自动]` resolved_config.yaml |
| best epoch / best val loss | `[自动]` run_metadata.json |

### 5.3 运行环境

| 字段 | 记录方式 |
|---|---|
| GPU 型号、CUDA 版本、PyTorch 版本 | `[自动]` run_metadata.json |
| conda 环境名 | `[自动]` run_metadata.json |
| Repo A git commit | `[自动]` run_metadata.json |
| Repo B / Repo C git commit | `[手动]` 在 `--notes` 里说明（暂未自动化） |

### 5.4 评测侧

| 字段 | 记录方式 |
|---|---|
| eval resolved config（含阈值） | `[自动]` eval_resolved_config.yaml |
| eval 使用的 checkpoint 路径 | `[自动]` metrics.json → experiment_record |
| n_rollouts | `[自动]` metrics.json → experiment_record |
| 各口径 success rate | `[自动]` rollout_manifest.json → experiment_record |
| mean failure counts | `[自动]` rollout_manifest.json → experiment_record |
| 本次实验假设/目的 | `[手动]` `--hypothesis` 参数 |
| 结果解读与结论 | `[手动]` `--notes` 参数 |

### 5.5 输出产物清单

训练侧（自动落盘到 `ckpt_dir/`）：
- `train_val_split.yaml`
- `resolved_config.yaml`
- `run_metadata.json`
- `dataset_stats.pkl`
- `loss_curve.png`
- `policy_best.ckpt`
- `policy_latest.ckpt`
- `policy_epoch_{n}_seed_{s}.ckpt`

评测侧（自动落盘到 `eval_results_dir/`）：
- `eval_resolved_config.yaml`
- `eval_run_metadata.json`
- `metrics.json`
- `results.csv`
- `rollout_manifest.json`
- `rollouts/rollout_XXX.jsonl`
- `rollouts/rollout_XXX_summary.json`

数据侧（自动落盘到 `dataset_dir/qc/`）：
- `summary.json`
- `episodes.csv`
- `episode_length_hist.png`
- `action_distribution.png`
- `state_ranges.png`

实验级记录（`tb-experiment-record` 生成）：
- `runs/experiments/<name>/experiment_record.json`
- `runs/experiments/<name>/experiment_record.md`
- `runs/experiments/experiment_registry.csv`

---

## 6. 实验记录工作流

每次正式训练 + 评测完成后，运行：

```bash
tb-experiment-record \
  --train-ckpt-dir  runs/ckpts/<run_name> \
  --eval-results-dir runs/eval/<run_name>/results \
  --name  "<实验名，参见第 4 节命名规范>" \
  --hypothesis "<本次实验想验证什么>" \
  --notes "<实际观察到的现象、结论、下一步建议>"
```

`hypothesis` 和 `notes` 的区别：
- `hypothesis`：实验前写，描述"我们期望通过这次实验验证什么假设"
- `notes`：实验后写，描述"实际观察到什么、结论是什么"

生成的 `experiment_registry.csv` 是横向比较表，当前记录列：

| 列 | 说明 |
|---|---|
| `experiment_name` | 实验唯一标识 |
| `train_best_epoch` / `train_best_val_loss` | 训练质量 |
| `n_rollouts` / `eval_ckpt_path` | eval 使用的 checkpoint 和规模 |
| `success_mode` | 主口径 |
| 各口径 success rate | `primary/legacy/final_hold/strict_final_hold/dump_complete_final_hold/strict_dump_complete` |
| `avg_return` / `avg_episode_len` | 整体 rollout 质量 |
| `avg_final_bucket_mass` | dump 完整性指标 |
| mean failure counts | `spill_before_target / hard_target_collision / unsafe_target_distance` |
| `hypothesis` / `notes` | 实验目的与结论 |

如果 `experiment_registry.csv` 的 schema 与当前代码不同步（增加了新字段但 header 没更新），用下面命令从现有 JSON 记录重建：

```bash
conda run -n aloha python3 -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from testbed.runtime.experiment_record import rewrite_experiment_registry

json_files = sorted(Path('runs/experiments').glob('*/experiment_record.json'))
records = [json.loads(p.read_text()) for p in json_files]
rewrite_experiment_registry(records, Path('runs/experiments/experiment_registry.csv'))
print('done, rows:', len(records))
"
```

---

## 7. 每次实验启动前检查

### 训练前

1. `python scripts/agx_smoke.py --strict` 能过
2. 新数据目录里的 episode 是当前 9D `env_state`
3. `task.dataset_dir` 和 `task.num_episodes` 已改到目标数据集
4. `chunk_size` 不大于 episode 实际有效长度
5. `ckpt_dir` 是新的 run 目录，不会覆盖旧实验
6. git commit 已经记录当前代码状态

### 评测前

1. 确认 eval 使用的 checkpoint 路径（`policy.ckpt_path`）
2. 确认 `success.mode` 与当前对比目标一致
3. 确认 `success.mass_thresh` / `hold_steps` / `residual_bucket_mass_thresh` 与上一轮一致（若做横向比较）
4. 确认 `eval.num_rollouts` 足够（当前建议 ≥ 10）
5. `eval_results_dir` 是新的目录，不会覆盖旧结果

### 记录前

1. 确认 `--hypothesis` 已填写（这次实验想验证什么）
2. 确认 `--notes` 已填写（实际观察到的结果和结论）
3. 确认 `--name` 符合第 4 节命名规范
4. 运行 `tb-experiment-record`，检查 `experiment_registry.csv` 新行是否合理

---

## 8. Trainer 真实行为（参考）

- 验证由 `val_every` 控制，但首个 epoch 和最后一个 epoch 一定会验证
- `policy_latest.ckpt` 由 `save_latest_every` 控制，训练结束时额外写一次
- `policy_epoch_{n}_seed_{s}.ckpt` 由 `checkpoint_every` 控制
- 训练曲线图由 `plot_every` 控制
- 如果 `keep_only_best_ckpt: true`，trainer 会在 `policy_best.ckpt`
  写入后删除 `policy_epoch_*_seed_*.ckpt`、`policy_latest.ckpt` 和
  `policy_last.ckpt`，只保留 best checkpoint 与 metadata/曲线文件。
- 对 image-VDS 中间数据，使用 `tb-materialize-vds --recursive --workers N`
  可以把 primitive VDS 并行落成训练用 copy；建议只在 primitive/window
  级数据上开多 worker，不要对完整 20000-step raw relabel 直接并行复制。
- 训练结束后的空间回收使用 `tb-cleanup-training-artifacts --delete`。V2.4
  hindsight pipeline 在 `--train` 成功后默认自动调用它：删除可由
  primitive VDS 重建的 materialized primitive copy、清掉指向该 copy 的
  current symlink，并扫描本次 dig/return `ckpt_dir` 删除非
  `policy_best.ckpt` 的 checkpoint。需要保留训练 copy 做诊断时，用
  `--no-cleanup-after-train` 显式关闭。
- AMP：`amp_dtype=auto` 时 CUDA 优先 bf16，否则回退 fp16；fp16 路径启用 GradScaler

---

## 附录 A：历史验证记录

### 2026-03-26 smoke 验证结论

这轮工作重点是确认新增的训练/评测/数据记录能力已经落地，不是比较算法性能。

已确认工作正常：
- 训练侧：`train_val_split.yaml`、`resolved_config.yaml`、`run_metadata.json`
- 数据侧：`tb-dataset-qc`、demo-level metadata、录制成功即结束
- 评测侧：`metrics.json`、`results.csv`、`rollout_manifest.json`、rollout 日志

当时的 `0/2` success 是合理的（demo 数量极小、训练规模极小），rollout 日志显示失败模式是"没有进入 good dig start"，不是接口问题。

重要运行时约束（本轮确认）：
- `1920×1060` 级别图像会让 step-ack 路径明显变慢，AGX 窗口发抖
- 录制、训练、评测必须使用同一套固定图像分辨率

### 2026-03-27 首轮 fulltest baseline 结论

第一轮正式 baseline（20 条 demo，`ACT(qpos)`）主要结论：
- 训练本身收敛，ACT 学到了任务骨架
- policy 能挖、能运，但 dump 质量不足
- 典型失败模式：模仿了 teleop 中的减速/纠偏反向拨杆，而不是理解"为什么此刻需要减速"
- 这指向末端速度控制问题，优先尝试 `qpos + qvel` 对照实验

新增的五套 success 口径（`legacy_any` / `final_hold` / `strict_final_hold` / `dump_complete_final_hold` / `strict_dump_complete`）在本轮已完成接入与验证。推荐主口径切换为 `dump_complete_final_hold`。

### 2026-03-31 fulltest `qpos+qvel` 对照结论

第一轮 `qpos+qvel` 对照的主要结论：
- 主口径 `dump_complete_final_hold` 成功率从 `30%` 提升到 `60%`
- `hard_target_collision` 明显下降
- `unsafe_target_distance` 明显下降
- 速度信息对 dump phase 的稳定性有直接帮助

这轮实验证明 `qvel` 不是无效附加项，它至少在 `fulltest` 数据集上有明确收益。

### 2026-04-02 rerecord `v1` baseline 结论

第一轮 `v1(qpos)` 业务 baseline 的主要结论：
- 数据集 `data/agx_teleop_v1/` 已经具备 `30` 条 success demo
- 主口径 `dump_complete_final_hold` 下达到 `10 / 10` success
- 当前更像“完成质量问题”而不是“可学习性问题”

当前最重要的残留问题不是 success rate，而是：
- `strict_dump_complete` 仍然是 `0%`
- `spill_before_target` 仍然偏高

因此，下一轮实验设计的重点应该放在严格口径 failure analysis，而不是重新证明 baseline 能否学会任务。
