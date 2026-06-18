# Planner Evidence Classification Report

- event_count: 75902
- evidence_packet_count: 3
- dead_candidate_min_packets: 1

| classification | retention | capability | owner | observed | decision | reported |
| --- | --- | --- | --- | ---: | ---: | ---: |
| confirmed-live | retain-and-migrate | `execution.predict_tick` | `PrimitivePlannerACTPolicy.predict` | 5584 | 5584 | 5584 |
| confirmed-live | retain-and-migrate | `fsm.skill_switch` | `PrimitivePlannerACTPolicy._maybe_switch_skill/_set_skill` | 5584 | 5584 | 5584 |
| confirmed-live | retain-and-migrate | `action.dispatch` | `PrimitivePlannerACTPolicy.predict/_active_policy` | 5584 | 5584 | 5584 |
| confirmed-live | retain-and-migrate | `token.goal` | `PrimitivePlannerACTPolicy._goal_tokens/_policy_obs` | 5584 | 5584 | 5584 |
| dead-candidate | retain-legacy-parking | `token.cell_entry` | `PrimitivePlannerACTPolicy._cell_entry_tokens_for_obs` | 0 | 0 | 0 |
| confirmed-live | retain-and-migrate | `token.dig_cut` | `PrimitivePlannerACTPolicy._ensure_dig_cut_plan_for_cycle` | 520 | 520 | 520 |
| confirmed-live | retain-and-migrate | `token.dig_depth_profile` | `PrimitivePlannerACTPolicy._dig_depth_profile_tokens_for_obs` | 5317 | 5317 | 5317 |
| confirmed-live | retain-and-migrate | `token.return_target` | `PrimitivePlannerACTPolicy._ensure_return_target_plan_for_cycle` | 4833 | 4833 | 4833 |
| confirmed-live | retain-and-migrate | `token.return_relocate` | `PrimitivePlannerACTPolicy._return_relocate_tokens_for_obs` | 4833 | 4833 | 4833 |
| confirmed-live | retain-and-migrate | `token.return_start_envelope` | `PrimitivePlannerACTPolicy._return_start_envelope_tokens_for_obs` | 4833 | 4833 | 4833 |
| dead-candidate | retain-legacy-parking | `gate.pre_dig_align` | `PrimitivePlannerACTPolicy._maybe_switch_skill/pre_dig_align` | 0 | 0 | 0 |
| support-live | retain-and-migrate | `metric.dig_progress` | `PrimitivePlannerACTPolicy._update_dig_progress` | 5317 | 0 | 5317 |
| confirmed-live | retain-and-migrate | `gate.dig_to_carry` | `PrimitivePlannerACTPolicy._maybe_switch_skill/dig` | 5317 | 5317 | 5317 |
| confirmed-live | retain-and-migrate | `gate.carry_to_dump` | `PrimitivePlannerACTPolicy._maybe_switch_skill/carry` | 4797 | 1745 | 4797 |
| confirmed-live | retain-and-migrate | `gate.dump_to_return` | `PrimitivePlannerACTPolicy._maybe_switch_skill/dump` | 1310 | 1310 | 1310 |
| confirmed-live | retain-and-migrate | `gate.return_to_dig` | `PrimitivePlannerACTPolicy._maybe_switch_skill/return` | 5584 | 1768 | 5584 |
| confirmed-live | retain-and-migrate | `coverage.corridor` | `PrimitivePlannerACTPolicy coverage corridor helpers` | 5319 | 5319 | 5319 |
| report-only | retain-report-boundary | `debug.debug_state` | `PrimitivePlannerACTPolicy.debug_state/_make_debug_state` | 5584 | 0 | 5584 |
| report-only | retain-report-boundary | `report.rollout_summary` | `PrimitivePlannerACTPolicy.rollout_summary` | 1 | 0 | 1 |
| report-only | retain-report-boundary | `trace.planner_trace` | `PrimitivePlannerACTPolicy.planner_trace` | 1 | 0 | 1 |
| compatibility | retain-compatibility | `policy.public_adapter` | `PrimitivePlannerACTPolicy` | 0 | 0 | 0 |
| compatibility | retain-compatibility | `compat.5p_policy` | `PrimitivePlannerACT5PPolicy` | 0 | 0 | 0 |
