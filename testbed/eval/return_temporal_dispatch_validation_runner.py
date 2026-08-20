"""No-overwrite source-disjoint validation runner for Return dispatch candidates.

The frozen checkpoint lineage is read from the Return stability *manifest* so
the runner can prove checkpoint/stat identity without reading the two failed
target-pair results.  Strategy selection itself receives only strict Return
training data and the source-balanced held-validation sample.
"""

from __future__ import annotations

import gc
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from testbed.data.return_temporal_dispatch_sampling import (
    build_source_balanced_return_temporal_dispatch_sample,
)
from testbed.data.return_temporal_dispatch_validation import (
    load_strict_return_temporal_dispatch_validation_population,
)
from testbed.eval.return_goal_response_stability_contract import (
    RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA,
)
from testbed.eval.return_temporal_dispatch_validation_eval import (
    RETURN_TEMPORAL_DISPATCH_VALIDATION_EVALUATION_SCHEMA,
    evaluate_return_temporal_dispatch_validation,
)
from testbed.policies.act.inference import (
    build_act_adapter_config,
    load_act_policy,
)
from testbed.runtime.torch_performance import (
    configure_torch_performance,
    eval_torch_performance_config,
)

RETURN_TEMPORAL_DISPATCH_VALIDATION_MANIFEST_SCHEMA = (
    "return_temporal_dispatch_validation_manifest_v1"
)
RETURN_TEMPORAL_DISPATCH_CANDIDATES_SCHEMA = "return_temporal_dispatch_candidates_v1"
RETURN_TEMPORAL_DISPATCH_VALIDATION_ARTIFACT_SCHEMA = (
    "return_temporal_dispatch_validation_artifact_v1"
)

EvaluationRunner = Callable[..., Mapping[str, Any]]


def run_return_temporal_dispatch_validation_from_file(
    *,
    return_training_config_path: str | Path,
    checkpoint_lineage_manifest_path: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    evaluation_runner: EvaluationRunner | None = None,
    policy_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Freeze a Return dispatch shadow candidate from held validation only.

    ``checkpoint_lineage_manifest_path`` points at a prior stability manifest;
    this runner reads only its source checkpoint/stat/config records.  It never
    opens that artifact's failed-pair results, and the evaluator accepts no
    Stage-A root or target frames.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"Return temporal-dispatch validation output already exists: {destination}"
        )
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("Return temporal-dispatch validation requires a clean Git worktree")

    lineage_manifest_path = Path(checkpoint_lineage_manifest_path).expanduser().resolve(
        strict=True
    )
    checkpoint_lineage = _load_checkpoint_lineage(lineage_manifest_path)
    training_path = Path(return_training_config_path).expanduser().resolve(strict=True)
    _verify_record(
        checkpoint_lineage["return_training_config"],
        training_path,
        "Return training config",
    )
    population = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=training_path
    )
    sample = build_source_balanced_return_temporal_dispatch_sample(population)
    performance = eval_torch_performance_config(
        checkpoint_lineage["eval_config"].get("eval", {})
    )
    configure_torch_performance(performance, device=str(device))
    _verify_performance(
        checkpoint_lineage["manifest"].get("torch_performance"),
        performance.as_config_dict(),
    )

    owned_pool: _ReturnPolicyPool | None = None
    if policy_factory is None:
        owned_pool = _ReturnPolicyPool(
            eval_config=checkpoint_lineage["eval_config"],
            checkpoint=checkpoint_lineage["checkpoint"],
            stats=checkpoint_lineage["stats"],
            device=str(device),
        )
        factory = owned_pool.factory
    else:
        factory = policy_factory
    try:
        evaluator = evaluation_runner or evaluate_return_temporal_dispatch_validation
        evaluation = evaluator(
            population=population,
            sample=sample,
            policy_factory=factory,
        )
    finally:
        if owned_pool is not None:
            owned_pool.close()
    _validate_evaluation(evaluation)

    selected = _selection(evaluation).get("selected_strategy_id")
    status = "completed" if selected else "dispatch_contract_not_selected"
    source_lineage = {
        "checkpoint_lineage_manifest": _source_record(lineage_manifest_path),
        "return_training_config": _source_record(training_path),
        "return_checkpoint": _source_record(checkpoint_lineage["checkpoint"]),
        "return_dataset_stats": _source_record(checkpoint_lineage["stats"]),
        "eval_resolved_config": _source_record(checkpoint_lineage["eval_config_path"]),
        "source_aware_split": _source_record(Path(population.split_path)),
        "primitive_dataset_dir": _directory_record(Path(population.primitive_dataset_dir)),
        "code": clean_code,
    }
    manifest = {
        "schema": RETURN_TEMPORAL_DISPATCH_VALIDATION_MANIFEST_SCHEMA,
        "status": status,
        "evidence_kind": evaluation["evidence_kind"],
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "runtime_default_changed": False,
        "target_stage_a_failures_used": False,
        "source_lineage": source_lineage,
        "selected_strategy_id": selected,
        "selection": _selection(evaluation),
        "artifact_files": {
            "candidates": "candidates.json",
            "validation": "validation.json",
            "report": "report.md",
        },
    }
    candidates = {
        "schema": RETURN_TEMPORAL_DISPATCH_CANDIDATES_SCHEMA,
        "primitive": "return",
        "target_stage_a_failures_used": False,
        "strategies": evaluation["strategies"],
        "selected_strategy_id": selected,
        "selection": _selection(evaluation),
    }
    validation = {
        "schema": RETURN_TEMPORAL_DISPATCH_VALIDATION_ARTIFACT_SCHEMA,
        "primitive": "return",
        "target_stage_a_failures_used": False,
        "input_scope": evaluation["input_scope"],
        "sample": evaluation["sample"],
        "metric_contract": evaluation["metric_contract"],
        "policy_verification": evaluation["policy_verification"],
        "selection": _selection(evaluation),
        "interpretation_limit": evaluation["interpretation_limit"],
    }
    report = _render_report(status=status, evaluation=evaluation)

    destination.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(destination / "manifest.json", manifest)
    _write_json_exclusive(destination / "candidates.json", candidates)
    _write_json_exclusive(destination / "validation.json", validation)
    _write_text_exclusive(destination / "report.md", report)
    return {
        "status": status,
        "output_root": str(destination),
        "selected_strategy_id": selected,
        "manifest": manifest,
    }


class _ReturnPolicyPool:
    """Keep four independent public ACT temporal states for held replay."""

    _STREAM_SUFFIXES = frozenset(
        {
            "baseline_primary",
            "baseline_replica",
            "alternate_primary",
            "alternate_replica",
        }
    )

    def __init__(
        self,
        *,
        eval_config: Mapping[str, Any],
        checkpoint: Path,
        stats: Path,
        device: str,
    ) -> None:
        policy = _mapping(eval_config.get("policy"), "resolved Return eval policy")
        task = _mapping(eval_config.get("task"), "resolved Return eval task")
        self._config = build_act_adapter_config(
            config=eval_config,
            camera_names=[str(value) for value in task["camera_names"]],
            equipment_model=str(task["equipment_model"]),
            max_episode_len=int(task["episode_len"]),
            low_dim_keys=[str(value) for value in policy["return_low_dim_keys"]],
            act_params=_mapping(policy.get("act_params"), "resolved Return ACT params"),
            outcome_head_config=dict(policy.get("return_outcome_head", {}) or {}),
            image_mask_config=dict(policy.get("image_mask", {}) or {}),
        )
        self._checkpoint = checkpoint
        self._stats = stats
        self._device = device
        self._policies: dict[str, Any] = {}

    def factory(self, label: str) -> Any:
        suffix = str(label).rsplit(":", 1)[-1]
        if suffix not in self._STREAM_SUFFIXES:
            raise ValueError(f"unknown Return temporal stream suffix {suffix!r}")
        policy = self._policies.get(suffix)
        if policy is None:
            policy = load_act_policy(
                ckpt_path=self._checkpoint,
                policy_config=self._config,
                norm_stats_path=self._stats,
                temporal_agg=True,
                device=self._device,
            )
            self._policies[suffix] = policy
        return policy

    def close(self) -> None:
        self._policies.clear()
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


def _load_checkpoint_lineage(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json_mapping(manifest_path)
    if manifest.get("schema") != RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA:
        raise ValueError("checkpoint lineage manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise ValueError("checkpoint lineage manifest is not completed")
    if (
        manifest.get("diagnostic_only") is not True
        or manifest.get("promotion_eligible") is not False
        or manifest.get("closed_loop_claim") is not False
    ):
        raise ValueError("checkpoint lineage evidence boundary mismatch")
    lineage = _mapping(manifest.get("source_lineage"), "checkpoint lineage")
    checkpoint = _record_path(lineage.get("return_checkpoint"), "Return checkpoint")
    stats = _record_path(lineage.get("return_dataset_stats"), "Return stats")
    training = _mapping(lineage.get("return_training_config"), "Return training record")
    config_path = _record_path(lineage.get("eval_resolved_config"), "resolved eval config")
    _verify_record(_mapping(lineage.get("return_checkpoint"), "Return checkpoint"), checkpoint, "Return checkpoint")
    _verify_record(_mapping(lineage.get("return_dataset_stats"), "Return stats"), stats, "Return stats")
    _verify_record(training, _record_path(training, "Return training config"), "Return training config")
    _verify_record(
        _mapping(lineage.get("eval_resolved_config"), "resolved eval config"),
        config_path,
        "resolved eval config",
    )
    return {
        "manifest": manifest,
        "checkpoint": checkpoint,
        "stats": stats,
        "return_training_config": training,
        "eval_config_path": config_path,
        "eval_config": _load_yaml_mapping(config_path),
    }


def _verify_performance(stored: Any, resolved: Mapping[str, Any]) -> None:
    value = _mapping(stored, "frozen Return torch performance")
    required = {"allow_tf32", "cudnn_benchmark", "matmul_precision"}
    if not required <= set(value):
        raise ValueError("frozen Return torch performance is incomplete")
    if {key: value[key] for key in required} != {
        key: resolved[key] for key in required
    }:
        raise ValueError("current Return torch performance differs from frozen replay")


def _validate_evaluation(evaluation: Mapping[str, Any]) -> None:
    if evaluation.get("schema") != RETURN_TEMPORAL_DISPATCH_VALIDATION_EVALUATION_SCHEMA:
        raise ValueError("Return temporal-dispatch evaluation schema mismatch")
    if (
        evaluation.get("diagnostic_only") is not True
        or evaluation.get("promotion_eligible") is not False
        or evaluation.get("closed_loop_claim") is not False
        or evaluation.get("target_stage_a_failures_used") is not False
        or evaluation.get("runtime_default_changed") is not False
    ):
        raise ValueError("Return temporal-dispatch evaluation boundary mismatch")
    _selection(evaluation)


def _selection(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    return dict(_mapping(evaluation.get("selection"), "Return temporal selection"))


def _render_report(*, status: str, evaluation: Mapping[str, Any]) -> str:
    selection = _selection(evaluation)
    lines = [
        "# Return temporal dispatch 合同验证",
        "",
        f"- 状态：`{status}`",
        f"- 选中的 opt-in shadow 候选：`{selection.get('selected_strategy_id')}`",
        "- 验证只覆盖固定的 source-balanced held Return 样本；两段 Stage-A 失败样本未参与选择。",
        "- 默认 runtime 未改变；即使选中候选，也只能进入后续 Unity/闭环影子验证。",
        "",
        "| strategy | aggregate response | every pair >=80% | quality no worse | selectable |",
        "|---|---:|---:|---:|---:|",
    ]
    strategies = _mapping(evaluation.get("strategies"), "Return strategies")
    for strategy_id, result in strategies.items():
        if not isinstance(result, Mapping):
            continue
        aggregate = _mapping(result.get("aggregate"), "strategy aggregate")
        response = _mapping(aggregate.get("response"), "strategy response")
        gates = _mapping(result.get("pre_registered_gates"), "strategy gates")
        lines.append(
            "| {id} | {fraction:.6f} | {pairs} | {quality} | {selectable} |".format(
                id=strategy_id,
                fraction=float(response.get("active_frame_fraction", 0.0)),
                pairs=bool(gates.get("every_pair_reaches_fixed_80_percent_response")),
                quality=bool(gates.get("quality_is_no_worse_than_legacy")),
                selectable=bool(result.get("passes_pre_registered_selection")),
            )
        )
    lines.extend(
        [
            "",
            "结果不证明桶轨迹、地形残差、安全或生产可用性。",
            "",
        ]
    )
    return "\n".join(lines)


def _record_path(value: Any, label: str) -> Path:
    record = _mapping(value, label)
    return Path(str(record.get("path", ""))).expanduser().resolve(strict=True)


def _verify_record(record: Mapping[str, Any], path: Path, label: str) -> None:
    if Path(str(record.get("path", ""))).expanduser().resolve(strict=True) != path:
        raise ValueError(f"{label} path does not match its lineage")
    if str(record.get("sha256", "")) != _sha256(path):
        raise ValueError(f"{label} SHA does not match its lineage")
    if int(record.get("size_bytes", -1)) != path.stat().st_size:
        raise ValueError(f"{label} size does not match its lineage")


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": int(path.stat().st_size),
    }


def _directory_record(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(resolved)
    return {"path": str(resolved)}


def _load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    return dict(_mapping(payload, str(path)))


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(_mapping(payload, str(path)))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=False, capture_output=True, text=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


__all__ = [
    "RETURN_TEMPORAL_DISPATCH_CANDIDATES_SCHEMA",
    "RETURN_TEMPORAL_DISPATCH_VALIDATION_ARTIFACT_SCHEMA",
    "RETURN_TEMPORAL_DISPATCH_VALIDATION_MANIFEST_SCHEMA",
    "run_return_temporal_dispatch_validation_from_file",
]
