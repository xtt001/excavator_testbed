# Planner Evidence Trace Tool

Status: active tool documentation.

The planner evidence tool classifies primitive planner capabilities from
rollout evidence. It exists to decide what should be retained, migrated,
held for more evidence, or parked outside the mainline architecture during
planner refactors.

The tool does not delete code. It produces evidence-backed retention decisions.

## Commands

Run against an existing rollout JSONL, planner trace, and rollout summary:

```bash
python -m testbed.cli.planner_evidence classify \
  --rollout-jsonl runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl \
  --planner-trace runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_planner_trace.json \
  --rollout-summary runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_summary.json \
  --output-json docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.json \
  --output-md docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md
```

Installed console-script form:

```bash
tb-planner-evidence classify --rollout-jsonl <path> --output-json <path>
```

The CLI accepts:

- `--rollout-jsonl`: existing rollout step JSONL from eval or Unity rollout
- `--planner-trace`: existing `rollout_000_planner_trace.json`
- `--rollout-summary`: existing `rollout_000_summary.json`
- `--evidence-jsonl`: future instrumented planner evidence JSONL rows

## Schema

Instrumented evidence JSONL rows use schema version `1`:

- `tick_id`
- `capability_id`
- `event_type`
- `producer`
- `observed`
- `consumed_by_decision`
- `reported`
- `supports`
- `payload`

The stable code owner is `testbed/planner/evidence_trace.py`.

## Classifications

`confirmed-live`:
Observed in rollout evidence and consumed by a planner decision path.

`support-live`:
Observed as a metric or helper fact that supports a confirmed-live capability.

`report-only`:
Observed only through debug, trace, or rollout summary reporting. Keep it at a
diagnostic/reporting boundary.

`compatibility`:
Not necessarily observed in this rollout, but kept because it owns public API or
legacy compatibility.

`test-only`:
Kept only for tests or diagnostics until a better owner exists.

`not-observed`:
Not seen in the selected evidence packet, but the packet count is below the
configured dead-candidate threshold or the capability is explicitly protected.

`dead-candidate`:
No success-path evidence shows the capability contributes, or failure evidence
does not highlight it as a missing cause. Once the configured evidence threshold
is met, unobserved non-compatibility capabilities default to
`dead-candidate`.

## Retention Decisions

The report maps classifications to decisions:

- `retain-and-migrate`: migrate behind the execution kernel/capability/backend
  architecture when that slice is selected.
- `retain-report-boundary`: keep as debug, trace, or summary output.
- `retain-compatibility`: keep as a public or legacy compatibility shell.
- `retain-test-only`: keep only while the tests or diagnostics need it.
- `hold-unobserved`: hold only when evidence is below threshold or explicit
  protection exists.
- `retain-legacy-parking`: do not migrate into the mainline backend/runtime
  architecture; keep only as legacy, diagnostic, test-only, or compatibility
  material until a later explicit cleanup review.

## Current Baseline Report

The current report is:

- `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.json`
- `docs/planner_evidence_reports/2026-06-18-baseline-aggregate_tx24.md`

Input evidence:

- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000.jsonl`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_planner_trace.json`
- `runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/rollouts/rollout_000_summary.json`

Initial decision, updated after checking the successful mainline rollout
configuration:

- Retain and migrate the execution tick, FSM skill switch, action dispatch,
  goal token, dig-cut token, dig-depth-profile token, return-target token,
  return-relocate token, return-start-envelope token, dig progress metric,
  dig-to-carry gate, carry-to-dump gate, dump-to-return gate, return-to-dig
  gate, and coverage corridor logic.
- Retain debug state, rollout summary, and planner trace at reporting
  boundaries.
- Retain `PrimitivePlannerACTPolicy` and `PrimitivePlannerACT5PPolicy` as
  compatibility owners for now.
- Mark `token.cell_entry` and `gate.pre_dig_align` as `dead-candidate` /
  `retain-legacy-parking` for the current mainline route. The successful
  `aggregate_tx24` rollout disables `policy.pre_dig_align.enabled`, has no
  `policy.cell_entry` / `cell_entry_enabled` setting, and uses
  `dig_low_dim_keys: [qpos, qvel, dig_cut_tokens]` instead of
  `cell_entry_tokens`.
- Do not migrate `cell_entry` or `pre_dig_align` into the execution-kernel /
  backend architecture. Keep them only as legacy/diagnostic parking material
  while legacy config and test owners are checked.

## Limits

The current report is based on an existing rollout artifact. It is enough to
decide the first retain/migrate set and to mark disabled mainline features as
legacy parking candidates. It is not by itself a code deletion patch.

Before any later deletion review, remove, move, or explicitly reclassify any
legacy config, diagnostic config, test-only owner, or compatibility owner that
still references the parked capability.
