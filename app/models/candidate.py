import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, Enum as SQLEnum

from app.models.enums import ApplicationStatus

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.candidate_profile import CandidateProfile
    from app.models.evaluation import CandidateEvaluation


class Candidate(SQLModel, table=True):
    __tablename__ = "candidates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", index=True, nullable=False)
    
    full_name: str = Field(nullable=False)
    email: str = Field(index=True, nullable=False)
    phone: Optional[str] = Field(default=None)
    
    raw_resume_url: str = Field(nullable=False)
    github_url: Optional[str] = Field(default=None)
    linkedin_url: Optional[str] = Field(default=None)
    portfolio_url: Optional[str] = Field(default=None)
    
    application_status: ApplicationStatus = Field(
        sa_column=Column(SQLEnum(ApplicationStatus), nullable=False, default=ApplicationStatus.APPLIED)
    )
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign: Optional["Campaign"] = Relationship(back_populates="candidates")
    profile: Optional["CandidateProfile"] = Relationship(
        back_populates="candidate",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    evaluation: Optional["CandidateEvaluation"] = Relationship(
        back_populates="candidate",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
