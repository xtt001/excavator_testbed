---
name: compatibility-cleanup
description: Use when removing obsolete facades, adapters, shims, duplicate state, legacy config branches, or tests that preserve private glue after a focused owner or public contract already exists.
---

# Compatibility Cleanup

## Overview

Use this skill to retire obsolete compatibility material without breaking the
public contract. The key distinction is public compatibility versus private
glue: keep the former intentionally, remove the latter once the real owner is
covered.

## Cleanup Decision

Before deleting anything, classify the surface:

- `public contract`: API, config, schema, CLI, file format, log/report key, or
  integration behavior users may rely on.
- `compat facade`: thin adapter preserving a public import or old integration
  while delegating to the new owner.
- `private glue`: old helper, mirror field, wrapper, monkeypatch target, or
  duplicated reset/writeback path used only by internals or tests.
- `diagnostic-only`: useful for debugging but not part of runtime behavior.
- `test-only`: exists only because tests still call the old private shape.
- `dead`: no owner, no callers, no compatibility reason.

Only `private glue`, `test-only`, and `dead` are default cleanup candidates.
`public contract` needs an explicit compatibility or deprecation decision.

## Preconditions

Proceed only when:

- a focused owner, service, module, or public contract already exists;
- current callers can use that owner directly or through a thin public facade;
- behavior, schema, ordering, and config defaults are already locked by tests or
  evidence;
- the cleanup target is one coherent family of glue, not a mix of unrelated
  semantics.

If the new owner does not exist yet, use a refactor skill first. Cleanup is not
where new semantics should be invented.

## Test Strategy

Use tests to stop protecting the old private shape:

- Add absence/source checks for private names when their removal is the point.
- Move tests from monkeypatching private helpers to exercising the focused
  owner or public facade.
- Keep public compatibility tests only for surfaces that are intentionally
  supported.
- If a test fails because it depended on private glue, decide whether that test
  should move, become compatibility-specific, or be deleted.

Do not add production fallback wrappers just to keep old private tests green.

## Implementation Rules

- Delete the old private path and its duplicate state/writeback in the same
  slice when they are one responsibility.
- Prefer direct calls to the owner over a new pass-through object.
- Keep public facades thin and boring; they should contain no fresh algorithms.
- Do not change behavior, thresholds, ordering, schemas, or defaults unless the
  task explicitly asks for a semantic change.
- Do not bundle cleanup with new feature work, product decisions, or unrelated
  refactors.

## Verification

Use the smallest set that proves cleanup:

- focused owner/public-contract tests;
- absence checks for removed private names;
- compile/lint for touched modules;
- one integration or scenario test only if the public behavior could be
  affected;
- docs update only when public compatibility, deprecation, or source of truth
  changed.

For planner/reviewer closure, audit executor evidence instead of rerunning the
same full suite unless a different risk is being checked.

## Stop Conditions

Stop and ask when:

- the target might be a public contract;
- current callers still need the old path;
- no focused owner exists;
- deleting the path would silently change defaults, schemas, ordering, or
  external behavior;
- the cleanup justification is mainly line count or aesthetics.
