---
name: evidence-guided-refactor
description: Use when refactoring a complex system where code paths may be live, legacy, test-only, compatibility-only, or obsolete, and behavior evidence, source-of-truth ownership, or migration scope is uncertain.
---

# Evidence Guided Refactor

## Overview

Use this skill to refactor from evidence instead of from code shape alone. The
goal is to solve the architectural problem while preserving confirmed behavior,
not to protect every existing path or shrink files for its own sake.

## Required Stance

- Treat existing code as evidence to inspect, not as proof that every path is
  necessary.
- Protection is a constraint, not the objective. If old code is unnecessary,
  duplicative, or private glue, plan to retire it after behavior is locked.
- Do not let line count, age, naming, or test references alone decide whether a
  path should stay, move, or die.
- Prefer the smallest core ownership move that actually reduces coupling over a
  defensive micro-edit that preserves the old structure.

## Evidence Scope

Before moving or deleting behavior, classify the evidence:

- `verified-current`: checked in the live repo, artifact, config, or logs this
  turn.
- `historical`: true for an older run, branch, or version but not necessarily
  current.
- `selected-scenario`: true for one chosen config, rollout, user flow, or test
  packet; do not generalize it to all history.
- `inference`: reasoned from multiple artifacts; name the assumption.
- `needs-confirmation`: semantics, compatibility, or product intent is unclear.

If current evidence and historical evidence disagree, state the scope instead of
collapsing them into a single verdict.

## Path Classification

Classify every candidate path before implementation:

- `confirmed-live`: observed in current behavior evidence and eligible for
  migration.
- `current-unused`: present but absent from the selected current scenario.
- `historically-useful`: had value in older evidence; needs an explicit product
  decision before promotion or removal.
- `public-compatibility`: external API, schema, config, or integration surface
  that needs a stable facade or deprecation plan.
- `private-glue`: old helper, wrapper, mirror state, or compatibility shim that
  can be retired once callers/tests move to the focused owner.
- `test-only`: needed only for tests or diagnostics; update the test contract
  before preserving it as production structure.
- `dead-candidate`: no current evidence and no required compatibility owner.

Do not migrate `current-unused`, `test-only`, or `dead-candidate` paths into the
new architecture as if they were live behavior.

## Refactor Gate

Before coding, answer briefly:

- What problem will this slice solve?
- What evidence proves the target behavior is necessary?
- What source of truth should own the behavior afterward?
- What old code becomes facade, compatibility, test-only, or dead?
- What behavior contracts must stay identical?
- What is explicitly out of scope?
- What verification proves the slice without duplicating unrelated checks?

If these answers cannot be given, do an audit slice instead of a migration slice.

## Work Sizing

- Use one coherent responsibility slice, not one helper at a time.
- Split work only when two changes have different owners, risks, or verification
  standards.
- Merge work when separate micro-slices would repeat the same setup, tests, and
  review without reducing risk.
- Stop when the remaining work is only aesthetic, line-count driven, or a new
  product decision.

## Verification

Lock behavior at the boundary that matters:

- focused tests for the new owner;
- parity or contract tests for old facade versus new owner when behavior must
  stay identical;
- source checks proving private glue is gone when cleanup is the point;
- integration or scenario tests only when the slice touches external behavior;
- docs or design notes only when the source of truth changed.

Avoid running the same verification twice under different names. Planner/review
checks should sample or audit executor evidence unless they are proving a
different risk.

## Stop Conditions

Stop and ask or return an audit result when:

- evidence is missing, stale, or scoped too narrowly for the proposed change;
- the change would alter public API, schema, ordering, config defaults, or
  compatibility without confirmation;
- the new module would mostly wrap old private methods without owning behavior;
- tests preserve private glue instead of the public or owner-level contract;
- the slice is optimized for file size rather than ownership or behavior.
