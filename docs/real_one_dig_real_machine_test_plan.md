# Real One-Dig 真机测试状态与流程

状态日期：`2026-06-01`

本文记录当前 real one-dig imitation checkpoint 的状态，以及进入真机测试时推荐采用的安全流程。

## 当前状态

当前目标不是泛化到新场景，而是先验证：模型是否能在 9 条成功真机 one-dig 数据上学会模仿专家动作。

当前推荐 checkpoint：

```text
runs/ckpts/real_one_dig_v1_all9_zero_latent_dense_overfit/policy_best.ckpt
```

训练配置：

```text
testbed/configs/act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml
```

数据：

```text
data/real_one_dig_v1_windows/
```

这份数据来自移动硬盘原始真机数据 `/media/pingfan/EXTERNAL_USB/real_teleop_v1` 的成功 `episode_13..21`，转换后为 `episode_0..8`。raw real-world 数据不修改；训练主标签是转换窗口中的 `action`，`raw_action` 和 `commanded_action` 只作为诊断和安全对照。

## 离线评测结果

真机候选使用同一个 checkpoint，但评测和后续真机推理建议打开 ACT temporal aggregation。对应离线评测目录：

```text
runs/eval/real_one_dig_v1_all9_zero_latent_dense_overfit_temporal
```

评测命令：

```bash
tb-offline-real-one-dig-eval \
  --config testbed/configs/act_real_one_dig_v1_all9_zero_latent_dense_overfit.yaml \
  --temporal-agg \
  --output-dir runs/eval/real_one_dig_v1_all9_zero_latent_dense_overfit_temporal
```

9 条训练数据上的离线 imitation 结果：

| 指标 | 数值 |
|---|---:|
| mean overall MAE | `0.0485` |
| mean active MAE | `0.0468` |
| mean sign accuracy | `0.990` |
| worst episode | `episode_4` |
| worst active MAE | `0.0531` |

按轴误差：

| 轴 | active MAE | sign accuracy |
|---|---:|---:|
| swing | `0.1581` | `0.9765` |
| boom | `0.0609` | `0.9955` |
| stick | `0.0850` | `0.9929` |
| bucket | `0.0817` | `0.9961` |

可视化输出：

```text
runs/eval/real_one_dig_v1_all9_zero_latent_dense_overfit_temporal/episode_N_overlay.mp4
runs/eval/real_one_dig_v1_all9_zero_latent_dense_overfit_temporal/episode_N_actions.png
runs/eval/real_one_dig_v1_all9_zero_latent_dense_overfit_temporal/gap_summary.json
```

结论：在这 9 条成功记录本身上，模型已经能较好模仿专家 one-dig 动作序列。当前结果支持进入真机测试流程，但不建议直接全幅度闭环自主挖掘。

## 为什么使用 Temporal Aggregation

当前 ACT `chunk_size = 25`，50 Hz 下约等于 0.5 秒 action chunk。不开 temporal aggregation 时，policy 输出容易呈现阶梯状。打开 temporal aggregation 后，当前 step 会融合多个历史 chunk 的预测，曲线更平滑，离线指标也略有提升。

后续真机测试应保持这个推理口径：

```text
temporal_agg = true
```

如果未来仍觉得动作不够平滑，再考虑重训小 `chunk_size` 版本，例如 `10` 或 `5`；当前阶段不需要先重训。

## 真机测试推荐流程

### 1. Live Shadow

目的：验证实时输入链路和模型输出阶段是否正确，不下发模型 action。

流程：

1. 真机正常启动，接入实时 FPV、qpos、qvel。
2. 人类操作员执行一次 one-dig。
3. 模型同步预测 `policy_action`，但不发送给真机。
4. 记录人类 action、模型 action、FPV、qpos、qvel、时间戳。
5. 检查四轴是否同方向、同阶段，尤其看 swing 回转、boom 抬落、bucket 收放。

通过标准：

- 没有持续反向动作。
- 没有长时间非零错误输出。
- 动作阶段与人工操作基本一致。
- 传感器丢帧、图像异常、qpos/qvel 异常时能安全记录并阻止下发。

### 2. 低幅度 Guarded Test

目的：只验证闭环动作方向和稳定性，不追求一次完成挖掘。

建议：

- policy action 乘以低幅度 scale，例如 `0.2` 或更低。
- 先跑短窗，不跑完整 one-dig。
- 操作员保持 deadman 和人工接管。
- 任一轴方向异常、持续抖动、靠近机械限位或图像输入异常时立即切零动作。

通过标准：

- swing、boom、stick、bucket 方向和离线预期一致。
- action 没有明显阶梯抖动导致机械不自然响应。
- qpos 变化与 action 方向一致。
- 操作员能随时接管。

### 3. 分阶段放大

低幅度测试稳定后，再逐步提高 action scale：

```text
0.2 -> 0.4 -> 0.6 -> 1.0
```

每一档都先做短窗，再做更长窗口。只有在方向、平滑性、机械姿态和安全边界都稳定后，才尝试完整 one-dig。

### 4. 完整 One-Dig 尝试

完整尝试前必须确认：

- temporal aggregation 已启用。
- action clamp 到 `[-1, 1]`。
- 有 rate limiter 限制相邻 step action 变化。
- 有 joint limit guard。
- 有 deadman 和人工接管。
- 图像丢帧、qpos/qvel 丢帧、policy 推理异常时输出零动作。
- 所有测试日志落盘，便于之后离线复盘。

## 当前边界

当前离线结果证明的是：模型能在 9 条真实 FPV/qpos/qvel 记录上输出接近专家的 one-dig action。

它尚未证明：

- 闭环误差不会累积。
- 新土堆、新初始姿态或新光照下仍能工作。
- 真机执行器对模型 action 的响应一定与录制时一致。

因此当前推荐动作是：进入 live shadow 和低幅度 guarded test，而不是直接全幅度自主运行。
