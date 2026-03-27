"""
Pydantic config schemas for the testbed.

Usage
-----
Load a YAML file and validate it::

    import yaml
    from testbed.configs.schema import TaskConfig

    with open("testbed/configs/task_v0.yaml") as f:
        data = yaml.safe_load(f)
    cfg = TaskConfig.model_validate(data)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─── Backend ──────────────────────────────────────────────────────────────────

class BackendConfig(BaseModel):
    """Configuration for the simulation backend."""

    name: Literal["mujoco"] = "mujoco"
    """Backend implementation to use. Currently only 'mujoco' is supported."""

    dt: float = Field(default=0.02, gt=0, description="Control timestep in seconds (50 Hz = 0.02)")
    assets_dir: str = Field(
        default="",
        description="Absolute path to MJCF assets root. Empty = auto-resolved relative to package.",
    )

    @field_validator("assets_dir", mode="before")
    @classmethod
    def resolve_assets_dir(cls, v: str) -> str:
        if not v:
            # Auto-resolve: testbed/assets/ relative to this file's package root
            return str(Path(__file__).resolve().parents[1] / "assets")
        return str(Path(v).resolve())


# ─── Task ─────────────────────────────────────────────────────────────────────

class TaskConfig(BaseModel):
    """Configuration for a simulation task / data collection run."""

    task_name: str = Field(..., description="Unique task identifier, e.g. 'sim_lifting_cube_scripted'")
    equipment_model: str = Field(
        default="excavator_simple",
        description="Robot / equipment model folder under assets/. E.g. 'excavator_simple', 'vx300s_bimanual'.",
    )
    dataset_dir: str = Field(..., description="Directory where HDF5 episodes are written / read.")
    num_episodes: int = Field(default=50, gt=0)
    episode_len: int = Field(default=400, gt=0, description="Max timesteps per episode.")
    camera_names: list[str] = Field(default_factory=lambda: ["top"])

    backend: BackendConfig = Field(default_factory=BackendConfig)

    # Data collection specifics
    inject_noise: bool = False
    only_save_success: bool = False
    success_reward_threshold: float | None = None
    target_success_episodes: int | None = None
    fixed_object_pose: list[float] | None = Field(
        default=None,
        description="Fixed 7-DOF object pose [x,y,z, qw,qx,qy,qz] for reproducible smoke tests.",
    )

    # Excavator-specific pipeline
    excavator_pipeline: Literal["ee_replay", "direct_sim"] = "ee_replay"


# ─── Policy ───────────────────────────────────────────────────────────────────

class PolicyConfig(BaseModel):
    """Identifies which policy plugin to use and its hyperparameters."""

    name: str = Field(..., description="Registered policy name, e.g. 'act', 'dummy', 'diffusion'.")
    params: dict = Field(
        default_factory=dict,
        description="Plugin-specific hyperparameters passed verbatim to the adapter.",
    )


class ACTPolicyParams(BaseModel):
    """ACT-specific hyperparameters (used as PolicyConfig.params when name='act')."""

    lr: float = 1e-5
    lr_backbone: float = 1e-5
    backbone: str = "resnet18"
    enc_layers: int = 4
    dec_layers: int = 7
    nheads: int = 8
    hidden_dim: int = 512
    dim_feedforward: int = 3200
    chunk_size: int = 100
    kl_weight: float = 10.0
    latent_dim: int = 32
    temporal_agg: bool = False


# ─── Training ─────────────────────────────────────────────────────────────────

class TrainConfig(BaseModel):
    """Configuration for a training run."""

    task: TaskConfig
    policy: PolicyConfig
    ckpt_dir: str = Field(..., description="Directory to save checkpoints + stats.")
    num_epochs: int = Field(default=2000, gt=0)
    batch_size: int = Field(default=8, gt=0)
    seed: int = 0
    num_workers: int = 4
    prefetch_factor: int = 2
    persistent_workers: bool = True
    pin_memory: bool = True
    split_seed: int | None = None
    train_split_ratio: float = 0.8
    split_path: str | None = None
    reuse_split: bool = True
    val_every: int = 1
    save_latest_every: int = 1
    checkpoint_every: int = 100
    plot_every: int = 100
    amp: bool = False
    amp_dtype: Literal["auto", "bf16", "fp16"] = "auto"
    resume_ckpt: str | None = None


# ─── Evaluation ───────────────────────────────────────────────────────────────

class EvalConfig(BaseModel):
    """Configuration for a fixed-seed evaluation run."""

    task: TaskConfig
    policy: PolicyConfig
    ckpt_path: str = Field(..., description="Path to checkpoint file (policy_best.ckpt etc).")
    dataset_stats_path: str = Field(..., description="Path to dataset_stats.pkl for normalization.")
    output_dir: str = Field(..., description="Where to write metrics.json + summary.csv + videos/.")

    num_rollouts: int = Field(default=50, gt=0)
    seed: int = 1000
    save_videos: bool = True
    video_camera: str = "angle"

    # Eval thresholds used for pass/fail annotation in video overlay
    success_reward_threshold: float | None = None
