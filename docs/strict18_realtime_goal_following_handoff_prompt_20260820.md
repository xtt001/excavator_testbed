# Strict-18 实时地形目标跟随开发 handoff prompt

你正在继续 Strict-18 从“连续作业恢复”走向“实时地形目标跟随”的开发。

当前授权路线已切换为**阶段 B → C → D 的 Dig 单铲位置 A/B 土体效果验证**。停止继续深挖 Return。
两臂从同一个冻结训练姿态出发，只改 DigArea 中目标的 z 位置，并比较实际轨迹、入土/出土几何和
目标 cell 的土体移除效果。不训练、不更换 checkpoint、不改时序聚合，也不放宽安全阈值。

请先完整阅读本文件和
[`docs/strict18_goal_following_roadmap.md`](strict18_goal_following_roadmap.md)，再检查当前 checkout、
正式工件和 Unity 能力。不要从下方 Return 历史恢复已被当前路线取代的任务。

## 先向用户说明的通俗版本

开始工作前，用一段通俗的话告诉用户：

> 当前要验证的是：相同可观测起点上，只把 Dig 目标沿 z 方向移到另一格，冻结 ACT 是否会把铲尖和土体效果同步移过去。
> 代码先冻结目标、阈值、独立会话、一次执行和立即停止规则。真正动作必须另行显式授权。
> Unity 还不能证明隐藏土体完全复位，所以成功结果也只能作诊断，不改默认策略或生产行为。

随后把工作拆成四步说明：

1. 用正式 Dig v1 支持工件生成并校验 `contract.json`；这一步不启动 Unity、不发动作。
2. original/cell 2 和 alternate/cell 4 分别使用独立、可丢弃、no-save Play Mode，做 20 tick 稳定和 100 tick 冻结 ACT 安全预演。
3. 只在另有明确动作授权、两个预演都通过时，按 original→alternate 运行两个独立单 Dig 臂；每臂一次、最多 250 tick。
4. 任一初态、支持、原子动作遥测或安全合同失败都归为 `invalid_or_safety_blocked`，报告实际执行数相对计划 `2/2` 的差额。

实现入口是 `tb-dig-single-shovel-ab`。`validate` 只读核对正式 support 工件与冻结合同，不启动 Unity、
不创建实验目录、不发送动作。`run` 必须同时提供全新的 `--artifact-root`、`--execute-authorized` 和目标
Unity Editor PID；不得把 `validate` 通过写成阶段 C/D 已执行。真实运行前仍须单独确认动作授权和当前
Unity 会话，且结果始终保持隐藏土体未证明、仅作诊断、不可晋级。

在线入口还会比较 Dig 依赖的 Unity C# 源文件与 `Library/ScriptAssemblies/Assembly-CSharp*.dll` 的
修改时间。源码更新但 Editor 尚未重新编译时，必须在进入 Play Mode 前以
`unity_script_assembly_stale` 拒绝运行；这条门槛不能替代全零原子动作诊断握手。运行异常会在工件中
保留单行、最多 300 字符的具体错误，便于区分陈旧程序集、协议解析和服务端安全拒绝。

实验工件必须区分完整写入的轨迹 tick（`observed_ticks`）与 Unity 已返回响应的效果 STEP 数
（`acknowledged_effect_step_calls`）。后者在响应到达后立即计数，所以响应后的 DTO/遥测校验失败也要如实
保留已经推进过的物理步；不能因为没有生成 trace row 就写成零动作。

默认 107D 中的 `bucket_dig_area_penetration_contact_mask` 是动态测量包围盒相对局部土面的几何入土信号，
不是 AGX 刚体接触回调。A/B 效果指标改用只在诊断 STEP 中返回的固定中齿前缘点及其局部深度；默认
107D 字节和生产观测不变。可变形土体入侵时几何信号可以为真，而 worktool monitor 同帧仍报告零刚体
接触；这不构成遥测矛盾。两条通道仍分别要求完整和自洽，墙、硬底、禁止/未知接触、高力等停止条件不变。

冻结姿态的释放与首个诊断零动作采用同一 STEP 的原子静止交接：只允许四轴零动作，Unity 先验证
静止锁再推进一帧；零动作期间继续保持，首个非零动作前恢复原控制器配置。交接后的实际位置和速度仍
按原始 `0.005` 与 `0.10` 门槛判定。该路径仅由本 Dig 实验显式请求，普通 STEP 和默认控制行为不变。

Python 仓库仍在 `tx/continous_follow_dev` / `533a77a3...`，Unity 仓库仍在
`codex/2_4-yulong-factory-replacement` / `2ef27457...`。两个工作树都包含未提交材料，不能写成干净、可重建的实验基线。

## 2026-08-21 Dig 在线状态

已修复两项只在在线路径暴露的问题。Unity 接触分类现在用非空 AGX UUID 把当前 shovel、其 active Dig
terrain、精确 bucket geometry 和 shovel 生成的 soil aggregate 绑定起来；生成几何的显示名称只作诊断，
不能授权接触。Python JSON 工件不再直接写相机 bytes，而是记录 `binary_sha256_v1` 的长度和 SHA-256，
并在独占创建文件前先完成序列化，避免半截 JSON。相机原始帧仍只写四路和 2×2 合成视频。

最终 no-overwrite 运行根是：

```text
/home/pingfan/PACT/excavator_testbed/runs/eval/
dig_single_shovel_ab_20260821T181507+0800/
```

两个 100 tick 预演均通过。original 效果臂执行 226 个 STEP，第 59 步首次入土，此后没有出土下降沿。
铲斗归一化位置在第 225 步达到 `1.000`；第 226 步 ACT 请求的第 4 轴动作仍为 `+0.46673834`，Unity
报告 `soft_limit_axes=[false,false,false,true]` 并将该轴最终目标速度置零。runner 立即转零，7 步后四轴
目标速度均为零并取得 neutral ACK。最大力 `16008.61 N`，没有墙、硬底、未知/禁止接触或碰撞，活动场景
路径、dirty 状态和磁盘 SHA 均未改变。

因此结果固定为 `invalid_or_safety_blocked`，实际效果臂 `1/2`；alternate 未启动。不能把 cell 2 的
`0.02283448 m` 局部移除深度写成 A/B 成功，因为 original 没有出土且发生安全限位。该次 original 已消费
冻结合同的唯一机会，`retry_allowed=false`。不要原样重启、换目标、放宽限位或补跑 alternate。后续若要
继续在线测试，必须先把“ACT 为什么持续卷斗至边界”作为执行精度/目标几何或训练覆盖问题形成新的冻结
实验合同，并重新取得动作授权。生产默认、checkpoint、temporal aggregation 和安全阈值均未改变。

随后复查发现，上述运行的轨迹、入土/出土和局部深度还混入了独立测量缺陷：Unity 每帧从铲斗测量盒
27 个点中重新选择 DigArea-local y 最低点，近似并列的底部角点会切换。同一关节姿态下记录点可跳约
`0.44 m`，因此它不是连续的物理铲尖。修复没有改默认 107D，而是在显式 `ADQ1` 响应中追加
`bucket_fixed_tip_diagnostic_v1`，冻结中齿前缘中点
`bucket_center_tooth_leading_edge_midpoint_v0_1`；Python A/B runner 对每步 schema、候选、STEP lineage、
有限值、`0.005 m` 入土阈值和唯一性做 fail-closed 校验，再用该点生成实验轨迹。普通 STEP 和生产默认
保持原样。修复后轨迹最大相邻 20 ms 位移降到 original `0.014009 m`、alternate `0.013997 m`。

用户重新授权后，新实验只写根为：

```text
/home/pingfan/PACT/excavator_testbed/runs/eval/
dig_single_shovel_ab_20260821T193147+0800/
```

两个 100 tick 预演通过，两个效果臂完成 `2/2`。original 在第 61 帧入土、第 186 帧出土，188 个效果
STEP 后停止；alternate 在第 52 帧入土、第 134 帧出土，136 个效果 STEP 后停止。两臂均以连续 3 帧
无土体接触确认出土并取得 neutral ACK；最大安全力分别为 `20972.54 N` 和 `12059.06 N`，均低于
`100000 N`。没有动作裁剪、软限位、墙、FactoryFloor、硬碰撞、禁止或未知接触；既有加速度限速在每臂
最初 6 tick 对称工作。四个 Play session
身份独立，场景磁盘 SHA 前后仍为 `97b01deb...51d154fe5cc6514b7c9`。

结果没有通过“指哪挖哪”。初始 100×4 raw chunk 的目标响应比例为 `1.0`，但接触段轨迹中位分离只有
`0.282983 m`，低于冻结的 `0.50 m`。original/alternate 的入土误差分别为 `0.452967 m`/`0.860084 m`，
深度误差为 `0.220922 m`/`0.276756 m`，出土误差为 `1.406151 m`/`1.432217 m`。original 在目标 cell 2
移除 `0.021632 m`，alternate 在目标 cell 4 移除 `0 m`，反而仍在 cell 2 移除 `0.004594 m`。唯一分类为
`action_only_no_trajectory_separation`：目标 token 改变了 raw action，但没有把实体切削轨迹和土体效果移到
alternate 目标。逐步回报证明 policy action、Unity received/clamped action 完全一致，没有输入裁剪或
软限位；每臂仅最初 6 tick 触发相同的既有加速度限速。当前证据排除了传输裁剪和软限位作为直接原因，
但仍需一起审计执行器/动力学映射与训练覆盖，不进入 Return→Dig 集成。该运行 `diagnostic_only=true`、
`promotion_eligible=false`、
`retry_allowed=false`，隐藏土体一致性仍未证明，默认系统未改变。

## 冻结历史：2026-08-20 Return handoff

从下节开始的 Return A.6/A.6-S 内容仅供证据溯源。不继续实现、补跑或放宽其合同。

## 仓库与 Git 锁定

Python 仓库：

```text
/home/pingfan/PACT/excavator_testbed
branch: tx/continous_follow_dev
HEAD/upstream/remote: 533a77a3b1595e83860340fe3537e56f47e39a76
```

交接时 Python 工作树干净，本地、upstream 和远端 SHA 已核对一致。最近四个提交是：

```text
1bc058f feat(data): freeze recorded return closed-loop fixtures
a262d75 feat(eval): define bounded return causal contract
14bbc1b feat(eval): add fail-closed return-only probe
533a77a docs(strict18): authorize bounded return causal diagnostic
```

Unity 仓库：

```text
/home/pingfan/AGXUnityE85ExcavatorSim
branch: codex/2_4-yulong-factory-replacement
HEAD: 2ef27457999a54090f64e151a73dbafc88ec1670
```

交接时 Unity 仍有 17 个受跟踪修改和 48 个未跟踪文件。它们混合了桥接协议、控制／标定／接触、
Editor 诊断、测试、场景、`.meta` 和文档。上一轮没有修改或提交 Unity。不要使用 `git add -A`、
`git clean`、`reset`、rebase，也不要把现有改动当成本任务自动生成的内容。任何 Unity 写入前，先取得
用户对 Unity 修改范围和提交策略的明确授权，并逐文件完成责任盘点。

## 我们最终要实现什么

系统的长期目标是：Planner 根据目标地形和当前残差选择下一铲任务级目标，goal-conditioned ACT
执行当前 primitive，独立安全链约束动作，执行结果再更新地形状态。

当前冻结的职责边界：

- Planner 生成任务级目标，不输出 joystick 或 qpos 跟踪轨迹。
- ACT 直接输出 `[swing, boom, stick, bucket]` 四轴动作。
- Dig 使用 `qpos + qvel + dig_cut_tokens`。
- Return 使用 `qpos + qvel + return_start_envelope_tokens_v1`。
- Carry/Dump 使用 `qpos + qvel`，不得被下一铲 token 错误条件化。
- `exact-tuple` 和 continuous-qpos predictor 保留为 `diagnostic_legacy`。
- 安全链独立，不能为通过实验而放宽接触、硬底、高力、限位、卡死或 timeout。

“指哪挖哪”至少需要三层证据：ACT 在相同观测下读取不同目标、Unity 闭环产生相应轨迹和目标命中、
实际地形效果与安全约束同时成立。当前只完成了第一层的大部分离线证据，第二层 Return 因果测试尚未
执行，第三层仍未开始。

## 已完成进展

### 1. Python 代码治理与 ACT 推理接口

- Python 主仓库的重复 ACT 加载、低维输入构造和私有 chunk 访问已经收敛到公共推理接口。
- `ACTAdapter.predict_action_chunk(obs)` 可读取完整反归一化 chunk，且不推进 temporal 时钟或写 cache。
- exact-tuple、continuous-qpos 和旧 replay 源码没有删除，只标记为诊断遗留路径。
- 空、无 `.gitmodules` 映射且不可恢复的 `legacy` gitlink 已移除。
- Unity 的 Git 混乱仍未治理；不要把 Python 干净误写成双仓都干净。

### 2. 阶段 A 冻结 ACT 目标条件敏感性审计

正式 Stage-A v3 工件：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/run/
act_goal_condition_sensitivity_v3/
```

结果：

- Dig：10 段中 9 段 `goal_response_plausible`，1 段按冻结 v1 规则 `out_of_support`。
- Return：采用独立验证选出的 Return joint v2 支持规则后，9 段均在支持范围；7 段
  `goal_response_plausible`，2 段 `goal_response_invalid`。
- Carry/Dump 无关 token 隔离通过。
- 所有结果都是 `teacher_forced_recorded_observation`、`diagnostic_only=true`、
  `promotion_eligible=false`，不证明真实轨迹、地形效果或生产可用性。

Dig 的唯一 OOS 段是 `dig:1044-1083:37a4b7afda73`。对齐、字段顺序、dtype、前一帧 observation
和 `action_loss_mask=1` 过滤均通过；`qvel[1]` 有连续 17 帧超过 v1 p99，但 strict-train 同一数值
区间已有 253 行。联合 Mahalanobis 和局部完整状态候选都没有通过独立 held-validation 的 99% 验收。
因此不可自动放宽 v1。项目决定是停止为这个单例继续设计自动放行规则，把它保留为后续 Dig 单铲
闭环的尾部观察样本。可以承认已有 Dig 目标响应的离线诊断证据，但不得重写不可变 OOS 工件或宣称
Dig 已通过 Unity／生产证明。

### 3. Return 两段失败的原因已经定位

固定失败段：

```text
return:898-1043:bb329f176aba
return:3959-4161:4afcef2eee82
```

token 归一化、图像与 qpos/qvel 历史、前一帧对齐、replica、cache/reset、action scale、公开 chunk
查询及 aggregation 重建都已核验。冻结 80% 门槛没有降低。

结果是 `temporal_aggregation_dilution`：

- 第一段当前 query 原始响应约 99.3%，实际聚合后为 77.4%。33 个受抑制帧中，13 帧被历史计划
  反向抵消，20 帧主要是最新计划权重过低；最新 query 权重仅 1.10%–2.66%。
- 第二段当前 query 原始响应为 100%，实际聚合后为 71.9%。57 个受抑制帧中，41 帧被历史计划
  反向抵消，16 帧主要是权重稀释；最新 query 权重仅 0.62%–2.04%。

这证明旧 aggregation 在 teacher-forced 记录回放中会压低新目标响应，但不证明 Unity 中两个目标一定
收敛到同一轨迹。

### 4. Return temporal dispatch 独立验证没有选出替代策略

候选只在两个 source-disjoint held Return source 的固定 16 段上比较，失败段没有参与选参：

| 策略 | 聚合目标响应 | 每段均达到 80% | 动作质量不差于 legacy | 可选择 |
| --- | ---: | ---: | ---: | ---: |
| legacy 100-step oldest-first | 0.953433 | 否 | 是 | 否 |
| newest-first 100-step | 0.950034 | 否 | 否 | 否 |
| newest-first max-age 20 | 0.929640 | 否 | 否 | 否 |
| latest-current-chunk 诊断对照 | 0.933719 | 否 | 否 | 否 |

状态为 `dispatch_contract_not_selected`。不得继续根据两个失败样本反复调整 newest-first 或窗口。
默认 legacy 不变；latest-current-chunk 只用于闭环因果诊断，永远不是本轮上线候选。

### 5. Return-only 16 臂闭环诊断已经实现，但真实动作未开始

Python 已冻结四个入口：

| fixture | Return 段 | pre-action observation | original → alternate |
| --- | --- | ---: | --- |
| F1 | `return:898-1043:bb329f176aba` | 897 | cell 0 → cell 4 |
| N1 | `return:3453-3664:bb329f176aba` | 3452 | cell 0 → cell 4 |
| F2 | `return:3959-4161:4afcef2eee82` | 3958 | cell 4 → cell 1 |
| N2 | `return:4437-4633:4afcef2eee82` | 4436 | cell 4 → cell 1 |

每个 fixture 运行 `original/alternate × legacy/latest-current-chunk`，共 16 臂。每臂独立 policy 和
temporal state，最多 420 STEP，只运行一次，完成／超时／安全停止后必须 zero → neutral ACK。整个
测试只允许 Return，禁止 scheduler 进入 Dig、Carry 或 Dump。

主要实现入口：

- `testbed/data/recorded_return_closed_loop_fixture.py`
- `testbed/eval/return_closed_loop_causal_contract.py`
- `testbed/eval/return_closed_loop_preflight.py`
- `testbed/eval/return_closed_loop_probe.py`
- `testbed/eval/return_closed_loop_results.py`
- `testbed/eval/return_closed_loop_runtime.py`
- `testbed/cli/return_closed_loop_probe.py`

## 当前正式状态：`preflight_blocked`

正式执行请求已经运行，但在连接执行后端、加载 ACT 和发送任何非零动作之前停止。不要把它写成
Unity 闭环测试已完成。

不可覆盖工件：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/run/
bounded_return_closed_loop_causal_diagnostic_v1/
```

关键结果：

```text
status=preflight_blocked
execution_requested=true
arm_count=16
executed_count=0
nonzero_action_count=0
runtime_default_changed=false
results.status=not_evaluated
```

阻断原因分三组：

1. **起点不可精确复现**：当前 `REALIGN_POSE` 会清零速度并报告 `qvel_applied=false`；没有完整刚体／
   约束／非零 qvel 的请求级状态恢复。历史 source 只保存 107D 可观测地形，没有完整土壤快照或可验证
   的确定性 soil seed。107D 相似不能证明隐藏土壤状态相同。
2. **执行证据不足**：协议没有原子回报实际施加的四轴动作、每轴限幅干预和正式 Return handoff 结果。
   请求值回显不能代替真实 applied action。
3. **Unity 基线不可复现**：Unity 工作树脏，当前 source 尚不能作为已审查、可重建的实验基线。

特别注意：即使现在增加完整 snapshot/restore API，也不能凭空恢复历史 source 从未记录的隐藏土壤状态。
如果坚持“与历史失败段完全相同的地形”，旧数据本身不足以满足合同。推荐的严格路径是先建立确定性土壤
与完整状态捕获能力，再生成一套新的、成对可恢复的 Return fixture；它必须作为新实验，不能冒充历史
隐藏状态复刻。只有用户明确接受更弱证据时，才可另立 `surrogate_initial_state` 合同使用 qpos/qvel 加
107D 可观测指纹；当前 A.6 合同不允许这种代理。

## 下一轮工作边界

在用户明确授权修改 Unity 之前，只允许继续只读盘点和设计，不得写 Unity 仓库。

获得授权后，推荐按下面顺序实施：

### 第一步：收口 Unity Git 和可重建基线

- 将 17 个 tracked 修改和 48 个 untracked 文件按协议／四相机、控制／标定／接触、Editor 诊断／测试、
  scene／`.meta`／文档分组审查。
- `ProjectSettings/Packages/com.algoryx.agxunity/EditorData.json` 视为本机编辑器状态，默认不提交。
- 根 `AGENTS.md` 默认保留未跟踪，不纳入产品提交。
- 不丢弃用户修改，不盲拆 scene、协议、C# 和对应 `.meta` 的强耦合变更。
- 用 Unity Editor 编译和测试证明基线可重建，再形成显式文件清单的本地提交。

### 第二步：增加默认关闭的实验能力

- 提供 request-local、opt-in 的完整状态 capture/restore，覆盖 qpos、非零 qvel、相关刚体位姿／速度、
  约束状态以及可恢复的土壤状态或确定性 soil seed。
- restore 响应必须区分 requested、applied 和 observed，不能只回显请求。
- 普通 RESET、默认 runtime 和现有安全阈值保持不变。
- 断连、超时或 capability 禁用时必须执行 zero → neutral ACK。

### 第三步：补齐原子执行遥测

每次 STEP 至少原子记录：

```text
commanded_action
applied_action
per_axis_limit_intervention
qpos/qvel
bucket/tip pose
collision/contact/safety-stop state
official Return handoff assessment
```

正式 handoff evaluator 必须独立于 token 几何近似。direct token envelope 只能作为诊断字段，不能冒充
正式 Return→Dig readiness。

### 第四步：重新运行严格矩阵

- 先让全部 16 臂的静态和逐臂 preflight 在任何非零动作前通过。
- 不覆盖现有 v1 阻断工件；使用新的 no-overwrite 根，例如
  `bounded_return_closed_loop_causal_diagnostic_v2/`。
- 仍只比较 legacy 与 latest-current-chunk，不复活 newest-first/max-age20。
- 记录两个目标的轨迹分离、首次分离帧、各自目标包络、动作 jitter／跳变／限位、碰撞、安全停止和
  Return handoff。
- latest-current-chunk 无论结果如何都保持 diagnostic-only，不得直接替换默认策略。

结果解释固定为：

| 闭环结果 | 允许的解释 |
| --- | --- |
| legacy 下两个目标已到达不同位置 | 原离线失败可能主要受 teacher-forced 限制影响，暂不改默认 TA |
| legacy 趋同，latest 能分开 | TA 很可能压制目标响应，但 latest 仍不能上线 |
| 两种方式都趋同 | 更可能是目标表达、ACT 条件能力或动力学执行问题 |
| 两种方式都能分开，但 latest 更抖或越界 | legacy 平滑有价值，需要另行设计响应与连续性的平衡策略 |

若没有实际运行任何 arm，以上四类一律不得选择。

## 禁止事项

- 不训练、不重训、不创建训练 HDF5。
- 不降低 80% 响应门槛，不根据失败段调 support 或 dispatch 参数。
- 不改 planner、默认 temporal aggregation、安全阈值或 timeout。
- 不用 qpos-only、zero-qvel、请求值回显或 observable-only terrain 冒充严格 fixture。
- 不运行完整 planner、连续作业、1×10 或真实机器。
- 不覆盖任何已有工件。
- 不把离线、预检、Unity 诊断写成生产证明或“指哪挖哪”已完成。
- 不在未审查的 Unity 脏工作树上执行 `git add -A`、`clean`、`reset` 或历史压缩。

## 恢复时先执行的只读检查

```bash
cd /home/pingfan/PACT/excavator_testbed
git status --short --branch
git rev-parse HEAD
git rev-parse '@{upstream}'
git log -5 --oneline --decorate

git -C /home/pingfan/AGXUnityE85ExcavatorSim status --short --branch --untracked-files=all
git -C /home/pingfan/AGXUnityE85ExcavatorSim rev-parse HEAD

python -m testbed.cli.return_closed_loop_probe --help
```

正式 A.6 工件优先读取：

```text
.../bounded_return_closed_loop_causal_diagnostic_v1/manifest.json
.../bounded_return_closed_loop_causal_diagnostic_v1/preflight.json
.../bounded_return_closed_loop_causal_diagnostic_v1/results.json
.../bounded_return_closed_loop_causal_diagnostic_v1/report.md
```

其中 `...` 是：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/run
```

当前 runtime lock：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/run/
bounded_return_closed_loop_causal_diagnostic_v1_runtime_lock.json
```

不要再次向 v1 根执行 CLI。它是 no-overwrite 证据，下一次正式尝试必须使用新的根。

## 已完成验证

交接基线已通过：

```text
pytest: 2394 passed, 44 warnings
ruff: passed
compileall: passed
documentation inventory/architecture/changed-doc guards: passed
git diff --check: passed
```

这些结果证明 Python 实现与合同一致，不证明 Unity 闭环或物理安全结果。Unity 侧必须在修改后重新运行
Editor 编译、相关 EditMode/PlayMode 测试、协议契约测试和 Python focused tests。

## 下一轮完成标准

只有同时满足以下条件，才能说 Return 受限闭环因果诊断完成：

1. Unity 来源经过责任盘点并有可重建的干净基线。
2. 每个 arm 的完整 qpos/qvel 与地形状态实际恢复并由 observed state 验证。
3. STEP 原子记录 applied action、限幅、碰撞、安全和正式 handoff。
4. 16 臂按冻结顺序各执行一次，无补跑、换 seed 或替代入口。
5. 每臂结束均完成 zero → neutral ACK，Dig/Carry/Dump 调用数为零。
6. 新 no-overwrite 工件完整写出 manifest、preflight、逐臂 trace、结果和报告。
7. 报告明确区分因果诊断、生产默认和后续晋级证据，默认策略仍未改变。

如果严格历史地形不可恢复，必须停止并向用户陈述信息缺口，让用户在“新建确定性 fixture”与“明确
降级为 surrogate 合同”之间决策。不得替用户静默降低证据标准。
