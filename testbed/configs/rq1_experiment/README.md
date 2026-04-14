# RQ1 Control Experiment — Latency vs Data Quality

## 实验目的

量化证明：不同时延（step-ack RTT）配置下，遥操作采集的示教数据质量不同，
最终导致 ACT 模仿学习成功率的系统性差异。

这是整个论文动机的实验基础。

## 前提：Realtime Mode

Unity 侧必须开启 **Realtime Mode**（`AgxSimStepAckServer` Inspector 勾选）。

开启后物理在 `FixedUpdate`（50Hz）里独立推进，不被 Python 通信延迟拖慢。
未收到新命令时保持上一个 action（zero-order hold）。
这样注入网络延迟才能正确模拟真实远程操控的效果：
- 命令延迟：操作员推杆后，挖掘机延后反应
- 视觉延迟：操作员看到的 Python 窗口画面是 RTT 前的状态

操作员 **必须看 Python 窗口**（`display.enabled: true`），不看 AGX 窗口。
AGX 窗口是本地渲染，零延迟，不能反映真实延迟体验。

## 实验矩阵

| 条件 | 分辨率 | 注入时延 | 预期 RTT | 配置文件 | 数据目录 |
|---|---|---|---|---|---|
| baseline | 720×480 | 0ms | ~23ms | `teleop_c_fullres.yaml` | `data/rq1/c_fullres` |
| 25ms | 720×480 | 25ms | ~73ms | `teleop_c25ms_delay.yaml` | `data/rq1/c_25ms` |
| 50ms | 720×480 | 50ms | ~123ms | `teleop_c50ms_delay.yaml` | `data/rq1/c1_50ms` |

分辨率对照（独立于延迟实验）：

| 条件 | 分辨率 | 注入时延 | 配置文件 | 数据目录 |
|---|---|---|---|---|
| fullres | 720×480 | 0ms | `teleop_c_fullres.yaml` | `data/rq1/c_fullres` |
| lowres | 240×160 | 0ms | `teleop_c_lowres.yaml` | `data/rq1/c_lowres` |

## 实验流程

每个延迟条件：

1. 确认 Unity **Realtime Mode** 已开启
2. `sudo scripts/inject_delay.sh <delay_ms>` — 注入延迟
3. `scripts/verify_latency.sh <delay_ms>` — 确认 RTT 符合预期
4. `tb-record-teleop --config testbed/configs/rq1_experiment/teleop_cXXX.yaml` — 录制（看 Python 窗口）
5. `sudo scripts/inject_delay.sh 0` — 录完清掉延迟
6. `tc qdisc show dev lo` — 确认已清除

分析：

```bash
python -m testbed.latency_module.analysis.rq1_data_quality \
    --datasets "data/rq1/c_fullres:0ms(baseline)" \
               "data/rq1/c_25ms:25ms" \
               "data/rq1/c1_50ms:50ms" \
    --out outputs/rq1/latency_proof
```

分辨率对照在跑完 `tb-train` / `tb-eval` 之后，建议继续补一轮行为级分析：

```bash
python scripts/resolution_behavioral_analysis.py
```

这会在 `outputs/rq1/resolution_proof/` 下额外生成：
- `resolution_policy_behavior.png`：fullres vs lowres rollout 的阶段性行为差异
- `resolution_evidence_summary.png`：teleop 质量、BC loss、policy success、subtask ladder 的整合证据图
- `summary_table.md`：适合 thesis proposal / paper motivation 的文字摘要

## 评测指标

### 数据质量指标（录制时测量）
- `mean_step_interval_ms`：平均步长（越接近 20ms 越好）
- `step_interval_p95_ms`：步长 p95（衡量抖动）
- `action_jerk`：动作加加速度（衡量操作平滑度）
- `reversal_rate`：方向反转率（衡量过度补偿）

### 模型效果指标（评测时测量）
- `success_rate`：dump_complete_final_hold 成功率（主指标）
- `mean_episode_steps`：平均完成步数（越少越好）
- `mean_retained_mass_kg`：平均保留质量

## 预期假设

- H1：25ms 条件的 reversal_rate 开始高于 baseline
- H2：50ms 条件的 action_jerk 和 reversal_rate 显著高于 baseline
- H3：高延迟条件下 ACT 训练后 success_rate 低于 baseline（需下游实验验证）
