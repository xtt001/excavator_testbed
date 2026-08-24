# Dig 短轨迹条件 ACT 下一阶段开发计划

## 1. 阶段结论

当前系统已经能够表达连续 Dig 目标，ACT 也会对目标变化产生 raw action response，但尚未建立
“当前观测 + 空间目标 → 正确局部动作”的可靠映射。最近三条离线证据把问题进一步收窄：

- temporal aggregation 不是主要阻塞。每帧读取最新 recorded observation、只派发最新 chunk 首动作后，
  10-step direction/ranking 仍只有 `24.34%/50.26%`，projected separation p10 只有 `0.485 mm`。
- 现有自然数据不能为 10D planner goal 提供严格的反事实动作监督。241 个合格 t0 episode 中，2,021 个
  同 source/controller metadata 组合在 qpos `≤0.005`、qvel `≤0.02` 后变成 0；112 个 planner
  base/alternate 目标的自然示范覆盖为 `0/112`。
- 直接换成最小 Diffusion Policy 没有恢复目标响应。goal effect p10 只有 `0.000560`，diffusion noise p95
  为 `1.428145`；direction/ranking 为 `30.08%/50.01%`，10-step separation p10 为 `0.0274 mm`。

这些结果否定了“继续调 temporal 参数”“只换生成架构”以及“恢复 100-step learned dynamics”三条路线。
它们没有否定 ACT 作为短时域、数据驱动局部执行器的可能性。

下一阶段只回答一个问题：

> 使用现有自然数据自动生成的 5/10-step achieved tip trajectory 作为条件，ACT 能否学习局部逆动力学，
> 并在严格 action support 内通过方向、排序和厘米级空间分离门？

如果答案仍是否定，应停止 ACT 作为精准 Dig executor 的路线。后续只能引入真实目标干预数据，或改变底层
执行器分工；不能继续扩大模型和训练预算。

## 2. 当前痛点

### 2.1 高层目标离即时动作太远

当前 10D Dig token 描述 entry、exit、方向、深度、payload 和 valid，但一个固定 token 在 approach、
penetration、cutting、curl 和 exit 阶段对应完全不同的动作。ACT 需要同时从图像中推断当前阶段、局部误差和
后续动作顺序，BC loss 并未直接约束空间执行。

### 2.2 100-step chunk 混合多个接触阶段

运行时移除旧 chunk 没有解决问题，但 query-0 仍由 100-step 训练目标产生。远期动作、阶段切换和专家习惯可能
稀释眼前的空间纠偏信号。这个训练语义尚未被单独验证。

### 2.3 自然数据缺少 planner goal 的动作标签

严格数据门已经确认，同状态不同 planner goal 的专家动作不可辨识。继续用 10D token 做普通 BC，loss 下降
也不能证明模型使用目标。专门采集完全复位的 paired demonstration 又不符合当前自然作业数据原则。

### 2.4 当前 loss 只要求动作拟合

现有训练不会直接惩罚以下错误：

- 铲尖朝错误方向移动；
- 自己目标比另一个目标更远；
- 两个目标的空间结果只有毫米级分离；
- 不同观测时刻生成的重叠 chunk 相互冲突；
- 策略通过离开专家 action support 改善 surrogate 指标。

### 2.5 短期模型可用范围有限

固定齿尖 FK 已通过高精度交叉验证。真实状态每 10 步重锚时，当前短期 dynamics 的 worst-source endpoint
误差约 `1.08 cm`，说明 5/10-step state-action 关系可以用于有界训练和评估。但该证据只覆盖自然
state/action support，不能递归到 100 步，也不能预测土体效果。

## 3. 下一阶段目的

本阶段不追求完整单铲或土体效果。目的分为四层：

1. 把 ACT 的条件从高层整铲语义改为与即时动作直接相关的 5/10-step local tip trajectory。
2. 验证自然数据能否支持“当前观测 + 已实现局部轨迹 → 专家动作”的局部逆动力学学习。
3. 在没有 alternate 专家动作的情况下，只在冻结短期 dynamics/FK、严格 trust region 和 action support 内
   引入反事实空间目标信号。
4. 用一次固定预算 A/B/C 对照决定 ACT 精准 Dig 路线是否继续。

项目叙事保持为数据驱动执行器：Planner 生成局部铲尖路径，ACT 产生动作，实际执行结果自动生成新的 achieved
trajectory 和土体效果标签。几何只负责目标表达、监督和验收，不在运行时替 ACT 计算动作。

## 4. 冻结边界

### 4.1 本阶段允许

- 使用 strict-train/source-grouped 现有自然 Dig 数据；
- 从未来真实 qpos 和固定 FK 派生 5/10-step achieved tip trajectory；
- 新训练实验 checkpoint，但只能保存在 no-overwrite 运行目录；
- 新建 trajectory-conditioned ACT 小分支和辅助 head；
- 使用冻结的 5/10-step dynamics/FK 计算有界训练 loss；
- 每帧 latest-observation 推理，只派发 query 0；
- 纯离线 source/episode bootstrap 和 action support 评估。

### 4.2 本阶段禁止

- source 33/34 参与结构、阈值、超参数、early-stop 或选择；
- 新采集数据、人工构造 paired demonstration 或修改自然数据标签；
- 失败的 100-step dynamics、soil predictor 或递归长程 rollout；
- 修改 temporal decay、window、weight order 或其他 primitive 默认 dispatch；
- 启动 Unity、调用 backend 或发送真实动作；
- 写入 production checkpoint/config；
- 把短期 FK/dynamics projection 描述成真实轨迹或土体效果；
- 同时修改模型结构、条件合同、loss 和训练预算而不做独立消融。

## 5. 新的条件合同

### 5.1 训练条件

每个自然窗口从 pre-action observation 开始，固定顺序为：

```text
images[formal camera order]
qpos[4]
qvel[4]
desired_tip_path[K,3]
path_mask[K]
phase/progress auxiliary targets
```

其中 `K∈{5,10}`。`desired_tip_path` 使用 DigArea 坐标下相对当前固定齿尖的局部位移。训练时来自实际未来 qpos
经固定 FK 得到的 achieved path；运行时同一字段由 Planner 根据 entry/depth/exit 切出的局部路径生成。

训练 condition 可以使用 hindsight achieved path，但运行时不得输入专家未来 qpos、未来 observation 或
hindsight outcome。manifest 必须分别记录：

```text
train_condition_source=achieved_tip_path_hindsight
runtime_condition_source=planner_desired_tip_path
```

### 5.2 策略输出

ACT 只预测 `K×4` action chunk。正式 runtime 语义固定为：

```text
当前真实 observation
→ 生成新 chunk
→ 只派发 action[0]
→ 读取下一帧真实 observation
→ 重新预测
```

不保留或聚合旧 chunk。goal/path SHA 或 request 改变时清空 request-local cache。该语义默认关闭，不能替换
现有 ACTAdapter.predict() 的生产默认。

## 6. 分阶段实施

## Phase 0：短轨迹标签与支持审计

### 目标

在训练前确认自然 achieved path 与 Planner 所需局部路径存在可用重叠。

### 实现

- 对 strict-train 每个完整窗口生成 K=5/10 的 fixed-tip path；
- 锁定 HDF5、split、qpos、qvel、camera、FK artifact 和 path-row SHA；
- 按 source、episode、phase、路径方向、幅度、qpos 边界和 metadata 分层；
- 计算 112 个 planner goal 转换出的 local path 到自然 path support 的距离；
- 不随机拆重叠窗口，source 先分组，episode 作为 bootstrap cluster。

### 停止门

以下任一失败时不训练 A/B/C：

- lineage、camera order、FK 或 split 不完整；
- 任一 train/validation source 重叠；
- 少于 100 个冻结目标具有完整 K=5/10 planner-path condition；
- planner local path 在至少 80% 的目标上离开自然 path p01-p99/support envelope；
- 关键 ±x/±z、penetration、cutting 和 exit path bin 缺少 source/episode 覆盖。

## Phase A：Trajectory-conditioned ACT + BC

### 目标

验证 ACT 能否在 held-out strict-train source 上恢复自然 achieved path 对应的专家动作。

### 冻结设置

- K=5 和 K=10 分开训练，不根据结果改变 horizon；
- 使用相同 camera encoder、normalization、source folds、seed 和更新预算；
- 不加入任何 counterfactual dynamics/FK loss；
- 保留现有 BC/KL 定义，输出维度改为 K×4；
- 三个独立训练 seed。

### 验收

- held-out BC/action 指标不比同 horizon、无 path condition baseline 恶化超过 2%；
- matched path 的 action likelihood 显著优于 zero/shuffled path；
- 三 seed 在自然 path 上的 query-0 action 和 5/10-step projected tip 指标稳定；
- action p01-p99、非有限值和 qpos boundary 不恶化；
- Planner path 与自然 path 的支持距离逐样本保留。

### 停止门

如果 A 无法在自然 achieved path 上恢复专家动作，停止 ACT 局部逆动力学路线；不进入 B/C。

## Phase B：最小辅助监督

### 目标

解决 path condition 被忽略、phase 混淆和稀有局部运动梯度不足。

### 只允许加入

1. 未来 5/10-step tip path auxiliary head；
2. approach/penetration/cutting/curl/exit phase auxiliary head；
3. path progress、remaining delta 或 next-waypoint distance；
4. source/episode/phase/path-bin 平衡采样；
5. matched/zero/shuffled path condition-use audit。

重叠 chunk consistency 只作为后续独立消融，不能与上述内容同时加入。latest dispatch 已说明 temporal conflict
不是当前第一原因。

### 验收

- matched condition 在三个 seed 上都显著优于 zero/shuffled；
- phase/progress 指标在 held-out source 上稳定；
- BC 恶化仍不超过 2%；
- 稀有 path bin 不通过重复采样掩盖真实 source 覆盖不足。

## Phase C：保守的短期物理优化

### 目标

在没有 alternate 专家动作的情况下，通过 goal-independent short dynamics + FK 提供有界反事实空间信号。

### 训练链

```text
ACT(obs, local_path_A/B)
→ predicted actions[K,4]
→ frozen source-grouped short dynamics
→ predicted qpos[K,4]
→ fixed-tip FK
→ direction / ranking / separation
```

### Loss

```text
L = L_BC
  + λ_goal (L_direction + L_ranking + L_separation)
  + λ_support L_action_support
  + λ_uncertainty L_ensemble_disagreement
```

- `λ_goal` 通过梯度匹配确定，不从 112 目标结果反调；
- 物理 loss 梯度上限为 BC 梯度的 30%；
- held-out BC 恶化上限 2%；
- action support violation 相对 A 不得增加超过 1 个百分点；
- dynamics 和 FK 全部 `eval()`、`requires_grad=false`，不创建它们的 optimizer；
- disagreement 高或动作离开支持时，当前样本物理梯度归零并记录原因；
- 训练 dynamics member 与最终 OOF evaluator 必须 source-disjoint。

## Phase D：固定 112 目标离线验收

### 主指标

- own-goal direction success；
- own-goal ranking accuracy；
- 5/10-step projected tip separation；
- query-0 与完整 K-step action separation；
- BC/action likelihood；
- action p01-p99、非有限值和 boundary violation；
- source/episode/seed paired bootstrap；
- independent evaluator disagreement。

### 正式门

- direction 和 ranking 均 `≥80%`；
- C 相对 A 至少提高 15 个百分点；
- separation p10 `≥0.02 m`；
- paired bootstrap 95% 下界确认 C 优于 A；
- BC 恶化 `≤2%`；
- action support violation 增幅 `≤1` 个百分点；
- 三训练 seed 的方向一致率通过预注册门；
- 独立 OOF evaluator 上结论一致；
- lineage、支持或短期 dynamics gate 缺失时结果无效。

### 唯一决策

1. 合同、lineage、path support 或 OOF evaluator 失败：`invalid_short_trajectory_act_experiment`；
2. Phase A 失败：`trajectory_conditioned_inverse_policy_not_learned`；
3. A/B 通过但 C 未改善方向、排序或分离：`act_precise_dig_route_not_supported`；
4. C 改善但依赖越界动作或高模型不确定性：`short_dynamics_model_exploitation_blocked`；
5. C 全部门通过：`short_trajectory_act_offline_promising`，下一步才允许申请
   `minimal_unity_tip_path_tracking_test`。

任何失败都不得通过调低 80%、15pp、2 cm、2% 或 1pp 门继续。

## 7. 建议代码边界

新功能进入职责明确的小模块，CLI 只做解析和编排：

```text
testbed/data/dig_short_trajectory_conditioning.py
    HDF5 对齐、achieved path 标签、path support 和 lineage

testbed/policies/act/trajectory_conditioning.py
    path encoder、输入合同和 checkpoint-compatible facade

testbed/policies/act/short_horizon_objectives.py
    tip/phase/progress 与冻结 dynamics/FK loss

testbed/eval/dig_short_trajectory_contract.py
    A/B/C 冻结合同、阈值和决策

testbed/eval/dig_short_trajectory_runtime.py
    source folds、训练臂编排、no-overwrite 工件

testbed/eval/dig_short_trajectory_reporting.py
    指标聚合、图表和中文报告

testbed/cli/dig_short_trajectory_act.py
    薄 CLI
```

不得向超过 1,000 行的 Python 文件添加算法逻辑。现有 `ACTAdapter` 只允许加入薄 facade、参数传递和公开
inspection API；条件编码、loss 和数据算法必须放在新模块。

## 8. TDD 与验证要求

### 单元测试

- 5/10-step achieved tip path 与固定 FK 一致；
- pre-action observation/action/path 对齐无 off-by-one；
- train/runtime path 字段顺序和坐标系一致；
- runtime condition 不含专家未来 qpos；
- matched/zero/shuffled condition audit 正确；
- path-bin/source/episode 分组不泄漏；
- latest query-0 dispatch 每帧只使用新 chunk；
- dynamics/FK 参数冻结且不创建 optimizer；
- support、uncertainty、非有限值和 hard mask 正确；
- gradient cap 与 BC degradation gate 正确；
- source/episode/seed bootstrap 正确；
- no-overwrite 和 dry-run 不加载 backend/Unity。

### 集成验证

- Phase 0 数据和 lineage smoke；
- K=5/K=10 单 batch overfit；
- 三臂相同 batch/sample schedule；
- checkpoint reload 与 action byte/behavior smoke；
- independent OOF dynamics evaluation；
- 112 目标完整离线运行；
- Ruff、compileall、focused pytest、public import smoke 和 `git diff --check`。

## 9. 固定产物

每次正式运行写入不存在的新目录，至少包含：

```text
contract.json
input_manifest.json
path_support.json
sample_schedule/
A/
B/
C/
pair_metrics.json
bootstrap.json
decision.json
report.md
必要图表
```

全部绑定 Python HEAD/dirty 状态、代码 SHA、HDF5/split/stats/FK/dynamics/checkpoint SHA、camera/path/action order、
source folds、seed、训练预算和 evidence boundary。失败运行保留，不覆盖或重标。

## 10. 新分支启动建议

本阶段归档提交完成后，从该提交创建新分支：

```bash
git switch -c codex/dig-short-trajectory-act
```

新会话第一轮只执行 Phase 0，不创建 ACT optimizer。Phase 0 通过后再分别实现 A、B、C。不要在同一个提交中
混合 path contract、模型结构、辅助 loss 和短期物理 loss。

新会话开始时应重新记录：

```text
cwd
branch
HEAD
git status --short
最终 receding dispatch artifact
最终 identifiability artifact
最终 minimal DP probe artifact
```

当前权威输入分别为：

- `runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/`；
- `runs/eval/dig_goal_action_identifiability_precheck_20260823T205439+0800/`；
- `runs/eval/dig_minimal_diffusion_probe_20260824T150222+0800/`。

## 11. 阶段完成定义

下一阶段只有两种完整结果：

1. C 通过全部离线门，形成一次最小 Unity tip-path tracking 申请；
2. 任一正式停止门触发，形成 `act_precise_dig_route_not_supported` 或更早的 fail-closed 决策，并结束 ACT
   作为精准 Dig executor 的路线。

“完成代码”“训练 loss 下降”“raw action 随 path 改变”或“短期 projection 有局部改善”都不能单独视为阶段成功。
