import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class EvaluatedPillarScores(BaseModel):
    """
    Sub-scores for the 3 core evaluation pillars.
    """
    technical_score: float = Field(description="Deterministic Python skill mapping score (0.0 - 100.0)")
    soft_skills_score: float = Field(description="Vector embedding cosine similarity score (0.0 - 100.0)")
    experience_score: float = Field(description="Rule-constrained Gemini experience score (0.0 - 100.0)")


class ExperienceEvaluationOutput(BaseModel):
    """
    Structured output returned by the Rule-Constrained Experience Evaluator Agent.
    """
    score: float = Field(description="Experience score from 0.0 to 100.0")
    duration_subscore: float = Field(description="Duration ratio score (0-40)")
    title_alignment_subscore: float = Field(description="Role title alignment score (0-40)")
    scope_subscore: float = Field(description="Domain scope & complexity score (0-20)")
    justification: str = Field(description="Clear explanation of the experience score")


class CandidateEvaluationRead(BaseModel):
    """
    Database response schema matching candidate_evaluations table.
    """
    id: uuid.UUID
    candidate_id: uuid.UUID
    campaign_id: uuid.UUID
    screening_strategy: str
    overall_match_score: float
    skill_match_score: float
    semantic_score: float
    experience_score: float
    portfolio_score: float
    rank: Optional[int]
    is_shortlisted: bool
    key_strengths: list[str] = Field(default_factory=list)
    potential_concerns: list[str] = Field(default_factory=list)
    summary_reasoning: str
    evaluated_at: datetime

    model_config = {"from_attributes": True}


class LeaderboardItem(BaseModel):
    """
    DTO for candidate ranking item on the recruiter leaderboard.
    """
    candidate_id: uuid.UUID
    full_name: str
    email: str
    rank: Optional[int]
    is_shortlisted: bool
    overall_match_score: float
    skill_match_score: float
    semantic_score: float
    experience_score: float
    application_status: str
    key_strengths: list[str] = Field(default_factory=list)
    potential_concerns: list[str] = Field(default_factory=list)
    summary_reasoning: str
