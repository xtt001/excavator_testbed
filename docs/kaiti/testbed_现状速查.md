# Testbed 现状速查（开题汇报用）

> 整理时间：2026-05-03  
> 信息来源：Repo A（excavator_testbed）、Repo B（AGXUnity_Excavator）、Repo C（sim-protocol）

---

## 1. AGXUnity 场景已实现的任务

**任务名称**：`agx_excavation_teleop`（V0 固定位置挖掘任务）

**任务定义**：

> 在固定重置场景中，使用 4D 臂关节（swing / boom / stick / bucket）控制挖掘机，完成一个或多个"挖土 → 转运 → 卸料 → 保留"循环，将足够的物料稳定保留在当前激活的卸料目标中。

**具体实现内容**：

- 固定初始位姿的挖掘机 + 固定土堆 + 场景 DigArea 引导区（可视化轮廓）
- 两种卸料目标（运行时路由切换）：
  - `ContainerBox`（静态刚体箱）
  - `TruckBed`（卡车车斗，含完整碰撞体与质量测量）
- 4D 动作空间：`[swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]`，不含行驶/转向
- FPV 相机图像实时导出（step-ack 协议打包传回 Python）
- 质量信号：铲斗装载量、累计挖出量、目标中沉积量、reset 相对净沉积量
- 距离信号：铲斗到目标距离、铲斗到 DigArea 距离、铲斗入土深度、水平对准距离、铲斗高于目标顶部高度
- 碰撞信号：目标硬碰撞累计次数、当步最大接触法力
- 场景重置：地形、位姿、质量计数器、约束状态全部还原

**当前成功条件**（Stage-1 配置）：

```
deposited_mass_in_target_box_kg >= 300.0 kg
residual_bucket_mass_kg <= 100.0 kg
连续保持 25 步
```

**当前多循环录制流程**（V2.1 Stage-1 主线）：

- 自然多循环遥操作（无固定"准备姿态"停止点）
- 检测到第 3 次 `dump_end` 后停止录制
- `max_steps = 4000` 仅作保险上限

---

## 2. 遥操作输入方式

**主要输入：手柄（Joystick / Gamepad）**，兼支持键盘

### 手柄配置（典型 RQ1 实验配置）

| 参数 | 值 |
|---|---|
| 轴映射 `axis_map` | `[0, 1, 1, 0]` |
| 设备分配 `joystick_ids` | `[1, 0, 1, 0]`（双摇杆，左杆控 swing/boom，右杆控 stick/bucket） |
| 反向 `invert` | `[false, false, false, false]`（各轴可独立配置） |
| 死区 `deadzone` | `0.05` |
| 缩放 `scale` | `[0.6, 0.3, 0.7, 0.7]`（各轴独立） |
| 硬限幅 `clip` | `1.0` |
| 重置按钮 | 按键 10（丢弃当前 episode 并重置） |

**Response Profile（平滑曲线）**：

| 参数 | 值 |
|---|---|
| attack_rate | 4.0 |
| release_rate | 6.0 |
| recenter_rate | 7.0 |
| exponent | 1.0 |

### 键盘模式

- 配置 `key_speed` 控制单步命令幅值（默认 0.5）
- 通过 pygame 事件驱动（Q 键退出会话，D 键丢弃当前 episode）

---

## 3. 视频采集方式

**视角**：第一人称视角（FPV），相机挂载在挖掘机驾驶室位置

**采集链路**：

```
Unity FPV 相机 → AGX step-ack 二进制 TCP 协议
→ raw RGB bytes（行优先，top-to-bottom，RGB 通道）
→ Python AGXSimBackend 解包
→ HDF5 /observations/images/fpv (T, H, W, 3) uint8
```

**分辨率**：

| 实验条件 | Unity 渲染分辨率 | HDF5 存储分辨率 | 操作员看到 |
|---|---|---|---|
| 基准（fullres） | 720×480 | 720×480 | 720×480 |
| 低分辨率（lowres） | 720×480 | 240×160 | 240×160（Python 侧 3× 下采样后展示） |

> **注**：低分辨率条件下 Unity 仍以 720×480 渲染，Python 侧下采样后同时用于操作员显示和 HDF5 保存，操作员在 Python 窗口（而非 Unity 编辑器）看到的是 240×160 的像素化图像。

**帧率**：50 fps（与控制频率同步，每个 step-ack 周期对应一帧）

**协议元数据**（GET_INFO_RESP 广播）：

- `pixel_format = "raw_rgb"`
- `row_order = "top_to_bottom"`
- `camera_names = ["fpv"]`
- 分辨率和帧率由 Unity 运行时广播，非固定全局常量

---

## 4. 网络扰动注入方式

**机制**：Linux `tc netem`（流量控制）在 loopback 网络接口注入对称时延

**脚本**：`scripts/inject_delay.sh`

```bash
# 注入 100ms 单向时延
sudo ./scripts/inject_delay.sh 100

# 注入 100ms 时延 + 10ms 抖动（正态分布）
sudo ./scripts/inject_delay.sh 100 10

# 清除所有 netem 规则
sudo ./scripts/inject_delay.sh 0
```

**原理**：Unity 和 Python 运行在同一台机器，对 `lo`（loopback）注入对称时延，双向各加 delay_ms，实际 RTT 约为注入值的 2 倍。

**实验条件（RQ1）**：

| 条件 | 注入单向时延 | 实测 step interval 均值 |
|---|---|---|
| c0_baseline | 0 ms | ~27 ms |
| c25ms | 25 ms | ~74 ms |
| c50ms | 50 ms | ~126 ms |
| c100ms | 100 ms | ~227 ms |

**当前实现状态**：

| 扰动类型 | 状态 |
|---|---|
| 时延注入（tc netem delay） | ✅ 已实现并用于 RQ1 实验 |
| 抖动注入（tc netem jitter） | ✅ 脚本支持，配置文件有 `jitter_inject_ms` 字段 |
| 丢包注入 | ⚠️ 配置文件有 `loss_rate` 字段，但尚无对应注入脚本 |
| 码率控制 | ⚠️ 配置文件有 `bitrate` 字段（用于 trace 记录），尚未实际限速 |

**时延观测（ControlProbe / LatencySession）**：

挂在 step-ack 客户端旁的可插拔探针，对每个 step() 打点记录：
- `cmd_send_ns` / `cmd_recv_ns` / `round_trip_ms`
- Unity 侧分段时戳（请求到达 → 出队 → 物理完成 → 图像就绪 → 响应发出）
- 图像帧大小 `payload_bytes`、分辨率 `image_w/h`

---

## 5. HDF5 当前保存字段

**Schema 版本**：`v1.1`（`sim-protocol/schema.md`）

### 文件结构

```
episode_XXXX.hdf5
├── metadata/              ← HDF5 attributes
├── timestamps/
│   ├── step_id            (T,) int64
│   └── step_ns            (T,) int64  ← 墙钟时间戳
├── action_source/
│   ├── type               (T,) str    ← "teleop" / "policy" / "scripted"
│   └── id                 (T,) str    ← "joystick" / "keyboard" / policy 标识
├── observations/
│   ├── qpos               (T, 4) float32  ← 归一化关节位置
│   ├── qvel               (T, 4) float32  ← 关节速度
│   ├── env_state          (T, 13) float32 ← 13维环境状态
│   └── images/
│       └── fpv            (T, H, W, 3) uint8  ← RGB 图像
├── action                 (T, 4) float32  ← 归一化动作命令
├── rewards                (T,) float32
└── v2/                    ← 可选，Repo A Stage-1 扩展
```

### qpos (T, 4) — 关节位置（归一化）

| 列 | 含义 |
|---|---|
| 0 | `swing_position_norm` |
| 1 | `boom_position_norm` |
| 2 | `stick_position_norm` |
| 3 | `bucket_position_norm` |

### qvel (T, 4) — 关节速度

| 列 | 含义 |
|---|---|
| 0 | `swing_speed` |
| 1 | `boom_speed` |
| 2 | `stick_speed` |
| 3 | `bucket_speed` |

### env_state (T, 13) — 环境状态

| 列 | 字段名 | 说明 |
|---|---|---|
| 0 | `mass_in_bucket_kg` | 铲斗当前载土质量 |
| 1 | `excavated_mass_kg` | 累计已挖出质量 |
| 2 | `mass_in_target_box_kg` | 当前激活目标中的总质量 |
| 3 | `deposited_mass_in_target_box_kg` | reset 相对净沉积质量（任务奖励主信号） |
| 4 | `min_distance_to_target_m` | 铲斗到目标的近似最小距离（诊断用） |
| 5 | `target_hard_collision_count` | 目标硬碰撞累计次数（episode 内） |
| 6 | `target_contact_max_normal_force_n` | 当步最大接触法力（N） |
| 7 | `min_distance_to_dig_area_m` | 铲斗到 DigArea 的近似最小距离 |
| 8 | `bucket_depth_below_dig_area_plane_m` | 铲斗入土深度（低于 DigArea 平面） |
| 9 | `target_horizontal_distance_m` | 铲斗与目标水平对准距离 |
| 10 | `bucket_height_above_target_rim_m` | 铲斗底部高于目标顶部的高度 |
| 11 | `bucket_over_target_footprint_mask` | 铲斗足迹是否覆盖目标足迹（0/1） |
| 12 | `dump_clearance_ok_mask` | 卸料姿态是否满足目标间隙要求（0/1） |

### action (T, 4) — 动作命令（归一化至 [-1, 1]）

| 列 | 含义 |
|---|---|
| 0 | `swing_speed_cmd` |
| 1 | `boom_speed_cmd` |
| 2 | `stick_speed_cmd` |
| 3 | `bucket_speed_cmd` |

### rewards (T,) — 任务奖励

Repo A 计算的 AGX 挖掘任务复合奖励（含阶段奖励和碰撞惩罚），**不是** Unity wire 字段 `deposited_mass_in_target_box_kg` 的原始镜像。

### metadata 主要属性

```
schema_version, task_name, sim_backend, seed, param_version, timestamp,
control_hz (50), dt (0.02), action_semantics, camera_names, image_format,
protocol_version, camera_width, camera_height, camera_fps, camera_row_order,
operator_id, session_id, notes, record_config_yaml,
teleop_input, deadzone, scale, limit, axis_map, joystick_ids, invert,
response_profile_*, reset_mode, success, n_steps, scenario_id, recording_mode, ...
```

---

## 6. ACT 训练代码输入格式与 Rollout 流程

### 输入格式

**低维 proprio**（可配置 `low_dim_keys`，默认仅 `qpos`）：

```
proprio: (B, Nq)  float32
  - 默认 Nq = 4（qpos），可扩展为 qpos+qvel = 8
  - 使用 dataset_stats.pkl 中的 proprio_mean / proprio_std 归一化
```

**图像**（可配置 `camera_names`，默认 `["fpv"]`）：

```
image: (B, n_cams, C, H, W)  float32
  - 接受 channel-first [0,1] 或 channel-last uint8 两种格式（自动转换）
  - ImageNet 均值/标准差归一化（torchvision Normalize）
```

### 模型结构

- DETR-VAE（Transformer + VAE），来自 ACT 原论文
- 输出：action chunk `(B, C, Na)`，其中 C = `num_queries`（chunk size），Na = 4
- 训练损失：`L1 loss + KL divergence × kl_weight`（默认 kl_weight = 10）

### Rollout 流程（推理时）

**非 temporal aggregation 模式**（默认）：

```
每隔 num_queries 步查询一次模型 → 缓存整个 chunk
→ 在 chunk 窗口内按位置逐步执行对应动作
→ 完成一个 chunk 后再重新查询
```

**Temporal aggregation 模式**（可选，`temporal_agg=True`）：

```
每步都查询模型 → 将当前 chunk 写入历史累积张量 (T, T+C, Na)
→ 对所有覆盖当前时刻的历史预测做指数加权平均（衰减系数 k=0.01）
→ 输出加权均值作为当前步动作
```

**动作反归一化**：

```python
action = action_normalized * norm_stats["action_std"] + norm_stats["action_mean"]
```

### 训练流程要点

- 检查点格式：`{model_state_dict, optimizer_state_dict, epoch, min_val_loss, config}`
- 验证集最优模型保存为 `policy_best.ckpt`
- 支持 `resume_ckpt` 断点续训
- 支持 AMP（混合精度）

---

## 7. 当前已完成的实验图及对应指标

共 5 组实验，已整理归档于 `docs/kaiti/figures/exp{1..5}_*/`。

---

### 实验一：链路时延对遥操作示教数据质量的影响

**数据来源**：真实 teleop，4 组时延条件（0 / 25 / 50 / 100 ms 单向注入）

**核心图**：`figures/exp1_latency_data_quality/proof_summary.png`

**6 维指标**：

| 指标 | 含义 | 趋势 |
|---|---|---|
| Step-Ack RTT Distribution | 实测控制回路间隔分布 | 四组明显分开（27 / 74 / 126 / 227 ms） |
| Action Jerk | 动作突变程度 | 随时延单调上升 |
| Information Density | 每条 episode 的 step 数 | 791 → 271 → 167 → 92 |
| Action Reversal Rate | 方向反转频率 | 0.147 → 0.304 → 0.362 → 0.327 |
| Task Success Rate | Teleop 成功率 | 100% / 100% → 20% → 0% |
| Avg Episode Duration | 平均完成时长 | 高时延组趋近上限 20 s |

---

### 实验二：视觉分辨率对人类操作与模型学习的差异影响

**数据来源**：真实 teleop + 真实 ACT 训练评估（fullres 720×480 vs lowres 240×160）

**核心图**：
- `figures/exp2_resolution/resolution_evidence_summary.png`（三层证据汇总）
- `figures/exp2_resolution/resolution_policy_behavior.png`（策略行为过程对比）

**关键数据点**：

| 指标 | Fullres | Lowres |
|---|---|---|
| Teleop 成功率 | 100% | 100% |
| 平均成功步数 | 791 步 | 896 步 |
| BC 验证损失 | 0.236 | 0.261 |
| **ACT 评估成功率** | **30%** | **0%** |
| Subtask：dig ≥ 300 kg | 100% | 100% |
| Subtask：bucket ≤ 100 kg | >0% | **0%** |

**行为过程 4 维信号**：Reach Dig Area / Load Bucket / Move Toward Target / Actually Deposit Soil

---

### 实验三：不同链路退化条件下的阶段级失败分析

**数据来源**：真实 ACT rollout 50 次（4 时延条件 × 10 次 + lowres 对照）

**核心图**：`figures/exp3_behavioral_failure/behavioral_analysis.png`

**6 子图指标**：

| 子图 | 信号 |
|---|---|
| Mass in Bucket | 铲斗装载质量随步数变化 |
| Distance to Dig Area | 铲斗到 DigArea 距离 |
| Excavated Mass | 累计挖出质量 |
| Deposited Mass | 目标中沉积质量 |
| Swing Joint Trajectory | swing 关节命令轨迹 |
| Task Phase Distribution | idle / loading / approaching / depositing / retained_success 分布 |

**关键结论**（catastrophic failure cliff）：

| 条件 | 失败位置 |
|---|---|
| 0 ms fullres | 30% 成功；70% 失败在 dump 阶段 |
| 0 ms lowres | 100% 失败在 dump（铲斗中残留大量土） |
| 25 / 50 / 100 ms | 100% 失败在 dig 阶段（连挖掘都没学会） |

---

### 实验四：ROI 语义保护可行性验证

**数据来源**：真实 teleop 帧 + 真实 JPEG 压缩（ROI-protected vs Uniform，等比特预算对比）

**脚本**：`scripts/exp4_roi_protection.py`

**核心图**：
- `figures/exp4_roi_protection/roi_visual_comparison.png`（视觉对比）
- `figures/exp4_roi_protection/roi_quality_metrics.png`（ROI 区域 PSNR / SSIM / Sobel 边缘强度）
- `figures/exp4_roi_protection/roi_downstream_impact.png`（预测下游 ACT 成功率）

**真实计算指标（等比特预算下）**：

| 任务阶段 | Uniform PSNR | ROI-protected PSNR | 提升 |
|---|---|---|---|
| Loading (digging) | 30.7 dB | 34.0 dB | +3.3 dB |
| Transfer | 29.4 dB | 32.2 dB | +2.8 dB |
| Approach target | 31.0 dB | 35.6 dB | +4.5 dB |

**预测下游 ACT 成功率**（图中标注 predicted）：全局重压缩 ≈ 3%，ROI-protected ≈ 22%

---

### 实验五：AR 预测显示可行性验证

**数据来源**：真实 100 ms 延迟帧 + AR mockup 叠加 + 文献基准外推

**脚本**：`scripts/exp5_ar_prediction.py`

**核心图**：
- `figures/exp5_ar_prediction/ar_mockup_screenshots.png`（AR 界面对比）
- `figures/exp5_ar_prediction/ar_trajectory.png`（典型动作时序对比）
- `figures/exp5_ar_prediction/ar_predicted_metrics.png`（行为指标预测对比）

**预测指标（100 ms RTT 条件，图中标注 predicted）**：

| 指标 | 基准（无 AR） | AR 开启（预测） | 变化 |
|---|---|---|---|
| Action Jerk | 基准 | 预测下降 49% | ↓ |
| Reversal Rate | 基准 | 预测下降 45% | ↓ |
| Idle Ratio | 基准 | 预测下降 53% | ↓ |
| Task time | 基准 | 预测下降 17% | ↓ |

---

## 附：系统整体架构

```
Repo B (AGXUnity_Excavator)
  └─ Unity/C# 场景：AGX 物理、挖掘机、step-ack server、FPV 相机
       ↕  二进制 TCP（GET_INFO / RESET / STEP）
Repo A (excavator_testbed)
  ├─ 遥操作录制 → HDF5 落盘
  ├─ ACT 离线训练 → checkpoint
  ├─ Live eval rollout → metrics / videos
  └─ latency_module（可插拔观测层）
       ├─ ControlProbe：step-ack 打点
       └─ LatencySession：trace 导出 / 分析图

Repo C (sim-protocol)
  └─ 协议格式、env_state 语义、HDF5 schema — 两仓共享 source of truth
```
