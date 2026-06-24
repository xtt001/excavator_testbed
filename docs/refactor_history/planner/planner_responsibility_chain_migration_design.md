# Primitive Planner Responsibility-Chain Migration Design

Status: **historical design target, not an implementation plan**.

This document defines how future primitive-planner responsibility-chain
migrations should be selected, simulated, and accepted after the backend-ready
contract and initial package-layout seed. It is a planning artifact. It does
not move files, change imports, or alter runtime behavior by itself.

## Purpose

The current code has moved far beyond the original monolithic
`PrimitivePlannerACTPolicy`: backend facts, decision runtime, requested effects,
return handoff, coverage, token, report, and compatibility owners now exist as
focused modules. The remaining risk is that future cleanup keeps treating those
modules as isolated files instead of coherent SVG lanes.

A responsibility-chain migration should make one production chain easier to
understand end to end:

```text
policy shell weld
  -> focused runtime/service owner
  -> typed state/facts/effects/report contract
  -> tests that lock behavior at the focused owner
  -> package lane that reflects the SVG architecture
```

The goal is cleaner ownership and import direction, not smaller files for their
own sake.

## Relation To Existing Targets

Use this document with:

- `docs/planner_execution_abstraction_flow.svg`
- `docs/planner_policy_shell_target_interface.md`
- `docs/planner_package_layout_target.md`
- `docs/planner_primitive_interface_standard.md`
- `docs/planner_current_code_architecture_plan.md`

The policy shell target defines what `PrimitivePlannerACTPolicy` may keep. The
package-layout target defines where primitive modules should live. This
document defines how to choose the next production responsibility chain before
writing implementation code.

## Definition Of A Responsibility Chain

A chain is not a private-method cluster. It is a stable production capability
with a target owner and observable behavior contract.

Each candidate chain must identify:

- the production responsibility, named independently of current private method
  names;
- the target owner module or package lane;
- the shell role that should remain in `PrimitivePlannerACTPolicy`;
- the state, facts, effects, or report contracts it uses;
- old import paths and private test hooks that may be reclassified;
- behavior that must remain unchanged.

If those fields cannot be named, the next action is a read-only audit, not an
implementation slice.

## Current Valid Chain Families

These families are valid planning areas after the backend-ready closure and
decision/facts package seed:

| Chain family | Target lane | Primary reason to migrate |
| --- | --- | --- |
| Requested effects and return handoff | `primitive.effects` | Effect application should remain outside the policy shell and should have a package lane matching the SVG DecisionResult/effect box. |
| Token observation and planning | `primitive.token` | Token planner factories, observation injection, and return/dig token planning are not public shell responsibilities. |
| Coverage selection/effects/reports | `primitive.coverage` | Coverage has multiple focused owners but still carries broad import and test surfaces; it needs lane-level ownership. |
| Report composition and compatibility payloads | `primitive.report` and `primitive.compatibility` | Public output methods should expose schema only; schema assembly and parked payloads should remain focused. |
| Execution lifecycle and tick finalization | `primitive.execution` | Tick order and lifecycle state should stay coherent around prepare/decide/apply/dispatch/finalize. |
| Adapter config normalization | `primitive.config` | Config is large, but should split only when a focused config owner is clearer than the existing normalizer. |

These are planning areas, not permission to migrate all files in a family at
once.

## Slice Selection Gates

A migration slice may proceed only if all gates pass:

1. **Owner clarity.** The target owner has one stable responsibility and is not
   a pass-through facade over old policy-private methods.
2. **Behavior lock.** The slice names branch order, reason strings, token
   schema, public debug/summary/trace schema, reset timing, default backend,
   and selected AGX behavior that must stay unchanged.
3. **Import classification.** Old paths are classified as `public-compat`,
   `cross-module-compat`, `internal-only`, `test-only`, or `dead-candidate`.
4. **Shell boundary.** The policy shell keeps only public adapter methods,
   low-level policy handles, boundary-detector wiring, focused owner identity,
   default backend registration, and explicit typed welds.
5. **No broad containers.** The slice does not introduce planner `self`,
   blackboards, callback bags, broad config dictionaries, or one-callback-per-
   private-method port sets.
6. **No parked promotion.** `cell_entry`, `pre_dig_align`, and removed runtime
   paths are not promoted into mainline backend, token, coverage, or behavior
   tree surfaces without explicit approval.

## Simulation Before Implementation

Before dispatching an implementation executor, the planner should run a
design-only simulation. The simulation must answer:

- What files would move or change imports?
- Which old imports remain as compatibility facades?
- Which tests should stop importing or monkeypatching policy-private hooks?
- Which focused tests prove behavior after the move?
- What source checks prove the new package does not import the policy shell?
- What would make the slice stop rather than continue?

The simulation is allowed to reject a candidate and select a different chain.
It must not write production code.

## Parallel Work Policy

Parallel work is useful only before implementation:

- allowed: read-only inventories for token, coverage, report, compatibility,
  and execution lanes;
- allowed: import-impact scans and simulated patch plans for disjoint lanes;
- not allowed: multiple executors editing `PrimitivePlannerACTPolicy` at the
  same time;
- not allowed: a package relocation slice and a semantic responsibility
  migration touching the same tests or shell welds in parallel.

Implementation should merge one lane slice at a time unless two slices are
strictly disjoint and do not touch the policy shell or the same public output
tests.

## Verification Standard

Minimum verification for a responsibility-chain migration:

- focused tests for the target owner;
- import smoke for old and new paths when compatibility facades remain;
- selected AGX subset when the chain affects token, coverage, return, decision,
  or action behavior;
- `python -m compileall` for moved modules, facades, and touched tests;
- `python scripts/planner_refactor_guard.py --check-plan-contract`;
- `python scripts/planner_refactor_guard.py --check-skill-contract`;
- `git diff --check`;
- source checks for planner-self, policy-self, blackboard, callback-bag, and
  old private wrapper imports.

Documentation-only simulations may skip pytest but must run `git diff --check`
and the guard scripts if they touch plan contracts.

## Rejected Slice Examples

Reject these shapes:

- moving one helper only because it reduces `primitive_planner.py` line count;
- creating a service that forwards one-to-one to old private methods;
- keeping an old private policy method because tests mention it, without a
  production compatibility owner;
- moving package paths while also changing coverage selection or token planning
  semantics;
- creating a broad `PrimitivePlannerPorts` or blackboard object that recreates
  planner `self` indirectly.

## Preferred Next Planning Step

After a package-layout seed, the next non-code step should simulate the token,
coverage, report, and effects/return-handoff chains in parallel. The planner
should then choose one implementation slice with the clearest target owner and
lowest semantic ambiguity.
