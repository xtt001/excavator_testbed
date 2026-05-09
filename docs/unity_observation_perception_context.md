# Unity 观测与感知工作交接上下文

本文用于开启新对话时快速接上当前挖掘机项目状态，重点面向后续 Unity 观测、相机、感知、mask/视觉输入相关工作。

## 1. 仓库与路径

当前工作涉及几个仓库：

- testbed：
  `/home/zhaoshuai/workspace_excavator/excavator_testbed`
- Unity/AGX：
  `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc`
- 协议说明：
  `/home/zhaoshuai/workspace_excavator/sim-protocol`
- ViPACT：
  `/home/zhaoshuai/workspace_act/ViPACT`
- 缩比模型部署：
  `/home/zhaoshuai/workspace_deploy`

VS Code workspace：

- `/home/zhaoshuai/workspace_excavator/excavator.code-workspace`

## 2. 已经跑通的主流程

目前已经跑通过：

1. Unity 单独运行 AGX 挖掘机。
2. testbed 连接 Unity，通过 `StepReq/StepResp` 做同步 step。
3. 使用手柄/键盘采集 HDF5 数据。
4. 使用 testbed 内置 ACT 训练。
5. 使用 Unity 做 eval 推理。
6. eval 过程会输出 rollout JSONL，其中每步包含观测、action、奖励、任务指标。
7. 已额外做了缩比模型 action 回放脚本，把 eval JSONL 中的 action 发给缩比模型。

典型数据：

- 采集数据目录：
  `/home/zhaoshuai/workspace_excavator/excavator_testbed/data/agx_teleop_v1`
- eval rollout：
  `/home/zhaoshuai/workspace_excavator/excavator_testbed/runs/eval/agx_excavation_act_v1/results/rollouts/rollout_000.jsonl`
- 缩比模型测试 rollout：
  `/home/zhaoshuai/workspace_deploy/data/rollout_001.jsonl`

## 3. Action 语义

testbed/Unity 之间 action 固定为 4 维：

```text
action = [swing, boom, stick, bucket]
```

含义：

- `swing`：回转
- `boom`：动臂
- `stick`：斗杆/小臂
- `bucket`：铲斗

Unity bridge 中也明确声明：

- `action_order = ["swing_speed_cmd", "boom_speed_cmd", "stick_speed_cmd", "bucket_speed_cmd"]`
- `qpos_order = ["swing_position_norm", "boom_position_norm", "stick_position_norm", "bucket_position_norm"]`

关键 Unity 文件：

- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimStepAckServer.cs`
- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimProtocol.cs`

关键位置：

- `AgxSimStepAckServer.cs`
  - `CreateInfoPayload()`：返回 action/qpos/camera 元信息。
  - `HandleStepRequest()`：接收 testbed 的 action，并转成 Unity 控制命令。
  - `CreateStepPayload()`：返回 qpos/qvel/env_state/image/reward/metrics 等观测。
  - `CaptureImageFrame()`：采集图像。

## 4. 当前 Unity 返回给 testbed 的观测

每次 testbed 调 `env.step(action)` 后，Unity 会返回一个 observation。

目前主要包含：

- `qpos`：4 维归一化关节/机构位置，顺序 `[swing, boom, stick, bucket]`
- `qvel`：4 维速度
- `env_state`：任务相关状态与指标向量
- `images`：相机图像，目前主要是 `fpv`
- `reward`
- `task_metrics`
- `warnings`

在 eval JSONL 中可看到每步字段：

```json
{
  "t": 0,
  "step_id": 0,
  "qpos": [...],
  "qvel": [...],
  "env_state": [...],
  "action": [...],
  "task_metrics": {...},
  "warnings": []
}
```

注意：JSONL 默认没有直接保存完整图像，只保存了状态/action/metrics。视频保存和训练数据 HDF5 中会涉及图像。

## 5. Unity 相机与 fpv

当前训练/eval 配置通常使用：

```yaml
camera_names: ["fpv"]
```

Unity 侧的 `fpv` 对应场景中的 `FollowCamera`，Inspector 中显示 View Name 为 `First Person View`。它不是人眼严格驾驶舱视角，而是当前项目中用于观测的跟随/第一人称视角相机。

Unity 场景相关文件：

- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity`
- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_measurements.unity`

如果后续做感知/多视角，优先检查：

1. Unity 场景里有哪些 Camera GameObject。
2. `AgxSimStepAckServer.cs` 的 camera descriptor 如何收集。
3. `CaptureImageFrame()` 当前只输出哪个相机、格式和分辨率。
4. testbed `camera_names` 是否支持多个 camera。

## 6. testbed eval 中观测如何送给模型

关键文件：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/eval/suite.py`

关键逻辑：

```python
obs = ts.observation
policy_input = dict(obs)
for cam in task.camera_names:
    img = obs.get("images", {}).get(cam)
    policy_input[f"image_{cam}"] = ...
action = self.policy.predict(policy_input)
ts = env.step(action)
```

也就是说 eval 过程是：

```text
Unity 返回观测 obs
      ↓
testbed 整理 qpos + image_fpv 等 policy_input
      ↓
ACT/ViPACT 输出 action
      ↓
testbed 把 action 发给 Unity
      ↓
Unity 执行动作并返回下一步观测
```

每步的 action 会写入 rollout JSONL：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/eval/suite.py`
  - per-step log 中有 `"action": np.array(action, dtype=np.float32)`

## 7. ACT / ViPACT 输入输出

当前 ACT/ViPACT 在挖掘机任务中的核心输入：

- `qpos`：4 维
- `image_fpv`：RGB/RGBA 图像，通常由 Unity camera 得到

输出：

- 4 维 action
- 顺序仍是 `[swing, boom, stick, bucket]`

ACT/ViPACT 内部可能一次预测 chunk，但 adapter 在 eval 时每个环境 step 只取/聚合出当前要执行的一步 action。

testbed 内置 ACT 相关：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/policies/act/adapter.py`
- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/configs/act_agx_v1.yaml`

testbed ViPACT adapter：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/policies/vipact/adapter.py`
- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/configs/eval_vipact_agx_v1.yaml`

ViPACT 外部训练配置：

- `/home/zhaoshuai/workspace_act/ViPACT/configs/agx_excavator/02_train.yaml`

目前如果不启用 ViPACT mask conditioning，原来的 `qpos + fpv image + action` 数据足够训练。若启用 mask，则需要额外采集或生成 mask 图像/通道，并对齐 ViPACT 数据读取逻辑。

## 8. HDF5 数据大致内容

使用 `tb-record-teleop` 采集时，Unity 不关心输入来自键盘、手柄还是脚本；testbed 每步给 Unity 发 action，Unity 返回观测，testbed 存成 HDF5。

典型采集命令：

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed

tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 1 \
  --operator-id zhaoshuai \
  --session-id smoke-v1 \
  --notes "teleop recording" \
  --output-dir data/agx_teleop_v1
```

testbed 配置：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/configs/teleop_v1.yaml`

重点配置：

```yaml
task:
  camera_names: ["fpv"]
  max_steps: 1000
  control_hz: 50
  dt: 0.02

action_semantics: "actuator_speed_cmd"
```

## 9. Unity 端键盘/手柄控制

Unity 单独运行时的手柄/键盘控制和 testbed 采集时的输入源曾出现过方向不一致，后续要特别注意“数据来源”和“action 语义”不要混。

Unity 控制源文件：

- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/Control/Sources/KeyboardOperatorCommandSource.cs`
- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/Control/Sources/FarmStickOperatorCommandSource.cs`
- `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/Control/Sources/GamepadOperatorCommandSource.cs`

testbed 采集输入源：

- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/actions/keyboard.py`
- `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/actions/gamepad.py`

当前 testbed keyboard 约定：

```text
F / H -> swing -/+
I / K -> boom +/-
T / G -> stick -/+
J / L -> bucket -/+
```

## 10. 缩比模型联动

已新增缩比模型 action 回放脚本：

- `/home/zhaoshuai/workspace_deploy/deploy_scale_model/rollout_action_send.py`

缩比模型接收端：

- `/home/zhaoshuai/workspace_deploy/deploy_scale_model/excavator.py`

rollout action 到缩比模型轴的映射：

```text
action = [swing, boom, stick, bucket]

X1 = swing
Y1 = stick
X2 = bucket
Y2 = boom
Z1 = 0
Z2 = 0
```

缩比模型轴约定：

```text
x 左负右正
y 上负下正
```

为了避免 eval 输出 action 太小被缩比模型死区吃掉，已在 `excavator.py` 中做了区分：

- 手柄直控保留 0.15 死区。
- `source == "testbed_rollout_jsonl"` 的回放数据不走死区。

曾对 `/home/zhaoshuai/workspace_deploy/data/rollout_001.jsonl` 做过动臂安全调整：

- 只改 `action[1]` boom。
- 正向动臂下压动作限制到最大 `0.02`。
- 原始备份：
  `/home/zhaoshuai/workspace_deploy/data/rollout_001_before_boom_limit.jsonl`

## 11. 后续做 Unity 观测/感知建议从这里开始

优先检查顺序：

1. Unity bridge 当前到底返回哪些观测：
   `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimStepAckServer.cs`

2. 协议字段定义：
   `/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc/Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimProtocol.cs`

3. Python 侧解析协议：
   `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/backends/agx/protocol.py`

4. testbed env 如何包装 Unity observation：
   `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/backends/agx/env.py`

5. eval 时如何把 obs 交给 policy：
   `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/eval/suite.py`

6. ACT/ViPACT adapter 需要什么输入：
   `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/policies/act/adapter.py`
   `/home/zhaoshuai/workspace_excavator/excavator_testbed/testbed/policies/vipact/adapter.py`

## 12. 观测/感知方向的待办问题

新对话可以从这些问题切入：

1. Unity 端能否返回多相机图像，而不仅是 `fpv`？
2. 当前图像格式是 RGB 还是 RGBA？分辨率是多少？是否可配置？
3. 是否需要保存 depth、segmentation、mask、bucket/soil/target 的语义标签？
4. 如果 ViPACT 需要 mask conditioning，mask 从 Unity 中如何生成？
5. HDF5 采集链路是否已经保存多相机/多模态观测？
6. eval JSONL 是否需要保存 action 之外的图像路径或感知结果？
7. 是否需要把 Unity 侧感知输出同步给缩比模型，而不是只回放 action？

## 13. 新对话建议开场

可以直接把下面这句话贴到新对话：

```text
请阅读 /home/zhaoshuai/workspace_excavator/excavator_testbed/docs/unity_observation_perception_context.md。
我接下来要做 Unity 观测和感知相关工作，重点检查 Unity 当前能返回哪些相机/图像/状态，如何扩展 mask/depth/segmentation，并让 testbed 采集、训练、eval 链路都能使用这些观测。
```
