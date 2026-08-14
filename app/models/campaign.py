import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, Enum as SQLEnum

from app.models.enums import EmploymentType, CampaignStatus

if TYPE_CHECKING:
    from app.models.hiring_profile import HiringProfile
    from app.models.preference import RecruiterPreference
    from app.models.job_post import JobPost
    from app.models.candidate import Candidate
    from app.models.monitoring import CampaignMonitoringLog


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    company_name: str = Field(index=True, nullable=False)
    company_description: Optional[str] = Field(default=None)
    job_title: str = Field(nullable=False)
    raw_job_description: str = Field(nullable=False)
    
    employment_type: EmploymentType = Field(
        sa_column=Column(SQLEnum(EmploymentType), nullable=False, default=EmploymentType.FULL_TIME)
    )
    location: str = Field(nullable=False)
    salary_range: Optional[str] = Field(default=None)
    
    status: CampaignStatus = Field(
        sa_column=Column(SQLEnum(CampaignStatus), nullable=False, default=CampaignStatus.SETUP)
    )
    
    target_shortlist_size: int = Field(default=5, nullable=False)
    min_target_applicants: int = Field(default=20, nullable=False)
    desired_applicants: Optional[int] = Field(default=None)
    duration_days: int = Field(default=30, nullable=False)
    application_deadline: Optional[datetime] = Field(default=None)
    
    auto_close_on_deadline: bool = Field(default=True, nullable=False)
    auto_approve_reposts: bool = Field(default=False, nullable=False)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    hiring_profile: Optional["HiringProfile"] = Relationship(
        back_populates="campaign",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    recruiter_preference: Optional["RecruiterPreference"] = Relationship(
        back_populates="campaign",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    job_posts: list["JobPost"] = Relationship(
        back_populates="campaign",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    candidates: list["Candidate"] = Relationship(
        back_populates="campaign",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    monitoring_logs: list["CampaignMonitoringLog"] = Relationship(
        back_populates="campaign",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
