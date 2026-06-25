# Planner Decision-Structure Tier 1 Schema v0

Status: **active research schema contract for Tier 1 offline/shadow
validation**.

This document defines the first schema contract for the two Tier 1 research
roles from `docs/planner_decision_structure_research_roadmap.md`:

- Coverage Utility shadow scorer.
- LLM explanation/report generator.

It is a research contract, not a production backend contract. It does not change
the default primitive decision backend and it does not authorize runtime state
mutation.

Use this document with:

- `docs/planner_decision_structure_research_roadmap.md`
- `docs/planner_decision_structure_tier1_gold_examples_v0.md`
- `docs/planner_decision_theory_backend_contract.md`
- `docs/planner_evidence_trace_tool.md`
- `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`
- local ignored package
  `runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/`

Prototype checker:

```text
tb-planner-tier1-validate validate \
  --package runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618 \
  --output-json runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/outputs/checker_v0/tier1_validation_report.json \
  --output-md runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/outputs/checker_v0/tier1_validation_report.md
```

## Scope And Boundaries

Tier 1 research remains offline, shadow, and human-audit only.

The schemas in this document may be used to:

- extract coverage candidate events from planner trace artifacts;
- score or re-rank coverage candidates outside the runtime;
- compare shadow rankings with legacy coverage selection;
- create field-grounded LLM explanations from public reports;
- reject unsupported claims when the required fields are missing.

The schemas in this document must not be used to:

- replace `legacy_fsm`;
- replace coverage scoring or candidate selection;
- write coverage, token, return, cycle, execution, or report state;
- call ACT policies;
- emit live actions or requested effects;
- read policy private attributes;
- treat explanations as decision source of truth.

If a future runtime backend consumes any of these ideas, it must first define
separate backend facts/effects and pass the implementation gates in
`docs/planner_decision_theory_backend_contract.md`.

## Package Contract

The first concrete validation package for this schema is:

```text
runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/
```

This package is intentionally under ignored `runs/`. It is not a tracked source
of truth.

Required package files:

- `README.md`
- `manifest.json`
- `hashes/sha256sums.txt`
- `inputs/rollout_000.jsonl`
- `inputs/rollout_000_planner_trace.json`
- `inputs/rollout_000_summary.json`
- `inputs/eval_resolved_config.yaml`
- `inputs/planner_evidence_report.json`
- `inputs/planner_evidence_report.md`

The current package facts are:

- dataset id: `aggregate_tx24_20260618`;
- source host: `pingfan`;
- source repo head observed: `887256f`;
- rollout row count: `5584`;
- planner trace coverage decision trace count: `20`;
- select-corridor event count: `10`;
- current select-corridor candidate count: `6` per select event;
- summary `success=true`;
- summary `completed_dump_count=9`;
- summary `coverage_completed_dump_count=9`;
- summary `coverage_depleted_count=6`;
- summary terminal reason: `dig_area_depleted`.

Validation limits:

- full offline action replay is not supported;
- raw image observations are not included;
- checkpoint state is not included;
- Unity or environment snapshot is not included;
- private planner mutable state is not included.

## Coverage Utility Shadow Input v0

### Design Position

The primary event source is:

```text
inputs/rollout_000_planner_trace.json#/coverage_decision_trace/<event_index>
```

Only events with `event == "select_corridor"` are valid input records for the
v0 shadow scorer. The rollout JSONL may be used for alignment and public summary
context, but raw rollout rows must not be forwarded wholesale.

### Required Top-Level Fields

```json
{
  "schema_version": "coverage_utility_shadow_input_v0",
  "dataset_id": "aggregate_tx24_20260618",
  "package_fingerprint": {
    "manifest_sha256": "sha256:<manifest>",
    "trace_sha256": "sha256:<planner_trace>"
  },
  "event_identity": {
    "source": "planner_trace.coverage_decision_trace",
    "event_index": 0,
    "event": "select_corridor",
    "rollout_id": 0,
    "cycle_index": 0,
    "skill_name": "dig",
    "active_corridor_id_before_select": -1,
    "last_selected_corridor_id_before_select": -1
  },
  "legacy_selection": {
    "selected_corridor_id": 3,
    "selected_score": 4.180294018773603,
    "selection_rule": "unique candidate matching selected_score"
  },
  "candidate_scores": [],
  "episode_context": {}
}
```

Field sources:

- `dataset_id`: `manifest.json`.
- `package_fingerprint`: `manifest.json` and `hashes/sha256sums.txt`.
- `event_index`: array index in `planner_trace.coverage_decision_trace`.
- `event`: planner trace event field; must be `select_corridor`.
- `rollout_id`: rollout JSONL alignment or single-rollout package metadata.
- `cycle_index`: trace event `cycle_index`.
- `skill_name`: trace event `skill_name`.
- `active_corridor_id_before_select`: trace event `active_corridor_id`.
- `last_selected_corridor_id_before_select`: trace event
  `last_selected_corridor_id`.
- `selected_score`: trace event `selected_score`.
- `selected_corridor_id`: derived from the unique candidate whose `score`
  matches `selected_score`.
- `candidate_scores`: trace event `candidate_scores`.
- `episode_context`: allowlisted fields from `rollout_000_summary.json` and
  `manifest.json`.

### Required Candidate Fields

Each candidate record must include:

- `corridor_id`
- `cell_id`
- `row_id`
- `score`
- `attempts`
- `attempt_limit`
- `depleted`
- `source_count`
- `source_fraction`
- `cell_confidence`
- `belief_coverage`
- `remaining_depth_m`
- `first_dig_bonus`
- `first_dig_entry_distance_m`
- `first_dig_entry_reachable`
- `first_dig_qpos_delta_norm`
- `first_dig_qpos_reachable`
- `first_dig_reachable`
- `first_dig_gate_applied`
- `first_dig_gated_out`
- `rare_first_dig_gated_out`
- `first_dig_max_entry_distance_m`
- `recent_row_penalty`
- `same_recent_row`
- `low_productivity_streak`
- `state_exemplar_distance`
- `state_exemplar_id`

### Optional Candidate Fields

Optional fields should be preserved when present:

- `first_dig_qpos_delta`
- `first_dig_max_qpos_delta`
- `recent_row_reference_corridor_id`
- `recent_row_reference_cell_id`
- `recent_row_reference_row_id`

Missing optional fields must be reported in `missing_facts` if the scorer uses a
consideration that depends on them.

### Required Episode Context Fields

The v0 episode context should include:

- `success`
- `episode_len`
- `rollout_stop_reason`
- `target_cycle_completed_dump_count`
- `completed_dump_count`
- `coverage_completed_dump_count`
- `coverage_depleted_count`
- `coverage_selected_corridor_id`
- `coverage_terminal_stop_requested`
- `coverage_terminal_stop_reason`
- `pre_dig_align_enabled`
- `primitive_final_skill`

Episode context is outcome/proxy context. It must not be treated as
counterfactual evidence for a different corridor choice.

### Forbidden Inputs

The v0 input envelope must not include:

- `action`
- `qpos`
- `qvel`
- `env_state`
- raw `task_metrics`
- raw image observations
- checkpoint paths
- policy private attributes
- owner state objects
- mutation callbacks or ports
- token arrays as coverage scorer features

Token contract fields may be cited by the LLM explainer, but they are not
Coverage Utility input fields in v0.

### Missing And Unsupported Handling

Hard fail:

- event is not `select_corridor`;
- event lacks `candidate_scores`;
- a candidate lacks `corridor_id`;
- a candidate lacks `score`;
- `selected_score` cannot be uniquely mapped to a candidate and no explicit
  unsupported reason is recorded.

Soft fail:

- optional consideration fields are missing;
- rollout id cannot be aligned from rollout rows;
- gate fields are incomplete for a requested gate explanation.

Soft failures must lower confidence and add entries to `missing_facts`. They
must not be filled with silent defaults.

## Coverage Utility Shadow Output v0

### Required Output Fields

```json
{
  "schema_version": "coverage_utility_shadow_output_v0",
  "input_fingerprint": "sha256:<canonical_input>",
  "scorer_config_fingerprint": "sha256:<canonical_config>",
  "event_identity": {
    "dataset_id": "aggregate_tx24_20260618",
    "event_index": 0,
    "cycle_index": 0,
    "skill_name": "dig"
  },
  "legacy_selection": {
    "corridor_id": 3,
    "rank_in_shadow": 1,
    "legacy_score": 4.180294018773603
  },
  "shadow_top1_corridor_id": 3,
  "shadow_ranking": [],
  "rank_diff_summary": {
    "top1_parity": true,
    "topk_overlap_3": 1.0,
    "legacy_rank_delta": 0,
    "score_margin_top1_top2": 1.125115685163225
  },
  "disagreement_category": "parity",
  "unsupported_or_missing_facts": [],
  "confidence": "high",
  "notes": []
}
```

Each `shadow_ranking` item must include:

- `corridor_id`
- `rank`
- `total_score`
- `score_breakdown`
- `gated_out`
- `missing_facts`

Each `score_breakdown` item must include:

- `name`
- `value`
- `field_refs`

`field_refs` must point to fields in the input envelope.

Allowed `disagreement_category` values:

- `parity`
- `tie_or_low_margin`
- `gate_policy_difference`
- `legacy_score_higher`
- `shadow_prefers_unblocked`
- `missing_fact`
- `unsupported_case`

Allowed `confidence` values:

- `high`
- `medium`
- `low`

Confidence describes auditability, not rollout improvement.

### Example Ranking Item

```json
{
  "corridor_id": 3,
  "rank": 1,
  "total_score": 1.0,
  "score_breakdown": [
    {
      "name": "reachable_gate",
      "value": 1.0,
      "field_refs": [
        "planner_trace:/coverage_decision_trace/0/candidate_scores/3/first_dig_reachable"
      ]
    },
    {
      "name": "remaining_depth",
      "value": 0.04234759137034416,
      "field_refs": [
        "planner_trace:/coverage_decision_trace/0/candidate_scores/3/remaining_depth_m"
      ]
    }
  ],
  "gated_out": false,
  "missing_facts": []
}
```

### Automatic Checks

A checker or prototype must validate:

- output schema version is known;
- `input_fingerprint` matches the canonical input;
- candidates in `shadow_ranking` are a subset of input candidates;
- no candidate id is duplicated;
- `legacy_selection.corridor_id` is mapped from input or marked unsupported;
- all `field_refs` exist in the input envelope;
- output is deterministic for the same input and scorer config;
- `tie_or_low_margin` threshold is recorded in scorer config;
- missing fields are reported rather than defaulted;
- forbidden raw fields are absent.

### Episode-Level Metrics

For a package, aggregate:

- `select_event_count`
- `candidate_count_per_event`
- `top1_parity_rate`
- `topk_overlap@k`
- `legacy_selected_rank_distribution`
- `mean_abs_rank_delta`
- `max_rank_delta`
- `score_margin_distribution`
- `gated_candidate_count_distribution`
- `depleted_candidate_count_distribution`
- `unsupported_case_rate`
- `coverage_trace_alignment_rate`

These metrics are shadow/replay metrics. They do not prove counterfactual
rollout improvement.

## LLM Explanation Input v0

### Design Position

The LLM explainer consumes an allowlisted source envelope. It must not consume a
whole rollout row, raw observations, or private planner state.

### Required Top-Level Fields

```json
{
  "schema_version": "llm_explanation_input_v0",
  "dataset_id": "aggregate_tx24_20260618",
  "package_metadata": {},
  "sources": {
    "planner_trace": {},
    "rollout_summary": {},
    "evidence_report": {},
    "debug_state_samples": [],
    "config": {}
  },
  "source_roles": {}
}
```

### Allowed Sources

`package_metadata` may include:

- dataset id;
- package path;
- file sizes;
- hashes;
- source host/repo/head;
- validation limits.

`planner_trace` may include:

- token contract names and versions;
- coverage config fields;
- `coverage_decision_trace`;
- coverage terminal stop flags and reasons.

`rollout_summary` may include:

- episode outcome/proxy fields;
- transition counts;
- coverage summary fields;
- pre-dig-align status fields;
- cell-entry status fields;
- recovery counters.

`evidence_report` may include:

- `capability_id`;
- classification;
- retention decision;
- owner;
- observed, consumed-by-decision, and reported counts;
- producers;
- reasons.

`debug_state_samples` may include allowlisted public report/debug fields from
rollout rows:

- `rollout_id`
- `step_id`
- `t`
- `skill_name`
- `skill_switch_reason`
- `primitive_cycle_index`
- coverage fields
- transition fields
- pre-dig-align flags
- cell-entry flags
- return readiness fields
- token source flags

`config` may include boundary-relevant resolved config facts, such as:

- primitive low-dimensional key lists;
- `pre_dig_align` enabled/config fields;
- return token configuration fields;
- output path identity when needed for provenance.

### Forbidden Inputs

The LLM input envelope must not include:

- raw `action`;
- raw `qpos`;
- raw `qvel`;
- raw `env_state`;
- raw `task_metrics`;
- raw image observations;
- full checkpoint paths when not needed for the claim;
- private policy attributes;
- owner state objects;
- mutation callbacks or ports;
- executable commands.

### Source Role Labels

Allowed source roles:

- `confirmed-live`
- `report-only`
- `parked`
- `config`
- `package-metadata`

Role meanings:

- `confirmed-live`: evidence report marks a capability as observed, consumed by
  decision, and reported.
- `report-only`: report/trace fields are available for audit but are not
  decision-source facts by themselves.
- `parked`: legacy or compatibility path retained only as parked/report
  material.
- `config`: resolved config fact.
- `package-metadata`: manifest, hash, source, or validation-limit fact.

Known role assignments for the aggregate-tx24 package:

- `coverage.corridor`: `confirmed-live`.
- `debug.debug_state`: `report-only`.
- `report.rollout_summary`: `report-only`.
- `trace.planner_trace`: `report-only`.
- `token.cell_entry`: `parked`.
- `gate.pre_dig_align`: `parked` or opt-in context, not default mainline.

### Field Citation Grammar

Use this citation form:

```text
<source_label>:<json_pointer>#role=<source_role>
```

Examples:

```text
planner_trace:/coverage_decision_trace/0/candidate_scores/3/score#role=report-only
rollout_summary:/coverage_terminal_stop_reason#role=report-only
evidence_report:/rows/by_capability_id/coverage.corridor/classification#role=confirmed-live
config:/policy/dig_low_dim_keys#role=config
package_metadata:/inputs/3/sha256#role=package-metadata
```

For evidence reports, a checker may build a `capability_id` index and support
semantic paths such as:

```text
evidence_report:/rows/by_capability_id/coverage.corridor/classification#role=confirmed-live
```

## LLM Explanation Output v0

### Required Output Fields

```json
{
  "schema_version": "llm_explanation_output_v0",
  "model_id": "<model>",
  "prompt_version": "tier1_explainer_prompt_v0",
  "decoding_config": {
    "temperature": 0
  },
  "input_fingerprint": "sha256:<canonical_input>",
  "summary_sections": {},
  "claims": [],
  "unsupported_claim_rejections": [],
  "missing_field_notes": [],
  "parked_path_labels": [],
  "uncertainty_notes": []
}
```

Each claim must include:

- `claim_id`
- `text`
- `claim_type`
- `confidence`
- `field_citations`

Allowed `claim_type` values:

- `summary`
- `coverage_decision`
- `capability_classification`
- `artifact_limit`
- `parked_path`
- `missing_information`
- `uncertainty`

Allowed `confidence` values:

- `high`
- `medium`
- `low`

### Example Claim

```json
{
  "claim_id": "c1",
  "text": "The rollout stopped because the coverage terminal reason was dig_area_depleted.",
  "claim_type": "summary",
  "confidence": "high",
  "field_citations": [
    "rollout_summary:/coverage_terminal_stop_reason#role=report-only",
    "planner_trace:/coverage_terminal_stop_reason#role=report-only"
  ]
}
```

### Example Unsupported Claim Rejection

```json
{
  "requested_claim": "The shadow scorer would improve rollout outcome.",
  "reason": "Counterfactual outcome labels are not present in the package.",
  "missing_fields": [
    "counterfactual_outcome_label"
  ]
}
```

### Example Parked Path Label

```json
{
  "path": "cell_entry",
  "label": "parked compatibility/report material",
  "citations": [
    "evidence_report:/rows/by_capability_id/token.cell_entry/classification#role=parked"
  ]
}
```

### Automatic Checks

A checker or prototype must validate:

- every claim has at least one citation;
- every citation source is allowlisted;
- every citation path exists;
- cited values support concrete values in the claim;
- report-only citations keep `role=report-only`;
- `cell_entry` and `pre_dig_align` claims include parked or opt-in labels;
- output does not invent skill, effect, backend, candidate, or artifact path;
- output does not reference forbidden raw fields;
- unsupported requests are rejected rather than guessed;
- model id, prompt version, decoding config, and input fingerprint are present.

### Human Audit Sampling Plan

For each validation package, first audit:

- all select-corridor explanations from `coverage_decision_trace`;
- one terminal stop explanation;
- one rollout summary explanation;
- one `cell_entry` parked-path explanation;
- one `pre_dig_align` parked or opt-in explanation.

If using rollout row samples, sample around skill-switch windows and apply an
allowlist projection before sending content to the explainer.

Human audit labels:

- `grounded`: citations fully support the claim.
- `partly_grounded`: fields exist, but the claim overstates causality or
  certainty.
- `unsupported`: cited fields do not support the claim.
- `role_mislabel`: report-only was presented as decision-source.
- `parked_path_drift`: parked paths were described as mainline/default.

## Schema Storage And Versioning

Tracked source of truth:

```text
docs/planner_decision_structure_tier1_schema_v0.md
```

Dataset-local schema snapshots may live under:

```text
runs/eval/planner_decision_structure_tier1_validation/<dataset_id>/schemas/
```

The tracked document owns schema semantics. Dataset-local schema files, when
created later, should record the exact schema snapshot and hash used for that
package.

Do not treat ignored package-local schema files as the only source of truth.

## Checker Prototype

The current minimal checker lives in:

```text
testbed/planner/decision_structure/tier1_validation.py
```

The CLI entry point is:

```text
tb-planner-tier1-validate
```

The checker validates:

- package manifest and input hashes;
- required input files;
- select-corridor event extraction;
- the four Coverage Utility gold examples;
- the six LLM explanation citation examples;
- the negative/rejection cases in the gold examples document;
- validation limits that prevent full action replay or production-readiness
  claims.

The checker does not:

- run a Utility scoring algorithm;
- call an LLM;
- validate external scorer or explainer outputs yet;
- call planner runtime, ACT policies, or requested-effect appliers;
- write tracked outputs by default.

Checker reports should be written under ignored validation output paths until
their output contract is accepted.

## Next Work

Recommended next bounded work:

1. Extend the checker to validate external Coverage Utility shadow outputs.
2. Extend the checker to validate external LLM explanation outputs.
3. Add dataset-local schema snapshots only after the tracked schema is accepted.
4. Add prompt/security/raw-observation sanitization tests before any LLM/VLM
   role expands beyond report-only validation.

Do not move to BT trace schema until Tier 1 schema validation has a basic
checker or human-audit sample.
