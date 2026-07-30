"""
EvalMetrics: dataclass for a single evaluation run's aggregate metrics.

Serialisable to JSON and CSV for easy comparison across runs.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalMetrics:
    """
    Aggregate metrics for one policy × task × config evaluation run.

    Attributes
    ----------
    task_name       Task identifier string.
    policy_name     Policy class name (e.g. "act", "dummy").
    ckpt_path       Path to the checkpoint used (empty string if none).
    n_rollouts      Total number of rollouts attempted.
    n_success       Number of rollouts where highest_reward == max_reward.
    success_rate    n_success / n_rollouts.
    avg_return      Mean cumulative reward across rollouts.
    avg_episode_len Mean number of steps per rollout.
    episode_returns Per-rollout cumulative rewards.
    highest_rewards Per-rollout maximum reward.
    extra           Any additional scalar metrics (e.g. action_jerk, guard_triggers).
    """

    task_name:        str
    policy_name:      str
    ckpt_path:        str

    n_rollouts:       int
    n_success:        int
    success_rate:     float
    avg_return:       float
    avg_episode_len:  float

    episode_returns:  list[float] = field(default_factory=list)
    highest_rewards:  list[float] = field(default_factory=list)
    extra:            dict[str, Any] = field(default_factory=dict)

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_rollouts(
        cls,
        task_name: str,
        policy_name: str,
        ckpt_path: str,
        episode_returns: list[float],
        highest_rewards: list[float],
        env_max_reward: float,
        episode_lengths: list[int] | None = None,
        successes: list[bool] | None = None,
        extra: dict | None = None,
    ) -> EvalMetrics:
        import numpy as np
        n = len(episode_returns)
        if successes is None:
            n_success = int(np.sum(np.array(highest_rewards) == env_max_reward))
            success_rate = n_success / n if n > 0 else 0.0
        else:
            n_success = int(np.sum(np.array(successes, dtype=np.bool_)))
            success_rate = n_success / n if n > 0 else 0.0
        return cls(
            task_name       = task_name,
            policy_name     = policy_name,
            ckpt_path       = ckpt_path,
            n_rollouts      = n,
            n_success       = n_success,
            success_rate    = success_rate,
            avg_return      = float(np.mean(episode_returns)),
            avg_episode_len = float(np.mean(episode_lengths)) if episode_lengths else 0.0,
            episode_returns = [float(r) for r in episode_returns],
            highest_rewards = [float(r) for r in highest_rewards],
            extra           = extra or {},
        )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: Path | str) -> EvalMetrics:
        with open(path) as f:
            d = json.load(f)
        return cls(**d)

    def to_csv_row(self) -> dict:
        """Flat dict suitable for csv.DictWriter."""
        row = {
            "task_name":       self.task_name,
            "policy_name":     self.policy_name,
            "ckpt_path":       self.ckpt_path,
            "n_rollouts":      self.n_rollouts,
            "n_success":       self.n_success,
            "success_rate":    f"{self.success_rate:.4f}",
            "avg_return":      f"{self.avg_return:.4f}",
            "avg_episode_len": f"{self.avg_episode_len:.1f}",
        }
        row.update({f"extra_{k}": v for k, v in self.extra.items()})
        return row

    @staticmethod
    def append_to_csv(metrics_list: list[EvalMetrics], path: Path | str) -> None:
        """Append multiple EvalMetrics to a CSV file (creates file if absent)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [m.to_csv_row() for m in metrics_list]
        if not rows:
            return
        write_header = not path.exists()
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

    # ── Display ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [
            f"Task:         {self.task_name}",
            f"Policy:       {self.policy_name}",
            f"Checkpoint:   {self.ckpt_path}",
            f"Rollouts:     {self.n_rollouts}",
            f"Success rate: {self.success_rate * 100:.1f}%  ({self.n_success}/{self.n_rollouts})",
            f"Avg return:   {self.avg_return:.4f}",
        ]
        if self.extra:
            for k, v in self.extra.items():
                lines.append(f"  {k}: {v}")

        # per-reward histogram
        import numpy as np
        if self.highest_rewards:
            max_r = int(max(self.highest_rewards))
            for r in range(max_r + 1):
                count = int(np.sum(np.array(self.highest_rewards) >= r))
                rate  = count / self.n_rollouts
                lines.append(f"  reward >= {r}: {count}/{self.n_rollouts} = {rate * 100:.1f}%")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"EvalMetrics(task={self.task_name!r}, policy={self.policy_name!r}, "
            f"success={self.success_rate:.2%}, avg_return={self.avg_return:.4f})"
        )
