import uuid
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class RecruiterPreference(SQLModel, table=True):
    __tablename__ = "recruiter_preferences"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", unique=True, index=True, nullable=False)
    
    skill_priorities: Any = Field(default_factory=dict, sa_column=Column(JSON))
    experience_weights: Any = Field(default_factory=dict, sa_column=Column(JSON))
    evaluation_weights: Any = Field(default_factory=dict, sa_column=Column(JSON))
    evidence_sources: Any = Field(default_factory=list, sa_column=Column(JSON))
    
    min_cgpa: Optional[float] = Field(default=None)
    immediate_joiner_only: bool = Field(default=False, nullable=False)
    work_authorization: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign: Optional["Campaign"] = Relationship(back_populates="recruiter_preference")
