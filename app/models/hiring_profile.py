import uuid
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class HiringProfile(SQLModel, table=True):
    __tablename__ = "hiring_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", unique=True, index=True, nullable=False)
    
    technical_skills: Any = Field(default_factory=list, sa_column=Column(JSON))
    preferred_skills: Any = Field(default_factory=list, sa_column=Column(JSON))
    min_experience_years: float = Field(default=0.0, nullable=False)
    educational_requirements: Any = Field(default_factory=list, sa_column=Column(JSON))
    key_responsibilities: Any = Field(default_factory=list, sa_column=Column(JSON))
    soft_skills: Any = Field(default_factory=list, sa_column=Column(JSON))
    role_expectations: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign: Optional["Campaign"] = Relationship(back_populates="hiring_profile")
