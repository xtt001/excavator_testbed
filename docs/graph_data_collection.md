# Graph Data Collection

## 流程图

```text
┌─────────────────────────────────────────────────────────────┐
│ Single source of truth: raw teleop (backward compatible)    │
│                                                             │
│  Unity teleop, export depth frames during each episode      │
│       │                                                     │
│       ├─ teleop stream ──→ tb-record-teleop                 │
│       │                       └→ data/graph_sessions/<sess>/teleop/ │
│       │                            episode_*.hdf5 (NO graph)│
│       │                                                     │
│       └─ depth frame sequence → DepthCameraSnapshots/       │
│                                  depth_camera_<ts>_frame*.json│
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ Post-processing (cheap, repeatable, swappable)
┌─────────────────────────────────────────────────────────────┐
│ Graph variant outputs                                       │
│                                                             │
│  tb-build-graph-dataset                                     │
│   --teleop-dir   data/graph_sessions/<sess>/teleop          │
│   --snapshot-map data/graph_sessions/<sess>/graph_attach.yaml │
│   --output-dir   data/graph_sessions/<sess>/graph_time_v1    │
│   --max-nodes 256 --gradient-node-ratio 0.7 ...             │
│                                                             │
│  → copies each episode_*.hdf5,                              │
│    injects time-aligned /observations/graph                 │
│  → same teleop can spawn graph_5hz, graph_10hz, ...         │
└─────────────────────────────────────────────────────────────┘
                          │
   ┌──────────────────────┴──────────────────────┐
   │                                             │
[baseline train]                         [with-graph train]
ACT(qpos) on teleop/                    ACT(qpos+graph) on graph_time_v1/
(existing yaml, unchanged)              (future yaml, NOT in scope)
```

## Snapshot 命名约定

Unity 侧 `DepthCameraSnapshotExporter` 会把深度快照写到
`GraphPerceptionPrj/DepthCameraSnapshots/`。

手动导出时，文件名保持旧形状：
`depth_camera_<yyyyMMdd_HHmmss_fff>_frame<N>.json`。

固定频率序列导出时，文件名形如：
`depth_camera_<session>_ep<episode>_seq<sequence>_step<step>_frame<N>_<timestamp>.json`。
对应 JSON metadata 会记录 `session_id`、`episode_index`、`sequence_index`、
`step_id`、`capture_hz`、`control_hz`、`capture_mode`、`wall_time_utc`。
新版 Repo B 还会写 `wall_time_unix_ns`；旧快照如果只有 `wall_time_utc`，
Repo A 会在生成 snapshot map 时解析成 `timestamp_ns`。

采集时保存原始 teleop HDF5 和 depth frame 序列，不实时建 graph。depth
frame 可以每个 timestep 保存，也可以按 5 Hz / 10 Hz 保存；后处理阶段再
决定实际构图频率，并把 graph 对齐到 episode 的所有 timestep。

Repo B 的序列导出可在 Unity Inspector 中启用，也可通过 Unity 启动参数控制：

```text
--depth-capture-enabled true
--depth-capture-hz 10
--depth-capture-control-hz 50
--depth-capture-session graph_smoke_001
--depth-capture-episode 0
--depth-capture-first-step 0
--depth-capture-output-dir /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/DepthCameraSnapshots
```

当前 `step_id` 是 Repo B 按固定频率估计出的对齐索引：
`first_step + sequence_index * round(control_hz / capture_hz)`。如果采集过程
存在漂移，优先使用时间戳对齐，而不是只相信这个估算 step。真机环境也建议
沿用这个做法：控制/状态 HDF5 保存 `step_ns`，传感器帧保存 `timestamp_ns`，
后处理时用 `--align-domain time` 合并。

## 同步采集命令

推荐使用 session 派生路径，避免手动重复填写多个目录。`--graph-session`
会同时设置：

```text
session_id                 = <session>
session data dir           = data/graph_sessions/<session>
teleop HDF5 output         = data/graph_sessions/<session>/teleop
snapshot map YAML          = data/graph_sessions/<session>/graph_attach.yaml
graph HDF5 output          = data/graph_sessions/<session>/graph_time_v1
Unity depth snapshot dir   = <depth_root>/<session>
depth capture              = enabled
```

其中 `<depth_root>` 默认是：

```text
/home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/output/DepthCameraSnapshots
```

也可以用环境变量覆盖：

```bash
export TESTBED_DEPTH_SNAPSHOT_ROOT=/path/to/DepthCameraSnapshots
```

常用采集命令：

```bash
python -m testbed.cli.record_teleop \
  --config testbed/configs/teleop_v1.yaml \
  --num-episodes 1 \
  --input keyboard \
  --operator-id zhaoshuai \
  --graph-session graph_smoke_003 \
  --notes "synchronized depth graph smoke recording" \
  --depth-capture-hz 1
```

等价的派生路径为：

```text
session-dir:   data/graph_sessions/graph_smoke_003
teleop-dir:    data/graph_sessions/graph_smoke_003/teleop
snapshot-root: /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/output/DepthCameraSnapshots/graph_smoke_003
```

推荐正式 smoke 采集时不要在 Unity Inspector 中提前勾选
`Sequence Capture Enabled`。让 Repo A 在 episode 开始/结束时通过 step-ack
可选控制消息启动和停止深度采集：

```bash
python -m testbed.cli.record_teleop \
  --config testbed/configs/teleop_v1.yaml \
  --num-episodes 1 \
  --input keyboard \
  --operator-id zhaoshuai \
  --session-id graph_smoke_001 \
  --notes "first synchronized depth graph smoke recording" \
  --output-dir data/agx_teleop_graph_smoke_001 \
  --depth-capture \
  --depth-capture-hz 1 \
  --depth-capture-output-dir /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/DepthCameraSnapshots/graph_smoke_001
```

这条命令会在每个 episode `reset()` 后发送
`DEPTH_CAPTURE_START_REQ`，并在 episode 保存/丢弃前发送
`DEPTH_CAPTURE_STOP_REQ`。Unity 侧导出的 `episode_index` 使用实际 HDF5 episode
编号，`step_id` 从 `0` 开始。

## YAML 样例

```yaml
# graph_attach_smoke_v1.yaml
defaults:
  snapshot_root: /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/DepthCameraSnapshots
episodes:
  - episode_index: 0
    snapshots:
      - step_id: 0
        snapshot: depth_camera_20260601_140012_frame000.json
      - step_id: 5
        snapshot: depth_camera_20260601_140012_frame005.json
      - step_id: 10
        snapshot: depth_camera_20260601_140012_frame010.json
```

## 自动生成 Snapshot Map

录制完成后，可从 Repo B 的 `DepthCameraSnapshots/` 自动生成
`graph_attach_*.yaml`：

```bash
python -m testbed.cli.build_graph_snapshot_map \
  --graph-session graph_smoke_003
```

会自动读取：

```text
/home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/output/DepthCameraSnapshots/graph_smoke_003
```

并输出：

```text
data/graph_sessions/graph_smoke_003/graph_attach.yaml
```

完整手动形式仍然可用：

```bash
python -m testbed.cli.build_graph_snapshot_map \
  --snapshot-root /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/DepthCameraSnapshots \
  --session-id graph_smoke_001 \
  --output graph_attach_graph_smoke_001.yaml
```

该命令优先读取 JSON metadata 中的 `episode_index`、`step_id`、
`session_id`、`sequence_index`。如果 metadata 中有 `wall_time_unix_ns`，
会写入 snapshot map 的 `timestamp_ns`；如果只有 `wall_time_utc`，会解析成
纳秒时间戳后写入 `timestamp_ns`。如果旧快照缺少 episode/step metadata，
则回退解析文件名中的 `epXXXXXX` 和 `stepXXXXXX`。生成的 YAML 可直接传给
`tb-build-graph-dataset --snapshot-map`。

旧的手动单帧快照如果既没有 metadata，也没有 `epXXXXXX/stepXXXXXX` 文件名，
不会被自动写入 snapshot map，因为脚本无法知道它对应 teleop 的哪一个 step。

## CLI 命令

推荐的时间戳合并简写：

```bash
python -m testbed.cli.build_graph_dataset \
  --graph-session graph_smoke_003 \
  --align-mode nearest \
  --max-nodes 256 \
  --max-edges 1024
```

会自动使用：

```text
teleop-dir:    data/graph_sessions/graph_smoke_003/teleop
snapshot-map:  data/graph_sessions/graph_smoke_003/graph_attach.yaml
output-dir:    data/graph_sessions/graph_smoke_003/graph_time_v1
align-domain:  time
```

完整手动形式仍然可用：

```bash
tb-build-graph-dataset \
  --teleop-dir   data/agx_teleop_graph_smoke_v1 \
  --snapshot-map graph_attach_smoke_v1.yaml \
  --output-dir   data/agx_teleop_graph_smoke_v1_graph_v1 \
  --roi-u-min 0.23 --roi-u-max 0.70 \
  --roi-v-min 0.22 --roi-v-max 0.70 \
  --gradient-node-ratio 0.7 \
  --max-nodes 256 --max-edges 1024 \
  --knn-k 4 \
  --graph-rate-hz 10 \
  --control-hz 50 \
  --align-domain auto \
  --align-mode previous
```

`--align-domain auto` 是默认值：当 teleop HDF5 有 `step_ns` 且 snapshot map
中每个快照都有 `timestamp_ns` 时，自动按时间戳对齐；否则回退到 `step_id`
对齐。正式采集和真机数据建议显式使用：

```bash
tb-build-graph-dataset \
  --teleop-dir   data/agx_teleop_graph_smoke_001 \
  --snapshot-map graph_attach_graph_smoke_001.yaml \
  --output-dir   data/agx_teleop_graph_smoke_001_graph_time_v1 \
  --align-domain time \
  --align-mode nearest \
  --max-nodes 256 --max-edges 1024
```

时间戳合并后的 `/observations/graph` 会额外包含：

- `source_time_ns`：当前 timestep 采用的 depth snapshot 时间戳。
- `alignment_delta_ns`：当前 teleop `step_ns - source_time_ns`。
- `source_step_id`：同一个 snapshot 的估算 step id，保留用于调试。
- `is_fresh`：本 timestep 是否切换到了新的 graph keyframe。

如果已经每个 timestep 都保存了 depth frame，可以改用：

```bash
tb-build-graph-dataset \
  --teleop-dir data/agx_teleop_graph_smoke_v1 \
  --snapshot-map graph_attach_smoke_v1.yaml \
  --output-dir data/agx_teleop_graph_smoke_v1_graph_every_step \
  --graph-every-step \
  --max-nodes 256 --max-edges 1024
```

## 验证步骤

```bash
python -c "from testbed.data.hdf5_io import read_episode; \
           ep = read_episode('data/agx_teleop_v1_graph_v1/episode_000000.hdf5', load_images=False); \
           print(sorted(ep.keys())); print(ep['observation_graph'].keys()); \
           print(ep['observation_graph']['source_step_id'][:10]); \
           print(ep['observation_graph']['is_fresh'][:10])"
```
