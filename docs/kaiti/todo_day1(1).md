# 任务描述：为现有 AGXUnity 遥操作 testbed 新增“时延观测与分析模块”

## 背景
我当前已经有一个基于 AGXUnity 的遥操作 testbed。  
这个 testbed 目前的主要用途是：
- 跑遥操作任务；
- 录制数据；
- 对比不同模型或不同配置的表现效果。

现在我不希望把现有 testbed 改造成另一个独立系统，而是希望**在不破坏现有主链路的前提下，新增一个可插拔、低侵入、可复用的时延观测与分析模块**。

这个模块的定位是：

- 服务当前论文研究中的时延分析；
- 同时作为未来挖机项目的通用时延检测基础设施长期保留；
- 能够挂载到现有 testbed 上，对视频链路、控制链路、闭环反馈链路进行打点、记录、分析和出图。

---

## 总体目标
请基于现有 testbed，新增一个独立模块：

**Latency Instrumentation & Analysis Module**

要求这个模块满足以下原则：

1. **模块化**：以插件/组件形式接入，不重构整个 testbed；
2. **低侵入**：尽量少改现有业务逻辑；
3. **可开关**：支持开启/关闭时延分析功能；
4. **可复用**：后续任何遥操作实验都能复用；
5. **可扩展**：未来可以继续接入 ROI、AR、调度器等实验。

---

## 设计原则

### 1. 不替换现有 testbed，只做增量增强
我不希望你把当前 testbed 改写成一个全新的 latency-only 系统。  
正确思路是：

- 保留现有 testbed 的运行方式；
- 保留现有控制、视频、录制、评测流程；
- 在关键节点增加打点与 trace 采集能力；
- 在 testbed 外围补充日志分析与绘图脚本。

换句话说：

> 现有 testbed 仍然是主系统，时延模块只是一个附加能力层。

---

### 2. 模块应该以“观测层”形式存在
请把新增内容理解为一个 observability layer，而不是新的业务主干。

模块职责包括：
- 记录关键时间戳；
- 关联 frame / command / feedback 的生命周期；
- 输出统一 trace；
- 离线分析时延；
- 自动生成图表和摘要结果。

模块不负责：
- 替代现有任务执行逻辑；
- 改写现有训练流程；
- 重构整个通信框架。

---

## 需要新增的模块能力

### A. Trace 打点能力
请在现有 testbed 的关键节点上，以最小侵入方式加入打点。

#### 视频链路关键事件
- `frame_capture`
- `encode_start`
- `encode_end`
- `packet_send`
- `packet_recv`
- `decode_start`
- `decode_end`
- `frame_render`

#### 控制链路关键事件
- `cmd_input`
- `cmd_send`
- `cmd_recv`
- `cmd_apply`

#### 闭环反馈关键事件
- `state_feedback_ready`
- `state_feedback_send`
- `state_feedback_recv`
- `state_feedback_visualized`（如适用）

要求：
- 尽量使用统一时间基准；
- 打点逻辑独立封装；
- 现有主逻辑只需要少量 hook 调用。

---

### B. ID 追踪能力
请为系统增加统一的追踪 ID 管理。

至少包括：
- `trace_id`
- `run_id`
- `config_id`
- `frame_id`
- `cmd_id`

目标：
- 可以追踪一帧视频的完整生命周期；
- 可以追踪一个控制命令从输入到生效再到反馈的完整链路。

---

### C. 统一日志输出
请新增统一日志导出模块，推荐 JSONL。

每条日志建议包含：
- `timestamp_ns`
- `event_name`
- `trace_id`
- `run_id`
- `config_id`
- `frame_id`
- `cmd_id`
- `resolution`
- `fps`
- `bitrate`
- `codec`
- `delay_inject_ms`
- `jitter_inject_ms`
- `loss_rate`
- `extra_info`

要求：
- 每次实验单独输出；
- 日志结构清晰；
- 方便后续离线分析。

---

### D. 自动时延分析
请新增 analysis 脚本，从 trace 自动计算以下指标：

#### 视频链路
- `capture_to_encode`
- `encode_latency`
- `network_video_latency`
- `decode_latency`
- `render_latency`
- `video_e2e_latency`

#### 控制链路
- `control_network_latency`
- `cmd_apply_latency`

#### 闭环反馈链路
- `step_ack_latency`

统计输出至少包括：
- mean
- median
- p90
- p95
- p99
- std

---

### E. 自动绘图
请新增一个离线绘图模块，能够自动生成：

1. **端到端时延分布图**
2. **分段时延堆叠图**
3. **时延时间序列抖动图**
4. **不同配置下的时延对比图**

要求：
- 用 Python 实现；
- 优先 matplotlib；
- 自动保存 PNG；
- 目录清晰。

---

## 推荐接入方式
请不要大改现有系统，而是优先采用以下方式接入：

### 方式 1：Hook / Callback
在关键节点插入：
- `latency_module.log_event(...)`

### 方式 2：Decorator / Wrapper
对于已有发送、接收、编码、渲染函数，可用 wrapper 包裹。

### 方式 3：Sidecar-style 分析脚本
trace 采集与离线分析分离：
- 在线阶段只负责记日志；
- 离线阶段再做解析、统计和绘图。

---

## 推荐项目结构
请将新增功能组织为独立模块，例如：

```text
testbed/
  core/
    ... existing code ...
  latency_module/
    instrumentation/
      trace_logger.py
      event_schema.py
      id_manager.py
    probes/
      video_probe.py
      control_probe.py
      feedback_probe.py
    analysis/
      parse_trace.py
      compute_metrics.py
      plot_latency.py
      export_summary.py
    configs/
      latency_default.yaml
  outputs/
    run_xxx/
      trace.jsonl
      summary.json
      plots/


要求：

latency_module/ 尽量独立；
与现有 core 解耦；
未来能单独维护。
开发优先级
Phase 1：最小接入版

先实现：

独立 trace logger；
关键事件打点；
基础 JSONL 导出；
基础时延统计；
基础绘图。
Phase 2：增强版

再实现：

多配置实验自动汇总；
更完整的指标统计；
配置对比图；
更清晰的 summary 导出。
Phase 3：预留扩展接口

最后再考虑：

ROI 编码实验接入；
AR 预测补偿实验接入；
调度器实验接入；
性能回归检测。
非目标

当前阶段不要做：

不重构整个 testbed 架构；
不重写现有控制/视频主链路；
不做外部硬件 G2G 测量；
不做完整 ACT 训练闭环；
不做复杂 GUI。
验收标准

完成后，我希望达到：

现有 testbed 可以保持原有功能不变；
只需少量接入代码，就能开启时延观测模式；
可以自动输出统一 trace；
可以分析视频链路、控制链路和闭环链路的时延；
可以生成开题报告可直接使用的时延图表；
未来项目继续做遥操作时延检测时，这个模块可以直接复用。
输出要求

请直接给我：

模块化代码；
与现有 testbed 的接入说明；
示例 hook 点位；
一份最小 demo；
trace 输出示例；
自动分析与绘图脚本；
README，说明如何在现有 testbed 中启用该模块。