"""Hard-bottom box-emptying residual planning contracts and services."""

from testbed.planner.box_emptying.contracts import TerrainBoxResidual
from testbed.planner.box_emptying.online_provider import (
    BoxEmptyingResidualPlanService,
)

__all__ = ["BoxEmptyingResidualPlanService", "TerrainBoxResidual"]
