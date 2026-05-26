"""
ACT policy adapter.

Wraps the original ACTPolicy (nn.Module) behind the testbed Policy ABC so
that the evaluator and CLI can call policy.predict(obs) without knowing
any ACT internals.

Temporal aggregation
--------------------
When `temporal_agg=True`, actions are chunked and averaged using the
scheme from the original paper. Only the last `num_queries` chunks can
contribute to the current action, so inference keeps a rolling
`(C, C, Na)` buffer instead of the original dense `(T, T+C, Na)` tensor.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import torch
from einops import rearrange
import torchvision.transforms as transforms

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.image_masks import apply_image_mask
from testbed.policies.base import Policy, register_policy


def _kl_divergence(mu, logvar):
    if mu.data.ndimension() == 4:
        mu = mu.view(mu.size(0), mu.size(1))
    if logvar.data.ndimension() == 4:
        logvar = logvar.view(logvar.size(0), logvar.size(1))
    klds = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp())
    total_kld       = klds.sum(1).mean(0, True)
    dimension_wise  = klds.mean(0)
    mean_kld        = klds.mean(1).mean(0, True)
    return total_kld, dimension_wise, mean_kld


@register_policy("act")
class ACTAdapter(Policy):
    """
    Runnable ACT policy for inference.

    Parameters
    ----------
    policy_config  Dict passed to build_ACT_model_and_optimizer.
    norm_stats     Dataset normalisation stats (proprio_mean/std, action_mean/std).
    temporal_agg   Use temporal action aggregation (default False).
    device         Torch device string (default "cuda").
    """

    def __init__(
        self,
        policy_config: dict,
        norm_stats: dict[str, np.ndarray],
        temporal_agg: bool = False,
        device: str = "cuda",
    ):
        from testbed.policies.act.detr.main import build_ACT_model_and_optimizer

        self.device       = torch.device(device if torch.cuda.is_available() else "cpu")
        self.policy_config = dict(policy_config)
        self.norm_stats   = norm_stats
        self.temporal_agg = temporal_agg
        self.kl_weight    = policy_config.get("kl_weight", 10)
        outcome_cfg = dict(policy_config.get("outcome_head") or {})
        self.outcome_loss_weight = float(outcome_cfg.get("loss_weight", 0.0))
        self.token_swap_outcome_loss_weight = float(
            outcome_cfg.get("token_swap_loss_weight", 0.0)
        )
        self._camera_names = list(policy_config.get("camera_names", []))
        self._low_dim_keys = list(policy_config.get("low_dim_keys", ["qpos"]))
        self._image_mask_config = dict(policy_config.get("image_mask") or {})

        model, optimizer = build_ACT_model_and_optimizer(policy_config)
        self._model     = model.to(self.device)
        self._optimizer = optimizer

        # temporal aggregation state
        self._num_queries: int  = policy_config["num_queries"]
        self._t: int            = 0
        self._all_time_actions: torch.Tensor | None = None
        self._all_time_actions_valid: torch.Tensor | None = None
        self._max_episode_len = int(policy_config.get("max_episode_len", 400))

        self._normalize  = transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        )
        self._proprio_mean, self._proprio_std = self._resolve_proprio_norm_stats()
        self._token_slice = self._resolve_goal_token_slice()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Called once per evaluation rollout to clear temporal state."""
        self._t = 0
        self._all_time_actions = None
        self._all_time_actions_valid = None

    # ── inference ─────────────────────────────────────────────────────────────

    def predict(self, obs: dict) -> np.ndarray:
        """
        Parameters
        ----------
        obs   dict with keys:
                "qpos"      : (Nq,) float32
                "qvel"      : (Nv,) float32 when configured in low_dim_keys
                "goal_tokens": (10,) float32 when configured in low_dim_keys
                "image_<cam>": (C, H, W) float32 [0, 1]   for each camera
              Camera images should be in channel-first format.

        Returns
        -------
        action : (Na,) float32  in *unnormalised* action space.
        """
        proprio = self._build_proprio(obs)

        # normalise low-dimensional robot state
        proprio = (
            proprio - self._proprio_mean
        ) / self._proprio_std

        # Assemble image tensor in configured camera order. Ignore metadata
        # keys like `image_format` that may appear in live AGX observations.
        cam_images: list[np.ndarray] = []
        for cam in self._camera_names:
            key = f"image_{cam}"
            if key not in obs:
                raise ValueError(
                    f"ACTAdapter.predict(): missing required camera input {key!r}."
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
                    f"ACTAdapter.predict(): expected {key!r} to be rank-3, got shape {cam_img.shape}."
                )
            # Accept either channel-first float images or raw channel-last RGB.
            if cam_img.shape[0] == 3:
                pass
            elif cam_img.shape[-1] == 3:
                cam_img = np.transpose(cam_img, (2, 0, 1))
                if cam_img.max() > 1.0:
                    cam_img = cam_img / 255.0
            else:
                raise ValueError(
                    f"ACTAdapter.predict(): expected {key!r} to have 3 channels, got shape {cam_img.shape}."
                )
            cam_images.append(cam_img)

        if not cam_images:
            raise ValueError("ACTAdapter.predict(): no camera inputs configured.")

        img = np.stack(cam_images, axis=0)                 # (n_cams, C, H, W)
        image = torch.from_numpy(img).float().to(self.device).unsqueeze(0)  # (1, n_cams, C, H, W)
        image = self._normalize(image)

        self._model.eval()
        with torch.no_grad():
            model_out = self._model(proprio, image, None)   # (1, C, Na)
            a_hat, _, _, _ = self._unpack_model_output(model_out)

        if self.temporal_agg:
            action = self._aggregate(a_hat)
        else:
            # non-aggregated: execute every num_queries steps
            if self._t % self._num_queries == 0:
                self._cached_actions = a_hat.squeeze(0)    # (C, Na)
            step_in_chunk = self._t % self._num_queries
            action = self._cached_actions[step_in_chunk].cpu().numpy()

        self._t += 1

        # unnormalise
        action = (
            action
            * self.norm_stats["action_std"]
            + self.norm_stats["action_mean"]
        )
        return action.astype(np.float32)

    def predict_with_outcome(self, obs: dict) -> tuple[np.ndarray, np.ndarray | None]:
        """Return the first action plus optional outcome-head prediction."""
        proprio = self._build_proprio(obs)
        proprio = (proprio - self._proprio_mean) / self._proprio_std

        cam_images: list[np.ndarray] = []
        for cam in self._camera_names:
            key = f"image_{cam}"
            if key not in obs:
                raise ValueError(
                    f"ACTAdapter.predict_with_outcome(): missing required camera input {key!r}."
                )
            cam_img = apply_image_mask(
                np.asarray(obs[key]),
                camera_name=cam,
                mask_config=self._image_mask_config,
                mask=obs.get(f"image_mask_{cam}"),
            )
            cam_img = np.asarray(cam_img, dtype=np.float32)
            if cam_img.shape[0] == 3:
                pass
            elif cam_img.shape[-1] == 3:
                cam_img = np.transpose(cam_img, (2, 0, 1))
                if cam_img.max() > 1.0:
                    cam_img = cam_img / 255.0
            else:
                raise ValueError(
                    f"ACTAdapter.predict_with_outcome(): expected {key!r} to have 3 channels."
                )
            cam_images.append(cam_img)

        image = torch.from_numpy(np.stack(cam_images, axis=0)).float()
        image = image.to(self.device).unsqueeze(0)
        image = self._normalize(image)

        self._model.eval()
        with torch.no_grad():
            model_out = self._model(proprio, image, None)
            a_hat, _, _, outcome_hat = self._unpack_model_output(model_out)
        action = a_hat[:, 0].squeeze(0).cpu().numpy()
        action = action * self.norm_stats["action_std"] + self.norm_stats["action_mean"]
        outcome = None
        if outcome_hat is not None:
            outcome = outcome_hat.squeeze(0).detach().cpu().numpy().astype(np.float32)
        return action.astype(np.float32), outcome

    def _build_proprio(self, obs: dict) -> torch.Tensor:
        parts: list[np.ndarray] = []
        for key in self._low_dim_keys:
            if key not in obs:
                raise ValueError(
                    f"ACTAdapter.predict(): missing required low-dimensional input {key!r}."
                )
            value = np.asarray(obs[key], dtype=np.float32).reshape(-1)
            parts.append(value)
        if not parts:
            raise ValueError("ACTAdapter.predict(): low_dim_keys must not be empty.")
        proprio = np.concatenate(parts, axis=0).astype(np.float32)
        return torch.from_numpy(proprio).float().to(self.device).unsqueeze(0)

    def _resolve_proprio_norm_stats(self) -> tuple[torch.Tensor, torch.Tensor]:
        if "proprio_mean" in self.norm_stats and "proprio_std" in self.norm_stats:
            mean = self.norm_stats["proprio_mean"]
            std = self.norm_stats["proprio_std"]
        elif self._low_dim_keys == ["qpos"]:
            # Backward compatibility for older qpos-only checkpoints.
            mean = self.norm_stats["qpos_mean"]
            std = self.norm_stats["qpos_std"]
        else:
            raise KeyError(
                "dataset_stats.pkl does not contain proprio_mean/proprio_std for "
                f"low_dim_keys={self._low_dim_keys}. Recompute stats by retraining "
                "with the updated data pipeline."
            )
        return (
            torch.from_numpy(np.asarray(mean, dtype=np.float32)).to(self.device),
            torch.from_numpy(np.asarray(std, dtype=np.float32)).to(self.device),
        )

    def _aggregate(self, a_hat: torch.Tensor) -> np.ndarray:
        """
        Temporal aggregation from the ACT paper.
        a_hat shape: (1, C, Na)
        """
        chunk = a_hat.squeeze(0)
        num_queries, Na = chunk.shape
        if num_queries != self._num_queries:
            raise ValueError(
                "ACTAdapter._aggregate(): model query count changed from "
                f"{self._num_queries} to {num_queries}."
            )

        if (
            self._all_time_actions is None
            or self._all_time_actions.shape != (self._num_queries, self._num_queries, Na)
        ):
            self._all_time_actions = torch.zeros(
                [self._num_queries, self._num_queries, Na],
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

        # Weighted average of past chunks that cover step t.  The dense ACT
        # implementation reads rows in chronological order; preserve that order
        # while using only the rolling window that can still affect this step.
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
        action = (actions_for_curr_step * exp_weights).sum(0).cpu().numpy()
        return action

    # ── training forward ──────────────────────────────────────────────────────

    def forward_loss(
        self,
        proprio: torch.Tensor,
        image: torch.Tensor,
        actions: torch.Tensor,
        is_pad: torch.Tensor,
        outcome_target: torch.Tensor | None = None,
        outcome_mask: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """
        Training-time forward pass.

        Parameters
        ----------
        proprio (B, Np)
        image   (B, n_cams, C, H, W)   normalised
        actions (B, C, Na)
        is_pad  (B, C)  bool

        Returns
        -------
        {"l1": ..., "kl": ..., "loss": ...}
        """
        image   = self._normalize(image)
        actions = actions[:, : self._model.num_queries]
        is_pad  = is_pad[:,  : self._model.num_queries]

        model_out = self._model(proprio, image, None, actions, is_pad)
        a_hat, _, (mu, logvar), outcome_hat = self._unpack_model_output(model_out)
        total_kld, _, _        = _kl_divergence(mu, logvar)

        import torch.nn.functional as F
        all_l1 = F.l1_loss(actions, a_hat, reduction="none")
        l1     = (all_l1 * ~is_pad.unsqueeze(-1)).mean()
        loss = l1 + total_kld[0] * self.kl_weight

        zero = loss.new_tensor(0.0)
        outcome_loss = zero
        token_swap_outcome_loss = zero
        if outcome_hat is not None and outcome_target is not None:
            outcome_target = outcome_target.to(outcome_hat.device).float()
            if outcome_mask is None:
                outcome_mask = torch.ones_like(outcome_target, device=outcome_hat.device)
            else:
                outcome_mask = outcome_mask.to(outcome_hat.device).float()
            raw = F.smooth_l1_loss(outcome_hat, outcome_target, reduction="none")
            denom = outcome_mask.sum().clamp(min=1.0)
            outcome_loss = (raw * outcome_mask).sum() / denom
            loss = loss + outcome_loss * self.outcome_loss_weight

            if (
                self.token_swap_outcome_loss_weight > 0.0
                and proprio.shape[0] > 1
                and self._token_slice is not None
            ):
                swapped_proprio = self._swap_goal_token_in_batch(proprio)
                swapped_target = torch.roll(outcome_target, shifts=1, dims=0)
                swapped_mask = torch.roll(outcome_mask, shifts=1, dims=0)
                swap_out = self._model(swapped_proprio, image, None)
                _, _, _, swapped_outcome_hat = self._unpack_model_output(swap_out)
                if swapped_outcome_hat is not None:
                    raw_swap = F.smooth_l1_loss(
                        swapped_outcome_hat,
                        swapped_target,
                        reduction="none",
                    )
                    token_swap_outcome_loss = (
                        raw_swap * swapped_mask
                    ).sum() / swapped_mask.sum().clamp(min=1.0)
                    loss = loss + (
                        token_swap_outcome_loss
                        * self.token_swap_outcome_loss_weight
                    )

        return {
            "l1":   l1,
            "kl":   total_kld[0],
            "outcome": outcome_loss,
            "token_swap": token_swap_outcome_loss,
            "loss": loss,
        }

    def configure_optimizers(self):
        return self._optimizer

    def state_dict(self):
        return self._model.state_dict()

    def load_state_dict(self, sd, strict: bool = True):
        return self._model.load_state_dict(sd, strict=strict)

    @staticmethod
    def _unpack_model_output(model_out):
        if isinstance(model_out, tuple) and len(model_out) == 4:
            a_hat, is_pad_hat, latent, outcome_hat = model_out
            return a_hat, is_pad_hat, latent, outcome_hat
        a_hat, is_pad_hat, latent = model_out
        return a_hat, is_pad_hat, latent, None

    def _resolve_goal_token_slice(self) -> slice | None:
        start = 0
        for key in self._low_dim_keys:
            dim = self._low_dim_key_dim(key)
            if key in {
                "dig_cut_tokens",
                "dig_depth_profile_tokens_v1",
                "return_target_tokens",
                "return_relocate_tokens_v1",
                "return_start_envelope_tokens_v1",
                "goal_tokens",
            }:
                return slice(start, start + dim)
            start += dim
        return None

    def _low_dim_key_dim(self, key: str) -> int:
        if key in {
            "dig_cut_tokens",
            "return_target_tokens",
            "return_relocate_tokens_v1",
            "goal_tokens",
        }:
            return 10
        if key == "dig_depth_profile_tokens_v1":
            return int(DIG_DEPTH_PROFILE_TOKEN_DIM)
        if key == "return_start_envelope_tokens_v1":
            return 18
        if key == "cell_entry_tokens":
            return 10
        if key in {"qpos", "qvel"}:
            equipment_model = str(self.policy_config.get("equipment_model", "")).lower()
            if "bimanual" in equipment_model:
                return 14
            if (
                "excavator_simple" in equipment_model
                or "agxunity" in equipment_model
                or "agx" in equipment_model
                or "yulong" in equipment_model
            ):
                return 4
            return 7
        raise ValueError(f"Unsupported low_dim key {key!r}.")

    def _swap_goal_token_in_batch(self, proprio: torch.Tensor) -> torch.Tensor:
        if self._token_slice is None:
            return proprio
        mean = self._proprio_mean.to(proprio.device)
        std = self._proprio_std.to(proprio.device)
        unnorm = proprio * std + mean
        swapped = unnorm.clone()
        swapped[:, self._token_slice] = torch.roll(
            unnorm[:, self._token_slice],
            shifts=1,
            dims=0,
        )
        return (swapped - mean) / std

    # ── checkpoint helpers ────────────────────────────────────────────────────

    @classmethod
    def from_checkpoint(
        cls,
        ckpt_path: str | Path,
        policy_config: dict,
        norm_stats_path: str | Path,
        temporal_agg: bool = False,
        device: str = "cuda",
    ) -> "ACTAdapter":
        """
        Convenience factory: load an ACT policy from a checkpoint file.

        Parameters
        ----------
        ckpt_path       Path to policy_best.ckpt (or policy_epoch_N.ckpt).
        policy_config   Same config dict used during training.
        norm_stats_path Path to dataset_stats.pkl.
        """
        ckpt_path       = Path(ckpt_path)
        norm_stats_path = Path(norm_stats_path)

        with open(norm_stats_path, "rb") as f:
            norm_stats = pickle.load(f)

        adapter = cls(
            policy_config=policy_config,
            norm_stats=norm_stats,
            temporal_agg=temporal_agg,
            device=device,
        )

        raw = torch.load(ckpt_path, map_location="cpu")
        if isinstance(raw, dict) and "model_state_dict" in raw:
            sd = raw["model_state_dict"]
        elif isinstance(raw, dict):
            sd = raw
        else:
            raise ValueError(f"Unsupported checkpoint format: {type(raw)}")

        adapter.load_state_dict(sd)
        adapter._model.to(adapter.device)
        adapter._model.eval()
        return adapter
