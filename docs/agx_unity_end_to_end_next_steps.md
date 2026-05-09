# AGX Unity End-to-End Next Steps

本文件用于把当前 testbed 和 Unity 项目跑通为一个完整闭环：

```text
Unity/AGX step-ack server
  -> testbed teleop HDF5 recording
  -> dataset QC and replay
  -> ACT training
  -> live Unity inference/eval
```

当前建议先跑稳定的 V1 baseline。Unity README 中提到的 V2.1 multicycle raw 可以作为下一阶段，不建议在第一次打通闭环时同时切任务版本。

## 0. 路径与主配置

Unity 项目：

```text
/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc
```

testbed 项目：

```text
/home/zhaoshuai/workspace_excavator/excavator_testbed
```

当前主线配置：

```text
testbed/configs/teleop_v1.yaml
testbed/configs/act_agx_v1.yaml
testbed/configs/eval_agx_v1.yaml
```

默认 Unity step-ack 地址：

```text
127.0.0.1:5057
```

推荐输出目录：

```text
data/agx_teleop_v1
runs/ckpts/agx_excavation_act_v1
runs/eval/agx_excavation_act_v1
```

## 1. 启动 Unity 场景

在 Unity 打开项目：

```text
/home/zhaoshuai/workspace_uinty/AGXExcavatorCodeDoc
```

优先使用固定工位任务场景：

```text
Assets/AGXUnity_Excavator/AGXUnity_Excavator_small.unity
```

需要确认：

- 场景能正常 Play。
- `AgxSimStepAckServer` 在场景中启用。
- server 端口为 `5057`。
- `ActObservationCollector` 能导出 `qpos / qvel / env_state / fpv`。
- 当前任务仍是固定工位、4 维机械臂动作，不含底盘动作。

如果 Unity 侧 `GET_INFO` 没响应，后面的录制、训练评测都先不要跑。

## 2. 安装 testbed

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed
conda activate aloha
pip install -e ".[dev]"
```

如果环境已经安装过，可以先跳过安装，直接跑下一步 smoke。

## 3. Live 协议 Smoke

Unity 必须正在 Play，并监听 `5057`。

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200
python scripts/agx_smoke.py --host 127.0.0.1 --port 5057 --steps 200 --strict
```

通过标准：

- `GET_INFO` 成功。
- `RESET` 成功。
- 连续 `STEP` 不超时。
- `STEP_RESP.step_id` 与请求一致。
- `qpos` 是 4 维。
- `qvel` 是 4 维。
- `env_state` 是 9 维或兼容版本。
- `fpv` 图像存在且尺寸稳定。

如果失败：

- 不继续录制。
- 不继续 `tb-eval`。
- 先检查 Unity 是否正在 Play、端口是否为 `5057`、`AgxSimStepAckServer` 是否启用。

## 4. 录 1 条 Smoke Demo

先只录 1 条，确认 HDF5 录制链路。

摇杆：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 1 \
  --operator-id zhaoshuai \
  --session-id smoke-v1 \
  --notes "first smoke recording" \
  --output-dir data/agx_teleop_v1
```

键盘 fallback：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input keyboard \
  --num-episodes 1 \
  --operator-id zhaoshuai \
  --session-id smoke-v1-keyboard \
  --notes "first keyboard smoke recording" \
  --output-dir data/agx_teleop_v1
```

键盘录制时请以弹出的 `Testbed Teleop` pygame 小窗口为准，让这个窗口保持焦点。不要按 Unity HUD 上的 PageUp/PageDown 提示，那是 Unity 自己主控制链的键位；`tb-record-teleop --input keyboard` 走的是 Python step-ack 键盘源。

当前 Python 键盘映射：

```text
F / H       -> 回转 swing   - / +
T / G       -> 斗杆 stick   - / +
J / L       -> 铲斗 bucket  - / +
I / K       -> 动臂 boom    + / -
Q           -> 结束录制 session
Backspace   -> 丢弃当前 episode 并重新开始
Ctrl+C      -> 结束命令
```

录制时当前 V1 配置默认使用：

- success mode: `dump_complete_final_hold`
- `deposited_mass_in_target_box_kg >= 300 kg`
- `mass_in_bucket_kg <= 100 kg`
- hold `25` steps
- success 后继续录 `50` steps tail

## 5. 数据质检

离线 QC：

```bash
tb-dataset-qc --dataset-dir data/agx_teleop_v1
```

离线导出 FPV 视频：

```bash
tb-dataset-videos data/agx_teleop_v1/ -o runs/videos/agx_teleop_v1
```

需要检查：

- `data/agx_teleop_v1/qc/summary.json`
- `data/agx_teleop_v1/qc/episodes.csv`
- `runs/videos/agx_teleop_v1`

通过标准：

- episode 可读。
- `action_dim = 4`
- `qpos_dim = 4`
- `qvel_dim = 4`
- `env_state_dim = 9`
- 有 `fpv` 图像。
- `step_id` 单调。

如果 QC 发现坏文件，可以先把坏 episode 移到单独目录，避免训练读到。

## 6. Replay QA

这一步需要 Unity 正在 Play。

单条回放：

```bash
tb-replay \
  --episode data/agx_teleop_v1/episode_0.hdf5 \
  --config testbed/configs/teleop_v1.yaml \
  --save-video
```

批量回放：

```bash
tb-replay \
  --episode data/agx_teleop_v1/ \
  --config testbed/configs/teleop_v1.yaml \
  --save-video
```

通过标准：

- replay 能正常 RESET 和 STEP。
- 机械运动与录制视频大体一致。
- 没有明显的 action 顺序错位，例如 boom/bucket/swing/stick 串轴。
- 没有严重的图像缺失或 qpos 发散。

## 7. 录正式 Demo

Smoke 和 QC 都通过后，再录正式数据。

建议第一轮录 20 到 30 条，不要直接追求很大数据量。

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 30 \
  --operator-id zhaoshuai \
  --session-id baseline-v1 \
  --notes "baseline teleop v1" \
  --output-dir data/agx_teleop_v1
```

录完后重复：

```bash
tb-dataset-qc --dataset-dir data/agx_teleop_v1
tb-dataset-videos data/agx_teleop_v1/ -o runs/videos/agx_teleop_v1
```

建议保留每次录制的 `session_id`，以后做数据筛选和失败分析会轻松很多。

## 7.1 代码生成轨迹验证

如果只是想验证“不用人工输入，直接由代码生成 action 序列并写入 HDF5”的难易程度，可以使用 scripted 输入源：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input scripted \
  --num-episodes 1 \
  --operator-id scripted \
  --session-id scripted-probe-v1 \
  --notes "open-loop scripted trajectory probe" \
  --output-dir data/agx_scripted_probe_v1
```

当前 scripted 轨迹定义在：

```text
testbed/configs/teleop_v1.yaml
```

配置块：

```yaml
teleop:
  scripted:
    segments:
      - {name: "settle", duration_steps: 50, action: [0.0, 0.0, 0.0, 0.0]}
      - {name: "boom_up", duration_steps: 50, action: [0.0, 0.25, 0.0, 0.0]}
```

action 顺序固定是：

```text
[swing, boom, stick, bucket]
```

这个 scripted 输入源适合验证：

- Python 能否无人工输入地驱动 Unity。
- action 顺序是否接对。
- 自动生成的 action 能否进入 HDF5。
- `action_source/type` 是否记录为 `scripted`。
- 后续 `tb-dataset-qc` / `tb-dataset-videos` / 训练读取链路是否兼容。

它不等于“自动专家挖掘策略”。当前实现是开环分段动作，不看土、斗、目标和质量状态。真正想自动生成可训练的高质量 demo，至少还需要引入状态反馈，例如根据 `qpos / qvel / env_state` 做阶段切换和动作修正。

推荐验证命令：

```bash
tb-dataset-qc --dataset-dir data/agx_scripted_probe_v1
tb-dataset-videos data/agx_scripted_probe_v1/ -o runs/videos/agx_scripted_probe_v1
```

## 7.2 关键帧轨迹生成数据

如果想复用“手动摆关键帧，然后自动插值回放”的思路，可以走 keyframe 输入源。这个项目里的实现做了一点适配：当前 Unity step-ack 协议只接受速度命令，不能直接 `set_qpos` 或设置 drive target，所以回放时会：

```text
JSON keyframes {step/t, qpos}
  -> 线性插值得到 q_target
  -> action = clip(kp * (q_target - 当前 qpos), +/- max_abs_action)
  -> STEP 发送 [swing, boom, stick, bucket]
```

### 7.2.1 采集关键帧 JSON

Unity 必须正在 Play。

```bash
tb-keyframe-capture \
  --config testbed/configs/teleop_v1.yaml \
  --output data/keyframes/agx_keyframes_v1.json \
  --operator-id zhaoshuai \
  --session-id keyframe-v1 \
  --notes "manual qpos keyframes"
```

操作方式：

```text
F / H       -> 回转 swing   - / +
T / G       -> 斗杆 stick   - / +
J / L       -> 铲斗 bucket  - / +
I / K       -> 动臂 boom    + / -
R           -> 记录当前 qpos 为一个关键帧
Q           -> 结束采集并保存 JSON
```

至少需要记录 2 个关键帧。保存后的 JSON 大致长这样：

```json
{
  "schema_version": "agx_keyframes_v1",
  "control_hz": 50,
  "action_order": ["swing", "boom", "stick", "bucket"],
  "qpos_order": ["swing", "boom", "stick", "bucket"],
  "keyframes": [
    {"name": "k0", "step": 20, "t": 0.4, "qpos": [0.1, 0.2, 0.3, 0.4]},
    {"name": "k1", "step": 120, "t": 2.4, "qpos": [0.2, 0.3, 0.2, 0.5]}
  ]
}
```

当前 debug 信息会额外保存 `qvel` 和 `env_state`。末端执行器 `xyz/rpy` 目前不在 step-ack 观测里，所以不会自动保存；如果后续 Unity 把 EE pose 加到协议或 `env_state` 里，再补进 JSON 即可。

### 7.2.2 用关键帧自动生成 HDF5

确认 `testbed/configs/teleop_v1.yaml` 里这个路径存在：

```yaml
teleop:
  keyframe:
    path: "data/keyframes/agx_keyframes_v1.json"
```

然后运行：

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input keyframe \
  --num-episodes 1 \
  --operator-id keyframe \
  --session-id keyframe-rollout-v1 \
  --notes "qpos keyframe interpolation rollout" \
  --output-dir data/agx_keyframe_rollout_v1
```

检查输出：

```bash
tb-dataset-qc --dataset-dir data/agx_keyframe_rollout_v1
tb-dataset-videos data/agx_keyframe_rollout_v1/ -o runs/videos/agx_keyframe_rollout_v1
```

### 7.2.3 这个方案的限制

这个方案比纯 open-loop segments 更好，因为它会闭环跟踪当前 `qpos`；但它仍然不是完美专家：

- `qpos` 是归一化 4D 观测，不一定等价于真实关节角物理范围。
- 线性插值只保证姿态轨迹平滑，不保证斗齿路径、入土角、装载质量。
- P 控制器输出的是速度命令，存在滞后和超调。
- 土体、碰撞、bucket 内质量会改变实际运动结果。
- 当前 JSON 不含 EE pose，除非 Unity 侧增加观测字段。

建议先把它当成“半自动轨迹模板”和“自动生成 smoke 数据”的工具。若要生成可训练的高质量 demo，下一步应在 keyframe 回放中加入 phase 条件，例如根据 `mass_in_bucket_kg`、`deposited_mass_in_target_box_kg`、`min_distance_to_target_m` 做阶段切换和失败重试。

## 8. 训练 Smoke

先跑短训练确认训练链路没有环境或维度问题。

```bash
tb-train \
  --config testbed/configs/act_agx_smoke.yaml \
  --epochs 5
```

通过标准：

- DataLoader 能读 HDF5。
- 模型能正常 forward/backward。
- checkpoint 能写出。
- loss 没有 NaN。

## 9. 正式训练 ACT V1

```bash
tb-train --config testbed/configs/act_agx_v1.yaml
```

默认配置：

- dataset: `data/agx_teleop_v1`
- checkpoint dir: `runs/ckpts/agx_excavation_act_v1`
- best checkpoint: `runs/ckpts/agx_excavation_act_v1/policy_best.ckpt`
- input: 默认 `qpos`
- model: ACT

训练产物重点看：

```text
runs/ckpts/agx_excavation_act_v1/policy_best.ckpt
runs/ckpts/agx_excavation_act_v1/resolved_config.yaml
runs/ckpts/agx_excavation_act_v1/run_metadata.json
runs/ckpts/agx_excavation_act_v1/train_val_split.yaml
```

如果训练效果不稳定，先不要急着改模型，优先检查：

- demo 是否都是同一个任务口径。
- 图像尺寸是否一致。
- action 是否有大量饱和或反向修正。
- success demo 是否真的完成 dump，而不是只短暂达到 retained mass。

## 10. Live 推理 Smoke

Unity 必须正在 Play。

```bash
tb-eval --config testbed/configs/eval_agx_smoke.yaml
```

通过标准：

- policy checkpoint 能加载。
- Unity 能 RESET。
- rollout 能跑完整。
- action 输出不是 NaN。
- 视频和 rollout logs 能落盘。

## 11. 正式 Live Eval

```bash
tb-eval --config testbed/configs/eval_agx_v1.yaml
```

结果目录：

```text
runs/eval/agx_excavation_act_v1/results
runs/eval/agx_excavation_act_v1/videos
```

重点文件：

```text
metrics.json
results.csv
rollout_manifest.json
rollouts/rollout_XXX.jsonl
rollouts/rollout_XXX_summary.json
eval_run_metadata.json
eval_resolved_config.yaml
```

当前主 success 口径：

```text
dump_complete_final_hold
```

核心阈值：

```text
deposited_mass_in_target_box_kg >= 300 kg
mass_in_bucket_kg <= 100 kg
hold_steps = 25
```

strict 口径额外要求：

```text
hard_target_collision = 0
spill_before_target = 0
```

## 11.1 使用外部 ViPACT checkpoint 做 Live Eval

如果模型在外部 ViPACT 仓库训练，建议让 ViPACT 继续负责训练，testbed 只负责连接 Unity 做实时推理。当前已预留配置：

```text
testbed/configs/eval_vipact_agx_v1.yaml
```

需要先把配置里的两个路径改成 ViPACT 实际产物：

```yaml
eval:
  ckpt_path: "/home/zhaoshuai/workspace_act/ViPACT/ckpts/agx_excavation_vipact/policy_best.ckpt"

policy:
  norm_stats_path: "/home/zhaoshuai/workspace_act/ViPACT/ckpts/agx_excavation_vipact/dataset_stats.pkl"
```

然后运行：

```bash
tb-eval --config testbed/configs/eval_vipact_agx_v1.yaml
```

注意对齐点：

- ViPACT 训练数据仍需包含 `/observations/qpos`、`/observations/images/fpv`、`/action`。
- `camera_names` 需要和训练时一致；当前 AGX 默认是 `["fpv"]`。
- 当前 ViPACT 用 `equipment_model` 推断维度，`excavator_simple` 对应 4 维 action。
- action 顺序必须保持 `[swing, boom, stick, bucket]`，否则 Unity 执行动作会串轴。
- 如果 ViPACT 使用 4 通道 mask 条件，把 `image_channels` 改成 `4`，并确认训练时也是 4 通道。

## 12. 常见分支处理

### Smoke 连接不上 Unity

先检查：

- Unity 是否 Play。
- 场景里是否有 `AgxSimStepAckServer`。
- 端口是否为 `5057`。
- 是否有旧 Python 进程占着连接。
- testbed 配置里的 `agx.host / agx.port` 是否一致。

### 录制动作串轴

检查：

```text
testbed/configs/teleop_v1.yaml
```

重点字段：

```yaml
teleop:
  joystick:
    joystick_ids:
    axis_map:
    invert:
    scale:
```

先用小动作单轴测试，不要直接录正式 demo。

### Dataset QC 失败

先看：

```text
data/agx_teleop_v1/qc/summary.json
data/agx_teleop_v1/qc/episodes.csv
```

常见问题：

- 未完整写完的 HDF5。
- 图像缺失。
- `env_state` 维度不一致。
- step_id 不单调。

### 训练 loss 异常

优先检查：

- dataset 目录是否混入旧 schema 数据。
- `task.num_episodes` 是否超过实际 episode 数。
- 图像尺寸是否一致。
- action 是否全零或存在 NaN。
- checkpoint 目录是否复用了不兼容旧 run。

### Eval 成功率低

先做 failure analysis，不急着改模型：

- 看 rollout 视频。
- 看 `rollout_XXX_summary.json`。
- 对比各 success 口径：
  - `legacy_any`
  - `final_hold`
  - `strict_final_hold`
  - `dump_complete_final_hold`
  - `strict_dump_complete`
- 区分是挖不到、运不到、倒不干净、碰撞、还是目标前洒土。

## 13. 当前推荐执行顺序

按这个列表逐步尝试：

- [ ] Unity 打开 `AGXUnity_Excavator_small.unity` 并 Play。
- [ ] 确认 `AgxSimStepAckServer` 监听 `5057`。
- [ ] 跑 `scripts/agx_smoke.py`。
- [ ] 跑 `scripts/agx_smoke.py --strict`。
- [ ] 录 1 条 smoke demo。
- [ ] 跑 `tb-dataset-qc`。
- [ ] 跑 `tb-dataset-videos`。
- [ ] 跑单条 `tb-replay`。
- [ ] 录 20 到 30 条正式 demo。
- [ ] 再跑一次 `tb-dataset-qc`。
- [ ] 跑 `tb-train --config testbed/configs/act_agx_smoke.yaml --epochs 5`。
- [ ] 跑 `tb-train --config testbed/configs/act_agx_v1.yaml`。
- [ ] 跑 `tb-eval --config testbed/configs/eval_agx_smoke.yaml`。
- [ ] 跑 `tb-eval --config testbed/configs/eval_agx_v1.yaml`。
- [ ] 根据 rollout 视频和 logs 做 failure analysis。

## 14. 暂不建议现在做的事

第一次闭环跑通前，先不要做这些：

- 不要同时切到 V2.1 multicycle raw。
- 不要改 wire protocol。
- 不要改 action 维度。
- 不要把底盘动作加进训练。
- 不要把模型直接搬进 Unity Sentis/ONNX。
- 不要在 smoke 未通过时继续录制或 eval。

先把 V1 baseline 稳定跑通，再决定下一轮是扩数据、做输入消融，还是升级到 V2.1 多循环任务。
