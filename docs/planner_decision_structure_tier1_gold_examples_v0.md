# Planner Decision-Structure Tier 1 Gold Examples v0

Status: **active research gold examples for Tier 1 human audit**.

This document provides concrete human-audit examples for the Tier 1 schemas in
`docs/planner_decision_structure_tier1_schema_v0.md`.

It is not an implementation plan and it does not authorize production backend
changes. These examples are for offline/shadow validation only.

Use this document with:

- `docs/planner_decision_structure_research_roadmap.md`
- `docs/planner_decision_structure_tier1_schema_v0.md`
- `docs/planner_decision_theory_backend_contract.md`
- local ignored package
  `runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/`

## Source Package

The examples below are derived from the local ignored validation package:

```text
runs/eval/planner_decision_structure_tier1_validation/aggregate_tx24_20260618/
```

Relevant input files:

- `inputs/rollout_000_planner_trace.json`
- `inputs/rollout_000_summary.json`
- `inputs/planner_evidence_report.json`
- `manifest.json`

Package facts used by these examples:

- rollout row count: `5584`;
- `coverage_decision_trace` event count: `20`;
- select-corridor event count: `10`;
- current candidate count per select event: `6`;
- `completed_dump_count=9`;
- `coverage_completed_dump_count=9`;
- `coverage_depleted_count=6`;
- terminal reason: `dig_area_depleted`;
- `pre_dig_align_enabled=0`;
- `cell_entry_enabled=0`.

## Audit Sample Selection Policy

Use the following four coverage events as the first human-audit sample set:

| Sample | Event index | Why it is useful |
| --- | ---: | --- |
| First select / first-dig gate | `0` | Exercises first-dig reachability and gate references. |
| Low-margin select | `2` | Exercises tie/low-margin handling and overclaim prevention. |
| Mid-run depleted context | `12` | Exercises depleted candidates, remaining depth, and source confidence. |
| Terminal-adjacent all-depleted select | `19` | Exercises terminal context, non-unique selected-score mapping, and low confidence. |

Known missing sample classes:

- no real shadow scorer disagreement output exists yet;
- no per-candidate counterfactual outcome labels exist;
- no raw image or VLM sample exists;
- no online backend or requested-effect sample belongs in Tier 1.

## Coverage Utility Gold Examples

### Example A: First Select / First-Dig Gate

Source:

```text
planner_trace:/coverage_decision_trace/0
```

Identity:

- `event_index=0`
- `cycle_index=0`
- `skill_name=dig`
- `selected_score=4.180294018773603`
- `candidate_count=6`
- `depleted_count=0`

Legacy selected corridor:

- `corridor_id=3`
- selection can be derived from the unique candidate matching
  `selected_score`.

Key fields:

| Corridor | Score | Gate | Entry distance | Max entry distance | Remaining depth | Confidence |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 3 | `4.180294018773603` | reachable, not gated out | `0.034843039602471065` | `0.45` | `0.04234759137034416` | `1.5` |
| 2 | `3.055178333610378` | reachable, not gated out | `0.21836537250803723` | `0.45` | `0.07809290324803442` | `1.107204` |
| 1 | `-999999999999.8756` | gated out | `0.5897081057841622` | `0.45` | `0.07999999821186066` | `1.423548` |
| 0 | `-1000000000000.3949` | gated out | `0.6348769552229985` | `0.45` | `0.07999999821186066` | `0.801408` |
| 5 | `-1000000000002.1738` | gated out | `0.817041879177792` | `0.45` | `0.07999999821186066` | `0.885762` |
| 4 | `-1000000000002.6787` | gated out | `0.8220341737505699` | `0.45` | `0.07999999821186066` | `0.242532` |

Expected audit result:

- A shadow output that agrees with corridor `3` may use
  `disagreement_category=parity`.
- Gated-out candidates must not be treated as normal available top-1 choices in
  v0.
- Field references should cite `first_dig_entry_distance_m`,
  `first_dig_max_entry_distance_m`, `first_dig_reachable`, and
  `first_dig_gated_out`, not only the final legacy `score`.

Human audit question:

```text
Does the output explain the first-dig gate with field citations, or does it only
repeat that the legacy score is higher?
```

Rejected claim:

```text
Corridor 3 would make the rollout more successful.
```

Reason: no counterfactual outcome label exists.

### Example B: Low-Margin Return Select

Source:

```text
planner_trace:/coverage_decision_trace/2
```

Identity:

- `event_index=2`
- `cycle_index=0`
- `skill_name=return`
- `selected_score=4.847767649391016`
- `candidate_count=6`
- `depleted_count=1`

Legacy selected corridor:

- `corridor_id=1`
- runner-up is `corridor_id=0`;
- top-1 margin is about `0.15631127406733292`.

Key fields:

| Corridor | Score | Depleted | Confidence | Remaining depth | Recent-row penalty |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `4.847767649391016` | `0` | `1.423548` | `0.07999999821186066` | `0.0` |
| 0 | `4.691456375323683` | `0` | `0.801408` | `0.07999999821186066` | `0.0` |
| 5 | `4.380161063673871` | `0` | `0.885762` | `0.07999999821186066` | `0.0` |
| 4 | `3.908949402817915` | `0` | `0.242532` | `0.07999999821186066` | `0.0` |
| 2 | `3.31129819135648` | `0` | `1.107204` | `0.07716013840399683` | `1.5` |
| 3 | `-1000000001.0` | `1` | `1.5` | `0.033358365297317505` | `0.0` |

Expected audit result:

- If a shadow scorer re-ranks corridor `0` above corridor `1`, the output should
  use `tie_or_low_margin` unless it has a recorded threshold and cited fields
  supporting a stronger disagreement.
- The output must not claim that legacy was wrong solely from a small score
  margin.
- Depleted corridor `3` should not be presented as a normal available top
  candidate.

Human audit question:

```text
Does the output record the tie or margin policy, and does it avoid overstating a
low-margin difference?
```

### Example C: Mid-Run Select With Depleted Context

Source:

```text
planner_trace:/coverage_decision_trace/12
```

Identity:

- `event_index=12`
- `cycle_index=5`
- `skill_name=return`
- `selected_score=1.84523706678468`
- `candidate_count=6`
- `depleted_count=3`

Legacy selected corridor:

- `corridor_id=2`;
- runner-up is `corridor_id=5`;
- margin is about `2.484456094440614`.

Key fields:

| Corridor | Score | Depleted | Attempts | Limit | Remaining depth | Confidence |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | `1.84523706678468` | `0` | `1` | `3` | `0.0661872522905469` | `1.107204` |
| 5 | `-0.6392190276559341` | `0` | `1` | `3` | `0.006537124514579773` | `0.885762` |
| 4 | `-100000001.0` | `0` | `1` | `1` | `0.06663330737501383` | `0.242532` |
| 0 | `-1000000001.0` | `1` | `1` | `3` | `0.05162375420331955` | `0.801408` |
| 1 | `-1000000001.0` | `1` | `1` | `3` | `0.0` | `1.423548` |
| 3 | `-1000000001.0` | `1` | `1` | `3` | `0.0` | `1.5` |

Expected audit result:

- A parity output may have high confidence if it cites non-depleted status,
  remaining depth, and source confidence.
- The output may mention depleted candidates only with event-local field
  references.
- The output must not use episode-level success to justify this event-level
  candidate choice.

Human audit question:

```text
Does the output distinguish event-local candidate evidence from episode summary
outcome?
```

### Example D: Terminal-Adjacent All-Depleted Select

Source:

```text
planner_trace:/coverage_decision_trace/19
```

Identity:

- `event_index=19`
- `cycle_index=8`
- `skill_name=return`
- `selected_score=-1000000001.0`
- `terminal_stop_requested=1`
- `terminal_stop_reason=dig_area_depleted`
- `candidate_count=6`
- `depleted_count=6`

Legacy selected corridor:

- `selected_score=-1000000001.0` matches corridors `0`, `1`, and `3`;
- there is no unique selected corridor from `selected_score` alone.

Key fields:

| Corridor | Score | Depleted | Remaining depth | Low productivity |
| ---: | ---: | ---: | ---: | ---: |
| 0 | `-1000000001.0` | `1` | `0.045304179191589355` | `0` |
| 1 | `-1000000001.0` | `1` | `0.0` | `0` |
| 3 | `-1000000001.0` | `1` | `0.0` | `1` |
| 2 | `-1000000002.0` | `1` | `0.025462787598371506` | `0` |
| 4 | `-1000000002.0` | `1` | `0.02859591320157051` | `0` |
| 5 | `-1000000002.0` | `1` | `0.0` | `0` |

Expected audit result:

- `legacy_selection.selected_corridor_id` should be `null`, or the output must
  explicitly mark the mapping as non-unique.
- `disagreement_category` should be `unsupported_case` or `tie_or_low_margin`.
- Confidence should be `low` or `medium`.
- The output should cite `terminal_stop_requested`, `terminal_stop_reason`, and
  all-depleted candidate status.

Human audit question:

```text
Does the output refuse to explain corridor 3 as uniquely best when the selected
score maps to multiple depleted candidates?
```

Rejected claim:

```text
Corridor 3 was uniquely selected because it was the best remaining option.
```

Reason: selected-score mapping is non-unique.

## LLM Explanation Gold Examples

### Claim 1: Coverage Terminal Reason

Claim:

```text
The rollout or coverage path ended with terminal reason dig_area_depleted.
```

Valid citations:

- `rollout_summary:/coverage_terminal_stop_reason#role=report-only`
- `planner_trace:/coverage_terminal_stop_reason#role=report-only`

Expected confidence: `high`.

Common failure mode:

- presenting the report-only terminal reason as a full decision-source causal
  explanation.

### Claim 2: Coverage Corridor Is Confirmed-Live

Claim:

```text
coverage.corridor is confirmed-live in the evidence report.
```

Valid citations:

- `evidence_report:/rows/by_capability_id/coverage.corridor/classification#role=confirmed-live`
- `evidence_report:/rows/by_capability_id/coverage.corridor/consumed_by_decision_count#role=confirmed-live`
- `evidence_report:/rows/by_capability_id/coverage.corridor/reported_count#role=confirmed-live`

Expected confidence: `high`.

Common failure mode:

- citing `planner_trace` alone to claim confirmed-live status.

### Claim 3: Planner Trace Is Report-Only

Claim:

```text
planner_trace is available for audit as a report-only source, not as a
decision-source fact by itself.
```

Valid citations:

- `evidence_report:/rows/by_capability_id/trace.planner_trace/classification#role=report-only`
- `evidence_report:/rows/by_capability_id/trace.planner_trace/consumed_by_decision_count#role=report-only`

Expected confidence: `high`.

Common failure mode:

- treating `coverage_decision_trace` as a complete internal causal proof instead
  of an audit trace.

### Claim 4: Cell Entry Is Parked

Claim:

```text
cell_entry is parked compatibility/report material in this research context and
must not be promoted into mainline Tier 1 inputs.
```

Valid citations:

- `evidence_report:/rows/by_capability_id/token.cell_entry/classification#role=parked`
- `evidence_report:/rows/by_capability_id/token.cell_entry/retention_decision#role=parked`
- `rollout_summary:/cell_entry_enabled#role=report-only`
- `rollout_summary:/cell_entry_trace_count#role=report-only`

Expected confidence: `high` for this package.

Common failure mode:

- treating the presence of cell-entry report fields as evidence that cell entry
  should become a default decision input.

### Claim 5: Pre-Dig Align Is Parked Or Opt-In

Claim:

```text
pre_dig_align is not active in aggregate_tx24; it should be treated as opt-in or
parked context rather than default mainline.
```

Valid citations:

- `evidence_report:/rows/by_capability_id/gate.pre_dig_align/classification#role=parked`
- `evidence_report:/rows/by_capability_id/gate.pre_dig_align/retention_decision#role=parked`
- `rollout_summary:/pre_dig_align_enabled#role=report-only`

Expected confidence: `high` for this package.

Common failure modes:

- presenting `pre_dig_align` as the current default route;
- claiming `pre_dig_align` is useless in general. The valid claim is narrower:
  it is not active in this package and must remain opt-in or parked unless a
  separate route promotes it.

### Claim 6: Artifact-Level Validation Limit

Claim:

```text
This package supports artifact/report-level validation but not full offline
action replay.
```

Valid citations:

- `package_metadata:/validation_limits/full_action_replay_supported#role=package-metadata`
- `package_metadata:/validation_limits/raw_image_observations_included#role=package-metadata`
- `package_metadata:/validation_limits/checkpoint_state_included#role=package-metadata`

Expected confidence: `high`.

Common failure mode:

- claiming ACT parity, production backend readiness, or VLM validation from this
  package.

## Negative Examples And Rejection Cases

### Counterfactual Rollout Improvement

Rejected claim:

```text
The shadow scorer would have improved the rollout outcome.
```

Reject because counterfactual outcome labels are absent. Shadow ranking metrics
do not prove rollout improvement.

Expected rejection field:

```text
missing_fields=["counterfactual_outcome_label"]
```

### Full Action Replay Parity

Rejected claim:

```text
This package proves full offline action replay parity with current HEAD.
```

Reject because the package validation limits mark full action replay as
unsupported and do not include raw images, checkpoint state, Unity snapshot, or
private planner mutable state.

### Forbidden Raw Field Explanation

Rejected claim:

```text
The explanation uses qpos, env_state, or action to explain why corridor 3 was
selected.
```

Reject because v0 LLM inputs forbid raw `action`, `qpos`, `qvel`, `env_state`,
raw `task_metrics`, and raw image observations.

### Cell Entry Mainline Drift

Rejected claim:

```text
cell_entry should be added as a default planner input because it appears in
rollout rows.
```

Reject because `token.cell_entry` is classified as a dead candidate with
`retain-legacy-parking`, and report presence is not mainline evidence.

### Pre-Dig Align Default Drift

Rejected claim:

```text
pre_dig_align should be the default recovery route for Tier 1.
```

Reject because aggregate-tx24 has `pre_dig_align_enabled=0`, and the evidence
row for `gate.pre_dig_align` is parked/dead-candidate in this context.

### Invented Online Backend Or Effect

Rejected claim:

```text
Use BehaviorTreeBackend or LLMBackend effects to switch online routing now.
```

Reject because Tier 1 schemas forbid live effects/actions and runtime mutation.
The current roadmap also excludes online backend promotion from this phase.

### Non-Unique Terminal Selection

Rejected claim:

```text
Event 19 selected corridor 3 because it was uniquely best.
```

Reject because `selected_score=-1000000001.0` maps to multiple depleted
candidates. Correct handling is non-unique selection, unsupported case, or
low-confidence tie-like explanation.

## Human Audit Label Refinement

The schema labels remain valid:

- `grounded`
- `partly_grounded`
- `unsupported`
- `role_mislabel`
- `parked_path_drift`

Add these refinement labels for gold-example reviews:

- `non_unique_selection`: selected score cannot uniquely identify a candidate.
- `counterfactual_overclaim`: shadow ranking or summary outcome is presented as
  proof of a better rollout.
- `forbidden_field_use`: raw or private fields appear in input, output, or
  explanation.
- `source_role_ok_but_causality_overstated`: cited fields exist and role labels
  are correct, but the natural-language claim overstates causality.

Manual audit can check:

- whether a claim has citations;
- whether citation values support the claim;
- whether parked paths drift into mainline language;
- whether low-margin or non-unique selection is over-explained;
- whether artifact limits are ignored.

Future checker/prototype work should automate:

- JSON pointer existence;
- forbidden field detection;
- candidate id subset and duplicate-candidate checks;
- selected-score uniqueness checks;
- field reference existence;
- source-role consistency with evidence classification;
- input/output fingerprint validation.

## Next Work

Recommended next bounded work:

1. Extend the checker to validate external Coverage Utility shadow outputs
   against these examples.
2. Extend the checker to validate external LLM explanation outputs against
   these examples.
3. Keep checker outputs under an ignored validation-output path until the output
   format is accepted.
4. Only after Tier 1 checker output is stable, revisit BT trace schema.
