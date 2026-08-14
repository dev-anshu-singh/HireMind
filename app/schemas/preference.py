import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class RecruiterPreferenceCreate(BaseModel):
    """
    Schema for recruiter submitting custom configuration preferences.
    """
    skill_priorities: dict[str, str] = Field(
        default_factory=dict,
        description="Map of skill names to priority: MUST_HAVE, PREFERRED, or BONUS",
        examples=[{"Python": "MUST_HAVE", "FastAPI": "MUST_HAVE", "Docker": "PREFERRED"}]
    )
    experience_weights: dict[str, float] = Field(
        default_factory=lambda: {"min_years_weight": 0.5, "skill_depth_weight": 0.5},
        description="Relative weighting for experience parameters"
    )
    evaluation_weights: dict[str, float] = Field(
        default_factory=lambda: {"technical_depth": 0.50, "experience": 0.30, "soft_skills": 0.20},
        description="Overall evaluation weights (technical_depth + experience + soft_skills should equal 1.0)"
    )
    evidence_sources: list[str] = Field(
        default_factory=lambda: ["GITHUB_REPOS", "WORK_EXPERIENCE", "PROJECTS"],
        description="Prioritized list of candidate evidence sources"
    )
    min_cgpa: Optional[float] = Field(
        default=None,
        description="Minimum CGPA cutoff requirement (e.g. 7.5)"
    )
    immediate_joiner_only: bool = Field(
        default=False,
        description="Flag restricting shortlist to immediate joiners only"
    )
    work_authorization: Optional[str] = Field(
        default=None,
        description="Work authorization requirement (e.g., 'US Citizen', 'Remote India')"
    )


class RecruiterPreferenceRead(BaseModel):
    """
    Schema for returning stored recruiter preferences from database.
    """
    id: uuid.UUID
    campaign_id: uuid.UUID
    skill_priorities: Any
    experience_weights: Any
    evaluation_weights: Any
    evidence_sources: Any
    min_cgpa: Optional[float]
    immediate_joiner_only: bool
    work_authorization: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RecruiterPreferenceDefaults(BaseModel):
    """
    Intelligent defaults generated from HiringProfile for recruiter configuration.
    """
    campaign_id: uuid.UUID
    suggested_skill_priorities: dict[str, str]
    suggested_evaluation_weights: dict[str, float]
    suggested_evidence_sources: list[str]
    min_experience_years: float
