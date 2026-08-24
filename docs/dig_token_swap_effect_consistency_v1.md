# Dig token-swap 冻结物理结果约束 v1

## 当前结论

实现与离线前置实验已经完成，但 A/B/C 微调没有启动。冻结的
`dig_action_effect_model_v1` 未通过预注册的物理可信度门，因此三臂均为
`executed_steps=0 / planned_steps=2000`。停止发生在 ACT checkpoint 加载和
optimizer 创建之前；生产 checkpoint、时序聚合、planner 默认、协议和安全链均未改变。

权威 no-overwrite 根为：

`runs/eval/dig_token_swap_effect_consistency_20260822T150051+0800/`

其中 `ablation_precondition/decision.json` 和 `report.md` 是本轮最终决定。此前的
`effect_model`、`effect_model_v2`、`variants`、`variants_v2` 是保留的失败开发尝试；
最终输入固定为 `effect_model_v3` 和 `variants_v3`，不得事后覆盖或重标。

## 冻结合同

- `fixed_tip_fk_artifact_v1`：Unity Editor 只读打开已锁 SHA 的 scene，在 Edit Mode
  创建 `HideAndDontSave` shadow-FK service。没有进入 Play Mode、推进 simulation、发送
  action 或保存 scene。32 个 strict-support 姿态的 Python/Unity 最大误差为
  `3.9321e-6 m`，低于 `0.002 m` 门。
- `dig_action_effect_windows_v1`：使用现有自然 Dig 数据。train/validation 分别有
  `39193/6472` 个 100-step action + pre-action observation 窗口；context 只含 t0 的
  qpos/qvel 和六格 surface/removed/target/valid，不含 token、hindsight outcome 或未来观测。
- `dig_action_effect_model_v1`：三个 seed 的 GRU ensemble 不接收 token。它预测 qpos，
  再经冻结 FK 得到固定中齿轨迹，并预测六格 removed-depth 与 payload。冻结后参数无梯度，
  但 action 输入保留梯度。
- `planner_reachable_dig_variant_v1`：自然 token 只服务 BC/hindsight；swap 分支先将当前
  observation 投影为自洽的 `ContinuousCutGoal` planner 基准，再生成固定的 position、depth
  和可达 adjacent-cell 变体。每个变体同时通过 p10-p90、18D axis support、有效 cell、
  remaining-depth 和 fixed-tip p25 reachability。
- `token_swap_effect_consistency_loss_v1`：包含 2 cm tracking、own-goal ranking、按 token
  差异比例计算的 position/depth separation、目标 cell effect、action support 和 ensemble
  uncertainty。C 关闭旧 swapped-outcome loss；A/B 仍固定 `token_swap_loss_weight=1.0`。

## 实际门控结果

`effect_model_v3` 在 source 33/34 上的结果为：

- fixed-tip trajectory MAE `0.132864 m > 0.04 m`；
- endpoint MAE `0.245817 m > 0.03 m`；
- positive-effect removed-depth MAE `0.008851 m > 0.005 m`；
- shuffle-action error worsening `2.668 > 0.20`，说明模型确实使用 action；
- ensemble p95 fixed-tip disagreement `0.202517 m > 0.02 m`。

变体覆盖门本身通过：train `1769`，validation `269`，其中 validation 包含
position `220`、depth `44`、adjacent-cell `5`，且 source 33/34 均有样本。

source 33/34 的指标已在 v1/v2/v3 诊断迭代中被查看，因此不能再把后续针对这些指标的模型
调整称为全新 held-out promotion 证据。修复 predictor 时应在 strict-train source 内建立新的
开发/选择折，再将架构和阈值冻结后只做一次独立最终评估。

## 下一步边界

只修复并重新冻结 action→物理结果 predictor。新 predictor 未通过相同门之前，不运行
A/B/C、不提高 token-swap 权重、不重训正式 checkpoint，也不恢复 Unity Dig A/B。

## 2026-08-22 source-grouped predictor 定位

后续工作只处理 effect predictor，没有加载或修改 ACT。strict-train 的 16 个 source 被一次性冻结为
四个互斥开发折：

- fold 0: `[6, 9, 23, 32]`；
- fold 1: `[24, 27, 28, 30]`；
- fold 2: `[13, 16, 19, 25]`；
- fold 3: `[3, 7, 8, 29]`。

折分单位是 source，不是随机窗口。训练采样先让各 source 等权，再让同一 source 内各 primitive
episode 等权。正式报告同时保存 per-window、per-episode equal、per-source equal、by-source 和
worst-source。source 33/34 没有参与结构、超参数、early-stop 或选择，本轮也没有重新评估。

新模型只做一步 `qpos/qvel + action -> next qvel`；`next qpos` 使用数据已验证的
`qpos[t+1] = qpos[t] + qvel[t+1] * 0.02 / raw_range`。固定中齿继续使用已通过微米级交叉验证的
静态 FK。四折三 seed 的 OOF fixed-tip per-source equal 误差为：

- 1/5/10 step: `0.000725 / 0.005986 / 0.014777 m`；
- 25/50/100 step: `0.040282 / 0.071962 / 0.225685 m`；
- 100-step trajectory mean: `0.084032 m > 0.04 m`；
- 100-step ensemble p95 disagreement: `0.054990 m > 0.02 m`。

因此一步映射准确，失败定位为 `long_horizon_dynamics_accumulation`。轨迹门未通过，所以没有冻结
最终 dynamics predictor、没有训练独立 removed-depth/payload head，也没有加载 ACT 或创建 A/B/C
optimizer。权威工件位于
`runs/eval/dig_token_swap_effect_consistency_20260822T150051+0800/predictor_source_grouped_v1/`。

### Joint rollout curriculum 与 observability

分轴复查确定 bucket 是最早发散轴：5-step bucket qvel error 是次差轴的 `1.732×`；原一步模型在
100 step 的 bucket qpos/qvel per-source equal 误差为 `0.149767/0.767936`。在不改变 256 hidden、
不提高 loss 权重的前提下，训练改为完全自回归，并依次使用 `5→10→25→50→100` horizon。损失由
归一化 next-qvel、积分 qpos、固定齿尖、速度连续性和 qpos range 五项等权组成。

软 qpos penalty 仍允许越界，因此最终版本在每一步积分后硬投影到已知 `[0,1]`。同一 source folds
上的最终 per-source equal 指标为：

- 1/5/10/25/50/100-step tip：`0.000787/0.006079/0.013612/0.029639/0.044634/0.056302 m`；
- trajectory：`0.040195 m > 0.04 m`；
- endpoint：`0.056302 m > 0.03 m`；
- ensemble disagreement：`0.021728 m > 0.02 m`。

多步训练明显改善了长程误差，但仍未通过冻结门。observability audit 发现：bucket 一步残差与
lag 1–10 action 的最大 source-均衡平均绝对相关只有 `0.02767 < 0.20`；现有 HDF5 还缺少
`final_target_speed`、`acceleration_limited_mask`、cylinder position 和 cylinder velocity。该结果只形成
“缺执行器响应状态”的候选解释，随后用显式有限历史模型做了直接检验。

### Bucket finite-history 输入比较

该比较只训练 bucket 残差修正器。原三成员 joint curriculum checkpoint 全部保持 `eval()` 且
`requires_grad=false`；每一步的 swing/boom/stick qpos 与 qvel 直接取冻结基座，最终折外轨迹的最大绝对差为
`0.0`。输入固定为四臂：当前 qpos/qvel + action、再加 5 步 action、再加 10 步 action，以及 5 步
action + bucket qvel + 冻结基座预测残差。四臂使用相同 source folds、seed、source/episode 均衡采样和
`5→10→25→50→100` 课程，每阶段 100 次更新；没有根据结果调整网络、损失或门槛。

共评估 strict-train 内 16 个 source、331 个 primitive episode 和 35,573 个完整历史窗口。第 5 步的
per-source equal 结果为：

- 无历史臂：bucket qvel `0.045053`，qpos `0.00117572`，bucket-isolated fixed-tip
  `0.00171520 m`；
- 5/10 步 action history 的 qvel 改善仅 `0.45%/0.90%`；10 步的配对 95% 区间还跨过 0；
- action + qvel + residual history 的 qvel 改善 `8.55%`，配对 95% 区间为
  `[6.16%, 11.19%]`；qpos 和 fixed-tip 都改善 `11.23%`。

最后一臂有稳定但有限的收益，仍低于预注册的 qvel/qpos/fixed-tip `30%/30%/20%` 门；bucket 对冻结其余
轴的第 5 步 qvel error ratio 仍为 `1.673 > 1.5`。100 步 bucket qvel/qpos/bucket-isolated fixed-tip
仍为 `0.271644/0.0238205/0.0346477 m`。因此有限历史没有消除第 5 步发散，不能把根因固定为状态窗口太短。

分层结果显示问题集中在关节边界：near-boundary 第 5 步 qvel 为 `0.178388`，而 interior 为
`0.0404995`；`qpos∈[0.8,1.0]` 的误差为 `0.265234`，response history 还轻微恶化到 `0.269143`。
最差 source 仍是 24。完整历史条件还使 374 个 train episode 中只有 331 个能形成窗口；source 19/23
分别只有 90/11 个窗口和 2/1 个 episode，source 等权结果必须保留这一覆盖边界。controller epoch/profile
的未配对分层存在差异，但最近历史配对并不支持其为直接原因：
最相似 10% 跨 episode 历史的标准化距离为 `0.1210`，下一步 qvel 响应差中位数只有 `0.00169`，低于
`0.02` 歧义门；跨 epoch/标定对的响应差也没有高于同 metadata 对。

正式分类为 `insufficient_bucket_history_fit_or_coverage`。下一步先审计边界窗口、少样本 source 和集中异常
episode 是否包含关节饱和、状态跳变或不完整 controller epoch 覆盖；不增加模型、不提高损失权重，也不把
未配对的 controller cohort 差异写成因果结论。权威 no-overwrite 工件为
`predictor_source_grouped_v1/bucket_only_v1/comparison_full_v1/`。soil head、ACT、Unity 和生产默认继续保持未启动或未改变。

### Bucket 数据分层只读定位

随后基于上述 OOF 误差和原始 HDF5 元数据执行了纯只读定位，没有加载模型、重训、删除样本或修改 support。
主指标固定为 `response_history_5` 的 h5 bucket normalized-qvel MAE，`state_action` 只作参照。

边界是唯一通过预注册定位门的因素。距最近 qpos 边界不超过 0.05 的 source 等权误差为 `0.173959`，内部为
`0.0364567`，比值 `4.772×`；13 个共同 source 的配对 bootstrap 95% 区间为 `[3.363,6.784]`。即使先
移除误差质量最高的 5% episode（17 个），该比值仍为 `3.105× [2.537,5.127]`。按上下边界分别使用固定
距离分箱，并要求纳入区间的误差不超过各自核心区间的 2 倍后，得到非对称可信支持候选
`bucket qpos normalized ∈ [0.05,0.80]`。这是 predictor 证据范围候选，不修改生产关节范围、planner 或默认 support。

episode 确有长尾，但不是 source 等权失败的主因：误差质量最高 5% episode 占总 per-window 误差
`43.67%`，移除后 per-window 改善 `33.19%`，source 等权只改善 `11.00% < 15%`。episode 324/191
分别占 `12.73%/10.46%` 的窗口误差质量且都是长 episode，但单独 leave-one-out 对 source 等权指标只改善
`1.69%/0.34%`。因此保留为数据核查对象，不能据此自动排除。

leave-one-source-out 中 source 24/30 分别改善 source 等权误差 `7.42%/4.45%`，但相近 qpos/qvel 和前
5 步 action 的一对一匹配没有留下任何合格 source：source 24 只有 36 对、平衡后最大标准化均值差
`0.671 > 0.10`，99% 区间跨 0。controller epoch 的 h5 匹配只有 95 对，最大平衡差 `0.156 > 0.10`，
post-pre 为 `-5.42%` 且 95% 区间跨 0；h1 同样跨 0。全部数据只记录一个 calibration schema，无法比较
标定版本。先前未配对的 controller cohort 差异因此不能解释为控制时期因果。

最终分类为 `tighten_predictor_trust_support`。权威 no-overwrite 工件为
`predictor_source_grouped_v1/bucket_only_v1/read_only_localization_v2/`。下一步若实施，应只把
`[0.05,0.80]` 接入 predictor 离线可信度/不确定性门并重新计算轨迹 gate；在另行确认前不改变训练数据、
planner、ACT 或生产默认配置。

### `[0.05,0.80]` 内部范围冻结 predictor 复评

内部范围复评没有重训。窗口选择在任何 checkpoint 加载前完成，只读取真实数据：初始 bucket qpos 和真实
未来 100 步 bucket qpos 都必须在 `[0.05,0.80]`；qvel/action 的逐轴 p01-p99 从原 one-step
strict-train transition cache 冻结，并应用到过去 10 步、当前状态和真实未来 100 步。筛选不读取模型预测或
误差。35,573 个完整历史窗口最终保留 12,922 个（36.33%）。

同一四折三成员冻结 checkpoint 的 `response_history_5` OOF source 等权结果为：

- bucket qvel h1/5/10/25/50/100：
  `0.011604/0.033586/0.046074/0.048876/0.034084/0.062501`；
- bucket qpos：
  `0.0000935/0.0009119/0.0024387/0.0073116/0.0110735/0.0156435`；
- full fixed-tip：
  `0.000513/0.004142/0.009545/0.022703/0.036220/0.046381 m`。

100 步 full-tip trajectory mean 为 `0.031580 m ≤ 0.04 m`，通过；ensemble p95 disagreement 为
`0.013407 m ≤ 0.02 m`，通过；但第 100 步 endpoint 为 `0.046381 m > 0.03 m`，失败。冻结 joint base 的
对应三项为 `0.032177/0.047175/0.014853 m`，说明 bucket 修正只有有限改善，末端失败不是由边界样本单独造成。

覆盖门也独立失败。保留集只有 197 个 episode 和 14 个 source；source 19/23 均为 0 窗口，低于冻结的
250 episode、16 source、每 source 至少 50 窗口/2 episode 门。最终分类为
`audit_actuator_state_or_change_predictor_structure`：不能冻结动力学 predictor，也不能开始 soil effect model。
下一步才检查执行器 target speed、限速器/cylinder response 等缺失状态，或改用更适合长程 rollout 的
predictor 结构。权威工件为 `bucket_only_v1/internal_support_eval_v1/`；ACT、planner、真实挖机范围和生产默认未改变。

### 一步残差隐藏状态只读定位

在换 predictor 结构前，使用当前 `qpos+qvel+action` joint predictor 的 OOF 一步 bucket qvel 有符号残差
`actual_next_qvel - predicted_next_qvel` 做了最小状态归因。只保留当前 bucket qpos 在 `[0.05,0.80]`、
当前 qvel/action 通过原 strict-train p01-p99 的真实行，共 53,229 行、373 个 episode、16 个 source。
模型保持冻结，没有 residual target 参与筛样本。

一步绝对残差 source 等权 MAE 为 `0.015436`，signed bias 为 `0.001713`。每个状态对照都要求相近
qpos/qvel/action、跨 source、一对一匹配、至少 100 对和 3 个 source 对、最大标准化均值差不超过 0.10，
并使用 source-pair cluster 99% bootstrap。

现有物理字段没有一项通过完整解释门：

- 静态载荷 top quartile 的描述性 MAE 为 `0.019404`，bottom quartile 为 `0.014754`，但 empty/loaded
  只得到 97 对，balance `0.1045 > 0.10`，99% 区间跨 0；quartile 匹配更稀疏。
- `bucket_mass_delta_kg` 的 stable/gaining 与 q25/q75 对照分别有 727/819 对，balance 约 `0.032`，但
  signed/absolute effect 都很小且区间跨 0，说明已记录的载荷变化率不能解释剩余残差。
- depth q25/q75 有 135 对但 balance `0.203`，区间跨 0；几何 contact mask 只有 354 个 no-contact 行，
  最终仅 2 个合格匹配。
- 最近 10 步反向有 357 行，但仅 20 对且 balance `0.906`；效果方向虽较大，不能作结论。controller
  epoch/profile 各有 253 对，但 balance `0.172` 且 99% 区间跨 0。action calibration valid 恒为 1。

现有 `target_contact_max_normal_force_n` 是目标箱接触力，在这些 Dig 行中恒为 0，不能代表 bucket/土体阻力；
`boundary_mask` 是 primitive 生命周期边界，不是关节软限位。数据未记录 soil worktool force/resistance、
Unity final target speed、acceleration/soft-limit mask、bucket cylinder position/velocity 或液压压力/执行器力。

最终分类为 `collect_missing_actuator_and_contact_telemetry`。权威工件为
`bucket_only_v1/residual_state_audit_v3/`；v1/v2 保留为历史开发工件，v2 修复了反向定义，v3 又补齐
`bucket_mass_delta_kg`。下一步只做同初态/同 bucket 动作序列的 no-contact 与 controlled-contact 小样本采集，
建议每条件 3 次独立 session，并让固定序列包含一次 neutral 过渡后的反向。swing/boom/stick 保持冻结，
不加载 ACT。只有新字段形成 source/session 分组数据后，才运行固定预算 A/B/C；若 endpoint 仍高于 3 cm，
放弃当前冻结 predictor 路线。

### 周期性真实状态重锚诊断

在补遥测或改结构前又执行了一次低成本判别。它复用内部范围复评的同一批 12,922 个窗口、四个 source folds、
三成员 joint base 与 `response_history_5` corrector，不重新筛样本、不训练。每隔 1/5/10/25 步，在本步预测
误差已经记录后，把下一步输入的 qpos/qvel 替换为真实状态；action/history contract 和 checkpoint 均不变。

100 步 full fixed-tip endpoint 的 source 等权误差分别为：

- interval 1：`0.000433 m`；
- interval 5：`0.003097 m`；
- interval 10：`0.006721 m`；
- interval 25：`0.016091 m`。

四个 source 等权值均低于 3 cm，因此分类为 `autoregressive_accumulation_primary`。按 worst-source 稳定门，
interval 1/5/10 的最差值为 `0.000924/0.005077/0.010843 m`，仍通过；interval 25 的 source 24 为
`0.032449 m > 0.03 m`，所以最大稳定间隔收紧为 10 步。冻结 joint base 的结果与 corrector 很接近，说明
当前主要瓶颈是长程自回归累计，有限 bucket correction 不是决定因素。

覆盖门仍失败：这批数据只有 197 个 episode、14 个 source，source 19/23 缺失。因此该结果只允许下一轮
比较“小型直接轨迹模型”和“紧凑隐状态长程模型”，且必须沿用相同训练预算、source/session folds 和 3 cm
source-equal + worst-source 双门；不能冻结正式 predictor、训练 soil head 或恢复 ACT A/B/C。任何新结构若
仍不能同时通过 3 cm 与覆盖门，应正式停止离线物理约束支线，不能把门放宽到 5 cm。权威工件为
`bucket_only_v1/reanchor_eval_v2/`；v1 仅保留为未加入 worst-source 稳定门的历史工件。

### Direct trajectory 与 compact hidden-state 等预算比较

按重锚结论执行了最后一个结构对照。两个模型使用完全相同的 12,922 个 selected windows、四个 source folds、
三个 seed、source/episode 均衡权重、每 seed 的逐 batch sample schedule、五项等权物理 loss 和每成员
`2000 updates × batch 128`。direct MLP 为 226,400 参数，compact action-history GRU 为 181,208 参数，
比例 `1.249 < 1.30`。两者都读取 initial qpos/qvel、过去 10 步 action 和未来 100 步 action；没有状态重锚，
也没有加载 ACT 或训练 soil head。

最终 OOF source 等权 / worst-source 结果为：

- direct full-trajectory MLP：trajectory `0.109417 m`，endpoint `0.116209 m`，worst source 24
  `0.184532 m`，ensemble disagreement `0.092906 m`；
- compact hidden-state GRU：trajectory `0.091635 m`，endpoint `0.122010 m`，worst source 32
  `0.181832 m`，ensemble disagreement `0.052354 m`。

两种结构都同时失败于 4 cm trajectory、3 cm source-equal endpoint、3 cm worst-source endpoint 和 2 cm
disagreement。GRU 的轨迹和分歧较好，direct MLP 的平均末端略好，但两者都远离正式门；即使改成禁止的
5 cm 也不会通过。覆盖门仍只有 197 episode、14 source，同样失败。

最终分类为 `stop_offline_predictor_route`，没有 winner，也没有冻结任何 dynamics predictor。当前
token-swap effect-consistency / 离线物理约束支线在此正式停止；不得继续调大模型、加 loss、训练 soil head、
恢复 ACT A/B/C 或重标 5 cm 成功。权威工件为 `bucket_only_v1/structure_comparison_full_v1/`；
`structure_comparison_smoke_v1` 只保留为 2-update 接线烟雾工件。

## 2026-08-23 ACT latest-feedback dispatch 离线诊断

`dig_act_receding_horizon_dispatch_diagnostic_v1` 已完成。它只比较两种 dispatch：正式
`ACTAdapter.predict()` 的 legacy oldest-first temporal aggregation，以及默认关闭、request-local 的
latest-chunk 首动作。112 个 position-translation 变体分别绑定 112 个独立 episode，来自 11 个
strict-train source；每个变体使用相同的 baseline/alternate recorded observation，共回放 100 帧。
source 33/34 没有参与筛选、阈值或评估。

raw 100-step chunk 的 source 等权响应率为 `80.89%`，仍高于固定 80% 门。legacy cache 的 contributor
age 实际覆盖 `0–99` 帧，中位数为 29 帧，p99 为 90 帧。随后在 91 个 recorded-state 锚点上分别执行
5/10 步冻结 joint-dynamics + fixed-tip FK 投影；每个窗口从真实 qpos/qvel 重新开始，不使用失败的
100-step rollout 作为物理证据。

10-step source 等权结果为：

- own-goal direction success：legacy `26.72%`，latest `24.34%`；latest 下降 `2.37` 个百分点，
  paired 95% 区间为 `[-3.71,-1.26]` 个百分点；
- own-goal ranking accuracy：legacy `50.33%`，latest `50.26%`；paired 95% 区间为
  `[-0.21,0.09]` 个百分点；
- projected tip separation p10：legacy `0.411 mm`，latest `0.485 mm`，均远低于 `20 mm` 门；
  latest 的平均 separation 反而少 `1.01 mm`，paired 95% 区间为 `[-1.48,-0.61] mm`；
- dispatched action support violation：legacy `7.38%`，latest `7.65%`，增加 `0.27` 个百分点，
  仍在“不高于 1 个百分点”的门内；两臂均无非有限值或 clipping。

因此正式分类为 `temporal_dispatch_not_primary`。只保留最新 chunk 没有改善方向、排序或宏观短期分离，
legacy temporal aggregation 不是当前 Dig 空间目标跟随失败的主要阻塞。下一实验固定为
`goal_conditioned_act_vs_diffusion_policy`，不申请 Unity 单铲因果测试。

本轮没有训练或修改 ACT，没有创建 optimizer、调用 backward、启动 Unity 或发送动作。默认 dispatch、
checkpoint、planner、协议和生产配置均未改变。权威 no-overwrite 工件为
`runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/`。其中的 5/10 步结果仅为
`short_horizon_projection_only`，不能解释为真实轨迹、土体效果或“指哪挖哪”。

## 2026-08-23 goal/action 数据可辨识性硬门

在创建 ACT-vs-Diffusion Policy 训练任务前，执行了默认关闭的
`dig_goal_action_identifiability_precheck_v1`。检查单位固定为 strict-train primitive 的 t0；每行必须有完整
100-step action supervision、通过正式 18D p01-p99，并锁定 qpos/qvel、四相机、controller epoch/profile、
calibration schema 和自然 Dig token。目标 token 不参与状态匹配。source 33/34 未使用。

241 个 episode、15 个 source 通过行级前置条件。28,920 个无序 episode 组合中，2,021 个具有相同 source 和
controller metadata，但没有一对同时满足 qpos 最大差不超过 `0.005`、qvel 最大差不超过 `0.02`。因此机械
状态门后的 pair 数为 0，四相机门、同目标动作噪声和不同目标动作信号都没有正式可评估样本。

112 个冻结目标中，109 个有可用 reference episode，另外 3 个因更严格的 t0/完整 action supervision 合同而
缺少 reference。109 个 reference 只有自身通过状态匹配；其自然训练 token 对 planner base/alternate 目标的
匹配数均为 0。最终 base demo、alternate demo 和成对动作监督覆盖都是 `0/112`，八个 0.1/0.2 m 平移 bin
也全部为 0。

正式分类为 `data_supervision_unidentifiable`。ACT-vs-DP 训练没有启动；下一步固定为
`paired_goal_action_demonstrations`。应在同一可恢复初态和相机/terrain 条件下，对至少两个不同 Dig 目标分别
采集示教动作，使目标变化对应可辨识的前 10 步和完整 chunk 动作变化。通过相同数据门前，不继续更换模型。

本轮没有加载或训练 ACT/DP，没有创建 optimizer、调用 backward、训练土体模型、启动 Unity 或发送动作；
temporal 参数和生产默认未改变。权威 no-overwrite 工件为
`runs/eval/dig_goal_action_identifiability_precheck_20260823T205439+0800/`。

## 2026-08-24 最小 Diffusion Policy 离线探针

在数据可辨识性门失败的前提下，额外执行了不可晋级的 `minimal_dig_diffusion_probe_v1`。该探针不修改
production `DiffusionAdapter` skeleton，而使用独立 eval 模块中的 100,148 参数条件 temporal-conv
epsilon predictor。训练输入复用 38,853 个正式 strict-train 100-step 窗口、四相机灰度 32×32、18D
`qpos+qvel+dig_cut_tokens`、原 action/proprio stats 和 source→episode 均衡采样。source 33/34 完全排除。

训练固定 seeds `[0,1,2]`，每 seed `1000 updates × batch 128`，没有 early-stop 或 model selection；DDPM
训练使用 50 个 timestep，评估使用 10-step deterministic DDIM。inference noise seeds 固定为
`[100,101,102]`，相同 initial noise 同时用于 base-correct、alternate-correct、zero 和 shuffled 条件。
每个 112×100 observation frame 都重新采样 chunk，只派发 query 0，contributor age 恒为 0，没有 temporal
aggregation。独立重训 seed 0 的完整 loss history 和 EMA state 逐张量一致。

正确 base/alternate token 的 first-action goal effect p10/p50 只有
`0.000560/0.001462`，raw goal response 为 `0%`；diffusion noise effect p50/p95 为
`0.759460/1.428145`，远大于 goal effect。shuffled-token effect p50 为 `0.006608`，也高于正确目标变化；
zero token effect p50 为 `0.297630`，但 zero 是有意 out-of-support control，其 dispatched action support
violation 为 `25.71%`，不能作为有效目标跟随证据。

9 个 training/noise replica 的 10-step direction/ranking 为 `30.08%/50.01%`；projected separation p10
仅 `0.0000274 m`，远低于 `0.02 m`。训练 seed 的目标动作变化方向一致率只有 `6.65%`。正确 alternate
条件的 dispatched action support violation 为 `6.69%`，没有比 ACT latest 参照 `7.65%` 恶化，且无
非有限值；但其余绝对门全部失败。

正式分类为 `minimal_dp_probe_noise_dominates`。该结果与此前数据门一致：在缺少同状态、多目标动作监督时，
换成最小 DP 没有恢复目标跟随。下一步仍是 `paired_goal_action_demonstrations`，不申请 Unity，不增加模型、
denoising steps 或训练预算。

ACT 没有训练或修改，土体模型、Unity、动作发送、temporal 参数和生产默认均未改变。权威 no-overwrite
工件为 `runs/eval/dig_minimal_diffusion_probe_20260824T150222+0800/`，永久
`promotion_eligible=false`。
