# Deprecated Primitive Scheduler Artifacts

This folder preserves retired primitive-scheduler ideas and private facade code
before removal from the live planner shell.

These files are not runtime modules. Do not import from this directory, do not
extend these snippets, and do not treat them as source-of-truth. Live semantics
must continue to come from `testbed/`, especially the contract, planner service,
and capability modules listed in
`docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md`.

## Why This Exists

The primitive scheduler refactor has two different kinds of deprecated artifacts:

- **Negative experimental branches**, such as the 5P approach/release split. These
  were real design attempts and need their original reasoning and failure evidence
  preserved.
- **Migration facades**, such as old private planner methods that were kept while
  tests and callers moved to focused service/capability modules. When those facades
  become zero-call pass-through wrappers, they should be archived here before being
  removed from `PrimitivePlannerACTPolicy`.

Archiving does not mean the old path is a supported compatibility surface. It means
future agents can see what was tried, why it existed, and why live code should not
keep depending on it.

## Current Records

- `primitive_planner_pre_facade_cleanup_2026_06_17.py.txt`: complete
  `testbed/policies/hybrid/primitive_planner.py` snapshot taken immediately before
  the 2026-06-17 zero-call private facade cleanup.
- `primitive_planner_deprecated_facades.py.txt`: private facade snippets that are
  already removed or identified as zero-call retirement candidates. The full
  snapshot above is authoritative for any removed facade not repeated as a
  focused snippet here.
- `primitive_scheduler_negative_experiments.md`: design rationale and negative
  evidence for deprecated scheduler experiments, starting with the 5P split.
