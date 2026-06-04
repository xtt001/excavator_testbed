"""Decision contracts shared by primitive scheduler service facades."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PrimitiveBoundaryFacts:
    profile_name: str = ""
    qualified_dig_start: bool = False
    next_dig_entry_ready: bool = False
    dig_start: bool = False
    dig_complete: bool = False
    dump_committed_start: bool = False
    release_onset: bool = False
    dump_complete: bool = False
    dump_end: bool = False
    raw_event: object | None = None
    debug: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandoffDecision:
    ready: bool
    from_skill: str
    to_skill: str | None
    reason: str
    checks: Mapping[str, Any] = field(default_factory=dict)
    debug: Mapping[str, Any] = field(default_factory=dict)


def primitive_boundary_facts_from_event(
    event: object | None,
    *,
    profile_name: str = "",
) -> PrimitiveBoundaryFacts:
    return PrimitiveBoundaryFacts(
        profile_name=str(profile_name),
        qualified_dig_start=bool(getattr(event, "qualified_dig_start", False)),
        next_dig_entry_ready=bool(getattr(event, "next_dig_entry_ready", False)),
        dig_start=bool(getattr(event, "dig_start", False)),
        dig_complete=bool(getattr(event, "dig_complete", False)),
        dump_committed_start=bool(getattr(event, "dump_committed_start", False)),
        release_onset=bool(getattr(event, "release_onset", False)),
        dump_complete=bool(getattr(event, "dump_complete", False)),
        dump_end=bool(getattr(event, "dump_end", False)),
        raw_event=event,
    )
