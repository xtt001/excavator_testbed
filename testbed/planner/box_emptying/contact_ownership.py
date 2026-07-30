"""Typed ownership contract for box-safety coverage mutations."""

from __future__ import annotations

from dataclasses import dataclass

CONTACT_KIND_NONE = "none"
CONTACT_KIND_WALL = "wall"
CONTACT_KIND_HARD_BOTTOM = "hard_bottom"
CONTACT_KINDS = frozenset(
    {
        CONTACT_KIND_NONE,
        CONTACT_KIND_WALL,
        CONTACT_KIND_HARD_BOTTOM,
    }
)


@dataclass(frozen=True)
class SafetyContactOwnership:
    """Keep wall blocking and hard-bottom exhaustion mutually exclusive."""

    contact_kind: str = CONTACT_KIND_NONE
    blocked_corridor_id: int = -1
    depth_exhausted_cell_id: int = -1
    wall_contact_session_count: int = 0

    def validate(self) -> SafetyContactOwnership:
        kind = str(self.contact_kind)
        blocked = int(self.blocked_corridor_id)
        exhausted = int(self.depth_exhausted_cell_id)
        wall_sessions = int(self.wall_contact_session_count)
        if kind not in CONTACT_KINDS:
            raise ValueError(
                f"unsupported safety contact_kind {kind!r}; "
                f"expected one of {sorted(CONTACT_KINDS)}"
            )
        if kind == CONTACT_KIND_NONE:
            if blocked >= 0 or exhausted >= 0:
                raise ValueError(
                    "none contact cannot carry coverage mutation ids"
                )
            if wall_sessions != 0:
                raise ValueError(
                    "none contact cannot carry a typed wall session"
                )
        elif kind == CONTACT_KIND_WALL:
            if exhausted >= 0:
                raise ValueError(
                    "wall contact cannot carry depth_exhausted_cell_id"
                )
            if wall_sessions <= 0:
                raise ValueError(
                    "wall contact requires a nonzero typed wall session"
                )
        else:
            if blocked >= 0:
                raise ValueError(
                    "hard_bottom contact cannot carry blocked_corridor_id"
                )
            if wall_sessions != 0:
                raise ValueError(
                    "hard_bottom contact cannot carry a typed wall session"
                )
        return self


def validate_contact_ownership(
    *,
    contact_kind: str,
    blocked_corridor_id: int,
    depth_exhausted_cell_id: int,
    wall_contact_session_count: int = 0,
) -> SafetyContactOwnership:
    """Build and validate one append-only contact ownership value."""

    return SafetyContactOwnership(
        contact_kind=str(contact_kind),
        blocked_corridor_id=int(blocked_corridor_id),
        depth_exhausted_cell_id=int(depth_exhausted_cell_id),
        wall_contact_session_count=int(wall_contact_session_count),
    ).validate()


__all__ = [
    "CONTACT_KIND_HARD_BOTTOM",
    "CONTACT_KIND_NONE",
    "CONTACT_KIND_WALL",
    "CONTACT_KINDS",
    "SafetyContactOwnership",
    "validate_contact_ownership",
]
