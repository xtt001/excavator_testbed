# ACT on AGX 挖机任务 Checklist

## 2026-03-26 当前状态快照

这份清单现在还没有“全部做完”，但当前阶段已经不再卡在基础 plumbing。

今天这轮之后，已经明确完成并验证的内容是：

- `record -> qc -> train -> eval` 最小闭环已经跑通
- frozen split、`resolved_config`、`run_metadata` 已落地
- eval 逐 timestep rollout logs 已落地
- dataset QC 已落地
- demo-level metadata 已落地

当前更准确的阶段判断是：

- 还不能说 baseline ACT 已经有性能结论
- 但可以说：外围实验管理层已经足够支撑第一轮正式 baseline 和失效归因

因此这份计划接下来应该把重点放在：

- 录制更正式、更紧凑的 demo 数据
- 补新数据上的 replay QA
- 用正式数据跑第一轮真正的 baseline
- 再根据 rollout logs 判断失败更像数据问题、任务问题，还是模型问题

## A. 先明确本阶段目标

### 本阶段唯一目标

- 验证 baseline ACT 是否能在 AGX 挖机任务上学会 in-distribution 模仿
- 暂时不追求泛化
- 暂时不急着魔改模型
- 先回答：它能不能学会“挖土 → 旋转 → 倒土”

### 本阶段输出物

- 一版固定的最小任务定义
- 一批可用 demo 数据
- 一次完整训练结果
- 一组 rollout 视频
- 一页失败模式总结

---

## B. ACT 理解与代码阅读

目标：先理解到“能指导实验”的程度，不求全懂。

### 1. 论文层面

- 看 ACT 论文摘要、方法图、实验设置
- 明确 ACT 的核心思想：action chunking
- 明确它为什么比单步 BC 更适合机器人动作生成
- 明确它的潜在问题：open-loop chunk 导致误差累积

### 2. 代码层面，优先看这四块

#### 数据

- demo 数据是怎么存的
- observation 包含哪些内容
- action 是什么格式
- episode 怎么切成训练样本
- chunk size / horizon 在哪里定义

#### 模型

- 模型输入 tensor shape 是什么
- 模型输出 tensor shape 是什么
- Transformer / CVAE / decoder 的主链路是什么
- 哪一部分决定了一次输出多个动作

#### loss

- loss 由哪些项组成
- action loss 是 L1 / L2 / 其他
- 有没有 KL loss
- loss 权重在哪里设

#### rollout / eval

- rollout 时是每步都推理还是每隔几步推理一次
- 预测出的 chunk 怎么执行
- 是否有 temporal aggregation
- action 是如何发送给环境的

### 3. 代码阅读输出

- 画一张你自己的流程图：`demo -> dataloader -> model -> loss -> checkpoint -> rollout`
- 写一个简短笔记，说明 ACT 在你们代码里到底是怎么工作的

---

## C. 定义 AGX 上的最小任务

目标：先让任务变成“可学”，而不是“真实且复杂”。

### 1. 最小任务版本

- 固定挖机初始位姿
- 固定土堆位置
- 固定倒土目标区域
- 固定 camera / observation 配置
- 暂时尽量少随机性
- 暂时不加 domain randomization
- 暂时不改输入输出维度

### 2. 动作定义确认

- 明确 action space 是哪些控制量
- 明确动作频率
- 明确是否需要 action clipping / smoothing
- 明确 rollout 时动作执行接口是否稳定

### 3. observation 定义确认

- 当前 baseline 用什么输入
- 是否先只用低维状态
- 如果用视觉，先确认视觉流是否稳定
- 明确 observation 在 train / eval 中完全一致

### 4. 任务成功标准

至少写清楚下面几个：

- 什么叫“挖到土”
- 什么叫“旋转完成”
- 什么叫“倒到目标区域”
- 什么叫整个 episode 成功

---

## D. 数据采集准备

目标：先拿到一批高质量、低难度、可复现 demo。

### 1. 录制前检查

- teleop 控制正常
- 环境 reset 稳定
- 数据记录无丢帧/错位
- observation、action、timestamp 都能正确保存
- 每个 episode 能唯一标识
- 能保存 rollout video 或回放

### 2. demo 采集原则

- 先求质量，不求数量
- 操作流程尽量一致
- 每条 demo 都尽量完整成功
- 避免明显犹豫、停顿、误操作
- episode 长度不要差异过大
- 先采固定场景下的数据

### 3. 第一批 demo 目标

- 先拿到一小批可用 demo（例如 10–30 条量级）
- 每条都人工回看一遍
- 标记成功 / 失败 demo
- 失败 demo 暂时单独放，不混入 baseline 训练

### 4. 数据质检

- action 曲线是否有异常尖峰
- observation 是否缺失
- episode 是否中途终止
- 是否存在明显不同风格的数据混杂
- 数据长度分布是否合理

---

## E. 训练前固定 baseline 配置

目标：先有一个“干净 baseline”。

### 1. 固定实验配置

- 固定 seed
- 固定 train / val split
- 固定 observation 配置
- 固定 action 配置
- 固定 chunk size
- 固定 batch size
- 固定训练轮数 / steps
- 固定学习率和 optimizer

### 2. 记录配置

- 所有超参写进 config 文件
- 训练命令可复现
- 输出目录规范命名
- 保存 git commit / 代码版本信息

### 3. 训练日志

- 记录 train loss
- 记录 val loss
- 定期保存 checkpoint
- 保存训练配置快照
- 记录异常/报错信息

---

## F. 首次 baseline 训练

目标：先跑通一次完整 train。

### 训练时重点关注

- loss 是否正常下降
- 是否出现 nan / 爆炸
- train 和 val 是否严重背离
- checkpoint 是否正常保存
- 数据加载是否稳定
- 训练速度是否合理

### 训练结束后必须保存

- best checkpoint
- last checkpoint
- train/val 曲线
- config 文件
- 训练日志

---

## G. Rollout Evaluation

目标：以 rollout 为主，不以 loss 为主。

### 1. eval 设置

- 固定 eval 场景
- 固定初始条件
- 暂时只测 in-distribution
- 每个 checkpoint 至少 rollout 多次
- 保存每次 rollout 视频

### 2. 必看指标

- 总 success rate
- 挖土阶段成功率
- 旋转阶段成功率
- 倒土阶段成功率
- 平均 episode 长度
- 是否存在明显动作抖动
- 是否存在提前崩溃

### 3. 视频回看时重点看

- 是不是一开始就偏
- 能不能正确进入土堆
- 能不能把土带起来
- 旋转是否平稳
- 倒土是否对准目标
- 后半段是否因为误差累积崩掉

---

## H. Failure Analysis

目标：第一轮不要急着改模型，先弄清楚它怎么失败。

### 失败分类表

给每个 rollout 贴标签：

- 类型 1：挖土失败
- 类型 2：挖到了但没带起
- 类型 3：旋转中轨迹偏掉
- 类型 4：能旋转但倒土失败
- 类型 5：前面正常，后面误差累积崩掉
- 类型 6：整体动作抖动严重
- 类型 7：训练 loss 低但 rollout 不行

### 分析输出

- 统计最常见失败类型
- 判断失败更像是数据问题、表示问题，还是 chunk/open-loop 问题
- 总结一句话：baseline ACT 在当前任务上的主要失败机制是什么

---

## I. 决定下一步研究方向

只有做完上面几步，才进入“魔改”。

### 如果 baseline 根本学不会

优先排查：

- 任务是不是太难
- demo 质量是否不够
- observation / action 定义是否不合理
- rollout 接口是否有问题
- 训练配置是否不合适

### 如果 baseline 能学会，但后半段容易崩

考虑方向：

- 缩短 chunk
- 更频繁 replanning
- temporal aggregation 改法
- feedback-aware 执行

### 如果 baseline 能学前半段，跨阶段差

考虑方向：

- phase-conditioned ACT
- phase token
- 分层策略 / 子任务结构

### 如果 baseline loss 好但 rollout 差

考虑方向：

- covariate shift
- corrective demos
- 数据增强
- closed-loop 修正机制

### 如果动作很抖

考虑方向：

- action smoothing
- 数据清洗
- 重采样
- 更稳的动作表示

---

## 今日-后天超短版执行计划

### 今天

- 把 ACT 论文快速过一遍
- 找到代码里的数据、模型、loss、rollout 四条主链路
- 和同事确认 AGX 任务的 observation/action 定义
- 定义最小任务版本和 success 标准

### 明天

- 开始录第一批 demo
- 做 demo 质检
- 固定 baseline config
- 跑第一次训练

### 后天

- rollout eval
- 看视频
- 做失败分类
- 写出 baseline 结论：能不能学会，失败在哪

