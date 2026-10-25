"""Import every ORM model so Base.metadata is complete (used by Alembic and tests)."""

from app.core.orm import Base
from app.modules.actions.models import ActionRecord
from app.modules.assets.models import AssetState, BiologicalAsset, LifecycleEvent
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Species
from app.modules.datasets.models import (
    Dataset,
    DatasetEvidence,
    DatasetSample,
    DatasetSplit,
    DatasetStatusHistory,
    LabelReview,
)
from app.modules.evidence.models import Evidence
from app.modules.harvests.models import HarvestRecord
from app.modules.identity.models import AuthThrottle, Organization, RefreshTokenRow, User
from app.modules.intelligence.models import AgentRun, Recommendation
from app.modules.issues.models import Issue, IssueObservation, IssueStatusHistory
from app.modules.locations.models import Location
from app.modules.observations.models import Observation
from app.modules.protocols.models import EvaluationProtocol, ProtocolSignoff
from app.modules.schedules.models import InspectionSchedule, ScheduleOccurrence
from app.modules.tasks.models import Task, TaskStatusHistory
from app.modules.workspaces.models import Membership, Workspace

__all__ = [
    "ActionRecord",
    "AssetState",
    "AuditEvent",
    "AuthThrottle",
    "Base",
    "Dataset",
    "DatasetEvidence",
    "DatasetSample",
    "DatasetSplit",
    "DatasetStatusHistory",
    "LabelReview",
    "BiologicalAsset",
    "Evidence",
    "EvaluationProtocol",
    "HarvestRecord",
    "InspectionSchedule",
    "Issue",
    "LifecycleEvent",
    "IssueObservation",
    "IssueStatusHistory",
    "Location",
    "Membership",
    "Observation",
    "ProtocolSignoff",
    "Organization",
    "AgentRun",
    "Recommendation",
    "RefreshTokenRow",
    "ScheduleOccurrence",
    "Species",
    "Task",
    "TaskStatusHistory",
    "User",
    "Workspace",
]
