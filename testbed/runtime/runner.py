"""
Runner: orchestrate a full record → train → eval pipeline run.

Typically invoked by the CLI scripts, but can also be used programmatically.

Usage (programmatic):
    runner = Runner.from_yaml("testbed/configs/act_v0.yaml")
    runner.record()
    runner.train()
    runner.eval()
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import yaml


class Runner:
    """
    Pipeline orchestrator.

    Parameters
    ----------
    config  Dict of merged task + policy + eval config.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, *yaml_paths: str | Path) -> "Runner":
        """
        Load and merge one or more YAML configs (later files override earlier).
        """
        merged: dict = {}
        for p in yaml_paths:
            with open(p) as f:
                merged.update(yaml.safe_load(f) or {})
        return cls(merged)

    # ── record ────────────────────────────────────────────────────────────────

    def record(self) -> None:
        """
        Collect scripted demonstration episodes and save to HDF5.

        Reads from config keys:
          task.name, task.dataset_dir, task.num_episodes, task.episode_len,
          task.equipment_model, task.pipeline
        """
        from testbed.runtime._record import record_episodes
        record_episodes(self.config)

    # ── train ─────────────────────────────────────────────────────────────────

    def train(self) -> None:
        """
        Train the policy on collected demonstrations.

        Reads from config keys:
          policy.*, train.*
        """
        from testbed.runtime._train import train_policy
        train_policy(self.config)

    # ── eval ──────────────────────────────────────────────────────────────────

    def eval(self, ckpt_path: str | Path | None = None) -> None:
        """
        Evaluate a trained policy with fixed seeds.

        Parameters
        ----------
        ckpt_path  Override the checkpoint to evaluate.
                   Defaults to <ckpt_dir>/policy_best.ckpt.
        """
        from testbed.runtime._eval import eval_policy
        cfg = dict(self.config)
        if ckpt_path:
            cfg["eval"]["ckpt_path"] = str(ckpt_path)
        eval_policy(cfg)
