import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class ParsedSkill(BaseModel):
    """A single skill extracted from the Job Description."""
    name: str = Field(description="Name of the skill (e.g., Python, React, Docker)")
    category: str = Field(description="Importance level: CRITICAL, PREFERRED, or BONUS")


class ParsedExperienceRequirement(BaseModel):
    """A single experience requirement extracted from the Job Description."""
    requirement: str = Field(description="Description of experience (e.g. 'Building async backend microservices')")
    target_role: str = Field(description="Target role or domain (e.g. 'Backend Engineer')")
    min_years: float = Field(default=0.0, description="Minimum years of experience required for this item")
    priority: str = Field(default="MUST_HAVE", description="Priority level: MUST_HAVE, PREFERRED, or BONUS")


class ParsedHiringProfile(BaseModel):
    """
    Complete structured representation of a Job Description.
    Returned by LLM parsing agents.
    """
    technical_skills: list[ParsedSkill] = Field(
        description="List of technical skills with their importance category (CRITICAL, PREFERRED, BONUS)"
    )
    preferred_skills: list[str] = Field(
        description="Nice-to-have skills that are not strictly required"
    )
    min_experience_years: float = Field(
        description="Minimum overall years of experience required. Use 0 for fresher/entry-level roles."
    )
    experience_requirements: list[ParsedExperienceRequirement] = Field(
        default_factory=list,
        description="Structured list of experience requirements categorized by priority (MUST_HAVE, PREFERRED, BONUS)"
    )
    educational_requirements: list[str] = Field(
        description="Required or preferred educational qualifications (e.g., 'B.Tech in Computer Science')"
    )
    key_responsibilities: list[str] = Field(
        description="Main responsibilities and duties of the role"
    )
    soft_skills: list[str] = Field(
        description="Non-technical skills like communication, leadership, teamwork"
    )
    role_expectations: str = Field(
        description="A brief 2-3 sentence summary of what the ideal candidate looks like for this role"
    )


class HiringProfileRead(BaseModel):
    """Schema for returning structured hiring profile to API clients."""
    id: uuid.UUID
    campaign_id: uuid.UUID
    technical_skills: Any
    preferred_skills: Any
    min_experience_years: float
    experience_requirements: Any
    educational_requirements: Any
    key_responsibilities: Any
    soft_skills: Any
    role_expectations: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
