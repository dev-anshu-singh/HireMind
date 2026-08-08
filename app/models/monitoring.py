import uuid
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON, Enum as SQLEnum

from app.models.enums import ActionProposed, ActionStatus

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class CampaignMonitoringLog(SQLModel, table=True):
    __tablename__ = "campaign_monitoring_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", index=True, nullable=False)
    
    total_applications_count: int = Field(nullable=False)
    expected_applications_count: int = Field(nullable=False)
    days_remaining: int = Field(nullable=False)
    
    agent_reasoning: str = Field(nullable=False)
    
    action_proposed: ActionProposed = Field(
        sa_column=Column(SQLEnum(ActionProposed), nullable=False, default=ActionProposed.NONE)
    )
    status: ActionStatus = Field(
        sa_column=Column(SQLEnum(ActionStatus), nullable=False, default=ActionStatus.PENDING_APPROVAL)
    )
    
    guardrail_flags: Any = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign: Optional["Campaign"] = Relationship(back_populates="monitoring_logs")
