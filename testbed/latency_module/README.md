
# Latency Instrumentation & Analysis Module

> **状态**：Phase 3 进行中（RQ1 采集工具链就绪，等待 AGX 修复后采集数据）
> **定位**：可插拔的观测层（Observability Layer），不替换现有 testbed 任何功能

---

## 快速命令单（Unity 恢复后直接使用）

> **前置**：Unity 已启动，Inspector → `AgxSimStepAckServer` → `m_useFixedUpdateForRequests = false`

### 分辨率实验（优先，不需要 sudo）

```bash
# === 条件 A：全分辨率 720x480 ===
# 1. 重启 Unity（每个条件前必须重启以清除 terrain 积累）
# 2. 运行（Python 会弹出 "Operator View" 窗口，请只看这个窗口，不看 Unity）
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c_fullres.yaml
# 数据保存至: data/rq1/c_fullres/

# === 条件 B：低分辨率 240x160 ===
# 1. 重启 Unity
# 2. 运行（窗口会显示像素化图像）
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c_lowres.yaml
# 数据保存至: data/rq1/c_lowres/

# === 两个条件都采集完后，运行分析 ===
python -m testbed.latency_module.analysis.rq1_data_quality \
    --datasets "data/rq1/c_fullres:720x480(full)" \
               "data/rq1/c_lowres:240x160(low)" \
    --out outputs/rq1/resolution_proof
# 输出: outputs/rq1/resolution_proof/proof_summary.png（论文用图）

# === 如果 fullres / lowres 两组 ACT 训练和评测也已完成，再补一轮行为级证明 ===
python scripts/resolution_behavioral_analysis.py
# 额外输出:
# - outputs/rq1/resolution_proof/resolution_policy_behavior.png
# - outputs/rq1/resolution_proof/resolution_evidence_summary.png
# - outputs/rq1/resolution_proof/summary_table.md
```

### 延迟实验（需要 sudo 权限）

```bash
# === 条件 0：无注入延迟（baseline） ===
# 1. 重启 Unity
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c0_baseline.yaml
# 数据保存至: data/rq1/c0_baseline/

# === 条件 1：注入 50ms（RTT ~123ms） ===
# 1. 重启 Unity
sudo bash scripts/inject_delay.sh 50    # 注入延迟
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c50ms_delay.yaml
sudo bash scripts/inject_delay.sh 0     # 采集完后清除

# === 条件 2：注入 100ms（RTT ~223ms） ===
# 1. 重启 Unity
sudo bash scripts/inject_delay.sh 100
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c100ms_delay.yaml
sudo bash scripts/inject_delay.sh 0

# === 三个条件都采集完后，运行分析 ===
python -m testbed.latency_module.analysis.rq1_data_quality \
    --datasets "data/rq1/c0_baseline:0ms(23ms RTT)" \
               "data/rq1/c1_50ms:50ms(123ms RTT)" \
               "data/rq1/c2_100ms:100ms(223ms RTT)" \
    --out outputs/rq1/latency_proof
# 输出: outputs/rq1/latency_proof/proof_summary.png（论文用图）
```

### 验证延迟注入是否生效

```bash
# 注入后用此命令验证（RTT 应接近 2×注入值 + 基线）
bash scripts/verify_latency.sh 50    # 验证 50ms 注入
ping -c 5 127.0.0.1                  # 快速验证（ICMP，仅参考）
tc qdisc show dev lo                 # 查看当前规则
```

---

## 背景

本模块是论文研究基础设施的第一层：**时延测量与分析**。

在动手做 RQ1（Pareto 前沿）、RQ2（ROI 编码）、RQ3（AR 预测补偿）的实验之前，需要一套可靠的时延打点机制，能够：

- 记录遥操作 step-ack 链路的端到端往返时延；
- **精确分解 RTT 为 6 段**（Python→Unity 网络 / 队列等待 / DoStep 物理 / 图像采集 / 序列化 / Unity→Python 网络）；
- 以统一的 JSONL trace 存储实验数据；
- 离线自动计算统计指标（mean/p95/p99 等）并绘图；
- 支持多配置（分辨率、码率、注入时延）对比实验。

---

## RTT 分段模型

一次 `step()` 调用的完整 RTT 被分解为 6 段，时间戳在 Unity 端和 Python 端双侧采集：

```
Python                         Unity (C#)
──────                         ──────────
t_cmd_send ─── STEP_REQ ────→ t_req_recv_ns      ┐ seg_py_to_unity
                               t_queue_exit_ns    ┐ seg_queue_wait  (等待 Update/FixedUpdate tick)
                               [DoStep()]
                               t_physics_done_ns  ┐ seg_physics     (AGX 物理步进)
                               [Collect()]
                               t_image_ready_ns   ┐ seg_image       (图像采集)
                               [Serialize]
                               t_resp_queued_ns   ┐ seg_serialize   (序列化响应)
t_cmd_recv ←── STEP_RESP ──── (send)              ┐ seg_unity_to_py (网络传输)
```

Unity 端 5 个时间戳通过 `AgxSimResponsePayload` 的扩展字段传回 Python。

### 典型数值（干净 Unity 会话，720×480 raw RGB，loopback）

| 段 | Update 模式 | FixedUpdate 模式 |
|---|---|---|
| py→unity (网络) | 5.0ms | 5.1ms |
| queue wait (tick 等待) | **3.2ms** | **12.2ms** |
| DoStep (物理) | 4.8ms | 4.9ms |
| Image Collect | 0.6ms | 0.6ms |
| Serialize | 3.0ms | 2.3ms |
| unity→py (网络) | 6.2ms | 8.6ms |
| **总 RTT** | **22.8ms** | **33.7ms** |

FixedUpdate 模式的 `queue_wait` 由 20ms physics tick 周期约束，是导致 +10.9ms overhead 和双峰抖动的根本原因。

---


## 目录结构

```
testbed/latency_module/
├── __init__.py                  ← 顶层入口：LatencySession, export_run_summary
├── session.py                   ← LatencySession（高层 context manager）
├── instrumentation/
│   ├── event_schema.py          ← 事件名常量 + LogEntry dataclass（含 6 段时延字段）
│   ├── id_manager.py            ← run_id / episode_id / cmd_id 管理
│   └── trace_logger.py          ← 线程安全的 JSONL 写入器
├── probes/
│   └── control_probe.py         ← 包裹 AgxSimClient.step()，计算 6 段时延
├── analysis/
│   ├── parse_trace.py           ← 加载 trace.jsonl → DataFrame
│   ├── compute_metrics.py       ← 计算 mean / p95 / p99 等统计量
│   ├── plot_latency.py          ← 自动生成 PNG 图表
│   ├── export_summary.py        ← 一键导出 summary.json + plots/
│   ├── hdf5_bridge.py           ← 从 HDF5 文件提取时间戳（仅 step 级 RTT）
│   └── rq1_data_quality.py      ← 多条件数据质量对比分析
└── configs/
    └── latency_default.yaml     ← 默认配置模板
```

输出目录结构：

```
outputs/
  run_xxx/
    trace.jsonl          ← 每步打点日志（含 6 段时延）
    summary.json         ← 统计摘要
    plots/
      e2e_distribution.png
      latency_timeseries.png
      payload_bytes.png
      segment_breakdown.png
      comparison_delay_inject_ms.png
  ab_test/
    ab_comparison.png    ← Update vs FixedUpdate 对比三联图
  step_ack_mode_record/
    comparison/          ← 遥操作模式对比分析
```

---

## Update / FixedUpdate A/B 测试

专门比较 `AgxSimStepAckServer.ProcessPendingRequests()` 放在
`Update()` 还是 `FixedUpdate()` 时的 RTT 分段时延和抖动分布。

```bash
# 干净 Unity → 2 轮交叉对比，每轮 200 步
python scripts/latency_ab_test.py --steps 200 --rounds 2 --out outputs/ab_test
```

**重要**：测试前必须重启 Unity 以消除 terrain 积累影响。

前提：

- Unity 已运行目标场景（刚重启的干净状态）；
- `AgxSimStepAckServer` Inspector 中可见
  `m_useFixedUpdateForRequests`；
- 从 `false`（`Update`）开始，脚本中途会提示切换。

输出：

- 终端 side-by-side RTT / 6 段时延对比；
- `outputs/ab_test/ab_comparison.png`（三联图：RTT 分布 + 时序 + 分段堆叠柱状图）。

### 关键发现

| 指标 | Update | FixedUpdate | 差异 |
|---|---|---|---|
| 总 RTT | 22.8ms | 33.7ms | **+10.9ms** |
| queue_wait | 3.2ms | 12.2ms | +9.0ms（占差异的 83%）|
| DoStep | 4.8ms | 4.9ms | 无差异 |
| 分布形态 | 单峰平滑 | **双峰**（20ms/40ms）| FixedUpdate 受 tick 相位约束 |

结论：`Update` 模式在 step-ack 同步场景下优于 `FixedUpdate`，差异完全来自 queue wait 段，物理仿真本身不受影响。

---

## 重启版 Teleop 对比

如果你的目标不是纯脚本 micro-benchmark，而是：

- 自己手动 teleop 去感受 jitter；
- 并且分别保存 `Update` / `FixedUpdate` 两组正式录制数据和 latency trace；

可以运行：

```bash
python scripts/record_step_ack_modes_restart.py \
  --config testbed/configs/teleop_v0.yaml \
  --num-episodes 1
```

这个脚本会：

- 基于一份 base teleop 配置，自动生成两份临时配置；
- 先跑一次 `Update` 版 `tb-record-teleop`；
- 提示你完整重启 Unity/AGX，并把
  `m_useFixedUpdateForRequests` 切到 `true`；
- 再跑一次 `FixedUpdate` 版 `tb-record-teleop`。

默认输出：

- latency trace:
  - `outputs/step_ack_mode_record/teleop_update_restart/`
  - `outputs/step_ack_mode_record/teleop_fixedupdate_restart/`
- datasets:
  - `data/step_ack_mode_record/update/`
  - `data/step_ack_mode_record/fixedupdate/`

这样更适合“主观体感 + 正式录制”的对比实验，因为两种模式之间明确做了完整重启。

补充说明：

- `tb-record-teleop` 的 live trace 录制本身不依赖 `pandas`；
- `pandas` 只在离线分析、导出 `summary.json` 和绘图时需要；
- 现在 `testbed.latency_module` 已改为惰性导入，所以即使当前环境没装
  `pandas`，也可以先正常录制 `trace.jsonl`。

---

## 快速接入

### 方式一：在 teleop 配置文件中开启

在你的 `teleop_vX.yaml` 中添加：

```yaml
latency:
  enabled: true
  output_dir: "outputs"          # 相对于运行目录
  network:
    delay_inject_ms: 0.0         # 填写 tc netem 注入的实际时延（仅元数据）
    jitter_inject_ms: 0.0
    loss_rate: 0.0
  stream:
    resolution: "1280x720"
    fps: 30.0
    bitrate: 0
    codec: "raw_rgb"
  analysis:
    auto_export_on_close: true   # session 结束后自动生成 summary + plots
```

然后正常运行 `tb-record-teleop`，**无需其他改动**：

```bash
tb-record-teleop --config testbed/configs/teleop_v0.yaml
```

### 方式二：编程接入

```python
from testbed.latency_module import LatencySession

session = LatencySession.from_config(cfg)
session.open()
session.start_run()

# 挂载探针（只改 backend._client.step，不动 backend 本身）
session.attach_probe(backend._client)

for ep_idx in range(num_episodes):
    session.start_episode(ep_idx)
    ts = backend.reset(seed=seed)

    for step in range(max_steps):
        action, ainfo = action_source.next_action(ts.observation)
        session.log_cmd_input()          # 可选：记录操作员输入时刻
        ts = backend.step(action)        # ← 探针自动打点 cmd_send/cmd_recv/cmd_apply

    session.end_episode(success=episode_success)

session.close()   # 自动导出 summary + plots（若 auto_export_on_close=true）
```

---

## 已记录的事件

| 事件名 | 含义 | 时间基准 |
|---|---|---|
| `session_start` | 实验 session 开始 | 壁钟 ns |
| `episode_start` | 单次 episode 开始 | 壁钟 ns |
| `cmd_input` | 操作员输入动作时刻 | 壁钟 ns |
| `cmd_send` | STEP_REQ 进入 socket | 壁钟 ns |
| `cmd_recv` | STEP_RESP 完整接收 | 壁钟 ns |
| `cmd_apply` | Unity sim 时钟（STEP_RESP 中的 sim_time_ns） | Unity 仿真时钟 |
| `frame_recv` | 图像数据到达（与 cmd_recv 同时刻） | 壁钟 ns |
| `state_feedback_ready` | obs dict 可用，Policy 可读取 | 壁钟 ns |
| `episode_end` | 单次 episode 结束 | 壁钟 ns |
| `session_end` | 实验 session 结束 | 壁钟 ns |

每条 `cmd_recv` JSONL 记录的字段：

```json
{
  "timestamp_ns": 1700000000000000000,
  "event_name": "cmd_recv",
  "run_id": "teleop_update_restart",
  "episode_id": "episode_0",
  "cmd_id": 42,
  "frame_id": 42,
  "round_trip_ms": 23.4,
  "payload_bytes": 2764800,
  "delay_inject_ms": 0.0,
  "resolution": "720x480",
  "codec": "raw_rgb",
  "sim_time_ns": 840000000,
  "seg_py_to_unity_ms": 3.3,
  "seg_queue_wait_ms": 4.2,
  "seg_physics_ms": 5.8,
  "seg_image_ms": 0.7,
  "seg_serialize_ms": 3.8,
  "seg_unity_to_py_ms": 7.3
}
```

6 段时延字段由 Unity 端 `AgxSimResponsePayload` 携带的 5 个纳秒时间戳计算得出。
值为 `-1` 表示该字段不可用（Unity build 不支持或该事件类型无此字段）。

---

## 离线分析

```bash
# 生成 summary.json + plots/（针对单次 run）
python -m testbed.latency_module.analysis.export_summary \
    --run-dir outputs/run_20240101_120000_abc123

# 或在 Python 中
from testbed.latency_module import export_run_summary
summary = export_run_summary("outputs/run_20240101_120000_abc123")
print(summary["control_round_trip_ms"])
# {'mean': 23.4, 'p95': 41.2, 'p99': 58.7, ...}
```

多配置对比（例如注入不同时延的实验）：

```python
from testbed.latency_module.analysis import load_all_runs, plot_all
from testbed.latency_module.analysis.parse_trace import pivot_step_latency

df = load_all_runs("outputs")
steps = pivot_step_latency(df)
plot_all(steps, out_dir="outputs/comparison", group_col="delay_inject_ms")
```

---

## tc netem 时延注入参考

```bash
# 注入 100ms 单向时延 + 20ms 抖动（在 Python 端和 Unity 端都运行时只需在 loopback 上注入）
sudo tc qdisc add dev lo root netem delay 100ms 20ms distribution normal

# 清除
sudo tc qdisc del dev lo root
```

注入后在配置文件中填写对应的 `delay_inject_ms: 100.0`，trace 中会自动记录这个元数据。

---

## Unity 端修改

为支持 6 段时延分解，Unity 侧做了以下修改（均在 `AGXUnity_Excavator` 仓库）：

### `AgxSimProtocol.cs`

- `AgxSimResponsePayload` 新增 5 个 `long` 字段：`t_req_recv_ns`, `t_queue_exit_ns`, `t_physics_done_ns`, `t_image_ready_ns`, `t_resp_queued_ns`
- 新增 `AgxSimTimestamp.NowNs()` 工具方法（UTC 纳秒）
- `WriteStepResponsePayload` 序列化这 5 个时间戳

### `AgxSimStepAckServer.cs`

- `PendingRequest` 新增 `ReceivedAtNs` 字段，在 TCP 接收线程记录到达时刻
- `CreateStepResponse` 在 4 个关键节点打时间戳
- 新增 `[SerializeField] bool m_useFixedUpdateForRequests` Inspector 开关，支持运行时切换 Update/FixedUpdate

### `protocol.py`（Python 端）

- `StepResponse` 新增对应的 5 个时间戳字段
- `decode_step_response` 可选读取扩展时间戳（向后兼容旧版 Unity build）

---

## 设计原则

- **零侵入**：只改 `backend._client.step`，不动 backend / protocol / recorder
- **可开关**：`latency.enabled: false` 时所有调用均为 no-op
- **可复用**：与 testbed 业务逻辑完全解耦，未来任何遥操作实验都能直接挂载
- **可扩展**：Phase 3 预留 ROI 编码指标、AR 虚影调度器接口

---

## Phase 路线图

| Phase | 内容 | 状态 |
|---|---|---|
| **Phase 1** | trace logger / control probe / 基础统计 / 基础绘图 | ✅ 完成 |
| **Phase 2** | Unity 端 5 时间戳 / 6 段分解 / AB 测试脚本 / 遥操作对比录制 | ✅ 完成 |
| **Phase 3** | RQ1 控制实验（tc netem 注入延迟 / 分辨率对比） / ACT 训练对比 | 进行中 |
| **Phase 4** | ROI 编码实验接入、AR 预测实验接入、回归检测 | 待开发 |

---

## RQ1 数据采集操作手册

### 环境前置条件

| 依赖 | 状态 | 说明 |
|---|---|---|
| `iproute2` (tc netem) | ✅ 系统已预装（v6.1.0） | 无需额外安装 |
| `sudo` 权限 | 需要 | 仅用于 `tc qdisc` 命令 |
| Unity AGXUnity_Excavator | 每轮必须重启 | 消除 terrain 积累 drift |
| `m_useFixedUpdateForRequests` | 必须为 `false` | Unity Inspector → AgxSimStepAckServer |

**每个采集条件之前必须重启 Unity**，以确保 terrain 干净（AGX `ResetHeightsAndRecreateNative` fix 已就位，但长期积累仍需重启）。

---

### 延迟实验采集（RQ1-Latency）

三个条件，loopback 双向注入，实际 RTT ≈ 自然基线 (~23ms) + 2×注入值：

```
条件           注入延迟    实际 RTT    类比真实场景
c0_baseline    0ms        ~23ms      本地/同机
c1_50ms        50ms       ~123ms     同城局域网
c2_100ms       100ms      ~223ms     跨城公网
```

**c0_baseline（0ms）：**
```bash
# 1. 重启 Unity，等场景完全加载
# 2. 确认 Unity Inspector: m_useFixedUpdateForRequests = false
# 3. 采集（10 个 episode）
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c0_baseline.yaml
```

**c1_50ms（50ms）：**
```bash
# 1. 重启 Unity
# 2. 注入延迟（需要 sudo 密码）
sudo bash scripts/inject_delay.sh 50
# 3. 验证 RTT（应在 ~120ms 左右）
bash scripts/verify_latency.sh 50
# 4. 采集
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c50ms_delay.yaml
# 5. 采集完毕后清除延迟
sudo bash scripts/inject_delay.sh 0
```

**c2_100ms（100ms）：**
```bash
# 1. 重启 Unity
sudo bash scripts/inject_delay.sh 100
bash scripts/verify_latency.sh 100
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c100ms_delay.yaml
sudo bash scripts/inject_delay.sh 0
```

**分析（三条件数据采集完后一次性运行）：**
```bash
python -m testbed.latency_module.analysis.rq1_data_quality \
    --datasets "data/rq1/c0_baseline:0ms(23ms RTT)" \
               "data/rq1/c1_50ms:50ms(123ms RTT)" \
               "data/rq1/c2_100ms:100ms(223ms RTT)" \
    --out outputs/rq1/latency_proof
```

---

### 分辨率实验采集（RQ1-Resolution）

两个条件，使用 Python 显示窗口（操作员看 Python 窗口，**不看 Unity 窗口**）：

```
条件          Python 显示   HDF5 分辨率   类比真实场景
c_fullres     720x480      720x480      高质量视频流
c_lowres      240x160      240x160      低带宽压缩流
```

**重要**：启动采集后，**关闭或遮挡 Unity 窗口**，只使用 Python 弹出的显示窗口进行操作，确保操作员的视觉感知与训练数据一致。

**c_fullres（720x480）：**
```bash
# 1. 重启 Unity
# 2. 采集（Python 会弹出 "Operator View (720x480)" 窗口）
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c_fullres.yaml
```

**c_lowres（240x160）：**
```bash
# 1. 重启 Unity
# 2. 采集（Python 会弹出 "Operator View (240x160)" 小窗口，图像像素化）
tb-record-teleop --config testbed/configs/rq1_experiment/teleop_c_lowres.yaml
```

**分析：**
```bash
python -m testbed.latency_module.analysis.rq1_data_quality \
    --datasets "data/rq1/c_fullres:720x480(full)" \
               "data/rq1/c_lowres:240x160(low)" \
    --out outputs/rq1/resolution_proof

# 如果已经跑完 rq1_act_fullres / rq1_act_lowres 的 eval，继续生成更强的 resolution proof：
python scripts/resolution_behavioral_analysis.py
```

---

### tc netem 常用命令参考

```bash
# 查看当前 lo 接口的网络规则
tc qdisc show dev lo

# 注入固定延迟
sudo bash scripts/inject_delay.sh 100       # 100ms 固定延迟

# 注入延迟 + 抖动
sudo bash scripts/inject_delay.sh 100 10   # 100ms ± 10ms

# 清除所有规则（恢复正常）
sudo bash scripts/inject_delay.sh 0

# 快速验证延迟是否生效（ping loopback）
ping -c 5 127.0.0.1
```
