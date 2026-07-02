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
- [ ] 比较三组 baseline：
  - A: current planner
  - B: residual planner + heuristic effect model
  - C: residual planner + calibrated effect model + capability filter
- [ ] 对 T1/T2 目标坑形跑多铲闭环。
- [ ] 记录每铲 residual、payload、overdig、handoff、deposit quality。

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
