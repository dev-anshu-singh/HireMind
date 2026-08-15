import uuid
from datetime import datetime
from typing import Optional, Any, TypedDict
from pydantic import BaseModel, Field
from app.models.enums import ActionProposed, ActionStatus


class MonitoringMetricsSnapshot(BaseModel):
    """Snapshot of campaign funnel and pacing metrics used for AI diagnosis."""
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


class ActionPayload(BaseModel):
    """Detailed payload specifying proposed adjustments or actions."""
    proposed_action: ActionProposed = Field(description="Action proposed by the agent")
    target_platform: Optional[str] = Field(default=None, description="Platform for job repost/refresh")
    relaxed_skills: list[str] = Field(default_factory=list, description="Skills proposed to shift from MUST_HAVE to PREFERRED")
    suggested_min_cgpa: Optional[float] = Field(default=None, description="Suggested lower CGPA threshold if bottleneck")
    suggested_min_experience_years: Optional[float] = Field(default=None, description="Suggested lower experience requirement")
    deadline_extension_days: Optional[int] = Field(default=None, description="Suggested days to extend campaign deadline")
    pool_simulation_insight: Optional[str] = Field(default=None, description="Simulated pool impact of criteria relaxation")
    alert_message: Optional[str] = Field(default=None, description="Notification alert message for recruiter")
    custom_instructions: Optional[str] = Field(default=None, description="Specific copy or strategy adjustments")


class MonitorAgentOutput(BaseModel):
    """Structured AI output returned by Campaign Monitor Agent."""
    diagnostic_category: str = Field(
        description="Health state category (HEALTHY_PACING, CRITICAL_PACING_DEFICIT, HARSH_FILTER_BOTTLENECK, SKILL_MISMATCH_DEFICIT, TARGET_ACHIEVED_EARLY)"
    )
    pacing_health_status: str = Field(description="Summary tag of campaign health: ON_TRACK, AT_RISK, or COMPLETED_EARLY")
    proposed_action: ActionProposed = Field(
        description="Action to take: NONE, REPOST_JOB, REFRESH_JOB, REVISE_REQUIREMENTS, EXTEND_DEADLINE, EARLY_SHORTLIST_ALERT"
    )
    action_details: ActionPayload = Field(description="Specific parameters of the action")
    detailed_reasoning: str = Field(description="Detailed explanation of the diagnosis and recommendation")
    impact_forecast: str = Field(description="Forecast of how this action will improve the pipeline")
    guardrail_flags: dict[str, Any] = Field(default_factory=dict, description="Risk level and approval requirement flags")


class CampaignMonitoringLogRead(BaseModel):
    """Database schema for campaign monitoring logs and actions."""
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


class MonitoringGraphState(TypedDict, total=False):
    """LangGraph State representation for Campaign Monitoring Agent."""
    campaign_id: str
    campaign_info: dict[str, Any]
    metrics_snapshot: dict[str, Any]
    hiring_requirements: dict[str, Any]
    candidate_pool_stats: dict[str, Any]
    diagnosis: Optional[dict[str, Any]]
    selected_tool: str
    tool_output: dict[str, Any]
    requires_hitl: bool
    action_status: str
    final_reasoning: str
    created_log_id: Optional[str]
