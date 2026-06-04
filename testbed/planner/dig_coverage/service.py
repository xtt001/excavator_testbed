"""Coverage service composition."""

from __future__ import annotations

from .base import CoverageServiceBase
from .candidates import CoverageCandidateBuilderMixin
from .progress import CoverageProgressMixin
from .raw_fields import CoverageRawFieldsMixin
from .selection import CoverageSelectionMixin


class CoverageService(
    CoverageProgressMixin,
    CoverageRawFieldsMixin,
    CoverageSelectionMixin,
    CoverageCandidateBuilderMixin,
    CoverageServiceBase,
):
    """Coverage/corridor planning service independent of planner ownership."""
