# Planner Decision-Structure Research Roadmap

Status: **active pre-implementation research roadmap and validation rubric**.

This document records the research stance for possible primitive-planner
decision structures. It is not a production backend migration plan and it does
not authorize changing the default planner backend.

Use this document with:

- `docs/planner_current_architecture.md`
- `docs/planner_decision_theory_backend_contract.md`
- `docs/planner_decision_structure_tier1_schema_v0.md`
- `docs/planner_decision_structure_tier1_gold_examples_v0.md`
- `docs/planner_scheduling_backend_design.md`
- `docs/planner_primitive_interface_standard.md`
- `docs/planner_evidence_trace_tool.md`
- `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`

## Research Stance And Non-Goals

The current research goal is to understand which decision structures are useful
before implementing a new backend. The first objective is better explanation,
shadow evaluation, replay validation, and risk reduction.

This roadmap is not:

- a request to replace `legacy_fsm`;
- a request to make BT, Utility, GOAP, HTN, TAMP, LLM, VLM, WAM, or plugin
  routing the production default;
- a license to move state mutation into a model or planner sidecar;
- a design for low-level ACT action generation.

Any future backend must still obey the implementation contract in
`docs/planner_decision_theory_backend_contract.md`. In particular, it may read
only the approved backend input/facts surface and may express state changes only
as ordered `RequestedPlannerEffect` records applied by the focused effect
owners.

## Current Primitive Planner Boundary

The accurate maturity statement for the current implementation remains:

```text
default legacy FSM backendified with focused services
```

Important current boundaries:

- Production composition registers only `legacy_fsm`.
- The backend facts packet is transition-oriented: common decision context plus
  bootstrap, dig, carry, dump, and return transition facts.
- Coverage scoring and candidate selection are owned by coverage services, not
  decision backends.
- Token construction, token injection, return handoff mutation, cycle state,
  dig recovery, report assembly, and low-level ACT dispatch already have focused
  owners.
- `pre_dig_align` is an opt-in runtime capability, not a default decision
  structure.
- `cell_entry` is parked compatibility/report material and must not silently
  become a mainline input.

The strongest safe integration boundary is:

```text
read-only facts/report/replay -> proposal, score, explanation, or requested
effect candidate -> validation/human audit -> focused owners apply state changes
```

## Candidate Structure Tier Map

| Tier | Candidate structure | First useful role | Why here | Main blocker |
| --- | --- | --- | --- | --- |
| Tier 1 | Coverage Utility shadow scorer | Read-only shadow scorer for coverage candidates | Current `coverage_candidate_scores` and decision trace already expose rich candidate features | Utility output schema, rank metric, tie policy, and replay artifacts |
| Tier 1 | LLM explanation/report generator | Read-only report explainer | Public `debug_state`, `planner_trace`, `rollout_summary`, and evidence reports already form a safe input envelope | Field-citation checker, gold examples, raw-observation sanitization, and model/prompt policy |
| Tier 2 | BT shadow trace / visualization | Structure and visualize current branch/recovery paths | BT maps naturally onto guarded fallback/recovery control | Node/path/condition trace schema, RUNNING semantics, blackboard policy |
| Tier 2 | LLM/VLM constraint generator | Offline typed constraint proposer | Can help surface missing guards or reject rules | Constraint schema, provenance, validator, and false-positive review |
| Tier 3 | GOAP/HTN offline proposer | Offline multi-step strategy proposer | Useful for longer recovery or decomposition research | Symbolic domain/problem schema, operator semantics, plan lifecycle |
| Tier 3 | TAMP / feasibility sidecar | Geometry feasibility evaluator | Useful when candidate feasibility depends on pose, reachability, or continuous geometry | Feasibility labels, sampler contract, latency, calibration |
| Tier 3 | World/action predictor or WAM | Outcome/risk predictor | Useful for longer-term model-based counterfactuals | Action-outcome labels, artifact access, OOD tests, calibration |
| Tier 3 | VLM fact extractor | Offline perception fact annotator | Could expose visual anomalies or scene facts | Perception fact schema, confidence/provenance, evaluation set |
| Not now | Online backend, VLA direct action, default plugin routing | None for the first phase | Violates current readiness and ownership boundaries | Production selector, parity/A-B target, safety gates, new contracts |

## Tier 1 Role A: Coverage Utility Shadow Scorer

### Purpose

The Coverage Utility shadow scorer investigates whether utility-style scoring
can make coverage/corridor tradeoffs easier to audit. It must run as a read-only
shadow analysis and must not replace live coverage selection.

Expected benefit:

- expose candidate tradeoffs as named considerations;
- compare shadow rank against legacy selected corridor;
- classify disagreements for human review;
- identify missing facts needed for future scoring research.

### Allowed Inputs

Allowed fields include:

- run, tick, event, cycle, and skill identifiers for alignment;
- legacy selected or active corridor id;
- `coverage_candidate_scores`;
- `coverage_decision_trace`;
- coverage summary or outcome proxies such as depleted count, completed dump
  count, terminal stop flag/reason, and selected corridor id.

Candidate-score fields may include the existing coverage payload fields from
`testbed/planner/primitive/coverage/selection.py`, such as:

- `corridor_id`, `cell_id`, `row_id`, and `score`;
- attempt and depletion fields;
- source count/fraction and confidence fields;
- belief coverage and remaining depth;
- first-dig entry and qpos gate fields;
- exemplar distance/id;
- recent-row penalty;
- low-productivity signals.

### Forbidden Inputs And Actions

The shadow scorer must not:

- read policy private attributes;
- read or write mutable coverage owner objects directly;
- call token builders, ACT policies, effect appliers, or state mutation ports;
- replace `CoverageSelectionService` or live coverage runtime coordination;
- claim that a shadow-selected corridor would improve rollout without outcome
  evidence.

### Minimum Output Schema

A shadow result should include:

- `schema_version`;
- `input_fingerprint`;
- tick/event/cycle alignment fields;
- `candidate_ids`;
- `legacy_selected_corridor_id`;
- `legacy_rank_in_shadow`;
- `shadow_top1_corridor_id`;
- `shadow_ranking`;
- `score_breakdown` with input field references;
- `rank_diff_summary`;
- `disagreement_category`;
- `unsupported_or_missing_facts`;
- `confidence`;
- notes that cite input fields only.

Suggested `disagreement_category` values:

- `parity`;
- `tie_or_low_margin`;
- `gate_policy_difference`;
- `legacy_score_higher`;
- `shadow_prefers_unblocked`;
- `missing_fact`;
- `unsupported_case`.

### Required Checks

Before the result can be trusted, the scorer must pass:

- schema validation;
- candidate-id subset validation;
- no state mutation by input snapshot comparison;
- deterministic output for identical input/config;
- trace alignment against the original `select_corridor` event;
- missing-fact handling that lowers confidence instead of inventing defaults;
- tie/margin handling that avoids declaring legacy wrong on low-margin cases.

### Metrics

Track at least:

- `top1_parity_rate`;
- `topk_overlap@k`;
- `mean_abs_rank_delta`;
- `max_rank_delta`;
- score-margin distribution;
- missing-fact count;
- unsupported-case rate;
- disagreement category counts;
- coverage trace alignment rate;
- legacy selected rank distribution;
- sampled human-audit reasonable-diff rate.

### Human Audit Rubric

For sampled disagreements, audit:

- whether the shadow scorer used exactly the same candidate set;
- whether gate, depleted, attempt-limit, and penalty fields were cited;
- whether the score margin supports the strength of the claim;
- whether any outcome proxy was used only as a proxy, not counterfactual truth;
- whether every consideration has an input-field source.

### Current Evidence

Existing tests and reports already support a first read-only study:

- coverage selection ports exclude `planner/self` and use typed ports;
- coverage service selected/candidate scores match the policy facade in unit
  tests;
- selection runtime records candidate scores before terminal paths;
- planner trace exposes coverage fields and decision trace projections;
- the aggregate evidence report marks coverage corridor as confirmed-live.

### Blockers And Stop Conditions

Blockers:

- the current checkout does not include the original `runs/eval/...`
  aggregate-tx24 replay artifacts;
- no Utility-specific schema, rank metric, or tie threshold is locked;
- no per-candidate counterfactual outcome labels exist.

Stop if:

- the scorer invents candidates or missing fields;
- output is not reproducible for identical input;
- the scorer reads private state or mutates owner state;
- disagreement claims exceed the available evidence;
- the proposal tries to become the online selector.

## Tier 1 Role B: LLM Explanation/Report Generator

### Purpose

The LLM explanation/report generator investigates whether a model can turn
public planner reports into field-grounded explanations for human audit. It is
not a decision source and must not emit requested effects.

Expected benefit:

- make trace/report state easier to review;
- expose missing fields instead of hiding them in prose;
- explain coverage decisions, terminal reasons, skill transitions, and recovery
  counters using cited fields;
- distinguish report-derived explanations from decision-source facts.

### Allowed Inputs

Allowed inputs are public read-only report artifacts:

- `debug_state`;
- `planner_trace`;
- `rollout_summary`;
- evidence report classification;
- `coverage_decision_trace`.

### Forbidden Inputs And Actions

The explainer must not:

- read raw `obs`, private policy attributes, owner state objects, or mutation
  ports;
- call ACT, effect appliers, or backend factories;
- output effects, executable commands, or live actions;
- treat natural-language explanation as source-of-truth;
- promote `cell_entry` or `pre_dig_align` into default mainline semantics.

If raw observations are ever requested, a field allowlist and sanitization
policy must be defined first.

### Minimum Output Schema

An explanation result should include:

- `schema_version`;
- `model_id`;
- `prompt_version`;
- `decoding_config`;
- `input_fingerprint`;
- `summary_sections`;
- `claims`;
- `field_citations`;
- `unsupported_claim_rejections`;
- `missing_field_notes`;
- `parked_path_labels`;
- `uncertainty_notes`.

Every claim should cite fields from the input envelope. Allowed source labels
are:

- `debug_state`;
- `planner_trace`;
- `rollout_summary`;
- `evidence_report`.

### Required Checks

Before explanations can be used for audit, they must pass:

- every claim has at least one valid citation path;
- cited paths exist in the input;
- cited values support the claim;
- no invented skill, effect, backend, path, candidate, or artifact path appears;
- report-only fields are labeled as report/trace sources, not decision sources;
- `cell_entry` is labeled parked compatibility/report material when mentioned;
- `pre_dig_align` is labeled opt-in or parked as appropriate;
- unsupported requests are rejected with missing-field notes;
- model id, prompt version, and decoding config are recorded when comparing
  outputs;
- no raw/private input source is used.

### Metrics

Track at least:

- citation coverage;
- citation path validity rate;
- unsupported-claim rejection rate;
- sampled hallucination rate;
- report-only mislabel count;
- parked-path misclassification count;
- human agreement score;
- missing-field exposure count.

### Human Audit Rubric

For sampled explanations, audit:

- whether each key claim is grounded in cited fields;
- whether the source role is correctly labeled;
- whether coverage explanations align with selected corridor and trace fields;
- whether recovery/path explanations stay within available counters/reasons;
- whether parked paths are not promoted to mainline;
- whether uncertainty is explicit when fields are missing.

### Current Evidence

Existing reports and tests already support a first read-only study:

- debug reports expose skill, transition, token, return, coverage, cell-entry,
  and pre-dig-align sections;
- planner trace exposes token contract fields and coverage decision trace;
- rollout summary exposes transition, coverage, pre-dig-align, and dig-replan
  public keys;
- the evidence report distinguishes confirmed-live, report-only, and parked
  paths.

### Blockers And Stop Conditions

Blockers:

- no field-citation checker exists yet;
- no generated explanation audit output exists yet;
- no prompt-injection, data-leakage, or raw-observation sanitization policy
  exists;
- no model/prompt/decoding reproducibility policy exists.

Stop if:

- explanations contain uncited claims;
- citation paths do not exist;
- report-only fields are presented as decision-source facts;
- parked paths drift into default semantics;
- raw/private fields are required without an allowlist;
- explanations are used to drive effects or runtime decisions.

## Deferred Routes And Stop Conditions

### BT Shadow Trace / Visualization

BT remains promising for representing current guard, fallback, recovery, and
handoff structure. The first safe role is shadow trace or visualization. It
should not become an online backend until node/path/condition trace schema,
blackboard policy, action side-effect limits, and RUNNING semantics are locked.

Stop if BT action nodes mutate state directly or if a blackboard becomes an
implicit second planner state.

### LLM/VLM Constraint Generator

A constraint generator may propose typed reject rules or missing guard
hypotheses from reports or visual context. It must remain offline until there is
a constraint schema, parser, validator, provenance policy, and false-positive
review process.

Stop if generated constraints bypass validation or emit unknown requested
effects.

### GOAP / HTN Offline Proposer

GOAP and HTN are useful for researching longer recovery or strategy sequences.
They require a symbolic world/domain/problem schema, operator
precondition/effect semantics, and a plan lifecycle that reconciles with the
one-tick requested-effect contract.

Stop if a multi-step plan owns token construction, coverage scoring, return
mutation, or low-level dispatch.

### TAMP / Feasibility Sidecar

TAMP-style feasibility sidecars may help explain pose, corridor, return, or
pre-dig-align feasibility. They need continuous/geometric facts, feasibility
labels, sampler contracts, latency budgets, and calibration checks.

Stop if the sidecar becomes a hidden selector or writes geometry decisions into
runtime state.

### VLM Fact Extractor

VLM fact extraction is deferred until perception fact schema, confidence,
provenance, time alignment, and a labeled evaluation set exist.

Stop if visual predictions directly enter planner state without owner
accept/reject semantics.

### World/Action Predictor Or WAM

If WAM means world/action model, treat it as a long-term outcome or risk
predictor. It needs action-to-outcome labels, calibration, OOD tests, and
artifact access before it can inform decisions.

Stop if a learned predictor replaces existing safety gates or claims
counterfactual rollout improvement without evidence.

### Online Backend

An online backend is explicitly out of scope for this research phase. Promotion
requires separate implementation design, contracts, tests, artifact validation,
A/B targets, rollback criteria, and a no-default-change guard for `legacy_fsm`.

## Validation Assets And Gaps

Existing assets:

- coverage selection and report tests;
- AGX-style coverage tests for first-dig preference, gates, penalties, decision
  trace, and terminal depletion;
- decision runtime tests for registry behavior and unsupported-backend
  fail-fast;
- requested-effect contract and effect-applier tests;
- debug report, planner trace, rollout summary, and evidence CLI tests;
- baseline aggregate evidence report;
- golden-window parity contract definitions.

Known gaps:

- original aggregate-tx24 replay artifacts are not present in the current
  tracked checkout;
- full action replay is not currently available from the golden-window
  contract alone;
- Utility rank schema has a v0 contract and package/gold checker; no real
  external shadow scorer output is validated yet;
- explanation schema has a v0 contract and gold citation checker; no generated
  LLM explanation output is validated yet;
- human-audit gold examples have a v0 document and aggregate-tx24 checker
  output under ignored `runs/`;
- raw-observation sanitization and LLM security tests are missing;
- multi-rollout evaluation breadth is missing.

## Artifact And Data Prerequisites

Original aggregate-tx24 artifacts, or equivalent replay artifacts, are required
before claiming rollout-level validation for:

- top-1 parity distribution;
- top-k overlap;
- rank-delta statistics;
- episode-level trace alignment;
- golden-window parity recomputation;
- rollout-sampled explanation audit;
- evidence report regeneration;
- cross-run comparison.

Until those artifacts are available, the first phase can still perform:

- schema design;
- static report/docs audit;
- focused unit/fixture validation;
- synthetic shadow examples;
- human audit rubric design.

If a local ignored validation package is available, use its manifest and hashes
as the artifact entry point. The current package convention is:

```text
runs/eval/planner_decision_structure_tier1_validation/<dataset_id>/
  README.md
  manifest.json
  inputs/
  hashes/sha256sums.txt
  schemas/
```

The first archived dataset id used by this research thread is:

```text
aggregate_tx24_20260618
```

This package lives under ignored `runs/` and is not a tracked source of truth.
The tracked source of truth remains this roadmap, the backend contract, and the
Tier 1 schema contract in
`docs/planner_decision_structure_tier1_schema_v0.md`.

## Promotion Gates

Any movement from research to a runtime-affecting path must pass these gates:

1. Artifact/data gate: replay artifacts are readable and the agreed validation
   target is defined.
2. Schema gate: input/output schemas, field allowlists, metrics, and failure
   categories are locked.
3. Safety gate: raw/private access policy, prompt/tool security, and provenance
   rules are defined where applicable.
4. Contract gate: any new facts/effects have owners and tests.
5. Parity gate: legacy behavior is measured and disagreements are audited.
6. Breadth gate: validation covers more than one rollout or one synthetic
   scenario.
7. Promotion gate: A/B acceptance target, rollback criteria, and
   no-default-change tests are explicit.

## Next Research Questions

Recommended next bounded questions:

1. Can a minimal Coverage Utility shadow scorer schema be frozen using existing
   `coverage_candidate_scores` and synthetic fixtures?
2. Can a field-citation grammar be defined for LLM explanations without reading
   raw observations?
3. Which aggregate-tx24 or equivalent replay artifacts are available outside
   the current checkout, and can they be archived into a stable validation
   location?
4. What is the smallest BT node/path/condition trace schema that explains the
   legacy FSM branch chain without introducing blackboard state?
5. Which facts are missing before any GOAP/HTN/TAMP/world-action sidecar can be
   evaluated honestly?
