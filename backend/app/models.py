"""Import every ORM model so Base.metadata is complete (used by Alembic and tests)."""

from app.core.orm import Base
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.catalog.models import Species
from app.modules.identity.models import Organization, RefreshTokenRow, User
from app.modules.intelligence.models import Recommendation
from app.modules.issues.models import Issue, IssueObservation, IssueStatusHistory
from app.modules.locations.models import Location
from app.modules.observations.models import Observation
from app.modules.tasks.models import Task, TaskStatusHistory
from app.modules.workspaces.models import Membership, Workspace

__all__ = [
    "AssetState",
    "Base",
    "BiologicalAsset",
    "Issue",
    "IssueObservation",
    "IssueStatusHistory",
    "Location",
    "Membership",
    "Observation",
    "Organization",
    "Recommendation",
    "RefreshTokenRow",
    "Species",
    "Task",
    "TaskStatusHistory",
    "User",
    "Workspace",
]
