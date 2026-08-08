import uuid
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

if TYPE_CHECKING:
    from app.models.candidate import Candidate


class CandidateProfile(SQLModel, table=True):
    __tablename__ = "candidate_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = Field(foreign_key="candidates.id", unique=True, index=True, nullable=False)
    
    parsed_education: Any = Field(default_factory=list, sa_column=Column(JSON))
    parsed_skills: Any = Field(default_factory=list, sa_column=Column(JSON))
    parsed_work_experience: Any = Field(default_factory=list, sa_column=Column(JSON))
    parsed_projects: Any = Field(default_factory=list, sa_column=Column(JSON))
    
    portfolio_insights: Any = Field(default_factory=dict, sa_column=Column(JSON))
    certifications: Any = Field(default_factory=list, sa_column=Column(JSON))
    achievements: Any = Field(default_factory=list, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    candidate: Optional["Candidate"] = Relationship(back_populates="profile")
