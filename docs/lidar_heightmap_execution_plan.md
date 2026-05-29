# LiDAR Heightmap 执行计划

状态：2026-05-28 首版。

目标：按规范 ROS 2 流程推进，不在 Unity/AGX 内部读取 ground-truth 地形。Repo B 只发布 AGX 原生 `/lidar/pointcloud`，Repo A 将标准 `sensor_msgs/msg/PointCloud2` 转成 local heightmap / depth / elevation grid，供后续固定点轨迹规划、RRT* 和 RL 轨迹跟踪使用。

## 当前决策

- 停止继续扩展 TerrainGraph publisher。
- 不做 depth camera 主线。
- 不新增 `Physics.Raycast` 风格传感器。
- 不把 heightmap 写进旧 HDF5 schema 或 `STEP_RESP`。
- 不提前做 learned dig-point / 下铲点 planner。
- 先验证 `/lidar/pointcloud` 到可用 local heightmap 的链路。

## 已有实现

- `testbed/perception/lidar_heightmap.py`：纯 numpy 点云到 height/depth grid 转换器。
- `testbed/cli/lidar_heightmap.py`：`tb-lidar-heightmap` 离线/ROS 2 live CLI。
- `tests/test_lidar_heightmap.py`：转换器单元测试。
- `pyproject.toml`：`tb-lidar-heightmap` console script。

已通过：

```bash
python -m pytest tests/test_lidar_heightmap.py
python -m compileall -q testbed/perception testbed/cli/lidar_heightmap.py
```

离线 smoke 已通过：

```bash
python -m testbed.cli.lidar_heightmap \
  --input-npy /tmp/lidar_heightmap_points.npy \
  --output-dir /tmp/lidar_heightmap_cli_smoke \
  --resolution-m 1.0 \
  --x-min-m 0 \
  --x-max-m 2 \
  --z-min-m 0 \
  --z-max-m 1
```

## 阶段 0：Repo B / Unity LiDAR 完整接入

### Pre-condition

- 使用 Unity 2022.3.62f3 打开 Repo B：

```text
/home/zhaoshuai/workspace_uinty/GraphPerceptionPrj
```

- 打开目标场景：

```text
Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity
```

- ROS 2 Jazzy 已安装：

```bash
source /opt/ros/jazzy/setup.zsh
ros2 topic list
```

### Action

在 Unity Editor 中完成，不手动编辑 `.unity` 文本：

1. 确认场景中存在 `SensorEnvironment`。
   - 如果没有，在场景根节点新建 `SensorEnvironment` GameObject。
   - Add Component：AGX Sensor Environment 相关组件。

2. 新建或选中 LiDAR GameObject。
   - 推荐命名：`DigAreaLidar`。
   - 推荐挂在挖掘机驾驶舱或上车体附近，先保证视野覆盖挖掘区域。
   - 暂时不要把它放在铲斗上，避免随铲斗剧烈运动导致点云难以调参。

3. 在 `DigAreaLidar` 上添加 AGX 原生 LiDAR 组件。
   - Add Component：`Lidar Sensor`。
   - 初始建议：

```text
Lidar Model Preset: Ouster OS1 或可用默认模型
Channel Count: 32
Lidar Mode: 512x20 或默认可运行模式
Lidar Range Min: 0.1
Lidar Range Max: 40
Remove Ray Misses: true
```

4. 在同一 GameObject 上添加 AGX ROS 2 publisher。
   - Add Component：`Lidar ROS2 Publisher`。
   - 初始建议：

```text
PCL24 Topic: /lidar/pointcloud
PCL48 Topic: /lidar/pointcloud_ex
Frame ID: world
Publish PCL24: true
Publish PCL48: true 或 false 均可，当前 heightmap 先用 PCL24
Publish Instance Id: false
```

5. 旧组件处理。
   - `LIDAR Snapshot Exporter` 可暂时禁用，避免混淆旧 Raycast/JSON 路线。
   - `DigAreaDepthCamera` 的 Camera 组件可暂时禁用，避免 Game 视图被它抢占。
   - 不删除旧对象，不批量重命名。

6. 进入 Play 模式。

### Acceptance

终端中能看到 topic：

```bash
source /opt/ros/jazzy/setup.zsh
ros2 topic list | grep lidar
```

期望至少看到：

```text
/lidar/pointcloud
```

确认频率：

```bash
ros2 topic hz /lidar/pointcloud
```

期望：

- topic 持续发布。
- 平均频率稳定。
- 不要求固定 50 Hz，但不能只发一帧。

确认数据非空：

```bash
ros2 topic echo /lidar/pointcloud --once
```

期望：

- `height` / `width` 非零。
- `data` 非空。

RViz 可视化：

```bash
rviz2
```

RViz 设置：

```text
Fixed Frame: world
Add -> PointCloud2
Topic: /lidar/pointcloud
Reliability Policy: Best Effort
Style: Flat Squares
Size: 0.01 或 0.02
Color Transformer: Intensity 或 XYZ
```

期望：

- 能看到点云。
- 控制挖掘机或移动铲斗时，点云实时变化。
- 点云覆盖挖掘区域或至少覆盖地面/台阶/挖掘机附近。

### STOP 条件

- `/lidar/pointcloud` 不出现：先检查 `LidarROS2Publisher` 是否启用、AGX ROS 2 license/module、Unity Console 是否报错。
- topic 出现但 `data` 为空：检查 Lidar range、SensorEnvironment、地形/物体是否能被 LiDAR 命中。
- RViz warning `RELIABILITY_QOS_POLICY`：把 PointCloud2 的 Reliability Policy 改为 `Best Effort`。
- RViz 看不到点云但 `echo --once` 有数据：先查 Fixed Frame 是否是 `world`，不要改代码。
- Game 视角不是 Main Camera：禁用 `DigAreaDepthCamera` 的 Camera 组件或调低 depth，不要删除对象。
- 任何需要改 `.unity` / `.prefab` / `.asset` 文本的操作：停止，改由 Unity Editor 保存。

## 阶段 1：live heightmap 验证

### Pre-condition

- 阶段 0 已通过。
- Unity Play 模式正在运行。
- Repo B 的 AGX 原生 Lidar 正在发布非空 `/lidar/pointcloud`。
- RViz 能看到 `/lidar/pointcloud` 点云。
- 当前 shell 是 zsh 时，使用 ROS 2 的 zsh setup：

```bash
source /opt/ros/jazzy/setup.zsh
```

- live ROS 2 Python 使用系统 Python，不使用 conda `python`：

```bash
/usr/bin/python3 -c "import rclpy, sensor_msgs_py; print('ok')"
```

### Action

在 Repo A 根目录执行：

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed
source /opt/ros/jazzy/setup.zsh

PYTHONPATH=$PWD /usr/bin/python3 -m testbed.cli.lidar_heightmap \
  --topic /lidar/pointcloud \
  --output-dir runs/lidar_heightmap/live_preview \
  --max-frames 10 \
  --png
```

### Acceptance

- 终端输出包含：

```text
Wrote .../heightmap_000000.npz points=<N> valid_cells=<M>
```

- `points > 0`。
- `valid_cells > 0`。
- 输出目录出现：

```text
runs/lidar_heightmap/live_preview/heightmap_000000.npz
runs/lidar_heightmap/live_preview/heightmap_000000_depth.png
```

- `*_depth.png` 能看到局部地形结构，不是全空、全黑或只有少量噪点。

### STOP 条件

- `rclpy` 或 `sensor_msgs_py` import 失败：确认是否用了 `/usr/bin/python3`，不要先改代码。
- `points = 0`：先回到 Unity/RViz 检查 Lidar topic。
- `points > 0` 但 `valid_cells = 0`：RoI 坐标范围不对，进入阶段 2 调参。
- PNG 全空或只有离散噪点：先调 RoI、分辨率、高度过滤，不进入轨迹规划。

## 阶段 2：RoI / 坐标系 / 分辨率调参

### Pre-condition

- 阶段 1 能生成 `.npz` 和 PNG。
- 至少保存 10 帧 live heightmap。

### Action

先扩大 RoI：

```bash
PYTHONPATH=$PWD /usr/bin/python3 -m testbed.cli.lidar_heightmap \
  --topic /lidar/pointcloud \
  --output-dir runs/lidar_heightmap/roi_probe \
  --max-frames 10 \
  --png \
  --resolution-m 0.05 \
  --x-min-m -8 \
  --x-max-m 8 \
  --z-min-m -8 \
  --z-max-m 8
```

如果 grid 太稀疏，改粗：

```bash
--resolution-m 0.10
```

如果大量无关高点或机械臂遮挡影响地形图，再尝试高度过滤：

```bash
--min-height-m <value> --max-height-m <value>
```

### Acceptance

- 找到一组默认参数：RoI、resolution、高度过滤、reference height 策略。
- PNG 中能稳定看到挖掘区域、台阶/坡面和铲斗附近变化。
- 控制挖掘机或铲斗运动后，连续帧的 height/depth grid 有可解释变化。
- 将最终参数回写到 README 或后续配置文件。

### STOP 条件

- 坐标轴明显反了或平移不对：先记录 Unity/RViz frame 信息，不在算法里硬猜。
- Lidar 看不到地形：检查 AGX `LidarSurfaceMaterial`、SensorEnvironment、Lidar range。
- 铲斗遮挡严重：先记录问题，必要时增加 crop/filter 策略，不进入 RRT*。

## 阶段 3：固定落铲点 / 卸料点

### Pre-condition

- 阶段 2 输出稳定。
- heightmap 坐标系和 Unity/RViz 视觉对应关系已确认。

### Action

- 在 Repo A 增加一个小配置，先手工指定：

```yaml
fixed_dig_point: [x, y, z]
fixed_dump_point: [x, y, z]
```

- 把固定点投影到 heightmap 坐标系。
- 在 Python/RViz 中可视化固定点和 heightmap。

### Acceptance

- 固定落铲点和卸料点能在 heightmap 可视化中显示。
- 点的位置与 Unity/RViz 中的场景位置一致。
- 固定点配置可复现，不依赖手动点击临时状态。

### STOP 条件

- 固定点在 heightmap 中对不上场景：先修 frame/坐标变换。
- 固定点无法稳定落在 RoI 内：先调整 RoI，不做 planner。

## 阶段 4：RRT* 参考轨迹

### Pre-condition

- 固定落铲点、卸料点已稳定。
- heightmap 可作为障碍/地形约束输入。

### Action

- 在 Repo A 增加轨迹规划模块。
- 先规划铲斗末端参考路径，不直接训练策略。
- 路径输出至少包含：

```text
time/index, bucket_x, bucket_y, bucket_z
```

- 可视化轨迹与 heightmap。

### Acceptance

- RRT* 或等价规划器能生成非空轨迹。
- 轨迹起点接近固定落铲点，终点接近固定卸料点。
- 轨迹不穿过明确障碍或不可行区域。

### STOP 条件

- 规划空间定义不清：先决定用铲斗笛卡尔空间、关节空间还是混合空间。
- 轨迹无法映射到当前 4D 动作表面：先补运动学接口，不训练 RL。

## 阶段 5：RL 轨迹跟踪控制器

### Pre-condition

- 阶段 4 能生成可视化参考轨迹。
- 现有 step-ack TCP 仍可控制 `[swing, boom, stick, bucket]` 速度命令。

### Action

- 训练低层控制器，使铲斗跟踪参考轨迹。
- 初期 observation 可包含 `qpos`、`qvel`、当前参考点、轨迹误差。
- action 仍保持当前 4D 速度命令。

### Acceptance

- 仿真中铲斗能沿参考轨迹运动。
- 轨迹误差有可记录日志。
- 固定点挖掘-卸料闭环能跑起来。

### STOP 条件

- 不要声称训练成功率或性能数字，除非 Repo A 有可复现实验日志。
- 如果跟踪失败，先分解为运动学、控制频率、动作符号、奖励设计问题，不直接改感知输入。

## 阶段 6：回到下铲点 planner

### Pre-condition

- heightmap 稳定。
- 固定点 RRT* 轨迹可规划。
- RL 控制器能跟踪参考轨迹。

### Action

- 再实现 dig-point / 下铲点 planner。
- planner 输入使用稳定的 heightmap，不使用 Unity ground-truth。
- 输出替换阶段 3 的 `fixed_dig_point`。

### Acceptance

- planner 输出的落铲点能进入同一条 RRT* + RL 跟踪链路。
- 替换固定点后，系统仍能跑完整闭环。

### STOP 条件

- 固定点闭环不稳定时，不启动 learned dig-point planner。
- 如果 planner 输出不可解释，先做可视化和离线评估，不直接接 live 控制。

## 当前下一步

先执行阶段 0，确认 Unity/AGX 原生 LiDAR 完整接入。阶段 0 通过后，再执行阶段 1 live heightmap 验证，并保存 `runs/lidar_heightmap/live_preview` 下的 `.npz` 和 `*_depth.png`。根据 PNG 结果再决定阶段 2 的 RoI 和 resolution。
