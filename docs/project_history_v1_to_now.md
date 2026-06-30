# Excavator Testbed 从 V1 到当前的项目复盘

生成日期：2026-06-06

本文把 `/home/pingfan/PACT/excavator_testbed` 从 V1 baseline 到当前 V2.4.5 / primitive
scheduler 重构阶段中遇到的主要问题、解决思路、结果和遗留风险归纳到一处。它的目标不是替代
各阶段设计文档，而是给后续排查、重构和实验决策提供一份可回溯的索引。

## Scope And Sources

当前核对的 checkout：

- branch: `tx/2_4-YuLong_Planner`
- 当前工作树状态：除未跟踪 `.codex/` 外无已跟踪文件改动。
- 当前 `PrimitivePlannerACTPolicy` 仍是大文件，`wc -l` 为 `6516` 行。
- 当前分支没有 `docs/primitive_scheduler_service_refactor_plan.md`。
- 当前分支没有历史 rollout 中提到的单文件 `testbed/planner/dig_coverage.py`、
  `testbed/planner/return_handoff.py`、`testbed/planner/snapshots.py`、
  `testbed/planner/primitive_decisions.py`、`testbed/planner/return_start_envelope.py`；
  因此相关 service-object 结论在本文中按 `historical-record` 标注，不能直接当成当前
  checkout 的模块事实。

本轮当前仓库已核对来源：

- `docs/v1_to_v2_3_exploration_path.md`
- `docs/v2_1_failure_retrospective.md`
- `docs/v2_4plan.md`
- `docs/v2_4_5_spatial_mass_ownership.md`
- `docs/planner_to_act_conceptual_contract.md`
- `testbed/configs/README.md`
- `testbed/policies/hybrid/primitive_planner.py`
- `testbed/planner/boundary_detector.py`
- `testbed/cli/build_v2_4_hindsight_pipeline.py`
- `tests/test_agx_primitives_v2_2.py`
- `tests/test_hindsight_goal_v2_4.py`
- `tests/test_return_ckpt_audit.py`

本轮 memory / rollout 来源：

- `/home/pingfan/.codex/memories/MEMORY.md`
- `rollout_summaries/2026-05-26T06-00-45-1YlI-coverage_service_object_centralization.md`
- `rollout_summaries/2026-06-04T09-32-15-8DE6-primitive_scheduler_service_refactor_phase1.md`
- `rollout_summaries/2026-06-05T08-23-08-ixul-primitive_scheduler_service_object_refactor_workflow.md`
- `rollout_summaries/2026-06-05T08-22-29-lvYA-primitive_scheduler_service_object_refactor_instructions.md`

本轮执行的核对命令包括：

- `project-history-synthesizer/scripts/collect_project_history.py`
- `git status --short`
- `git log --oneline --decorate -20`
- `git branch --show-current`
- `rg --files docs testbed tests`
- `rg -n ... docs testbed tests`
- `wc -l ...`

没有运行 pytest。本文中的测试结果分两类：仓库历史文档或 rollout summary 中记录的历史结果标为
`historical-record`；本轮只核对了测试文件和断言入口是否仍存在。

状态标签：

- `verified-current`：本轮对当前 checkout 做过文件、源码或文档核对。
- `historical-record`：来自 memory、rollout summary 或历史文档，本轮没有复跑。
- `inference`：由多个来源归纳出的判断。
- `needs-confirmation`：涉及语义或主线取舍，后续需要用户确认。

## Timeline

阶段总览按同一逻辑展开：这一阶段为了解决什么问题、实际如何尝试、哪些事情证明有效、仍留下哪些不足。

| 阶段 | 为了解决什么问题 | 如何尝试 | 什么成功 | 存在什么不足 | 状态 |
| --- | --- | --- | --- | --- | --- |
| V1 baseline | 先证明 Python/Unity/AGX 数据、训练、评测链路能跑通，建立可重复比较的单铲业务基线。 | 使用 `teleop_v1` 录制，建立 HDF5 schema、ACT 训练、live eval、dataset QC、rollout logs 和 experiment record。 | 基础链路跑通；`data/agx_teleop_v1` 成为业务 baseline；历史记录中 `dump_complete_final_hold` 达到 `10/10` success。 | 只覆盖单铲短任务；strict 口径仍失败；不能证明多轮闭环和高质量 dump。 | `verified-current` for docs, `historical-record` for run result |
| fulltest / qvel 对照 | 解释 qpos-only baseline 在 dump 尾段释放时机、碰撞和稳定 hold 上的问题。 | 增加 `qvel` 输入对照，拆分 success 口径，记录 spill、collision、unsafe distance。 | 历史记录显示 `dump_complete_final_hold` 从 30% 提升到 60%，hard collision 和 unsafe distance 降低。 | 对照仍在 fulltest 线上；没有直接解决 V1 strict 质量和多轮泛化。 | `historical-record` |
| V2.1 Stage 1 | 从单铲扩展到自然连续多铲，并摆脱 fixed ready pose / ready-anchor。 | 录制自然连续 3 铲 raw episode；用 `qualified_dig_start` 和 `dump_end` 事件化 cycle boundary；构建 `/v2` relabel。 | 多轮任务有统一语义边界，recording、labeling、evaluation 可以对齐。 | QDS 对齐的是可观测事件，不保证 hidden state distribution 与人类 teleop 完全一致。 | `verified-current` |
| V2.1 Stage 2 | 在 ACT 还不能独立完成多轮任务前，先让多轮闭环可运行、可诊断。 | Hybrid：`WORK = ACT V1`，`TRANSITION = scripted corridor servo`，并记录 transition timeout、boundary jump、cycle success。 | 多轮 live 闭环原型跑通；transition 变成可测 handoff，而不是不可解释的动作尾巴。 | scripted transition 与人类 transition 分布仍不同；触发 QDS 不等于交给 ACT 的状态完全可接管。 | `verified-current` |
| V2.1 Stage 3 | 缩短 ACT 学习对象，减少从 reset 到 dump end 的长程行为克隆难度。 | 裁剪 `qualified_dig_start -> dump_end` workskill；训练 qpos/qvel、goal-token 和 clean-profile 变体。 | 建立 workskill sibling dataset；V1 source 只读、relabel/crop 写兄弟目录的流程清楚。 | workskill 仍是 monolithic；早期 dig/carry 偏差会积累到 dump；goal token 约束不够硬。 | `verified-current` |
| V2.1 Stage 4 | 让 planner 管 cycle-level 目标和 trace，同时检查 ACT 是否真的执行 planner intent。 | 引入 rule planner、sector belief、planner trace、soft corridor 和 coarse replan。 | planner 进入 live eval；开始区分 planner 选了哪里、policy 实际到了哪里。 | planner 只能提出 intent，低层 ACT 不一定可靠接收和执行目标；成功率可能掩盖目标偏差。 | `verified-current` |
| V2.1 Stage 5 | 验证 `dump_end -> next qualified_dig_start` 是否可以由 learned transition 替代 scripted transition。 | 构建 transition dataset，训练 learned transition candidate，并保留 scripted fallback / compare。 | learned transition 数据、训练和对照链路跑通；transition 失败可以被量化。 | learned transition 没有根治 workskill 内部漂移；在 boundary、goal conditioning、ownership 未稳定前收益有限。 | `verified-current` |
| V2.2 | 解决 monolithic workskill 内部污染，明确 dig/carry/dump/return 的 skill ownership。 | 拆成 `dig -> carry -> dump -> return` 四 primitive；分别训练 checkpoint；清理 carry tail；加 post-dump hold。 | 3-cycle smoke 历史记录达到成功；四 primitive 成为稳定主线；carry 不再默认吞 dump release。 | 仍有 spill、target clearance、数据量和高质量窗口不足；没有解决“下一铲挖哪里”的参数化问题。 | `verified-current` |
| V2.2 5P diagnostic | 检查 dump 是否应该进一步拆成 approach 和 release，以获得更清楚的 release timing。 | 尝试 `approach_dump` / `dump_release` 5P split，并查找专业 teleop 中的自然内部边界。 | 得到明确负结果：专业 dump 是混合动作，默认不应过度拆分。 | 5P 数据窗口少且 boundary 不自然；作为诊断保留，不适合作为主线。 | `verified-current` |
| V2.3 / V2.3.5 | 推进参数化挖掘、coverage planner、payload atom 和更长时程作业区规划。 | 引入 paramdig、surface-depth fields、square planner、truck-token、effect-based atom、planner rebind 等多线探索。 | 证明 parameterized dig、target-centric diagnostics、hard chunk barrier、effect-based boundary 都有价值。 | 一次改变 dig/carry/dump/return/planner/metrics 太多，dump/return 退化，归因困难；最终回退到 V2.2 稳线。 | `verified-current` |
| V2.4 | 让低层 ACT 真正响应 planner token，而不是继续复现专业师傅的平均动作习惯。 | Outcome-grounded hindsight goal-conditioned learning；从自然操作中离线反推 actual cut、payload、deposit、return target，并写入 dig/return outcome targets、removed-depth outcome。 | 取得的是数据/训练契约和诊断能力：可以检查 planner token、ACT 执行结果、removed-depth outcome 是否一致；问题焦点从“能不能连续跑完”推进到“为什么没有按 token 挖”。 | V2.4 本身不应表述为已严格通过 10-cycle。主要失败点是旧 return target 只描述下一铲 cut intent，不能约束 return handoff；旧 boundary 仍会污染 carry/dump/return。 | `verified-current` |
| V2.4.5 | 修正 V2.4 暴露的 handoff 和 boundary 污染：旧 `/v2` 标签和阶段驱动边界不等于真实 material cycle。 | 使用 `v2_4_5_spatial_mass` ownership；按空间/质量事件重切四 primitive；引入 Gate 1/2/3、qc6、return-start envelope、return-relocate。 | qc6 accepted split 成为训练/eval 数据源；`BoundaryDetector`、builder、configs、runtime 均接入相关语义；历史记录中 return-relocate 路径达到 10-cycle smooth milestone：10 次 dump 后 gate terminal hold，无 spill / hard target collision。 | 10-cycle smooth 只证明四 primitive 闭环和 return-relocate 路径能连续运转；当时还没有 per-cycle intent/execution/prior 精度表，不能当作“严格指哪挖哪”的最终验收。handoff、dig checkpoint、live observation/action scaling、coverage depletion 仍需长期 rollout 和离线 audit 区分。 | `verified-current` for docs, `historical-record` for 10-cycle run |
| 最近 service-object refactor | 降低 `PrimitivePlannerACTPolicy` 大文件风险，把 scheduler/coverage/handoff 逻辑迁入稳定 capability。 | 历史 rollout 中采用 behavior-preserving service extraction，保留 facade、行为锁和 targeted tests。 | coverage service、return handoff Phase 1 等历史记录显示该路线可行。 | 当前 checkout 与历史 service-object rollout 模块形态不一致；缺少对应 plan 文档，后续不能直接套用历史模块名。 | `historical-record` + `needs-confirmation` |

### V2.4 和 V2.4.5 的区别

V2.4 是 token/outcome 学习问题的提出和落地：把自然操作数据转成 hindsight goal，
让 `dig_cut_tokens`、`return_target_tokens`、payload、deposit、removed-depth outcome
进入同一套可训练、可审计的契约。它的结果不是“已经稳定挖 10 铲”，而是让系统能回答：
planner 计划挖哪里、ACT 实际挖到哪里、outcome 是否支持这个 token。

V2.4 暴露出的关键失败是 handoff 和 boundary 语义不够干净：

- 旧 `return_target_tokens` 描述的是下一铲怎么切，不是 return 应该回到什么 next dig-start
  state envelope，因此 return 可能提前下铲、卡 DigArea，或者把不在训练分布内的状态交给 dig。
- `return -> dig` handoff 过宽时，第二铲可能 0 mass / 浅挖；诊断中看到 live handoff 的
  plane depth 约 `0.30m`，而 qc6 cell1 gold dig-start 的 p05/p50 约 `0.57/0.59m`。
- `dig_complete` 只说明一次 dig 轨迹结束，不保证 bucket 有足够 payload；underloaded 状态切
  carry 后，carry 可能在错误状态 release 或让 planner 卡住。
- 旧 boundary 可能让 dump 吞掉还在去 dump area 的 transport / pre-adjustment，导致
  carry/dump/return 的训练责任混在一起。

V2.4.5 是针对这些失败做的工程收敛：用 `v2_4_5_spatial_mass` 按空间/质量事件重切
material cycle；用 qc6 作为 copy/train/eval 主数据源；把 return conditioning 从
“下一铲 cut intent”改成 `return_start_envelope_tokens_v1`，后续又用
`return_relocate_tokens_v1` 给 return 暴露 target-specific relocation 信息。历史记录中
V2.4.5 return-relocate 路径跑过 10-cycle smooth milestone，但这个结果只能说明闭环能连续运转，
不能替代每铲 intent/execution/prior 精度审核。

## Problems Encountered

### 1. “链路能跑通”和“策略学会任务”被混在一起

- Problem: 早期最关键的问题不是模型是否强，而是 AGX step-ack、backend、HDF5、训练、eval、QC 和日志能否跑通。
- Symptom: smoke eval 失败时容易误判为接口坏或日志坏。
- Root cause: 基础设施和学习结果缺少分层验收。
- Fix: V1 阶段建立 dataset QC、rollout jsonl、summary、manifest、experiment record，并把 success 口径拆开。
- Result: 后续能区分“接口/日志可用”和“ACT 质量不足”。
- Status: `verified-current`

### 2. V1 单铲 baseline 成功，但 strict 质量不过关

- Problem: 单铲完成不代表 dump 质量、尾段稳定、spill/collision 都满足严格口径。
- Symptom: `dump_complete_final_hold` 可成功，但 `strict_dump_complete` 历史记录仍为 0%。
- Root cause: V1 数据和 success 规则主要证明可学习性，没有覆盖多轮和高质量完成。
- Fix: 增加严格 success 口径、spill/collision 指标、qvel 对照。
- Result: qvel 历史对照改善 dump 末段，但 V1 仍只是业务 baseline，不是完整作业能力证明。
- Status: `historical-record`

### 3. V2.1 多轮失败不是单纯 transition 问题

- Problem: 第二铲失败常被视觉上理解成 dump 或 transition 问题。
- Symptom: cycle2 开始后，dig start 略偏会一路放大到 bite、carry、dump。
- Root cause: planner 的 coarse goal 没有强约束 ACT；`qualified_dig_start` 对齐语义，但没有完全对齐 hidden state distribution；BC 闭环泛化弱。
- Fix: 事件化 cycle boundary、scripted transition 可测化、goal-token 基础设施、per-cycle metrics。
- Result: 失败开始可定位，但 monolithic workskill 仍缺中间纠偏点。
- Status: `verified-current`

### 4. Learned transition 不是 cycle2 gap 的主解法

- Problem: 容易把 “dump_end -> next QDS” 学习失败当成主阻塞。
- Symptom: learned transition 数据和训练链路跑通，但并未根治 workskill 内部漂移。
- Root cause: workskill 目标条件、边界和 ownership 未稳定前，替换 transition 收益有限。
- Fix: 保留 learned transition 为候选和诊断线，默认仍依赖稳定 scripted handoff / fallback。
- Result: 后续重心转向 boundary、goal conditioning 和 primitive ownership。
- Status: `verified-current`

### 5. Monolithic workskill 的 ownership 污染

- Problem: 一个 ACT 从 `qualified_dig_start` 一路学到 `dump_end`，中间没有责任边界。
- Symptom: 失败看起来像 dump 坏，但真正 drift 可能来自 dig start、bite 或 carry 姿态；carry 可能学到 dump release。
- Root cause: 专业 teleop 是连续混合动作，BC chunk 跨越 skill 边界会把后续动作监督污染到前一个 skill。
- Fix: V2.2 拆成四 primitive，并规定 `dig = bite/load`，`carry = loaded transport`，`dump = approach/alignment/release/post-hold`，`return = empty bucket return`。
- Result: V2.2 成为稳定主线，后续 5P split 被证明不宜默认采用。
- Status: `verified-current`

### 6. Target geometry 不能只看一个无方向距离

- Problem: dump readiness 早期依赖 fixed swing 或单个 horizontal/outside distance。
- Symptom: planner 会把靠近 dump area 尾部和位于可倒料区域上方混为一谈。
- Root cause: 无方向距离缺失 signed `relative_x/z`、height、clearance、over-target 等语义。
- Fix: V2.2/V2.4.5 引入 dump-area relative geometry、committed aiming band、release onset 和 dump complete 物理事件。
- Result: carry/dump 边界从单点阈值改为过程式 ownership 和 causal rolling stability。
- Status: `verified-current`

### 7. 过度拆分 skill 会破坏自然动作

- Problem: 5P split 希望把 dump 进一步拆成 approach 和 release。
- Symptom: 干净 boundary 难找，训练窗口少，动作责任变碎。
- Root cause: 专业 dump 自然就是 swing/boom/stick/bucket open 混合动作，不存在稳定离散停点。
- Fix: 保留 mixed dump，5P 只作为诊断历史。
- Result: 主线回到四 primitive ownership。
- Status: `verified-current`

### 8. V2.3 一次引入太多语义，导致归因失败

- Problem: paramdig、coverage planner、truck-token、5P、rebuild carry/dump/return、new metrics 同时变化。
- Symptom: dump 和 return 退化，长 rollout 反复挖少数 cell，低层不一定到达 planner 目标。
- Root cause: 没有保护 V2.2 稳线；paramdig 的影响理论上不应传到 dump，但训练/数据/边界同时改变造成能力遗忘。
- Fix: 回退到 V2.2，把 paramdig、effect-based atom、hard chunk barrier 等作为下一轮重启材料。
- Result: 形成“只先参数化 dig，保护 carry/dump/return”的路线。
- Status: `verified-current`

### 9. Return target token 描述“下一铲怎么切”，不等于 return 应到达的起挖状态

- Problem: 旧 `return_target_tokens` / next cut intent 不能充分约束 return。
- Symptom: return 可能提前下铲、卡 DigArea、或把状态交给 dig 时仍不在训练分布。
- Root cause: return 的任务是回到 next dig-start state envelope，而不是执行下一铲 cut。
- Fix: V2.4.5 新增 18D `return_start_envelope_tokens_v1` 和 per-dim valid mask；return policy 读 envelope，pending `dig_cut_tokens` 留在 planner 侧用于下一铲。
- Result: dataset、runtime、ACT adapter、eval planner、config 文档均已接入该 low-dim key。
- Status: `verified-current`

### 10. `return -> dig` handoff 过宽会导致第二铲浅挖

- Problem: 单纯 latch `next_dig_entry_ready` 或 shallow contact 会过早切 dig。
- Symptom: 第二铲 0 mass、浅挖、handoff 状态和 pending token 描述的 entry envelope 不一致。
- Root cause: local-surface depth 和 plane-depth 语义不同；qc6 dig-start 的稳定边界需要 plane-depth / contact / qpos envelope。
- Fix: `return_to_dig_start_envelope_gate_enabled` 同时检查 pending entry-close、long/short、local depth/contact、qpos 和 plane-depth p50 floor；detector event latch 后等待 envelope gate 同步 ready。
- Result: current code 中 `_return_to_dig_handoff_ready` 仍由 entry-close 和 envelope-ready 共同决定；debug 中保留 `return_to_dig_start_envelope_checks`。
- Status: `verified-current`

### 11. Dig complete 不代表 carry 有足够 payload

- Problem: `dig_complete` 只说明一次 dig 轨迹结束，不保证 carry/dump 可执行。
- Symptom: underloaded 状态切到 carry 后，carry policy 可能在错误状态 release，planner 卡住。
- Root cause: skill handoff 没有区分 dig trajectory completed 与 material payload enough。
- Fix: V2.4.5 planner 对 low-current-payload `dig_complete` 拒绝当前 cell 并 replan；carry 中如已发生 release，则 safety latch 转 return。
- Result: 当前 `_maybe_switch_skill` 中仍可看到 `dig_complete_low_current_payload` 和 carry release safety 路径。
- Status: `verified-current`

### 12. Planner 大文件和 service-object 边界仍是长期维护风险

- Problem: `PrimitivePlannerACTPolicy` 仍承担 scheduler、handoff、coverage、token 注入、debug/summary 等大量职责。
- Symptom: 当前文件 6516 行；大文件策略禁止在其中继续新增实质 algorithm / semantic branch。
- Root cause: 历史上为了快速推进 rollout 语义，很多稳定 capability 没有及时抽成独立模块。
- Fix: 最近 memory 记录的方向是 behavior-preserving service extraction：先行为锁，再迁移一个稳定 responsibility slice，保留旧 facade。
- Result: 历史 rollout 中 coverage service / return handoff Phase 1 有成功记录；但当前分支模块形态与该 rollout 不一致，后续必须先做 branch-specific reflection check。
- Status: `historical-record` + `needs-confirmation`

## Fixes And Results

### 已经证明有效的解决思路

- 把基础设施验收和 policy 质量验收分开：先保证 recording / train / eval / QC / logs 可用，再讨论模型能力。
- 把 success 口径拆开：`dump_complete_final_hold` 可以代表任务完成，`strict_dump_complete` 才代表高质量完成。
- 加 `qvel` 作为动态状态输入：历史 fulltest 对照显示对 dump 尾段明显有帮助。
- 用事件化边界替代 fixed ready pose：`qualified_dig_start` 让多轮 relabel/eval/handoff 有共同语义。
- 用四 primitive ownership 替代 monolithic workskill：这是从 V2.2 开始最稳定的系统切法。
- 保留 mixed dump：不要把专业连续倒土动作强拆成 release-only skill。
- 用 target-centric diagnostics 解释 planner 和 ACT 的偏差：selected target、actual QDS cell、actual removal cell、deposit fraction 需要分开记录。
- 用 `v2_4_5_spatial_mass` 把 primitive boundary 从标签/阶段驱动收敛到空间/质量事件驱动。
- 用 `return_start_envelope_tokens_v1` 表达 return 应到达的 dig-start 分布，而不是把 next cut token 塞给 return。
- 用 handoff gate 约束 skill 交接，但保持 planner 不写 joystick/qpos 轨迹。
- 用 Gate 1/2/3 和 contact sheet 人工审阅，把训练前 QC 和人工语义确认变成流程。
- 对 refactor，采用 behavior-preserving service extraction，而不是在大文件里继续添加新语义。

### 当前仓库已验证存在的实现入口

- `BoundaryDetector` 支持 `v2_4_5_spatial_mass` profile。
- `PrimitivePlannerACTPolicy._maybe_switch_skill` 是在线状态机核心入口。
- `PrimitivePlannerACTPolicy._return_to_dig_handoff_ready` 由 entry-close 和 envelope-ready 共同决定。
- `PrimitivePlannerACTPolicy` debug state 包含 return-start envelope 相关开关和检查信息。
- `tb-build-v2_4-hindsight-pipeline` 仍检查 `/v2/step/return_start_envelope_tokens_v1` 和 valid mask。
- `tests/test_agx_primitives_v2_2.py` 覆盖 `return_start_envelope_tokens_v1`、`cell_weighted_3x2`、`return_to_dig_start_envelope_gate_enabled` 等语义。

## Decisions Preserved

- V1 是业务 baseline，不是完整多轮作业能力证明。Status: `verified-current`
- V2.2 四 primitive 是稳定主线；5P split 和 payload atom 是诊断/研究路线，不是默认主线。Status: `verified-current`
- Planner 只提出任务级 goal/token、维护 belief、切换 skill、执行少量 readiness/safety gate；不手写 joystick/qpos 轨迹。Status: `verified-current`
- `return_start_envelope_tokens_v1` 和 `dig_cut_tokens` 语义不同：前者描述 return 要回到的可接管状态，后者描述下一铲要切什么。Status: `verified-current`
- `BoundaryDetector` 应是 event source，不应吸收 target selection 或 scheduler 决策。Status: `verified-current` + `historical-record`
- 行为保持重构的核心约束是 branch order、threshold、switch reason、terminal reason、debug/summary schema、policy reset timing、default config、token contract 和 rollout 输出不漂移。Status: `historical-record`
- 不确定语义时停止确认，不从聊天记录或当前假设中擅自决定官方语义。Status: `historical-record`

## Regression Locks

当前可用的锁定面：

- `docs/planner_to_act_conceptual_contract.md`：planner/ACT 职责、token 语义、V2.4.5 handoff 语义的概念源文档。
- `docs/v2_4_5_spatial_mass_ownership.md`：V2.4.5 primitive ownership 和 boundary profile 的详细标准。
- `testbed/configs/README.md`：配置、dataset、token、boundary profile 和训练入口索引。
- `tests/test_agx_primitives_v2_2.py`：当前最集中的 primitive planner / V2.4.5 语义测试面。
- `tests/test_hindsight_goal_v2_4.py`：hindsight goal / return envelope key 相关测试面。
- `tests/test_return_ckpt_audit.py`：return checkpoint audit 工具测试面。

历史 rollout 记录中的锁定面：

- coverage service direct-vs-facade parity tests。
- return handoff service tests。
- planner golden trace reset count parity。
- debug schema tests。
- `pytest tests -q` 历史记录曾达到 `359 passed, 41 warnings, 13 subtests passed`，但该结果来自另一个历史 checkout，本轮未复跑。

## Open Risks

- 当前 branch 与最近 service-object rollout 的模块形态不一致。后续若继续 refactor，必须先确认目标分支和 source-of-truth 文档，而不是直接套用历史 Phase 1 模块名。
- `PrimitivePlannerACTPolicy` 已超过 1000 行很多倍。根据 `AGENTS.md`，不应继续在该文件新增算法逻辑或新语义，只能做 facade、adapter、删除旧实现、或把行为迁移到小模块的薄接口工作。
- `docs/primitive_scheduler_service_refactor_plan.md` 在当前 checkout 缺失；若后续还要按 service-object 路线推进，需要先恢复、重建或确认新的 authoritative plan 文档。
- V2.4.5 的 `return_start_envelope_tokens_v1` / plane-depth / contact / qpos gate 已经收紧 handoff，但第二铲浅挖、dig checkpoint、live observation/action scaling、temporal aggregation 仍需要按离线 audit 区分。
- `cell_weighted_3x2`、state-conditioned exemplars、coverage depletion 和 bad-dig replan 仍需要长期 rollout 证据，不能只看单次 smoke。
- 训练数据路径、checkpoint path 和 token contract 分散在 docs/configs/tests/code 中；新增语义时必须先确认 source of truth，避免复制定义。
- 对“当前结果是否已训练通过”的表述要谨慎：很多 run 结果来自历史文档，当前本轮只做了文档/源码核对，没有复跑训练或 eval。

## Next Documentation Targets

- 若继续 primitive scheduler service-object refactor，先补当前分支对应的 authoritative plan 文档，或明确 `docs/primitive_scheduler_service_refactor_plan.md` 应从哪个分支恢复。
- 给 `PrimitivePlannerACTPolicy` 当前 6516 行职责做一次 branch-specific map：scheduler state machine、return handoff、coverage、pre-dig-align、debug/summary、policy adapter 分别占哪些区域。
- 把 V2.4.5 的“历史 run 结果”和“当前 checkout 已验证事实”分开维护，避免后续 agent 把历史数字当成本轮刚验证结果。
- 为每轮 refactor 建立固定复盘记录：目标 slice、行为锁、改动文件、测试命令、未验证风险、是否同步 source-of-truth docs。

## Final Summary

从 V1 到现在，项目主线经历了三次关键收敛。

第一次收敛是 V1：先证明 AGX/Python/ACT 的数据、训练、评测和日志链路能跑通，但也明确单铲成功不等于严格质量和多轮作业能力。

第二次收敛是 V2.2：V2.1 的多轮失败不是 learned transition 一个点能解决的问题，而是 goal conditioning、state distribution、BC covariate shift 和 monolithic workskill ownership 共同作用。四 primitive ownership 把问题拆开，成为后续稳定主线。

第三次收敛是 V2.4.5：V2.3 证明参数化和 coverage 是必要方向，但一次改太多会破坏稳定能力。V2.4.5 改为用空间/质量物理事件重切 ownership，用 return-start envelope 表达 handoff 分布，并把 planner 的边界固定在 task-level intent 和 readiness gate，而不是动作级控制。

当前最大的工程风险不再是“有没有方向”，而是“如何在已有复杂语义上继续推进而不漂移”：大文件 planner 需要行为保持式拆分，token/boundary/profile 需要单一 source of truth，所有历史聊天总结都必须回到当前 checkout 验证后才能转成当前事实。
