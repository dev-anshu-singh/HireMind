import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models.enums import ActionProposed, ActionStatus


class MonitoringMetricsSnapshot(BaseModel):
    """Simple snapshot of campaign pacing and candidate metrics."""
    elapsed_days: int = Field(description="Days elapsed since campaign published")
    duration_days: int = Field(description="Total campaign duration in days")
    days_remaining: int = Field(description="Days remaining until deadline")
    elapsed_ratio: float = Field(description="Ratio of elapsed time (0.0 to 1.0)")
    
    total_applicants: int = Field(description="Total candidates applied so far")
    knockout_rejected_count: int = Field(description="Count of applicants rejected by knockouts")
    knockout_rate: float = Field(description="Ratio of applicants knocked out")
    
    evaluated_count: int = Field(description="Count of evaluated candidates")
    shortlisted_count: int = Field(description="Current count of shortlisted candidates")
    target_shortlist_size: int = Field(description="Target shortlist size")
    shortlist_achievement_ratio: float = Field(description="Ratio of target shortlist reached")
    
    average_match_score: float = Field(description="Average score of evaluated applicants")
    highest_match_score: float = Field(description="Highest score in applicant pool")


class MonitorDecision(BaseModel):
    """Structured decision output from the Campaign Monitor Agent."""
    action: ActionProposed = Field(
        description="Action to take: NONE, REPOST_JOB, REVISE_REQUIREMENTS, EXTEND_DEADLINE, EARLY_SHORTLIST_ALERT"
    )
    reasoning: str = Field(description="Clear explanation of the diagnosis and recommendation")
    impact_forecast: str = Field(description="Forecast of how this action will improve the pipeline")
    
    # Specific tool parameters (optional based on action)
    target_platform: Optional[str] = Field(default=None, description="Platform for job repost (e.g. LINKEDIN, INDEED)")
    relaxed_skills: list[str] = Field(default_factory=list, description="Skills proposed to shift to PREFERRED")
    suggested_min_cgpa: Optional[float] = Field(default=None, description="Suggested lower CGPA threshold")
    suggested_min_experience_years: Optional[float] = Field(default=None, description="Suggested lower experience requirement")
    deadline_extension_days: Optional[int] = Field(default=None, description="Suggested days to extend campaign")
    alert_message: Optional[str] = Field(default=None, description="Recruiter alert message")


class CampaignMonitoringLogRead(BaseModel):
    """Database read schema for campaign monitoring logs."""
    id: uuid.UUID
    campaign_id: uuid.UUID
    total_applications_count: int
    expected_applications_count: int
    days_remaining: int
    agent_reasoning: str
    action_proposed: ActionProposed
    status: ActionStatus
    guardrail_flags: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionDecisionPayload(BaseModel):
    """Recruiter approval or rejection payload for proposed monitoring actions."""
    notes: Optional[str] = Field(default=None, description="Recruiter feedback or decision notes")
