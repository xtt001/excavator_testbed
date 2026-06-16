"""Coverage service composition."""

from __future__ import annotations

from .base import CoverageServiceBase
from .candidates import CoverageCandidateBuilderMixin
from .progress import CoverageProgressMixin
from .raw_fields import CoverageRawFieldsMixin
from .scoring import CoverageScoringMixin
from .selection import CoverageSelectionMixin
from .snapshots import CoverageSnapshotMixin
from .state_exemplars import CoverageStateExemplarMixin


class CoverageService(
    CoverageSnapshotMixin,
    CoverageProgressMixin,
    CoverageStateExemplarMixin,
    CoverageRawFieldsMixin,
    CoverageScoringMixin,
    CoverageSelectionMixin,
    CoverageCandidateBuilderMixin,
    CoverageServiceBase,
):
    """Coverage/corridor planning service independent of planner ownership."""
