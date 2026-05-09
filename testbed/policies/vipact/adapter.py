"""
Thin runtime adapter for using an external ViPACT checkpoint in testbed eval.

The ViPACT repository stays external. This adapter only imports ViPACT from a
configured repo path, loads policy_best.ckpt and dataset_stats.pkl, converts
testbed observations into ViPACT ACT tensors, and returns unnormalised AGX
action commands.
"""

from __future__ import annotations

import importlib
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

from testbed.policies.base import Policy, register_policy


@register_policy("vipact")
class ViPACTAdapter(Policy):
    """
    Deploy a ViPACT ACT policy inside the testbed evaluation loop.

    Expected action convention remains the testbed/Unity bridge convention:
    [swing, boom, stick, bucket].
    """

    def __init__(
        self,
        repo_path: str | Path,
        ckpt_path: str | Path,
        norm_stats_path: str | Path | None = None,
        camera_names: list[str] | tuple[str, ...] = ("fpv",),
        device: str = "cuda",
        temporal_agg: bool = False,
        max_episode_len: int = 1000,
        act_params: dict[str, Any] | None = None,
        equipment_model: str = "excavator_simple",
        image_channels: int = 3,
        use_mask_conditioning: bool = False,
        strict_load: bool = True,
    ) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.ckpt_path = Path(ckpt_path).expanduser()
        self.norm_stats_path = (
            Path(norm_stats_path).expanduser()
            if norm_stats_path is not None
            else self.ckpt_path.parent / "dataset_stats.pkl"
        )
        self.camera_names = list(camera_names)
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.temporal_agg = bool(temporal_agg)
        self.max_episode_len = int(max_episode_len)
        self.image_channels = int(image_channels)
        self.use_mask_conditioning = bool(use_mask_conditioning)

        if self.image_channels not in (3, 4):
            raise ValueError(
                f"ViPACTAdapter supports image_channels 3 or 4, got {self.image_channels}."
            )

        with open(self.norm_stats_path, "rb") as f:
            self.norm_stats = pickle.load(f)
        self.qpos_mean = np.asarray(self.norm_stats["qpos_mean"], dtype=np.float32)
        self.qpos_std = np.asarray(self.norm_stats["qpos_std"], dtype=np.float32)
        self.action_mean = np.asarray(self.norm_stats["action_mean"], dtype=np.float32)
        self.action_std = np.asarray(self.norm_stats["action_std"], dtype=np.float32)

        params = dict(act_params or {})
        self.num_queries = int(params.get("chunk_size", params.get("num_queries", 100)))
        policy_config = {
            "lr": float(params.get("lr", 1e-5)),
            "lr_backbone": float(params.get("lr_backbone", 1e-5)),
            "backbone": str(params.get("backbone", "resnet18")),
            "enc_layers": int(params.get("enc_layers", 4)),
            "dec_layers": int(params.get("dec_layers", 7)),
            "nheads": int(params.get("nheads", 8)),
            "num_queries": self.num_queries,
            "kl_weight": float(params.get("kl_weight", 10.0)),
            "hidden_dim": int(params.get("hidden_dim", 512)),
            "dim_feedforward": int(params.get("dim_feedforward", 3200)),
            "camera_names": self.camera_names,
            # Current ViPACT maps excavator_simple to state/action dim 4.
            "equipment_model": str(equipment_model),
            "image_channels": self.image_channels,
            "use_mask_conditioning": self.use_mask_conditioning,
            "temporal_agg": self.temporal_agg,
        }

        self._policy = self._build_external_policy(policy_config)
        raw = torch.load(self.ckpt_path, map_location=self.device)
        state_dict = (
            raw["model_state_dict"]
            if isinstance(raw, dict) and "model_state_dict" in raw
            else raw
        )
        load_result = self._policy.load_state_dict(state_dict, strict=bool(strict_load))
        if not bool(strict_load):
            missing = list(getattr(load_result, "missing_keys", []))
            unexpected = list(getattr(load_result, "unexpected_keys", []))
            if missing or unexpected:
                print(
                    "[ViPACTAdapter] non-strict checkpoint load: "
                    f"missing={missing}, unexpected={unexpected}"
                )
        self._policy.to(self.device)
        self._policy.eval()
        self.reset()

    def reset(self) -> None:
        self._t = 0
        self._cached_actions: torch.Tensor | None = None
        self._action_chunk_history: list[tuple[int, torch.Tensor]] = []

    @torch.inference_mode()
    def predict(self, obs: dict) -> np.ndarray:
        qpos = self._build_qpos_tensor(obs)
        image = self._build_image_tensor(obs)
        a_hat = self._policy(qpos, image)  # (1, chunk, action_dim)

        if self.temporal_agg:
            action = self._aggregate(a_hat)
        else:
            if self._cached_actions is None or self._t % self.num_queries == 0:
                self._cached_actions = a_hat
            action = self._cached_actions[:, self._t % self.num_queries]

        self._t += 1
        action_np = action.squeeze(0).detach().cpu().numpy()
        action_np = action_np * self.action_std + self.action_mean
        return action_np.astype(np.float32)

    def _build_external_policy(self, policy_config: dict[str, Any]):
        if not self.repo_path.is_dir():
            raise FileNotFoundError(f"ViPACT repo_path does not exist: {self.repo_path}")

        import_paths = [
            self.repo_path,
            self.repo_path / "detr",
        ]
        for path in reversed(import_paths):
            path_str = str(path)
            if path.is_dir() and path_str not in sys.path:
                sys.path.insert(0, path_str)

        # ViPACT's DETR builder parses sys.argv. Isolate it from tb-eval flags.
        argv_backup = sys.argv[:]
        module_cuda = torch.nn.Module.cuda
        tensor_cuda = torch.Tensor.cuda
        try:
            sys.argv = [sys.argv[0]]
            if self.device.type == "cpu":
                torch.nn.Module.cuda = lambda module, device=None: module
                torch.Tensor.cuda = lambda tensor, device=None, non_blocking=False, memory_format=None: tensor
            module = importlib.import_module("policy")
            policy_cls = getattr(module, "ACTPolicy")
            return policy_cls(policy_config)
        finally:
            sys.argv = argv_backup
            torch.nn.Module.cuda = module_cuda
            torch.Tensor.cuda = tensor_cuda

    def _build_qpos_tensor(self, obs: dict) -> torch.Tensor:
        if "qpos" not in obs:
            raise ValueError("ViPACTAdapter.predict(): missing required obs['qpos'].")
        qpos = np.asarray(obs["qpos"], dtype=np.float32).reshape(-1)
        if qpos.shape != self.qpos_mean.shape:
            raise ValueError(
                "ViPACTAdapter.predict(): qpos shape does not match dataset_stats.pkl: "
                f"obs={qpos.shape}, stats={self.qpos_mean.shape}."
            )
        qpos = (qpos - self.qpos_mean) / self.qpos_std
        return torch.from_numpy(qpos).float().to(self.device).unsqueeze(0)

    def _build_image_tensor(self, obs: dict) -> torch.Tensor:
        cam_images: list[np.ndarray] = []
        for cam in self.camera_names:
            key = f"image_{cam}"
            if key not in obs:
                raise ValueError(
                    f"ViPACTAdapter.predict(): missing required camera input {key!r}."
                )
            image = np.asarray(obs[key])
            if image.ndim != 3:
                raise ValueError(
                    f"ViPACTAdapter.predict(): expected {key!r} rank 3, got {image.shape}."
                )
            if image.shape[0] in (3, 4):
                chw = image.astype(np.float32)
                if chw.max() > 1.0:
                    chw = chw / 255.0
            elif image.shape[-1] in (3, 4):
                chw = np.transpose(image, (2, 0, 1)).astype(np.float32)
                if chw.max() > 1.0:
                    chw = chw / 255.0
            else:
                raise ValueError(
                    f"ViPACTAdapter.predict(): expected RGB/RGBA image for {key!r}, got {image.shape}."
                )

            if self.image_channels == 4 and chw.shape[0] == 3:
                mask = np.zeros(chw.shape[1:], dtype=np.float32)
                chw = np.concatenate([chw, mask[None, ...]], axis=0)
            elif self.image_channels == 3 and chw.shape[0] == 4:
                chw = chw[:3]
            elif chw.shape[0] != self.image_channels:
                raise ValueError(
                    f"ViPACTAdapter.predict(): expected {self.image_channels} channels "
                    f"for {key!r}, got {chw.shape[0]}."
                )
            cam_images.append(chw)

        stacked = np.stack(cam_images, axis=0)
        return torch.from_numpy(stacked).float().to(self.device).unsqueeze(0)

    def _aggregate(self, a_hat: torch.Tensor) -> torch.Tensor:
        step_id = int(self._t)
        chunk = a_hat.squeeze(0)
        self._action_chunk_history.append((step_id, chunk))

        candidates = []
        for start_t, actions in self._action_chunk_history:
            offset = step_id - start_t
            if 0 <= offset < int(actions.shape[0]):
                candidates.append(actions[offset])

        self._action_chunk_history = [
            (start_t, actions)
            for start_t, actions in self._action_chunk_history
            if start_t + int(actions.shape[0]) > step_id
        ]

        if not candidates:
            return chunk[0].unsqueeze(0)

        actions_for_curr_step = torch.stack(candidates, dim=0)
        weights = torch.exp(
            -0.01 * torch.arange(len(candidates), device=self.device, dtype=torch.float32)
        )
        weights = weights / weights.sum()
        return (actions_for_curr_step * weights.unsqueeze(1)).sum(dim=0, keepdim=True)
