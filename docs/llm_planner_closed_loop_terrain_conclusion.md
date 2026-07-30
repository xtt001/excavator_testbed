# LLM Planner 前的闭环地形规划结论

> 2026-07-31 最新主线：
> `exact diagnostic`
> → `contact audit/A-B`
> → `Unity wall+FactoryFloor diagnostic`
> → `return-handoff/action diagnostic`
> → `return-handoff owner isolation`
> → `carry-to-dump ownership priority diagnostic`
> → `contact-budget freeze`
> → `continuous predictor`
> → `E0/G1/W1`
> → `bounded live`
> → `conditional 1×10`。
>
> 最新单因素实验已经解决此前“第二铲直接从 carry 跳过 dump”的失败：
> 只有当 bucket 位于原卸载区且本 tick 出现达到原阈值的真实入箱/入
> dump-area 增量时，诊断开关才锁定 dump ownership；仅 bucket 失重不算。
> dump ownership 与 `carry_release_safety` 同帧出现时优先进入 dump，接触、
> 高力、hard-bottom、stuck、timeout 和 return-envelope 规则均未放宽。
> 相同公平 reset 下，source 在第 2 铲走
> `carry_to_return_release_safety`、只完成 2 次 dump；新 run 的该路径计数为
> 0，第 2 铲明确进入并完成 dump，最终完成 9 次 dump。
>
> 这仍不是 10 铲通过。第 9 次 dump 后，next-dig boundary 在 step 4738
> 锁存，但 spatial entry error 为 `0.574945m`，depth envelope 尚未 ready；
> step 4740–4741 depth/qpos envelope 短暂 ready 时，entry error 仍为
> `0.566971/0.562878m`，高于原 `0.55m`；step 4745 entry-close 首次通过时，
> local depth 又已经越出上界。两类条件没有同时成立，return 用满 420 steps
> 后按既有 zero-action → neutral-ack 链 timeout。终止时 local/plane depth
> 分别为 `0.411726/0.640196m`，qpos_1 为 `0.884200`，均越出原 envelope。
> 因此当前结论是：dump ownership 优先级修复有效，剩余问题已经后移为第
> 9 次 dump 后的 return-handoff 时序/轨迹不重叠。报告位于
> `carry_dump_ownership_priority_10cycle_diagnostic_v1/run/report.json`；
> 结果仍是 diagnostic/non-promotable。
>
> v7 同段离线重算已经确认两个 owner 问题。只取消全局
> `require_contact=true` 仍不会在 qpos_1 越界前 ready，因为该 flag 还把
> plane-depth floor 从 prior p05 `0.027709m` 隐式切到 p50 `0.304557m`。
> 保持原有效深度范围不变、让 contact 只由 18D token field 6 决定、depth
> 只由 runtime prior p05-p95 决定后，离线 gate 在 step 3554 ready，而
> qpos_1 首次越界是 step 3555。
>
> 首个全局 owner 改动 attempt 从第一铲就改变 handoff 时序，四次 dump 后
> timeout，已标记为 scope-confounded 并被 supersede。有效 target-scoped v2
> 保持前七次 dump 的 v7 门控，只在 `completed_dump_count=7` 后激活诊断
> override。它在公平 reset 下于 step 3475 进入第 8 次 dig；当时 qpos_1
> `0.598779 < 0.648137`，local/plane depth 均在原 prior bounds 内。随后完成
> 第 8 个 `dump_end`，无 contact 或 hard-stop violation，并由
> `target_cycle_gate=8` 正常停止。终止当帧通用计数尚为 7，但
> `target_cycle_completed_dump_count=8` 与 `dump_end_count=8` 一致证明完成。
> accepted report 为
> `return_handoff_owner_target_scoped_diagnostic_v2/run/report_reanalysis_v1.json`。
> 该结果只证明本次 bounded owner 修复充分，不是 production contract freeze、
> continuous predictor、E0/G1/W1 live 或 functional 1×10。
>
> 随后把同一 request-local 诊断边界扩到 10 dumps，并执行两个独立
> no-overwrite replicate。两次公平 reset 均通过，但都只完成 2 次 dump：
> 第 2 铲没有进入显式 dump skill，而是在 carry 中完成 release，随后经
> `carry_to_return_release_safety` 进入 return。该铲分别出现约
> `4.06s/66.637kN` 与 `4.02s/66.729kN` 的 bucket-only FactoryFloor 接触；
> return 又带着 `61.660kg/68.385kg` 残余负载进入深土，最终因 local depth
> 和 qpos_1 均越出原 envelope 而 timeout。owner control 的 active sample
> 两次都是 0，因此这不是第七铲后的 owner 隔离失败，也不是 10-dump pass。
> 当前更早的 blocker 是 `carry -> dump` committed-boundary 与 release 的
> 先后关系；继续盲目重跑没有价值。
>
> 接触语义证据阶段现已执行完毕并暂停：Unity 通过既有 warnings append-only 返回
> `worktool_wall_contact_detail_v1`，Python 在 ACT inference 前执行 typed
> component/wall/session/force 决策；`record_bucket_first_session` 必须带显式
> diagnostic A/B 标记，不能成为 production 默认。Unity geometry audit 的
> `374 train + 59 validation = 433` 条路径全部完成，且在线 rig 未移动；
> 18 个 source 的 recorded-action replay 也全部只运行一次。但是公平门判定
> `379/379` 个 train window 和 `61/61` 个 holdout window 均为 `invalid`，
> 因而可用于 production inference 的 expert window 为 `0`。
>
> `episode_168` 的 3 组 paired A/B 已按冻结顺序真实执行 6 次、无重试，三对
> reset fairness 均通过。B 在 seed 0/1 进入 carry 并完成 dump，首次 bucket
> session 在 carry 前结束；seed 2 因第二接触 session 硬停止。因此 B 为 `2/3`
> 完成，既不满足 `safety_too_strict` 的 `3/3`，也不满足其他正向规则，最终
> causal classification 为 `inconclusive`。append-only `reanalysis_v4` 只修复
> 原报告后处理对 sibling return provenance 与 `box_safety:` 前缀的解析，
> `executed_attempt_count=0`，没有重跑任何 attempt。
>
> 随后的独立 diagnostic B2 **只重跑 seed 2 一次**，并把唯一语义变量改为：
> wall-contact logical session 必须连续两个无接触 tick 才结束；单个 `20ms`
> 空帧仍属于同一 session。reset、目标、checkpoint、ACT 和全部硬停止阈值均与
> 原 seed-2 B source-lock 深相等。该次真实 closed-loop 运行把 Unity physical
> session 1（step 625）与 session 2（step 627..689）之间的单个空帧 step 626
> 合并为一个 logical session，随后进入 carry 并完成 dump；无 hard violation。
> B2 outcome 为 `single_clear_tick_split_supported`。
>
> 随后单独授权的 observe-only multi-shovel diagnostic 使用历史 7-dump
> Strict-18 config/reset/checkpoint lineage，从 fresh seed-1000 reset 开始，
> 只把 finite `<100kN` 的 bucket wall contact 改为跨任意 session、duration、
> region 和 wall 的 record-only。唯一 attempt 完成 6 次 dump，第 7 铲因
> `hard_bottom_depth_budget_guard_clearance_depth_increase` 安全终止。唯一
> 接触铲的 12 个 physical sessions / 21 ticks / `0.42s` 均为 bucket ×
> `Dig_ZMin_Board`，normal peak/RMS 为 `73924.76/43681.23N`，接触期间仍有
> 运动；普通接触没有触发 neutral、ACT reset、replan 或 corridor block。
>
> 后续 Unity-only wall+FactoryFloor diagnostic 的首次高力结论已被否定：
> `v2/v4` 用 `-nographics` 启动，ACT 四相机来自 Null renderer 冻结灰图。
> 新 camera runtime contract 现在在 GET_INFO 前 fail closed。真实 GPU 的最终
> 公平 run `v7` 只执行一个 RESET，与 frozen A0 首帧差值全部为 0；它完成 7 次
> dump，最后由既有 timeout 安全终止。第 6 铲 wall peak `68.353kN`；第 7 铲
> wall/floor peak 分别为 `31.971/61.433kN`，全部 bucket-only、低于 100kN，
> wall/floor 长接触期间仍有运动进展。没有 boom/stick/other、高力、stuck 或
> 数据异常。
>
> 本阶段不能推断或冻结 production bucket region、force、duration 或 impulse
> 预算；B2 只证明原 seed-2 B 的失败由一帧 session segmentation 触发，后续
> 两个 multi-shovel diagnostic 只证明普通 bucket wall/floor contact 不是各自
> 运行的终止原因。它们都不把原 A/B 的 `inconclusive` 改写为可推广结论，也未
> 达到 10 dump。现在仍必须等待人工审核。
> 此前不得修改
> continuous 安全合同、实现 qpos
> predictor、运行 E0/G1/W1、bounded live 或 1×10。
>
> 最新 return-handoff 单因素诊断进一步把 7-dump 后的 blocker 从“深度门或
> timeout”收窄为 boom action overshoot。358 个 train handoff 对 cell `0..5`
> 都支持在原 qpos_1 envelope 内设置制动目标，不支持直接放宽 envelope。
> no-overwrite `v5` 在 locked goal cell 2 上真实介入 19 ticks，保持原上界
> `0.622343`，进入第 8 次 dig 并完成第 8 次 dump。该证据只证明局部 action
> shaping 能解除本次第 8 铲 blocker；它不等于 production promotion 或 1×10。
>
> 随后的“专家动作 vs Unity 执行器”拆分诊断没有改阈值或重训。416 个
> strict-18 return→dig 边界中，cell 0 有 81 个，但与 v7 step 3550 的
> cut intent、完整 18D return envelope、qpos/qvel、local-depth gate 和
> contact requirement 联合匹配的样本为 0；即使忽略 contact，
> cut-intent+state 与 return-envelope+state 匹配仍都为 0，81 个 cell-0
> 边界中也只有 1 个进入当前 local-depth gate。全部 416 个边界仅 1 个
> contact-positive，cell 0 则为 0。boom 接近上界的 5 个 cell-0 专家样本都
> 继续输出负 boom action，handoff 前十帧、handoff 当帧和后十帧都没有提前
> 刹车。因此不能把问题解释成“专家会刹车而 ACT 没学到”。
> 此外，当前 locked 18D envelope 的 contact token 是 `0`，runtime config
> 却强制 `require_contact=true`，构成直接的 envelope-vs-gate override 冲突。
>
> 独立 Unity 检查关闭 ACT 与 terrain physics，并把其余三轴固定在失败姿态，
> 只在 boom qpos `0.42/0.52/0.62` 给 `±0.10` 小命令。六次 pulse 均无外部
> shape、墙或 FactoryFloor 接触；正命令始终降低 qpos_1，负命令始终提高
> qpos_1，方向与专家 action/qvel 一致。跨姿态增益 max/min 为 `1.119953`，
> 无异常放大。结论收敛为：Unity 执行正常，当前
> return target + contact/depth handoff 是专家联合分布之外，而不是已证明的
> Unity 映射故障或 ACT 时间序列刹车故障。该诊断仍不授权修改 production
> return contract、阈值、checkpoint 或后续 live gates。
>
> exact execution/return libraries、replay 和历史 artifact 均保留，但 runtime
> role 固定为 `diagnostic_legacy`；新的
> `continuous_goal_conditioned` 模式不读取 episode/exemplar/raw-fields SHA
> 作为动作菜单。连续 cut goal 现在是一个 canonical `goal_id` 下的原子对象，
> 10D dig token、prior-independent 18D return envelope 和 planned qpos sweep
> 使用同一 identity；return handoff 对 spatial、local/plane depth、contact、
> qpos/qvel 逐字段 fail closed，并要求连续 3 帧 ready。
>
> request-local offline preflight 已生成到
> `/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/goal_conditioned_runtime_recovery_v1/`。
> E0/G1/W1 三条件均为 `blocked`，唯一 blocker 是
> `continuous_goal_3d_predictor_missing`；`act_inference_allowed=false`、
> `live_allowed=false`、`functional_1x10_allowed=false`。这是 offline contract
> proof，不是 bounded live 或闭环成功；本轮没有创建 live、1×10、训练数据、
> 重训练或新录制产物。

## 2026-07-30 Return-Handoff Action Diagnostic 结论

有效 source `unity_contact_observe_only_multicycle_diagnostic_v7` 的最终
return 不是“只差更多 timeout”：在首次 contact 前，ACT 已连续输出负 boom
action，qpos_1 在 step 3555 越过 cell-0 上界 `0.648137`。same-goal expert
handoff 又不支持把上界增加 `0.005`，因此选择了保持 envelope 不变的
diagnostic PD limiter，而不是放宽 handoff gate。

实验迭代本身也保留为证据：

- v3 写死 cell 0，fresh run 却选择 cell 4，控制器没有介入；
- v4 使用任意 cell，但错误地把 bucket 当前空间 cell 当作 locked goal cell，
  bucket 从 goal cell 0 跨入 spatial cell 1 后被误判 lineage drift；
- v5 改为从 locked coverage return goal 取 cell identity，contact safety
  仍使用当前空间 cell。

v5 reset fairness 全通过。第 7 次 dump 后 goal 为 cell 2，原 dominant
qpos_1 上界为 `0.6223429823`。controller steps `3708..3726` 共介入
19 ticks；首次把 ACT proposed `-0.548` 改为 executed `+0.35`。最终最大
checked qpos_1 是 `0.6221795082`，无 upper violation；step 3728 进入第 8 次
dig，step 4028 完成第 8 次 dump。第 8 铲没有 wall 或 FactoryFloor contact，
没有 hard violation。报告：

```text
/data/pingfan/excavator_testbed_runs/eval/
  yulong_strict18_terrain_residual_v0/
  return_approach_axis_limit_diagnostic_v5/run/report.json
```

报告的通用 termination label `normal_completed_10` 是历史命名；该 manifest
明确 `max_shovels=8`，实际 stop reason 是
`target_cycle_gate_terminal_hold_reached`，所以它不能被引用为 10-dump pass。
production contact budget、diagnostic limiter 是否产品化、continuous
predictor 与后续 live gates 都仍需独立决策。

## 2026-07-30 Unity-only Wall+FactoryFloor Root Cause 与有效重跑

最终有效 root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  unity_contact_observe_only_multicycle_diagnostic_v7/
```

`v2/v4` 的 0-dump / 117.7kN 结果不是接触语义证据。两者的 Unity 命令含
`-nographics`，日志为 Null Gfx device；首帧 payload 约 `11.7kB` 且场景区域
跨帧冻结。qpos/qvel、goal token、checkpoint 与可工作 A0 均已排除差异，
ACT 第一视觉推理后才分叉。Unity 因此新增双层 fail-closed：
GET_INFO 在支持图像但 `GraphicsDeviceType.Null` 时返回
`recording_camera_graphics_device_unavailable`，JPEG capture 也拒绝 Null。

后续 create-new roots 的证据边界：

- `v5`：真实 GPU，4 dumps 后 timeout；人工 visual preflight 多做一次 RESET，
  仅作 side evidence；
- `v6`：step 243 的 FMOD native SIGSEGV，process return code 1，无完整
  rollout；
- `v7`：真实 RTX 5070 Ti、单 RESET、3771 steps、process return code 0，
  reset fairness 全通过，7 dumps 后在第 7 铲 return timeout。

有效逐铲接触：

| shovel（1-based） | wall | FactoryFloor | dump |
| ---: | --- | --- | --- |
| 1–5 | none | none | yes |
| 6 | bucket×`Dig_ZMin_Board`, `1 tick/0.02s`, peak/RMS `68.353/68.353kN`, impulse `1367.065N·s`, progress=false | none | yes |
| 7 | bucket×`Dig_ZMin_Board`, `199 ticks/3.98s`, peak/RMS `31.971/30.718kN`, impulse `122248.148N·s`, progress=true | bucket×`FactoryFloor`, `160 ticks/3.20s`, peak/RMS `61.433/56.799kN`, progress=true；v1 impulse unsupported | yes |

最终两行严格保留 timeout 的 zero action → neutral ack → terminal。原离线
report 把紧邻 timeout 错当成允许接触的副作用；共享 safety-evidence helper
现在只在紧邻 timeout/stuck 完整硬停止链成立时归因给独立 stop。原失败报告未
覆盖，append-only 修正为
`run/report_reanalysis_v2.json`，SHA256
`b64faeaaf4a3abedecbfe43b9dddcdcb2abf724e0049bd85bc132290a2e6dca2`，
状态 `passed/timeout`。

该结果恢复到历史 7-dump 水平，但不是 10-dump 成功或 production safety
promotion。hard-bottom production 语义、contact budget、continuous predictor、
E0/G1/W1、bounded live 和 functional 1×10 仍不变。

## 2026-07-30 Observe-only Multi-shovel Diagnostic 实测结论

唯一执行 root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_observe_only_multicycle_diagnostic_v2/
```

这是 current-code diagnostic，不是 formal 1×10，也不是从历史 cycle 8 续跑。
历史 `act_freeze_probe_1x10_strict_prior_v1` 的 7-dump run 只提供
resolved config、首帧 reset、四 checkpoint、planner prior 和 provenance。
本次从 fresh seed-1000 reset 开始；reset fairness 的 qpos、qvel、bucket-tip、
terrain depth 与 remaining mass 差均为 0。四份 `dataset_stats.pkl`、ACT
loader/eval runtime、Unity scene/normalization/contact sidecar 和报告代码均由
manifest SHA 锁定。

普通接触合同只允许 bucket-only、所有力有限且严格 `<100000N`；不限 physical
session 数、持续时间、bucket-local region 或 wall identity。允许接触只记录，
不得触发 neutral、ACT reset、replan 或 corridor block。boom/stick/other/
ambiguous、non-finite/invalid lineage、`>=100000N`、hard-bottom、stuck 与
timeout 仍走原子安全停止。

唯一 attempt 的逐铲事实：

| shovel index（0-based） | dump | contact | component / wall | sessions / ticks | duration | normal peak / RMS | normal impulse | progress |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| 0 | yes | no | — | — | — | — | — | N/A |
| 1 | yes | yes | bucket / `Dig_ZMin_Board` | `12 / 21` | `0.42s` | `73924.76 / 43681.23N` | `15555.178944N·s` | yes |
| 2 | yes | no | — | — | — | — | — | N/A |
| 3 | yes | no | — | — | — | — | — | N/A |
| 4 | yes | no | — | — | — | — | — | N/A |
| 5 | yes | no | — | — | — | — | — | N/A |
| 6 | no | no | — | — | — | — | — | N/A |

report index 1（第二铲）的 tangential peak/RMS 为
`438.448975/258.499294N`，total peak/RMS
为 `73919.875/43680.374292N`。21 个 contact tick 都满足 observe-only
side-effect-free 验证；unsafe contact event 为 0。运动进展只使用接触前一
post-step pose 与 contact-positive post-step poses，不计入离开接触后的帧。

运行共 3293 steps，完成 6 次 dump、开始第 7 铲；最终
`hard_bottom_depth_budget_guard_clearance_depth_increase` 经 neutral ack
terminal，process return code 为 0。报告 status `passed`，outcome
`hard_safety_stop_before_10`，report SHA256
`c9609b10242b52380de0b1c1501edd5d44c95fdd1fe05900269b33fbba25da17`。
没有 HDF5、没有重试。

因果边界是：放行的普通 bucket 接触没有终止该运行，接触铲完成 dump，之后又
完成 4 次 dump；本次实际 blocker 是 hard-bottom depth-budget clearance
increase。它没有达到 10 dump，也没有超过历史 7-dump 结果，因此不能单凭这一
次运行断言 production safety 过严、冻结 bucket region 或确定
force/duration/impulse budget。所有 downstream gate 继续为 false。

## 2026-07-30 独立 Diagnostic B2 单帧断档证明

唯一 no-overwrite root 为：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_session_gap_diagnostic_b2_v1/
```

B2 不是 paired A/B 的第七次重跑，也不是 production 配置。它只执行
`seed=2 / retry_count=0 / executed_attempt_count=1`，运行到目标 dump 或原安全
链终止。原 seed-2 B baseline 没有进入 carry/dump，并以
`box_safety:wall_contact_repeat_session` 终止；B2 保持原 reset、目标、
episode-168 lineage、四个 checkpoint、ACT、timeout 与所有 hard threshold，
只把 logical-session 结束条件从一个 clear tick 改为两个。

实际 contact timeline 为：

- physical session 1：step `625`，bucket × `Dig_ZMin_Board`，peak
  `40094.2852N`；
- step `626`：唯一一个 clear observation，nominal `0.02s`，不结束 logical
  session；
- physical session 2：step `627..689`，仍为同一 bucket × 同一 wall，peak
  `39874.3242N`；
- logical reconstruction：一个 session、`64` 个 contact ticks；contact 在
  carry 前结束，step `777` 进入目标 carry，step `946` 完成目标 dump。

reset fairness 同时对冻结 expected state 与原 seed-2 B 通过；qpos、bucket-tip、
terrain depth、remaining mass 差均为 `0`，paired qvel 逐轴最大差约
`7.1e-15`。未发生 boom/stick/other、wall drift、`>=100kN`、hard-bottom、
stuck 或 timeout，terminal reason 为 `target_cycle_gate_reached`。可信报告为
`run/report.json`，SHA256
`178edb7e7d4e5f110ec8f1d7b642e0fb3ce5dc20b2e26a4bae27e04935b847a5`。

因此，B2 对 seed 2 支持“单个 20ms 空帧不应切断同一贴壁过程”这一窄因果解释；
它不证明 production bucket allowed region，也不提供 force/duration/impulse
预算。`contact_budget_freeze_allowed`、`continuous_predictor_allowed`、
`offline_e0_g1_w1_allowed`、`bounded_live_allowed` 和
`functional_1x10_allowed` 全部保持 false，等待人工审核后另行冻结合同。

## 2026-07-29 Contact Audit / Paired A/B 实测结论

唯一正式 root 为：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  wall_contact_semantics_recovery_v1/
```

geometry collection 为 `passed`：433 条 split-authorized expert qpos path
全部具有 boom/stick/bucket × 四墙的完整 witness，分类计数为
`clear=4484 / near_wall=548 / contact_or_overlap=164`。Unity shadow-FK
`online_rig_moved=false`，逐子段 proven motion bound 最大值为
`0.009990016m <= 0.01m`。这些是离线几何证据，不是 action replay，也没有据此
选择 production region 或预算。

18 个 recorded-action Unity replay 都完成且无重试。它们只提供 descriptive
contact evidence：train 的 window 类别计数为
`near_wall=236 / bucket_touch=139 / bucket_scrape_like=142 /
high_force_collision=27 / forbidden_component=0`。但 train `379/379`、
holdout `61/61` 均未通过 qpos/qvel/bucket-tip/terrain/mass 联合公平门，
所以 `valid_for_inference_window_count=0`；holdout 也从未参与 region/budget
选择。原始 89D generic collision=0 仍不构成“无墙接触”证明。

paired A/B 是真实 one-cycle closed-loop diagnostic，不是 replay。三对 reset
fairness 全部有效；B 结果为：

| seed | carry / dump | bucket session | peak force | duration | normal impulse |
| ---: | --- | --- | ---: | ---: | ---: |
| 0 | yes / yes | 1，carry 前结束 | `39.860 kN` | `1.380 s` | `42.325 kN·s` |
| 1 | yes / yes | 1，carry 前结束 | `38.767 kN` | `1.040 s` | `31.570 kN·s` |
| 2 | no / no | 2，repeat-session 硬停止 | `38.250 kN` | `0.060 s` | `2.729 kN·s` |

正式初版报告保留了后处理解析失败的 blocker，不能覆盖。修复后只读复算位于
`reanalysis_v4/`，其 attempt set 明确记录
`reanalysis_only=true / executed_attempt_count=0`；最终 report 为 `passed`
但 causal classification 仍为 `inconclusive`，且所有 future gate 均为 false。
本结论不支持 production contact-budget change。

> 2026-07-28 最新状态：phase-specific tuple-start transition 的 Unity shadow-FK
> 实测已完成，结果没有推翻 production full-gate preflight v2 的 `0/5` blocker。
> `episode_171` 的真实 paired-handoff + expert-dig 路径在冻结
> `hard=0.24m / ACT=0.05m / interpolation=0.01m` 合同下仍不合格；与该路径
> 端点语义严格匹配的 paired-handoff scalar bound 也不是过保守，而是低估完整
> worktool 位移。本轮未修改阈值或 planner、未重跑 bounded live/1x10，也未补录、
> 重训或写入训练数据。

## 2026-07-28 Tuple-start Transition Shadow-FK 实测

新的 no-overwrite 证据位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  worktool_margin_calibrated_transfer_v1/
    start_transition_diagnosis_v2/
      measurement_input/worktool_transition_sweep_input_v1.json
      unity_measurement/worktool_transition_sweep_measurement_v1.json
      diagnosis/coverage_start_transition_geometry_diagnosis_v1.json
```

input、Unity measurement 和 diagnosis 的 SHA256 分别为
`8ed2bad464e084650329e0d1ced759117d46f25ff0519d7aa145dfac7c9b33b0`、
`b79867287bda71b48e1514a77261eb7498054992998b5ac9fa1a07087ab44d1a`
和 `f8637752408a129b5ec562b33ba75c68647c929a86f18daa5a908cf94e931d4a`。
早先同 root 的 `start_transition_diagnosis_v1` 保留为 frozen 历史产物，但其
cycle-0 endpoint 比较混用了不同起点，已由 v2 supersede，不得用于结论。
所有路径均来自连续 recorded qpos，不使用两点线性插值：

- cycle 0：strict source episode 6 的 `0..214` 专家初始化路径，以及冻结
  functional rollout 的 `1..137` runtime prefix；目标 tuple 为 `episode_24`。
- post-return：strict source episode 24 中 `episode_161` 的 return handoff
  `2304..2308`、完整 gold return `2125..2308`，以及 `episode_171` dig
  `2308..2423`。

Unity 使用同一个 inert shadow-FK service、自适应 `<=0.01m` 采样、完整
boom/stick/bucket convex cover 和四墙距离。关键结果为：

| 路径 | sampled 最小 3D 净距 | 解释 |
| --- | ---: | --- |
| cycle-0 source expert preamble | `0.379269m` | 只证明 source 6 专家初始化自身安全 |
| cycle-0 frozen runtime prefix | `0.402612m` | 终点不是 `episode_24` expert start |
| gold return `2125..2308` | `0.320002m` | return 到 tuple start 路径自身安全 |
| handoff tail `2304..2308` | `0.320002m` | 精确配对 handoff 尾迹自身安全 |
| handoff + expert dig `2304..2423` | `0.285414m` | 最小值发生于 dig，而非 handoff |
| expert dig `2308..2423` | `0.285414m` | 同上 |

因此 post-return 的已测 full-path effective clearance 为
`0.285413831 - 0.05 - 0.01 = 0.225413831m`，仍低于冻结 hard gate
`0.24m`。即使完全删除旧 `0.075173m` start subtraction，
`episode_171` 也不能通过；问题不是“start bound 单独过严”。

对完整 collision cover 的 endpoint displacement 直接测量还发现，paired
handoff tail 的同端点实测为 `0.092744m`，planner bound 为 `0.075173m`，
低估约 `0.017571m`。cycle-0 source preamble 与 production bound 的起点不同，
不能做数值比较；v2 artifact 用 `planner_bound_endpoint_match=false` 明确禁止了
这类跨语义比较。

所以不能把 scalar bound 改小或删除；它当前甚至不是严格 conservative bound。
cycle-0 专家 source preamble 也不能证明当前 runtime 已有到 exact tuple start 的
alignment policy。最终 diagnosis 固定为
`start_bound_contract_change_allowed=false`、
`bounded_live_allowed=false`、`thresholds_relaxed=false`。production config
和上一节的五状态 preflight 不变，故不进行无信息增益的同配置重跑，更不能启动
bounded live 或正式 1x10。

## 2026-07-28 校准后 Production Full-Gate Preflight v2

新的 no-overwrite 证据为：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  worktool_margin_calibrated_transfer_v1/
    configs/bounded_transfer_v1.yaml
    production_preflight_v2_1/
      coverage_execution_production_preflight_v2.json
```

preflight artifact SHA256 为
`20db8124e3f8f53ba8d1a09c3b345625a02cc9411abd6918fd7b060f1b04dba1`；
artifact 同时锁定七个实际 selector/gate 实现文件的 SHA256。
它调用 production selector，使用 config 中的 3D hard gate `0.24m`，不再沿用
历史 preflight 的硬编码 `0.30m`；每个 state 保留全部 374 条 candidate trace。
结果为：

| 冻结 state | 主要逐门拒绝 | 到达 3D 门 | 最优 effective clearance |
| --- | --- | ---: | ---: |
| cycle-0 step 137 | 2D `278`，3D `96` | 96 | `-0.116433m` (`episode_24`) |
| post-return reset 0 | 2D `278`，start `87`，3D `9` | 9 | `0.150241m` (`episode_171`) |
| post-return reset 1 | 2D `278`，start `87`，3D `9` | 9 | `0.150241m` (`episode_171`) |
| post-return reset 2 | 2D `278`，start `82`，3D `14` | 14 | `0.150241m` (`episode_171`) |
| step 2987 + physical cell 5 exhausted | depleted `219`，2D `128`，start `27` | 0 | 无 |

cycle-0 的最优 tuple nominal clearance 为 `0.633019m`，但 actual reset 到专家
start 的保守位移界为 `0.689452m`，所以失败来自 first-dig start alignment，而不是
`0.24m` 单独过严。三条 post-return state 中，能够同时到达 3D 门的最优
`episode_171` nominal clearance 只有 `0.285414m`；扣除 `0.01m` 插值、
`0.05m` ACT margin 和 `0.075173m` paired-handoff start bound 后只剩
`0.150241m`。因此当前问题是“reachability-supported tuple 与几何安全 tuple 的
生产交集为空”，不能通过直接重跑 bounded 或把 nominal `19` 条当成 live 候选解决。

该 preflight 是 frozen-observation production-service replay，不是闭环成功证据。
按照 fail-closed 合同，3-reset bounded transfer、diagnostic 1x3 和正式 1x10
均未启动。下一步若继续，应单独测量 cycle-0 初始化到真实 tuple start，以及
paired return handoff 到 dig start 的实际三维 clearance loss；在有新证据前不得
降低 `0.05/0.24m`、关闭 reachability 或加入 fallback。

## 2026-07-28 专家重放与同目标 ACT 三维实测

no-overwrite 证据位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  expert_act_tracking_calibration_v1/
    live_measurement.json
    trajectory_geometry_measurement.json
    wall_clearance_margin_recommendation_v2.json
    planner_contract_impact_v1.json
```

实验每次先重放 source episode 24 的 `0:899` 前缀，使目标段起始 qpos 与
strict-train `episode_168` 一致，再分别执行 recorded expert action 或 frozen dig
ACT。起始 qpos 最大绝对误差为 `2.19e-5-1.71e-4`，因此没有把旧错误 return
handoff/start mismatch 混入 ACT tracking measurement。3/3 expert 和 5/5 ACT
均执行完整 `899:1050` 目标段并 zero-action、neutral ack；这是 bounded-live
诊断，不是 functional 1x10。

Unity 使用同一 shadow-FK、全部 boom/stick/bucket active collision-shape convex
cover 和四块 serialized wall，对采集到的 qpos path 重新计算最小距离。结果为：

| 路径 | repeats | 最小 3D 净距范围 | contact |
| --- | ---: | ---: | ---: |
| expert action replay | 3 | `0.286671-0.295515m` | `0/3` |
| same-goal ACT | 5 | `0.244541-0.252072m` | `0/5` |

八条路径的最近 pair 均为 boom collision proxy 到 `Dig_XMin_Board`。recorded
expert nominal minimum 为 `0.288379m`；ACT 相对它的 path-min 净距损失为
P95 `0.043156m`、P99 `0.043701m`、max `0.043838m`。

单调 DTW 对齐后的完整 convex-cover point displacement 仍按用户要求保留：
P95 `0.493919m`、P99 `0.529946m`、max `0.550403m`；其中 bucket P99
`0.529946m`、stick P99 `0.315701m`、boom P99 `0.296547m`。该三维范数主要描述
不同 extraction 姿态及沿轨迹方向的差异，不等于向墙靠近同样距离。若直接把
`0.529946m` 当 wall margin，会与 5/5 实际无碰撞、最小净距仍大于 `0.244m`
的观测矛盾，也会再次把所有 candidate 过滤掉。

因此最终 3D gate 的中央值改为：

```text
act_tracking_margin_m       = ceil_cm(max clearance loss + 0.002m FK error)
                            = 0.05m
hard_clearance_m            = floor_cm(min contact-free ACT clearance
                                       - 0.002m FK error)
                            = 0.24m
pose_interpolation_bound_m  = 0.01m
minimum nominal clearance   = 0.30m
```

这里 `0.05m` 覆盖了 5 次中观察到的最大墙向净距损失，而 `0.24m` 是 contact-free
ACT 最小净距扣除 FK error 后向下取整的保守 lower bound。旧
`0.15+0.01+0.30=0.46m` 合同使 374 条 frozen tuple 的 nominal candidate 数为 0；
新 `0.05+0.01+0.24=0.30m` 合同使 19 条在不计 live-start、reachability、
hard-bottom/OOD 等后续门时通过。`episode_168` nominal `0.288379m` 仍低于
`0.30m`，所以 calibration target 不会因为本次实测而被 production gate 直接放行。

这批证据同时支持：旧 `episode_168` 事故不能归因于“这个专家目标本身必撞墙”；
在精确 replay prefix/start 下专家与 ACT 都无碰撞。当前更强的因果指向仍是旧
return/handoff start mismatch。下一步如要恢复 live，只能重新跑
start-reachability + 3D + hard-bottom 的 production preflight，再做 bounded
probe；正式 1x10 和新增数据仍不属于本轮。

## 2026-07-28 Tuple Start Reachability 与精确 Return 合同

新的 no-overwrite 数据和诊断证据为：

```text
/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0/qc/
  strict_train_coverage_return_transition_library_v1.json

/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  tuple_start_alignment_diagnosis_v1/
    diagnosis/tuple_start_alignment_diagnosis_v1.json
    production_preflight/resolved_config.yaml
```

return-transition library 只读取官方 return train split 的 358 条 gold return，
排除 validation 33/34、silver 和 partial/layered/salvage。它使用
`source_episode_id + return_next_material_cycle_id` 与 dig tuple 配对，不按 primitive
编号或空间邻近猜测。结果为 353 个可用于 post-return 的精确配对、16 个 episode-first
tuple 和 5 个只有非 gold return 的 tuple；后 21 个只允许 cycle 0。artifact SHA256
为 `65952a2932a1d1373a74b825eb4d79c24d43224ca3e2449abcd7515395ab1e86`，
并固定验证 `episode_168 -> return episode_158`。

reachability 特征是 return start 的
`qpos[4] + qvel[4] + bucket-tip DigArea xyz[3]`，按 strict-train p01-p99 range
归一化。358 条 gold return 的 leave-one-out 最近邻 p99 阈值由 artifact 唯一保存：
RMS `0.2242876880`、L-infinity `0.4098004329`。三条冻结 target-cycle return start
对 `episode_168` 的距离为：

| rollout | RMS | L-infinity | paired-start 结果 |
| ---: | ---: | ---: | --- |
| 0 | `0.225562` | `0.536048` | reject |
| 1 | `0.232370` | `0.479259` | reject |
| 2 | `0.187319` | `0.411518` | reject |

这三条 return start 本身都在全局 strict-train p01-p99 内，并且各自仍有
`35/40/61` 条 reachable alternative。因而证据支持的是：planner 过去忽略了
“当前 return start 是否支持所选 tuple 的专家 return transition”，而不是 return ACT
已经被证明整体 OOD 或失效。

冻结 rollout 中，live return end 到旧 cell-median qpos center 的最大误差只有
`0.028-0.051`，到正确 `episode_158` qpos center 的最大误差为
`0.197-0.205`。旧 cell token 对三条 handoff 都报告 ready；精确 paired token
分别因 `long_norm`，以及 `long_norm + qpos_2` 拒绝。因此旧系统基本执行了错误的
cell 聚合目标。离线“start mismatch 消失”的严格含义是：这些不匹配状态不再能通过
handoff 进入 dig；它不表示 teacher-forced replay 已把机器闭环带到正确状态。

运行时合同现在固定为：

1. cycle 0 使用实际当前 start；cycle >=1 只允许有 gold return 配对且同时通过
   RMS/L-infinity reachability 的真实 tuple。
2. 选中 tuple 后原子锁定 dig raw tuple、paired return、原始 18D token、valid mask
   和所有 artifact/raw-fields SHA；return 期间禁止 cell prior、relocate 或 synthetic
   token 改写。
3. return->dig handoff 复核精确 spatial、local/plane depth、contact、qpos 和
   token qvel 上限；exact envelope timeout 必须 zero action、neutral ack、terminal。
4. 3D precheck 在 return 前使用“paired expert handoff -> dig exemplar start”；
   return 结束后使用实际 live handoff qpos 重做最终 gate。pre-return qpos 不再伪装成
   dig start。

teacher-forced ACT 对照为每个 token 使用独立 policy/temporal state。旧 cell token
精确复现 recorded action，证明对齐时钟正确；换成精确 `episode_158` token 后，
三条 rollout 的 mean action L1 变化为 `0.3601/0.4129/0.3343`。这只说明 token
确实改变 return ACT 动作，不能写成闭环到达证明。

production replay 的最终状态为
`no_3d_wall_safe_corridor:execution_library_all_candidates_rejected`。即使假设
live-start displacement 为 0，374 条 tuple 的最大 nominal 3D clearance
`0.340938926m` 扣除固定 `0.01m` 插值界和 `0.15m` ACT margin 后也只有
`0.180938926m`，低于 `0.30m` hard clearance；合法 candidate 数为 0。因此输出
`nominal_3d_clearance_contract_blocks_all`，并在 live 前停止。重训、effect model、
planned-cut、A1/A2、3x10 和 30% freeze 继续暂停。

> 2026-07-28 历史阶段记录：Unity 生成、Python planner 消费的保守 3D
> worktool sweep 已实现。5 个 shadow-FK fixture 全部通过 `2mm/0.2deg` 门，
> 374 条 strict-train dig 路径均生成有效 convex-cover sweep。
> `episode_168` 在三条冻结 bounded 起始 qpos 上均于 ACT 推理前被拒绝，且 artifact
> 保留 bucket→`Dig_ZMin_Board` 的 pair witness。随后 production planner 对原始
> pre-state 和 step 2987 的离线重放均得到 `no_3d_wall_safe_corridor`：固定
> `0.15m` ACT margin、`0.01m` 插值界和 live-start displacement bound 下没有任何
> candidate 达到 `0.30m` effective clearance。因此 3-reset bounded one-dig 和
> 正式 1x10 均按 fail-closed 合同未运行；没有放宽 margin、阈值或 fallback。

## 2026-07-28 Unity 3D Worktool Sweep 实现与 Production Gate

新证据位于 no-overwrite root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  unity_3d_worktool_sweep_v1/
    strict_train_coverage_pose_paths_v1.json
    worktool_shadow_fk_calibration_v1_1.json
    coverage_worktool_sweep_library_v1_1.json
    episode_168_frozen_start_preflight_v1/
      coverage_worktool_sweep_episode_preflight_v1.json
    production_replan_preflight_v1/
      coverage_execution_candidate_preflight_v1.json
```

pose library 只读取 16 个 strict-train source 的 374 个 dig primitive，从首个到
最后一个有效 dig supervision row 保存完整 4D qpos path，覆盖 token peak 与
extraction tail；validation 33/34 和 partial/layered/salvage 均不允许进入。
pose-library SHA256 为
`cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2`。
冻结的真实 tuple library 未修改，SHA256 仍为
`b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614`。

Unity `WorktoolKinematicSweepService` 使用当前 YuLong constraint frame、关节方向和
`YuLong_norm.json` 构造不移动在线 rig 的 shadow FK。boom、stick、bucket 的 active
collision shapes 与四个 serialized wall Box 做 AGX convex distance query；Mesh
转换为包含全部碰撞顶点的 convex-hull cover。分段 qpos path 自适应细分到任一
worktool point 的区间运动上界不超过 `0.01m`。5 个 deterministic fixture 使用隔离的
native AGX hinge chain 求解，最大 link position error 约 `1.43e-6m`、姿态 error
`0deg`，明显低于 `0.002m/0.2deg` 门；fixture 不移动 online rig。

sweep artifact 共 374/374 geometry-valid records，SHA256 为
`e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21`。
它输出的是 conservative convex-cover
`minimum_3d_clearance_lower_bound_m`，不是 ACT 未来轨迹的精确物理仿真。
Python 最终硬门使用：

```text
effective_clearance
= sampled_convex_cover_clearance
- 0.01m pose interpolation bound
- 0.15m ACT tracking margin
- live-start-to-exemplar-start displacement bound
```

仅 `effective_clearance >= 0.30m` 可执行。geometry、qpos、artifact SHA、
normalization SHA 或 raw-fields SHA 缺失/漂移均 fail closed；2D gate 仍作为预过滤，
prototype 和最终 raw fields 各复核一次。所有 3D candidate 被拒绝时产生
`no_3d_wall_safe_corridor`，ACT 不推理，live 路径只能发送 zero action、等待 neutral
ack 后 terminal。107D env-state 和 step-ack 协议没有扩展。

`episode_168` 的冻结起始 preflight SHA256 为
`103ebfa471b4573f835edb09c075c5696e59a3bf4d1c922f869970204183f908`。
三个 recorded starts 的 effective clearance 分别为
`-0.753607/-0.715073/-0.720629m`，3/3 在 ACT inference 前拒绝。每次全局最小 pair
是 bucket→`Dig_XMax_Board`；artifact 同时保留了用户要求的
bucket→`Dig_ZMin_Board` pair-level minimum witness（nominal `0.641342m`，
`bucket_Mesh`，pose index 13）。两者是不同 pair 的最小值，不应混写。

production replay 报告 SHA256 为
`1150766de6be552684bb40c11342b6def60df227af23cd584c17fc4a9b40807c`，
状态为 `failed`、`bounded_live_allowed=false`：

| recorded state | 2D reject | 3D reject | 其他 reject | 最优 3D effective clearance |
| --- | ---: | ---: | ---: | ---: |
| 原始 pre-state | 278 | 96 | 0 | `-0.216433m` |
| step 2987，actual cell 5 exhausted | 128 | 27 | 219 outcome depleted | `-0.621955m` |

所以 `episode_168` 已满足离线拒绝门，但“production replan 仍有合法替代 candidate”
这一前置条件没有满足。当前合同下的结论是“没有已证明安全的 cut”，不是 3D gate
已经通过 live promotion。按批准顺序，本轮没有创建/执行新的 bounded results，
也没有启动
`functional_10cycle_a0_actual_tuple_3d_wall_safe_1x10_v1`。重训、effect model、
planned-cut、A1/A2、3x10 和 30% freeze 继续暂停。

> 2026-07-28 历史阶段记录：真实专家 tuple 与 extraction-tail 预算已接入 production
> coverage planner，并完成 3 个独立 reset 的 bounded live gate。三轮 target cycle
> 都逐字段选择 strict-train `episode_168`，二维计划净距均为 `0.373659m`，但
> 3/3 都发生 bucket→`Dig_ZMin_Board` typed wall contact。强 validator 已拒绝
> promotion，正式 1x10/3x10 均未运行；当前根因是
> `bucket_3d_swept_envelope_incomplete_primary`，下一步只能进入 Unity 3D
> worktool sweep，不允许放宽墙距、归咎 temporal window 或先启动重训。

## 2026-07-28 真实 Tuple bounded-live 结果与 3D Sweep Gate

strict-train execution library、离线 root-cause audit、production replan 及 bounded
live 证据统一位于 no-overwrite root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_goal_execution_contract_recovery_v1/
    root_cause_report_v3/manifest.json
    production_preflight/coverage_execution_candidate_preflight_v1.json
    production_replan_pre/coverage_replan_replay_v1.json
    production_replan_post/coverage_replan_replay_v1.json
    bounded_one_dig_pose_stable_v2/
      results/
      validation_v2/act_actual_tuple_bounded_one_dig_validation_v1.json
    root_cause_report_v4/manifest.json
```

`strict_train_coverage_execution_library_v1_1` 只读取 16 个 strict-train source 的
374 个 dig primitive，SHA256 为
`b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614`。
production selector 现在先分离 outcome/corridor/physical/return 四类 ID，再执行
wall、exhausted swept-cell、hard-bottom tail budget 和 per-cell LOO-p99 OOD
过滤；cell 内固定 `K=1`，最终 raw fields 必须逐字段对应同一条真实专家 tuple，
禁止 coordinate median、字段混合和 fallback。step 2987 离线重放按预期选择
primitive `episode_168` / source episode 24 / outcome cell 1 / return group 0 /
swept cells `[1,3]`。

第一次 bounded attempt 没有形成可解释的 ACT cut：Unity bucket-tip 测量在相邻帧间
切换 measurement-box 最低角点，Z 值出现精确 `0.22/0.44m` 跳变，导致 bootstrap
决策帧误判 candidate。该 artifact 保留为 invalid diagnostic，没有被当作模型失败。
exact-tuple eval 变体随后增加只作用于首次 plan 的 3-frame pose-stability gate：
相邻 pose 最大变化 `0.05m`、最多等待 30 steps；它不改变 checkpoint、相机顺序、
action scale、carry envelope、safety 阈值或 A0
`window=100 / legacy_oldest_first`。

pose-stable bounded run 的强证据如下：

| reset | target tuple | 2D clearance | first wall step | max force | external shape | tail |
| ---: | --- | ---: | ---: | ---: | --- | --- |
| 0 | `episode_168` | `0.373659m` | 625 | `39.25kN` | `Dig_ZMin_Board` | wall 在 planned depth 前，无法评估 |
| 1 | `episode_168` | `0.373659m` | 638 | `38.51kN` | `Dig_ZMin_Board` | wall 在 planned depth 前，无法评估 |
| 2 | `episode_168` | `0.373659m` | 639 | `38.62kN` | `Dig_ZMin_Board` | `0.044127m > 0.023428m` |

三轮 typed bottom、stuck、timeout 均为 0；三轮 wall trigger 后都完成 zero action、
neutral ack 和 terminal。也就是说，安全 interlock 正常，失败发生在 candidate 的
预测几何合同：当前 `0.70m` 固定宽度的二维 entry→exit 包络允许该目标，但真实
oriented bucket 在关节轨迹中仍碰到序列化 ZMin wall。它不是 hard-bottom 事故，
也不能由“tuple 已来自真实专家”推导为当前场景必然可执行。

`root_cause_report_v4/manifest.json` 对 bounded validation 及三条 JSONL 重新校验
size/SHA，并锁定 evidence matrix：

```text
exact tuple:                 3/3
planned 2D clearance pass:  3/3
typed bucket-wall contact:  3/3
neutral-stop contract:      3/3
bottom / stuck / timeout:   0 / 0 / 0
tail fully evaluable:       1/3
tail exceeded:              1/1 evaluable
```

因此 promotion 状态固定为：

```text
functional 1x10: not run, forbidden
functional 3x10 / bundle: not run, forbidden
v2_4_6 cut-then-extract: blocked until 3D wall cause is resolved
effect model / planned-cut / A1/A2 / 30% freeze: paused
next branch: unity_3d_worktool_sweep
```

下一分支必须用 Unity 中完整 oriented bucket、boom、stick 与四块 serialized wall
shape 做 3D clearance query，并覆盖 planned path 与实际 execution-deviation
envelope；缺 geometry 时 fail closed，trace 至少记录最近 excavator shape、最近 wall
shape、最小 3D 净距和对应 pose/time。`episode_168` 必须先被新查询拒绝，或由独立
3D preflight 证明安全，才允许新的 live retry。已生成的
`functional_1x10_pose_stable_v2.yaml` 只是未执行配置，不构成 rollout 证据。

> 2026-07-27 最新状态：第六铲失败 artifact 已按 SHA256 冻结并完成离线归因。
> bookkeeping 的 wall/bottom 字段所有权错误已经修复，但它不是唯一根因。第六铲
> planned swept clearance 为 `0.07870m`，高于既有 `0.02m` margin；ACT 实际
> penetration 却比 plan 多 `0.13783m`，接触时 bucket-tip 距硬底仅 `0.00649m`，
> 因此主因是 `act_execution_capability_primary`。同时 logical cell 4 的物理轨迹
> 穿过 cell 5，构成 `data_scene_cell_semantic_mismatch`。修正状态后 production
> replan 仍无合法候选，所以 bounded probe 和新 A0 1x10 均未运行，live gate 保持关闭。

## 2026-07-27 A0 第六铲 Hard-Bottom 归因与 Live Gate

冻结输入和所有派生证据位于新的 no-overwrite root：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_hard_bottom_cycle6_diagnosis_v1/
    source_lock_manifest.json
    cycle6_execution_diagnosis.json
    coverage_replan_replay_v1.json
    goal_comparison/manifest.json
    goal_comparison/policy_replay_v1/manifest.json
    root_cause_report_v2.json
    root_cause_report_v2.md
```

原失败目录
`functional_10cycle_a0_wall_safe_1x10_v1` 只被读取和哈希锁定，没有修改、覆盖或重跑。
cycle index 5 的实际 cut 窗口固定为 pre-action observation step 2934 到首次 typed
bottom 上升沿 observation step 2974；step 2975 之后的 neutral、10 个 clearance row
和 replan 不进入 peak-depth 计算。

离线还原得到：

| 项目 | 结果 |
| --- | ---: |
| planned depth | `0.364648m` |
| planned center-line physical cell | `5` |
| planned swept physical cells | `[3,5]` |
| planned minimum hard-bottom clearance | `0.078700m` |
| contact-local planned clearance | `0.187929m` |
| actual peak penetration | `0.502483m` |
| actual penetration overshoot | `0.137835m` |
| contact bucket-tip clearance | `0.006493m` |
| point-to-planned-segment error at contact | `0.118952m` |

计划在完整二维 swept cells 上仍满足现有 `0.02m` margin；实际轨迹则明显越过 token
深度并进入 hard-bottom margin。由于触底时 bucket-tip 本身已经只有 `6.49mm` 余量，
不能归为“bucket-tip 安全、其他结构触底”。锁定分类因此是
`act_execution_capability_primary`，不是 `planner_depth_geometry_primary` 或
`bucket_collision_envelope_incomplete_primary`。logical outcome cell 4 不属于
center-line physical cells，另记 `data_scene_cell_semantic_mismatch`；prior 的
outcome label 不再被当作安全几何 cell。

bookkeeping 现在使用 append-only `contact_kind=none|wall|hard_bottom`：
wall 只拥有 `blocked_corridor_id`，hard-bottom 只拥有实际 bucket physical cell，
且只有 neutral ack 后才能修改 coverage state。clearance 不重复耗尽，typed wall
session 为 0 时不能写 `wall_contact_blocked_corridor`。大型 policy 只调用独立
box-safety state-effect service。

step 2987 的 production replan replay 使用原 A0 resolved config、真实 observation、
真实 attempts/depleted 状态及 production coverage builder/selection，不手工伪造分数：

- 只移除错误的 wall depletion 时，corridor 4 恢复为可选；
- 正确把实际 cell 5 标为 depth-exhausted 后，corridor 4 的 swept cells `[3,5]`
  与 cell 5 相交，被
  `swept_footprint_intersects_depth_exhausted_cell` 硬过滤；
- cell 0/1 被 wall safety 拒绝，cell 2/3/5 已 depleted，最终仍为
  `no_wall_safe_corridor`。

三方 M0/E1/W1 对照严格是
`teacher_forced_recorded_observation`。E1 按锁定距离合同重新验证为 strict-train
primitive `episode_354`、source episode 32；nearest-expert/OOD 索引只使用 16 个
train source episode 的 76,469 个有效 action-loss steps，validation 33/34 和
partial/salvage 均排除。三个目标在 40-frame recorded window 内的数值 p01–p99
support fraction 都为 1.0。现有 replay 工具不能证明三套独立 checkpoint ACT
temporal buffer，所以基础 `goal_comparison/manifest.json` 当时把 fresh/A0 action
栏明确记为 `blocked`，没有用合成 action 填空。随后新增的 no-overwrite
`policy_replay_v1` 为 M0/E1/W1 各自重新加载同一 dig checkpoint，逐分支 reset，
使用独立 temporal state 串行重放相同 40 帧；四相机、A0 window 100、
`legacy_oldest_first` 和 TF32-off 合同均锁定。M0 aggregate 与记录 actual action
逐帧完全一致（最大绝对差 0），证明 replay 时钟复现正确。

三目标 checkpoint action 结果仍只能按 teacher-forced 解释：

| target | aggregate mean | aggregate/expert sign agreement | aggregate vs nearest-expert MAE |
| --- | --- | ---: | --- |
| M0 | `[0.0130,-0.5236,-0.0310,0.1563]` | `0.49375` | `[0.0144,0.1884,0.0830,0.1896]` |
| E1 | `[-0.0056,-0.6445,-0.2494,-0.1550]` | `0.48750` | `[0.0636,0.3498,0.2417,0.3978]` |
| W1 | `[0.0143,-0.5711,-0.0898,0.1018]` | `0.68750` | `[0.0146,0.2084,0.1219,0.1385]` |

这说明 ACT 对 goal conditioning 很敏感，M0 的已执行 action 与相近训练专家仍有明显
差异；W1 在同一 recorded M0 observation 上方向一致性更高，E1 则更差。它不能证明
W1 闭环安全，也不能把 E1 判为失败，因为 E1/W1 observation 都没有反事实 resimulate。
它补齐了 action 证据，但不改变 ACT capability 主因和 live gate 关闭结论。

证据边界和执行决策为：

| evidence | 状态 | 允许的结论 |
| --- | --- | --- |
| frozen live source + offline reconstruction | complete | 第六铲实际计划、轨迹、接触与根因分类 |
| offline production replan | complete | bookkeeping 修复后仍无合法候选 |
| M0/E1/W1 teacher-forced comparison | complete with independent checkpoint replay | train lineage、几何和 recorded-observation action；不是闭环证明 |
| bounded one-dig probe | not run, not required | offline 主因唯一且几何/动作事实无冲突 |
| fresh formal A0 1x10 | not run, gate closed | 不能生成 preflight 或启动 Unity |

当前必须另立单因素 ACT/conditioning 修复，同时把 logical outcome cell 与 physical
safety geometry 分离；不得用 planned-depth clamp 或放宽安全门掩盖根因。两项均完成并
重新通过离线门之后，才允许生成新 preflight，并唯一运行一次
`functional_10cycle_a0_wall_safe_hard_bottom_fix_1x10_v2`。effect model、
planned-cut、A1/A2、3x10、30% freeze、重训和新增数据继续暂停。

## 2026-07-27 A0 Wall-Safe Corridor 修复与正式 1x10

本轮只改变 coverage candidate 的墙体安全语义。四 checkpoint、四相机、
dig/carry/dump/return handoff、安全阈值以及 A0
`window=100 / legacy_oldest_first` 均保持不变；这里的“原 A0”指这些行为合同不变，
不表示配置文件 SHA 不变。

实现使用 `conservative_2d_worktool_swept_footprint_v1`：entry→exit 完整线段按与
cut 垂直方向的 `0.35m` 半宽膨胀，工作装置宽度按 `0.70m` 保守取值；净距
`<0.30m` 硬过滤，`0.30–0.45m` 线性扣分，`>=0.45m` 不扣分。prototype selection
和最终 raw fields 各有一次 guard；无候选时禁止 fallback，ACT 不推理，实际发送
zero action并等待 neutral ack 后 terminal。它是保守二维包络，不是 Unity 3D
未来关节轨迹预测。

no-overwrite preflight 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  coverage_wall_safety_preflight_v1/
    coverage_wall_safety_preflight_v1.json
```

preflight 锁定 prior、A0 config、coverage code 和 Unity scene SHA，并得到预期分类：
cell 0/1 为 hard reject；cell 2/3/4/5 为 near-wall 且可选；最小可选净距
`0.3209796224m`，C1 对应 cell 2 净距 `0.3351545641m`。

正式 live artifact 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a0_wall_safe_1x10_v1/
    results/
    videos/rollout_000.mp4
```

结果必须区分通用 task success 与功能门：eval CLI 因累计倒土量给出
`success=1.0`，但强口径 validator 没有接受它。真实证据为：

- cycle 0–4 均完成 `dig→carry→dump→return`，共 5 次 dump；cycle 5 只有
  `dig→return`。
- typed wall mask、force、session 全为 0；stuck、timeout 也为 0。已执行 cut
  只来自 cell 2–5，记录到的最小 footprint 净距为 `0.3209796224m`。
- cycle 5 在 step 2975 发生唯一一次 typed bottom contact。step
  `2975→2976→2977→2986→2987` 分别完成 contact zero、neutral ack + ACT
  restart、scripted clearance、clearance complete、第二次 neutral ack + replan；
  离线 hard-bottom contract validator 单独通过。
- step 2988 发送 `no_wall_safe_corridor` zero action，step 2989 收到 neutral ack
  后 terminal。validation 目录没有生成 passing record。

当时从 live artifact 直接观察到的首个 bookkeeping 问题是：hard-bottom event 同时
携带 `planned corridor=4` 和实际 `depth_exhausted_cell=5`，旧通用 applier 把
corridor 4 误写为 `wall_contact_blocked_corridor`。该观察仍成立，但顶部最新离线归因
已经证明它不是唯一根因：第六铲还存在 ACT depth overshoot 和 logical/physical cell
错配。以下状态是本次 live run 的历史快照，不是当前修复完成度。

因此当前状态是：

```text
wall-safe preflight: passed
原 cell-0 侧壁回归: removed in this rollout
A0 wall-safe 1x10: failed at 5 complete cycles + sixth dig
bookkeeping ownership fix: implemented and offline verified
cycle-6 root causes: ACT execution capability + data/scene cell mismatch
fresh A0 1x10: gate closed, not run
A0 3x10 / functional bundle: not started / not released
formal freeze / effect-model / planned-cut: still paused
```

字段所有权修复已经完成；不能据此直接重进 1x10。后续须先完成顶部列出的
ACT/conditioning 单因素修复和 logical/physical cell 合同修复，再从新的 no-overwrite
离线 gate 与 A0 1x10 重进。本轮 artifact 保持原样。

> 2026-07-25 最新状态：Strict-18 ACT 回归的模块级因果诊断已经完成。锁定的
> 3x4 bounded-live 矩阵将根因分类为 `corridor_geometry_primary`：原 cell-0
> corridor 的 F0 在 3 次有效 reset 中 2 次碰侧壁；只降低 planned depth 的 D1
> 仍为 2/3 碰壁；只替换为 wall-safe cell-2 corridor 的 C1 为 0/3 碰壁且 3/3
> 达到 carry-start envelope；DC1 同样 0/3 碰壁、3/3 达到 envelope。因此当前主要
> 回归模块是 `operator_prior_sweep_belief` 的 corridor 选择缺少 bucket
> swept-footprint / wall-inset 过滤，不是 hard-bottom recovery，planned-depth
> 也不是本矩阵中的主要原因。

## 2026-07-25 Strict-18 ACT 回归模块因果诊断

本轮严格限定为归因，不修改生产 planner 默认语义、不修复、不重训、不做升级判定。
effect-model、planned-cut calibration、A2、十铲 promotion 和 30% mass gate 的执行
继续暂停。最终 no-overwrite 证据位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  act_regression_module_diagnosis_v1/final_verified/
    evidence_matrix.json
    diagnosis.json
    root_cause_report.md
    representative_clips/
```

证据必须按范围分开解释：

1. **Offline recorded-observation replay。** A0 第 2 铲 dig 有 40 个诊断 row，
   首次 wall 为 step 671；A1 有 60 个 row，首次 wall 为 step 706。二者都没有
   bottom contact。fresh ACT、100/20-step aggregate、train-only nearest expert 和
   F0/D1/C1/DC1 token 反事实是在相同已记录 observation 上计算的
   `teacher_forced_recorded_observation`，只证明局部动作敏感性，不能冒充闭环因果
   证据。train support 严格只读 16 个 train source episode，共保留 76,469 个
   `action_loss_mask=1` steps；validation 33/34 和 partial/layered salvage 均未进入。
2. **Bounded live probe。** cycle 0、四 checkpoint、四相机、100-step legacy
   aggregation、handoff 和 typed safety 全部锁定；cycle 1 只按 allowed-field guard
   改 depth、corridor 或两者。12 次按交错顺序执行，12/12 个 reset 的初始 qpos、
   5-step median bucket pose、6-cell terrain depth 和 remaining mass 均在锁定容差
   内。5-step median 用于排除 reset 后首帧 Unity pose publication 瞬态，不改变
   rollout 或生产 observation。
3. **Old TX24 bridge。** 未触发。F0 已达到 2/3 原失败复现要求，且 C1 满足
   0/3 wall、至少 2/3 envelope 的预设判定门；因此不需要用旧 bundle 来区分
   strict checkpoint 链与 Unity/reset integration。

live evidence matrix 为：

| condition | cycle-1 变化 | valid reset | wall repeat | envelope repeat | bottom / stuck / timeout |
| --- | --- | ---: | ---: | ---: | ---: |
| F0 | 原 cell-0 corridor，depth 0.419068m | 3 | 2 | 1 | 0 / 0 / 0 |
| D1 | 仅 depth 降为 0.243690m | 3 | 2 | 1 | 0 / 0 / 0 |
| C1 | 仅换 wall-safe cell-2 corridor | 3 | 0 | 3 | 0 / 0 / 0 |
| DC1 | wall-safe corridor + 低 depth | 3 | 0 | 3 | 0 / 0 / 0 |

12/12 probes 都在首次 envelope 或 typed safety 事件后实际发送 zero action、收到
neutral ack，并在 cycle 1 内 terminal；最高 typed wall force 为 91,933.62N，低于
100kN 高力终止阈值。C1 保持原 0.419068m depth 仍完全消除 wall，而 D1 保持原
cell-0 corridor 即使降低 depth 仍 2/3 wall，这构成当前归因的关键反事实。

所以目前可以排除或降级的假设是：

- hard-bottom recovery 不是最新 A0/A1 第 2 铲事故的直接原因：offline 和 12 次 live
  probe 的 bottom contact 都是 0。
- planned-depth 合同可能影响轨迹，但不是侧壁事故的主要原因：D1 未消除事故。
- 100-step aggregation 可能影响跟手，但不是唯一根因：A1 window-20 仍撞墙，且
  live C1 在 window-100 下已经 3/3 安全达到 envelope。
- carry-start envelope 不是本次侧壁事故的制造者：安全 corridor 下 C1/DC1 均
  3/3 达到 envelope；该 gate 在所有 live probe 中保持启用。

当前诊断已经把问题收敛到 coverage/corridor geometry 模块，但尚未证明加入
swept-footprint / wall-inset filter 后可恢复十铲。下一项实现若获准，应只修改
candidate corridor 的 wall-safe 过滤和 exhausted/blocked corridor 约束，然后从
A0 1x10 重新进入功能门；在此之前不得发布 functional bundle 或恢复 effect-model
路线。

> 2026-07-23 最新状态：当前是一次明确的系统级功能回归。旧
> aggregate-TX24 已完成 10 铲，但几何跟手不足；strict-18 新 ACT 尚未完成跟手评价，
> 已先失去稳定十铲能力。当前暂停 effect-model、planned-cut calibration、30%
> remaining-mass freeze gate 的执行、重训和新增数据；30% 正式合同本身保留，不降低
> 标准。

当前唯一允许推进的顺序是：

```text
锁定旧十铲功能基线
-> 修复 hard-bottom / handoff runtime regression
-> 独立 hard-bottom probe
-> A0 1x10
-> A0 3x10
-> A1/A2 单因素跟手 A/B
-> 恢复原 30% formal freeze
-> effect model / planned-cut / residual planner
```

旧功能基线已经由机器可读 manifest 锁定：

```text
testbed/configs/baselines/yulong_aggregate_tx24_functional_10cycle_v1.json
```

它引用
`runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results`
中的 resolved config、summary、rollout manifest、review、视频和四个 checkpoint
SHA256，记录 10 次 qualified dig、10 次 dump、9 次中间 return handoff，并以
`dig_area_depleted` 停止。计划草案曾把这个旧 artifact 称为 89D；实际 JSONL
`env_state` 宽度是 64D，因此 manifest 按实测记录为 64D。它没有当前 typed
wall/bottom 字段，只是功能基线，不是 107D 安全合同证明。

本轮 runtime 合同已经落地：

- same-skill 恢复使用显式 `restart_skill()`，无条件调用 ACT `reset()`；reset 清空
  timestep、temporal action tensor、valid mask 和 cached chunk。
- hard-bottom 首次 neutral ack 后清除 held return/start-envelope/relocate token、
  current return plan 和 pending dig plan；clearance 在 policy inference 前短路，不让
  ACT 继续生成或积累动作。
- normal dig-to-carry 必须同时满足原 payload/boundary 条件和 train-only
  `carry_start_envelope_v1` 连续 3 步；500 dig steps 未满足则 neutral-stop，无隐藏
  fallback。该 artifact 来自 16 个 train source episode 的 374 个 carry 首帧，SHA256
  为 `ab8e13ac8ff4565a9faf13264c96071289b8a92e3ddcf2baaced0918920b621a`。
- 新增独立 `act_functional_10cycle_validation_v1`、hard-bottom probe、
  `functional_baseline_only` bundle 和 A0/A1/A2 单因素 promotion contract；这些接口均
  不能冒充原 `act_unity_closed_loop_validation_v1` 或解锁 effect-model。

修复后的正式 A0 配置仍使用 100-step legacy aggregation 和
`return_to_dig_max_entry_error_m=0.65`。最新真实 Unity 复跑位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a0_postguard_1x10_v1/
```

该 run 只完成 1 次完整 dump；第 2 铲 dig 在 step 672 发生首次 wall contact，系统正确
发送 neutral 并 ack，随后 return 在 step 1094 timeout。强口径 validator 明确拒绝为
`cycle_inventory_not_0_through_9:actual=[0, 1]`，且未生成 passing artifact。因此：

```text
hard-bottom probe: not passed
A0 1x10: failed
A0 3x10: not started
A1 window-20 diagnostic 1x10: failed, non-promotable
A2: not started
functional_baseline_only bundle: not released
formal frozen ACT bundle: not released
```

wall 时 payload 已为 `36.71kg`，但 normal carry 的 base condition 和 train envelope
都未满足；carry gate 正确保持在 dig，没有提前切换。此时 qpos[3] 为 `0.237`，低于
train carry-start p01 `0.719`，plane depth 为 `0.532m`，高于 carry-start p99
`0.277m`，bucket-tip x/y 也在 envelope 外。也就是说，修复并没有制造新的 carry
handoff；它暴露的是 strict-18 dig 在到达专家 carry-start pose 之前已经碰壁。随后
return 的 local/plane depth 继续处于 envelope 外并 timeout。

经明确授权，A1 只作为一次不具升级资格的单因素因果实验运行。resolved config 已验证
除 no-overwrite 输出路径、诊断 metadata 和
`temporal_agg_window: 100 -> 20` 外完全一致；weight order 仍为
`legacy_oldest_first`，decay 仍为 `0.01`。artifact 位于：

```text
/data/pingfan/excavator_testbed_runs/eval/yulong_strict18_terrain_residual_v0/
  functional_10cycle_a1_window20_diagnostic_1x10_v1/
```

A1 同样只完成 1 次 dump。第 2 铲首次 wall 从 dig 后第 40 步推迟到第 60 步，wall 时
payload 从 A0 的 `36.71kg` 增至 `52.37kg`，plane depth 从 `0.537m` 降至
`0.517m`，bucket qpos 从 `0.243` 提高到 `0.296`；说明短窗口确实让执行向
carry-start envelope 靠近。但它仍远低于 qpos p01 `0.719`，且 depth 仍远高于 p99
`0.277m`，所以 envelope 正确保持 false。首次 neutral ack 后立即形成第 2 次 typed
wall session，按安全合同在 step 710 terminal。

不完整两铲窗口中的诊断指标也不支持 A1 promotion：平均 entry error 改善 `6.79%`，
但 exit error 恶化 `30.91%`，depth absolute error 恶化 `4.39%`，唯一完整 cycle 的
deposit fraction 从 `1.000` 降至 `0.817`，恶化 `18.32%`。这些不是正式 A/B
promotion 统计，但已足以否定这次 A1 诊断：它有局部方向性改善，却没有恢复功能并且
引入超限运输/几何退化。强 validator 仍拒绝为
`cycle_inventory_not_0_through_9:actual=[0, 1]`，未生成 passing artifact；A0 source
config 已按 SHA256 原样恢复。

一个更严格的 `return_to_dig_max_entry_error_m=0.10` 只读诊断还证明了另一个边界：
return 在 step 683、plane depth 约 `0.604m` 时触发 non-dig hard-bottom depth-budget
guard，随后连续实际发送零动作；机构惯性仍把深度推进到约 `0.618m`，超过“恢复期间
继续加深 0.002m 即 neutral 后终止”的硬规则，系统因而 fail-closed。该结果证明
neutral/terminal 安全链生效，但不证明 hard-bottom recovery probe 通过，也不能通过
放宽深度规则改写为成功。

所以当前阻塞点已经从“缺少 runtime contract”收窄为：strict-18 dig 无法在不碰壁的
情况下到达 carry-start envelope，而 window 20 只能延后、不能消除该失败；严格
return handoff 还会逐步进入深度 OOD。A0 尚未恢复旧功能能力，A1 诊断已淘汰，不能
启动 A2、3x10、30% freeze、effect-model 或 planned-cut 工作。下文关于坑形和
residual planner 的内容只保留为历史设计背景，本轮 T1/T2 仍为 deferred。

本文记录当前关于 LLM planner、ACT 低层执行、多铲挖掘跟手性和地形闭环规划的阶段性结论。核心判断是：下一阶段不应直接接入 LLM planner，而应先验证 ACT 是否能作为可预测的粗执行器，并把主规划目标从“单铲 token 严格跟手”升级为“目标地形残差闭环收敛”。

本结论的执行版开发计划见
[`docs/oracle_terrain_residual_planner_v0_plan.md`](oracle_terrain_residual_planner_v0_plan.md)。

## 1. 当前技术方案

当前系统的主体流程是：

```text
高层 planner / FSM
-> 选择下一铲目标 token，例如 entry / exit / depth / payload
-> ACT 执行具体动作
-> 根据 gate 判断 dig / carry / dump / return 切换
```

当前方案并不是等 return 完成后才决定下一铲。为了保持连续丝滑，return 阶段会提前生成 `return_target`，并缓存下一铲的 `pending_dig_cut_*`。因此当前节奏更接近：

```text
上一铲 dig 完成
-> carry / dump / return
-> return 过程中提前决定下一铲回到哪里
-> 到位后直接 handoff 到 pre_dig_align 或 dig
```

该架构在旧 aggregate-TX24 功能基线中已经证明的优点是：

- 旧 checkpoint/runtime 组合能够跑完十铲。
- 挖、转、倒、回之间能保持较连续的节奏。
- planner 已经有一定 coverage / corridor 选择能力。
- 部分模式下会使用 `env_state` 中的 removed depth / target depth / coverage belief 做粗粒度闭环。

这些优点不能外推成 strict-18 新 ACT 已恢复功能；顶部 A0 live gate 已经明确否定了
这一点。架构的本质仍然是：planner 给 ACT 一个目标，ACT 自己负责完成这一刀。
planner 并没有完整掌握“当前目标地形和实际地形之间还差多少”，也没有显式建模“给定
某个 cut target，ACT 大概率会挖掉哪里、挖多少、是否过挖”。

## 2. 历史 aggregate-TX24 基线阶段遇到的问题

在旧 aggregate-TX24 已经能跑完 10 铲的历史基线阶段，主要问题不是“能不能跑
10 铲”，而是：

```text
跑通 != 严格跟手 != 能挖出指定形状
```

已经暴露的问题可以分为几类：

| 问题 | 通俗解释 |
| --- | --- |
| entry / exit / depth 不稳定 | planner 给了目标，但 ACT 实际挖的位置和深度不一定跟得上 |
| depth / payload / 执行效果不可分离 | token 同时带深度、路径和 payload intent，但 live 地形变化和 ACT 执行效果不受单独几何目标约束，payload 成功不能证明形状正确 |
| 土体状态变化导致分布外 | 第 N 铲的土体已经不是专家训练时的状态，ACT 需要在新土体条件下泛化 |
| coverage 闭环偏粗 | 当前有 removed depth / coverage belief，但还不是明确的目标坑形残差闭环 |
| success 指标太粗 | 10 铲完成、`success=1.0` 不能证明每铲形状、深度、位置都正确 |

### 2.1 当前“跟手”审查口径

这里的“跟手”不能理解成一个单一指标。当前 rollout review 能稳定审查的是三层问题：

| 层级 | 当前要求 | 当前 planned-vs-actual 是否完整 |
| --- | --- | --- |
| dig cut 跟手 | ACT 是否按 planner 给出的 entry / exit / depth / payload 执行这一铲 | 相对完整 |
| return handoff 跟手 | return 是否把机器带回下一铲 entry 附近，能否交接给 dig | 有 handoff readiness 指标 |
| carry / dump 运输质量 | 挖出来的料是否带住、是否有效倒出、是否残留或漏料 | 目前主要是质量指标，不是完整几何目标跟手 |

因此，当前 audit 不能解读成完整任务级“指哪挖哪”审查。它更准确地说是：

```text
dig cut target 跟手
+ return->dig handoff readiness
+ carry / dump transport quality
```

如果未来 planner 给出明确的 carry / dump 目标，例如 dump pose、deposit footprint、允许残留 bucket mass、指定卸料区域等，carry / dump 也应该升级成 planned-vs-actual 审查。目前还没有这一级目标，所以 deposit fraction 只能说明运输和倒料质量，不能证明 dump 几何跟手。

### 2.2 当前 10 铲 rollout 的修正后审查结论

以当前主 run 为例：

```text
runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results
```

在修正两个审查口径后，结论发生了变化：

- depth 跟手结论使用 `rollout_review.json` 中的
  `depth_tracking.dig_local_surface`：从 per-rollout jsonl 的连续 `dig`
  段读取 `env_state[31] bucket_depth_below_local_surface_m` 峰值，目标值来自
  `dig_cut_tokens[7] * 0.8`。`planned_actual_cycles.depth_peak_m` 仍是历史
  summary plane-depth 诊断字段，不作为 command-depth 跟手结论。
- return handoff 过滤 episode 末端残留 return 段，不再把 terminal 状态污染进 handoff 统计。

修正后的总览是：

```text
return handoff 已合格；
dig entry / exit 明显不跟手；
depth 没有之前 plane-depth 口径看起来那么糟，但仍有真实过深铲；
payload 平均接近目标；
carry / dump 的 deposit fraction 波动较大。
```

| 指标 | 当前结果 | 判断 | 解释 |
| --- | ---: | --- | --- |
| dig entry 误差 | 平均 20.4cm，最大 41.3cm | 不跟手 | 入铲点离目标偏大；55cm handoff 阈值只是能交接，不代表形状精确 |
| dig exit 误差 | 平均 39.2cm，最大 55.6cm | 明显不跟手 | 出铲点是当前最严重的几何问题 |
| exit 纵向误差 | 平均 27.1cm，最大 52.6cm | 不跟手 | 很多铲提前或滞后出铲 |
| exit 横向误差 | 平均 21.7cm，最大 47.3cm | 不跟手 | 很多铲横向偏差也明显 |
| dig local-surface depth 误差 | 平均 +3.4cm，最大 +20.3cm | 局部不跟手 | 来自 `depth_tracking.dig_local_surface`；第 7、10 铲真实过深 |
| summary plane-depth 诊断 | 平均 +15.7cm，最大 +25.9cm | 仅诊断 | 来自旧 `cycleN_depth_peak_m - cycleN_depth_target_m`，窗口和深度参考不同，不能和 local-surface 跟手口径混用 |
| payload mass out | 目标均值 58.0kg，实际均值 61.3kg | 基本接近 | 平均装载量接近目标，不能证明形状正确 |
| deposited fraction | 平均 80.2%，最低 57.3% | 不稳定 | 料能挖出来，但运输和倒料质量波动大 |
| return->dig handoff | 0.339m <= 0.55m | 合格 | 过滤 terminal 污染后，return 能交接给下一铲 dig |
| coverage trace | 存在 | 有证据 | 有 coverage 证据，但 candidate ranking 仍需要继续 root-cause |

逐铲看更直观：

| Cycle | Entry err | Exit err | Dig depth over | Deposit fraction |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3.5cm | 52.4cm | -14.1cm | 78% |
| 2 | 22.4cm | 15.6cm | +4.7cm | 62% |
| 3 | 39.7cm | 31.3cm | +4.2cm | 82% |
| 4 | 33.3cm | 18.9cm | -6.4cm | 85% |
| 5 | 41.3cm | 43.8cm | +12.9cm | 83% |
| 6 | 9.7cm | 38.6cm | -1.6cm | 80% |
| 7 | 18.3cm | 32.9cm | +19.0cm | 89% |
| 8 | 7.8cm | 55.6cm | -1.5cm | 97% |
| 9 | 13.7cm | 52.9cm | -4.0cm | 88% |
| 10 | 14.1cm | 49.6cm | +20.3cm | 57% |

这个结果说明：

```text
当前 rollout 能跑完多铲流程，
return 也能把系统带回下一铲附近，
但 ACT 对 planner cut target 的几何跟手仍然不够。
```

特别要注意，handoff 合格和 entry 精确不是一回事。handoff 阈值是为了判断“能不能进入下一铲”，通常会比较宽；而未来如果要挖指定形状，entry / exit 的绝对误差必须明显更小。因此当前结果不能证明系统已经具备稳定的“指哪挖哪”能力。

我们认可的关键判断是：

```text
要求 ACT 在多铲动态土体里严格跟手，
本质上是在要求它对自己造成的土体变化后的状态继续泛化。
```

这对纯 BC / ACT 是很高要求。ACT 训练时学到的是专家分布下的动作映射；推理时，多铲挖掘会持续改变土体，使后续观测逐渐偏离专家数据分布。因此，不应该把全部闭环控制责任都压给 ACT。

## 3. 下一步计划与最终可以达到的目标

下一步更合理的架构方向是地形闭环：

```text
语义任务
-> 目标地形 / 目标坑形
-> 当前地形观测或地形 belief
-> 形状残差：哪里没挖够，哪里已经挖过
-> 下一铲 cut plan
-> ACT 粗执行
-> 观测或估计实际地形变化
-> 更新残差并继续规划
```

在这个架构里，ACT 的定位需要变化：

```text
从“严格执行给定 entry / exit / depth”
变成“在指定区域产生大致可预测的挖掘效果”
```

最终目标仍然可以是语义级挖掘任务，例如：

```text
挖一个指定形状 / 指定用途 / 指定约束的坑，
机器在可行范围内自由选择路径完成。
```

但“自由选择路径”的主体应该是地形残差 planner，而不是 ACT 自由发挥。LLM 更适合放在最上层，把自然语言任务转成目标几何、约束和验收标准；不应让 LLM 直接控制低层动作。

闭环规划也不意味着破坏连续丝滑。正确实现方式应是流水线：

```text
dig 期间记录实际效果
carry / dump 期间更新地形 belief
return 期间提前规划下一铲
handoff 前锁定目标
必要时只做小范围修正
```

因此，未来目标不是“每铲结束后停下来重新想”，而是“边执行、边估计、边准备下一铲”。这和当前提前生成 return target / pending dig cut 的方向是一致的，只是未来需要把当前较粗的 coverage/corridor 选择升级成显式地形残差规划。

### 3.1 当前地形如何获得

地形闭环的第一前提是系统能知道“当前坑是什么形状”。这里需要的是度量地形状态，而不是单纯给 ACT 更多 RGB 图像。

在仿真阶段，最便宜可靠的做法是直接使用现有 `env_state` / height grid / removed-depth grid：

```text
sim ground truth terrain
-> dig_area 坐标系下的 current height / removed depth / target depth
-> residual planner
```

真实机器上则必须补一个可用的地形感知方案，目标是得到：

```text
dig_area 坐标系下的 elevation / removed_depth / confidence map
```

可选传感器路线如下：

| 方案 | 作用 | 主要风险 |
| --- | --- | --- |
| 3D LiDAR / depth sensor / stereo | 直接重建 dig area elevation map | 灰尘、遮挡、阳光、标定和同步 |
| 多 GMSL 相机 | 可做多视角感知，也可辅助重建 | 需要标定和深度估计，不能只当 RGB 输入 |
| 斗尖轨迹 + 接触 / 深度估计 | 可补充“斗经过哪里、可能挖到哪里” | 稀疏、间接，不能完整重建坑形 |
| 仿真 ground truth | 研发上层 residual planner 最快 | 到真实机器前还要迁移传感器链路 |

因此真实传感器优化的重点不是“让 ACT 看更多画面”，而是让上层 planner 拿到可量化的地形状态和不确定性。

### 3.2 实时残差如何计算

语义任务需要先落到目标地形。例如：

```text
挖一个 2m x 1m x 0.4m 的坑
-> target_depth_grid[x, z]
```

实时感知或仿真状态给出：

```text
current_removed_depth_grid[x, z]
confidence_grid[x, z]
```

残差定义为：

```text
residual[x, z] = target_depth_grid[x, z] - current_removed_depth_grid[x, z]
```

解释很直接：

| residual | 含义 |
| ---: | --- |
| `> 0` | 这里还没挖够 |
| `≈ 0` | 这里基本达到目标 |
| `< 0` | 这里已经超挖 |

真实系统必须同时维护 `confidence_grid`。如果某个区域被斗、扬尘、车体或视角遮挡，就不能把该区域的 residual 当成确定事实。后续 planner 应区分：

- confirmed terrain：观测可靠，可以直接用于规划。
- estimated terrain：由上一铲效果模型或斗尖轨迹估计，需要保守使用。
- uncertain terrain：不确定，不应贸然规划深切。

### 3.3 Effect Model 和 Capability Model

Residual planner 不能只知道“哪里还没挖够”，还需要知道“某个 cut 大概会造成什么效果”和“当前 ACT 是否能可靠执行这个 cut”。

因此至少需要两个配套模型：

```text
Effect model:
当前地形 + cut plan -> 预计 removed_depth_delta_grid / payload / uncertainty

Capability model:
当前 obs + 当前地形 + cut plan -> ACT/DP 执行成功概率 / 风险
```

这里的 effect model 就是类似 world/action model 的挖掘效果模型。它不需要一开始完美，可以分阶段做：

| 阶段 | 做法 | 作用 |
| --- | --- | --- |
| 几何近似模型 | 假设 bucket 沿 entry->exit 扫过一个带状区域，按宽度和目标深度移除土 | 最快跑通 residual planner |
| 经验统计模型 | 从 sim / rollout 数据统计某类 cut 通常移除多少土、获得多少 payload、失败概率多高 | 比手写 kernel 更贴近实际 |
| 学习型 effect / WAM | 输入 terrain patch、cut token、bucket pose，预测地形变化、payload 和不确定性 | 支撑更复杂地形和更精细评分 |

Capability model 的作用是约束上层不要给 ACT 任意目标。上层应只在 ACT/DP 的 reachable envelope 内选 cut。否则 residual planner 只是更聪明地给 token，底层仍然可能执行不出来。

### 3.4 如何根据残差选择下一铲 cut plan

Residual planner 规划的不是低层动作，而是下一铲预计改变哪块地形。一个 cut plan 至少应包含：

```python
CutPlan(
    entry_xz,
    exit_xz,
    target_surface_penetration,
    target_payload,
    expected_removed_depth_patch,
    confidence,
)
```

基本流程是：

```text
1. 找 residual 为正、置信度高、机器可达的区域
2. 围绕这些区域生成多个候选 cut
3. 用 effect model 预测每个 cut 的地形变化和 payload
4. 用 capability model 判断 ACT/DP 执行风险
5. 用 scoring function 选分数最高的 cut
6. 交给 ACT/DP 作为局部执行目标
7. 执行后重新观测地形并更新 residual
```

评分函数可以先从朴素版本开始：

```text
score(cut) =
  + 预计减少的正残差
  - 预计造成的超挖
  + 预计 payload 是否合理
  - ACT/DP 执行失败风险
  - entry / handoff / return 成本
  - 预测不确定性
```

这类评分不应由 LLM 直接“凭感觉”给出，而应基于可测量的地形残差、效果预测、执行能力和安全约束。

### 3.5 ACT、DP、MPC、LLM/VLM 的位置

在这个架构里，ACT 仍然是底层局部动作执行器，但不再承担“长期形状控制”的责任。更准确的要求是：

```text
给定当前 obs 和局部 cut intent，
ACT 执行后在统计上应朝减少 residual 的方向改变地形。
```

这比要求 ACT 厘米级跟随 entry / exit / depth 弱很多。如果 ACT 连“平均减少 residual”都做不到，就说明它不适合作为该任务的底层 executor，需要换更闭环的低层控制器，或者重新训练 terrain-conditioned / effect-aware policy。

DP 可能改善低层动作质量，因为它通常能生成更平滑、更可重采样的动作轨迹。但 DP 本身仍然不是地形 residual planner。除非 DP 的输入和训练目标显式包含 terrain residual 和地形变化，否则它只是更强的 imitation executor，而不是“指哪挖哪”的上层规划器。

MPC 的优势是显式使用模型预测未来状态，但完整土体物理 MPC 成本很高。更现实的路线是先做：

```text
高层 residual cut planner
-> effect / capability model
-> ACT/DP 或简单 feedback controller 执行局部 cut
```

LLM/VLM 更适合做语义层和辅助判断：

| 适合 LLM/VLM | 不适合 LLM/VLM |
| --- | --- |
| 把自然语言任务转成目标坑形、约束和验收标准 | 厘米级 grid residual 数值优化 |
| 识别场景、障碍、dump 区和高层风险 | 直接决定 bucket entry / exit / depth |
| 解释失败原因、生成候选策略、做人机交互 | 替代 effect model / capability model |

因此未来 planner 可以使用 LLM/VLM，但核心闭环仍应是数值的：

```text
target terrain map + current terrain map
-> residual
-> candidate cut planning
-> effect / capability scoring
-> low-level execution
-> terrain re-observation
```

## 4. 开始计划前需要验证的东西

在正式进入地形闭环 planner 或 LLM planner 前，需要先验证以下问题。

### 4.1 ACT 是否能作为可预测的粗执行器

需要验证：

- 同类地形状态 + 同类 cut target 下，ACT 是否大概率在指定区域移除土。
- 浅切、深切、长切、短切是否能产生可区分的统计效果。
- ACT 是否存在明显不可达或高失败率的区域、姿态、深度组合。
- 给定目标时，entry / exit / depth / payload 的误差分布是否稳定。

如果 ACT 的执行效果完全不可预测，那么 residual planner 也无法稳定收敛。这时应优先升级低层控制、反馈控制或训练范式，而不是接 LLM。

### 4.2 当前地形状态是否可信

需要验证：

- `env_state` 中的 removed depth / target depth 是否真实反映坑形变化。
- removed-depth grid 的更新是否及时、稳定、无遮挡或错位。
- 当前 coverage belief 和真实地形残差之间是否一致。
- 是否能区分 confirmed terrain、estimated terrain 和 uncertain terrain。

如果地形观测本身不准，planner 根据残差做出的下一铲选择就是错的。

### 4.3 当前 return 提前规划机制是否能承接新 planner

当前机制已经能在 return 阶段提前生成 return target 和 pending dig cut。下一步需要确认：

- 未来 terrain residual planner 是否能接入当前 `pending_dig_cut_*` 机制。
- return 过程中是否可以使用最新地形 belief 更新候选，但在 handoff 前锁定目标。
- 目标锁定后是否能避免临门跳变，保持连续性。
- 如果 return 过程中发现原目标不可达，是否有清晰 fallback 策略。

这一步的目标是保留“丝滑”，而不是把系统改成停顿式重规划。

### 4.4 区分 planner 目标问题和 ACT 执行能力问题

后续 audit 需要继续区分：

- planner 给出的 entry / exit / depth 是否合理。
- ACT 实际是否跟随这些目标。
- 土体变化后是否应该重新规划目标。
- payload 不足是否导致继续深挖。
- 过挖是否发生，以及过挖是否不可逆。
- success=1.0 的 rollout 是否真的满足形状、位置、深度质量要求。

## 总结

当前路线已经能证明：

```text
多铲流程可以跑。
```

但它还不能证明：

```text
系统能按目标形状稳定挖。
```

下一阶段应该先验证 ACT 是否能作为可预测的粗执行器，然后把主规划能力从 token 跟手升级为地形残差闭环规划。如果这个验证通过，最终的语义挖坑目标是可达的；如果验证不通过，就需要优先升级低层控制、反馈控制或训练数据，而不是直接接入 LLM。
