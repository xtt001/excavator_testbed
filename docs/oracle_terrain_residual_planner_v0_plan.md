# Oracle Terrain Residual Planner v0 开发计划

> 2026-07-31 主线已切换为：
> `exact diagnostic`
> → `contact audit/A-B`
> → `Unity wall+FactoryFloor diagnostic`
> → `return-handoff/action diagnostic`
> → `return-handoff owner isolation`
> → `contact-budget freeze`
> → `continuous predictor`
> → `E0/G1/W1`
> → `bounded live`
> → `conditional 1×10`。
>
> contact evidence 阶段已经完成并冻结：补强 typed per-part/per-wall sidecar，修复
> 同一 wall-contact session 从低力升至 `>=100 kN` 时仍可能推进 ACT 的漏洞，
> 审计 18 个 expert source，并对 diagnostic-only `episode_168` 执行 seeds
> `0/1/2` 的 3 组 paired A/B。B 只允许首次连续 bucket-only、same-wall、
> finite 且 `<100 kN` 的 session；一个无接触 tick 即消耗豁免。A/B 结束后
> 必须暂停等待人工冻结 production bucket region 与接触预算。
>
> 实测为：geometry `433/433` 完成；18 个 source replay 均一次完成，但
> train `379/379` 与 holdout `61/61` dig window 全部因公平门 `invalid`，
> production inference window 为 `0`。paired A/B 的 3 对 reset fairness
> 全通过，B 在 seed 0/1 完成 carry+dump，seed 2 因第二接触 session 硬停止，
> 即 `2/3`。因果分类是 `inconclusive`，production contact budget 仍未冻结。
> `reanalysis_v4` 是读取原 6 个 rollout 的 append-only 后处理复算，
> `executed_attempt_count=0`，不是第 7 次或后续重跑。
>
> 人工审核前又获准执行一个独立 diagnostic B2：只重跑 seed 2 一次，且只把
> logical wall-contact session 的结束条件改为连续两个 clear ticks。该 run
> 通过双重 reset fairness，把 step 625 和 `627..689` 的两个 Unity physical
> sessions 经单个 step-626 `20ms` clear tick 合并为一个 logical session，
> 随后进入 carry 并完成 dump；无 boom/stick、wall drift、`>=100kN`、
> hard-bottom、stuck 或 timeout。outcome 为
> `single_clear_tick_split_supported`。这不覆盖原 paired A/B 的
> `inconclusive`，也不授权冻结 production contact budget。
>
> 又单独授权并只执行了一次 seed-1000 observe-only multi-shovel
> diagnostic。它从历史 7-dump Strict-18 resolved config 的 fresh reset 开始，
> 不续跑 cycle 8；finite `<100kN` bucket wall contact 跨任意 session、
> duration、region 和 wall 全部只记录。运行完成 6 次 dump，第 7 铲因
> hard-bottom depth-budget clearance increase 安全终止。唯一接触铲的
> 12 sessions / 21 ticks 全部 bucket-only、side-effect-free，并在接触期间
> 保持运动进展。这是 current-code、non-promotable 诊断，不授权 production
> contract 或预算。
>
> 最新单独授权的 Unity-only wall+FactoryFloor diagnostic 在用户允许定位问题后
> 进行了 create-new 诊断重跑。根因不是接触放行：`v2/v4` host 带
> `-nographics`，Unity 使用 Null renderer，四路 ACT 相机是低方差冻结灰图；
> 因而 step 331 的 `117717.805N` 是 blind-camera ACT 产生的无效物理结论。
> Unity 现已在支持图像但 graphics device 为 Null 时，于 GET_INFO/首次 capture
> 前以 `recording_camera_graphics_device_unavailable` fail closed，并把 camera
> capture 源码纳入 manifest SHA。
>
> `v5` 用真实 GPU 完成 4 次 dump 后 timeout，但人工视觉 preflight 多做了一次
> RESET，只保留为旁证；`v6` 在 step 243 因 FMOD native SIGSEGV 失败，属于
> infrastructure failure。最终公平证据 `v7` 无额外 preflight reset：RTX 5070 Ti、
> 单 RESET、与 frozen A0 首帧全部公平门差值为 0。它完成 7 次 dump，最终在第
> 7 铲 return 由既有 timeout zero→neutral ack→terminal。第 6 铲只有
> `0.02s` bucket×`Dig_ZMin_Board` 接触，peak `68.353kN`；第 7 铲 wall
> `3.98s/31.971kN peak`、FactoryFloor `3.20s/61.433kN peak`，两者均有
> motion progress。没有 boom/stick/other、`>=100kN`、stuck 或数据异常。
> append-only `report_reanalysis_v2.json` 修复了 contact post-step 与下一行
> timeout ownership 的离线归因，状态 `passed/timeout`；没有重写原 failed
> report。结果仍为 diagnostic/non-promotable，production 合同和全部 downstream
> gate 不变。
>
> 随后的 expert return→dig handoff 审计没有支持放宽既有 qpos envelope：
> v7 的最终 return 是 ACT 在 contact 前持续命令 boom 下压，先越过 qpos_1
> 上界，再与接触条件同时成为 blocker。为保持 envelope 不变，新增了只在第
> 7 次 dump 后启用的 diagnostic boom-axis PD action limiter。`v3` 因把目标
> 写死为 cell 0、而 fresh rollout 选择 cell 4，实际介入为 0；`v4` 又暴露出
> wiring 把 bucket 当前空间 cell 错当成 locked goal cell，因而 fail closed。
> 修复后 `v5` 从 locked return goal 读取 cell 2，在原 qpos_1 上界
> `0.622343` 内介入 19 ticks，进入第 8 次 dig 并完成第 8 次 dump。它是一次
> 有效的单因素因果证明，不是 production controller promotion，也不是 1×10。
>
> 随后的 owner 诊断直接重算 v7 gate。只取消 global contact override 会把
> plane-depth floor 从 prior p05 隐式切到 p50，因此仍不能在 qpos_1 越界前
> ready。保持原有效 p05-p95 深度边界，并让 contact 仅由 18D token field 6
> 决定后，离线 step 3554 ready、step 3555 才越界。首个全局 live attempt
> 因从第一铲就改变 handoff 时序而被 supersede；有效 v2 只在七次 dump 后
> 激活 owner control，step 3475 进入第 8 次 dig 并完成第 8 个 dump_end，
> 无 hard-stop violation。该证据支持 owner-conflict 因果结论，但仍是
> request-local、diagnostic-only、non-promotable。
>
> 同一 owner 诊断随后把 bounded target 扩为 10，并执行两个独立
> no-overwrite replicate。两次都在 owner 激活前重复出现第二铲
> carry-side release，随后 loaded/deep return timeout，只完成 2 dumps。
> 因而当前不能声称 diagnostic 1×10；下一单因素对象前移为 carry 的
> committed-dump boundary 与 release ordering，而不是继续调整 return
> owner、阈值或 timeout。
>
> `continuous_goal_conditioned` 已作为独立 fail-closed mode 落地。它固定
> `fallback_mode=raise`、dig/return 全程 hold，禁止 exact library、episode
> selection、state-exemplar raw-field 合成、coordinate median、nearest-expert
> snap、prior/live-current/relocate return fallback。原子 `ContinuousCutGoal`
> 只由 entry/exit 派生 direction 与 length；`LockedCutGoalExecutionPlan`
> 同时锁定 10D token、同源 18D envelope、qpos path SHA 和 diagnostic-only
> support/OOD。
>
> Python 继续唯一拥有 `ACT=0.05m / interpolation=0.01m / hard=0.24m`。
> Unity append-only `continuous_goal_worktool_sweep_input_v1` /
> `continuous_goal_worktool_sweep_measurement_v1` 使用 v2 per-joint arc-length
> subdivision，逐子段证明 `<=0.01m`，并返回 12 个 link×wall witness；旧 v1
> evaluator 保留为 diagnostic。当前仓库仍没有可信 goal→qpos predictor，
> 因此 offline preflight 在
> `continuous_goal_3d_predictor_missing` 停止，三方 live 与 conditional 1×10
> 均未解锁。

## 0Q. 2026-07-31 Diagnostic 10-Shovel Lifecycle Replicates

现有 owner-isolation runner 已改为显式接收 `target_completed_dumps`，并在
report 中以目标 cycle 而不是写死的“第八铲”识别 handoff 与终止。target 只
允许在 owner 激活门槛之后且最多为 10；collector 现在也能保留 owner 尚未
激活时的有效 early-stop 证据，而不会把它误报为 artifact failure。

gate-10 v1/v2 与已接受 gate-8 配置相比，只改变输出路径、诊断 metadata 和
`target_cycle_gate: 8 -> 10`。两次 reset fairness 的全部差值均为 0，且都
完成两次 dump 后在 cycle 2 return timeout。owner evidence 分别为
`848 inactive / 0 active` 和 `839 inactive / 0 active`，所以该结果没有检验
第七铲后的 owner override。

两个 run 都在第二铲复现同一生命周期链：

1. dig 正常转 carry；
2. bucket 在 FactoryFloor 上保持约 4 秒、force 约 66.6--66.7kN；
3. release/dump_end 在 carry ownership 内完成，没有
   `carry_to_dump_dump_committed_boundary`；
4. 状态机经 `carry_to_return_release_safety` 进入 return；
5. return 带着 61.660kg/68.385kg 残余负载重新接触并挖入土体；
6. local depth 与 qpos_1 均越出原 envelope，最终走既有
   timeout zero-action/neutral/terminal 链。

没有 boom/stick、`>=100kN`、stuck 或数据异常。该重复结果说明下一步不应
再次盲跑 10 铲，也不应修改 return timeout；应先保持 contact 和 envelope
不变，只诊断 carry 为什么在 committed dump transition 前完成 release。

## 0P. 2026-07-31 Return Handoff Owner-Isolation Diagnostic

冻结 source 是有效 GPU v7。production gate 的 contact 决策原为
`config.require_contact OR token[6]`，而该 source 的 token[6] 为 0、config
却为 true。238 个 final-return tick 的 production-service replay 与原记录
逐字段一致。

第一阶段只把 config contact override 设为 false。它没有产生 ready 帧，因为
`p50_floor` 的 plane-depth lower bound 同时从 prior p05 `0.027709m` 切到
p50 `0.304557m`。这证明 contact owner 与 depth owner 存在隐藏交叉耦合，不是
local depth 本身的新阈值问题。第二阶段把 depth 明确留给 runtime prior
p05-p95；其有效 local/plane bounds 与 v7 原 gate 完全相同。该离线反事实在
step 3554 ready，qpos_1 在 step 3555 才首次超过 `0.648137`。

全局 owner attempt 从第一轮 return 就生效，改变了较早 transition，随后走
cycle-3 carry release-safety 并在 cycle 4 return timeout；它只证明实验 scope
有混淆。有效 v2 增加 diagnostic-only delayed control：

```yaml
return_start_envelope_owner_control:
  enabled: true
  diagnostic_only: true
  min_completed_dump_count: 7
  contact_owner: token
  depth_owner: runtime_prior_p05_p95
```

因此前七次 dump 的 base gate 不变。公平 reset 全部为 0-delta；控制在完成
7 dumps 后激活。step 3475 handoff ready 并切到第 8 次 dig：qpos_1
`0.598779`，距离上界尚有 `0.049358`；local depth `0.001567m` 与 plane depth
`0.185409m` 均通过原 prior bounds。rollout 随后产生第 8 个 dump_end，并由
gate-8 正常终止；无 wall/floor contact 或 hard stop。authoritative report：

```text
/data/pingfan/excavator_testbed_runs/eval/
  yulong_strict18_terrain_residual_v0/
  return_handoff_owner_target_scoped_diagnostic_v2/
    run/report_reanalysis_v1.json
```

该结果只证明本次 owner 隔离足以解除第八铲 handoff，不直接修改 production
合同，也不解锁 predictor、E0/G1/W1、bounded live 或 functional 1x10。

## 0O. 2026-07-30 Return Handoff Boom-Axis Single-Factor Diagnostic

冻结 source 是有效 GPU `v7`。其第 7 次 dump 位于 step 3350，随后最终
return 的原始 cell-0 qpos_1 上界为 `0.648137`。ACT 在首次 contact 前已持续
输出约 `-0.55` 的 boom action；新的 `0.02` activation margin 对应
step 3550，原 run 在 step 3555 首次越过上界并同时满足 contact。单纯延长
timeout 不会改变这条动作链，放宽 qpos envelope 又没有 same-goal expert
支持，因此本诊断只改 return 末段的 boom action，不改 handoff checks。

expert support audit 的 358 个 train handoff 覆盖 cell `0..5`。每个 cell 都以
既有 `p95 + 0.04` 上界计算 `target=upper-0.016`；六个 target 均不高于对应
train maximum，最小 headroom 是 cell 1 的约 `0.000332`。controller 只在第
7 次 dump 后、locked return goal 的 qpos_1 距原上界 `0.02` 以内且仍向上运动
时介入；其余三个 action 维度、ACT checkpoint、reset、contact rules、
timeout 和 envelope 全部不变。recorder 持久化 controller lineage，若未实际
介入则报告 fail closed。

no-overwrite 诊断链保留如下：

- `return_approach_axis_limit_diagnostic_v1/v2`：prepared-only，没有 rollout；
- `v3`：reset fairness 通过并完成 7 dumps，但 fresh goal 是 cell 4，而配置
  错误写死 cell 0；intervention count 为 0，最终仍 timeout；
- `v4`：已推广到任意 locked cell，但 controller 接收到 bucket 当前空间 cell。
  locked goal 为 cell 0，bucket 在 step 3707 跨到 spatial cell 1 后触发
  `diagnostic_return_approach_axis_limit_lineage_drift`，完成 7 dumps，属于
  diagnostic wiring failure；
- `v5`：controller 改为读取 locked coverage return goal cell；reset fairness
  全部为 0-delta，goal cell 2，真实介入 19 ticks（controller steps
  `3708..3726`），ACT proposed boom action 首次约 `-0.548`，executed action
  被制动到 `+0.35`。

`v5` 的 dominant cell-2 bound 从 steps `3495..3727` 保持
`0.6223429823`；最大 checked qpos_1 为 `0.6221795082`，没有 upper-bound
violation。随后 step 3728 进入第 8 次 dig，step 4028 完成第 8 次 dump，
rollout 由 target-cycle gate 正常结束。通用 contact report 仍使用历史标签
`normal_completed_10`，但 manifest、`max_shovels=8`、dump pulses 和 stop
reason 都明确这是 gate-8 诊断，不是十铲验证。

第 8 铲无 wall/FactoryFloor contact 或 hard violation。整次 run 只有第 2 铲
出现 bucket×`Dig_ZMin_Board` 的低力接触：40 ticks / `0.8s`，normal
peak/RMS `84.846/41.377kN`，impulse `28161.825N·s`，且有 motion progress。
报告为：

```text
/data/pingfan/excavator_testbed_runs/eval/
  yulong_strict18_terrain_residual_v0/
  return_approach_axis_limit_diagnostic_v5/run/report.json
```

report SHA256 是
`e4b27b77d64c81e677e2de14d1dd36854f8e3fdf14644832132a03003d1a3d22`。
因果结论仅为：**在该公平 rollout 中，return 末段 boom overshoot 是阻止第
8 铲的真实 blocker，保持 envelope 不变的局部 action shaping 足以解除它。**
该结果不冻结 production contact budget，不把 diagnostic limiter 变成默认，
也不解锁 continuous predictor、E0/G1/W1、bounded live 或 functional 1×10。

## 0N. 2026-07-30 GPU Camera Contract Recovery And Valid Unity Diagnostic

最终可解释 root：

```text
.../unity_contact_observe_only_multicycle_diagnostic_v7/
```

根因对比锁定了 qpos/qvel、10D token、checkpoint SHA 和首次 dig 前状态：
`v4` 与历史可工作 A0 在这些字段上相同，首次视觉 ACT inference 后才分叉。
`v4` Unity 日志却明确为 `Forcing GfxDevice: Null / Renderer: Null Device`，
step-0 四相机 payload 仅约 `11.7kB`，视频无 overlay 区域跨帧完全冻结；历史
GPU run 的 payload 约 `216kB`，场景随运动变化。ACT inference latent 固定为
zero，skill switch 也已清空 temporal state，因此剩余唯一因果差异是无效相机。

修复保持协议和 107D 不变：

- `AgxSimCameraRuntimeContract` 拒绝 `GraphicsDeviceType.Null`；
- 支持图像的 GET_INFO 在任何 STEP/RESET 前返回
  `recording_camera_graphics_device_unavailable`；
- JPEG capture 本身再次 fail closed，防止绕过 GET_INFO；
- camera capture、server 和 diagnostic host test 源码一起进入 source
  lineage；live camera rollout 禁止 `-nographics`，离线 inert FK/sweep 不受影响。

重跑证据按 no-overwrite root 保留：

- `v5`：真实 GPU，2143 steps、4 dumps、timeout；但启动前的人工相机
  preflight 额外执行一次 RESET，故只作 side evidence；
- `v6`：真实 GPU，在 step 243 遇到 FMOD `AudioManager::systemCallback`
  native SIGSEGV，Python 收到 socket close；无完整 rollout，归为 infrastructure
  failure；
- `v7`：真实 GPU、3771 steps、单 RESET、process return code 0；相对 frozen
  baseline 的 qpos/qvel/bucket-tip/terrain depth/remaining mass 差值全部为 0，
  reset fairness `valid=true`。

`v7` dump pulses 位于 steps `417/845/1282/1814/2294/2834/3350`，共 7 次。
逐铲接触为：

| shovel（1-based） | dump | wall | FactoryFloor | motion |
| ---: | --- | --- | --- | --- |
| 1–5 | yes | none | none | N/A |
| 6 | yes | bucket×`Dig_ZMin_Board`, `1 tick/0.02s`, peak/RMS `68.353/68.353kN`, impulse `1367.065N·s` | none | wall 未过进展阈值 |
| 7 | yes | bucket×`Dig_ZMin_Board`, `199 ticks/3.98s`, peak/RMS `31.971/30.718kN`, impulse `122248.148N·s` | bucket×`FactoryFloor`, `160 ticks/3.20s`, peak/RMS `61.433/56.799kN`；v1 不提供 impulse | wall/floor 均有进展 |

最终 step `3770/3771` 是独立 timeout 的 zero request 与 neutral-ack terminal。
旧 report 把 step 3769 的 post-step contact 和下一行 timeout 错配为 contact
side effect。TDD 后的 shared evidence owner 只在紧邻的 timeout/stuck
zero→neutral→terminal 链完整时接受这种重叠；unsafe contact 仍不能借此绕过。
原 `report.json` 保持冻结，append-only 修正证据为：

```text
.../unity_contact_observe_only_multicycle_diagnostic_v7/run/
  report_reanalysis_v2.json
```

其 SHA256 为
`b64faeaaf4a3abedecbfe43b9dddcdcb2abf724e0049bd85bc132290a2e6dca2`，
状态 `passed`、termination `timeout`、completed dumps `7`、reset fairness
`valid=true`。`v1` reanalysis 也保持 append-only；`v2` 进一步证明 timeout
不能掩盖 timeout 前一 contact row 上已有的 safety side effect。这证明放行的
低力 bucket wall/floor contact 与历史 7-dump
功能水平相容，但不是 10-dump 成功，也不冻结 production region 或预算。

## 0M. 2026-07-30 Historical Invalid Unity Wall+FactoryFloor Diagnostic

> 本节保留 `v2` 当时的原始观察。0N 后续证明 `v2/v4` 均运行在 Null renderer
> 灰图上，因此这里的 117.7kN 不能用于接触合同判断。

执行 root：

```text
.../unity_contact_observe_only_multicycle_diagnostic_v2/
```

`v1` 只在 RESET/STEP 前的 GET_INFO preflight 暴露 action/qpos/qvel order
校验误用了简写字段；它没有 `attempt_started.json` 或 `run/`，不计作
rollout。校验改为 wire protocol 的 canonical field names 后，以 create-new
`v2` 重新锁定源码 SHA。`v2` 只有一个
`attempt_started.json`，`retry_count=0`，没有 HDF5。

与历史 7-dump A0 source 相比，reset、seed 1000、四 checkpoint、
`dataset_stats.pkl`、ACT、planner、timeout 和既有 hard threshold 均保持
source-locked。唯一诊断语义是：

- finite 且严格 `<100000N` 的 bucket wall/FactoryFloor contact 只记录；
- 不限制 session、duration、region 或 wall identity；
- ordinary contact 不得 neutral、ACT reset、replan 或 block corridor；
- 仅在显式 `agx_unity` diagnostic 中关闭 typed hard-bottom takeover 和
  hard-bottom depth-budget warning；
- `>=100000N`、boom/stick/other、invalid/non-finite lineage、stuck 和
  timeout 仍硬停止。

唯一 attempt 运行 333 steps，只开始第 1 铲并进入 carry，完成 dump 为 `0`。
wall sidecar 在 steps `331..333` 记录同一 bucket × `Dig_ZMin_Board`
session：duration `0.06s`，normal peak/RMS
`117717.805/95080.743312N`，normal impulse `5611.64844N·s`。step 331
已经超过 100kN；step 332 输出 zero neutral request，step 333 收到 neutral
ack 并 terminal。接触窗口有 qpos/tangential motion，但 bucket-tip 的大位移
包含高力冲击响应，不能解释为任务方向的有效进展。FactoryFloor contact tick
为 `0`，所以 bottom bypass 未被实测。

eval process return code 为 `0`，rollout summary stop reason 是
`box_safety:wall_contact_high_force`。严格 report 状态仍为 `failed`，blocker
是已消费 JSONL 缺少 per-row Unity diagnostic marker/contact kind，并沿用
wall event id `-1`，无法证明 strict same-event lineage。append-only
`posthoc_observational_evidence_v1.json` 只保留可直接从 canonical sidecar 和
summary 复核的高力事实，状态为 `blocked/non-promotable`。日志字段与 event-id
漏洞已在运行后用 TDD 修复；按 no-retry 约束未再次执行 rollout。该证据不授权
production contact-budget、predictor、E0/G1/W1、bounded live 或 functional
1×10。

## 0L. 2026-07-30 Current-code Observe-only Multi-shovel Diagnostic

正式 no-overwrite root：

```text
.../wall_contact_observe_only_multicycle_diagnostic_v2/
```

v2 是唯一执行 root；此前 v1 只在 final code review 前生成过 stale prestart
manifest，没有 `run/`，不构成 attempt。v2 从历史 7-dump
`act_freeze_probe_1x10_strict_prior_v1` 锁定 config、reset、四 checkpoint、
四份 `dataset_stats.pkl` 与 planner prior，再从 fresh seed-1000 reset 开始。
current ACT/eval/contact/report 代码和 Unity scene/normalization/contact lineage
也按 SHA 锁定。

唯一普通 wall-contact 语义变化是
`wall_first_touch_mode=record_bucket_all_contacts` 加显式
`wall_contact_diagnostic_observe_only_enabled=true`。finite、严格 `<100kN`
且 bucket-only 的接触不限 session、duration、region 或 wall identity，只做
观测；不得 neutral、ACT reset、replan 或 corridor block。任何
boom/stick/other/ambiguous、non-finite/invalid lineage、`>=100kN`、
hard-bottom、stuck 或 timeout 仍硬停止。一次 attempt、最多 10 铲、无重试、
不写 HDF5。

实际结果：

- 3293 steps，started shovel `7`，completed dump `6`；
- report shovel index 1（第二铲）出现 bucket × `Dig_ZMin_Board`：12
  physical sessions、21 ticks、
  `0.42s`，normal peak/RMS `73924.76/43681.23N`，normal impulse
  `15555.178944N·s`，接触期间 motion progress 为 true；
- 其余 shovel 没有 wall contact；21 个允许 tick 的 neutral、ACT reset、
  replan、corridor block 全为 0；
- 第 7 铲以
  `hard_bottom_depth_budget_guard_clearance_depth_increase` 经 neutral ack
  terminal；
- report `passed / hard_safety_stop_before_10`，reset fairness 通过，
  process return code 0。

这只证明普通 bucket wall contact 不是该次运行的终止原因；没有达到 10 dump，
也没有超过历史 7-dump 结果。不得从这一个 diagnostic 推导 production allowed
region、force/duration/impulse budget，或改变原 paired A/B 的
`inconclusive`。contact-budget freeze、continuous predictor、E0/G1/W1、
bounded live、functional 1×10 gate 全部继续为 false。

## 0K. 2026-07-30 Independent Seed-2 Session-Gap Diagnostic B2

唯一 create-new root：

```text
.../wall_contact_session_gap_diagnostic_b2_v1/
```

实验合同只有一个变量：`session_end_clear_ticks=2`。一个 clear tick 保留在当前
logical session；只有连续两个 clear ticks 才消费首次 bucket-session 豁免。
Unity 原始 physical session 计数不改，Python 只在 raw session `N→N+1`、
中间恰好一个 clear tick、新 session 从 `consecutive_contact_steps=1` 开始，
且 component/wall identity 未漂移时建立 logical bridge。boom/stick/other、
非有限或 `>=100kN` 力、wall drift、hard-bottom、stuck、timeout 仍在 ACT
inference 前走 zero→neutral→terminal。

该 root 只包含 seed-2 B2 的一个 attempt：

- `retry_count=0`、`executed_attempt_count=1`、process return code `0`；
- physical session 1 为 step `625`，physical session 2 为 `627..689`，
  二者同为 bucket × `Dig_ZMin_Board`，中间只有 step `626` 的 `0.02s`
  clear observation；
- logical session 为一个、共 `64` 个 contact ticks，peak force 分别
  `40094.2852N` 和 `39874.3242N`；
- contact 在 carry 前结束，随后进入 carry、完成 dump，并以
  `target_cycle_gate_reached` 结束；
- 双重 reset fairness 通过，hard-stop violation 为空，未写训练 HDF5。

报告 outcome 为 `single_clear_tick_split_supported`。它只推翻“seed 2 必须因
第二次独立贴壁而失败”这一窄解释；不会修改原始六次 A/B artifact 或 causal
classification。production bucket region 与 force/duration/impulse budget
仍须人工审核后冻结；continuous contract、predictor、E0/G1/W1、bounded live
和 1×10 继续禁止。

## 0J. 2026-07-29 Contact Semantics Evidence Gate

正式 evidence root：

```text
.../wall_contact_semantics_recovery_v1/
```

该阶段的三类证据必须分开解释：

- Unity geometry 是 433 条 recorded qpos path 的 inert shadow-FK audit，
  不是动作回放或 closed-loop；最大逐子段 proof 为 `0.009990016m`。
- expert replay 是 18 个 source 各一次完整 recorded-action Unity replay；
  typed lineage 完整，但 440 个 dig window 全部未通过联合公平门，因此只能描述，
  不能选择 production region/budget。
- paired A/B 是 6 次真实 one-cycle diagnostic closed-loop。三对公平门通过，
  B 的 dump/carry/contact-ended-before-carry 均为 `2/3`，seed 2 以
  `wall_contact_repeat_session` 结束。

初版 report 的 A/B extractor 误把 cycle 0 sibling return provenance 当作目标
identity drift，并拒绝 EvalSuite 的 `box_safety:` terminal 前缀。原始 artifact
不可覆盖；TDD 修复后，`reanalysis_v4` 只重新抽取原始 rollout 并记录执行次数
为 0。复算 collection 为 `passed`，但 causal classification 仍是
`inconclusive`。因此下一步仍是人工审核并冻结 bucket region 与
force/duration/impulse budget；continuous contract、predictor、E0/G1/W1、
bounded live 和 1×10 全部保持禁止。

> 2026-07-28 最新阶段覆盖：tuple-start phase-specific Unity shadow-FK 实测
> 已完成，未支持修改 start-bound 或放宽校准后的 3D 合同。
> `episode_171` 的真实 paired-handoff + expert-dig 路径 effective clearance
> 只有 `0.225414m < 0.24m`；同端点的 post-return scalar bound 还低估完整
> 工作装置位移约 `17.6mm`。cycle-0 source preamble 起点不同，禁止与 production
> bound 做数值比较。因此原 preflight `0/5` 继续生效，bounded transfer、1x10、
> 重训和 effect model 均保持暂停。

## 0I. 2026-07-28 Phase-specific Tuple-start Transition 实测

诊断入口和 no-overwrite evidence root 为：

```bash
python -m testbed.cli.build_coverage_start_transition_diagnosis prepare --help
python -m testbed.cli.build_coverage_start_transition_diagnosis finalize --help
```

```text
.../worktool_margin_calibrated_transfer_v1/start_transition_diagnosis_v2/
  measurement_input/worktool_transition_sweep_input_v1.json
  unity_measurement/worktool_transition_sweep_measurement_v1.json
  diagnosis/coverage_start_transition_geometry_diagnosis_v1.json
```

该诊断只读取冻结 artifact 和连续 qpos。cycle 0 使用 source episode 6
`0..214` 与冻结 runtime `1..137`；post-return 使用 source episode 24 中
`episode_161` handoff `2304..2308` 和 `episode_171` dig `2308..2423`。
中间 `2305..2307` 没有被 primitive 拼接遗漏，也没有用 synthetic interpolation
替代。

Unity 的通用 transition sweep 是既有 shadow-FK 的 append-only editor schema：
旧 `3 expert + 5 ACT` measurement contract 不变；新 schema 接受任意数量 recorded
path，并输出 boom/stick/bucket × 四墙共 12 组 witness、全局最小净距、自适应采样
bound 和完整 convex-cover endpoint displacement。它不移动在线 rig，也不更改
107D/step-ack 协议。

实测说明：

```text
episode_24 source expert preamble clearance: 0.379269 m
frozen cycle-0 runtime prefix clearance:      0.402612 m
episode_161 handoff -> episode_171 start:     0.320002 m
episode_171 expert dig:                       0.285414 m
post-return full-path effective:
  0.285414 - 0.05 ACT - 0.01 interpolation = 0.225414 m
```

后者低于 `hard_clearance_m=0.24`，所以删除 start margin 也不能使该 tuple 合法。
同时 paired handoff 的同端点 exact cover displacement 为
`0.092744m > 0.075173m` planner chord-sum bound。这否定“旧 start bound
过保守”的修复方向；本轮不把 bound 改小、不删 gate、不修改 planner selection。
cycle-0 两条 recorded path 都不连接 frozen live start 与 exact expert start，
因此 v2 明确将它们标为 `planner_bound_endpoint_match=false`，不输出伪比较。

cycle-0 source expert preamble 只证明训练 episode 的初始化轨迹安全，不能证明
当前 runtime prefix 会到达 `episode_24` start。因此 diagnosis 结果锁定为：

```text
start_bound_contract_change_allowed = false
bounded_live_allowed                = false
thresholds_relaxed                  = false
```

由于 production config 和候选语义没有变化，上一轮五状态 preflight 仍是当前门，
不做同配置重复 replay。下一项工作应是重新设计可证明 conservative 的
phase-specific start geometry contract，并寻找/生成同时满足 exact start transition
和 full expert-dig clearance 的 tuple；这属于新的单因素方案，不能在本阶段暗中
加入 bridge、降低 `0.24/0.05/0.01m` 或启动 live。

## 0H. 2026-07-28 Calibrated Production Full-Gate Preflight

新的配置和只读 production replay 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  worktool_margin_calibrated_transfer_v1/
    configs/bounded_transfer_v1.yaml
    production_preflight_v2_1/
      coverage_execution_production_preflight_v2.json
```

artifact SHA256 为
`20db8124e3f8f53ba8d1a09c3b345625a02cc9411abd6918fd7b060f1b04dba1`，
并锁定七个 production selector/gate 实现文件的 SHA256。
新 `coverage_execution_production_preflight_v2` 使用生产
`CoverageExecutionLibraryRuntime` 和配置中的 `hard_clearance_m=0.24`，覆盖五个
必须状态并保留每个状态全部 374 条 tuple trace。Gate 结果为：

```text
cycle0:       278 wall-2D + 96 worktool-3D reject
post-return0: 278 wall-2D + 87 start + 9 worktool-3D reject
post-return1: 278 wall-2D + 87 start + 9 worktool-3D reject
post-return2: 278 wall-2D + 82 start + 14 worktool-3D reject
step2987:     219 outcome-depleted + 128 wall-2D + 27 start reject
```

cycle-0 最优 `episode_24` nominal `0.633019m`，但 reset-to-exemplar start bound
`0.689452m`，effective 为 `-0.116433m`。三条 post-return 的共同最优
`episode_171` nominal 为 `0.285414m`，paired-handoff start bound
`0.075173m`，effective 为 `0.150241m < 0.24m`。这说明校准后的剩余 blocker
不是旧的“全库 nominal 必为空”，而是 live first-start 与
reachability-supported return transition 同几何安全 tuple 没有交集。

因此本阶段在 offline gate 后停止：不得启动 3-reset bounded、diagnostic 1x3、
正式 1x10、重训或 effect-model；不得降低 `0.05m` tracking margin、
`0.24m` hard clearance、关闭 start reachability 或引入 fallback。后续单因素
诊断应分别实测 first-dig initialization→tuple start 和 paired expert/live
handoff→dig start 的 worktool clearance loss，再决定 start-bound 合同是否保守；
不能用本次 replay 声称闭环已经修正。

## 0G. 2026-07-28 Worktool Tracking 实测与 3D Margin 校准

实测固定使用 source episode 24 的相同 replay prefix `0:899` 和 strict-train
`episode_168` target segment `899:1050`。每次 reset 后先用 recorded actions
恢复相同 terrain/history/start，再做 expert continuation 或 ACT takeover，避免把
return/handoff mismatch 误记为 ACT tracking error。三次 expert replay 与五次
ACT repeat 均有 terminal zero-action/neutral ack，且不生成训练 HDF5。

证据 root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  expert_act_tracking_calibration_v1/
```

关键测量：

```text
expert replay minimum clearance: 0.286671 .. 0.295515 m
ACT repeat minimum clearance:     0.244541 .. 0.252072 m
ACT full-3D deviation P95/P99:    0.493919 / 0.529946 m
wall-clearance loss P95/P99/max:  0.043156 / 0.043701 / 0.043838 m
```

完整 3D deviation 使用 monotonic DTW 后的
`maximum_corresponding_convex_cover_point_displacement_m`，保留为 capability
诊断；它包含沿 cut 方向平移和 link rotation，不允许直接代替 wall-normal safety
margin。3D gate 的墙相关合同按全路径最小净距损失校准：

```yaml
worktool_sweep_3d:
  act_tracking_margin_m: 0.05
  pose_interpolation_bound_m: 0.01
  hard_clearance_m: 0.24
```

`0.05m` 是五次 ACT 中最大 clearance loss 加 `0.002m` FK error 后向上取整；
`0.24m` 是最小 contact-free ACT clearance 扣除同一 FK error 后向下取整。
2D coverage prefilter 的 `hard_clearance=0.30m / soft_clearance=0.45m` 是另一套
平面 corridor 合同，本次不修改。

在冻结的 374-tuple sweep 上，旧总 nominal 要求
`0.15+0.01+0.30=0.46m` 通过 0 条；新要求
`0.05+0.01+0.24=0.30m` 在后续 live-start/reachability/hard-bottom/OOD gate
之前通过 19 条。`episode_168` nominal clearance `0.288379m` 仍被新 3D nominal
gate 拒绝。更新中央默认值只解除错误的“全库必定为空”算术合同，不是 bounded
promotion，更不是 1x10 通过。

恢复 live 的顺序仍为：用新值重放 production candidate intersection；存在合法
tuple 后才运行 bounded probes；bounded gate 通过后另行批准正式 1x10。本轮
effect model、重训、A1/A2、3x10、30% freeze 和新增数据继续暂停。

## 0F. 2026-07-28 Tuple Start 与 Return Target 统一合同

中央数据 artifact：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/qc/
  strict_train_coverage_return_transition_library_v1.json
```

它从 358 条 strict-train gold return 中按
`source_episode_id + return_next_material_cycle_id` 形成 353 个 post-return 精确配对；
16 个 episode-first 和 5 个无 gold 配对 tuple 只允许 cycle 0。
`episode_168 -> episode_158` 是固定 lineage guard。artifact 同时拥有唯一的
11D reachability 归一化范围及 leave-one-out p99 阈值：

```text
RMS:        0.2242876880450012
L-infinity: 0.4098004328849277
SHA256:     65952a2932a1d1373a74b825eb4d79c24d43224ca3e2449abcd7515395ab1e86
```

production selection 的顺序为：

1. outcome/depleted、blocked corridor 和 2D wall；
2. 当前 return-start 对真实 tuple 的 paired-start reachability；
3. paired expert handoff 到 dig exemplar start 的 3D nominal precheck；
4. exhausted physical cell、hard-bottom budget 和 removed-depth OOD；
5. cell 内真实 tuple K=1 与原 A0 跨 cell 排序；
6. return 结束时用 actual live handoff qpos 执行最终 3D gate。

tuple 一旦选择，dig raw tuple、paired return ID、精确 18D start-envelope token、
valid mask 和四类 SHA 原子提交。exact path 固定
`use_prior_spatial_bounds=false`、`use_prior_qpos_bounds=false`；cell/global prior、
relocate、synthetic token 和 fallback 都不能改写它。handoff 必须通过精确
spatial/local-depth/plane-depth/contact/qpos/qvel gate。缺配对、reachability
artifact/SHA 漂移、exact timeout 或 final 3D fail 都走
zero-action -> neutral ack -> terminal。

离线 diagnosis 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  tuple_start_alignment_diagnosis_v1/
    diagnosis/tuple_start_alignment_diagnosis_v1.json
    production_preflight/resolved_config.yaml
```

三条冻结 return start 都在全局 train p01-p99 内，但 `episode_168` 的精确配对
reachability 3/3 拒绝；每条仍分别有 `35/40/61` 个 reachability alternative。
旧 cell token 3/3 接受 recorded handoff，精确 `episode_158` token 3/3 拒绝。
teacher-forced ACT 对照证明 token 会显著改变动作，但不构成闭环修正证据。

校准前的独立 blocker（历史）是 `nominal_3d_clearance_contract_blocks_all`：
374 条记录中最大
nominal clearance 为 `0.340938926m`；即使 start displacement 为 0，扣除
`0.01m + 0.15m` 后最大 effective clearance 只有 `0.180938926m`，没有记录达到
`0.30m`。因此 production replay 无合法 candidate，本阶段必须停止，不得放宽阈值、
运行 bounded live/1x10 或用旧目标 fallback。

> 2026-07-28 历史阶段记录：Unity 3D worktool sweep companion、374 条
> strict-train qpos pose path、5-fixture FK calibration、Python fail-closed
> candidate gate 和 production replay 均已实现。`episode_168` 已在三条冻结 live
> start 上 3/3 提前拒绝；但原始 pre-state 与 step 2987 replay 均没有
> `effective_clearance >=0.30m` 的替代真实 tuple。因此 bounded one-dig 和正式
> 1x10 没有运行。本阶段在 `no_3d_wall_safe_corridor` 停止，不改变
> `0.15m/0.01m/0.30m` 合同。

## 0E. 2026-07-28 Unity 3D Worktool Sweep 与 Fail-Closed 结果

实现分为三个稳定所有者：

1. `testbed.data.coverage_pose_paths` 从 materialized strict-train dig primitives
   构建 374 条完整 qpos path，并锁定 tuple/raw-fields、source、qpos order 和
   normalization SHA。
2. Unity `WorktoolKinematicSweepService` 负责 shadow FK、collision-shape ownership、
   convex cover、四墙 AGX distance 和自适应 path sampling；editor exporter 负责
   no-overwrite artifact 与 source SHA。
3. Python `CoverageWorktoolSweepService` 只消费 companion artifact，计算
   live-start bound 并在 production candidate/final guard 中执行硬门。

中央配置位于
`dig_cut_planner.coverage.actual_tuple_execution_library.worktool_sweep_3d`：

```yaml
enabled: true
profile: unity_kinematic_convex_cover_worktool_sweep_v1
hard_clearance_m: 0.30
act_tracking_margin_m: 0.15
pose_interpolation_bound_m: 0.01
artifact_path: <coverage_worktool_sweep_library_v1_1.json>
artifact_sha256: e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21
execution_library_sha256: b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614
pose_library_sha256: cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2
missing_contract: fail_closed
```

Unity artifact 对 boom/stick/bucket 的全部 active collision shapes 与
`Dig_XMin/XMax/ZMin/ZMax_Board` 精确 serialized Box 逐 pair 记录 minimum witness。
Mesh 用包含全部 collision vertices 的 convex-hull cover，输出因此是保守 lower
bound。液压杆和独立 linkage 本版不纳入。5 个隔离 native AGX hinge-chain fixture
的最大 position error 约 `1.43e-6m`、rotation error `0deg`；不移动 online rig，
通过 `2mm/0.2deg` 门。107D/step-ack 合同未修改。

证据 root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  unity_3d_worktool_sweep_v1/
```

验收结果：

```text
pose paths:                         374 strict-train, passed
Unity geometry sweeps:              374/374 valid
episode_168 frozen-start rejection: 3/3, passed
episode_168 bucket->ZMin witness:    present
initial production replay:          no_3d_wall_safe_corridor
step-2987 production replay:        no_3d_wall_safe_corridor
bounded live:                       forbidden, not run
functional 1x10:                    forbidden, not run
```

初始 replay 的 374 条候选中 278 条由 2D gate 拒绝、其余 96 条由 3D gate
拒绝；3D 中最优 effective clearance 为 `-0.216433m`。step 2987 修正状态下，
219 条 outcome depleted、128 条 2D reject、剩余 27 条 3D reject，最优值为
`-0.621955m`。这些负值主要反映锁定的
live-start-to-exemplar-start displacement conservative bound；本轮不允许据此反向
调小 ACT margin、插值界、hard clearance 或使用 fallback。只有新证据能证明存在
合法 candidate 后，才可重新进入 3-reset bounded one-dig；其 3/3 通过后才允许唯一
一次 A0 1x10。

> 2026-07-28 历史阶段记录：真实专家 tuple、四类 ID 所有权、execution-tail
> hard-bottom budget 和 per-cell LOO-p99 gate 已接入 production selector；离线
> step 2987 重放通过。随后 3-reset bounded live 的 target cycle 均选择
> `episode_168`，二维净距 `0.373659m`，但 3/3 bucket 接触
> `Dig_ZMin_Board`。当前主因锁定为
> `bucket_3d_swept_envelope_incomplete_primary`。1x10/3x10 未运行，promotion
> fail closed；下一阶段转为 Unity 3D worktool sweep。

## 0D. 2026-07-28 Actual-Tuple 执行合同与 3D Wall 分支

新的 strict-train execution library：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/qc/
  strict_train_coverage_execution_library_v1_1.json
```

它包含 374 个 dig primitive 的完整 raw fields/token、source lineage、outcome cell、
corridor、return-envelope cell、live centerline/swept physical cells、token peak、
plane-depth extraction-tail reserve 和 pre-state removed-depth grid。只允许 16 个
train source；validation 33/34 和 partial/salvage 不得进入。library SHA256：
`b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614`。

production coverage 现在采用：

1. outcome-cell attempt/depleted gate；
2. blocked corridor gate；
3. live 0.70m 2D wall/swept-cell gate；
4. `remaining_depth - token_depth - tail_reserve >= 0.02m`；
5. per-outcome-cell LOO-p99 removed-grid support gate；
6. cell 内真实 tuple `K=1`，cell 间沿用 A0 score/wall penalty；
7. final guard 只复核完整 tuple，不改写字段。

step 2987 production replay 选择 `episode_168` / source episode 24 / outcome cell 1 /
return group 0 / swept `[1,3]`；离线 wall clearance `0.373659m`，planned bottom
clearance `0.064260m`，tail reserve `0.003428m`。这证明 synthetic M0 median 已从
新变体中移除，但不是 live capability 证明。

第一次 bounded run 暴露 Unity bucket-tip measurement-box 角点切换造成的单帧
`0.22/0.44m` pose 跳变。该 run 被标记为 invalid diagnostic。exact-tuple 变体只在
首次计划前增加 3-frame pose stability（最大 frame delta `0.05m`，最多 30 steps）；
超时 fail closed。四 checkpoint、四相机、action scale、handoff/safety 和 A0
window/weight 均未改变。

随后 3 个独立 reset 的 production bounded target cycle 均逐字段执行真实
`episode_168`。结果为：

| evidence | count |
| --- | ---: |
| exact library tuple | 3/3 |
| conservative 2D clearance `>=0.30m` | 3/3 |
| typed wall contact | 3/3 |
| bucket diagnostic external shape=`Dig_ZMin_Board` | 3/3 |
| zero-action + neutral ack + terminal | 3/3 |
| bottom / stuck / timeout | 0/0/0 |

首次 wall force 分别约 `39.25/38.51/38.62kN`。前两轮在达到 planned depth 前即被
wall 截断；第三轮可评估的 actual tail 为 `0.044127m`，超过 tuple
reserve+容差 `0.023428m`。根因排序仍由 3/3 wall 决定：先进入 3D worktool sweep，
不能先启动 `v2_4_6_cut_then_extract`，也不能把事故改写成 temporal aggregation
问题。

机器证据：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_goal_execution_contract_recovery_v1/
    bounded_one_dig_pose_stable_v2/
      validation_v2/act_actual_tuple_bounded_one_dig_validation_v1.json
    root_cause_report_v4/manifest.json
```

3D 分支的最小合同为：

- query 覆盖完整 oriented bucket、boom、stick 和 serialized box walls；
- 覆盖 planned pose path 以及从 strict/live 证据得到的 execution-deviation envelope；
- 继续使用 `0.30m` hard clearance，缺 geometry/shape 时 fail closed；
- candidate trace 输出最小 3D clearance、最近 shape pair、pose/time index 和 rejection；
- `episode_168` 必须由 3D query 拒绝或独立 preflight 证明安全，之后才允许 live；
- 不得放宽墙距、复用 2D pass、切 A1/A2、启动 effect-model 或发布 bundle。

当前 gate：

```text
exact-tuple offline replay: passed
3-reset bounded live: failed, 3/3 bucket-wall
functional 1x10 / 3x10: forbidden, not run
cut-then-extract retraining: deferred behind 3D wall resolution
next implementation branch: Unity 3D worktool sweep
```

> 2026-07-27 最新阶段覆盖：第六铲 hard-bottom 离线归因完成。wall/bottom
> bookkeeping 字段所有权已修复，但不是唯一剩余问题。计划在 swept cells 上仍有
> `0.07870m` 硬底余量，ACT 实际却比 planned depth 多下探 `0.13783m`；同时 logical
> cell 4 的物理 swept cells 为 `[3,5]`。因此当前主因是
> `act_execution_capability_primary`，附加
> `data_scene_cell_semantic_mismatch`。修正 production replan 后仍无合法候选，
> bounded probe 与新 1x10 均未运行；3x10、temporal A/B、30% freeze、effect-model
> 和 planned-cut 继续暂停。

## 0C. 2026-07-27 第六铲 Hard-Bottom 诊断、Bookkeeping 与 Gate

no-overwrite artifact root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_hard_bottom_cycle6_diagnosis_v1/
```

该 root 的 `source_lock_manifest.json` 引用并锁定原失败 JSONL、HDF5、resolved config、
metadata、planner trace、summary、视频、prior、四 checkpoint/stats 和 Unity scene；
原 `functional_10cycle_a0_wall_safe_1x10_v1` 未修改、未复制覆盖、未重跑。诊断窗口只含
cycle index 5 从 dig pre-action observation 到首次 typed bottom 上升沿；neutral、
clearance 和 replan 分开记录。

锁定根因矩阵：

| 检查 | 证据 | 分类 |
| --- | --- | --- |
| planned swept depth | depth `0.364648m`，cells `[3,5]` 最小余量 `0.078700m` | 计划满足既有 `0.02m` margin |
| actual bucket trajectory | peak `0.502483m`，比 plan 深 `0.137835m` | ACT execution capability 主因 |
| contact shape | bucket-tip 余量仅 `0.006493m` | 不是其他结构先触底 |
| cell semantics | logical cell 4，center-line cell 5，swept `[3,5]` | data/scene cell semantic mismatch |

`SafetyActionDecision` 追加 `contact_kind=none|wall|hard_bottom`，并在 JSONL 输出
`box_safety_contact_kind`。状态 effect 只在 neutral ack 后应用：

- wall 只携带 `blocked_corridor_id`，`depth_exhausted_cell_id=-1`，且 typed wall
  session 必须大于 0 才能阻塞 corridor；
- hard-bottom/depth guard 只携带实际 bucket physical cell，
  `blocked_corridor_id=-1`；
- clearance 保留事件种类但 mutation id 为 `-1`，不能重复耗尽；
- policy shell 只薄调用 box-safety effect service。

coverage state 另存 `coverage_depth_exhausted_physical_cell_ids`。每个 candidate 在
prototype、selection 和 final raw-field guard 都计算 conservative 0.70m worktool
swept cells；与任一 exhausted physical cell 相交时，必须在评分前以
`swept_footprint_intersects_depth_exhausted_cell` 硬拒绝。

step 2987 的 production replay 证明：

1. 只修正 wall/bottom ownership 时，corridor 4 不再被错误耗尽且会被选中；
2. neutral ack 后正确耗尽实际 cell 5 时，corridor 4 swept `[3,5]` 与 cell 5 相交；
3. 其余 corridor 分别被 wall safety 或已有 depleted 状态过滤，最终仍为
   `no_wall_safe_corridor`。

所以“修 bookkeeping 后必然还有候选”的假设不成立。不得把 logical outcome cell
当作安全 cell，也不得为制造候选而放松 wall、attempt/depleted 或 exhausted-sweep
规则。

M0/E1/W1 对照在相同 40-frame recorded observations 上完成，证据范围固定为
teacher-forced。E1 重新验证为 strict-train `episode_354` / source episode 32；
train-only nearest-expert 索引保留 76,469 steps，明确排除 validation 33/34 和
partial/salvage。基础 comparison manifest 没有复用会互相污染的单一 policy
instance，而是先将 action 栏显式标为 blocked。随后
`goal_comparison/policy_replay_v1/manifest.json` 为三个目标分别构建同 checkpoint、
独立 reset 的 ACT instance，并以 A0 window 100 串行重放。M0 aggregate 与记录
actual action 逐帧完全一致；M0/E1/W1 aggregate 对 nearest-expert 的全轴 sign
agreement 分别为 `0.49375/0.48750/0.68750`。E1/W1 仍使用 M0 的 recorded
observations，不能当闭环反事实，但证明 goal conditioning 确实改变动作，且 M0
执行动作与相近训练专家存在差异。offline 几何、实际执行和 checkpoint action
证据共同给出唯一且无冲突的 ACT 主因，bounded M0/E1/W1 one-dig probe 的触发条件
不成立。

当前 live gate：

```text
bookkeeping ownership fix: passed
offline primary classification: ACT execution capability
data/scene physical-cell contract: unresolved
bounded probe: not run, not required
fresh A0 1x10 v2: not run, forbidden by gate
```

下一阶段必须单独定位/修复 ACT execution 或 goal conditioning，并分离 prior logical
outcome label 与 physical safety geometry。不能添加 planned-depth clamp、重训或
安全阈值放宽来掩盖根因。两项获批修复并重新通过全部离线 gate 后，才生成 fresh
preflight，并唯一运行一次
`functional_10cycle_a0_wall_safe_hard_bottom_fix_1x10_v2`。

## 0B. 2026-07-27 A0 wall-safe 修复与 1x10 结果

新增中央配置
`dig_cut_planner.coverage.wall_safety`，A0 固定为：

```yaml
enabled: true
profile: conservative_2d_worktool_swept_footprint_v1
worktool_width_m: 0.70
hard_clearance_m: 0.30
soft_clearance_m: 0.45
max_score_penalty: 1.0
missing_geometry: fail_closed
```

coverage 域现在用 live env-state 的 `long_axis`、3×2 cell count 和 cell size 重建盒内
X/Z 边界。entry→exit 线段按垂直方向的 `0.35m` 半宽膨胀；prototype 和最终 raw
fields 各检查一次。hard-rejected、final-rejected、blocked、depth-exhausted 或
depleted corridor 在评分前不可选。无候选时不复用旧目标、不 fallback，pre-policy
直接发送 zero action，neutral ack 后才 terminal。candidate JSONL/trace 保存原始
score、wall penalty、最终 score、footprint X/Z、净距、class 和 rejection reason。
该合同仍是 conservative 2D，不宣称精确预测 boom/stick/bucket 的 Unity 3D sweep。

preflight artifact：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  coverage_wall_safety_preflight_v1/coverage_wall_safety_preflight_v1.json
```

结果与锁定预期完全一致：

| cell | class | eligible | minimum clearance |
| ---: | --- | ---: | ---: |
| 0 | hard_reject | 0 | 0.1208166921m |
| 1 | hard_reject | 0 | 0.2339312894m |
| 2 | near_wall | 1 | 0.3351545641m |
| 3 | near_wall | 1 | 0.3850791080m |
| 4 | near_wall | 1 | 0.4008731379m |
| 5 | near_wall | 1 | 0.3209796224m |

正式 A0 artifact：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a0_wall_safe_1x10_v1/
```

四 checkpoint、相机顺序、handoff/safety 以及
`temporal_agg_window=100 / legacy_oldest_first` 均由 preflight/resolved config
确认。live 结果为 5 个完整 cycle，cycle 5 在 dig 后触发 hard-bottom，最终在 step
2989 以 `box_safety:no_wall_safe_corridor` neutral ack 后停止。typed wall 为
0 event / 0N / 0 session，stuck/timeout 为 0；唯一 bottom session 的恢复顺序完整，
且最低已执行 footprint 净距为 `0.3209796224m`。

强 validator 按预期拒绝：

```text
cycle_inventory_not_0_through_9:actual=[0, 1, 2, 3, 4, 5]
```

eval CLI 的通用物料 success 为 1.0，不具有覆盖此失败的权限，也没有生成
`validation/` passing artifact。

当时的首个直接观察是 recovery bookkeeping：step 2975 同时记录 planned corridor
4 和 actual bottom cell 5，旧 applier 又把 corridor 4 写为
`wall_contact_blocked_corridor`。顶部 0C 已完成该字段所有权修复及后续离线重放，
并证明 bookkeeping 不是唯一根因。不能沿用“修字段后直接重跑 1x10”的旧结论；必须先
解决 ACT execution/conditioning 和 logical/physical cell 合同。原 live artifact
继续保持只读。

> 2026-07-25 最新阶段覆盖：回归恢复主线已经完成模块级因果归因，但尚未执行生产
> 修复。3x4 bounded-live 矩阵的锁定分类为 `corridor_geometry_primary`：F0
> 2/3 wall、D1 2/3 wall、C1 0/3 wall 且 3/3 envelope、DC1 0/3 wall 且
> 3/3 envelope。当前应先补齐 candidate corridor 的 bucket swept-footprint /
> wall-inset filter，再从 A0 1x10 重进功能门；effect-model、planned-cut、A2、
> 重训、30% freeze 的执行和 functional promotion 仍保持暂停。

## 0A. 2026-07-25 回归模块因果诊断闭环

本轮新增的 `act_regression_module_diagnosis_v1` 是诊断专用接口，不改变 A0 默认
配置或 production planner 行为。最终 artifact root 是：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_regression_module_diagnosis_v1/final_verified/
```

机器可读 `evidence_matrix.json` 锁定四 checkpoint/stats、resolved base config、
四相机顺序、plan-matrix/runtime-source/config SHA、100-step aggregation 和 Unity
build/scene lineage；每个 repeat 同时保存 HDF5/JSONL SHA、initial-state check、
typed wall/bottom mask、force/session、stuck/timeout 和 terminal neutral-ack。

三类证据的边界固定为：

| evidence | 本轮结果 | 允许的结论 |
| --- | --- | --- |
| offline replay | A0/A1 第 2 铲 recorded observation 上重算 fresh/aggregate/nearest-expert 和 token 反事实 | teacher-forced 局部动作诊断；不是闭环证明 |
| bounded live | 12 个最多两铲的 F0/D1/C1/DC1 probe，全部 initial-state valid、zero-action、neutral ack、cycle-1 terminal | 用于 locked module-level causal classification；不是 1x10/3x10 |
| TX24 bridge | 未执行 | F0 2/3 已复现且 C1 达到判定门，因此 bridge trigger 不成立 |

live matrix：

| condition | corridor | raw/token depth | wall | envelope | bottom/stuck/timeout |
| --- | --- | --- | ---: | ---: | ---: |
| F0 | 原 cell 0 | 0.419068 / 0.523835 | 2/3 | 1/3 | 0/0/0 |
| D1 | 原 cell 0 | 0.243690 / 0.3046125 | 2/3 | 1/3 | 0/0/0 |
| C1 | wall-safe cell 2 | 0.419068 / 0.523835 | 0/3 | 3/3 | 0/0/0 |
| DC1 | wall-safe cell 2 | 0.243690 / 0.3046125 | 0/3 | 3/3 | 0/0/0 |

C1 的 entry/exit 为 `(0.615094,-0.439306)` 到
`(0.516926,-0.276453)`；corridor 改变包含 direction 和由 entry 派生的 return
target，不能写成逐字段完全相同。plan-matrix allowed-field diff guard 已证明 cycle
0、cut length、payload/effect intent 和非 geometry/depth 字段保持锁定。所有 safety
gate 均启用；12/12 terminal contract 通过，bottom/stuck/timeout 均为 0，最高 wall
force 91,933.62N。

预设判定器输出：

```text
category = corridor_geometry_primary
primary_modules = [corridor_geometry]
native_a0_control_required = false
```

因此本阶段的主要原因是 `operator_prior_sweep_belief` 选择靠侧壁 corridor 时缺少
bucket swept-footprint / wall inset 过滤。低 planned depth 没有单独消除 wall；
hard-bottom recovery 与最新事故无直接关系；window-20 已说明 temporal aggregation
不是唯一原因；安全 corridor 在 window-100 下 3/3 到达 carry envelope，也说明
envelope gate 不是本次事故的制造模块。

本轮只完成归因。没有修改 A0 checked-in 默认配置，没有发布 functional/frozen
bundle，没有启动 native A0 control 或 TX24 bridge，也没有恢复 effect-model、
planned-cut 或 residual planner。后续若批准修复，必须单独走：

```text
wall-safe candidate/swept-footprint filter
-> A0 1x10
-> A0 3x10
-> 重新评估 temporal A/B
-> 原 30% formal freeze
-> effect-model / planned-cut / residual planner
```

> 2026-07-23 最新阶段覆盖：strict-18 四模型训练已经完成，但当前首先是十铲功能
> 回归恢复，不是 effect-model 或坑形优化。旧 aggregate-TX24 是可完成十铲、但跟手
> 不足的功能基线；strict-18 新 ACT 当前连 A0 1x10 都未通过。effect-model、
> planned-cut calibration、30% freeze gate 的执行、重训和新增数据全部暂停；30%
> 正式标准保留，不降低。

## 0. 当前 box-emptying 实施锁定

当前数据证据与运行证据必须分开表述：strict-18 的 18/18 HDF5、307,785 steps、
293,463 个 action-loss steps、446 个 ACT cycle 和 439 个 effect cycle 已通过 replay
QC；这证明数据可训练，不证明新 ACT 已在 Unity 闭环可用。

本轮使用以下定义和安全边界：

- residual 是 3x2 cell 内从当前地形表面到 `FactoryFloor` 顶面的剩余土体积，并计入
  尚未并回地形的动态 particle / `HandleAsParticle` 质量；密度固定为 `1600kg/m3`。
- 成功条件是 remaining mass fraction 连续 3 个有效 observation 不高于 5%，若斗内
  payload 仍不低于 15kg，则先完成 dump 再 neutral-stop。
- 暂不把超挖或极浅挖覆盖作为主要优化目标，但保留硬底、盒壁、无效挖掘、低 payload、
  stuck、timeout 和 120-cycle 上限；任何安全终止/恢复都必须先实际发送 neutral action
  并收到 step ack。
- 正式训练只使用 episode `3,6,7,8,9,13,16,19,23,24,25,27,28,29,30,32,33,34`；
  33/34 只用于 validation，partial/layered salvage 禁止进入训练。
- 新 ACT 的真实冻结门是 3 个独立 reset、每个 10 cycles；planner 最终门是 3/3
  独立 empty-box rollout。未完成这些 live gate 前不得将 replay QC 写成闭环通过。
- candidate 的 `direction_x/z` 沿用现有 dig-token 合同：它是三维 cut direction 的
  水平分量。给定 cut length 与 planned depth 时，水平 reach 按
  `sqrt(length^2 - depth^2)` 计算；不得用纯水平单位向量冒充专家 direction。候选几何
  在保持 swept corridor、wall inset、目标 cell 相交的前提下约束到 strict-18
  p01-p99 support envelope，无法满足时显式过滤。

当前实现状态以 `docs/training_setup.md` 的 strict-18 小节为准。旧 T1/T2 章节标记为
deferred，后续恢复正式坑形控制时再重新启用。

### 0.1 十铲功能回归恢复状态

旧 aggregate-TX24 功能证据由
`testbed/configs/baselines/yulong_aggregate_tx24_functional_10cycle_v1.json` 锁定。
manifest 保存 resolved config、summary、rollout manifest、review、视频和四 checkpoint
SHA256，且把证据范围限制为：

- 10 次 qualified dig、10 次 dump、9 次中间 return handoff；
- `dig_area_depleted` 停止；
- source rollout 实测为 64D，而不是草案中误写的 89D；
- 无 typed wall/bottom，因此只是功能基线，不是当前安全证明。

三个 runtime regression 修复已经实现并由聚焦测试覆盖：

1. `restart_skill()` 强制 same-skill ACT reset，清空 timestep、temporal tensors、
   valid mask 和 cached chunk；hard-bottom 首次 ack 同时 invalidate return/pending dig
   plan 和 held token。
2. hard-bottom 恢复严格执行 neutral/ack、标记 exhausted cell、reset、scripted
   clearance、第二次 neutral/ack 和 fresh switch/restart。clearance 在 inference 前
   短路；恢复期间新增深度超过 0.002m 或超过 150 steps 时先 neutral 再终止。
3. normal dig-to-carry 由 train-only 374-sample
   `carry_start_envelope_v1` 连续 3 步 gate 约束，500 steps 未满足则显式
   `carry_start_envelope_timeout`。

独立 functional gate、hard-bottom probe、functional-only bundle 和 temporal A/B
promotion contract 也已实现，但 release 取决于真实 Unity 证据，不能靠单元测试发布。
当前 gate 状态是：

| gate | 状态 | 证据 |
| --- | --- | --- |
| cycle-6 hard-bottom offline gate | 关闭 | 唯一主因 ACT execution capability，附加 logical/physical cell mismatch |
| bounded one-dig probe | 未运行、不需要 | offline 证据无歧义且无冲突 |
| A0 1x10 | 失败 | 最新 `functional_10cycle_a0_wall_safe_1x10_v1` 完成 5 个 cycle，第六铲 hard-bottom |
| fresh A0 1x10 v2 | 禁止运行 | ACT/conditioning 与 cell contract 尚未修复 |
| A0 3x10 | 未启动 | fresh 1x10 是前置门 |
| A1 diagnostic 1x10 | 失败、不可升级 | 经一次性授权只改 window 100→20；仍只完成 1 次 dump，第二次 wall session 在 step 710 terminal |
| A2 | 未启动 | A1 未恢复功能且未获 promotion 资格 |
| functional bundle | 未发布 | 需要 A0 或获准替代版本 3x10 |
| formal freeze | 未恢复 | 仍保留原 30% mass 和 3x10 安全标准 |

以下是 wall-safety 修复前 A0 的历史对照，不是最新 live 结果。其第 2 铲 wall
不是被 carry early-switch 触发：step 672 payload 为
36.71kg，但 carry base/envelope 均为 false，gate 正确保持 dig。此时 bucket qpos
0.237 低于 carry-start p01 0.719，plane depth 0.532m 高于 p99 0.277m，bucket-tip
x/y 也在 envelope 外。当前具体阻塞因此是 strict-18 dig 尚未到达专家 carry-start
姿态就已碰壁；neutral/ack 后 return 又无法回到 start envelope并最终 timeout。

一次性 A1 诊断的 resolved config 已证明只有 contributor window 从 100 改为 20；
weight order/decay、checkpoint、planner 和全部 gate 不变。A1 将第 2 铲首次 wall 从
dig 后第 40 步推迟至第 60 步，并把 wall 时 payload 从 36.71kg 提高到 52.37kg、
plane depth 从 0.537m 降到 0.517m、bucket qpos 从 0.243 提高到 0.296，说明缩短
窗口有方向性作用。但 carry envelope 仍为 false；neutral ack 后立即出现第 2 次 wall
session并按合同 terminal。平均 entry error 仅改善 6.79%，exit error 恶化 30.91%，
depth absolute error 恶化 4.39%，完整 cycle deposit fraction 恶化 18.32%。因此这次
A1 不通过功能门，也明显不满足 promotion 条件；A0 配置已按原 SHA256 恢复，A2
继续禁止启动。

另一个 `return_to_dig_max_entry_error_m=0.10` 诊断在 return 深度约 0.604m 时触发
hard-bottom depth-budget neutral；机构惯性在连续零动作下继续到约 0.618m，超过
0.002m 恢复增深上限，因此安全终止。它说明 fail-closed 生效，也说明 return 闭环
仍会向硬底发散；不得靠放宽安全阈值把它记成通过。

只有某个版本先通过 1x10、再通过 3x10，才生成 `functional_baseline_only` bundle。
本次 A1 是一次不具升级资格的诊断例外，不改变 promotion 顺序，也不能作为 A2 的
predecessor。A2 仍只能从最近被正式接受的版本改为真实 action-age
`exp(-0.01*age)` 权重。最终接受版本通过后，才恢复 30% formal freeze；effect-model
与 planned-cut 路线继续等待正式 frozen ACT。

### 0.2 历史 live freeze 证据（已被功能回归门覆盖）

四个 strict-18 ACT 训练 run 已全部完成，四个 `policy_best.ckpt` 均可 strict-load：

| primitive | checkpoint SHA256 |
| --- | --- |
| dig | `86c27e19904b4be7dbb4173b6e8b2b07a9280166f12e51d1aaa03b3e2d42d38f` |
| return | `443f5396ff238107f0cda26555be435cb4da2bcf31b4735333e9b38ac96b67d1` |
| carry | `44d389a48d0f170e00c6757ecad02db77a8b24a01b4d9150ce7783f0f87f1322` |
| dump | `b4f4c919ea75dc584b689e2ec68bf7e222a5e4713633f7e8574ac7469d2f537b` |

live eval 使用 train-only strict prior、四相机顺序
`stick_up,stick_down,eye_left,eye_right`、107D source-residual/contact 协议和真实
Unity editor scene。2-cycle smoke 已完成 1 个完整有效 cycle 且无 safety failure；
三次 10-cycle probe 则分别在第 8 铲触底后的 carry 撞壁、return timeout、以及第 3 铲
carry 撞壁处停止。当前最佳 probe 为 7 个完整有效 cycle、remaining mass 下降
8.84%；推理 P95 为 36.25ms。

这意味着当前状态是：

```text
ACT training completed
-> real closed-loop freeze gate failed
-> no frozen bundle
-> effect training intentionally not started
```

已实现的 hard-bottom carry swing guard 会在 neutral ack 后、bucket 清出 DigArea plane
前抑制 swing；它消除了对应 probe 的墙碰撞，但没有解决 return/carry 的全部分布外
恢复。专用 freeze 配置把 return entry gate 从 0.55m 调到 0.65m，因为实测 0.626m
状态已经满足 strict-18 start envelope，且仍低于对应 cell 的 train-only expert radial
p95 0.889m；该调整消除了同类 return timeout，但后续独立 reset 仍出现 carry wall
contact。

冻结门中的 30% remaining-mass 下降也需要单独复核：当前初始 remaining mass 为
7407.28kg，10 cycles 达到 30% 需要平均净减少约 222.22kg/cycle；目前最佳 7 个有效
cycle 合计减少 654.51kg，约 93.50kg/cycle。未获得用户明确批准前不得修改 30% 门，
也不得用短程 smoke 或 legacy `success` 标志替代它。

### 0.3 2026-07-23 failed-rollout diagnosis

在不改数据、checkpoint 或运行阈值的前提下，对现有失败 rollout 做了逐步只读审查。
当前证据不支持“primitive 切换后第一批动作因相机顺序、归一化或静态 action scale
错误而立即失控”：

- carry wall contact 分别发生在 carry 切换后的第 56 和第 79 步；
- legacy return wall contact 发生在 return 切换后的第 114 步；
- strict-prior return 的 hard-bottom contact 发生在第 326 / 333 步，timeout 在第
  419 步；
- train/live 相机顺序均为
  `stick_up,stick_down,eye_left,eye_right`，JPEG 都是 top-to-bottom RGB，训练和推理
  使用相同 ImageNet normalization；
- live 直接发送 ACT 的四轴 unnormalized action，host 侧没有第二次 action scale；
  action 轴、语义以及 Unity scene 的 target-speed 上限
  `[0.7,0.1,0.1,0.2]` 与数据的 current-controller target contract 一致；
- return live token 为 18D
  `return_start_envelope_tokens_v1`，失败长段使用 train-derived cell token，未走
  zero/fallback token。

主要诊断结果是：

1. **carry handoff 与训练边界不一致。** 20/20 个 live carry 起点都超出 train
   primitive-start min/max。最明显的是 bucket qpos：live 为 `0.166-0.530`，train
   为 `0.679-0.998`；bucket relative x：live `0.272-0.845`，train
   `-1.216-0.256`；relative y：live `-0.665--0.443`，train
   `-0.396-0.200`。train dig 最后一帧和 carry 第一帧的分布基本对齐，说明问题不是
   primitive 数据拼接，而是 live `semantic_material_loaded` / hard-bottom recovery
   在专家 dig-to-carry pose 形成前过早切到 carry。
2. **regular return 起点不是主要 OOD。** 排除 wall/bottom safety 产生的 2-3 step
   micro-segment 后，17 个 regular return 起点全部在 train-start min/max 内；失败
   return 是运行后逐渐离开支持区。触底前 boom qpos 约 `0.88`，已高于 train 全窗口
   p99 `0.664`；local depth 已到 `0.41-0.49m`，而 held return envelope 允许上界仅
   `0.16m` 或更低，handoff gate 因此持续失败。
3. **carry 碰壁前动作偏离近邻专家。** 以 qpos/qvel/bucket pose 近邻比较，entry065
   wall 前 expert action 中位数约为 `[0.000,0.572,0.000,0.497]`，live aggregate 为
   `[0.452,0.608,0.297,0.457]`；swing 和 stick 超出近邻 expert p05-p95。另一 wall
   样本的 stick 同样反号并超出 expert 区间。相反，return 两次触底前的 action 均在
   近邻 expert p05-p95 内，说明 return 是在 planner 未及时结束时继续执行
   expert-like 下探，而不是首步模型输出完全错误。
4. **不存在跨 primitive 的旧 chunk，但存在 primitive 内部的显著滞后。** skill
   switch 会 reset 新 active policy；从 segment 起点重放模型后，未被 safety guard
   改写的 aggregate action 与 live log 逐项一致。当前 100-step aggregator 按旧到新
   排列并令旧预测权重更大；57 / 80 / 100 个 contributor 时，平均来源年龄分别约
   `30.7 / 44.8 / 57.7` steps，即 `0.61 / 0.90 / 1.15s`。entry065 wall 时 fresh
   first action 是 `[0.123,0.611,0.177,0.630]`，而 aggregate 已漂到
   `[0.452,0.608,0.297,0.457]`。return timeout 前 fresh boom action 已反向为
   `+0.175`，aggregate 仍为 `-0.177`。
5. **hard-bottom same-skill replan 有确定的 runtime 缺口。** 第二次 return 触底后，
   runtime 正确发送 neutral 并收到 ack，但 `next_skill=return` 触发同技能 early
   return，没有 reset return ACT，也没有替换 held return token。接下来在 typed
   bottom contact 仍持续时恢复发送约
   `[-0.011,-0.398,-0.081,-0.021]`，最终 timeout。这不满足“hard bottom neutral
   后必须离底/replan，且不得在 exhausted cell/corridor 继续下探”的安全意图。

另有两个训练审计问题，但目前不能把它们单独写成 live failure 根因：

- checkpoint 的 saved normalization stats 确实被 live 正确加载，但当前
  `load_data()` 用 train+validation 的 `available` episodes 计算 stats，而不是仅用
  `train_ids`；这是 validation leakage，需要在任何正式重训前修复。
- strict-18 train windows 的 controller response provenance 是混合的：carry 有
  163 个 `recording_pre_fix_v1` 与 211 个 `production` episode，return 有 155 / 203；
  action 都已校准到 current-controller target speed，但 observation transition
  dynamics 仍不完全同域。live 使用 production。该混合可能放大闭环累积误差，需要
  受控 A/B 隔离，不能仅凭相关性立即重训。

因此冻结门前的最小顺序改为：

```text
same-skill hard-bottom reset/clearance contract
-> dig-to-carry train-envelope handoff gate
-> bounded temporal-aggregation A/B
-> production-vs-pre-fix provenance A/B
-> only then decide whether retraining is necessary
```

这些是现有 107D Unity closed-loop artifact 加离线 checkpoint replay 的诊断证据；
fresh-action 和 alternative aggregation 仍是 teacher-forced counterfactual，不是新的
Unity 闭环通过证明。

本文是 `docs/llm_planner_closed_loop_terrain_conclusion.md` 的执行版开发计划。它把下一阶段目标从“接入 LLM planner”收敛为：

```text
先在仿真 ground truth 地形下，验证目标坑形 residual 是否能在多铲闭环中收敛。
```

本轮建议名称为：

```text
Oracle Terrain Residual Planner v0
```

这里的 `Oracle` 表示第一阶段使用仿真 ground truth terrain，不表示最终系统依赖真值。这里的 `v0` 表示先验证闭环规划问题是否成立，不提前承诺复杂 world model、LLM planner 或真实传感器重建方案。

## 1. 本轮目标

本轮目标不是继续证明“10 铲能跑完”，也不是证明 ACT 能厘米级跟随每一铲 entry / exit / depth。更合适的目标是：

```text
给定一个简单目标坑形，
系统使用仿真 ground truth height / removed-depth grid 计算当前 residual；
planner 根据 residual 选择下一铲 cut plan；
ACT 只执行局部 cut intent；
执行后用实际地形变化更新 residual；
多铲后，最终坑形在 bucket-aware tolerance 下接近目标。
```

这个目标比单铲 token 精准跟手更现实，也更接近最终的自动挖坑系统。ACT 的定位应是“统计上可预测的局部执行器”，而不是长期坑形控制器。

## 2. 本轮非目标

本轮明确不做以下事情：

- 不直接把 LLM 接到低层 cut selection 上。
- 不把完整 height grid 直接塞给 ACT。
- 不训练大规模端到端 grid world model。
- 不以真实传感器重建作为阻塞项。
- 不在没有 shadow evidence 的情况下直接修改生产 dig gate 语义。
- 不用 `success=1.0`、跑完 10 铲、payload 均值接近作为主要验收。

LLM/VLM 未来可以做语义任务解析、场景约束生成、失败解释和人机交互，但本轮核心闭环必须是数值的：

```text
target terrain
-> current terrain
-> residual
-> candidate cuts
-> effect / capability scoring
-> execution
-> terrain update
```

## 3. 当前问题重新定义

当前系统已经能在 10 铲左右移除整个作业区域约 70% 的土量。这说明“挖得动”和“多铲流程能跑”已经有基础，但不能证明下面三件事：

- 是否能只挖指定目标区域。
- 是否能控制边界和深度，不靠超挖换 payload。
- 是否能在多铲后让目标坑形 residual 稳定下降。

因此，本轮任务设计不能只是“继续把整块作业区域挖空”。如果目标坑形和当前默认覆盖区域高度重叠，当前 planner 可能天然就能获得较高 removed-volume 指标，无法检验新 planner 的价值。v0 任务必须把评价重点放在目标形状、边界、过挖和残差曲线上。

## 4. 目标坑形任务设计

### 4.1 Grid 粒度

第一阶段使用 dig area 坐标系离散目标坑形：

```text
target_removed_depth_grid
current_removed_depth_grid
residual = target_removed_depth_grid - current_removed_depth_grid
```

符号约定：

| residual | 含义 |
| ---: | --- |
| `> 0` | 欠挖，还需要移除 |
| `= 0` | 接近目标 |
| `< 0` | 过挖 |

建议 cell size 先设为 `0.2m - 0.3m`。理由是铲斗外包络约在 `0.5m` 量级，当前 ACT 几何误差也在 `0.2m - 0.4m` 量级。过细 grid 会制造虚假的精度要求。

### 4.2 第一阶段目标坑形 curriculum

当前基线已经能移除大量土，所以 v0 的目标坑形应从“容易但能区分形状控制能力”的任务开始。

| 阶段 | 目标坑形 | 设计理由 | 建议尺度 |
| --- | --- | --- | --- |
| T0 | 现有 rollout 目标重放审查 | 不改 planner，先把当前结果投影到 target/residual 指标上 | 使用当前作业区域 |
| T1 | 大矩形浅坑 | 与当前覆盖能力接近，但增加边界和目标深度约束 | 覆盖当前 dig area 的 `50% - 70%`，深度 `0.20m - 0.30m` |
| T2 | 长条浅槽 | 检验方向、中心线、边界和连续多铲覆盖 | 宽约 `1` 个 bucket footprint，长不少于 `1.5 - 2` 个 bucket footprints |
| T3 | 双深度台阶坑 | 检验 residual 分区和避免把浅区挖深 | 浅区 `0.15m`，深区 `0.25m - 0.35m` |
| T4 | 斜坡过渡坑 | 检验连续深度场和边界过渡 | 放到 v0 后半或 v1 |

T1 是最适合本轮首个闭环验收的任务。它不能太小，否则当前 ACT 的位置误差会让任务不可判定；也不能覆盖全作业区，否则基线的“挖空倾向”会掩盖形状控制问题。

### 4.3 评价区域

每个目标坑形都应拆成三个区域：

| 区域 | 用途 |
| --- | --- |
| target interior | 评价欠挖、深度误差、目标体积完成率 |
| boundary tolerance band | 给 bucket footprint 和 ACT 几何误差留合理容差 |
| outside protected area | 评价目标外过挖和形状破坏 |

第一版 boundary tolerance 建议不小于半个 bucket 尺度，可从 `0.25m - 0.30m` 开始；如果使用完整 bucket footprint 容差，可以上调到 `0.45m - 0.55m`。两种口径都应记录，避免把早期系统误判为“完全失败”或“虚假成功”。

## 5. Payload 与形状目标的权重原则

payload 不能被简单降成很低权重。payload 是作业效率、运输效率和每铲经济性的核心指标；如果 planner 只追求形状而让每铲装载过低，系统会变成低效的“刮土器”。

但 payload 也不能成为硬目标并压过形状约束。土体过挖通常不可逆，如果 ACT 因 payload 不足而在同一位置持续下探，最终坑形会被牺牲。

因此，本轮采用三层优先级：

| 层级 | 内容 | 规则 |
| --- | --- | --- |
| 硬约束 | 安全、可达性、局部最大过挖、目标外保护、ACT 高风险 cut | 违反则候选 cut 直接不可选 |
| 主目标 | 正 residual 下降、负 residual 可控、边界误差可控 | 决定任务是否成功 |
| 效率目标 | payload、cuts-to-convergence、return/carry/dump 成本 | 在不破坏形状的前提下优化 |

### 5.1 分阶段权重

建议 scoring 使用阶段自适应权重，而不是固定把 payload 设得很低。

| 阶段 | 触发条件 | 权重倾向 |
| --- | --- | --- |
| bulk phase | 大部分 target interior 仍为正 residual | residual reduction 和 payload 都重要，overdig 仍是硬惩罚 |
| finish phase | 剩余 residual 小、接近边界或目标深度 | overdig、boundary、depth RMSE 权重升高，payload 变成软目标 |
| recovery phase | 上一铲 low payload 或偏离目标 | 优先换到仍有正 residual 的区域补 payload，不在已够深区域继续下探 |

参考评分函数：

```text
score(cut) =
  A_phase * expected_positive_residual_reduction
+ F_phase * payload_efficiency_bonus
- B_phase * expected_overdig_volume
- C_phase * overdig_risk
- D * effect_uncertainty
- E * return_or_alignment_cost
- G_phase * boundary_violation
- H * repeated_low_payload_risk
```

其中 `F_phase` 不是无限增益。payload bonus 应该是带饱和的软目标：

```text
低于最低有效 payload: 扣分或触发 low_payload outcome
处在目标 payload band: 加分
超过目标 payload band: 不继续加分，必要时因过挖风险扣分
```

### 5.2 Dig gate 的原则

dig gate 需要引入 shape guard。核心规则是：

```text
payload 不足只能在局部 residual 仍为正时支持继续挖；
如果局部 residual 已接近 0 或 depth budget 用尽，payload 不足不能继续驱动下探。
```

建议 shadow 阶段先记录这些分支，不立即改变生产行为：

| 条件 | gate 行为 |
| --- | --- |
| payload 不足，局部 positive residual 仍明显 | 允许继续浅切或小范围修正 |
| payload 不足，局部 residual 已接近 0 | 停止当前 dig，记录 `low_payload_shape_guard_stop` |
| payload 达到最低 carry 价值，shape budget 接近上限 | 进入 carry/dump |
| payload 太低，但当前 cut shape budget 已耗尽 | 结束当前 cut，记录 low_payload outcome，由下一铲换区域补 |
| 继续挖会高概率 overdig | 停止 dig，禁止用 payload 需求覆盖 overdig 风险 |

这会把“补 payload”的责任从 ACT 的持续下探，转移到 planner 的下一铲选择。它保留 payload 的效率地位，但不允许 payload 破坏已达标的局部形状。

## 6. 系统模块计划

### 6.1 TerrainStateProvider

从第一天就按未来真机接口设计，但仿真实现直接使用 ground truth。

建议输出：

```text
elevation_grid
removed_depth_grid
confidence_grid
valid_mask
frame_id
timestamp
cell_size_m
origin_in_world
```

第一阶段：

- 仿真实现使用 ground truth height / removed-depth。
- confidence 可先全 1，但接口保留。
- 真机实现不作为本轮阻塞项，未来可接多相机重建、LiDAR、depth sensor 或其他 terrain reconstruction。

### 6.2 Bucket-aware residual metrics

新增任务级坑形评价，不再只看逐铲跟手和 payload 均值。

核心指标：

| 指标 | 含义 |
| --- | --- |
| final positive residual volume | 最终欠挖体积 |
| final overdig volume | 最终过挖体积 |
| target removed volume completion | 目标挖方完成率 |
| outside protected overdig volume | 目标外过挖 |
| shape IoU after dilation | bucket-aware 形状 IoU |
| boundary error | 边界偏差 |
| depth MAE / RMSE | 目标区域深度误差 |
| local extreme overdig count | 局部极端过挖事件 |
| residual convergence curve | 每铲后的正/负 residual 曲线 |
| payload mean / variance | 效率稳定性 |
| cuts to convergence | 达到目标所需铲数 |

第一版建议阈值：

- 目标体积完成率：`70% - 85%`，随任务逐步收紧。
- 过挖体积：不高于目标挖方体积 `10% - 15%`；早期可放宽到 `20%` 做诊断。
- depth RMSE：先用 `8cm - 12cm` 作为 bucket-aware 可接受范围。
- 局部极端过挖：任何局部超过目标深度 `15cm` 以上标红。
- boundary error：第一阶段控制在一个 bucket footprint 内。

### 6.3 Discrete cut candidate generator

第一版不要做连续优化。每一轮从正 residual 最大、置信度最高、可达的区域附近生成 `20 - 100` 个候选 cut。

候选 cut 至少包含：

- entry
- exit
- cut direction
- target penetration
- target payload band
- maximum local depth budget
- cut length
- cut footprint estimate
- return/alignment cost estimate

候选深度建议取 residual 分位数，而不是取最大 residual，减少局部极端过挖。

### 6.4 Effect model v0

effect model v0 不应一上来预测完整高分辨率 grid。推荐 hybrid 结构：

```text
geometric bucket swept-footprint kernel
+ statistics calibration from gold samples
+ bootstrap / quantile uncertainty
```

第一阶段输入：

- cut geometry
- target penetration
- cut length / direction
- local residual patch statistics
- local slope
- cycle index
- handoff distance
- bucket pose summary
- previous outcome summary

第一阶段输出：

- expected removed volume
- expected payload
- expected centerline offset
- expected effective footprint
- expected overdig volume
- uncertainty
- 可选低分辨率 delta patch，例如 `8x8` 或 `16x16`

训练和评估要求：

- 使用 episode split，不使用随机 sample split，避免同一 rollout 相邻铲泄漏。
- 不追求每个 cell 的精确预测，优先评估 ranking quality。
- 通过标准是 top-1 / top-3 candidate 在真实或回放评估中能稳定降低 positive residual，且不显著增加 overdig。

### 6.5 Capability filter

capability model 不负责预测挖掉多少土，只判断 ACT 对某个 cut 是否可靠。

第一版可以从规则和浅模型开始：

```text
P_success
P_overdig
P_low_payload
```

输入特征：

- cut 几何特征
- 当前 bucket / base 姿态
- entry / exit 相对位置
- local residual patch
- local slope
- 上一铲 outcome
- handoff 误差
- target penetration / cut length / cut angle

初始实现可以是统计规则、logistic regression、random forest、gradient boosted trees 或小 MLP。570 条左右 gold 样本不适合直接支撑复杂模型，但足够建立低维可解释的 capability filter。

### 6.6 Residual planner v0

planner v0 流程：

```text
1. task spec 生成 target_removed_depth_grid
2. TerrainStateProvider 给出 current_removed_depth_grid
3. 计算 residual
4. 从正 residual 区域生成候选 cut
5. effect model 预测每个 cut 的效果
6. capability filter 去掉高风险 cut
7. scoring function 选择下一铲
8. 压缩为 dig_cut_tokens / local cut intent
9. 交给现有 ACT 执行
10. 执行后更新 terrain state，再进入下一轮
```

集成时保留现有 return 阶段提前生成 `pending_dig_cut_*` 的机制：

```text
dig 结束后记录 outcome
-> carry / dump 阶段更新 terrain state
-> return 前半段生成候选 cut
-> return 后半段锁定 pending dig cut
-> handoff 前只允许小范围修正
```

目标锁定很重要。return 快到位时如果 target 频繁跳变，会造成 handoff 抖动，并把 planner 问题伪装成 ACT 跟手问题。

## 7. 开发阶段与验收

### Phase 0: 指标来源和接口合同

- [ ] 明确 current removed-depth / height grid 的来源、坐标系、分辨率和时间戳。
- [ ] 给 `TerrainStateProvider` 写接口文档或最小数据合同。
- [ ] 对现有 depth 指标建立 provenance，区分 local-surface depth 与历史 plane-depth 诊断字段。
- [ ] 把 current rollout 结果投影到新 residual 指标上，作为 baseline。

通过标准：

- 指标脚本能复现当前主 run 的关键 residual / overdig / payload 数值。
- 每个指标都能追溯到明确字段和计算口径。

### Phase 1: Bucket-aware 任务级评价

- [x] 实现显式参数 target grid 生成器，支持 T1-like 矩形浅坑诊断输入。
- [x] 实现 target 内 positive residual / overdig / completion、target 外 removed-depth、residual grid，以及 current compact-grid residual summary。
- [x] 记录 latest snapshot、dig-segment residual convergence curve 和 convergence summary。
- [x] 实现 target-interior depth-error 诊断：RMSE、MAE、absolute max。
- [x] 实现 raw target-cell overlap、一格 Chebyshev / 8-neighbor dilated overlap、dual tolerance profile records（`narrow_0_30m`、`bucket_0_50m`）。
- [x] 生成 durable current-run explicit-target baseline report：`docs/oracle_terrain_residual_baseline_report.md`。
- [ ] 未完成/未声明：官方 T1 默认尺寸/深度、cell size 与 meter-derived tolerance、物理体积、官方 cycle ID、target-shape pass/fail、production planner 改进。

通过标准：

- 能回答“当前 planner 对指定坑形是否越挖越接近目标”。
- 不再用单一 `success=1.0` 判断任务完成。

Phase 1 acceptance note：

- Phase 1 现在作为诊断 baseline / evidence milestone 关闭。它可以回答当前 run 中 current planner 是否让显式目标 residual 证据朝正确方向移动。
- 当前非官方显式目标证据显示 target positive residual 和 target-interior depth error 下降；同时 raw outside-target removed-depth 明显增长，且一格 dilated mask 在当前 `3 x 2` compact grid 上饱和。因此这些事实是诊断 baseline evidence，不是 target-shape success / failure。
- 仍缺失的 provenance：cell size、origin、frame transform、height/elevation/confidence grid、physical volume conversion、official cycle ID、official target defaults。

### Phase 2: Shape guard shadow audit

- [x] 不改变生产 gate，先做 shape guard shadow audit，只记录会在何处触发。
- [x] 在 durable current-run baseline report 中统计默认 shadow events：`low_payload_shape_guard_stop`、`overdig_guard_stop`、`depth_budget_exhausted`、`outside_protected_removed_increased`。
- [ ] 分析这些 shadow events 是否会降低 overdig risk，同时不 materially 降低 payload / cycle efficiency。（当前 deferred / blocked by missing shadow-stop counterfactual evidence。）
- [ ] 继续保持 no production gate change、no official pass/fail、no official T1 defaults，直到 shadow evidence 足够明确。

Phase 2A note：

- `testbed.eval.terrain_shape_guard_shadow.build_shape_guard_shadow_audit()` 已定义 shadow-only event contract / review surface。
- 当前 contract 只读取 explicit-target baseline report 中已有 nested facts，不重新实现 target-grid、metric、projection 或 report 公式。
- 所有 threshold / payload 约束都必须由调用方显式传入；缺少证据或 threshold 时返回 `not_evaluated`，非法数值返回 `invalid_input`。
- 当前阶段仍不接 production gate、不写 run artifact、不接 `rollout_review.json` schema、不声明 eval pass/fail / planner success / official T1 default。

Phase 2B note：

- `docs/oracle_terrain_residual_baseline_report.md` 已记录当前 run 的 shadow audit report。
- 该报告使用显式非官方示例阈值，只用于 durable baseline / smoke evidence：target overdig max `0.0`、target positive residual max `0.4`、outside-target removed-depth delta max `0.0`，payload 输入缺失。
- 当前 run 中 `depth_budget_exhausted` 和 `outside_protected_removed_increased` 为 `triggered`，`overdig_guard_stop` 为 `not_triggered`，`low_payload_shape_guard_stop` 为 `not_evaluated`。
- 这些状态不是官方 threshold、production gate、eval pass/fail 或 planner success 语义。

Phase 2C note：

- `docs/oracle_terrain_residual_baseline_report.md` 已记录 current-run shadow-event impact evidence review，作为 partial evidence。
- 当前证据支持 overdig-risk signal：`outside_protected_removed_increased` 在 outside-target removed-depth delta `0.428853750229` 对显式示例上限 `0.0` 时触发，`depth_budget_exhausted` 在 latest target positive residual `0.374313589186` 对显式示例上限 `0.4` 时触发。
- 当前 artifact 可见的 payload / cycle evidence 是 actual run 结果：10 个 planned/actual cycle 记录、bucket mass out mean/min/max `61.33190612793` / `28.913818359375` / `79.430519104004` kg、deposited fraction mean/min/max `0.802401915908` / `0.572773417672` / `0.968514219634`，但 rollout review overall status 为 `needs_root_cause_audit`，`target_cycle_gate_success=false`，且 `quality_issue_count=183`、`low_cycle_deposited_fraction_count=9`。
- 影响分析仍未完成：当前 evidence 没有 shadow stop / replan counterfactual，`low_payload_shape_guard_stop` 因 payload 输入缺失未评估，也没有 guarded cycle count 或 cycle-time 证据。因此不能证明 shape guard 会降低 overdig 且不 materially 降低 payload / cycle efficiency。

Phase 2 closure note：

- Phase 2 作为 no-production-gate shadow-audit milestone 关闭：shadow audit 对 current run 是有用的 retrospective evidence，尤其暴露 outside-target removed-depth 增长风险。
- 当前 artifact 不足以证明 production shape guard 会降低 overdig，也不足以证明不会 materially 降低 payload / cycle efficiency；因此不提升为 production gate、不定义默认阈值、不声明 pass/fail。
- Phase 3A 默认入口是 offline discrete candidate generator / candidate evidence：先生成和审查候选 cut 及其离线证据，不接 production planner integration。

通过标准：

- 能证明 shape guard 是否会减少过挖风险。
- 能证明它是否会导致 payload 或 cycle efficiency 明显下降。

### Phase 3: Discrete candidate generator

- Phase 3A default entry target: offline discrete candidate generator / candidate evidence, not production planner integration.
- [x] 从正 residual 区域生成 `20 - 100` 个候选 cut。
- [x] 对候选 cut 加入 grid-cell footprint proxy、边界保护半径、depth budget 和 return/alignment proxy evidence。
- [x] 先用 heuristic scoring 跑离线排序证据，不接入 production planner。

Phase 3A note：

- `testbed.eval.terrain_candidate_generation.build_discrete_cut_candidates()` 已定义 offline-only discrete cut candidate contract。
- 该 helper 只使用显式 row-major residual grid、target mask、valid mask、grid shape、direction options、depth fraction options 和显式 min/max candidate count。
- 当前 run latest projection 使用显式非官方 target spec、方向 `row_forward` / `row_reverse` / `col_forward` / `col_reverse`、depth fraction `0.5` / `0.75` / `1.0` 生成 `24` 个候选，覆盖 positive residual target cells `[0, 2]`，结果数量落在 `20 - 100` 的显式 smoke 范围内。
- Phase 3A 本身未完成 bucket physical footprint、boundary tolerance、depth budget、return/alignment cost、heuristic effect model scoring、production planner integration、official direction/depth defaults 或 pass/fail 语义；Phase 3B 只补其中的 grid-cell proxy evidence。

Phase 3B note：

- `testbed.eval.terrain_candidate_evidence.build_candidate_constraint_evidence()` 已定义 offline-only candidate constraint/evidence contract。
- 该 helper 按输入候选顺序输出 row-major grid-cell footprint proxy、target/outside-target footprint cells、valid/invalid footprint cells、显式 Chebyshev boundary cell-radius 保护区证据、显式 max candidate depth budget evidence，以及可选 Manhattan return-alignment proxy evidence。
- 当前 run latest projection 使用 Phase 3A 候选和 smoke-only 约束 `max_candidate_depth_m=0.2`、`protected_boundary_cell_radius=1`、`return_origin_cell_index=0` 得到 evidence status `present`、candidate count `24`、depth-budget exceeded count `0`、outside-target footprint candidate count `9`、outside-protected footprint candidate count `0`、boundary saturation ratio `1.0`、return proxy min/max `0` / `1` cells，结果文件数保持 `10 -> 10`。
- 该证据仍是 grid-cell proxy，不是 physical bucket swept-footprint kernel；不做 heuristic scoring、top-k selection、production planner integration、official defaults、eval pass/fail 或 planner success 语义。

Phase 3C note：

- `testbed.eval.terrain_candidate_scoring.build_candidate_heuristic_scores()` 已定义 offline-only heuristic score evidence contract。
- 该 helper 只读取 Phase 3B `evidence_records` 和显式权重，按输入顺序输出 score records，并单独给出 deterministic diagnostic ranking；ranking 只按 total score 降序、再按原输入顺序排列，不包含 selected/top-k/action 字段。
- 当前 run 使用 smoke-only 权重 `candidate_depth_reward=10.0`、`target_footprint_cell_reward=1.0`、`outside_target_footprint_cell_penalty=2.0`、`outside_protected_boundary_cell_penalty=4.0`、`depth_budget_exceeded_penalty=5.0`、`grid_boundary_clipped_penalty=0.5`、`return_alignment_distance_penalty=0.25` 得到 scoring status `present`、score count `24`、best candidate `cut_candidate_000009` score `3.91985052079`、worst candidate `cut_candidate_000013` score `-0.33835731446`、ranking first `cut_candidate_000009`、ranking last `cut_candidate_000019`，结果文件数保持 `10 -> 10`。
- 该 scoring 是 heuristic offline evidence，不是 calibrated effect/capability model；不定义官方权重、默认 top-k、production planner 行为、pass/fail、eval success 或 planner success 语义。

Phase 3 closure note：

- Phase 3 作为 offline candidate evidence milestone 关闭：候选枚举、grid-cell proxy constraint evidence 和显式权重 heuristic scoring/ranking evidence 都已具备 focused eval owner 和 current-run smoke evidence。
- 该阶段仍没有 physical bucket swept-footprint kernel、expected delta patch、payload proxy、calibrated effect/capability model、production planner integration、official defaults、top-k selection 或 pass/fail 语义。
- Phase 4A 默认入口是 geometric swept-footprint / expected delta patch kernel，仍从 explicit-input eval owner 开始，不从 current run 推断 cell size 或 bucket geometry。

通过标准：

- 候选集覆盖主要正 residual 区域。
- 候选集不会大量包含显然越界、不可达或必然过挖的 cut。

### Phase 4: Heuristic effect model

- [x] 实现 geometric swept-footprint kernel。
- [x] 用 bucket 尺寸、entry/exit、方向、目标 penetration 生成 expected delta patch。
- [x] 输出 expected removed volume、overdig volume、payload proxy 和 footprint。

Phase 4A note：

- `testbed.eval.terrain_candidate_effect_model.build_geometric_swept_footprint_effect()` 已定义 offline-only geometric swept-footprint / expected delta patch contract。
- 该 helper 只使用显式 candidate、row-major depth grids、target / valid masks、grid shape、cell size、bucket width/length 和可选 penetration depth；当前 run smoke 使用非官方示例几何 `cell_size_m=0.25`、`bucket_width_m=0.25`、`bucket_length_m=0.5`，不从当前 run 推断这些值。
- Footprint model 明确是 `centerline_rectangular_swept_footprint_approximation`，不是 calibrated bucket physics；它输出 row-major footprint cells、grid-boundary clipping、expected delta depth grid、expected removed volume、target/outside-target removed delta volume 和 overdig delta volume。
- 当前 run smoke 以 Phase 3C diagnostic best candidate `cut_candidate_000009` 为输入，得到 effect status `present`、footprint `[0, 2, 4]`、clipped `true`、penetration depth `0.191985052079` from `candidate_depth_m`、expected removed depth sum / volume `0.575955156237` / `0.035997197265`、target removed delta sum / volume `0.383970104158` / `0.02399813151`、outside-target delta sum / volume `0.191985052079` / `0.011999065755`、overdig delta sum / volume `0.201641567051` / `0.012602597941`，结果文件数保持 `10 -> 10`。
- Phase 4A 本身仍不是 production planner integration、official geometry defaults、top-k action selection、calibrated effect/capability model、payload proxy、pass/fail、eval success 或 planner success 语义；entry/exit 线段证据和校准模型当时仍保持未完成。

Phase 4B note：

- `testbed.eval.terrain_candidate_effect_summary.build_candidate_effect_summary()` 已定义 offline-only candidate effect summary / payload proxy evidence contract。
- 该 helper 只读取 Phase 4A effect records 和显式 `payload_capacity_m3`；payload capacity 是调用方输入，不是 config/default/official bucket capacity，也不推断 material density、cycle time 或 fill model。
- 它按 effect record 输入顺序输出 summary records，包含 expected / target / outside-target / overdig volume、footprint count / clipped flag、payload proxy volume / fraction，以及 outside-target / overdig volume fractions；并输出 payload / outside-target / overdig 的 diagnostic rankings。ranking 只用于 evidence，不包含 selected/top-k/action 字段。
- 当前 run smoke 使用显式非官方 `payload_capacity_m3=0.04`，24 个 Phase 4A effect records 全部为 `present`，effect summary status `present`，payload proxy volume min / max / mean `0.005697766785` / `0.035997197265` / `0.015352705806`，payload proxy fraction min / max / mean `0.142444169625` / `0.899929931625` / `0.383817645159`。
- 当前 run max payload proxy candidate `cut_candidate_000009`，max outside-target volume candidate `cut_candidate_000003`，max overdig volume candidate `cut_candidate_000009`；结果文件数保持 `10 -> 10`。
- Phase 4B 仍不是 calibrated effect/capability model、production planner integration、official geometry/capacity default、top-k action selection、pass/fail、eval success 或 planner success 语义。

Phase 4C note：

- `testbed.eval.terrain_candidate_effect_model.build_entry_exit_swept_footprint_effect()` 已定义 offline-only explicit entry/exit swept-footprint / expected-delta evidence contract；公共入口保留在 effect model，具体实现位于 focused owner `testbed.eval.terrain_candidate_entry_exit_effect`。
- 该 helper 使用显式 entry cell、exit cell、cell size、bucket width 和 target penetration；candidate direction 被保留为 evidence，但 swept centerline 使用 entry cell center 到 exit cell center 的显式线段，不从 current run 或配置推断 entry/exit、geometry、ACT capability 或 penetration 默认值。
- 它输出 `entry_exit_path`、entry/exit segment length、target / outside-target / valid / invalid footprint cells、row-major expected delta depth grid，以及与 Phase 4A 相同口径的 expected / target / outside-target / overdig depth sum 和 volume。
- 当前 run smoke 仍以 Phase 3C diagnostic best candidate `cut_candidate_000009` 为输入，使用显式非官方 `entry_cell_index=0`、`exit_cell_index=4`、`cell_size_m=0.25`、`bucket_width_m=0.25`、`target_penetration_depth_m=0.191985052079`，得到 effect status `present`、entry/exit segment length `0.5`、footprint `[0, 2, 4]`、expected removed depth sum / volume `0.575955156237` / `0.035997197265`、target removed delta sum / volume `0.383970104158` / `0.02399813151`、outside-target delta sum / volume `0.191985052079` / `0.011999065755`、overdig delta sum / volume `0.201641567051` / `0.012602597941`，validation errors `[]`，结果文件数保持 `10 -> 10`。
- Phase 4C 仍不是 calibrated effect/capability model、production planner integration、official geometry/capacity/entry-exit default、top-k action selection、pass/fail、eval success 或 planner success 语义。

Phase 4 closure note：

- Phase 4 作为 offline heuristic effect evidence milestone 关闭：centerline rectangular footprint、entry/exit segment footprint、expected delta depth grid、expected / target / outside-target / overdig volume、payload proxy summary 和 diagnostic rankings 都已有 focused eval owner 与 current-run smoke evidence。
- 该 closure 不声明 residual planner + heuristic effect model 已优于 current planner；Phase 4 的实现项完成，但离线/仿真闭环优劣仍要到 Phase 6 baseline comparison 证明。
- Phase 5A 默认入口是 gold-sample calibration inventory / schema evidence：先确认可用于 calibration 的样本来源、字段、episode split 键和缺失项，再拟合任何 calibrated effect 或 capability model。

通过标准：

- residual planner + heuristic effect model 能在离线或仿真闭环中优于 current planner 的 target residual 指标。
- 如果不能优于 current planner，先定位 candidate 或 gate 问题，不急着训练模型。

### Phase 5: Calibrated effect / capability

- [x] 建立 gold-sample calibration inventory / schema evidence，先清点显式 source、required fields、episode split key 和 missing provenance。
- [x] 建立 observed source-field catalog / required-field gap summary，只记录原始字段存在性与显式 schema gap，不推断 alias 或 labels。
- [x] 建立 explicit calibration extraction / mapping feasibility evidence，只应用 caller-provided provisional mapping，不推断官方 schema。
- [ ] 使用 gold samples 做统计校准，修正深度增益、横向偏移、长度缩放和 payload。
- [ ] 增加 bootstrap 或 quantile uncertainty。
- [ ] 单独训练或拟合 capability filter，输出 `P_success`、`P_overdig`、`P_low_payload`。
- [ ] 使用 episode split 评估，禁止随机 sample split 泄漏。

Phase 5A note：

- `testbed.eval.terrain_calibration_inventory.build_gold_sample_calibration_inventory()` 已定义 offline-only gold-sample calibration inventory / schema evidence contract。
- 该 helper 只检查调用方显式传入的 source paths、required fields 和 episode split key candidates；目录只在显式 root 下递归枚举，不扫描整个 repo 或整个 `runs`，也不定义官方 sample schema、label 语义、episode split 语义、pass/fail、eval success 或 planner success。
- 当前支持 JSONL object records 与 JSON list-of-object records；JSON metadata dict 只作为 metadata document 报告，不当作 calibration records；unsupported files 和 parser errors 都保留为 source-level facts。
- 当前 repo smoke 检查显式路径 `runs/calibration/v2_3_reachability_live` 和 `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/frame_audit`，文件数保持 `9 -> 9` 和 `17 -> 17`。
- 使用显式非官方未来校准 required fields `candidate_id`、`expected_removed_volume_m3`、`target_removed_volume_m3`、`outside_target_removed_volume_m3`、`overdig_volume_delta_m3`、`payload_volume_m3`、`success`、`overdig_event`、`low_payload_event`，以及 split-key candidates `episode_id`、`rollout_id`、`run_id`。
- Smoke inventory status `present`，source count `26`，supported / unsupported source count `9` / `17`，total records `14639`，usable records `0`，detected split keys `[]`，records with any split key `0`，所有显式 required fields 都在 `14639` 条记录中缺失。因此当前 artifacts 还不足以拟合 calibrated effect / capability model。

Phase 5B note：

- Inventory 现在输出 `observed_field_catalog` 和 `schema_gap_summary`，只统计支持源 JSON/JSONL records 的原始 top-level fields，并按 field 名稳定排序。
- 当前 repo smoke 中 observed field count 为 `19`；全量出现字段包括 `action`、`bucket_tip_depth_plane_m`、`bucket_tip_depth_surface_m`、`bucket_tip_x_m`、`bucket_tip_y_m`、`bucket_tip_z_m`、`excavated_mass_kg`、`mass_in_bucket_kg`、`qpos`、`qvel`、`soil_grid_mass_kg`、`step_id`、`t`、`target_hard_collision_count` 和 `warnings`，`label` 出现 `11639` 次，`source_id` 出现 `6371` 次。
- `schema_gap_summary` 明确显示所有显式 future calibration required fields 都在全部 `14639` 条 records 中缺失，`episode_id`、`rollout_id`、`run_id` 也都没有出现；`usable_record_implication` 为 `no_usable_records_for_explicit_required_fields_and_split_keys`。
- 这些字段只作为 raw observed field facts 记录；当前没有把 `label`、`source_id`、payload-like mass fields 或 telemetry fields 推断成 success、payload、episode split 或 calibrated model schema。

Phase 5C note：

- `testbed.eval.terrain_calibration_extraction.build_explicit_calibration_record_extraction()` 已定义 offline-only explicit mapping/extraction evidence contract。
- 该 helper 只应用调用方显式传入的 `field_mapping`、`required_output_fields` 和 split-key candidates；不从 observed field catalog 自动推断 alias，不把 `label`、`source_id`、`mass_in_bucket_kg`、`excavated_mass_kg` 或 telemetry fields 自动解释成 success、payload、split key、pass/fail、eval success 或 planner success。
- 当前 repo smoke 使用 provisional telemetry-only mapping：`telemetry_time_s <- t`、`telemetry_step_id <- step_id`、`telemetry_label <- label`、`telemetry_source_id <- source_id`、`telemetry_mass_in_bucket_kg <- mass_in_bucket_kg`、`telemetry_excavated_mass_kg <- excavated_mass_kg`、`telemetry_soil_grid_mass_kg <- soil_grid_mass_kg`。
- Provisional smoke status `present`，source count `26`，supported / unsupported source count `9` / `17`，total source records `14639`，extracted records `14639`，usable extracted records `3371`；`telemetry_label` 缺失 `3000` 条，`telemetry_source_id` 出现在 `6371` 条记录中且只有 `1` 个 distinct group。文件数保持 `9 -> 9` 和 `17 -> 17`。
- Negative smoke 使用 explicit future calibration identity mapping 仍得到 `usable_extracted_record_count=0`，所有 Phase 5A future required fields 缺失 `14639` 条，`episode_id`、`rollout_id`、`run_id` 都未检测到。因此当前 mapping feasibility 只证明 provisional telemetry extraction 可行，不证明 calibrated effect / capability labels 已存在。

Phase 5 closure note：

- Phase 5 目前关闭为 calibration evidence / schema-readiness milestone，而不是 calibrated model milestone。
- 统计校准、uncertainty、capability filter 和 episode-split evaluation 继续保持未完成；原因是当前 inspected artifacts 没有满足显式 future calibration schema 的 usable records，也没有经确认的 official labels、split semantics、material/payload semantics 或 capability targets。
- 后续默认推进方向转入 Phase 6A 的 heuristic-only offline baseline comparison scaffold；calibrated-model 分支必须保持 `not_evaluated`，直到 gold sample schema 和可用样本被明确提供。

通过标准：

- calibrated model 的 candidate ranking 明显优于 heuristic effect model。
- `P_overdig` 对真实过挖事件有足够召回，不追求只优化平均误差。

### Phase 6: Oracle residual planner 闭环仿真

- [x] 建立 heuristic-only offline baseline-comparison scaffold，先汇总 current / heuristic / calibrated branch evidence 和限制项。
- [x] 将 Phase 6A offline baseline-comparison output / limitations 刷新进 durable baseline report。
- [x] 记录 Phase 6C closure / next-decision note，暂停继续实现，直到真实闭环仿真设计被明确 scoped。
- [x] 建立 Phase 6D closed-loop simulation design packet，先定义 T1 A/B 设计门槛，不运行仿真。
- [x] 建立 Phase 6E-A eval-only closed-loop experiment manifest / artifact contract owner，不运行仿真、不创建 `runs` artifact。
- [x] 建立 Phase 6E-B eval-only branch run plan / executable cut-intent boundary contract owner，不运行仿真、不输出 runtime action。
- [x] 建立 Phase 6E-C eval-only heuristic cut-intent generation owner，从 B branch 候选/评分/effect evidence 生成一个 future harness cut intent，不输出 production runtime action。
- [x] 建立 Phase 6E-D eval-only predicted residual update / one-cut counterfactual owner，将 selected cut-intent 的 effect delta 应用到当前 terrain evidence 并重算 before/after metrics。
- [x] 建立 Phase 6E-E eval-only predicted B-branch rollout loop，在显式小 cycle budget 内迭代更新 predicted terrain state 并输出 per-step evidence。
- [x] 建立 Phase 6E-F predicted A/B comparison report，将 current planner A evidence 与 predicted B rollout evidence 放进同一比较输出，仍不声明真实 closed-loop pass/fail。
- [x] 建立 Phase 6F-A predicted A/B artifact writer，将 in-memory manifest / branch plan / predicted B rollout / predicted A-B comparison 物化到新的非覆盖 eval results root。
- [x] 建立 Phase 6F-B predicted A/B artifact pipeline，从 source rollout JSONL 到 predicted B rollout、A/B comparison 和 artifact writer 形成一个显式 eval-only 端到端链路。
- [x] 建立 Phase 6F-C runner-facing CLI entrypoint，用显式 request JSON 调用 Phase 6F-B pipeline 并输出 pipeline result JSON。
- [x] 建立 Phase 6G-A residual eval run command plan owner，把 current A branch 的 `tb-eval` 命令改写到未来 A/B run root，并把 B branch runtime integration 缺口落到 command-plan evidence。
- [x] 建立 Phase 6G-B residual cut-intent dig-cut token adapter，将 Phase 6E-C eval-only cut intent 转成现有 primitive dig-cut raw fields / `dig_cut_tokens` 合约。
- [x] 建立 Phase 6G-C residual cut-intent runtime planner mode，使 primitive token runtime 能消费显式 provider。
- [x] 建立 Phase 6G-D residual cut-intent runtime source provider，使 `dig_cut_planner.mode=residual_cut_intent` 能从显式 durable source 构造 provider。
- [x] 建立 Phase 6G-E residual cut-intent runtime source artifact materialization，使 Phase 6F predicted A/B artifact pipeline 写出可被 Phase 6G-D provider 加载的 `residual_cut_intent_runtime_source.json`。
- [x] 建立 Phase 6G-F runner-facing B-branch eval request / invocation artifact bridge，使真实 `tb-eval` B branch config/argv 能显式指向 runtime source。
- [x] 建立 Phase 6G-G B-branch bounded smoke stop-timing contract，使 request-local config 显式用 zero terminal hold 避免 bounded smoke 请求未覆盖的 next-cycle source plan。
- [x] 建立 Phase 6G-H same-gate real A/B bounded smoke comparison，将 current A branch 和 Phase 6G-G B branch 的真实 one-cycle smoke artifacts 放进同一 durable comparison 输出。
- [x] 建立 Phase 6G-I smallest multi-cycle B request source-coverage preflight，并用显式 multi-step predicted source 完成 `target_cycle_gate=2` real A/B bounded smoke comparison。
- [x] 完成 Phase 6G-J B gate-2 no-dump 根因审查，确认 B 已消费 residual dig-cut token 且实际发生一次 dump，但 dump 后 return/handoff 链和 coverage-count 口径导致 gate 计数为 `0`。
- [x] 建立 Phase 6G-K explicit residual return-target handoff contract，使 B branch dump 后 return-target 规划使用同一 request-local residual source 的 next-cycle plan，而不是落到 `fallback_zero`。
- [x] 完成 Phase 6G-S request-local surface-depth prior counterfactual，证明在保持 6G-P mixed source / gate 设置不变时，单独换到既有 surface-depth prior 可让 B 完成 return handoff 和 gate-2 bounded smoke。
- [x] 完成 Phase 6G-T fresh gate-2 real A/B bounded smoke，并用同一显式非官方 target spec 投影 residual metrics；B 在 target residual projection 上小幅优于 A，但 deposit/depth execution quality 更差，不能声明完整 Phase 6 成功。
- [ ] 比较三组 baseline：
  - A: current planner
  - B: residual planner + heuristic effect model
  - C: residual planner + calibrated effect model + capability filter
- [ ] 对 T1/T2 目标坑形跑多铲闭环。
- [ ] 记录每铲 residual、payload、overdig、handoff、deposit quality。

Current testing audit note：

- Phase 6G-S / 6G-T closed the immediate runnable gate-2 test path after the
  return-handoff blocker: request-local surface-depth prior evidence let B reach
  gate 2, and a fresh same-gate A/B smoke reached gate 2 for both branches.
- C is not an omitted run in that smoke; it remains blocked by missing usable
  gold-sample calibration evidence and must not be replaced by telemetry
  fallback.
- The user authorized reasonable request-local default assumptions for the
  broader Phase 6 objectives. Under those assumptions, T1 is a `2 x 2` shallow
  rectangle over the `3 x 2` compact grid at `0.25m`, and T2 is a one-column
  long shallow trench at `0.25m`. These assumptions drive diagnostic artifacts
  only; they are not checked-in official defaults or pass/fail thresholds.

Phase 6A note：

- `testbed.eval.terrain_residual_baseline_comparison.build_residual_planner_baseline_comparison()` 已定义 heuristic-only offline baseline-comparison evidence scaffold。
- 该 helper 只接收显式 in-memory evidence：current rollout / target residual facts、Phase 3 candidate generation / constraint / scoring evidence、Phase 4 effect summary evidence，以及 Phase 5 calibrated branch availability evidence；不读取隐式全局路径，不启动 simulation rollout，不写 `runs` artifact，不接入 rollout-review schema 或 production planner。
- Current-run smoke 使用当前 rollout `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/rollouts/rollout_000.jsonl` 和显式非官方 T1-like target spec；comparison status `present`，current branch `present`，heuristic branch `present`，calibrated branch `not_evaluated` / `blocked_by_missing_gold_samples`。
- Smoke 中 heuristic candidate count `24`，best score candidate `cut_candidate_000009`，effect record count `24`，payload proxy fraction max `0.899929931625`，expected / target / outside-target / overdig volume totals 分别为 `0.368464939353`、`0.263189242395`、`0.105275696958`、`0.105879229144`。
- Phase 5 calibrated evidence 仍为 usable gold sample count `0`，因此 calibrated branch 只记录 blocker，不发明 telemetry fallback 或 calibrated model。检查的 results / calibration source file counts 保持 `10 -> 10`、`9 -> 9`、`17 -> 17`。
- 该 Phase 6A scaffold 不证明 B 优于 A，也不证明 C 优于 B；完整 Phase 6 baseline 仍需要真正的 closed-loop resimulation、counterfactual cycle count、cycle time、production integration boundary 和官方成功语义之外的明确评价口径。

Phase 6B note：

- `docs/oracle_terrain_residual_baseline_report.md` 已刷新 `Offline Residual Baseline Comparison` section，记录 Phase 6A comparison schema/source、三条 branch status、current-run smoke facts 和 comparison limits。
- 该 durable report refresh 只把现有 Phase 6A offline evidence 写入报告；不新增代码、不改测试、不启动新 rollout、不写 `runs` artifact、不接入 production planner，也不把 Phase 6 完整 A/B/C baseline comparison 标记完成。

Phase 6C closure / next-decision note：

- Phase 6 的 offline evidence / durable report milestone 有用：当前已经能把 current planner evidence、heuristic residual candidate/effect pipeline evidence 和 calibrated branch blocker 放进同一离线比较 scaffold。
- 但完整 A/B/C closed-loop baseline comparison 仍未完成，继续保持 deferred：当前没有新 simulation rollout、没有 counterfactual cycle count、没有 cycle-time evidence、没有 T1/T2 多目标闭环复现实验，也没有 C 分支可用 gold-sample calibration。
- 默认决策是暂停 Phase 6 implementation work，直到 Phase 6D 真实闭环仿真设计被明确 scoped。最低 design packet 必须先写清：
  - target set：T1/T2 或其他目标坑形的显式 target specs、是否为 official/default、以及 target/protected/boundary 口径；
  - cycle budget：每组 baseline 的最大 cycle 数、stop 条件、carry/dump 约束和失败处理；
  - metrics：positive residual、overdig、outside-protected removal、target completion、payload/deposited fraction、cycle count、handoff/deposit quality，以及是否记录 cycle time；
  - artifact paths：run root、rollout jsonl、planner trace、summary/comparison report 的路径和不覆盖现有证据的规则；
  - branch definitions：A=current planner，B=residual planner + heuristic effect model，C=calibrated residual planner only when usable gold samples / calibration are available, otherwise `not_evaluated`；
  - acceptance and non-goals：运行前明确验收指标和非目标，不从 smoke thresholds 推断 official defaults，不引入 production integration、runtime action selection、pass/fail、eval success 或 planner success 语义。

Phase 6D design note：

- 本节作为 Phase 6D durable closed-loop simulation design packet：它是 future runner / harness / code work 之前的 design gate，不是一次 run，也不是 production planner integration。
- Branch definitions：
  - A: current planner baseline，复用现有 current-run planner / rollout evidence。
  - B: residual planner + heuristic candidate/effect/scoring pipeline，可复用 Phase 3/4 offline eval owners，但必须先在 harness contract 中定义如何把 diagnostic candidate ranking 转成 executable cut intent，不能提前把 selected / top-k / action semantics 泄漏进 report。
  - C: calibrated residual planner，在没有 usable gold samples / calibration 前保持 `not_evaluated` / blocked，不允许从 telemetry fallback 发明 calibrated model。
- Initial experiment scope：
  - 第一轮只做 T1 A/B：large shallow rectangular pit，初始 explicit non-official target spec 保持 current smoke 口径 `grid_shape=[3, 2]`，rows `[0:2]`，cols `[0:1]`，`target_depth_m=0.25`，除非后续 design 明确修改。
  - T2 deferred until T1 A/B artifacts are comparable。
- Cycle budget and stops：
  - 初始比较预算保留 current 10-cycle baseline，除非后续 design 显式修改。
  - Phase 6E implementation 前必须明确 stop conditions：max cycles、target residual threshold、overdig / outside-protected abort、no-valid-candidate、low-payload handling、simulation/runtime failure。
- Required metrics per cycle and final：
  - positive residual、overdig、outside-target / outside-protected removal、target completion、target depth error、payload / deposited fraction、low-payload events、cycle count / stop reason、handoff/deposit quality，以及 cycle time 是否可用。
- Artifact layout / no-overwrite：
  - 建议 future run root pattern：`runs/eval/oracle_terrain_residual_phase6d_t1_ab_<timestamp>/results/`；本 slice 不创建该目录。
  - Expected files：`eval_resolved_config.yaml`、`eval_run_metadata.json`、`rollouts/<branch>/rollout_000.jsonl`、`rollouts/<branch>/rollout_000_summary.json`、`rollouts/<branch>/rollout_000_planner_trace.json`、`residual_per_cycle_report.json`、`branch_comparison_report.json`、`rollout_manifest.json`。
  - Future Phase 6E must not reuse or overwrite existing evidence under `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results/`。
- Acceptance criteria before Phase 6E：
  - design packet accepted；
  - artifact paths and branch definitions explicit；
  - no official target / pass-fail / runtime semantics inferred from smoke thresholds；
  - C branch remains blocked unless usable gold samples are available。
- Non-goals：本 slice 不运行 simulation，不写 `runs` artifact，不改代码/测试，不接入 production planner / gate / policy / runtime，不定义 official defaults、thresholds、pass/fail、eval success、planner success，也不提供 calibrated fallback。

Phase 6E default entry target：

- 先实现 eval-only closed-loop experiment manifest / artifact contract owner，固定 A/B/C branch definitions、T1 target spec、future run-root / expected-file layout 和 no-overwrite validation。
- Phase 6E-A 不运行 simulation、不创建 `runs` artifact、不接 production planner；它只让后续 runner/harness 有一个可测试、可复用、不会覆盖既有证据的 manifest contract。

Phase 6E-A note：

- `testbed.eval.terrain_residual_closed_loop_manifest.build_closed_loop_experiment_manifest()` 已定义 eval-only closed-loop experiment manifest / artifact contract owner。
- 该 helper 只接收显式输入：future `results_root`、target spec、A/B/C branch definitions、cycle budget、stop conditions、expected metric names、expected artifact files 和 protected evidence roots；它不读取隐式全局路径、不创建 run root、不写 `runs` artifact、不启动 simulation、不接 rollout-review schema 或 production planner。
- Branch order 固定为 `current_planner_baseline`、`heuristic_residual_pipeline`、`calibrated_residual_pipeline`。A branch 为 current planner baseline，B branch 为 heuristic residual pipeline 且保持 `runtime_integration_status=not_integrated`，C branch 在 `calibration_available=False` 时保持 `not_evaluated` / `blocked_by_missing_gold_samples`。
- Artifact contract 验证 expected files 必须是相对路径且不能逃逸 future results root；no-overwrite validation 会在 proposed results root 等于或嵌套在 protected current evidence root 下时返回 `protected_evidence_root_overlap`。
- Phase 6E-A 仍不完成完整 A/B/C closed-loop baseline comparison；它只把 Phase 6D 设计变成可测试 manifest shape，不引入 selected candidate、top-k、runtime action、pass/fail、eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

Phase 6E-B default entry target：

- 下一步应实现 eval-only branch run plan / executable cut-intent boundary contract owner，把 Phase 6E-A manifest 中的 A/B/C branch definitions 转换成未来 runner 可消费的 per-branch run plan。
- 重点只定义 B branch 的 diagnostic ranking 到 executable cut-intent 的边界字段和 validation 状态；不得把 ranking 提升为 selected candidate、top-k、runtime action、production planner 行为或 pass/fail / eval success / planner success 语义。
- 该 slice 仍不运行 simulation、不创建 `runs` artifact、不接 production planner、不覆盖 current evidence；C branch 继续在没有 usable calibration 时保持 `not_evaluated` / `blocked_by_missing_gold_samples`。

Phase 6E-B note：

- `testbed.eval.terrain_residual_closed_loop_branch_plan.build_closed_loop_branch_run_plan()` 已定义 eval-only branch run plan / executable cut-intent boundary contract owner。
- 该 helper 只接收显式 `experiment_manifest`、`branch_inputs` 和 `cut_intent_contract`；它验证 Phase 6E-A manifest status / branch order / artifact layout / no-overwrite evidence，并输出固定 A/B/C branch run plan records。
- A branch 只记录 current planner baseline source evidence / artifact expectations，`run_status=not_run`。B branch 只记录 heuristic residual pipeline input readiness、`runtime_integration_status=not_integrated` 和 future cut-intent boundary status，不声明 production readiness。C branch 在 calibration unavailable 时继续保持 `not_evaluated` / `blocked_by_missing_gold_samples`。
- B cut-intent boundary 只列出 future runner 需要的字段：candidate id、anchor cell / row / col、direction、candidate depth、score/rank provenance、effect/evidence provenance、target spec provenance 和 safety/stop-condition provenance；它不输出实际 selected candidate、不选择 top-k、不生成 runtime action。
- Phase 6E-B 仍不完成完整 A/B/C closed-loop baseline comparison；它只补齐 runner 前的 dry-run branch plan / intent-boundary contract，不运行 simulation、不创建 `runs` artifact、不引入 pass/fail、eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

Phase 6E-C default entry target：

- 下一步不再继续扩展外围 safety / manifest contract；按当前决策，直接实现 eval-only heuristic cut-intent generation owner，把 B branch 的 candidate generation / evidence / scoring / effect summary 结果转换成一个 future runner 可消费的 cut-intent record。
- Phase 6E-C 可以在 eval-only 范围内显式产生 `cut_intent_candidate_id` / selected cut-intent evidence，因为这是 runner 输入的核心缺口；但它仍不得生成 production runtime action、不得接 production planner、不得运行 simulation、不得创建 `runs` artifact，也不得声明 pass/fail、eval success、planner success、official defaults 或 official thresholds。
- 该 owner 必须保留 provenance：candidate source、score/rank source、effect evidence source、target spec source、safety/stop-condition source，以及为什么该 intent 可用于未来 harness 而不是当前 runtime。

Phase 6E-C note：

- `testbed.eval.terrain_residual_cut_intent.build_heuristic_residual_cut_intent()` 已定义 eval-only heuristic cut-intent generation owner。
- 该 helper 只接收显式输入：Phase 6E-B-like `branch_run_plan`、Phase 3 `candidate_generation` / `candidate_evidence` / `candidate_scoring`、Phase 4 `candidate_effect_summary`、`target_spec` 和 `selection_policy`；当前唯一实现的 policy 是 `score_ranking_first`。
- 它读取 scoring ranking 第一名，并 cross-check 同一个 candidate id 存在于 candidate generation、constraint evidence 和 effect summary records。通过后输出一个 `cut_intent`，包含 `cut_intent_candidate_id`、anchor cell / row / col、direction、candidate depth、score/rank provenance、effect evidence provenance、target spec provenance、safety/stop-condition provenance status、`runner_input_status=ready_for_eval_harness` 和 `production_runtime_action=False`。
- Phase 6E-C 是 core B-branch runner-input evidence，但仍不是 simulation 或 production planner behavior：它不创建 `runs` artifact、不写 branch output files、不输出 command-space controls、不选择 top-k、不声明 pass/fail、eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

Phase 6E-D default entry target：

- 下一步直接实现 eval-only predicted residual update / one-cut counterfactual owner：用 Phase 6E-C cut intent 对应的 Phase 4 effect delta 更新当前 removed-depth grid，并重新计算 post-cut target residual metrics。
- 该 slice 应输出 before / after residual、overdig、outside-target removal、payload proxy 和 effect provenance，用来形成 B branch 单步闭环证据；它不是新的 safety wrapper，也不应只增加合同字段。
- 仍不运行真实 simulation、不写 `runs` artifact、不接 production planner、不声明 pass/fail / eval success / planner success / official defaults / official thresholds；但它必须实际计算预测状态变化，而不只是记录边界。

Phase 6E-D note：

- `testbed.eval.terrain_residual_cut_update.build_predicted_residual_update()` 已定义 eval-only predicted residual update / one-cut counterfactual owner。
- 该 helper 只接收显式输入：Phase 6E-C cut intent 或其 nested cut-intent record、matching Phase 4 effect record、current removed-depth grid、target depth grid、target region mask、valid mask、grid shape 和可选 `cell_size_m`。
- 它验证 cut intent 为 future harness-ready 且 `production_runtime_action=False`，验证 effect record candidate id 与 cut intent candidate id 一致，并用 `expected_delta_depth_grid_m` 计算 `predicted_removed_depth_grid_m`。随后复用 `build_target_residual_metrics()` 计算 before / after metrics 和 delta summary。
- Delta summary 记录 target positive residual delta、target overdig delta、outside-target removed-depth delta、target completion ratio delta 和 expected delta depth sum；只有显式提供 `cell_size_m` 时才记录 volume deltas。
- Phase 6E-D 是单步 B-branch counterfactual evidence，仍不是真实 simulation 或 production planner behavior：它不创建 `runs` artifact、不写 branch output files、不输出 command-space controls、不声明 pass/fail、eval success、planner success、official defaults、official thresholds 或 calibrated fallback。
- Current-run planner-side smoke 中，selected candidate `cut_candidate_000009` 的 predicted update 将 target positive residual `0.374313589186 -> 0.0`，completion ratio `0.251372821628 -> 1.0`，同时 target overdig `0.0 -> 0.009656514972`、outside-target removed depth `0.488698139786 -> 0.680683191865`，这些仍只是 effect-model counterfactual evidence，不是真实 closed-loop rollout。

Phase 6E-E default entry target：

- 下一步直接实现 eval-only predicted B-branch rollout loop：用显式 cycle budget 在内存中重复执行 residual metrics -> candidate generation -> constraint evidence -> heuristic scoring -> cut intent -> geometric effect -> predicted update。
- 该 slice 应输出 per-step trace、stop reason、final before/after metrics、overdig/outside-target deltas、completion ratio 和 provenance，用来从 one-cut evidence 推进到多步 B-branch counterfactual evidence。
- 仍不运行真实 simulation、不创建 `runs` artifact、不接 production planner、不改 rollout-review schema、不输出 command-space controls、不声明 pass/fail / eval success / planner success / official defaults / official thresholds；但必须实际迭代更新 predicted terrain state，而不是只生成新的合同字段。

Phase 6E-E note：

- `testbed.eval.terrain_residual_predicted_rollout.build_predicted_residual_rollout()` 已定义 eval-only predicted B-branch rollout loop owner。
- 该 helper 只接收显式输入：Phase 6E-B-like `branch_run_plan`、initial removed-depth grid、target depth grid、target-region mask、valid mask、grid shape、target spec、cycle budget、Phase 3 candidate generation / constraint options、Phase 3C scoring weights、Phase 4 effect geometry、Phase 4B payload capacity 和 selection policy。
- 每一步都会基于当前 predicted terrain state 重新计算 target residual metrics，生成 candidates，构造 constraint evidence 和 heuristic scores，生成 geometric effects / effect summary，调用 Phase 6E-C cut-intent helper 选择 eval-only cut intent，再调用 Phase 6E-D update helper 应用 effect delta。
- 输出记录 step count、stop reason、initial / final metrics、per-step `cut_intent_candidate_id`、before / after positive residual、overdig、outside-target removed depth、completion ratio、expected delta depth / volume 和 provenance。stop reasons 是 diagnostic evidence（例如 `max_cycles_reached`、`zero_target_positive_residual`、`no_positive_residual_cells`、`no_valid_candidate_path`），不是 pass/fail 或 success 语义。
- Phase 6E-E 仍不是真实 closed-loop rollout 或 production planner behavior：它不运行 simulation、不创建 `runs` artifact、不写 branch output files、不输出 command-space controls、不声明 eval success、planner success、official defaults、official thresholds 或 calibrated fallback。

Phase 6E-E planner acceptance note：

- Planner-side acceptance split support parsing / result-assembly helpers into `testbed.eval.terrain_residual_predicted_rollout_contract` so the public rollout owner stays below the repository large-file threshold. Public behavior remains `build_predicted_residual_rollout()`.
- Current-run planner-side smoke reproduced the Phase 6E-E facts after the split: status `present`, one predicted B step, stop reason `zero_target_positive_residual`, selected candidate `cut_candidate_000009`, target positive residual `0.374313589186 -> 0.0`, overdig `0.0 -> 0.009656514972`, outside-target removed depth `0.488698139786 -> 0.680683191865`, completion ratio `0.251372821628 -> 1.0`, and no `runs` artifact writes.

Phase 6E-F default entry target：

- 下一步直接建立 predicted A/B comparison report：将现有 current planner A target residual evidence 与 Phase 6E-E predicted B rollout evidence 放进同一个比较输出，记录 branch status、initial/final residual、completion、overdig、outside-target movement、predicted step count、stop reason、calibrated C blocker 和限制项。
- 该 slice 应刷新 durable baseline report 或建立小 focused report owner（视现有 owner 边界决定），但不得把 predicted B counterfactual 写成真实 simulation 结果，不得声明 pass/fail、eval success、planner success、official thresholds 或 production readiness。

Phase 6E-F note：

- `testbed.eval.terrain_residual_baseline_comparison.build_predicted_residual_ab_comparison()` 已扩展现有 offline comparison owner，生成 Phase 6E-F predicted A/B residual comparison report。
- 该 helper 只接收显式 in-memory evidence：current planner A evidence、target residual report、Phase 6E-E predicted B rollout output 和 calibrated branch evidence。它不读取隐式全局路径、不运行 simulation、不创建 `runs` artifact、不写 branch output files、不接 production planner 或 rollout-review schema。
- A branch 输出 `evidence_type=current_rollout_evidence`，只记录 current rollout / target residual facts，target success 继续 `not_claimed`。B branch 输出 `evidence_type=predicted_counterfactual`，记录 predicted step count、stop reason、selected eval-only cut-intent candidate ids、initial / final residual、completion、overdig、outside-target movement 和 aggregate expected delta depth / volume。C branch 在 usable gold samples 缺失时继续 `not_evaluated` / `blocked_by_missing_gold_samples`。
- Current-run smoke facts: current report status `present`，predicted rollout status `present`，step count `1`，stop reason `zero_target_positive_residual`，selected candidate `cut_candidate_000009`；A positive residual / completion / overdig / outside-target removed depth 为 `0.374313589186` / `0.251372821628` / `0.0` / `0.488698139786`；B final values 为 `0.0` / `1.0` / `0.009656514972` / `0.680683191865`；expected delta depth / volume 为 `0.575955156237` / `0.035997197265`。
- Phase 6E-F 仍不是真实 A/B closed-loop comparison：B branch 是 effect-model predicted counterfactual，不是真实 simulation rollout；该输出不声明 pass/fail、eval success、planner success、official thresholds、production readiness、command-space controls 或 calibrated fallback。完整 Phase 6 baseline comparison 仍需要真实 A/B/C closed-loop run artifacts 和明确评价口径。

Phase 6F-A note：

- `testbed.eval.terrain_residual_ab_artifact_writer.write_predicted_residual_ab_artifacts()` 已定义 focused eval artifact writer，负责把 Phase 6E-F predicted A/B evidence 写成 JSON artifact。
- Current-run materialization root：
  `runs/eval/oracle_terrain_residual_phase6f_predicted_ab_20260702/results`。
- 写入文件：`eval_run_metadata.json`、`experiment_manifest.json`、`branch_run_plan.json`、`predicted_b_rollout.json`、`branch_comparison_report.json`、`rollout_manifest.json`。
- Smoke facts: writer status `present`，comparison status `present`，predicted B step count `1`，stop reason `zero_target_positive_residual`，candidate `cut_candidate_000009`，A residual `0.374313589186`，B final residual `0.0`，completion delta `0.748627178372`，overdig increase `0.009656514972`，outside-target increase `0.191985052079`，expected delta depth / volume `0.575955156237` / `0.035997197265`；protected current results file count stayed `10 -> 10`。
- Phase 6F-A 仍不是真实 simulation：它只物化 predicted counterfactual artifacts，不接 production planner，不声明 pass/fail、eval success、planner success、official thresholds、production readiness 或 calibrated fallback。

Phase 6F-B note：

- `testbed.eval.terrain_residual_ab_artifact_pipeline.build_and_write_predicted_residual_ab_artifacts()` 已定义 focused eval pipeline owner，将 source rollout JSONL、显式 target spec、cycle budget、candidate/effect/scoring/payload options 串成完整 predicted A/B artifact 生成链路。
- 该 helper 在内存中重建 target residual report、Phase 6E-A manifest、Phase 6E-B branch plan、Phase 6E-E predicted B rollout 和 Phase 6E-F predicted A/B comparison，然后调用 Phase 6F-A writer 写入新的非覆盖 results root。它不读取隐式全局配置、不运行 simulation、不接 production planner 或 rollout-review schema。
- Current-run pipeline smoke root：
  `runs/eval/oracle_terrain_residual_phase6f_pipeline_ab_20260702/results`。
- 写入文件：`eval_run_metadata.json`、`experiment_manifest.json`、`branch_run_plan.json`、`predicted_b_rollout.json`、`branch_comparison_report.json`、`rollout_manifest.json`。
- Smoke facts: pipeline status `present`，nested statuses all `present`，source record count `6148`，predicted B step count `1`，stop reason `zero_target_positive_residual`，selected candidate `cut_candidate_000009`，A residual `0.374313589186`，B final residual `0.0`，completion delta `0.748627178372`，overdig increase `0.009656514972`，outside-target increase `0.191985052079`，expected delta depth / volume `0.575955156237` / `0.035997197265`；protected current results file count stayed `10 -> 10`。
- Phase 6F-B 仍不是真实 simulation 或 production behavior：它只把 predicted counterfactual pipeline 物化为 eval artifacts，不声明 pass/fail、eval success、planner success、official thresholds、production readiness、command-space controls 或 calibrated fallback。

Phase 6F-C note：

- `tb-terrain-residual-ab-artifacts` 已作为 runner-facing CLI entrypoint 接入 `pyproject.toml`，实现位于 `testbed.cli.terrain_residual_ab_artifact_pipeline`。
- CLI 只读取显式 `--request-json`，调用 `build_and_write_predicted_residual_ab_artifacts()`，并把 top-level pipeline result 写到 `--output-json` 或 stdout。request JSON 必须携带 source rollout path、results root、target spec、cycle budget、candidate/effect/scoring/payload options、selection policy 和 protected evidence roots；CLI 不提供 official target、threshold、geometry、payload 或 scoring 默认值。
- Current-run CLI smoke root：
  `runs/eval/oracle_terrain_residual_phase6f_cli_ab_20260702/results`。
- Smoke facts: CLI return code `0`，pipeline status `present`，nested statuses all `present`，predicted B step count `1`，stop reason `zero_target_positive_residual`，selected candidate `cut_candidate_000009`，A residual `0.374313589186`，B final residual `0.0`，completion delta `0.748627178372`，overdig increase `0.009656514972`，outside-target increase `0.191985052079`，expected delta depth / volume `0.575955156237` / `0.035997197265`；protected current results file count stayed `10 -> 10`。
- Phase 6F-C 仍不是真实 simulation 或 production behavior：CLI return code 不是 eval pass/fail、planner success 或 production readiness；该入口不接 production planner、不接 rollout-review schema、不生成 runtime action、不定义 official thresholds 或 calibrated fallback。

Phase 6G-A note：

- `testbed.eval.terrain_residual_eval_run_plan.build_residual_eval_run_plan()` 已定义 focused eval run-plan owner，负责把当前 baseline metadata 和 Phase 6F predicted A/B artifacts 转成下一步真实 eval A/B 的 per-branch command plan。
- 该 helper 只接收显式 `current_eval_metadata`、`predicted_ab_artifacts`、future `planned_results_root`、protected evidence roots 和 residual runtime integration availability；它不读取隐式全局配置、不启动 `tb-eval`、不创建 run root、不写 artifact、不改 production planner。
- A branch 从 current baseline `argv` 还原可运行命令，并把 `--output-dir` 改写到 `runs/eval/oracle_terrain_residual_phase6g_real_ab_20260702/current_planner_baseline`。Current-run smoke 中 A branch status / command status 均为 `runnable`，source config 是 `runs/jobs/yulong_v2_4_5_return_relocate_token_swap_all_train_eval_20260526/eval_configs/eval_10cycle_next_entry_cell_prior_relocate_spatial_bounds_fail_fast.yaml`。
- B branch 在当前 repo 状态下保持 `not_runnable` / `runtime_integration_status=missing`，blockers 为 `missing_residual_runtime_planner_mode`、`missing_cut_intent_to_dig_cut_token_adapter`、`missing_residual_cut_intent_source_provider`、`missing_simulated_branch_execution_artifacts`。C branch 继续 `not_evaluated` / `blocked_by_missing_gold_samples`。
- Smoke facts: run plan status `present`，validation errors `[]`，no-overwrite status `present`，future root `runs/eval/oracle_terrain_residual_phase6g_real_ab_20260702` remained absent `False -> False`，protected current results file count stayed `10 -> 10`。
- Phase 6G-A 是从 predicted artifact pipeline 走向真实 eval runner 的 command-level bridge，但仍未完成 B branch runtime integration；完整 Phase 6 baseline comparison 仍需要把 B branch cut intent 接入 runtime planner / dig-cut token adapter 后运行真实 closed-loop simulation。

Phase 6G-B note：

- `testbed.planner.primitive.token.residual_cut_intent.build_residual_cut_intent_dig_cut_token()` 已定义 focused primitive token adapter owner，负责把 Phase 6E-C eval-only cut intent 或 nested `cut_intent` record 转成现有 `DigCutTokenPlanner.plan_from_raw_fields()` 可消费的 raw fields 和 `dig_cut_tokens` list。
- 该 helper 只接收显式 `cut_intent`、`cell_centers_m`、`direction_vectors`、`bucket_length_m`、`payload_kg` 和 profile；`cell_centers_m` 可用 integer/string cell id 映射到 `{x_m, z_m}` 或 two-item sequence，`direction_vectors` 用 cut-intent direction 映射到 two-item x/z vector。它不推断 grid-to-world axes、不定义 official geometry，也不从 volume 推断 payload。
- Adapter 验证 finite positive bucket length / candidate depth、finite non-negative payload、known anchor cell、known direction 和 nonzero direction vector。输出包含 schema/source/status/offline_only/profile、candidate id、primitive raw fields、`dig_cut_tokens` plain list、validation errors、adapter y=0 convention、token contract constants、non-goal statuses 和 provenance statuses。
- `operator_entry_y_m` / `operator_exit_y_m` 使用 `0.0` 是 offline adapter convention，不是 official terrain geometry。`payload_kg` 显式写入 `operator_cut_payload_gain_kg` 和 `operator_effective_deposit_delta_kg`。
- `build_residual_eval_run_plan()` 新增默认 `False` 的显式 `residual_cut_intent_token_adapter_available` evidence。默认行为保持 Phase 6G-A B blockers 不变；当调用方显式传入 `True` 且 residual runtime integration 仍不可用时，B branch 仍为 `not_runnable` / `runtime_integration_status=missing`，但 blockers 只保留 `missing_residual_runtime_planner_mode`、`missing_residual_cut_intent_source_provider` 和 `missing_simulated_branch_execution_artifacts`。
- Phase 6G-B 仍不新增 `dig_cut_planner.mode`，不运行 `tb-eval` 或 simulation，不创建 `runs` artifact，不写 branch output files，不改 production planner / rollout-review schema / CLI entrypoint，也不定义 command-space controls、official thresholds、pass/fail、eval success、planner success 或 calibrated fallback。

Phase 6G-C note：

- `testbed.planner.primitive.token.dig_planning.PrimitiveDigTokenPlanningService` 已新增显式 `residual_cut_intent` runtime token-planning mode。该 mode 只消费 caller-provided `residual_cut_intent_plan_provider` 返回的 `DigCutTokenPlan` 或 existing dig-cut raw-fields tuple，并继续通过 `apply_dig_cut_token_plan()` 写入现有 token source / fallback / prior-range state。
- `testbed.planner.primitive.token.planning_runtime.PrimitiveTokenPlanningRuntimePorts` 只做 provider 端口传递；`dig_cut_planner.mode=residual_cut_intent` 被 config validation 接受，但不是默认值，也不读取全局文件、env vars、`runs` artifact 或隐藏状态。
- provider 返回 no plan 或抛错时，只有 `dig_cut_planner_fallback_mode=conservative_pose` 才走 existing conservative fallback；否则按 existing operator-prior mode 规则抛出原始错误。
- `build_residual_eval_run_plan()` 新增默认 `False` 的显式 `residual_runtime_planner_mode_available` evidence。默认 Phase 6G-A / 6G-B blockers 不变；当 runtime mode 与 token adapter 都被调用方显式证明 available 且 full runtime integration 仍不可用时，B branch 仍保持 `not_runnable` / `runtime_integration_status=missing`，blockers 只剩 `missing_residual_cut_intent_source_provider` 和 `missing_simulated_branch_execution_artifacts`。
- Phase 6G-C 不运行 `tb-eval` 或 simulation，不创建 `runs` artifact，不写 branch output files，不改 eval YAML/default config/production planner decisions/rollout-review schema/CLI entrypoint，也不定义 command-space controls、official thresholds、pass/fail、eval success、planner success 或 calibrated fallback。

Phase 6G-D note：

- `testbed.planner.primitive.token.residual_cut_intent_source.build_residual_cut_intent_plan_provider_from_source_path()` 已定义 explicit residual cut-intent runtime source/provider contract。调用方必须显式提供 `dig_cut_planner.residual_cut_intent_source_path`；空 path 返回 `None`，不会扫描当前 `runs`、env vars、默认配置或隐藏全局状态。
- Source JSON contract 是 `residual_cut_intent_runtime_source_v1` / `explicit_residual_cut_intent_runtime_source`，必须包含 `status=present` 和 cycle-indexed `plans`。每个 plan 可以包装 Phase 6G-B adapter output，并提供 `dig_cut_tokens`、`raw_fields`、plan `source` 和可选 `fallback_reason`；provider 用当前 primitive cycle index 做 exact deterministic lookup。
- `PrimitivePlannerACTPolicy` 只做 optional source path 保存和 provider port pass-through；默认值仍为空，默认 `dig_cut_planner.mode` 仍为 `conservative_pose`。
- `build_residual_eval_run_plan()` 新增默认 `False` 的显式 `residual_cut_intent_source_provider_available` evidence。当 runtime mode、token adapter、source provider 都由调用方显式证明 available 且 full residual runtime integration 仍不可用时，B branch 仍保持 `not_runnable` / `runtime_integration_status=missing`，blockers 只剩 `missing_simulated_branch_execution_artifacts`。
- Phase 6G-D 不运行 `tb-eval` 或 simulation，不创建 `runs` artifact，不写 branch output files，不改 eval YAML/default config/production planner decisions/rollout-review schema/CLI entrypoint，也不定义 command-space controls、official thresholds、pass/fail、eval success、planner success 或 calibrated fallback。

Phase 6G-E note：

- `testbed.eval.terrain_residual_cut_intent_runtime_source.build_residual_cut_intent_runtime_source()` 已定义 focused source-payload builder，负责把 Phase 6E-E predicted B rollout step 中保留的 nested `cut_intent` 与显式 `cell_centers_m`、`direction_vectors`、`bucket_length_m`、`payload_kg` 转成 Phase 6G-B adapter output，并包装为 Phase 6G-D loader 可消费的 cycle-indexed runtime source payload。
- `testbed.eval.terrain_residual_predicted_rollout.build_predicted_residual_rollout()` 的 per-step records 现在保留 nested eval-only `cut_intent` record；原有 step summary fields、stop reasons、metrics 和 non-goal 语义保持不变。
- Phase 6F writer/pipeline 的 fixed artifact list 新增 `residual_cut_intent_runtime_source.json`。pipeline request 必须显式提供 `residual_cut_intent_runtime_source_inputs`；CLI `--request-json` 合同同步要求该字段。缺失或无效的 source-building 输入返回 deterministic `invalid_runtime_source_inputs` / `invalid_request`，并在 writer 前停止，不创建 results root。
- 生成的 runtime source 使用 `testbed.planner.primitive.token.residual_cut_intent_source` 中的 `residual_cut_intent_runtime_source_v1` / `explicit_residual_cut_intent_runtime_source` 常量；每个 source plan 包含 `cycle_index`、`cut_intent_candidate_id`、Phase 6G-B `plan` payload、plan `source` 和可选 `fallback_reason`。
- Phase 6G-E 仍不运行 `tb-eval` 或 simulation，不改 eval YAML/default config/production planner decisions/rollout-review schema，不生成 runtime action，不定义 command-space controls、official thresholds、pass/fail、eval success、planner success、production readiness 或 calibrated fallback。

Phase 6G-F note：

- `testbed.eval.terrain_residual_b_branch_eval_request.write_residual_b_branch_eval_request()` 已定义 focused B-branch eval request owner，负责把 current eval metadata、Phase 6G-E predicted artifact root、`residual_cut_intent_runtime_source.json`、fresh request root、fresh planned results root 和 protected evidence roots 转成 runner-facing request artifacts。
- `tb-terrain-residual-b-branch-request` 是该 owner 的薄 CLI entrypoint；它只读取显式 request JSON 和 current `eval_run_metadata.json`，不运行 simulation，不写 branch execution outputs，也不改现有 eval YAML/default config。
- request writer 读取 current eval config 后写出 `heuristic_residual_pipeline_eval_config.yaml`，并显式设置 B branch runtime config：`dig_cut_planner.enabled=true`、`dig_cut_planner.mode=residual_cut_intent`、`dig_cut_planner.residual_cut_intent_source_path=<runtime_source_path>`、`dig_cut_planner.fallback_mode=raise`、`dig_cut_planner.hold_token_until_skill_exit=false`、`dig_cut_planner.prior_path=""`。这些值只存在于 request artifact config，不改变默认 `dig_cut_planner.mode=conservative_pose`。
- request root 固定写入 `heuristic_residual_pipeline_eval_config.yaml`、`heuristic_residual_pipeline_invocation.json` 和 `residual_eval_run_plan.json`；若 CLI 使用 `--output-json`，还会写出 top-level request result。planned real branch root 只作为 expected output root 记录，request writer 不创建该 root。
- Current-run request smoke 先用当前 Phase 6F CLI 在 fresh root `runs/eval/oracle_terrain_residual_phase6g_f_predicted_ab_with_source_20260702/results` 重新物化 7 个 predicted artifacts，包括 `residual_cut_intent_runtime_source.json`。runtime source status `present`，plan count `1`，candidate id `cut_candidate_000009`。
- B-branch request smoke 写入 `runs/eval/oracle_terrain_residual_phase6g_f_b_branch_request_20260702`，request status `present`，request writer files `3`，CLI result 后该 root 文件数为 `4`。planned full root `runs/eval/oracle_terrain_residual_phase6g_f_real_ab_20260702` 仍未创建；protected current results file count stayed `10 -> 10`。
- 最小真实 B-branch execution smoke 使用 generated config、fresh smoke output root、`--target-cycle-gate 1` 和 `--no-video` 启动 `tb-eval`。它证明 runtime mode/source 已进入 primitive runtime，但失败于 `ResidualCutIntentPlanSourceError: residual_cut_intent source missing plan for cycle_index 1`；partial smoke outputs 为 `eval_resolved_config.yaml`、`eval_run_metadata.json(status=failed)` 和 `rollout_000.partial.jsonl`。
- Phase 6G-F 因此没有声明 B branch eval success、planner success、pass/fail 或 production readiness。剩余 blocker 是 runtime source 的 cycle coverage / runner stop-timing contract：后续真实 B branch execution 需要 source plans 覆盖 runner 实际会请求的 primitive cycle indices，或显式确认 bounded smoke 的 terminal-hold/stop semantics。

Phase 6G-G note：

- Root cause: Phase 6G-F 的 failed smoke 使用 `--target-cycle-gate 1` 覆盖了 gate 数值，但 request-local config 仍继承 baseline `eval.target_cycle_gate_terminal_hold_steps=100`。partial rollout 最后一条仍是 `primitive_cycle_index=0` 且 `dump_end_mask=1`；下一 tick 在写下一条 rollout record 前进入 cycle `1` source lookup，因此 exact provider 抛出 missing cycle plan。
- `testbed.eval.terrain_residual_b_branch_eval_request.write_residual_b_branch_eval_request()` 现在在 B request artifact config 内显式设置 `eval.target_cycle_gate_terminal_hold_steps=0`，并在 request result `runtime_config` 中记录 `eval.target_cycle_gate_terminal_hold_steps: 0`。这是 request-local stop-timing contract，不改 checked-in eval YAML/default config、不改 `tb-eval` CLI、不改 provider exact lookup、不新增 hidden fallback 或 last-plan reuse。
- Fresh Phase 6G-G predicted source root `runs/eval/oracle_terrain_residual_phase6g_g_predicted_ab_with_source_20260702/results` 写出 7 个 predicted artifacts；包含 status `present` 的 `residual_cut_intent_runtime_source.json`，plan count 仍为 `1`，覆盖 cycle `0`，candidate id `cut_candidate_000009`。
- Fresh B request root `runs/eval/oracle_terrain_residual_phase6g_g_b_branch_request_20260702` 写出 3 个 request files；generated config 保留 `dig_cut_planner.mode=residual_cut_intent`、`fallback_mode=raise` 和 source path，并把 `target_cycle_gate_terminal_hold_steps` 写为 `0`。
- Fresh bounded B smoke 使用 generated config、fresh smoke output root、`--target-cycle-gate 1` 和 `--no-video` 启动 `tb-eval`，exit code `0`。`eval_run_metadata.json` status `completed`、error `null`，`metrics.json` 记录 `target_cycle_gate_success_rate=1.0`，`rollout_manifest.json` 记录 stop reason `target_cycle_gate_reached`。这只证明 bounded smoke stop-timing contract 避免 missing cycle plan；仍不声明 official pass/fail、eval success、planner success、production readiness、official threshold 或 calibrated fallback。

Phase 6G-H note：

- `testbed.eval.terrain_residual_real_ab_smoke_comparison` 定义 focused real smoke artifact owner：`write_current_planner_bounded_smoke_request()` 只为 A branch 写 request-local current planner config/argv，`write_real_ab_bounded_smoke_comparison()` 只汇总真实 A/B bounded smoke result roots。
- A branch request root `runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/current_planner_baseline_request` 写出 `current_planner_baseline_eval_config.yaml`、`current_planner_baseline_invocation.json` 和 request result；request-local config 显式设置 `eval.target_cycle_gate=1`、`eval.target_cycle_gate_terminal_hold_steps=0`、`eval.save_video=false`，并保留 current planner `dig_cut_planner.mode=operator_prior_sweep_belief`。
- Fresh A smoke 使用 generated config、`--target-cycle-gate 1`、`--no-video` 和 fresh output root `runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/real_smoke_runs/current_planner_baseline` 运行 `tb-eval`，exit code `0`。A metadata status `completed`、error `null`，`target_cycle_gate_success_rate=1.0`，stop reason `target_cycle_gate_reached`，rollout line count `736`。
- B branch 没有重跑，复用 Phase 6G-G completed root `runs/eval/oracle_terrain_residual_phase6g_g_real_b_smoke_20260702/heuristic_residual_pipeline/results`；B metadata status `completed`、error `null`，`target_cycle_gate_success_rate=1.0`，stop reason `target_cycle_gate_reached`，rollout line count `708`，config 仍为 `dig_cut_planner.mode=residual_cut_intent` 且显式 source path 指向 Phase 6G-G runtime source。
- Durable comparison artifact `runs/eval/oracle_terrain_residual_phase6g_h_real_ab_smoke_comparison_20260702/real_ab_bounded_smoke_comparison.json` status `present`，branch order 为 A/B/C，C 保持 `not_evaluated` / `blocked_by_missing_gold_samples`。该 artifact 标注 `evidence_scope=bounded_one_cycle_smoke`、`full_phase6_success_claim=not_claimed`、`official_pass_fail_status=not_defined`、`production_readiness_status=not_claimed`，不声明完整 Phase 6 成功。
- Protected current evidence root `runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results` file count stayed `10 -> 10`。

Phase 6G-I note：

- `testbed.eval.terrain_residual_b_branch_eval_request.write_residual_b_branch_eval_request()` and the thin
  `tb-terrain-residual-b-branch-request` CLI now accept optional request-local `target_cycle_gate`. When provided,
  the B request writer validates that the explicit `residual_cut_intent_runtime_source.json` covers every required
  cycle in `[0, target_cycle_gate)` before writing request artifacts.
- If source coverage is sufficient, the writer writes `eval.target_cycle_gate=<target_cycle_gate>` only into the
  request-local config and argv. It still writes `eval.target_cycle_gate_terminal_hold_steps=0`, keeps
  `dig_cut_planner.mode=residual_cut_intent`, and does not alter checked-in eval YAML/default configs.
- If source coverage is insufficient, the writer returns `invalid_runtime_source` before creating the request root or
  planned results root. This preserves the exact-cycle provider contract and does not introduce hidden fallback,
  last-plan reuse, source plan repetition, or calibrated fallback.
- Fresh Phase 6G-I predicted coverage probe root
  `runs/eval/oracle_terrain_residual_phase6g_i_multicycle_coverage_probe_20260702/results` wrote 7 predicted
  artifacts. `predicted_b_rollout.json` status `present`, step count `1`, stop reason
  `zero_target_positive_residual`; `residual_cut_intent_runtime_source.json` status `present`, plan count `1`,
  cycle coverage `[0]`, candidate id `cut_candidate_000009`.
- Fresh Phase 6G-I B request input root
  `runs/eval/oracle_terrain_residual_phase6g_i_b_branch_request_inputs_20260702` wrote request/result files `2`.
  The `target_cycle_gate=2` request returned `invalid_runtime_source` with
  `runtime source missing required cycle plans for target_cycle_gate 2: [1]`.
- Planner recovery identified that the original predicted source cleared target positive residual in one predicted step.
  `max_candidate_depth_m` is constraint/scoring evidence, not a hard generation cap. A new explicit predicted source
  run used `depth_fraction_options=[0.1]`, `min_candidate_count=1`, and `max_cycles=3` under the same explicit
  non-official target spec. Fresh root
  `runs/eval/oracle_terrain_residual_phase6g_i_fraction_010_depth025_min1_20260702/results` produced predicted
  rollout status `present`, step count `3`, stop reason `max_cycles_reached`, and runtime source cycle coverage
  `[0, 1, 2]` with candidate id `cut_candidate_000003`.
- With that source, gate-2 B request root
  `runs/eval/oracle_terrain_residual_phase6g_i_gate2_b_branch_request_20260702` was written with `target_cycle_gate=2`
  and zero terminal hold. Real A and B smoke outputs were written under
  `runs/eval/oracle_terrain_residual_phase6g_i_gate2_real_ab_20260702/`.
- Corrected comparison artifact
  `runs/eval/oracle_terrain_residual_phase6g_i_gate2_real_ab_20260702/real_ab_gate2_bounded_smoke_comparison.json`
  has status `present`, validation errors `[]`, and `evidence_scope=bounded_multi_cycle_smoke`. A/current completed
  the bounded gate with `target_cycle_gate_success_rate=1.0`, `target_cycle_completed_dump_count=2`, stop reason
  `target_cycle_gate_reached`, and rollout line count `1383`. B/residual runtime completed the run but did not meet
  the gate: `target_cycle_gate_success_rate=0.0`, `target_cycle_completed_dump_count=0`, empty gate stop reason, and
  rollout line count `921`.
- C remains `not_evaluated` / `blocked_by_missing_gold_samples`. The gate-2 comparison is bounded smoke evidence only;
  it does not define official pass/fail, eval success, planner success, full Phase 6 success, production readiness,
  command-space controls, or calibrated fallback.

Phase 6G-J note：

- Phase 6G-J read-only root-cause review inspected the gate-2 A/B result roots without code or doc changes in the
  executor thread. The executor callback did not reach the planner automatically, so the planner recovered it with
  `codex_app.read_thread` and then corrected the workflow profile to require explicit callback routing.
- B did consume residual cut-intent plans: rollout records contain
  `dig_cut_token_source=explicit_residual_cut_intent_dig_cut_token`, and the runtime source had status `present`,
  plan count `3`, and cycles `[0, 1, 2]`.
- B also had a physical dump event: `dump_start_mask=1` and `dump_end_mask=1` appear in the rollout. However the eval
  summary used `coverage_completed_dump_count=0`, so `target_cycle_completed_dump_count` stayed `0`.
- The coverage count stayed zero because coverage effect runtime is currently enabled for
  `operator_prior_coverage` / `operator_prior_sweep_belief`, while B runs with
  `dig_cut_planner.mode=residual_cut_intent`; B planner traces show empty coverage corridors.
- First behavioral divergence after the first dump: A enters a return span and then reaches the next qualified dig
  start; B switches directly from dump to dig with `return_target_token_source=fallback_zero`, remains in `cycle_id=0`,
  and the next dig ends with `dig_failed_bad_dig_low_payload`.
- Phase 6G-K should therefore target the core residual-branch handoff problem: residual mode needs an explicit
  return-target / cycle-handoff contract after dump, or a narrowly justified target-cycle counting fix if evidence
  proves the count is wrong. It must not invent official pass/fail, hidden fallback, source repetition, or default
  runtime behavior.

Phase 6G-K note：

- `testbed.planner.primitive.token.return_planning.PrimitiveReturnTokenPlanningService` now has the residual
  return-target planning owner for `dig_cut_planner.mode=residual_cut_intent`. It consumes only an explicit
  `residual_cut_intent_return_target_plan_provider`; missing provider or missing plan keeps the existing exception
  path and does not introduce hidden fallback.
- `PrimitivePlannerACTPolicy` wires that provider as a thin port from the same request-local
  `dig_cut_planner.residual_cut_intent_source_path`, but with `cycle_index + 1` lookup. Active dig token planning
  still uses exact current-cycle lookup, so the source contract remains explicit and no source repetition or
  last-plan reuse is added.
- Return target source is derived through existing return target prefix semantics, for example
  `conditioned_return_explicit_residual_cut_intent_dig_cut_token`. The generated return-start envelope continues to
  use existing return-start-envelope planning; no checked-in eval YAML/default config, threshold, pass/fail,
  planner success, production readiness, command-space control, or calibrated fallback semantics are changed.

Phase 6G-L note：

- Residual return-target planning now maps explicit next-dig raw entry fields to the nearest existing coverage
  corridor before building `return_start_envelope_tokens_v1`; the existing corridor-to-cell mapping then selects the
  cell-conditioned qc6 return-start envelope prior. This lets residual B use the same envelope prior path as coverage
  modes when a request-local or checked-in prior is present, without feeding dig-cut tokens to return ACT or confusing
  pending corridor ids with cell ids.
- Missing coverage prior/corridors still degrades to the existing live-current-observation return envelope path; it
  does not turn missing residual source into hidden fallback success and does not relax entry, contact, depth, qpos,
  or transition-count gates.
- Fresh 6G-L B smoke with a request-local config that only restored checked-in
  `testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json` changed the first post-dump envelope
  source from `live_current_obs_fallback+relocate...` to
  `qc6_return_start_envelope_cell_2+relocate_spatial_linear+relocate_qpos_linear`. The return handoff still timed
  out: `completed_transition_count=0`, `transition_timeout_count=1`, `target_cycle_gate_success_rate=0.0`.
- The remaining 6G-L runtime blocker is no longer return-start envelope prior selection. The smoke never reached
  entry-close (`min return_to_dig_entry_error_m ~= 0.781m`, threshold `0.55m`) and envelope-ready stayed false with
  plane-depth/qpos failures.

Phase 6G-P note：

- The mixed-source isolation smoke preserved original cycle-0 residual active-dig tokens so B reached carry, dump,
  and return, while cycles `1` / `2` supplied corridor-conditioned next-cycle return target / relocate tokens.
- The first return row used
  `conditioned_return_explicit_residual_cut_intent_dig_cut_token` for return target and return relocate, and
  `qc6_return_start_envelope_cell_0+relocate_spatial_linear+relocate_qpos_linear` for the return-start envelope.
  No `fallback_zero` path was involved.
- Return handoff still timed out with `completed_transition_count=0`, `transition_timeout_count=1`,
  `entry_close_count=0`, and `envelope_ready_count=0`. The closest entry row remained just outside the entry gate
  (`return_to_dig_entry_error_m ~= 0.572m`) and still failed contact/depth/qpos checks.
- This rules out the narrow hypothesis that isolated corridor-conditioned next-cycle return target / relocate tokens
  are sufficient. The next core slice should compare residual B return trajectories against the working 2026-06-16
  handoff path before running more source-shape variants or promoting source semantics.

Phase 6G-Q note:

- The return-trajectory diagnostic recovered from a missed executor callback and wrote the request-local analysis
  artifact
  `runs/eval/oracle_terrain_residual_phase6g_q_return_trajectory_diagnostic_20260703/phase6g_q_return_trajectory_analysis.json`.
- 6G-P and the working 2026-06-16 run used the same return checkpoint family and the same return low-dim keys. In
  6G-P, first/min/last return rows all used nonzero corridor-conditioned return target / relocate tokens and the
  `qc6_return_start_envelope_cell_0+relocate_spatial_linear+relocate_qpos_linear` envelope source, so source fallback
  and near-origin token conditioning are no longer the current blocker.
- The remaining observed failure is depth/contact compatibility at the selected return-start envelope: 6G-P failed
  `local_depth_m`, `plane_depth_m`, `dig_contact`, and `qpos_3` through all return rows, with the min-entry row at
  `return_to_dig_entry_error_m ~= 0.572m`. The working row reached `entry_error ~= 0.099m`,
  `start_envelope_error=0.0`, `dig_contact=1`, and no failed checks through the same reporting fields.
- The next core slice should focus on whether the selected QC6 cell-0 return-start envelope target is incompatible
  with residual B dump-exit terrain/contact state, or whether return ACT cannot reach a valid target from that state.
  It should not default to another residual-source coordinate variant.

Phase 6G-R note:

- The envelope-compatibility diagnostic confirmed that 6G-P selected cell `0` by the current nearest-entry rule:
  cycle-1 raw entry `(0.8955, -0.952)` exactly matches checked-in prior cell `0`, and all return rows used
  `qc6_return_start_envelope_cell_0+relocate_spatial_linear+relocate_qpos_linear`.
- No mapping/reporting bug was evidenced. The checked-in 6G-P prior cell `0` lacks a `dig_start_local_depth_m`
  summary, generates a local-depth lower bound around `0.240m`, has a plane-depth floor around `0.586m`, and requires
  contact. The 6G-P dump-exit and all `420` return rows stayed at local depth `0.0`, plane depth `0.0`, and contact
  `0.0`.
- The working 2026-06-16 handoff used a different surface-depth prior artifact whose selected cell includes shallow
  local-depth stats and a plane-depth p05 of `0.0`. The next bounded evidence should therefore be a request-local
  counterfactual that keeps the 6G-P mixed source but swaps only the prior path to that already-existing
  surface-depth prior, without promoting config defaults.

Phase 6G-S note:

- The request-local prior counterfactual copied the 6G-P B config and changed only
  `policy.dig_cut_planner.prior_path` to
  `runs/jobs/yulong_v2_4_5_surface_depth_replay_train_eval_20260523/planner_prior_v2_4_5_surface_depth_tight_dump_qc6labels_scale080_20260524_next_entry_cells.json`.
- The smoke root
  `runs/eval/oracle_terrain_residual_phase6g_s_real_b_smoke_20260703_r1/heuristic_residual_pipeline/results`
  completed with `target_cycle_gate_success_rate=1.0`, `target_cycle_completed_dump_count=2`,
  `completed_transition_count=1`, and `transition_timeout_count=0`.
- All return rows selected
  `qc6_return_start_envelope_cell_1+relocate_spatial_linear+relocate_qpos_linear`; the completed transition row
  had `return_to_dig_entry_error_m=0.21173654848258414`, `return_to_dig_start_envelope_error=0.0`, contact true,
  local/plane depth checks ok, qpos checks ok, and no failed envelope checks.
- This supports the prior-artifact compatibility hypothesis from 6G-R. It does not promote the working prior to a
  checked-in default; the durable decision remains whether to rebuild a residual-compatible surface-depth prior or use
  a request-scoped prior selection policy.

Phase 6G-T note:

- Fresh A/B gate-2 roots were written under
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703`.
  A used current planner baseline mode, and B reran the same surface-prior residual config.
- Both A and B reached `target_cycle_gate_success_rate=1.0` with terminal hold `0` and stop reason
  `target_cycle_gate_reached`; C remains `not_evaluated` / `blocked_by_missing_gold_samples`.
- Explicit target residual projection comparison:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/real_ab_gate2_surface_prior_residual_metric_comparison.json`.
  B-vs-A deltas were target positive residual `-0.000311200623`, target completion ratio `+0.000622401246`,
  outside-target removed depth `-0.016043230891`, and target overdig `0.0`.
- The residual projection therefore shows a small bounded-smoke B improvement over A, not merely matching stop reason.
  However, B had worse execution-quality context: deposited fraction mean/min `0.6729643155685991` /
  `0.6371127565113851` versus A `0.8045243480617356` / `0.7736410550070904`, and B dig-depth absolute error mean
  `0.24203957766294482m` versus A `0.03503912687301633m`.
- This is bounded one-rollout smoke evidence only. It does not establish full Phase 6 success, production readiness,
  official pass/fail, checked-in prior promotion, or calibrated C benefit.

Phase 6G-U note:

- `testbed.eval.terrain_cycle_quality_report` now owns diagnostic per-cycle residual / payload / deposit / handoff /
  execution-quality summaries from explicit rollout artifacts and a caller-provided target spec. It reads
  `rollout_000.jsonl` plus `rollout_000_summary.json`, writes no-overwrite JSON reports, and keeps scope labels as
  diagnostic / bounded smoke only.
- The original 6G-T target now has per-cycle quality reports:
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/current_planner_baseline_cycle_quality_report.json`
  and
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/heuristic_residual_pipeline_cycle_quality_report.json`.
- Request-local T1/T2 default assumptions and comparison are recorded in
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/phase6_request_local_default_target_assumptions.json`
  and
  `runs/eval/oracle_terrain_residual_phase6g_t_gate2_real_ab_20260703/phase6_request_local_default_t1_t2_ab_comparison.json`.
- T1 default B-minus-A latest positive residual is `+0.015732030268`, completion ratio `-0.015732030268`, outside-target
  removed depth `0.0`, target overdig `0.0`; B is worse than A on the T1 residual projection.
- T2 default B-minus-A latest positive residual is `-0.000311200623`, completion ratio `+0.000414934164`,
  outside-target removed depth `-0.016043230891`, target overdig `0.0`; B remains slightly better on this trench-shaped
  projection.
- In both T1 and T2 default projections, B remains worse on deposit / payload quality: deposited fraction mean delta
  `-0.131560032493`, effective deposit delta mean `-11.33339881897kg`, payload peak mean `-9.625952243805kg`.
- These are posthoc projections on existing 6G-T gate-2 A/B rollouts, not new target-specific simulation reruns. They
  satisfy the current request-local diagnostic closure for T1/T2 assumptions, but not production readiness or official
  target semantics.
- The target-specific follow-up generated request-local T1/T2 B runtime sources with the same mixed-source isolation
  design as 6G-P: cycle `0` from the near-origin source and cycles `1` / `2` from the corridor-conditioned source.
  It then reran bounded gate-2 B smokes with the 6G-T surface-depth prior preserved.
- Both target-specific B reruns reached gate 2: T1 line count `1476`, T2 line count `1439`, each with
  `target_cycle_gate_success=1`, `target_cycle_completed_dump_count=2`, `completed_transition_count=1`, and
  `transition_timeout_count=0`.
- Target-specific T1/T2 comparison is recorded in
  `runs/eval/oracle_terrain_residual_phase6g_u_target_specific_t1_t2_ab_20260703/phase6g_u_target_specific_t1_t2_ab_comparison.json`.
  Compared with the Phase 6G-T current baseline projected onto the same target, T1 B-minus-A latest positive residual
  is `+0.013392139722` and T2 is `+0.000310925942`; both are worse for B. T2's earlier posthoc B advantage therefore
  does not survive target-specific source regeneration and rerun.
- The target-specific B reruns remain worse than A on deposit / payload / depth tracking: deposited fraction mean
  deltas are T1 `-0.082576753762` and T2 `-0.094762842451`; depth absolute error mean deltas are T1
  `+0.188530640304m` and T2 `+0.210038141906m`.

Phase 6 official-v0 closure note:

- `testbed.eval.terrain_residual_contract` is the stable eval contract owner
  for official Phase 6 v0 terrain residual semantics. It defines
  `terrain_residual_target_v1` with official T1
  `t1_large_shallow_rectangular_pit_default` (`grid[3,2]`, rows `[0,2)`,
  cols `[0,2)`, depth `0.25m`) and official T2
  `t2_long_shallow_trench_default` (`grid[3,2]`, rows `[0,3)`, cols `[0,1)`,
  depth `0.25m`).
- The conservative official v0 pass/fail profile is
  `not_worse_than_current_A_gate2_baseline`. A branch is evaluated against the
  same-run A gate-2 baseline and must reach the gate, complete at least two
  dumps, have zero transition timeouts, and be no worse than A on target
  positive residual, target overdig, outside-target removal, deposited
  fraction, and depth absolute error.
- Manifest / branch-plan / comparison artifacts now use the shared status
  source: `official_success_semantics_status=defined_by_terrain_residual_pass_fail_v1`,
  `official_default_status=defined_by_terrain_residual_target_v1`, and
  `official_threshold_status=defined_by_a_baseline_anchored_v0`. This upgrades
  only the eval contract and report status language; it does not change
  checked-in eval defaults, planner defaults, prior artifacts, or production
  gates.
- Request-local official pass/fail evidence is written at
  `runs/eval/oracle_terrain_residual_phase6_official_v0_pass_fail_20260703/official_t1_t2_a_baseline_pass_fail_comparison.json`.
  In that artifact A passes both T1 and T2 by construction against its own
  gate-2 baseline. Target-specific B reaches gate 2 with zero transition
  timeouts for both targets but fails official v0 on
  `target_positive_residual_worse_than_baseline`,
  `deposited_fraction_below_baseline`, and
  `depth_abs_error_above_baseline`.
- The current B failure is therefore not a return reachability blocker. The
  artifact evidence points to execution-quality / ACT depth response or
  dump-exit state: request-local cut intents ask for shallow depth around
  `0.015m - 0.019m`, while real B depth peaks are around `0.21m - 0.29m` and
  deposit / payload are lower than A. No planner behavior change or scoring
  guard was promoted from this evidence.
- `testbed.eval.terrain_cycle_quality_report` now accepts an official target id
  and includes official pass/fail output when a baseline summary is supplied.
  Its execution-quality summary also preserves planned/actual entry and exit
  coordinates plus depth target / peak / error fields from the rollout summary.
  The per-cycle residual summary now also preserves the start/end compact
  removed-depth grid, target-depth grid, target-region mask, and valid mask so
  replay/calibration consumers do not have to reconstruct terrain evidence
  from scalar residual metrics.
- `testbed.eval.terrain_residual_execution_diagnostic` now also owns the
  request-local official-v0 failure packet builder/writer. The packet combines
  official T1/T2 pass/fail evidence, B depth-execution diagnostic summaries,
  cycle-quality artifact references, and B runtime-source references into one
  no-overwrite JSON output. Its conservative conclusion keeps
  `planner_behavior_change_status=not_made`,
  `production_readiness_status=not_claimed`, and
  `calibrated_branch_status=blocked_pending_gold_replay_samples`.
  The current request-local generated packet is
  `runs/eval/oracle_terrain_residual_phase6_official_v0_failure_packet_20260707/official_v0_failure_packet.json`.
- `testbed.eval.terrain_gold_cycle_samples` is the official gold cycle sample
  JSONL owner. It writes one `terrain_gold_cycle_sample_v1` record per
  completed cycle, requires at least one split key (`episode_id` or
  `rollout_id`), and uses `payload_mass_kg` as the required payload label. A
  complete cycle-quality-derived record includes start/end removed-depth grids,
  target grid/masks, target residual metrics, payload peak, effective deposit,
  deposited fraction, depth target/peak/error, planned/actual entry and exit
  fields, success, transition, and gate fields. Volume labels remain
  `requires_unity_volume_fields`; volume fields must come from future direct
  Unity / env-state measurements rather than `removed_depth_delta * cell_area`
  inference.
- `tb-replay` now has thin request-local JSONL flags for these samples:
  `--gold-cycle-samples-jsonl`, `--gold-cycle-samples-target-id`, and
  `--gold-cycle-samples-low-payload-kg`. The CLI only wires arguments and calls
  the focused sample owner; it does not put sample semantics into the large
  replay file. Raw replay records can capture env-state terrain/payload fields
  before Unity exposes every planned/actual execution label; Phase 5
  calibration must use records that satisfy the full gold-cycle schema.
- C remains `blocked_pending_gold_replay_samples`. The new recorder establishes
  the formal replay output chain and schema tests, but it does not fabricate
  calibration success or claim that usable calibrated samples already exist.

Phase 6 depth-execution diagnostic note:

- `testbed.eval.terrain_residual_execution_diagnostic` is the focused owner for
  aligning residual cut intent with execution and dump-exit evidence. It reads
  explicit `residual_cut_intent_runtime_source.json`, `rollout_000_summary.json`
  and `rollout_000.jsonl` inputs, then writes no-overwrite request-local JSON
  diagnostics. It does not change planner behavior or checked-in config.
- Request-local root:
  `runs/eval/oracle_terrain_residual_phase6_depth_execution_diagnostic_20260703`.
- Index artifact:
  `runs/eval/oracle_terrain_residual_phase6_depth_execution_diagnostic_20260703/t1_t2_b_depth_execution_diagnostic_index.json`.
- T1 target-specific B: `cycle_count=2`, `depth_overshoot_cycle_count=2`,
  `target_cycle_gate_success=1`, `transition_timeout_count=0`, mean depth peak
  minus intent `0.223569767456m`, mean deposited fraction `0.7219475943`.
- T2 target-specific B: `cycle_count=2`, `depth_overshoot_cycle_count=2`,
  `target_cycle_gate_success=1`, `transition_timeout_count=0`, mean depth peak
  minus intent `0.245077269058m`, mean deposited fraction `0.709761505611`.
- Per-cycle evidence shows intent/token depth around `0.017m - 0.019m`, while
  actual depth peaks are `0.213m - 0.290m`. Dump-exit rows report return
  envelope readiness rather than timeout. This strengthens the current
  hypothesis that B's official-v0 failure is dominated by ACT depth execution /
  dump-exit state, not return reachability or a missing source plan.

通过标准：

- B 优于 A，说明收益来自 residual closed-loop。
- C 优于 B，说明 gold samples 的 effect / capability 校准有价值。
- 如果 B 和 C 都不优于 A，优先检查 target design、candidate generation、shape guard 和 ACT 可预测性。

### Phase 7: Runtime gate intervention

只有在 Phase 2 shadow audit 和 Phase 6 闭环仿真都支持后，才把 shape guard 作为运行时 gate 选项接入，并且必须放在明确 flag 后。

通过标准：

- shape guard 开启后，overdig 下降。
- payload / deposited fraction / cycle count 没有不可接受退化。
- 不引入 return handoff 抖动或状态机死锁。

## 8. 本轮总体验收口径

第一阶段务实标准：

| 指标 | v0 验收建议 |
| --- | --- |
| final positive residual volume | 相比 current planner 降低 `40% - 50%`，目标逐步收紧 |
| target removed volume completion | `70% - 85%` |
| final overdig volume | 不高于目标挖方体积 `10% - 15%`，早期诊断可放宽 |
| outside protected overdig | 不高于 current planner，且不能持续增加 |
| boundary error | 控制在一个 bucket footprint 内 |
| depth RMSE | 第一版 `8cm - 12cm` |
| local extreme overdig | 超过目标深度 `15cm` 的 cell / patch 标红 |
| residual curve | 10 铲内 positive residual 总体下降，negative residual 不持续增加 |
| payload efficiency | 均值、方差和 deposited fraction 不低于 current planner 的 `80% - 90%` 区间 |
| cuts to convergence | 不因形状控制变成明显低效流程 |

payload 验收不能只看平均值。需要同时看：

- payload mean
- payload variance
- low-payload event count
- deposited fraction
- 每单位 overdig 换来的有效 payload
- 每单位 cycle time 或每铲完成的 target residual reduction

这样可以避免两种错误：

- 为了形状牺牲效率，每铲 payload 太低。
- 为了 payload 牺牲形状，靠过挖装满。

## 9. 代码所有权建议

实现时应遵守 repo 的责任边界：

- `planner` 负责 target selection、candidate cuts、handoff、gates 和 replan。
- `data` 负责 HDF5 / rollout 数据读取和 derived fields。
- `eval` 负责 residual metrics、baseline 报告和离线审查。
- `policy` / adapter 只负责 ACT 输入输出、checkpoint 和 normalization，不承载任务级坑形语义。
- CLI 只做 orchestration，复杂逻辑进入 focused library module。

后续实现前需要再次检查当前代码树，避免把新算法塞进已经过大的 planner 状态机文件。新增模块应按稳定责任命名，例如 terrain state、residual metrics、candidate generation、effect model、capability filter，而不是按某次实验日期或临时 run 名命名。

## 10. 风险与停止条件

| 风险 | 判断方式 | 应对 |
| --- | --- | --- |
| ACT 对相似 cut 的效果不可预测 | effect model ranking 无效，candidate top-k 不稳定降低 residual | 暂停上层复杂 planner，优先升级 executor、feedback 或训练数据 |
| terrain state 不可信 | residual 与真实坑形变化不一致 | 先修 TerrainStateProvider / QC |
| payload guard 过强导致效率崩 | payload / deposited fraction / cuts-to-convergence 明显退化 | 调整阶段权重和最低有效 payload 规则 |
| overdig 仍持续增长 | negative residual 曲线持续恶化 | 提高 overdig penalty，收紧 depth budget，检查 gate |
| candidate 空间太连续 | effect/capability 数据稀疏，排序不稳定 | 缩小离散候选空间 |
| return 目标跳变 | handoff 抖动或 entry 误差变大 | 增加 return 后半段 target lock |

## 11. 最终判断

两个方案可以整合为一条路线：

```text
B 版作为工程骨架：
Oracle Terrain Residual Planner v0
+ coarse target/residual grid
+ discrete candidates
+ hybrid effect model
+ separate capability filter
+ strong baseline experiments

A 版补齐系统边界：
bucket-aware task metrics
+ TerrainStateProvider
+ return pending cut integration
+ payload-aware shape guard
+ future real sensor interface
```

本轮最关键的技术判断不是“LLM 是否足够聪明”，而是：

```text
在 ground truth terrain + bucket-aware tolerance 下，
当前 ACT 是否能作为可预测的局部执行器，
让 residual planner 多铲后稳定接近目标坑形。
```

如果答案是 yes，再讨论 LLM/VLM 如何把自然语言任务转成目标坑形和约束；如果答案是 no，应先修低层执行、地形观测或 gate 逻辑，而不是把不稳定性上交给 LLM。
