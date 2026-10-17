"""Import every ORM model so Base.metadata is complete (used by Alembic and tests)."""

from app.core.orm import Base
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Species
from app.modules.evidence.models import Evidence
from app.modules.identity.models import AuthThrottle, Organization, RefreshTokenRow, User
from app.modules.intelligence.models import AgentRun, Recommendation
from app.modules.issues.models import Issue, IssueObservation, IssueStatusHistory
from app.modules.locations.models import Location
from app.modules.observations.models import Observation
from app.modules.tasks.models import Task, TaskStatusHistory
from app.modules.workspaces.models import Membership, Workspace

__all__ = [
    "AssetState",
    "AuditEvent",
    "AuthThrottle",
    "Base",
    "BiologicalAsset",
    "Evidence",
    "Issue",
    "IssueObservation",
    "IssueStatusHistory",
    "Location",
    "Membership",
    "Observation",
    "Organization",
    "AgentRun",
    "Recommendation",
    "RefreshTokenRow",
    "Species",
    "Task",
    "TaskStatusHistory",
    "User",
    "Workspace",
]
