__all__ = [
    "ACTActionChunk",
    "ACTAdapter",
    "ACTTrainer",
    "TemporalAggregationContract",
    "build_act_adapter_config",
    "describe_act_inference",
    "load_act_policy",
    "resolve_act_low_dim_state_dim",
]


def __getattr__(name: str):
    if name == "ACTAdapter":
        from testbed.policies.act.adapter import ACTAdapter

        return ACTAdapter
    if name == "ACTTrainer":
        from testbed.policies.act.trainer import ACTTrainer

        return ACTTrainer
    if name in {
        "ACTActionChunk",
        "TemporalAggregationContract",
        "build_act_adapter_config",
        "describe_act_inference",
        "load_act_policy",
        "resolve_act_low_dim_state_dim",
    }:
        from testbed.policies.act import inference

        return getattr(inference, name)
    raise AttributeError(name)
