import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models.enums import ApplicationStatus, CampaignStatus


class EnrichedLeaderboardItem(BaseModel):
    """
    Enriched candidate ranking entry for recruiter leaderboard.
    Includes 4-pillar sub-scores, verified proof badges, and candidate links.
    """
    candidate_id: uuid.UUID
    rank: Optional[int]
    full_name: str
    email: str
    phone: Optional[str] = None
    application_status: str
    is_shortlisted: bool
    
    # 4-Pillar Composite & Sub-Scores
    overall_match_score: float
    skill_match_score: float
    experience_score: float
    portfolio_score: float
    semantic_score: float
    
    # Proof-of-Work & Evidence
    evidence_score: Optional[float] = None
    verified_badges: list[str] = Field(default_factory=list)
    broken_links: list[str] = Field(default_factory=list)
    
    # Links & Reasoning
    raw_resume_url: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    key_strengths: list[str] = Field(default_factory=list)
    potential_concerns: list[str] = Field(default_factory=list)
    summary_reasoning: str


class ScoreDistribution(BaseModel):
    """Score histogram buckets across the applicant pool."""
    tier_90_100: int = Field(default=0, description="Score 90.0 - 100.0")
    tier_80_89: int = Field(default=0, description="Score 80.0 - 89.9")
    tier_70_79: int = Field(default=0, description="Score 70.0 - 79.9")
    tier_60_69: int = Field(default=0, description="Score 60.0 - 69.9")
    tier_below_60: int = Field(default=0, description="Score < 60.0")


class CampaignAnalytics(BaseModel):
    """Campaign intelligence metrics and applicant pool insights."""
    campaign_id: uuid.UUID
    campaign_title: str
    company_name: str
    status: str
    target_shortlist_size: int
    
    # Funnel Metrics
    total_applicants: int
    knockout_rejected_count: int
    evaluated_count: int
    shortlisted_count: int
    pass_through_rate_pct: float
    
    # Score Statistics
    average_match_score: float
    median_match_score: float
    highest_match_score: float
    lowest_match_score: float
    score_distribution: ScoreDistribution
    
    # Insights Breakdown
    top_skills_represented: dict[str, int] = Field(default_factory=dict)
    top_institutions_represented: dict[str, int] = Field(default_factory=dict)
    evidence_verification_stats: dict[str, int] = Field(default_factory=dict)


class CandidateStatusUpdatePayload(BaseModel):
    """Payload for recruiter manual candidate status override."""
    status: ApplicationStatus = Field(description="New candidate application status")
    notes: Optional[str] = Field(default=None, description="Optional recruiter decision notes")


class CandidateExportDossier(BaseModel):
    """Full nested candidate profile for structured ATS/JSON export."""
    candidate_id: uuid.UUID
    rank: Optional[int]
    full_name: str
    email: str
    phone: Optional[str] = None
    application_status: str
    is_shortlisted: bool
    applied_at: datetime
    
    # Scores
    scores: dict[str, float]
    
    # Parsed Resume Data
    parsed_skills: list[str] = Field(default_factory=list)
    parsed_education: list[dict[str, Any]] = Field(default_factory=list)
    parsed_work_experience: list[dict[str, Any]] = Field(default_factory=list)
    parsed_projects: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    
    # Evidence & Verification
    evidence_score: Optional[float] = None
    verified_sources: list[dict[str, Any]] = Field(default_factory=list)
    verified_badges: list[str] = Field(default_factory=list)
    
    # Links & AI Reasoning
    raw_resume_url: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    key_strengths: list[str] = Field(default_factory=list)
    potential_concerns: list[str] = Field(default_factory=list)
    summary_reasoning: str


class CampaignExportResponse(BaseModel):
    """Hierarchical JSON export for ATS and external dashboard ingestion."""
    campaign_id: uuid.UUID
    company_name: str
    job_title: str
    status: str
    target_shortlist_size: int
    exported_at: datetime
    total_candidates_exported: int
    hiring_profile: Optional[dict[str, Any]] = None
    recruiter_preferences: Optional[dict[str, Any]] = None
    candidates: list[CandidateExportDossier] = Field(default_factory=list)
