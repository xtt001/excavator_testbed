"""Small graph encoder used by the graph-conditioned ACT branch."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


@dataclass(frozen=True)
class GraphEncoderConfig:
    node_feature_dim: int = 8
    edge_feature_dim: int = 5
    graph_global_dim: int = 6
    hidden_dim: int = 128
    output_dim: int = 64
    message_passing_steps: int = 2
    dropout: float = 0.0


class GraphEncoder(nn.Module):
    """Encode padded terrain graphs with lightweight message passing."""

    def __init__(self, config: GraphEncoderConfig):
        super().__init__()
        self.config = config
        hidden_dim = int(config.hidden_dim)
        self.message_passing_steps = max(1, int(config.message_passing_steps))
        self.node_proj = nn.Sequential(
            nn.Linear(int(config.node_feature_dim), hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.edge_proj = nn.Sequential(
            nn.Linear(int(config.edge_feature_dim), hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.global_proj = nn.Sequential(
            nn.Linear(int(config.graph_global_dim), hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.message_mlp = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(float(config.dropout)),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.update_mlp = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(float(config.dropout)),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.update_norm = nn.LayerNorm(hidden_dim)
        self.readout = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(float(config.dropout)),
            nn.Linear(hidden_dim, int(config.output_dim)),
            nn.LayerNorm(int(config.output_dim)),
        )

    def forward(self, graph: dict[str, torch.Tensor]) -> torch.Tensor:
        node_features = graph["node_features"].float()
        node_mask = graph["node_mask"].bool()
        edge_indices = graph["edge_indices"].long()
        edge_features = graph["edge_features"].float()
        edge_mask = graph["edge_mask"].bool()
        graph_globals = graph["graph_globals"].float()

        node_state = self.node_proj(node_features)
        edge_state = self.edge_proj(edge_features)
        global_state = self.global_proj(graph_globals)

        for _ in range(self.message_passing_steps):
            aggregated = _aggregate_messages(
                node_state=node_state,
                edge_state=edge_state,
                edge_indices=edge_indices,
                node_mask=node_mask,
                edge_mask=edge_mask,
                graph_global=global_state,
                message_mlp=self.message_mlp,
            )
            global_per_node = global_state.unsqueeze(1).expand_as(node_state)
            update_input = torch.cat([node_state, aggregated, global_per_node], dim=-1)
            updated = self.update_mlp(update_input)
            node_state = self.update_norm(node_state + updated)
            node_state = node_state * node_mask.to(dtype=node_state.dtype).unsqueeze(-1)

        node_summary = _masked_mean(node_state, node_mask)
        edge_summary = _masked_mean(edge_state, edge_mask)
        pooled = torch.cat([node_summary, edge_summary, global_state], dim=-1)
        return self.readout(pooled)


class ACTGraphModel(nn.Module):
    """Wrap an ACT model and prepend a graph embedding to proprioception."""

    def __init__(self, act_model: nn.Module, graph_encoder: GraphEncoder):
        super().__init__()
        self.act_model = act_model
        self.graph_encoder = graph_encoder
        self.num_queries = int(act_model.num_queries)

    def forward(
        self,
        proprio: torch.Tensor,
        image: torch.Tensor,
        env_state,
        graph: dict[str, torch.Tensor],
        actions: torch.Tensor | None = None,
        is_pad: torch.Tensor | None = None,
    ):
        graph_embedding = self.graph_encoder(graph)
        augmented_proprio = torch.cat([proprio, graph_embedding], dim=-1)
        return self.act_model(
            augmented_proprio,
            image,
            env_state,
            actions=actions,
            is_pad=is_pad,
        )


def _masked_mean(features: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.to(dtype=features.dtype).unsqueeze(-1)
    total = (features * weights).sum(dim=1)
    count = weights.sum(dim=1).clamp(min=1.0)
    return total / count


def _aggregate_messages(
    *,
    node_state: torch.Tensor,
    edge_state: torch.Tensor,
    edge_indices: torch.Tensor,
    node_mask: torch.Tensor,
    edge_mask: torch.Tensor,
    graph_global: torch.Tensor,
    message_mlp: nn.Module,
) -> torch.Tensor:
    batch_size, node_count, hidden_dim = node_state.shape
    edge_count = edge_state.shape[1]
    if edge_count == 0:
        return torch.zeros_like(node_state)

    src = edge_indices[..., 0].clamp(min=0, max=max(0, node_count - 1))
    dst = edge_indices[..., 1].clamp(min=0, max=max(0, node_count - 1))
    batch_index = torch.arange(batch_size, device=node_state.device).unsqueeze(1)
    src_state = node_state[batch_index, src]
    dst_state = node_state[batch_index, dst]
    global_per_edge = graph_global.unsqueeze(1).expand(-1, edge_count, -1)
    message_input = torch.cat([src_state, edge_state, global_per_edge], dim=-1)
    messages = message_mlp(message_input)

    valid_edges = (
        edge_mask
        & node_mask[batch_index, src]
        & node_mask[batch_index, dst]
    )
    weights = valid_edges.to(dtype=messages.dtype).unsqueeze(-1)
    messages = messages * weights

    aggregated = torch.zeros(
        batch_size,
        node_count,
        hidden_dim,
        dtype=messages.dtype,
        device=messages.device,
    )
    aggregated.scatter_add_(
        dim=1,
        index=dst.unsqueeze(-1).expand(-1, -1, hidden_dim),
        src=messages,
    )
    counts = torch.zeros(
        batch_size,
        node_count,
        1,
        dtype=messages.dtype,
        device=messages.device,
    )
    counts.scatter_add_(
        dim=1,
        index=dst.unsqueeze(-1),
        src=weights,
    )
    aggregated = aggregated / counts.clamp(min=1.0)
    return aggregated * node_mask.to(dtype=aggregated.dtype).unsqueeze(-1)
