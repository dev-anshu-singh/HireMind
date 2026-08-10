import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class ParsedSkill(BaseModel):
    """A single skill extracted from the Job Description."""
    name: str = Field(description="Name of the skill (e.g., Python, React, Docker)")
    category: str = Field(description="Importance level: CRITICAL, PREFERRED, or BONUS")


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
        description="Minimum years of experience required. Use 0 if not specified."
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
    educational_requirements: Any
    key_responsibilities: Any
    soft_skills: Any
    role_expectations: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
