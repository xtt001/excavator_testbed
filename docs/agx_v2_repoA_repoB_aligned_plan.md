# AGX 挖掘机 V2 技术方案与实验矩阵

> 实现状态更新（2026-04-15）  
> Repo A phase-1 已按本文主线接入：`/v2` add-only extension、`tb-label-v2`、`goal_tokens` 低维通路、`teleop.stop_mode=dump_plus_ready`、continuity metrics、`scenario_id` backend 透传。  
> Repo B phase-1 当前只实现最小 `scenario_id -> preset` 路径，preset 只覆盖 `reset_terrain / reset_pose / ActiveTargetIndex`，不包含 `ExcavatorPoseOffset`、`DigAreaOffset` 或 `DigAreaYawDeg`。  
> `aux heads` 仍延后到下一子阶段，不属于本轮代码范围。

## 1. 这版方案的对齐前提

这份方案按三个现状来设计。

第一，Repo A 当前主线已经固定在 `teleop_v1 / act_agx_v1 / eval_agx_v1` 这组入口上，训练和评测主线还是 `agx_excavation_teleop`，动作空间还是 4 维臂控，低维输入主线还是 `qpos`，`qvel` 目前在 `fulltest` 上作为正式对照线存在。

第二，Repo B 当前真值源还是二进制 step-ack 协议，动作语义是 `actuator_speed_cmd`，观测主合同是 `qpos / qvel / env_state / fpv`。Repo B 内部已经有更丰富的量，比如 base pose world、bucket pose world、当前 active target 等，但这些量还没有进入 Repo A 当前 live wire。

第三，Repo C 当前边界已经很明确。live 协议和 offline HDF5 schema 是分开的。schema 规则是 add-only，所以 V2 需要的新标签应该加在新 group 或新 optional attr 下，不应该破坏当前 v1/v0 读写兼容。

因此，V2 第一阶段不要先升协议，不要先改 action 维度，也不要先要求 Unity 每步导出世界坐标。最稳的路径是先在 Repo A 内部补齐目标条件、phase 标签、多铲评测和连续性指标，然后再用 Repo B 现有的 reset、target switching、DigArea、collision 量测能力做受控扩展。

---

## 2. V2 的系统边界

### 2.1 保持不变的部分

- `task_name` 第一阶段继续使用 `agx_excavation_teleop`
- live action 继续保持 4 维 `actuator_speed_cmd`
- Repo C `agx-sim/v0` 不先改版本
- HDF5 主体结构继续沿用 v1.1 的 `metadata / timestamps / action_source / observations / action / rewards`
- Unity 的主 reset 路径继续走 `SceneResetService.ResetScene(resetTerrain, resetPose)`

### 2.2 V2 新增但不破坏兼容的部分

- Repo A 新增 V2 配置族
- Repo A 新增 `/v2/...` 离线标签组
- Repo A 新增 goal-conditioned ACT 路径
- Repo A evaluator 新增连续性与多铲指标
- Repo B 可选新增 scenario preset 应用逻辑，但不要求第一阶段就把新字段加到 wire

---

## 3. 先给结论，V2 的最小可落地结构

### 3.1 最小技能单元

V2 的 atomic primitive 直接定义成完整一铲：

`ready -> dig -> transport -> dump -> ready`

不是 `scoop -> dump -> retain`，而是把 return-ready 也纳入 primitive 完成条件。原因很简单，当前 Repo B 的场景合同只要求 retained mass 成功，不保证结束姿态适合作为下一铲起点，所以 V2 必须把“归位到可复用状态”变成 Repo A 侧显式建模和显式评测的一部分。

### 3.2 上层和 ACT 的接口

第一版不要让上层给连续整条轨迹。上层只给局部作业意图，低层 ACT 负责把这一铲做完。

建议统一成下面两层表达。

#### 供分析与日志使用的结构化目标

```python
PlannerGoal = {
    "cycle_id": int,
    "scenario_id": str,
    "src_patch_id": int,
    "dst_target_id": int,
    "ready_anchor_id": int,
    "cut_depth_class": int,
    "fill_target_class": int,
    "lookahead_next_src_patch_id": int,
    "max_cycle_steps": int,
}
```

#### 真正喂给 ACT 的低维 goal token

```python
goal_tokens = [
    src_u_norm,
    src_v_norm,
    dst_target_norm,
    ready_anchor_norm,
    cut_depth_norm,
    next_src_u_norm,
    next_src_v_norm,
    has_lookahead,
]
```

这里的关键点有三条。

1. `src_patch_id` 和 `lookahead_next_src_patch_id` 主要用于日志、评测和规则式高层。
2. 真正进模型的是 `goal_tokens`，也就是归一化后的局部目标参数，而不是 patch 整数 id。
3. 这样做可以最小化对 Repo A 当前 `low_dim_keys -> proprio concat` 结构的改动。

### 3.3 ready anchor 的定义

第一版 ready anchor 不要用世界坐标定义，而要用 `qpos` 模板定义。因为 Repo B 内部虽然能拿到 base pose world 和 bucket pose world，但当前 live 协议并没有把它们送到 Repo A。

建议先做 3 个 anchor class。

- `anchor_left`
- `anchor_mid`
- `anchor_right`

每个 anchor 用一组 4 维 `qpos` 模板和容差来定义。

```python
ReadyAnchor = {
    "anchor_id": 0,
    "qpos_ref": [0.52, 0.41, 0.63, 0.28],
    "qpos_tol": [0.06, 0.05, 0.05, 0.05],
    "hold_steps": 10,
}
```

这样可以直接接上 Repo A 当前 policy、dataset、eval 的输入输出定义，也能自然回答“上一铲和下一铲怎么接”。

当前 phase-1 实现里，Repo B 侧已经补了两层操作员提示：

- HUD `Ready Anchor Guide`：显示当前 `qpos`、`qpos_ref`、逐轴剩余偏差和颜色状态
- 场景 3D `ReadyAnchorWorldMarker`：进入 Play Mode 后会先用当前 ready / reset pose 的 bucket 世界位置做 bootstrap 标记，首次真正命中 ready anchor 后再升级为 confirmed 标记，并连线到当前 bucket

另外，当前 teleop 录制 stop gate 已经专门为人工操作放宽到 `anchor_error <= 1.35`；
`/v2` 里仍然保留原始连续 `anchor_error_l1`，后处理和分析不丢精度。

这样录制时不需要靠记忆 `qpos_ref` 数值回位。

---

## 4. Repo A 的具体改法

## 4.1 配置层

保持当前三类入口不变，只新增 V2 配置族。

建议新增这些文件。

```text
testbed/configs/
  teleop_v2_cycle_s0.yaml
  teleop_v2_cycle_s1_pose_jitter.yaml
  act_agx_v2_cycle_qpos.yaml
  act_agx_v2_cycle_qvel.yaml
  act_agx_v2_gcact.yaml
  eval_agx_v2_cycle.yaml
  eval_agx_v2_multicycle.yaml
```

命名规则尽量沿用现在的口径。也就是谁负责录制、训练、评测，就沿用 `teleop_ / act_agx_ / eval_agx_`。

### 4.1.1 录制配置建议

`teleop_v2_cycle_s0.yaml` 相比 `teleop_v1.yaml` 建议新增这些字段。

```yaml
teleop:
  stop_on_success: false
  stop_mode: dump_plus_ready
  post_dump_tail_steps: 80
  ready_anchor_hold_steps: 10
  ready_anchor_hit_threshold: 1.35

task:
  dataset_dir: data/agx_teleop_v2_cycle_s0
  param_version: v2_cycle_s0
  scenario_id: s0_baseline
  max_steps: 1500

v2:
  enable_cycle_labels: true
  anchor_vocab: v1
  patch_grid:
    rows: 3
    cols: 3
  default_dst_target_id: 0
```

这里 `stop_on_success` 不建议沿用 v1 的语义。V2 要录到 ready，而不是录到 dump success 再额外补固定尾段。
phase-1 录制默认也建议把 `task.max_steps` 提到 `1500`，否则完整单铲经常会被 `1000` 步上限截断。

### 4.1.2 训练配置建议

`act_agx_v2_cycle_qvel.yaml` 只是 qvel 转正版本。

```yaml
policy:
  class: ACT
  low_dim_keys: [qpos, qvel]
```

`act_agx_v2_gcact.yaml` 才是 V2 主线。

```yaml
policy:
  class: ACT
  low_dim_keys: [qpos, qvel, goal_tokens]
  act_params:
    chunk_size: 80
    kl_weight: 10.0
    hidden_dim: 512
    dim_feedforward: 3200
  aux_heads:
    phase: true
    progress: true
    fill: true
    anchor: true
```

第一版建议把 `chunk_size` 从当前 100 下调到 80，再把 `temporal_agg` 打开做对照。原因不是更先进，而是为了更频繁地重规划，降低多铲交界处的硬切感。

### 4.1.3 评测配置建议

`eval_agx_v2_cycle.yaml` 继续保留 `dump_complete_final_hold` 作为主完成口径，再额外加 V2 指标。

```yaml
success:
  mode: dump_complete_final_hold
  signal_name: deposited_mass_in_target_box_kg
  mass_thresh: 300.0
  residual_bucket_mass_thresh: 100.0
  hold_steps: 25

eval:
  num_rollouts: 10
  save_rollout_logs: true
  step_log_interval: 25

policy:
  temporal_agg: true

v2_eval:
  enable_cycle_metrics: true
  require_ready_anchor: false
  multi_cycle_plan:
    enabled: false
```

`eval_agx_v2_multicycle.yaml` 则额外引入规则式 high-level sequencer。

---

## 4.2 数据层

### 4.2.1 不改现有主 schema，只加 `/v2` 组

建议在每个 episode HDF5 下新增：

```text
/v2/
  /step/
    cycle_id                  (T,) int32
    phase_id                  (T,) int32
    phase_progress            (T,) float32
    goal_tokens               (T, 8) float32
    anchor_error_l1           (T,) float32
    pause_mask                (T,) int8
    boundary_mask             (T,) int8
  /cycle/
    start_step                (K,) int32
    end_step                  (K,) int32
    src_patch_id              (K,) int32
    dst_target_id             (K,) int32
    ready_anchor_id           (K,) int32
    next_src_patch_id         (K,) int32
    cut_depth_class           (K,) int32
    fill_peak_kg              (K,) float32
    deposit_delta_kg          (K,) float32
    cycle_success             (K,) int8
```

metadata attrs 再补：

```text
v2_schema_version = "0.1"
scenario_id = "s0_baseline"
patch_grid_spec = "3x3"
anchor_vocab_version = "v1"
goal_token_dim = 8
```

### 4.2.2 为什么先用 `/v2/step/goal_tokens`

因为 Repo A 当前训练入口和 ACT adapter 都已经把 low-dim 输入设计成拼接后的 `proprio`。如果直接引入一个全新 goal encoder 接口，会同时改 `_train.py`、dataset loader、adapter、checkpoint config 和 inference input。那样第一阶段改动太大。

最稳的做法是第一版把 `goal_tokens` 当成额外 low-dim 键。等这条线稳定以后，再拆成独立 embedding path。

---

## 4.3 训练层

### 4.3.1 Phase 标签不要等 Unity 导出，先在 Repo A 里算

因为 Repo B 当前合同明确没有显式 phase label，所以 V2 第一版 phase 标签应该在 Repo A 离线生成。

建议 phase 划分成 7 段。

```text
0 pre_approach
1 dig_contact
2 cut_fill
3 lift_clear
4 transport
5 dump
6 return_ready
```

### 4.3.2 每段的规则化判定

下面这套规则是按当前 `env_state + qpos` 能直接算出来的。

#### `pre_approach`

- `min_distance_to_dig_area_m > 0.05`
- 还没有 qualified dig start

progress 建议：

```python
p = clip(1 - min_distance_to_dig_area_m / 0.30, 0, 1)
```

#### `dig_contact`

- `min_distance_to_dig_area_m <= 0.05`
- `bucket_depth_below_dig_area_plane_m < 0.02`

progress 建议：

```python
p = clip(bucket_depth_below_dig_area_plane_m / 0.02, 0, 1)
```

#### `cut_fill`

- `bucket_depth_below_dig_area_plane_m >= 0.02`
- `delta_mass_in_bucket_kg > 0` 或 `delta_excavated_mass_kg > 0`

progress 建议：

```python
p = clip(mass_in_bucket_kg / load_mass_threshold_kg, 0, 1)
```

#### `lift_clear`

- 已经有有效载荷
- dig area 深度回落，且 bucket 逐步离开 DigArea

progress 建议：

```python
p = clip(1 - min_distance_to_dig_area_m / 0.20, 0, 1)
```

#### `transport`

- `mass_in_bucket_kg >= load_mass_threshold_kg`
- `min_distance_to_target_m` 在下降

progress 建议：

```python
p = clip(1 - min_distance_to_target_m / target_approach_distance_m, 0, 1)
```

#### `dump`

- `delta_deposited_mass_in_target_box_kg > 0`
- 或 `mass_in_target_box_kg` 开始增长

progress 建议：

```python
p = clip(deposited_mass_in_target_box_kg / success_mass_thresh, 0, 1)
```

#### `return_ready`

- `mass_in_bucket_kg <= residual_bucket_mass_thresh`
- `qpos` 接近 `ready_anchor.qpos_ref`

progress 建议：

```python
anchor_err = mean(abs((qpos - qpos_ref) / qpos_tol))
p = clip(1 - anchor_err, 0, 1)
```

### 4.3.3 Auxiliary heads

建议在现有 imitation loss 旁边加四个辅助头。

```text
phase_logits
phase_progress
fill_estimate
anchor_residual
```

loss 建议：

```text
L = L_act
  + 0.2 * L_phase_ce
  + 0.1 * L_progress_l1
  + 0.1 * L_fill_l1
  + 0.1 * L_anchor_l1
```

第一版不要上 diffusion，也不要先改 action semantics。先把当前 ACT 路线走到稳定可复用。

---

## 4.4 评测层

当前 Repo A evaluator 已经会写 rollout JSONL、summary、manifest。V2 不要另起一套产物目录，继续在现有结果目录里加字段。

建议新增这些指标。

### 4.4.1 单铲完成质量

- `cycle_success_rate`
- `avg_fill_peak_kg`
- `avg_deposit_delta_kg`
- `avg_final_bucket_mass`
- `avg_target_hard_collision_count`

### 4.4.2 连续性

- `pause_ratio`
- `boundary_jump_l1`
- `boundary_jump_l2`
- `mean_action_jerk`
- `handover_gap_steps`

定义建议：

```python
pause_ratio = (# steps where ||action||_1 < eps and phase not in idle) / valid_steps
boundary_jump_l1 = mean(||a_t - a_{t-1}||_1 over cycle boundary window)
mean_action_jerk = mean(||a_t - 2a_{t-1} + a_{t-2}||_2)
```

### 4.4.3 可复用性

- `ready_anchor_hit_rate`
- `anchor_error_mean`
- `cycle2_success_rate`
- `cycle3_success_rate`
- `carry_over_drop`

```python
carry_over_drop = cycle1_success_rate - cycle3_success_rate
```

---

## 5. Repo B 的具体改法

## 5.1 第一阶段，尽量不改 wire

Repo B 当前已经提供了 V2 很多需要的底层能力。

- `SceneResetService` 已经能做 terrain reset 和 pose reset
- `SwitchableTargetMassSensor` 已经支持 runtime target list、切换和测距
- `ActObservationCollector` 已经能拿到 base pose world、bucket pose world、actuator state、DigArea 量测、active target collision 量测

所以第一阶段只需要两件事。

### 5.1.1 把 `scenario_id` 真正接上 scene preset

当前 shared protocol 里 `RESET_REQ` 已经有 `scenario_id`。V2 最稳的用法是让 Repo B 新增一个很轻的 scenario preset 路径。

建议新增：

```text
AGXUnity_Excavator_Assets/Scripts/Experiment/
  ScenarioPreset.cs
  ScenarioPresetLibrary.cs
  ScenarioPresetApplier.cs
```

定义：

```csharp
public class ScenarioPreset {
    public string Id;
    public bool ResetTerrain;
    public bool ResetPose;
    public int ActiveTargetIndex;
    public Vector3 DigAreaOffset;
    public float DigAreaYawDeg;
    public Vector3 ExcavatorPoseOffset;
}
```

接入点建议放在 `AgxSimStepAckServer` 的 reset 路径里，在调用 `SceneResetService.ResetScene(...)` 之前应用 preset。

这样就能把 repoC 里已经存在但目前比较空的 `scenario_id` 变成真正可用的实验开关。

### 5.1.2 不急着把世界坐标上 wire

Repo B 内部确实已经有 `base_pose_world` 和 `bucket_pose_world`，但当前 wire 只定义了 `qpos / qvel / env_state / image`。所以第一阶段不要把 world pose 变成 required field。

如果后面 E08 以后证明 goal-conditioned 需要更强几何表达，再考虑加 optional field：

- `active_target_name`
- `base_pose_world`
- `bucket_pose_world`

第一阶段不需要。

## 5.2 与 AGX for Unity plugin 的边界

这个项目确实用的是 AGX for Unity。官方文档说明插件通常以 `.unitypackage` 或 UPM package 形式装进项目。你们现在仓库里的是项目侧脚本，不是整个 AGX 插件源码。所以 V2 第一阶段不要把关键路径建立在“必须改 AGX 插件内部”这件事上。最稳的做法是尽量只改：

- 你们自己的 scene scripts
- Repo A 的训练评测逻辑
- Repo C 可选的说明文档

也就是把 V2 设计成“利用 AGX 公共 API 和现有场景脚本”来做，而不是依赖 plugin fork。

---

## 6. 关于坐标、mask 和泛化

## 6.1 第一版不要让 visual mask 成为唯一控制量

原因有两个。

第一，当前 live wire 没有 mask 通道。
第二，Repo B 内部有更强的几何量，但还没上 wire。

所以第一版建议是：

- 策略主输入用 `qpos + qvel + goal_tokens + fpv`
- `goal_tokens` 里用 scenario-local 归一化 patch 坐标
- mask 只作为离线分析或后续 ablation

## 6.2 ground coordinate 和 relative coordinate 怎么统一

先分两层。

### 供上层和日志用的 scene-local ground frame

- 原点是 DigArea 中心
- x 轴是 DigArea 长边方向
- y 轴是横向
- 所有 patch center 归一化到 `[-1, 1]`

### 供当前 ACT 直接消费的低维 token

- 不直接用世界位姿
- 用 `src_u_norm / src_v_norm / next_src_u_norm / next_src_v_norm`
- `ready_anchor` 用 qpos 模板

这样第一版可以完全不依赖世界坐标 live export，但仍然保留“目标位置是明确的、可对齐的”这个能力。

## 6.3 泛化的课程式推进

建议按下面顺序扩。

### s0

- 固定 baseline scene
- 固定 active target
- 只录 return-ready primitive

### s1

- reset pose 轻抖动
- ready anchor 容差内起始扰动

### s2

- dig patch 在 3x3 网格里切换
- active target 可选 `ContainerBox` / `TruckBed`

### s3

- 连续 2 到 3 铲
- 上一铲改写下一铲局部状态

---

## 7. 实验矩阵

| ID | 目标 | 主要改动 | Repo 触点 | 数据 | 主指标 | 通过门槛 |
|---|---|---|---|---|---|---|
| E00 | 冻结当前业务基线 | 复现 `teleop_v1 / act_agx_v1 / eval_agx_v1` | Repo A only | `data/agx_teleop_v1` | `dump_complete_final_hold` | 与当前公开结果一致 |
| E01 | 先把平滑度量跑出来 | 只加 `pause_ratio / boundary_jump / jerk`，模型不变 | Repo A eval | 当前 v1 ckpt | 连续性指标可稳定产出 | rollout summary 有新字段 |
| E02 | 低成本试平滑 | `temporal_agg=false/true` 对照 | Repo A eval config | 当前 v1 ckpt | `boundary_jump` | `temporal_agg` 不降主成功率 |
| E03 | 正式录 V2 primitive | 录到 `dump + return_ready` | Repo A recorder | `agx_teleop_v2_cycle_s0` | demo 成功率、QA | 30 条合格 demo |
| E04 | V2 primitive 可学性 | qpos-only ACT | Repo A train/eval | `v2_cycle_s0` | `cycle_success_rate` | 可稳定完成单铲 ready-return |
| E05 | qvel 是否转正 | `qpos` 对照 `qpos+qvel` | Repo A train/eval | `v2_cycle_s0` | 主成功率、collision、smoothness | `qvel` 至少不差于 qpos |
| E06 | phase 头是否有用 | 加 `phase/progress/fill/anchor` heads | Repo A train/eval | `v2_cycle_s0` | `pause_ratio`、`anchor_error` | 连续性优于 E05 |
| E07 | goal-conditioned 雏形 | 加 `goal_tokens`，但目标固定 | Repo A data/policy | `v2_cycle_s0` | 与 E06 持平 | 不因 goal token 退化 |
| E08 | 多 patch 条件化 | 3x3 dig patch，规则式下发 `src_patch_id` | Repo A + 可选 Repo B scenario preset | `v2_cycle_s2` | 分 patch 成功率 | 非中心 patch 不明显崩 |
| E09 | lookahead 解决衔接 | 加 `next_src_patch_id` 和 ready anchor lookahead | Repo A policy/eval | `v2_cycle_s2` | `handover_gap_steps` | 比 E08 更低 |
| E10 | 连续两铲 | 规则式 high-level sequencer 跑 2 cycle | Repo A eval | `v2_multi2_s2` | `cycle2_success_rate` | 第二铲不雪崩 |
| E11 | reset 泛化 | pose jitter | Repo A + Repo B scenario preset | `v2_cycle_s1` | 成功率、anchor hit | 下降可控 |
| E12 | target 泛化 | `ContainerBox` / `TruckBed` 切换 | Repo B target preset + Repo A labels | `v2_cycle_s3` | 成功率、collision | 两类目标都可评测 |

---

## 8. 推荐的代码改动顺序

### 第一步

只动 Repo A。

- evaluator 加 V2 continuity metrics
- recorder 加 V2 stop mode
- HDF5 writer 加 `/v2` 组
- phase labeler 先离线生成

### 第二步

Repo A 训练链路扩 `goal_tokens`。

- dataset loader 支持 `goal_tokens`
- `_train.py` 和 `adapter.py` 支持 `low_dim_keys: [qpos, qvel, goal_tokens]`
- ACT 加 aux heads

### 第三步

Repo B 把 `scenario_id` 接到 preset。

- baseline scene 不变
- 只在 reset 前应用 preset
- 不改 action 维度
- 不强行加新 response required field

### 第四步

确认 E08 以后再决定要不要把 `base_pose_world / bucket_pose_world` 做成 optional wire field。

---

## 9. 这版方案最核心的判断

最重要的不是立刻做一个更大的模型，而是把下面四件事先定死。

1. `ready -> dig -> transport -> dump -> ready` 是 V2 primitive。
2. 上层和 ACT 的合同第一版用 `goal_tokens`，不是连续整条轨迹。
3. ready anchor 第一版用 `qpos` 模板定义，不等世界坐标上 wire。
4. V2 第一阶段主要动 Repo A，Repo B 只做 scenario preset 和受控扩展。

如果这四件事先定下来，你们当前 branch 就能和 V2 直接接上，而且不会把协议、场景、训练栈同时改炸。
