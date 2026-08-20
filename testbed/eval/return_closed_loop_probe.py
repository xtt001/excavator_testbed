"""Bounded Return-only Unity causal probe.

The runner is deliberately request-local.  It accepts a frozen four-fixture,
sixteen-arm contract, verifies every arm before any non-zero command, and then
executes only the Return policy.  It never invokes the primitive planner and
therefore cannot transition into Dig, Carry, or Dump.

``latest_current_chunk_diagnostic`` is a causal diagnostic control.  It calls
``predict_action_chunk(...).first_action`` on every frame and is never a
candidate runtime default.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.eval.return_closed_loop_artifacts import (
    json_safe as _json_safe,
)
from testbed.eval.return_closed_loop_artifacts import (
    render_return_closed_loop_report as _render_report,
)
from testbed.eval.return_closed_loop_artifacts import (
    write_json_exclusive as _write_json_x,
)
from testbed.eval.return_closed_loop_artifacts import (
    write_jsonl_exclusive as _write_jsonl_x,
)
from testbed.eval.return_closed_loop_artifacts import (
    write_text_exclusive as _write_text_x,
)
from testbed.eval.return_closed_loop_causal_contract import (
    return_target_envelope_from_token,
)
from testbed.eval.return_closed_loop_preflight import (
    ReturnClosedLoopPreflightError,
)
from testbed.eval.return_closed_loop_preflight import (
    clean_code_record as _clean_code_record,
)
from testbed.eval.return_closed_loop_preflight import (
    finite_vector as _finite_vector,
)
from testbed.eval.return_closed_loop_preflight import (
    fixture_application_blockers as _fixture_application_blockers,
)
from testbed.eval.return_closed_loop_preflight import (
    get_info_blockers as _info_blockers,
)
from testbed.eval.return_closed_loop_preflight import (
    mapping_record as _mapping_record,
)
from testbed.eval.return_closed_loop_preflight import (
    object_record as _object_record,
)
from testbed.eval.return_closed_loop_preflight import (
    observation as _observation,
)
from testbed.eval.return_closed_loop_preflight import (
    prepare_return_fixture as _prepare_fixture,
)
from testbed.eval.return_closed_loop_preflight import (
    request_neutral_step_ack as _neutral_ack,
)
from testbed.eval.return_closed_loop_preflight import (
    static_preflight_blockers as _static_preflight_blockers,
)
from testbed.eval.return_closed_loop_preflight import (
    step_action_telemetry as _step_action_telemetry,
)
from testbed.eval.return_closed_loop_results import (
    evaluate_return_closed_loop_results,
)
from testbed.eval.return_closed_loop_safety import (
    RETURN_ACTION_DIM,
    ReturnClosedLoopSafetyAdapter,
    ReturnProbeSafetyDecision,
)
from testbed.eval.return_closed_loop_safety import (
    project_return_probe_safety_decision as _project_safety_decision,
)
from testbed.eval.temporal_dispatch_contract import (
    pre_registered_temporal_dispatch_strategies,
    temporal_dispatch_contributors_for_frame,
)

PROBE_SCHEMA = "strict18_return_closed_loop_probe_v1"
PREFLIGHT_SCHEMA = "strict18_return_closed_loop_preflight_v1"
ARMS_SCHEMA = "strict18_return_closed_loop_arms_v1"
TRACE_SCHEMA = "strict18_return_closed_loop_trace_v1"
ARM_SUMMARY_SCHEMA = "strict18_return_closed_loop_arm_summary_v1"

LEGACY_STRATEGY_ID = "legacy_100_oldest_first_decay_0p01"
LATEST_CURRENT_STRATEGY_ID = "latest_current_chunk_diagnostic"
RETURN_TOKEN_KEY = "return_start_envelope_tokens_v1"
RETURN_MAX_STEPS = 420
RETURN_ARM_COUNT = 16
RETURN_FIXTURE_COUNT = 4
RETURN_TOKEN_DIM = 18

BackendFactory = Callable[[Mapping[str, Any]], Any]
PolicyFactory = Callable[[Mapping[str, Any]], Any]
SafetyFactory = Callable[[Mapping[str, Any]], Any]
HandoffEvaluator = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]
GitStateProvider = Callable[[], Mapping[str, Any]]
ResultEvaluator = Callable[..., Mapping[str, Any]]


ReturnClosedLoopProbeError = ReturnClosedLoopPreflightError


def run_return_closed_loop_probe(
    *,
    causal_contract: Any,
    fixture_set: Any,
    runtime_lock: Mapping[str, Any],
    output_root: str | Path,
    execute: bool = False,
    backend_factory: BackendFactory,
    policy_factory: PolicyFactory,
    safety_factory: SafetyFactory | None = None,
    handoff_evaluator: HandoffEvaluator | None = None,
    git_state_provider: GitStateProvider | None = None,
    result_evaluator: ResultEvaluator | None = None,
) -> dict[str, Any]:
    """Preflight and optionally execute the frozen sixteen-arm matrix.

    Backend, policy, safety, and handoff ownership are injected so focused
    tests can prove that no planner transition or hidden retry is possible.
    A backend may implement ``prepare_fixture(fixture)``.  Otherwise the helper
    uses ``reset`` followed by ``realign_pose`` and requires an explicit
    positive qvel acknowledgement in the returned warnings.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"Return closed-loop probe output already exists: {destination}"
        )

    contract, arms = _validate_contract(causal_contract)
    frozen_set, fixtures = _validate_fixture_set(fixture_set)
    lock = _validate_runtime_lock(runtime_lock, frozen_set=frozen_set)
    contexts = _build_arm_contexts(arms, fixtures=fixtures, runtime_lock=lock)

    destination.mkdir(parents=True, exist_ok=False)
    git_state = dict((git_state_provider or _clean_code_record)())
    static_blockers = _static_preflight_blockers(
        git_state=git_state,
        runtime_lock=lock,
        fixture_source_lineage=_mapping_record(
            frozen_set.get("source_lineage", {}),
            "fixture_set.source_lineage",
        ),
    )
    preflight_arms: list[dict[str, Any]] = []
    if not static_blockers:
        for context in contexts:
            preflight_arms.append(
                _preflight_arm(
                    context,
                    backend_factory=backend_factory,
                    runtime_lock=lock,
                )
            )
    preflight_blockers = list(static_blockers)
    for record in preflight_arms:
        preflight_blockers.extend(
            f"{record['arm_id']}:{reason}"
            for reason in record["blockers"]
        )
    preflight_passed = not preflight_blockers
    qvel_confirmed = bool(preflight_arms) and all(
        record["qvel_fixture_application_confirmed"]
        for record in preflight_arms
    )
    preflight = {
        "schema": PREFLIGHT_SCHEMA,
        "status": "passed" if preflight_passed else "blocked",
        "execution_requested": bool(execute),
        "git": _json_safe(git_state),
        "runtime_lock": _manifest_runtime_lock(lock),
        "arm_count": RETURN_ARM_COUNT,
        "all_arms_checked_before_nonzero_action": bool(preflight_arms)
        and len(preflight_arms) == RETURN_ARM_COUNT,
        "qpos_fixture_application_confirmed": bool(preflight_arms)
        and all(
            record["qpos_fixture_application_confirmed"]
            for record in preflight_arms
        ),
        "qvel_fixture_application_confirmed": qvel_confirmed,
        "nonzero_action_count": 0,
        "blockers": preflight_blockers,
        "arms": preflight_arms,
    }
    _write_json_x(destination / "preflight.json", preflight)

    safety_builder = safety_factory or (
        lambda _arm: ReturnClosedLoopSafetyAdapter()
    )
    handoff = handoff_evaluator or (
        lambda _obs, _arm: {"would_handoff": False}
    )
    if not preflight_passed:
        arm_records = [
            _not_executed_arm(context, status="preflight_blocked")
            for context in contexts
        ]
        status = "preflight_blocked"
    elif not execute:
        arm_records = [
            _not_executed_arm(context, status="preflight_only")
            for context in contexts
        ]
        status = "preflight_passed"
    else:
        arm_records = []
        for context in contexts:
            arm_records.append(
                _execute_arm(
                    context,
                    destination=destination,
                    backend_factory=backend_factory,
                    policy_factory=policy_factory,
                    safety_factory=safety_builder,
                    handoff_evaluator=handoff,
                    runtime_lock=lock,
                )
            )
        status = (
            "completed"
            if all(
                record["executed"]
                and record["neutral_acknowledged"]
                for record in arm_records
            )
            else "execution_incomplete"
        )

    nonzero_count = sum(
        int(record.get("nonzero_action_count", 0)) for record in arm_records
    )
    results: dict[str, Any]
    if execute and preflight_passed:
        evaluator = result_evaluator or evaluate_return_closed_loop_results
        try:
            results = dict(
                evaluator(
                    output_root=destination,
                    arms=arm_records,
                    action_discontinuity_threshold=lock[
                        "action_discontinuity_threshold"
                    ],
                )
            )
        except Exception as exc:
            status = "execution_incomplete"
            results = {
                "status": "artifact_invalid",
                "reason": f"result_evaluation_exception:{type(exc).__name__}",
            }
    else:
        results = {
            "status": "not_evaluated",
            "reason": (
                "preflight_blocked"
                if not preflight_passed
                else "preflight_only"
            ),
        }
    _write_json_x(destination / "results.json", results)
    arms_artifact = {
        "schema": ARMS_SCHEMA,
        "status": status,
        "arm_count": RETURN_ARM_COUNT,
        "retry_allowed": False,
        "max_steps_per_arm": RETURN_MAX_STEPS,
        "nonzero_action_count": nonzero_count,
        "arms": arm_records,
    }
    _write_json_x(destination / "arms.json", arms_artifact)
    manifest = {
        "schema": PROBE_SCHEMA,
        "status": status,
        "execution_requested": bool(execute),
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": bool(execute and status == "completed"),
        "runtime_default_changed": False,
        "allowed_primitive": "return",
        "dig_or_dump_invocation_allowed": False,
        "arm_count": RETURN_ARM_COUNT,
        "max_steps_per_arm": RETURN_MAX_STEPS,
        "max_attempts_per_arm": 1,
        "retry_allowed": False,
        "nonzero_action_count": nonzero_count,
        "dispatch_strategy_ids": [
            LEGACY_STRATEGY_ID,
            LATEST_CURRENT_STRATEGY_ID,
        ],
        "latest_current_chunk_is_diagnostic_only": True,
        "source_contract_schema": contract.get("schema", ""),
        "fixture_source_lineage": _json_safe(
            frozen_set.get("source_lineage", {})
        ),
        "artifact_files": {
            "preflight": "preflight.json",
            "arms": "arms.json",
            "results": "results.json",
            "arm_summaries": "arms/<arm_id>/summary.json",
            "arm_traces": "arms/<arm_id>/trace.jsonl",
            "report": "report.md",
        },
    }
    _write_json_x(destination / "manifest.json", manifest)
    _write_text_x(
        destination / "report.md",
        _render_report(manifest=manifest, preflight=preflight, arms=arm_records),
    )
    return {
        "status": status,
        "output_root": str(destination),
        "arm_count": RETURN_ARM_COUNT,
        "nonzero_action_count": nonzero_count,
        "manifest": manifest,
        "results": results,
    }


def _validate_contract(value: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = dict(_mapping_record(value, "causal_contract"))
    strategies = contract.get("dispatch_strategies")
    if strategies is not None:
        strategy_records = _mapping_record(
            strategies, "causal_contract.dispatch_strategies"
        )
        expected_apis = {
            LEGACY_STRATEGY_ID: "predict.legacy_temporal_aggregation",
            LATEST_CURRENT_STRATEGY_ID: (
                "predict_action_chunk.first_action_each_frame"
            ),
        }
        if set(strategy_records) != set(expected_apis):
            raise ReturnClosedLoopProbeError("dispatch strategy inventory drifted")
        for strategy_id, dispatch_api in expected_apis.items():
            record = _mapping_record(
                strategy_records[strategy_id], f"strategy {strategy_id}"
            )
            if record.get("dispatch_api") != dispatch_api:
                raise ReturnClosedLoopProbeError(
                    f"{strategy_id}: dispatch_api drifted"
                )
    raw_arms = contract.get("arms")
    if not isinstance(raw_arms, Sequence) or isinstance(raw_arms, (str, bytes)):
        raise ReturnClosedLoopProbeError("causal_contract.arms must be a sequence")
    arms = [dict(_mapping_record(item, "causal arm")) for item in raw_arms]
    if len(arms) != RETURN_ARM_COUNT:
        raise ReturnClosedLoopProbeError(
            f"causal contract must contain exactly {RETURN_ARM_COUNT} arms"
        )
    if contract.get("diagnostic_only") is not True:
        raise ReturnClosedLoopProbeError("causal contract must be diagnostic_only")
    if contract.get("promotion_eligible") is not False:
        raise ReturnClosedLoopProbeError(
            "causal contract must set promotion_eligible=false"
        )
    expected: set[tuple[str, str, str]] = set()
    fixture_ids = {str(arm.get("fixture_id", "")) for arm in arms}
    if len(fixture_ids) != RETURN_FIXTURE_COUNT or "" in fixture_ids:
        raise ReturnClosedLoopProbeError(
            f"causal contract must name exactly {RETURN_FIXTURE_COUNT} fixtures"
        )
    for fixture_id in fixture_ids:
        for role in ("original", "alternate"):
            for strategy in (LEGACY_STRATEGY_ID, LATEST_CURRENT_STRATEGY_ID):
                expected.add((fixture_id, role, strategy))
    observed: set[tuple[str, str, str]] = set()
    arm_ids: set[str] = set()
    for arm in arms:
        arm_id = str(arm.get("arm_id", ""))
        fixture_id = str(arm.get("fixture_id", ""))
        target_role = str(arm.get("target_role", ""))
        strategy = str(arm.get("dispatch_strategy_id", ""))
        if not arm_id or arm_id in arm_ids:
            raise ReturnClosedLoopProbeError("arm_id must be unique and non-empty")
        arm_ids.add(arm_id)
        if arm.get("max_steps") != RETURN_MAX_STEPS:
            raise ReturnClosedLoopProbeError(
                f"{arm_id}: max_steps must be {RETURN_MAX_STEPS}"
            )
        if arm.get("no_retry") is not True:
            raise ReturnClosedLoopProbeError(f"{arm_id}: no_retry must be true")
        if arm.get("allowed_primitive") != "return":
            raise ReturnClosedLoopProbeError(
                f"{arm_id}: allowed_primitive must be return"
            )
        observed.add((fixture_id, target_role, strategy))
    if observed != expected:
        raise ReturnClosedLoopProbeError("causal contract is not the frozen 4x2x2 matrix")
    return contract, arms


def _validate_fixture_set(
    value: Any,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    fixture_set = dict(_mapping_record(value, "fixture_set"))
    cameras = tuple(str(item) for item in fixture_set.get("camera_names", ()))
    if len(cameras) != 4 or len(set(cameras)) != 4:
        raise ReturnClosedLoopProbeError("fixture_set must freeze four cameras")
    raw_fixtures = fixture_set.get("fixtures")
    if not isinstance(raw_fixtures, Sequence) or isinstance(
        raw_fixtures, (str, bytes)
    ):
        raise ReturnClosedLoopProbeError("fixture_set.fixtures must be a sequence")
    fixtures: dict[str, dict[str, Any]] = {}
    for raw in raw_fixtures:
        fixture = dict(_mapping_record(raw, "Return fixture"))
        fixture_id = str(fixture.get("fixture_id", ""))
        if not fixture_id or fixture_id in fixtures:
            raise ReturnClosedLoopProbeError("fixture_id must be unique and non-empty")
        initial = dict(
            _mapping_record(
                fixture.get("initial_observation"),
                f"{fixture_id}.initial_observation",
            )
        )
        _finite_vector(initial.get("qpos"), RETURN_ACTION_DIM, f"{fixture_id}.qpos")
        _finite_vector(initial.get("qvel"), RETURN_ACTION_DIM, f"{fixture_id}.qvel")
        _finite_vector(
            initial.get("env_state"), ENV_STATE_V2_4_DIM, f"{fixture_id}.env_state"
        )
        fixture["initial_observation"] = initial
        targets = fixture.get("targets", {})
        if targets and not isinstance(targets, Mapping):
            raise ReturnClosedLoopProbeError(
                f"{fixture_id}.targets must be a mapping"
            )
        for role in ("original", "alternate"):
            field = f"{role}_target"
            target = dict(
                _mapping_record(
                    fixture.get(field, targets.get(role)),
                    f"{fixture_id}.{field}",
                )
            )
            if str(target.get("target_role", "")) != role:
                raise ReturnClosedLoopProbeError(
                    f"{fixture_id}.{field}.target_role mismatch"
                )
            token = _finite_vector(
                target.get("token"), RETURN_TOKEN_DIM, f"{fixture_id}.{field}.token"
            )
            token_sha = hashlib.sha256(
                token.astype(np.float32).tobytes()
            ).hexdigest()
            if str(target.get("token_sha256", "")) != token_sha:
                raise ReturnClosedLoopProbeError(
                    f"{fixture_id}.{field}.token_sha256 mismatch"
                )
            target["token"] = token.astype(float).tolist()
            fixture[field] = target
        fixtures[fixture_id] = fixture
    if len(fixtures) != RETURN_FIXTURE_COUNT:
        raise ReturnClosedLoopProbeError(
            f"fixture_set must contain exactly {RETURN_FIXTURE_COUNT} fixtures"
        )
    return fixture_set, fixtures


def _validate_runtime_lock(
    value: Mapping[str, Any],
    *,
    frozen_set: Mapping[str, Any],
) -> dict[str, Any]:
    lock = dict(_mapping_record(value, "runtime_lock"))
    required_text = ("source_sha", "runtime_build_id", "scene_id", "scene_sha256")
    for field in required_text:
        if not str(lock.get(field, "")).strip():
            raise ReturnClosedLoopProbeError(f"runtime_lock.{field} is required")
    if len(str(lock["source_sha"])) != 40:
        raise ReturnClosedLoopProbeError("runtime_lock.source_sha must be a Git SHA")
    if len(str(lock["scene_sha256"])) != 64:
        raise ReturnClosedLoopProbeError("runtime_lock.scene_sha256 must be SHA-256")
    for field in ("camera_names", "action_order", "qpos_order", "qvel_order"):
        values = lock.get(field)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ReturnClosedLoopProbeError(f"runtime_lock.{field} must be a sequence")
        lock[field] = [str(item) for item in values]
    if lock["camera_names"] != [
        str(item) for item in frozen_set.get("camera_names", ())
    ]:
        raise ReturnClosedLoopProbeError(
            "runtime camera order disagrees with frozen fixture set"
        )
    for field in (
        "return_checkpoint",
        "return_stats",
        "return_training_config",
        "stage_a_v3_manifest",
        "return_validation",
    ):
        record = dict(_mapping_record(lock.get(field), f"runtime_lock.{field}"))
        if not str(record.get("path", "")) or len(str(record.get("sha256", ""))) != 64:
            raise ReturnClosedLoopProbeError(
                f"runtime_lock.{field} requires path and sha256"
            )
        lock[field] = record
    for field in ("qpos_atol", "qvel_atol"):
        tolerance = float(lock.get(field, 1.0e-6))
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise ReturnClosedLoopProbeError(f"runtime_lock.{field} is invalid")
        lock[field] = tolerance
    threshold = _finite_vector(
        lock.get("action_discontinuity_threshold"),
        RETURN_ACTION_DIM,
        "runtime_lock.action_discontinuity_threshold",
    )
    if np.any(threshold <= 0.0):
        raise ReturnClosedLoopProbeError(
            "runtime_lock.action_discontinuity_threshold must be positive"
        )
    lock["action_discontinuity_threshold"] = threshold.astype(float).tolist()
    return lock


def _build_arm_contexts(
    arms: Sequence[Mapping[str, Any]],
    *,
    fixtures: Mapping[str, Mapping[str, Any]],
    runtime_lock: Mapping[str, Any],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for arm in arms:
        fixture_id = str(arm["fixture_id"])
        if fixture_id not in fixtures:
            raise ReturnClosedLoopProbeError(
                f"arm references unknown fixture {fixture_id}"
            )
        fixture = dict(fixtures[fixture_id])
        target = dict(fixture[f"{arm['target_role']}_target"])
        other_role = (
            "alternate" if arm["target_role"] == "original" else "original"
        )
        other_target = dict(fixture[f"{other_role}_target"])
        declared_sha = arm.get(
            "target_token_sha256",
            arm.get("token_sha", arm.get("token_sha256")),
        )
        if declared_sha is not None and str(declared_sha) != str(
            target["token_sha256"]
        ):
            raise ReturnClosedLoopProbeError(
                f"{arm['arm_id']}: target token SHA mismatch"
            )
        contexts.append(
            {
                **dict(arm),
                "fixture": fixture,
                "target": target,
                "other_target": other_target,
                "target_envelope": _json_safe(
                    arm.get("target_envelope")
                    or return_target_envelope_from_token(target["token"])
                ),
                "other_target_envelope": _json_safe(
                    return_target_envelope_from_token(other_target["token"])
                ),
                "return_checkpoint": dict(runtime_lock["return_checkpoint"]),
                "return_stats": dict(runtime_lock["return_stats"]),
            }
        )
    return contexts


def _preflight_arm(
    context: Mapping[str, Any],
    *,
    backend_factory: BackendFactory,
    runtime_lock: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    backend = None
    prepared: dict[str, Any] = {}
    info: dict[str, Any] = {}
    neutral = {"acknowledged": False, "step_id": None}
    try:
        backend = backend_factory(context)
        info = _object_record(backend.get_info())
        blockers.extend(_info_blockers(info, runtime_lock=runtime_lock))
        prepared = _prepare_fixture(backend, context["fixture"])
        blockers.extend(
            _fixture_application_blockers(
                prepared,
                fixture=context["fixture"],
                runtime_lock=runtime_lock,
            )
        )
        if not blockers:
            neutral = _neutral_ack(backend)
            telemetry = _mapping_record(
                neutral.get("action_telemetry", {}),
                "preflight zero-step action telemetry",
            )
            if telemetry.get("applied_action_available") is not True:
                blockers.append("zero_step_applied_action_telemetry_missing")
            if telemetry.get("action_limit_intervention_available") is not True:
                blockers.append("zero_step_action_limit_telemetry_missing")
            if neutral.get("acknowledged") is not True:
                blockers.append("zero_step_neutral_not_acknowledged")
        else:
            neutral = _neutral_ack(backend)
    except Exception as exc:
        blockers.append(f"preflight_exception:{type(exc).__name__}")
        if backend is not None:
            neutral = _neutral_ack(backend)
    finally:
        _close(backend)
    return {
        "arm_id": str(context["arm_id"]),
        "fixture_id": str(context["fixture_id"]),
        "target_role": str(context["target_role"]),
        "dispatch_strategy_id": str(context["dispatch_strategy_id"]),
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "get_info": _json_safe(info),
        "reset_applied": prepared.get("reset_applied") is True,
        "qpos_fixture_application_confirmed": (
            prepared.get("qpos_applied") is True
            and "fixture_qpos_mismatch" not in blockers
        ),
        "qvel_fixture_application_confirmed": (
            prepared.get("qvel_applied") is True
            and "fixture_qvel_mismatch" not in blockers
        ),
        "neutral_ack": neutral,
    }


def _execute_arm(
    context: Mapping[str, Any],
    *,
    destination: Path,
    backend_factory: BackendFactory,
    policy_factory: PolicyFactory,
    safety_factory: SafetyFactory,
    handoff_evaluator: HandoffEvaluator,
    runtime_lock: Mapping[str, Any],
) -> dict[str, Any]:
    arm_dir = destination / "arms" / str(context["arm_id"])
    arm_dir.mkdir(parents=True, exist_ok=False)
    trace: list[dict[str, Any]] = []
    backend = None
    policy = None
    termination = ""
    neutral = {"acknowledged": False, "step_id": None}
    nonzero_count = 0
    executed = False
    setup_blockers: list[str] = []
    try:
        backend = backend_factory(context)
        info = _object_record(backend.get_info())
        setup_blockers.extend(_info_blockers(info, runtime_lock=runtime_lock))
        prepared = _prepare_fixture(backend, context["fixture"])
        setup_blockers.extend(
            _fixture_application_blockers(
                prepared,
                fixture=context["fixture"],
                runtime_lock=runtime_lock,
            )
        )
        if setup_blockers:
            termination = "execution_fixture_recheck_blocked"
            neutral = _neutral_ack(backend)
        else:
            policy = policy_factory(context)
            policy.reset()
            safety = safety_factory(context)
            safety.reset()
            obs = _observation(prepared["observation"])
            executed = True
            for frame_index in range(RETURN_MAX_STEPS):
                handoff = _handoff_result(handoff_evaluator(obs, context))
                if handoff["would_handoff"]:
                    termination = "would_handoff"
                    neutral = _neutral_ack(backend)
                    trace.append(
                        _trace_record(
                            context,
                            frame_index=frame_index,
                            obs=obs,
                            proposed=np.zeros(RETURN_ACTION_DIM, dtype=np.float32),
                            dispatched=np.zeros(RETURN_ACTION_DIM, dtype=np.float32),
                            safety={"reason": "handoff_observed"},
                            handoff=handoff,
                            backend_obs=neutral.get("observation"),
                            action_telemetry=neutral.get("action_telemetry", {}),
                            policy_query_executed=False,
                            neutral_ack=True,
                        )
                    )
                    break
                policy_obs = dict(obs)
                policy_obs[RETURN_TOKEN_KEY] = np.asarray(
                    context["target"]["token"], dtype=np.float32
                )
                proposed = _dispatch_action(policy, policy_obs, context)
                decision = _project_safety_decision(
                    safety.filter_action(
                        obs,
                        proposed,
                        active_cell_id=-1,
                        active_corridor_id=-1,
                        skill_name="return",
                    )
                )
                if decision.terminal or decision.replan:
                    termination = decision.reason or "safety_terminal"
                    neutral = _neutral_ack(backend)
                    trace.append(
                        _trace_record(
                            context,
                            frame_index=frame_index,
                            obs=obs,
                            proposed=proposed,
                            dispatched=np.zeros(RETURN_ACTION_DIM, dtype=np.float32),
                            safety=decision.as_dict(),
                            handoff=handoff,
                            backend_obs=neutral.get("observation"),
                            action_telemetry=neutral.get("action_telemetry", {}),
                            policy_query_executed=True,
                            neutral_ack=True,
                        )
                    )
                    break
                step = backend.step(decision.action)
                next_obs = _observation(step)
                action_telemetry = _step_action_telemetry(
                    step,
                    action_dim=RETURN_ACTION_DIM,
                )
                if np.any(decision.action != 0.0):
                    nonzero_count += 1
                trace.append(
                    _trace_record(
                        context,
                        frame_index=frame_index,
                        obs=obs,
                        proposed=proposed,
                        dispatched=decision.action,
                        safety=decision.as_dict(),
                        handoff=handoff,
                        backend_obs=next_obs,
                        action_telemetry=action_telemetry,
                        policy_query_executed=True,
                        neutral_ack=False,
                    )
                )
                if (
                    action_telemetry["applied_action_available"] is not True
                    or action_telemetry[
                        "action_limit_intervention_available"
                    ]
                    is not True
                ):
                    termination = "action_application_telemetry_missing"
                    neutral = _neutral_ack(backend)
                    break
                obs = next_obs
                if bool(getattr(step, "done", False)):
                    termination = "backend_done"
                    neutral = _neutral_ack(backend)
                    break
            else:
                termination = "return_horizon_420"
                neutral = _neutral_ack(backend)
    except Exception as exc:
        termination = f"execution_exception:{type(exc).__name__}"
        if backend is not None:
            neutral = _neutral_ack(backend)
    finally:
        _close(backend)

    summary = {
        "schema": ARM_SUMMARY_SCHEMA,
        "arm_id": str(context["arm_id"]),
        "fixture_id": str(context["fixture_id"]),
        "target_role": str(context["target_role"]),
        "target_token_sha256": str(context["target"]["token_sha256"]),
        "target_envelope": _json_safe(context["target_envelope"]),
        "other_target_token_sha256": str(
            context["other_target"]["token_sha256"]
        ),
        "other_target_envelope": _json_safe(
            context["other_target_envelope"]
        ),
        "dispatch_strategy_id": str(context["dispatch_strategy_id"]),
        "allowed_primitive": "return",
        "executed": executed,
        "attempt_count": 1 if executed else 0,
        "retry_allowed": False,
        "max_steps": RETURN_MAX_STEPS,
        "trace_frame_count": len(trace),
        "nonzero_action_count": nonzero_count,
        "termination_reason": termination or "execution_incomplete",
        "would_handoff_observed": termination == "would_handoff",
        "dig_or_dump_called": False,
        "neutral_acknowledged": bool(neutral.get("acknowledged", False)),
        "neutral_ack_step_id": neutral.get("step_id"),
        "setup_blockers": setup_blockers,
    }
    _write_jsonl_x(arm_dir / "trace.jsonl", trace)
    _write_json_x(arm_dir / "summary.json", summary)
    return summary


def _dispatch_action(
    policy: Any,
    obs: Mapping[str, Any],
    context: Mapping[str, Any],
) -> np.ndarray:
    strategy = str(context["dispatch_strategy_id"])
    if strategy == LEGACY_STRATEGY_ID:
        value = policy.predict(dict(obs))
    elif strategy == LATEST_CURRENT_STRATEGY_ID:
        value = policy.predict_action_chunk(dict(obs)).first_action
    else:  # Contract validation should make this unreachable.
        raise ReturnClosedLoopProbeError(f"unsupported dispatch strategy {strategy}")
    action = np.asarray(value, dtype=np.float32).reshape(-1)
    if action.shape != (RETURN_ACTION_DIM,):
        raise ValueError("Return policy action must be 4D")
    return action


def _handoff_result(value: Any) -> dict[str, Any]:
    if isinstance(value, (bool, np.bool_)):
        return {"would_handoff": bool(value)}
    record = dict(_mapping_record(value, "handoff evaluation"))
    record["would_handoff"] = bool(record.get("would_handoff", False))
    return _json_safe(record)


def _trace_record(
    context: Mapping[str, Any],
    *,
    frame_index: int,
    obs: Mapping[str, Any],
    proposed: Any,
    dispatched: Any,
    safety: Mapping[str, Any],
    handoff: Mapping[str, Any],
    backend_obs: Any,
    action_telemetry: Mapping[str, Any],
    policy_query_executed: bool,
    neutral_ack: bool,
) -> dict[str, Any]:
    next_obs = _observation(backend_obs) if backend_obs is not None else {}
    telemetry = dict(action_telemetry)
    return {
        "schema": TRACE_SCHEMA,
        "arm_id": str(context["arm_id"]),
        "frame_index": int(frame_index),
        "step_id_before": int(obs.get("step_id", -1)),
        "step_id_after": int(next_obs.get("step_id", -1)),
        "primitive": "return",
        "target_role": str(context["target_role"]),
        "target_token_sha256": str(context["target"]["token_sha256"]),
        "dispatch_strategy_id": str(context["dispatch_strategy_id"]),
        "qpos_before": _vector_list(obs.get("qpos")),
        "qvel_before": _vector_list(obs.get("qvel")),
        "env_state_before": _vector_list(obs.get("env_state")),
        "qpos_after": _vector_list(next_obs.get("qpos")),
        "qvel_after": _vector_list(next_obs.get("qvel")),
        "env_state_after": _vector_list(next_obs.get("env_state")),
        "proposed_action": _vector_list(proposed),
        "dispatched_action": _vector_list(dispatched),
        "applied_action": _vector_list(telemetry.get("applied_action")),
        "action_limit_intervention": [
            bool(value)
            for value in telemetry.get("action_limit_intervention", ())
        ],
        "action_application_telemetry_valid": bool(
            telemetry.get("applied_action_available") is True
            and telemetry.get("action_limit_intervention_available") is True
        ),
        "temporal_dispatch": _temporal_dispatch_record(
            context,
            frame_index=frame_index,
            policy_query_executed=policy_query_executed,
        ),
        "safety": _json_safe(safety),
        "handoff": _json_safe(handoff),
        "neutral_ack": bool(neutral_ack),
    }


def _temporal_dispatch_record(
    context: Mapping[str, Any],
    *,
    frame_index: int,
    policy_query_executed: bool,
) -> dict[str, Any]:
    strategy_id = str(context["dispatch_strategy_id"])
    if not policy_query_executed:
        return {
            "strategy_id": strategy_id,
            "policy_query_executed": False,
            "contributors": [],
        }
    strategy = pre_registered_temporal_dispatch_strategies()[strategy_id]
    contributors = temporal_dispatch_contributors_for_frame(
        current_frame=int(frame_index),
        strategy=strategy,
        epoch_start_frame=0,
    )
    return {
        "strategy_id": strategy_id,
        "policy_query_executed": True,
        "contributors": [item.as_dict() for item in contributors],
    }


def _not_executed_arm(
    context: Mapping[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "arm_id": str(context["arm_id"]),
        "fixture_id": str(context["fixture_id"]),
        "target_role": str(context["target_role"]),
        "target_token_sha256": str(context["target"]["token_sha256"]),
        "dispatch_strategy_id": str(context["dispatch_strategy_id"]),
        "status": status,
        "executed": False,
        "attempt_count": 0,
        "retry_allowed": False,
        "max_steps": RETURN_MAX_STEPS,
        "nonzero_action_count": 0,
        "neutral_acknowledged": False,
        "dig_or_dump_called": False,
    }


def _manifest_runtime_lock(lock: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(value) for key, value in lock.items()}


def _vector_list(value: Any) -> list[float]:
    if value is None:
        return []
    try:
        return np.asarray(value, dtype=np.float64).reshape(-1).astype(float).tolist()
    except Exception:
        return []


def _close(value: Any) -> None:
    if value is None:
        return
    close = getattr(value, "close", None)
    if callable(close):
        close()


__all__ = [
    "ARM_SUMMARY_SCHEMA",
    "ARMS_SCHEMA",
    "LATEST_CURRENT_STRATEGY_ID",
    "LEGACY_STRATEGY_ID",
    "PREFLIGHT_SCHEMA",
    "PROBE_SCHEMA",
    "RETURN_ARM_COUNT",
    "RETURN_MAX_STEPS",
    "ReturnClosedLoopProbeError",
    "ReturnClosedLoopSafetyAdapter",
    "ReturnProbeSafetyDecision",
    "run_return_closed_loop_probe",
]
