"""Graph-conditioned ACT adapter."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import torch
import torchvision.transforms as transforms

from testbed.data.image_masks import apply_image_mask
from testbed.policies.act.adapter import _kl_divergence
from testbed.policies.act.detr.main import get_args_parser
from testbed.policies.act.detr.models import build_ACT_model
from testbed.policies.act_graph.model import (
    ACTGraphModel,
    GraphEncoder,
    GraphEncoderConfig,
)
from testbed.policies.base import Policy, register_policy


@register_policy("act_graph")
class ACTGraphAdapter(Policy):
    """Training adapter for ACT with an additional graph observation branch."""

    def __init__(
        self,
        policy_config: dict,
        norm_stats: dict[str, np.ndarray],
        temporal_agg: bool = False,
        device: str = "cuda",
    ):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.norm_stats = norm_stats
        self.temporal_agg = bool(temporal_agg)
        self.kl_weight = float(policy_config.get("kl_weight", 10))
        self._camera_names = list(policy_config.get("camera_names", []))
        self._low_dim_keys = list(policy_config.get("low_dim_keys", ["qpos"]))
        self._image_mask_config = dict(policy_config.get("image_mask") or {})

        graph_config = _graph_encoder_config(policy_config.get("graph_params", {}))
        act_model = _build_act_model(policy_config)
        graph_encoder = GraphEncoder(graph_config)
        self._model = ACTGraphModel(act_model, graph_encoder).to(self.device)
        self._optimizer = _build_optimizer(self._model, policy_config)
        self._normalize = transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        )
        self._num_queries = int(policy_config["num_queries"])
        self._t = 0
        self._all_time_actions: torch.Tensor | None = None
        self._all_time_actions_valid: torch.Tensor | None = None
        self._cached_actions: torch.Tensor | None = None
        self._proprio_mean, self._proprio_std = self._resolve_proprio_norm_stats()

    def reset(self) -> None:
        self._t = 0
        self._all_time_actions = None
        self._all_time_actions_valid = None
        self._cached_actions = None

    def predict(self, obs: dict) -> np.ndarray:
        proprio = self._build_proprio(obs)
        proprio = (proprio - self._proprio_mean) / self._proprio_std
        image = self._build_image_tensor(obs)
        graph = self._build_graph_tensor(obs)

        self._model.eval()
        with torch.no_grad():
            a_hat, _, _ = self._model(proprio, image, None, graph)

        if self.temporal_agg:
            action = self._aggregate(a_hat)
        else:
            if self._t % self._num_queries == 0 or self._cached_actions is None:
                self._cached_actions = a_hat.squeeze(0)
            step_in_chunk = self._t % self._num_queries
            action = self._cached_actions[step_in_chunk].cpu().numpy()

        self._t += 1
        action = (
            action
            * self.norm_stats["action_std"]
            + self.norm_stats["action_mean"]
        )
        return action.astype(np.float32)

    def forward_loss(
        self,
        proprio: torch.Tensor,
        graph: dict[str, torch.Tensor],
        image: torch.Tensor,
        actions: torch.Tensor,
        is_pad: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        image = self._normalize(image)
        graph = {key: value.to(self.device) for key, value in graph.items()}
        actions = actions[:, : self._model.num_queries]
        is_pad = is_pad[:, : self._model.num_queries]

        a_hat, _, (mu, logvar) = self._model(
            proprio,
            image,
            None,
            graph,
            actions=actions,
            is_pad=is_pad,
        )
        total_kld, _, _ = _kl_divergence(mu, logvar)

        import torch.nn.functional as F

        all_l1 = F.l1_loss(actions, a_hat, reduction="none")
        l1 = (all_l1 * ~is_pad.unsqueeze(-1)).mean()
        return {
            "l1": l1,
            "kl": total_kld[0],
            "loss": l1 + total_kld[0] * self.kl_weight,
        }

    def configure_optimizers(self):
        return self._optimizer

    def state_dict(self):
        return self._model.state_dict()

    def load_state_dict(self, sd, strict: bool = True):
        return self._model.load_state_dict(sd, strict=strict)

    def _build_proprio(self, obs: dict) -> torch.Tensor:
        parts: list[np.ndarray] = []
        for key in self._low_dim_keys:
            if key not in obs:
                raise ValueError(
                    f"ACTGraphAdapter.predict(): missing required low-dimensional input {key!r}."
                )
            parts.append(np.asarray(obs[key], dtype=np.float32).reshape(-1))
        if not parts:
            raise ValueError("ACTGraphAdapter.predict(): low_dim_keys must not be empty.")
        proprio = np.concatenate(parts, axis=0).astype(np.float32)
        return torch.from_numpy(proprio).float().to(self.device).unsqueeze(0)

    def _build_image_tensor(self, obs: dict) -> torch.Tensor:
        cam_images: list[np.ndarray] = []
        for cam in self._camera_names:
            key = f"image_{cam}"
            if key not in obs:
                raise ValueError(
                    f"ACTGraphAdapter.predict(): missing required camera input {key!r}."
                )
            cam_img = apply_image_mask(
                np.asarray(obs[key]),
                camera_name=cam,
                mask_config=self._image_mask_config,
                mask=obs.get(f"image_mask_{cam}"),
            )
            cam_img = np.asarray(cam_img, dtype=np.float32)
            if cam_img.ndim != 3:
                raise ValueError(
                    f"ACTGraphAdapter.predict(): expected {key!r} to be rank-3, got shape {cam_img.shape}."
                )
            if cam_img.shape[0] == 3:
                pass
            elif cam_img.shape[-1] == 3:
                cam_img = np.transpose(cam_img, (2, 0, 1))
                if cam_img.max() > 1.0:
                    cam_img = cam_img / 255.0
            else:
                raise ValueError(
                    f"ACTGraphAdapter.predict(): expected {key!r} to have 3 channels, got shape {cam_img.shape}."
                )
            cam_images.append(cam_img)
        if not cam_images:
            raise ValueError("ACTGraphAdapter.predict(): no camera inputs configured.")
        image = torch.from_numpy(np.stack(cam_images, axis=0)).float().to(self.device)
        image = image.unsqueeze(0)
        return self._normalize(image)

    def _build_graph_tensor(self, obs: dict) -> dict[str, torch.Tensor]:
        raw_graph = obs.get("observation_graph", obs.get("graph"))
        if raw_graph is None:
            raise ValueError(
                "ACTGraphAdapter.predict(): missing graph observation. "
                "Expected obs['observation_graph'] or obs['graph'] with node_features, "
                "node_mask, edge_indices, edge_features, edge_mask, and graph_globals."
            )
        required = (
            "node_features",
            "node_mask",
            "edge_indices",
            "edge_features",
            "edge_mask",
            "graph_globals",
        )
        missing = [key for key in required if key not in raw_graph]
        if missing:
            raise ValueError(
                "ACTGraphAdapter.predict(): graph observation missing keys "
                + ", ".join(missing)
            )
        return {
            "node_features": _as_batched_tensor(raw_graph["node_features"], dtype=torch.float32, device=self.device),
            "node_mask": _as_batched_tensor(raw_graph["node_mask"], dtype=torch.bool, device=self.device),
            "edge_indices": _as_batched_tensor(raw_graph["edge_indices"], dtype=torch.long, device=self.device),
            "edge_features": _as_batched_tensor(raw_graph["edge_features"], dtype=torch.float32, device=self.device),
            "edge_mask": _as_batched_tensor(raw_graph["edge_mask"], dtype=torch.bool, device=self.device),
            "graph_globals": _as_batched_tensor(raw_graph["graph_globals"], dtype=torch.float32, device=self.device),
        }

    def _resolve_proprio_norm_stats(self) -> tuple[torch.Tensor, torch.Tensor]:
        if "proprio_mean" in self.norm_stats and "proprio_std" in self.norm_stats:
            mean = self.norm_stats["proprio_mean"]
            std = self.norm_stats["proprio_std"]
        elif self._low_dim_keys == ["qpos"]:
            mean = self.norm_stats["qpos_mean"]
            std = self.norm_stats["qpos_std"]
        else:
            raise KeyError(
                "dataset_stats.pkl does not contain proprio_mean/proprio_std for "
                f"low_dim_keys={self._low_dim_keys}."
            )
        return (
            torch.from_numpy(np.asarray(mean, dtype=np.float32)).to(self.device),
            torch.from_numpy(np.asarray(std, dtype=np.float32)).to(self.device),
        )

    def _aggregate(self, a_hat: torch.Tensor) -> np.ndarray:
        chunk = a_hat.squeeze(0)
        num_queries, action_dim = chunk.shape
        if num_queries != self._num_queries:
            raise ValueError(
                "ACTGraphAdapter._aggregate(): model query count changed from "
                f"{self._num_queries} to {num_queries}."
            )
        if (
            self._all_time_actions is None
            or self._all_time_actions.shape != (self._num_queries, self._num_queries, action_dim)
        ):
            self._all_time_actions = torch.zeros(
                [self._num_queries, self._num_queries, action_dim],
                device=self.device,
                dtype=chunk.dtype,
            )
            self._all_time_actions_valid = torch.zeros(
                [self._num_queries, self._num_queries],
                device=self.device,
                dtype=torch.bool,
            )
        elif self._all_time_actions_valid is None:
            self._all_time_actions_valid = torch.zeros(
                [self._num_queries, self._num_queries],
                device=self.device,
                dtype=torch.bool,
            )
        t = self._t
        slot = t % self._num_queries
        self._all_time_actions[slot] = chunk
        self._all_time_actions_valid[slot] = True
        start_step = max(0, t - self._num_queries + 1)
        actions_for_curr_step = []
        for source_step in range(start_step, t + 1):
            source_slot = source_step % self._num_queries
            query_offset = t - source_step
            if bool(self._all_time_actions_valid[source_slot, query_offset]):
                actions_for_curr_step.append(
                    self._all_time_actions[source_slot, query_offset]
                )
        actions_for_curr_step = torch.stack(actions_for_curr_step, dim=0)
        k = 0.01
        exp_weights = np.exp(-k * np.arange(len(actions_for_curr_step)))
        exp_weights = exp_weights / exp_weights.sum()
        exp_weights = torch.from_numpy(exp_weights).float().to(self.device).unsqueeze(1)
        return (actions_for_curr_step * exp_weights).sum(0).cpu().numpy()

    @classmethod
    def from_checkpoint(
        cls,
        ckpt_path: str | Path,
        policy_config: dict,
        norm_stats_path: str | Path,
        temporal_agg: bool = False,
        device: str = "cuda",
    ) -> "ACTGraphAdapter":
        with open(norm_stats_path, "rb") as f:
            norm_stats = pickle.load(f)
        adapter = cls(
            policy_config=policy_config,
            norm_stats=norm_stats,
            temporal_agg=temporal_agg,
            device=device,
        )
        raw = torch.load(Path(ckpt_path), map_location="cpu")
        sd = raw["model_state_dict"] if isinstance(raw, dict) and "model_state_dict" in raw else raw
        adapter.load_state_dict(sd)
        return adapter


def _build_act_model(policy_config: dict) -> torch.nn.Module:
    parser = argparse.ArgumentParser(
        "ACT graph training model", parents=[get_args_parser()]
    )
    args = parser.parse_args([])
    for key, value in policy_config.items():
        if key == "graph_params":
            continue
        setattr(args, key, value)
    return build_ACT_model(args)


def _graph_encoder_config(raw: dict) -> GraphEncoderConfig:
    raw = dict(raw or {})
    return GraphEncoderConfig(
        node_feature_dim=int(raw.get("node_feature_dim", 8)),
        edge_feature_dim=int(raw.get("edge_feature_dim", 5)),
        graph_global_dim=int(raw.get("graph_global_dim", 6)),
        hidden_dim=int(raw.get("hidden_dim", 128)),
        output_dim=int(raw.get("embedding_dim", raw.get("output_dim", 64))),
        message_passing_steps=int(raw.get("message_passing_steps", 2)),
        dropout=float(raw.get("dropout", 0.0)),
    )


def _as_batched_tensor(value, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
    tensor = torch.as_tensor(value, dtype=dtype, device=device)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    elif tensor.ndim == 2 and dtype != torch.long:
        tensor = tensor.unsqueeze(0)
    elif tensor.ndim == 2 and dtype == torch.long:
        tensor = tensor.unsqueeze(0)
    return tensor


def _build_optimizer(model: torch.nn.Module, policy_config: dict):
    lr = float(policy_config.get("lr", 1e-5))
    lr_backbone = float(policy_config.get("lr_backbone", 1e-5))
    weight_decay = float(policy_config.get("weight_decay", 1e-4))
    param_dicts = [
        {
            "params": [
                param
                for name, param in model.named_parameters()
                if "backbone" not in name and param.requires_grad
            ]
        },
        {
            "params": [
                param
                for name, param in model.named_parameters()
                if "backbone" in name and param.requires_grad
            ],
            "lr": lr_backbone,
        },
    ]
    return torch.optim.AdamW(param_dicts, lr=lr, weight_decay=weight_decay)
