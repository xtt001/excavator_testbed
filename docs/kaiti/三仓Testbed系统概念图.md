# 三仓 Testbed 系统概念图（含时延分析模块）

![](figures/system_concept_3repo_latency.svg)

## 图的核心含义

这张图从全局上展示了当前系统的三仓协同关系，以及 `latency_module` 在整个 testbed 中的位置。

三仓分工如下：

- **Repo A — `excavator_testbed`**
  Python 侧主控仓库，负责遥操作录制、HDF5 落盘、回放 QA、离线 ACT 训练、live rollout 评测，以及失效归因相关的实验管理。

- **Repo B — `AGXUnity_Excavator`**
  Unity / C# 场景仓库，负责 AGX 物理、挖掘机场景、step-ack server、相机渲染以及把 `qpos / qvel / fpv / env_state` 打包返回给 Python。

- **Repo C — `sim-protocol`**
  协议与语义共享仓库，负责消息格式、协议版本、`env_state` 字段定义、常量和评测语义，是 Repo A 与 Repo B 的共享 source of truth。

## 这张图怎么读

### 1. 主闭环

主闭环是蓝色箭头，对应当前系统最核心的在线链路：

1. 操作员通过 joystick / keyboard 在 Python 侧输入动作。
2. Repo A 的 CLI / runtime 调用 `AGXSimBackend`，通过 `GET_INFO / RESET / STEP` 与 Repo B 通信。
3. Repo B 执行物理步进、渲染相机并返回 `fpv + qpos/qvel + env_state`。
4. Repo A 一边把这些观测用于 teleop / replay / eval，一边把 episode 写入 HDF5，或者送入 policy rollout 评测。

这个主闭环是当前 testbed 的主系统。

### 2. 数据生产与模型使用两条支路

Repo A 收到 Repo B 返回的数据后，会分成两条主要支路：

- **数据支路**
  `record -> HDF5 -> replay QA / dataset QC / dataset videos`

- **模型支路**
  `ACT train -> checkpoint -> live eval -> metrics / videos / rollout logs`

这两条支路共享同一套 backend、任务语义和观测结构，因此可以把“数据问题”和“模型问题”放在同一平台内统一分析。

### 3. 时延分析模块的位置

橙色虚线箭头表示 `latency_module` 的观测路径。

它不是一个替代主系统的新框架，而是挂在 Repo A 主链路旁边的 **可插拔观测层**：

- 在线阶段：
  `LatencySession / ControlProbe` 可以挂到 step-ack 客户端上，对请求发送、Unity 接收、物理步进、图像准备、响应返回等关键节点打点。

- 离线阶段：
  `trace_logger / rq1_data_quality / plot scripts` 会读取 trace 与 HDF5 数据，生成：
  - RTT 与分段时延统计
  - teleop 数据质量图
  - latency proof / resolution proof
  - 面向论文动机的可视化证据

因此它属于：

> 在不改写主系统结构的前提下，为 testbed 增加“可观测、可定位、可复现实验”的能力层。

### 4. 为什么 Repo C 单独画出来

Repo C 并不直接参与每一步运行时闭环，但它决定了：

- 包格式怎么解释
- `env_state` 每一维代表什么
- 协议版本如何对齐
- 成功语义和评测字段如何统一

所以它是整个三仓系统的“语义对齐层”。
没有 Repo C，Repo A 和 Repo B 很容易出现“能连上，但对同一个字段理解不同”的问题。

## 这张图最适合在汇报里表达什么

如果你在开题或组会中使用这张图，最适合强调下面三点：

1. **当前系统不是单仓脚本集合，而是三仓协同的实验平台**
   Python testbed、Unity 场景和协议语义已经形成清晰边界。

2. **时延分析模块不是旁支小工具，而是主平台的 observability layer**
   它把“系统延迟 -> 数据质量 -> ACT 表现”放进了同一张实验地图里。

3. **当前平台已经具备做失效归因的能力**
   不只是看 policy 成不成功，还可以进一步区分：
   - 是系统链路问题
   - 还是 teleop 数据质量问题
   - 还是 reward / success 语义问题
   - 还是模型本身的问题

## 一句汇报版总结

可以直接用下面这句来口头介绍：

> 当前平台由三仓协同组成：Repo B 提供 AGXUnity 场景与 step-ack server，Repo C 提供共享协议与语义定义，Repo A 负责遥操作数据生产、ACT 训练评测以及实验管理；而新增的 latency analysis 模块以可插拔方式挂在 Repo A 主链路旁边，把系统时延、数据质量和模型表现统一纳入同一个 testbed 中分析。
