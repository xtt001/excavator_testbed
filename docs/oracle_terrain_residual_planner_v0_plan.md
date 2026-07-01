# Oracle Terrain Residual Planner v0 开发计划

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
- [ ] 用 bucket 尺寸、entry/exit、方向、目标 penetration 生成 expected delta patch。
- [x] 输出 expected removed volume、overdig volume、payload proxy 和 footprint。

Phase 4A note：

- `testbed.eval.terrain_candidate_effect_model.build_geometric_swept_footprint_effect()` 已定义 offline-only geometric swept-footprint / expected delta patch contract。
- 该 helper 只使用显式 candidate、row-major depth grids、target / valid masks、grid shape、cell size、bucket width/length 和可选 penetration depth；当前 run smoke 使用非官方示例几何 `cell_size_m=0.25`、`bucket_width_m=0.25`、`bucket_length_m=0.5`，不从当前 run 推断这些值。
- Footprint model 明确是 `centerline_rectangular_swept_footprint_approximation`，不是 calibrated bucket physics；它输出 row-major footprint cells、grid-boundary clipping、expected delta depth grid、expected removed volume、target/outside-target removed delta volume 和 overdig delta volume。
- 当前 run smoke 以 Phase 3C diagnostic best candidate `cut_candidate_000009` 为输入，得到 effect status `present`、footprint `[0, 2, 4]`、clipped `true`、penetration depth `0.191985052079` from `candidate_depth_m`、expected removed depth sum / volume `0.575955156237` / `0.035997197265`、target removed delta sum / volume `0.383970104158` / `0.02399813151`、outside-target delta sum / volume `0.191985052079` / `0.011999065755`、overdig delta sum / volume `0.201641567051` / `0.012602597941`，结果文件数保持 `10 -> 10`。
- Phase 4A 本身仍不是 production planner integration、official geometry defaults、top-k action selection、calibrated effect/capability model、payload proxy、pass/fail、eval success 或 planner success 语义；完整 entry/exit 和校准模型仍保持未完成。

Phase 4B note：

- `testbed.eval.terrain_candidate_effect_summary.build_candidate_effect_summary()` 已定义 offline-only candidate effect summary / payload proxy evidence contract。
- 该 helper 只读取 Phase 4A effect records 和显式 `payload_capacity_m3`；payload capacity 是调用方输入，不是 config/default/official bucket capacity，也不推断 material density、cycle time 或 fill model。
- 它按 effect record 输入顺序输出 summary records，包含 expected / target / outside-target / overdig volume、footprint count / clipped flag、payload proxy volume / fraction，以及 outside-target / overdig volume fractions；并输出 payload / outside-target / overdig 的 diagnostic rankings。ranking 只用于 evidence，不包含 selected/top-k/action 字段。
- 当前 run smoke 使用显式非官方 `payload_capacity_m3=0.04`，24 个 Phase 4A effect records 全部为 `present`，effect summary status `present`，payload proxy volume min / max / mean `0.005697766785` / `0.035997197265` / `0.015352705806`，payload proxy fraction min / max / mean `0.142444169625` / `0.899929931625` / `0.383817645159`。
- 当前 run max payload proxy candidate `cut_candidate_000009`，max outside-target volume candidate `cut_candidate_000003`，max overdig volume candidate `cut_candidate_000009`；结果文件数保持 `10 -> 10`。
- Phase 4B 仍不是 calibrated effect/capability model、production planner integration、official geometry/capacity default、top-k action selection、pass/fail、eval success 或 planner success 语义。

通过标准：

- residual planner + heuristic effect model 能在离线或仿真闭环中优于 current planner 的 target residual 指标。
- 如果不能优于 current planner，先定位 candidate 或 gate 问题，不急着训练模型。

### Phase 5: Calibrated effect / capability

- [ ] 使用 gold samples 做统计校准，修正深度增益、横向偏移、长度缩放和 payload。
- [ ] 增加 bootstrap 或 quantile uncertainty。
- [ ] 单独训练或拟合 capability filter，输出 `P_success`、`P_overdig`、`P_low_payload`。
- [ ] 使用 episode split 评估，禁止随机 sample split 泄漏。

通过标准：

- calibrated model 的 candidate ranking 明显优于 heuristic effect model。
- `P_overdig` 对真实过挖事件有足够召回，不追求只优化平均误差。

### Phase 6: Oracle residual planner 闭环仿真

- [ ] 比较三组 baseline：
  - A: current planner
  - B: residual planner + heuristic effect model
  - C: residual planner + calibrated effect model + capability filter
- [ ] 对 T1/T2 目标坑形跑多铲闭环。
- [ ] 记录每铲 residual、payload、overdig、handoff、deposit quality。

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
