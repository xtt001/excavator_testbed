# V2.2 Pro Operator Data Collection Plan

Date: 2026-05-12

本文设计下一轮邀请专业挖机师傅在仿真中操作采集数据的方案。目标是在更新任务场景后，
从 V2.2 四 primitive 稳线重新出发，录到既自然、又能支持后续 ACT / planner /
boundary 分析的数据。

核心原则：

- 录制时保持专业师傅自然操作，不要求他按模型 primitive 停顿。
- raw 数据尽量完整记录，不在录制阶段过早裁剪。
- 后处理按 V2.2 ownership 和执行效果切分。
- 每个 planner 目标和实际执行结果都要能对齐分析。
- 先保护 V2.2 已经学会的 `carry/dump/return`，不要把新需求一次性压到所有
  primitive 上。

## 当前录制规范检查

### 现有入口

当前 V2.2 分支可用的录制入口主要有：

| 配置 | 角色 | 停止规则 | 适用性 |
| --- | --- | --- | --- |
| `teleop_v1.yaml` | 单铲 baseline | `dump_complete_final_hold` success 后录 50 步尾段 | 适合单铲，不适合完整多轮任务 |
| `teleop_v2_1_multi_raw.yaml` | 多轮 raw 主入口 | `target_dump_count = 3` 个 `dump_end` 后录 50 步尾段 | 可作为新方案基础，但 3 铲太短 |

当前 `tb-record-teleop` 支持：

- joystick / keyboard 输入；
- episode metadata：`operator_id`、`session_id`、`notes`；
- `scenario_id`；
- `record_config_yaml` 快照；
- `stop_mode = target_dump_count`；
- `post_success_tail_steps`；
- discard 当前 episode；
- reset 并丢弃当前 episode；
- Ctrl+C 保存当前 partial episode 后退出 session。

### 现有 HDF5 数据格式

当前 HDF5 schema v1.1 已经记录：

- `/observations/qpos (T,4)`：
  `[swing, boom, stick, bucket]`
- `/observations/qvel (T,4)`
- `/observations/env_state (T,M)`
- `/observations/images/fpv`
- `/action (T,4)`
- `/rewards`
- `/timestamps/step_id`
- `/timestamps/step_ns`
- `/action_source/type`
- `/action_source/id`
- `/metadata/*`

当前 V2 optional group 可离线写入：

- `/v2/step/cycle_id`
- `/v2/step/mode_id`
- `/v2/step/phase_id`
- `/v2/step/work_stage_id`
- `/v2/step/goal_tokens`
- `/v2/step/qualified_dig_start_mask`
- `/v2/step/dump_start_mask`
- `/v2/step/dump_end_mask`
- `/v2/step/boundary_mask`
- `/v2/cycle/*`

### 当前可直接复用的后处理

现有 pipeline 支持：

1. `tb-label-v2_1`
   - 给 raw episode 写 `/v2` labels；
   - 检测 `qualified_dig_start`、`dump_start`、`dump_end`；
   - 生成 cycle-level summary。
2. `tb-build-workskill-v2_1`
   - 裁出 `qualified_dig_start -> dump_end` workskill；
   - 支持 clean profiles。
3. `tb-build-transition-v2_1`
   - 裁出 `dump_end -> next qualified_dig_start` transition。
4. `tb-build-primitives-v2_2`
   - 从 workskill/raw 切出 `dig/carry/dump/return` sibling datasets。

### 当前不足

当前录制规范还不够适合“专业师傅自然完成完整任务”：

- `target_dump_count = 3` 太短，只能验证短多轮，不够覆盖完整作业区。
- 当前 clean V2.2 主线没有正式的 cell/grid/bite-point 字段。
- 当前 recorder 没有独立的“手动保存并结束当前 episode，但不退出 session”按钮。
- 当前 stop 规则没有“作业区清空/达到目标深度”模式。
- 当前 `goal_tokens` 仍是 sector-level 10D，不够表达新场景的 cell/bite/depth。
- 如果不新增目标和实际效果字段，后续仍难判断：
  - planner 想挖哪里；
  - 师傅实际从哪里起挖；
  - soil 实际从哪里被移除；
  - 是否有目标外挖掘或目标外倒土。

## 新数据采集目标

这轮数据不是只为了训练一个当前模型，而是为了建立一个可反复切分的全量专家数据池。

数据应支持这些用途：

- 训练 V2.2 四 primitive：
  - `dig`
  - `carry`
  - `dump`
  - `return`
- 训练未来 parameterized `dig`：
  - target cell
  - bite point
  - cut depth
  - actual bite / actual removal
- 训练或评估 target-conditioned `return`：
  - next dig entry target
  - actual `qualified_dig_start`
- 评估 planner：
  - selected cell vs actual cell
  - planned depth vs actual removed depth
  - coverage progress
- 评估 dump：
  - deposited fraction
  - target/off-target deposit
  - dump area geometry
- 分析失败：
  - collision
  - spill
  - pause / hesitation
  - low-productivity scoop
  - repeated cell / missed cell

## 录制原则

### 给师傅的任务说明

只给 task-level 指令，不给 primitive-level 指令。

推荐说明：

```text
请像真实作业一样，把指定作业区挖到目标程度，并把土倒到指定倒土区域。
不需要按格子顺序挖，不需要在每个阶段停顿。
如果你认为某个位置更适合先挖，就按你的经验操作。
保持动作自然、连续、专业。
```

不应该要求：

- 每铲必须从指定 cell 开始；
- 每次必须停在 ready pose；
- carry/dump/return 中间停顿；
- dump 必须拆成 approach 和 release 两段；
- 每个 primitive 开始前等待提示。

### 对 operator 的最小约束

允许自然操作，但要设定少量安全/质量约束：

- 不故意撞车斗或 dump area 边界；
- 尽量把土倒入目标区域；
- 如果一铲低产或姿态差，可以自然 rebite，不要强行停；
- 一轮 episode 中尽量完成连续多铲，不要每铲 reset；
- 如果操作失误严重，可以丢弃该 episode 重来；
- 每个 session 开始先做短 warmup，不进入训练集。

### 覆盖多样性提示

2026-05-19 诊断显示，YuLong pro 数据里专业 cut motion 覆盖了左侧区域，但
`dig start` / `next entry` 明显集中在中右侧。后续采集仍应保持师傅自然操作，
不做 live token 或逐 cell 指挥；但 observer 可以在 episode 之间给 task-level
覆盖提示，让数据包含更多可训练的 start pose 与 cut corridor 多样性。

推荐提示方式：

- 不要求“每铲从某个格子开始”，只要求这一条 episode 的总体清理方向不同；
- 一条 episode 重点从左向右清理，下一条从右向左清理；
- 一条 episode 重点从前向后清理，下一条从后向前清理；
- 允许师傅使用自然的“中右入铲、向左刮削”动作，但也要采集少量左侧或不同
  `z` 带的有效 dig start；
- 如果某一区域已经低产，鼓励师傅自然换到另一条 cut corridor，而不是继续反复挖空区；
- observer 在 `observer_notes` 中记录本条 episode 的覆盖意图，例如
  `coverage_prompt=left_to_right`、`right_to_left`、`front_to_back`、
  `back_to_front`、`free_natural`。

这条约束的目的不是让专业师傅按外行规则操作，而是让自然专业操作覆盖更多
entry / exit / swept-area 组合，便于后续 planner 学会根据当前作业区状态选择更聪明的
cut corridor。

## 推荐 episode 设计

### Episode 单位

推荐一个 episode 是一个自然完整作业片段，而不是一铲：

```text
reset scene
  -> operator 自然挖多铲
  -> 作业区达到目标或 target dump count 达到上限
  -> terminal hold 50-100 steps
  -> save episode
```

如果新场景任务是“挖空作业区”，episode 应尽量覆盖完整清理过程。

如果完整清空太长，建议定义两种 episode：

- `full_task_episode`：从 reset 到作业区目标完成；
- `subtask_episode`：从 reset 到完成 6-10 铲，用于覆盖更多起始和中间状态。

不要只录 3 铲作为主数据。3 铲可以保留为 smoke / calibration。

当前 YuLong 主录制入口为：

```bash
tb-record-teleop --config testbed/configs/teleop_yulong_v2_2_pro_full_task.yaml
```

该配置把 `max_steps` 设为 20000，只作为防止失控和文件过大的硬上限；正常结束由 operator
或 observer 在“可达区域已经低产 / 只剩边缘不可达土”时手动保存。由于当前 Unity
3x2 `removed_depth` 仍为诊断字段，不作为成功来源，正式 success 暂时使用
mass/productivity 口径：

- episode 级：累计 `deposited_mass_in_target_box_kg`、完整 dump 次数和最近几铲边际产出；
- cycle 级：`payload_gain_kg`、`deposit_delta_kg`、`dump_deposited_fraction`；
- 质量分层：`stage_success` / `stage_failure_reason_code`；
- 目标安全：target/dump area hard collision 和 unsafe dump distance，不惩罚 dig area 接触。

### 专业录制前的 new-env pilot

因为下一阶段场景已经变化，专业师傅大规模录制前必须先做小规模 pilot。pilot 的目标是
验证新环境和数据链路，不是训练最终模型。

建议先由内部人员录：

- 3-5 条短 full-cycle episode；
- 每条至少覆盖 3-5 铲；
- 至少包含一次正常 dump、一次 return-to-next-entry；
- 如果新任务是挖空作业区，额外录 1 条更长 episode 观察 area progress。

pilot 通过条件：

- HDF5 能正常写入新 env_state 和 metadata；
- 视频导出正常；
- target / dump area geometry audit 正常；
- relabel 能写出 cycle、primitive boundary 和 planned/actual 字段；
- primitive split 能生成 `dig/carry/dump/return` sibling datasets；
- 能人工确认 actual start、actual bite、actual removal、actual deposit 大致可解释；
- 没有明显协议错位、坐标系反向、单位错误或 episode 截断问题。

pilot 不通过时，先修 Unity/protocol/recorder/relabel，不进入专业录制。

### 数据量建议

pilot 通过后，第一轮专业数据建议分三批：

| 批次 | 目的 | 建议数量 | 是否进训练 |
| --- | --- | ---: | --- |
| calibration / warmup | 调手柄、确认场景、让师傅熟悉仿真 | 5-10 episodes | 默认不进训练 |
| main natural full-task | 主训练数据，自然连续作业 | 30-50 episodes | 进训练和 relabel |
| targeted coverage | 补齐稀缺 dig start、cut corridor、深度、边界状态 | 10-20 episodes | 进训练，但单独标记 |

如果每个 full task 很长，可以先录：

- 15-20 条 full-task；
- 30-40 条 6-10 scoop subtask。

targeted coverage 不应变成逐铲命令。建议按 episode 轮换覆盖提示：

- `left_to_right`：整体从左侧可达区域开始，逐步清到右侧；
- `right_to_left`：整体从右侧开始，逐步清到左侧；
- `front_to_back` / `back_to_front`：补齐不同 `z` 带；
- `free_natural`：完全自由发挥，用来保持主数据分布不过度人工化。

每个方向至少保留若干条高质量 episode。QC 时同时检查 dig start 覆盖和
entry->exit swept cut segment 覆盖，不能只看 start point。

### 场景 reset 分布

这轮最好不要只录一个完全固定初态。建议有受控变化，但一次不要太大：

- 固定 dump area；
- 固定机械 base；
- 作业区土体初态可有少量随机；
- 目标深度可分浅/中/深；
- cell 目标不强制给师傅，但后处理要能识别实际覆盖。

如果 dump area 后续要变化，应单独开下一批，不要混在第一轮里。

## 录制字段需求

### 当前必须保留字段

这些当前已经有，必须保持稳定：

- `qpos`
- `qvel`
- `action`
- `fpv`
- `env_state`
- `step_id`
- `step_ns`
- `action_source`
- `operator_id`
- `session_id`
- `notes`
- `record_config_yaml`
- `scenario_id`
- `env_state_order`

### 新场景建议新增 env_state 字段

为了以后不用反复重录，Unity / protocol 最好 add-only 输出这些字段。

作业区局部坐标：

- `bucket_tip_dig_area_x_m`
- `bucket_tip_dig_area_z_m`
- `bucket_tip_dig_area_y_m`
- `bucket_depth_below_local_surface_m`
- `bucket_depth_below_target_surface_m`

作业区 grid / surface：

- `dig_area_surface_depth_m_r*_c*`
- `dig_area_removed_depth_m_r*_c*` 或等价 cumulative delta
- `dig_area_target_depth_m_r*_c*`
- `dig_area_cell_valid_mask_r*_c*`

payload / soil：

- `mass_in_bucket_kg`
- `bucket_mass_delta_kg`
- `excavated_mass_kg`
- `deposited_mass_in_dump_area_kg`
- `offtarget_deposited_mass_kg` 如果 Unity 可测

dump area：

- `bucket_dump_area_relative_x_m`
- `bucket_dump_area_relative_z_m`
- `bucket_dump_area_footprint_outside_distance_m`
- `bucket_height_above_dump_area_rim_or_plane_m`
- `bucket_over_dump_area_mask`
- `dump_clearance_ok_mask`

事件辅助：

- `target_geometry_available`
- `bucket_dig_area_cell_in_bounds_mask`
- `bucket_dig_area_penetration_contact_mask`
- `bucket_contact_dump_area_mask`
- `hard_collision_count`
- `target_contact_max_normal_force_n`

### 建议新增 metadata

每条 episode metadata 建议记录：

- `operator_id`
- `operator_experience_level`
- `session_id`
- `scenario_id`
- `scene_version`
- `soil_preset_id`
- `dig_area_preset_id`
- `dump_area_preset_id`
- `task_goal_description`
- `target_depth_m`
- `recording_protocol_version`
- `warmup_or_train`
- `operator_notes`
- `observer_notes`

metadata 比文件夹名更可靠。文件夹名可以换，metadata 不能缺。

## 建议录制规则

### 推荐 stop mode

当前工具直接可用的最接近方案：

```yaml
teleop:
  stop_mode: target_dump_count
  target_dump_count: 8  # 或 10/12，取决于新任务长度
  stop_on_success: false
  post_success_tail_steps: 100

task:
  max_steps: 10000
  recording_mode: teleop_multi_raw
```

如果新场景能输出“作业区完成”成功信号，建议新增或复用 task success：

```text
stop when area_clear_success == true
then record 100 tail steps
```

如果还没有 area clear success，先用 `target_dump_count` 做硬上限，并在 notes 中记录
是否真正完成作业区。

### 建议增加一个最小 recorder 功能

录专业师傅前，建议给 `tb-record-teleop` 增加一个“保存当前 episode 并进入下一次
reset”的手动按钮。

现在有：

- discard episode；
- reset and discard；
- quit session；
- target dump count stop；
- max steps stop。

建议新增：

- `save_episode_requested`：
  - 当前 episode 保存；
  - 写 `stop_reason = manual_episode_end`；
  - 记录 tail steps 后 reset；
  - 不退出整个 session。

这个小功能会显著降低现场录制风险：师傅完成一段自然任务后，可以由 observer 保存，
不用等 max_steps，也不用 Ctrl+C 结束整个 session。

## 后处理方案

### Step 1: Raw 保存

原始目录不要覆盖：

```text
data/agx_pro_v2_2_<scene>_raw_YYYYMMDD/
```

raw 数据只读，所有 relabel/crop 都写 sibling directory。

### Step 2: QC

每批录完立即跑：

```bash
tb-dataset-qc --dataset-dir data/agx_pro_v2_2_<scene>_raw_YYYYMMDD
tb-dataset-videos data/agx_pro_v2_2_<scene>_raw_YYYYMMDD
tb-audit-target-geometry --dataset-dir data/agx_pro_v2_2_<scene>_raw_YYYYMMDD
```

人工抽查视频：

- 每个 operator 至少抽查 20%；
- 每种 scene preset 至少抽查 3 条；
- 所有 rejected / max_steps episode 必看。

### Step 3: V2 relabel

按现有机制：

```bash
tb-label-v2_1 --dataset-dir data/agx_pro_v2_2_<scene>_raw_YYYYMMDD --scenario-id <scenario>
```

如果新场景新增 cell/grid 字段，建议 relabel 同时写：

- actual QDS local x/z；
- actual QDS cell；
- actual bite start cell；
- actual removal peak cell；
- per-cycle target/actual deposit metrics。

### Step 4: V2.2 primitive split

继续使用 V2.2 四 primitive：

```text
dig:    qualified_dig_start -> before carry
carry:  carry start -> first approach_dump ownership
dump:   first approach_dump ownership -> dump_end + hold
return: dump_end + hold -> next qualified_dig_start
```

生成 sibling datasets：

```text
raw
relabeled
workskill
primitives/dig
primitives/carry
primitives/dump
primitives/return
```

### Optional: Empty-Box Capacity Calibration

在正式定义 task success 前，可以单独录一条 YuLong capacity calibration：

```bash
tb-record-teleop --config testbed/configs/teleop_yulong_v2_2_empty_box_capacity.yaml
```

这条数据的目标是让 operator 尽量把**可达、可生产**区域挖到边际收益很低，
记录总 dump 次数、累计 `deposited_mass_in_target_box_kg`、各 cycle
`payload_gain_kg` / `deposit_delta_kg`，以及 3x2 grid 的 removed depth。
它不应直接把“挖空整个箱子”定义成 success，因为边缘土可能不可挖或不值得挖。

容量标定数据 relabel 时应复用同一份 YAML 阈值：

```bash
tb-label-v2_1 \
  --dataset-dir data/yulong_v2_2_empty_box_capacity_raw_20260514 \
  --config testbed/configs/teleop_yulong_v2_2_empty_box_capacity.yaml \
  --scenario-id s0_truck \
  --qualified-dig-start-mode contact_depth
```

### Step 5: 质量分层，不要只保留最干净数据

不要把数据一刀切成“好/坏”。建议分层：

- `gold`：动作自然、无碰撞、deposit 好、transition 顺；
- `silver`：有轻微纠偏或低产，但专业处理合理；
- `diagnostic`：失误、卡顿、碰撞、低产、目标外动作；
- `discard`：录制/接口错误、严重乱操作、非任务行为。

训练主线先用 `gold + selected silver`。`diagnostic` 不进主训练，但保留给失败分析和
robustness。

## 面向 ACT 的训练计划

### 第一阶段：验证新数据能否复现 V2.2

目标：

- 用新场景数据重新切 V2.2 四 primitive；
- 先不引入 paramdig；
- 验证 `carry/dump/return` 是否能学回 V2.2 水平。

训练：

- `dig(qpos+qvel)`
- `carry(qpos+qvel)`
- `dump(qpos+qvel)`
- `return(qpos+qvel)`

评估：

- 3-cycle smoke；
- dump deposited fraction；
- hard collision；
- transition timeout；
- actual QDS distribution。

### 第二阶段：只参数化 dig

目标：

- 只改变 `dig`，保持 `carry/dump/return` 不变。
- 验证 ACT 能否学会 condition 挖掘。

输入：

- qpos/qvel；
- target cell；
- bite point；
- target depth；
- local surface context。

不输入：

- dump target；
- truck token；
- 后续 return 目标。

评估：

- selected cell vs actual bite cell；
- selected bite point vs actual QDS/bite；
- bucket gain；
- surface removed at selected cell；
- 是否影响 carry/dump handoff。

### 第三阶段：必要时参数化 return

只有当 `dig` 已能按目标工作，但 return 不能把 bucket 带到下一次 dig entry 附近时，
再训练 target-conditioned return。

return 的目标是：

```text
next dig entry / QDS target
```

不是：

```text
next actual bite point after dig starts
```

这是 V2.3.5 的重要教训。

### 第四阶段：未来再参数化 dump

只有当 dump area 变成变量时，才给 `dump` 加 dump-target token。固定 truck / 固定
dump area 下不要加 truck-token。

## 现场执行流程

### 录制前

1. 确认 Unity 场景版本和 protocol 版本。
2. 跑 smoke：
   - reset；
   - step；
   - record 10 秒；
   - 保存 HDF5；
   - 打开视频；
   - 检查 `env_state_order`。
3. 调整 joystick 映射，让师傅确认手感。
   - 当前 YuLong FarmStick 约定：左手 swing 轴在 pygame 里使用反向
     `invert[0]=true`；手柄实体 Button 10 保存 episode，Button 11 丢弃并 reset。
4. 录 3-5 条 warmup，不进训练。
5. 让师傅看回放，确认仿真操作是否接近真实习惯。

### 录制中

每条 episode 记录 observer notes：

- 是否自然完成；
- 是否有明显失误；
- 是否发生碰撞；
- 是否某段是故意演示边界情况；
- 是否应该进入训练。

不要在动作过程中频繁提示师傅“现在该 carry / dump / return”。只在 episode 之间交流。

### 录制后

当天立即完成：

1. backup raw；
2. dataset QC；
3. video export；
4. target geometry audit；
5. 10%-20% 人工视频抽检；
6. relabel smoke；
7. primitive split smoke；
8. 写 session summary。

## 需要新增或确认的最小工程项

录制前建议完成：

- 新场景 `scenario_id` 和 metadata；
- 新场景 env_state add-only 字段；
- 作业区 local coordinate / grid surface 输出；
- dump area geometry 输出；
- manual save episode button；
- 新 teleop config，例如：
  `teleop_v2_2_pro_full_task.yaml`；
- relabel 扩展：记录 actual QDS cell / bite cell / removal cell；
- QC 扩展：cell coverage 和 target-vs-actual 统计。

专业录制前必须先完成 new-env pilot：

1. 内部录 3-5 条短 episode；
2. 跑 video export；
3. 跑 target geometry audit；
4. 跑 relabel smoke；
5. 跑 primitive split smoke；
6. 人工抽查 planned/actual 对齐；
7. 写 pilot summary，再决定是否进入专业录制。

如果时间不够，最低要求是：

1. `teleop_v2_1_multi_raw.yaml` 改成更长的 `target_dump_count` 和 `max_steps`；
2. metadata 记录 operator/session/notes；
3. Unity 输出新任务必需 env_state；
4. 录完立即做视频和 target geometry audit。

## 最重要的验收标准

这批数据是否成功，不看“录了多少条”，而看：

- 是否先通过了 new-env pilot；
- 是否保留了师傅自然动作；
- 是否覆盖多轮连续过渡；
- 是否能离线切出 V2.2 四 primitive；
- 是否能知道每铲目标与实际结果；
- 是否有足够的 return-to-next-dig-start 覆盖；
- 是否有足够的不同 cell / depth / soil state；
- 是否能把数据分成 gold/silver/diagnostic；
- 是否可以用同一批 raw 数据反复构建不同训练集，而不用每次重录。
