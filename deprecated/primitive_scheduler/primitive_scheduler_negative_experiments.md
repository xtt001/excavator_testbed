# Primitive Scheduler Negative Experiments

This note records deprecated scheduler directions that were useful experiments but
should not silently return as mainline planner semantics.

## 5P Approach/Release Split

### Original Design Intent

The 5P split tried to separate dump into two smaller skills:

- `approach_dump`: move toward and align with the dump target.
- `dump_release`: perform the release action after approach was considered ready.

The motivation was reasonable at the time: if release timing were a clean boundary,
the planner could learn or script the approach and release responsibilities more
explicitly than a single mixed `dump` primitive.

### Experimental Result

The diagnostic work found the opposite. Professional teleop does not naturally
pause at a clean `approach -> release` boundary. Operators blend swing, boom/stick
alignment, bucket opening, visual checking, and post-dump hold into one mixed dump
behavior.

The documented evidence is:

- `docs/v1_to_v2_3_exploration_path.md` records that 5P data windows were sparse,
  clean boundaries were hard to find, and the split made behavior cloning learn
  fragmented and unnatural responsibilities.
- `docs/v2_2_4primitives/summary.md` records the ownership pivot back to four
  primitives because strict `approach_dump` was not intuitive for human teleop and
  produced too few clean approach windows.
- `docs/v2_2_restart_layered_control_plan.md` records the standing conclusion that
  5P split is not suitable for professional-driver natural dump.

### Current Decision

5P remains compatibility-only. The live implementation is in
`testbed/policies/hybrid/primitive_planner_5p.py` only so old imports, registry
entries, diagnostics, and tests continue to work. It must not gain new acceptance
criteria, branch-order changes, or rollout semantics unless the user explicitly
reopens the 5P design.

## Planner Private Facade Surface

### Original Design Intent

During behavior-preserving service extraction, private planner methods were kept as
temporary facades. This reduced migration risk because tests and diagnostics could
continue to call familiar `policy._xxx` entry points while source-of-truth logic
moved into service/capability modules.

### Why Some Facades Are Now Deprecated

Once a facade has no call sites and only forwards to a stable service helper, keeping
it in `PrimitivePlannerACTPolicy` has negative value:

- It makes the large planner shell look like the owner of semantics that already
  live elsewhere.
- It invites future tests to bind to private shell fields instead of capability
  contracts.
- It increases the private API surface without preserving a real compatibility
  need.

The replacement is not to delete history. The replacement is to archive exact old
snippets in this directory, then remove or narrow the live private facade only after
focused tests prove branch order, thresholds, reason strings, reset timing,
debug/schema fields, token contracts, and rollout output remain unchanged.

