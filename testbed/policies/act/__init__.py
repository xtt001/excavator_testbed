__all__ = [
    "ACTActionChunk",
    "ACTAdapter",
    "ACTTrainer",
    "ACTImagePreprocessingResult",
    "ACTImageTransformResult",
    "TemporalAggregationContract",
    "build_act_adapter_config",
    "describe_act_inference",
    "load_act_policy",
    "resolve_act_low_dim_state_dim",
    "preprocess_act_observation_images",
    "transform_act_camera_images",
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
    if name in {
        "ACTImagePreprocessingResult",
        "ACTImageTransformResult",
        "preprocess_act_observation_images",
        "transform_act_camera_images",
    }:
        from testbed.policies.act import image_preprocessing

        return getattr(image_preprocessing, name)
    raise AttributeError(name)
