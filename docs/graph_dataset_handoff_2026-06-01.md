# Graph Dataset Pipeline — Handoff for Codex

**Date**: 2026-06-01
**Repo**: `excavator_testbed` (Repo A)
**Branch**: current working branch (no auto commits)
**Audience**: Codex agent picking up this task; reviewed by `zhaoshuai`

---

## 0. Mission for Codex

Decouple **teleop data collection** from **graph-observation construction**.
Add a new post-processing CLI `tb-build-graph-dataset` that takes an existing
teleop dataset (HDF5, no graph) plus a snapshot map (YAML) and emits a parallel
dataset directory whose HDF5 episodes contain `/observations/graph`.

The original teleop dataset is **never modified**. Old training configs that do
not consume `/observations/graph` continue to work against either dataset. New
configs (out of scope for this task) can consume the graph variant for ACT +
GNN experiments.

**Scope constraint**: this task is **add-only** to the source tree below.
Do NOT modify:

- `testbed/perception/depth_graph.py`
- `testbed/cli/depth_graph.py`
- `testbed/cli/record_teleop.py`
- `testbed/data/hdf5_io.py`

These are contract surfaces. All new work goes into new files plus tightly
scoped edits to `pyproject.toml` and the table row in `README.md`.

---

## 1. Current Progress Snapshot

### Completed

| Gate | Item | Where |
|---|---|---|
| 1 | `depth_frame_to_graph(depth, config, intrinsics)` baseline | `testbed/perception/depth_graph.py` |
| 1 | `tb-depth-graph` / `tb-depth-graph-preview` CLIs | `testbed/cli/depth_graph.py`, `depth_graph_preview.py` |
| 1 | `write_episode(observation_graph=...)` accepts optional graph dict | `testbed/data/hdf5_io.py` |
| 2 | Unity exporter writes `fx_px / fy_px / cx_px / cy_px` in metadata | Repo B `DepthCameraSnapshotExporter.cs` |
| 2 | `DepthCameraIntrinsics.from_metadata(meta)` classmethod | `testbed/perception/depth_graph.py` |
| 2 | CLI auto-injects intrinsics + emits `intrinsics_used: bool` in stdout | `testbed/cli/depth_graph.py` |
| 3 | ROI semantics fixed: crop-then-graph (removes median-fill boundary artifact) | `testbed/perception/depth_graph.py` |
| 3 | `_roi_pixel_bounds` helper replaces `_roi_pixel_mask` (deleted) | same file |
| Tests | 27 targeted tests green (run command below) | `tests/test_depth_graph*.py` etc. |

### Verified baseline tuning (from human preview review)

```text
--roi-u-min 0.23 --roi-u-max 0.70
--roi-v-min 0.22 --roi-v-max 0.70
--gradient-node-ratio 0.7
--max-nodes 256 --max-edges 1024
--knn-k 4
```

These are **defaults** that the new CLI should adopt unless overridden.

### Known gap (this task closes it)

- `tb-record-teleop` does **not** write `/observations/graph` (zero references).
- No batch script to attach graph to existing episodes exists.

---

## 2. Target Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Single source of truth: raw teleop (backward compatible)    │
│                                                             │
│  Unity teleop, press "8" once at start of each episode      │
│       │                                                     │
│       ├─ teleop stream ──→ tb-record-teleop (UNCHANGED)     │
│       │                       └→ data/agx_teleop_<sess>/    │
│       │                            episode_*.hdf5 (NO graph)│
│       │                                                     │
│       └─ one depth frame → DepthCameraSnapshots/            │
│                              depth_camera_<ts>_frame*.json  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ Post-processing (cheap, repeatable, swappable)
┌─────────────────────────────────────────────────────────────┐
│ Graph variant outputs                                       │
│                                                             │
│  tb-build-graph-dataset                                     │
│   --teleop-dir   data/agx_teleop_<sess>                     │
│   --snapshot-map graph_attach_<sess>.yaml                   │
│   --output-dir   data/agx_teleop_<sess>_graph_v1            │
│   --max-nodes 256 --gradient-node-ratio 0.7 ...             │
│                                                             │
│  → copies each episode_*.hdf5,                              │
│    injects /observations/graph (broadcast across all T)     │
│  → same teleop can spawn graph_v1, graph_v2, ...            │
└─────────────────────────────────────────────────────────────┘
                          │
   ┌──────────────────────┴──────────────────────┐
   │                                             │
[baseline train]                         [with-graph train]
ACT(qpos) on agx_teleop_<sess>          ACT(qpos+graph) on _graph_v1
(existing yaml, unchanged)              (future yaml, NOT in scope)
```

**Architectural invariants** (codex must preserve):

- Raw teleop episode files are immutable after collection.
- Graph attachment is a pure function `(episode_hdf5, snapshot_json, cfg) → new_hdf5`.
- HDF5 schema for `/observations/graph` does not change (node_features still
  `[T, max_nodes, 8]`, edge_features still `[T, max_edges, 5]`,
  `graph_globals` still `[T, 6]`).
- Same snapshot broadcast across all T timesteps for now; per-timestep snapshot
  mapping is a future extension and must not require schema changes.

---

## 3. Task List (execute in order)

### Task 0 — Pre-flight verification

Do not start until this passes:

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed
python -m pytest tests/test_depth_graph.py tests/test_depth_graph_cli.py \
  tests/test_depth_graph_preview_cli.py tests/test_observation_graph_hdf5.py \
  tests/test_lidar_heightmap.py -q
```

Expected: `27 passed`. If anything is red, STOP and report — the architecture
change should not begin on a broken baseline.

### Task 1 — New CLI: `tb-build-graph-dataset`

Create `testbed/cli/build_graph_dataset.py`.

#### 1.1 Module docstring (verbatim)

```python
"""Attach depth-derived graph observations to existing teleop episodes.

Reads a teleop dataset directory (containing episode_*.hdf5 with no graph
group) plus a YAML "snapshot map" pairing episode index → snapshot JSON.
For each episode, builds the graph once via depth_frame_to_graph and
broadcasts it across the episode's full T timesteps, then writes a new
HDF5 copy to --output-dir with /observations/graph populated.

The original teleop directory is never modified. Old training configs that
do not consume /observations/graph continue to work against either dataset.
"""
```

#### 1.2 CLI arguments

| Argument | Type | Required | Default | Notes |
|---|---|---|---|---|
| `--teleop-dir` | `Path` | yes | — | Existing `data/agx_teleop_*/` |
| `--snapshot-map` | `Path` | yes | — | YAML, schema below |
| `--output-dir` | `Path` | yes | — | Created; must not be the same as `--teleop-dir` |
| `--max-nodes` | `int` | no | `256` | |
| `--max-edges` | `int` | no | `1024` | |
| `--knn-k` | `int` | no | `4` | |
| `--gradient-node-ratio` | `float` | no | `0.7` | |
| `--roi-u-min` / `--roi-u-max` | `float` | no | `None` | Pass through to `DepthGraphConfig` |
| `--roi-v-min` / `--roi-v-max` | `float` | no | `None` | |
| `--min-depth` | `float` | no | `None` | Defaults to snapshot `metadata.near_m` |
| `--max-depth` | `float` | no | `None` | Defaults to snapshot `metadata.far_m` |
| `--dry-run` | flag | no | `False` | Print plan, write nothing |

Refuse to run if `--output-dir == --teleop-dir`. Refuse to run if
`--output-dir` already contains `episode_*.hdf5` unless `--dry-run`.

#### 1.3 Snapshot map YAML schema

```yaml
# graph_attach_<sess>.yaml
defaults:
  snapshot_root: DepthCameraSnapshots    # optional, base for relative snapshot paths
episodes:
  - episode_index: 0
    snapshot: depth_camera_20260601_140012_frame123.json
  - episode_index: 1
    snapshot: /abs/path/depth_camera_20260601_140235_frame456.json
  # ...
```

Rules:

- Absolute `snapshot` paths bypass `defaults.snapshot_root`.
- Missing episode in map → skip with a warning to stderr (not an error).
- `episode_index` referenced but `episode_{idx:06d}.hdf5` not in `--teleop-dir`
  → non-zero exit with friendly message naming the missing file.
- Duplicate `episode_index` → non-zero exit before any write.

#### 1.4 Core logic (reference implementation)

```python
for entry in episodes:
    src = teleop_dir / f"episode_{entry['episode_index']:06d}.hdf5"
    dst = output_dir / src.name

    ep = read_episode(src, load_images=True)
    T = ep["qpos"].shape[0]

    snapshot = json.loads(snapshot_path.read_text())
    meta = snapshot["metadata"]
    depth = np.asarray(snapshot["depth_m"], dtype=np.float32).reshape(
        int(meta["height"]), int(meta["width"]))

    config = DepthGraphConfig(
        max_nodes=args.max_nodes,
        knn_k=args.knn_k,
        max_edges=args.max_edges,
        gradient_node_ratio=args.gradient_node_ratio,
        min_depth_m=(args.min_depth
                     if args.min_depth is not None
                     else float(meta.get("near_m", 0.001))),
        max_depth_m=(args.max_depth
                     if args.max_depth is not None
                     else float(meta["far_m"]) if "far_m" in meta else None),
        roi_u_min=args.roi_u_min,
        roi_u_max=args.roi_u_max,
        roi_v_min=args.roi_v_min,
        roi_v_max=args.roi_v_max,
    )
    intrinsics = DepthCameraIntrinsics.from_metadata(meta)
    graph = depth_frame_to_graph(depth, config, intrinsics)

    observation_graph = _broadcast_graph_to_episode(graph, T)
    _write_with_passthrough(dst, ep, observation_graph)
```

Helper `_broadcast_graph_to_episode(graph, T)`:

- Returns a `dict[str, np.ndarray]` with leading T dim, matching the keys
  that `write_episode` already accepts (see `hdf5_io.py:60`).
- Use `np.broadcast_to(...).copy()` to materialise (HDF5 needs contiguous
  arrays); dtypes per existing `DepthGraphResult.as_observation_graph()`.

Helper `_write_with_passthrough(dst, ep, observation_graph)`:

- Inspect `write_episode`'s signature; pass through every parameter
  preserved in `ep` (qpos, qvel, actions, images, plus any metadata fields
  the existing `read_episode` surfaces).
- Codex MUST grep `write_episode` first and mirror its parameter list,
  rather than hardcoding a subset, to keep teleop metadata (operator_id,
  session_id, notes, stage labels, reward, etc.) intact.

#### 1.5 stdout summary

One JSON object per processed episode, plus a final aggregate:

```json
{"episode_index": 0, "src": "data/agx_teleop_v1/episode_000000.hdf5",
 "dst": "data/agx_teleop_v1_graph_v1/episode_000000.hdf5", "T": 300,
 "node_count": 256, "edge_count": 1024, "intrinsics_used": true,
 "snapshot": "depth_camera_20260601_140012_frame123.json"}
{"aggregate": true, "episodes_processed": 10, "episodes_skipped": 0}
```

`--dry-run` emits the same per-episode JSON with an extra `"dry_run": true`
field and no `dst` file created.

#### 1.6 `pyproject.toml`

Register the entry point alongside the existing `tb-depth-graph`:

```toml
tb-build-graph-dataset = "testbed.cli.build_graph_dataset:main"
```

Keep alphabetical / grouped formatting consistent with neighbouring entries.

### Task 2 — Tests

Create `tests/test_build_graph_dataset.py`. Minimum three cases:

1. **End-to-end smoke**
   - Build a fake `teleop_dir` with one `episode_000000.hdf5` (T = 4) using
     `write_episode(...)` directly.
   - Build a fake snapshot.json (3×3 depth, fx=fy=2, cx=cy=1) inside
     `tmp_path / "snapshots"`.
   - Build a YAML mapping episode 0 → that snapshot.
   - Invoke the CLI via `subprocess.run([sys.executable, "-m",
     "testbed.cli.build_graph_dataset", ...], check=True)`.
   - Assert:
     - Output HDF5 exists and `read_episode(...)["observation_graph"]` is
       not None.
     - `node_features.shape == (4, max_nodes, 8)`.
     - All T frames identical: `np.array_equal(node_features[0], node_features[t])`
       for every t.
     - Last stdout line contains `"aggregate": true` and
       `"episodes_processed": 1`.
     - Per-episode line contains `"intrinsics_used": true`.

2. **`--dry-run`**
   - Same inputs as case 1.
   - Assert: output directory has no `episode_*.hdf5`. Per-episode stdout
     line contains `"dry_run": true`.

3. **Missing episode → friendly error**
   - YAML references `episode_index: 5` but no such file in teleop_dir.
   - Assert: non-zero exit, stderr mentions `episode_000005.hdf5`.

Test file MUST import only from public modules (`testbed.perception`,
`testbed.data`, `testbed.cli.build_graph_dataset` only via subprocess).

### Task 3 — README update

In `README.md`, append a new row to the existing capabilities table
immediately after the `depth graph converter` row at line ~52:

```markdown
| graph dataset attach | 新增 | `tb-build-graph-dataset` 把一张 snapshot 的 graph broadcast 注入到现有 `episode_*.hdf5`，产出 `<dataset>_graph_v1/`；原 teleop 数据不变，新老 yaml 可并存训练 |
```

Match the surrounding table column widths and Chinese phrasing. Do not
reflow other rows.

### Task 4 — Operator docs

Create `docs/graph_data_collection.md` (~50–80 lines). Sections:

1. **流程图** — copy the ASCII diagram from §2 of this handoff
2. **Snapshot 命名约定** — explain that Unity writes
   `depth_camera_<yyyyMMdd_HHmmss_fff>_frame<N>.json` under
   `GraphPerceptionPrj/DepthCameraSnapshots/`; user presses `8` (or Keypad8)
   once per episode at the start
3. **YAML 样例** — embed `graph_attach_smoke_v1.yaml` skeleton
4. **CLI 命令** — paste the canonical invocation from §5 of this handoff
5. **验证步骤** — one-liner that loads an output HDF5 and prints its keys:
   ```bash
   python -c "from testbed.data.hdf5_io import read_episode; \
              ep = read_episode('data/agx_teleop_v1_graph_v1/episode_000000.hdf5', load_images=False); \
              print(sorted(ep.keys())); print(ep['observation_graph'].keys())"
   ```

### Task 5 — Final acceptance

```bash
cd /home/zhaoshuai/workspace_excavator/excavator_testbed
python -m pytest tests/test_depth_graph.py tests/test_depth_graph_cli.py \
  tests/test_depth_graph_preview_cli.py tests/test_observation_graph_hdf5.py \
  tests/test_lidar_heightmap.py tests/test_build_graph_dataset.py -q
```

Must end with **`30 passed`** (27 existing + 3 new). Anything less = task
failed.

Also verify CLI is discoverable:

```bash
tb-build-graph-dataset --help
```

Must print a usage banner containing all flags from §1.2.

---

## 4. Hard constraints (do not violate)

- ❌ Do not edit `testbed/perception/depth_graph.py`,
  `testbed/cli/depth_graph.py`, `testbed/cli/record_teleop.py`,
  `testbed/data/hdf5_io.py`.
- ❌ Do not change node_features dim (8), edge_features dim (5), or any
  existing HDF5 dataset name.
- ❌ Do not auto-commit. Leave changes staged or unstaged for human review.
- ❌ Do not introduce new third-party dependencies beyond what
  `pyproject.toml` already pins. Use `pyyaml` only if it is already a
  dependency; otherwise parse with a tiny manual loader or vendor a
  minimal YAML subset reader (verify by `grep -i yaml pyproject.toml`
  first; if absent, write a 30-line parser supporting only the schema in
  §1.3).
- ✅ Follow existing typing / docstring conventions (look at
  `testbed/cli/depth_graph.py` and `testbed/cli/record_teleop.py` for
  reference style).
- ✅ All new code must be `add-only`; deletions are limited to nothing.
- ✅ Run tests after each task completion (1 → 2 → 3 → 4 → 5).

---

## 5. Operator workflow (after codex finishes)

This is what `zhaoshuai` will run by hand:

### Step 1 — Collect (Unity + teleop)

In Unity Editor, with `DepthCameraSnapshotExporter` active on the depth
camera GameObject, press `8` (or Keypad8) **once at the start of each
episode** before pressing the teleop record button.

Then run the existing teleop CLI (NO changes from prior workflow):

```bash
tb-record-teleop \
  --config testbed/configs/teleop_v1.yaml \
  --input joystick \
  --num-episodes 10 \
  --operator-id zhaoshuai \
  --session-id smoke-graph-v1 \
  --notes "graph variant baseline collection" \
  --output-dir data/agx_teleop_graph_smoke_v1
```

### Step 2 — Author snapshot map

```yaml
# graph_attach_smoke_v1.yaml
defaults:
  snapshot_root: /home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/DepthCameraSnapshots
episodes:
  - episode_index: 0
    snapshot: depth_camera_20260601_140012_frame123.json
  - episode_index: 1
    snapshot: depth_camera_20260601_140235_frame456.json
  # ... one line per episode
```

### Step 3 — Build graph variant

```bash
tb-build-graph-dataset \
  --teleop-dir   data/agx_teleop_graph_smoke_v1 \
  --snapshot-map graph_attach_smoke_v1.yaml \
  --output-dir   data/agx_teleop_graph_smoke_v1_graph_v1 \
  --roi-u-min 0.23 --roi-u-max 0.70 \
  --roi-v-min 0.22 --roi-v-max 0.70 \
  --gradient-node-ratio 0.7 \
  --max-nodes 256 --max-edges 1024 \
  --knn-k 4
```

### Step 4 — Verify

```bash
python -c "from testbed.data.hdf5_io import read_episode; \
  ep = read_episode('data/agx_teleop_graph_smoke_v1_graph_v1/episode_000000.hdf5', load_images=False); \
  print(sorted(ep.keys())); \
  g = ep['observation_graph']; \
  print({k: v.shape for k, v in g.items()})"
```

Expected output includes `observation_graph` in keys, and shapes:

```text
{'node_features': (T, 256, 8), 'node_mask': (T, 256),
 'edge_indices': (T, 1024, 2), 'edge_features': (T, 1024, 5),
 'edge_mask': (T, 1024), 'graph_globals': (T, 6)}
```

### Step 5 — Train comparison (NOT in this task's scope)

- baseline: existing `act_agx_v1.yaml` on `data/agx_teleop_graph_smoke_v1`
- with-graph: future `act_agx_v1_graph.yaml` on `data/agx_teleop_graph_smoke_v1_graph_v1`

---

## 6. Progress dashboard

| Module | Status |
|---|---|
| Gate 1 perception pipeline | ✅ done |
| Gate 2 intrinsics | ✅ done |
| Gate 3 ROI crop fix | ✅ done |
| baseline tuning verified | ✅ done |
| **`tb-build-graph-dataset` CLI** | 🔲 codex |
| **`tests/test_build_graph_dataset.py`** | 🔲 codex |
| **README + docs** | 🔲 codex |
| Collect 10 teleop episodes + snapshots | 🔲 zhaoshuai (after codex) |
| ACT-side graph branch + yaml | 🔲 next gate (out of scope) |

---

## 7. One-line directive to codex

> Execute tasks 0 → 5 in order. Run `pytest` after each task. Do not modify
> the four contract files listed in §4. All new files follow the existing
> repo typing / docstring style. Task 5 acceptance requires **30 passed**
> from the listed pytest command; do not declare success otherwise. Do not
> auto-commit.
