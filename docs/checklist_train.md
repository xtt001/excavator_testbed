# AGX ACT 实验就绪检查清单

本文档分两层：

- **系统就绪层**（§1–§9）：搭建 testbed 期间检查一次，之后只在系统有重大变更时重查
- **每轮实验层**（§10）：每次正式实验前必须过一遍

---

## 系统就绪层

以下各节用于确认 testbed 的基础能力是否具备。
标记 `[x]` 表示已验证，`[ ]` 表示待完成。

---

## 1. 环境与 episode 控制

### 重置与初始化

- [x] 环境 reset 稳定、可重复
- [x] 初始挖掘机姿态对 baseline 实验是确定性的
- [ ] 土堆 / 目标倒土区初始化对 baseline 实验是确定性的
- [x] 相机位姿固定并已记录
- [ ] 环境中的随机性可通过配置开关控制

### Episode 生命周期

- [x] episode 开始条件明确
- [x] episode 结束条件明确（success / max_steps / discard）
- [x] timeout 条件明确
- [x] success 条件明确（`deposited_mass_in_target_box_kg >= mass_thresh` 持续 hold_steps）
- [x] failure 条件明确（hard collision / spill_before_target 等）
- [x] episode ID 唯一，所有相关产物都写入此 ID

### 时序

- [x] 控制频率固定已知
- [x] 观测频率固定已知
- [x] 每个 observation-action pair 都有 timestamp
- [ ] teleop 延迟已测量或估计

---

## 2. 观测管道

### 观测定义

- [x] baseline 观测空间已明确定义（`images + qpos`）
- [x] 观测的 key 名和维度已记录
- [x] 运行时打印并检查了观测维度
- [x] 训练时和 eval 时的观测接口保证一致
- [x] `qvel` 已录入 HDF5，`ACT(qpos+qvel)` 对照实验路径已就位
- [x] baseline / 对照实验分工明确：
  - baseline：`ACT(qpos)`
  - 对照：`ACT(qpos+qvel)`

### 传感器合理性检查

- [x] 关节角度读数正确
- [x] 关节速度读数正确
- [x] 相机图像已同步、无过期帧
- [ ] bucket 姿态正确
- [ ] end-effector / bucket tip 位置正确
- [ ] 目标区域状态正确
- [ ] 土相关状态（如使用）正确

### 日志

- [x] 原始观测可按 timestep 保存
- [x] 缺失 / NaN / 无效观测会触发 warning

---

## 3. 动作管道

### 动作定义

- [x] action space 已明确记录（4D speed cmd）
- [x] action 维度运行时打印并检查
- [ ] action bounds 已定义
- [ ] action clipping 行为已定义
- [x] action smoothing / filtering 已明确（当前无 filtering）

### 执行合理性检查

- [x] 指令动作能产生预期挖掘机行为
- [x] teleop action 格式和 policy action 格式一致
- [x] 录制动作和回放动作在同一 scale / convention 下

### 日志

- [x] 每 timestep 记录执行的 action
- [x] 突然的 action spike 可被检测（rollout 日志中可见）

---

## 4. Demo 录制管道

### Metadata

- [x] 每条 demo 存储 episode ID
- [x] 每条 demo 存储 operator ID
- [x] 每条 demo 存储 task 版本
- [x] 每条 demo 存储 timestamp
- [x] 每条 demo 存储 config snapshot
- [x] 每条 demo 存储 observation / action 定义

### 质量控制

- [x] 每条 demo 可以回放
- [x] 每条 demo 可标记 success / failure
- [x] 破损 demo 可干净地排除
- [ ] 极短或截断的 demo 可自动标记

### 视频

- [ ] 每条 demo 保存 rollout 视频
- [ ] 视频与 timestep index 同步
- [ ] 训练前可方便地检视 demo 视频

---

## 5. 数据集工具

### 数据集检查

- [x] `tb-dataset-qc`：打印数据集统计
- [x] episode 长度分布
- [x] action distribution
- [x] observation ranges
- [x] NaN / inf / 缺失值检测

### 数据集切分

- [x] train / val split 明确保存（`train_val_split.yaml`）
- [x] split 是 episode 级的，不是随机 timestep 级的
- [x] 可用固定 seed 复现
- [x] baseline 使用 frozen split

### 可视化

- [x] action 轨迹图（`action_distribution.png`）
- [x] episode 长度分布图（`episode_length_hist.png`）
- [x] 关键状态轨迹图（`state_ranges.png`）

---

## 6. 训练管道

### 可复现性

- [x] 每次 run 保存完整 config（`resolved_config.yaml`）
- [x] random seed 已保存
- [x] Repo A git commit 已保存（`run_metadata.json`）
- [x] checkpoint 命名规则一致
- [x] 输出目录命名规则一致（待推行第 4 节命名规范）

### 日志

- [x] train loss 已记录
- [x] validation loss 已记录
- [x] learning rate 已记录
- [x] KL loss 已记录
- [x] checkpoint 保存事件已记录

### 健全性测试

- [ ] 模型可以在少量 demo 上过拟合
- [x] 单个训练 batch 可以端到端跑通无报错
- [x] 早期 checkpoint 的 rollout 可以无接口错误运行

---

## 7. Rollout 评测管道

### Eval 协议

- [x] eval 环境配置对 baseline 固定
- [x] eval 使用的 seed 已固定并保存
- [x] 每个 checkpoint 评测的 rollout 数已固定
- [x] eval 使用的观测接口与训练一致
- [x] eval 使用的 action 接口与 deployment 一致

### Success 指标

- [x] 五套 success 口径已定义（见 `training_setup.md` §3.4）
- [x] 推荐主口径：`dump_complete_final_hold`
- [x] timeout 已定义（`task.episode_len = 1000`）
- [ ] safety violation / 无效行为已明确定义

### 每次 rollout 输出

- [x] rollout 日志（`rollout_XXX.jsonl`）
- [x] rollout summary（`rollout_XXX_summary.json`）
- [x] 最终 success / failure 标签
- [ ] rollout 视频
- [ ] 关键 event marker

---

## 8. 失败分析支持

### 失败分类法

失败类型已预定义，分析时对照使用：

- 无法正确入土（not entering soil correctly）
- 入土但无法铲料（enters soil but fails to scoop）
- 铲料后在旋转过程中撒料（loses material before dump）
- 旋转轨迹偏差（swing trajectory wrong）
- 到达倒料区但无法卸料（reaches dump zone but fails to unload）
- 动作抖动 / 振荡（action jitter / oscillation）
- 后期漂移 / 累积误差（late-stage drift）
- rollout 发散但训练 loss 很低（rollout diverges despite low train loss）

### 分析工具

- [x] `rollout_XXX.jsonl`：逐 timestep 状态 / 动作 / reward phase
- [x] `tb-dataset-qc` plots：action distribution / state ranges
- [ ] 快速浏览失败 rollout 的工具
- [ ] 成功 vs 失败 rollout 对比工具
- [ ] rollout 视频与 timestep 日志对齐工具

---

## 9. Debug 可视化

### 必须有的

- [ ] 视频上显示 episode ID
- [ ] 视频上显示 timestep
- [ ] 视频上显示 success / failure 状态
- [ ] 视频上显示当前 phase（如可用）

### 锦上添花

- [ ] 专家 vs policy rollout 并排对比
- [ ] 成功 vs 失败 rollout 并排对比
- [ ] 按 timestep 拖动视频
- [ ] 多摄像头视角查看 rollout

---

## 10. 每轮实验启动前最小清单

**每次跑正式实验前过一遍，不要跳步。**

### 10.1 环境确认

- [ ] `tb-agx-smoke --strict` 通过（或等效的 live 连通验证）
- [ ] 当前代码已 git commit，知道 Repo A 的 commit hash
- [ ] 知道对应的 Repo B / Repo C commit（手动记录到 `--notes`）

### 10.2 训练前

- [ ] `task.dataset_dir` 指向正确的数据目录
- [ ] `task.num_episodes` 与目录内实际 episode 数一致
- [ ] 数据目录已跑过 `tb-dataset-qc`，QC 结果无异常
- [ ] `chunk_size` ≤ episode 最短有效长度
- [ ] `train.ckpt_dir` 是新的目录，不会覆盖旧实验
- [ ] 实验名符合命名规范（见 `training_setup.md` §4）

### 10.3 评测前

- [ ] 确认 `policy.ckpt_path`（用 best？latest？特定 epoch？）
- [ ] 确认 `success.mode` 与这次对比目标一致
- [ ] 确认 `success.mass_thresh` / `hold_steps` / `residual_bucket_mass_thresh` 与对照组一致
- [ ] 确认 `eval.num_rollouts` ≥ 10
- [ ] `eval.results_dir` 是新的目录，不会覆盖旧结果

### 10.4 记录前

- [ ] 实验假设（`--hypothesis`）：**实验前**写，描述"想验证什么"
- [ ] 实验备注（`--notes`）：**实验后**写，描述"观察到什么、结论是什么"
- [ ] 实验名（`--name`）：符合第 4 节命名规范
- [ ] 运行 `tb-experiment-record`，检查 `experiment_registry.csv` 新行合理

### 10.5 结果可解释性检查

跑完之后，能回答下面所有问题才算这一轮合格：

- demo 数据干净吗？（`tb-dataset-qc` 结果）
- 观测正确吗？（replay QA 或 rollout 日志）
- 动作执行符合预期吗？（rollout 日志 action trace）
- 训练稳定吗？（loss curve）
- rollout 是在哪个阶段失败的？（failure taxonomy）
- 失败更像是策略问题还是 testbed/接口问题？（失效归因框架）
