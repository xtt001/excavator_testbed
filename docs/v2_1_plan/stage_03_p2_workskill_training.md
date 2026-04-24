# Stage 03 — P2 Work-Skill Training

## Goal

把 ACT 的训练窗口正式切到 `qualified_dig_start -> dump_end`，先用现有 `agx_teleop_v1` 数据 bootstrap 出 Stage-3 work-skill 训练链。

## Status

- State: `bootstrap_validated`
- Priority: `ready_for_stage_04_input`

## Locked Decisions

- source dataset 固定为 `data/agx_teleop_v1`
- source dataset **只读**
- Stage 3 全程非破坏式，只输出 sibling 数据集：
  - `data/agx_teleop_v1_v2_1_relabeled/`
  - `data/agx_teleop_v1_v2_1_workskill/`
- `qvel` 路线负责 live smoke
- `gcact` 路线只做 held-out / offline 对照
- Stage 3 不做在线 goal injection
- Stage 3 live 默认增加一个 **bootstrap 起手**：
  - reset 到第一次 `qualified_dig_start` 之前先沿用 `ACT V1`
  - 一旦进入“已装料且已离开 dig area”的 handoff 区间，再切到 Stage-3 work-skill checkpoint

## Main Deliverables

- `tb-build-workskill-v2_1`
- `workskill_relabel` sibling 数据集
- `act_agx_v2_1_workskill_qvel.yaml`
- `act_agx_v2_1_workskill_gcact.yaml`
- `eval_agx_v2_1_stage3_workskill_qvel.yaml`
- `task.num_episodes <= 0` 自动发现训练样本

## Data Plan

### Bootstrap Source

- 输入来自 `data/agx_teleop_v1`
- 先通过：
  - `tb-label-v2_1 --dataset-dir data/agx_teleop_v1 --scenario-id s0_truck`
- 默认输出：
  - `data/agx_teleop_v1_v2_1_relabeled/`

### Workskill Output

- 再通过：
  - `tb-build-workskill-v2_1 --dataset-dir data/agx_teleop_v1_v2_1_relabeled`
- 默认输出：
  - `data/agx_teleop_v1_v2_1_workskill/`
- 每个 successful cycle 裁成一个新的 episode
- 裁剪窗口固定为：
  - `qualified_dig_start -> dump_end`

### Bootstrap Result

- 当前 bootstrap sibling 数据集已生成：
  - `30` 条 relabeled full episodes
  - `30` 条 cropped workskill episodes

## Model Input Plan

### Live Promotion Path

- `qpos + qvel`
- 训练配置：
  - `act_agx_v2_1_workskill_qvel.yaml`
- live smoke：
  - `eval_agx_v2_1_stage3_workskill_qvel.yaml`
- 该 live 配置当前默认包含：
  - `bootstrap_ckpt_path = runs/ckpts/agx_excavation_act_v1/policy_best.ckpt`
  - `bootstrap_low_dim_keys = [qpos]`
  - `bootstrap_end_mode = loaded_and_clear`
  - `bootstrap_end_min_bucket_mass_kg = 300`
  - `bootstrap_end_min_distance_to_dig_area_m = 0.25`
  - `work_ckpt_dir = runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50`

### Offline Comparison Path

- `qpos + qvel + goal_tokens`
- 训练配置：
  - `act_agx_v2_1_workskill_gcact.yaml`
- 本阶段只看 held-out validation，不进入 live hybrid

### Goal Tokens

- 固定采用 `10D sector-first`
- 继续走 proprio concat
- 本阶段不新增独立 goal encoder

## Runtime / Config Notes

- `task.num_episodes <= 0` 表示自动发现整个数据集的 `episode_*.hdf5`
- bootstrap 的 cropped workskill 默认 `task.episode_len = 760`
- 这个值来自实际 sibling 数据集；最初的 `720` 不够覆盖最长窗口

## Smoke Results

- `qvel` smoke 训练已完成：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_qvel`
  - best val loss: `40.9493`
- `gcact` smoke 训练已完成：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_gcact`
  - best val loss: `25.3733`
- `qvel` Stage-2 hybrid live smoke 已完成 1 条 rollout：
  - runtime 接入成功
  - 本次 smoke 只证明链路打通，不代表已优于 Stage 2 baseline
- `qvel e50` 训练已完成：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50`
  - best val loss: `0.6962`
- `gcact e50` 训练已完成：
  - `runs/ckpts/agx_excavation_act_v2_1_workskill_gcact_e50`
  - best val loss: `0.6463`
- `qvel e50 + loaded_and_clear bootstrap` live 结果：
  - 已通过单条真实 live `dump_complete_final_hold` success gate
  - 参考结果目录：
    - `runs/preview/stage3_workskill_qvel_e50_live`
  - 当前说明：
    - 第一次 work cycle 已可成功完成
    - 但 rollout 仍会在尝试进入下一轮时出现 transition timeout
    - 所以它已经满足 Stage 3 的 live smoke 目标，但还不是 Stage 2 multicycle 替代线
- `gcact e50 + bootstrap` 诊断结果：
  - return 高于 `qvel e50 + bootstrap`
  - 但当前更偏向“更长 loading”，还没有稳定接上有效 dump
  - 依旧不作为 Stage 3 正式 live 默认

## Tests

- `tb-build-workskill-v2_1` 单测
- `task.num_episodes = 0` 自动发现单测
- legacy terminal-success relabel 单测
- `qvel` / `gcact` smoke 训练
- `qvel` live Stage-2 hybrid smoke
- Stage-2 hybrid bootstrap 起手单测
- Stage 1 / Stage 2 / Repo A integration 回归

## Acceptance Criteria

- `agx_teleop_v1 -> v2_1_relabeled -> v2_1_workskill` 链路可运行
- 原始 `data/agx_teleop_v1/` 不被改写或删除
- `qvel` work-skill checkpoint 完成真实 smoke 训练并能接入 live hybrid smoke
- `gcact` 完成真实 smoke 训练并产出可比较的 held-out 结果
- `qvel e50 + loaded_and_clear bootstrap` 已在 live 上通过单轮 success gate

## Risks and Stop Conditions

- 如果后续正式 `teleop_v2_1_multi_raw` 数据分布和 bootstrap 差距过大，Stage 4 前需要重建正式 workskill 数据集
- 如果 live smoke 继续无法通过 Stage 2 门槛，先留在 Stage 3/Stage 2 交界处做 work-policy 回归，不直接推进 Stage 4
