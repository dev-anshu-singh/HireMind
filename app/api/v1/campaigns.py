import uuid
from typing import Sequence, Optional, Any
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.models.enums import CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignStatusUpdate
from app.schemas.hiring_profile import HiringProfileRead
from app.schemas.preference import (
    RecruiterPreferenceCreate,
    RecruiterPreferenceRead,
    RecruiterPreferenceDefaults,
)
from app.schemas.job_post import JobPostRead
from app.schemas.candidate import CandidateRead
from app.schemas.evaluation import CandidateEvaluationRead, LeaderboardItem
from app.schemas.dashboard import (
    EnrichedLeaderboardItem,
    CampaignAnalytics,
    CandidateStatusUpdatePayload,
    CampaignExportResponse,
)
from app.schemas.monitoring import CampaignMonitoringLogRead, ActionDecisionPayload
from app.services.campaign_service import CampaignService
from app.services.jd_parser_service import JDParserService
from app.services.preference_service import PreferenceService
from app.services.job_post_service import JobPostService
from app.services.candidate_service import CandidateService
from app.services.evaluation_service import EvaluationService
from app.services.evidence_service import EvidenceService
from app.services.dashboard_service import DashboardService
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("/", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a new hiring campaign.
    Initial status will automatically be set to `SETUP`.
    """
    return await CampaignService.create_campaign(db, payload)


@router.get("/", response_model=Sequence[CampaignRead], status_code=status.HTTP_200_OK)
async def list_campaigns(
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve all hiring campaigns.
    """
    return await CampaignService.list_campaigns(db)


@router.get("/{campaign_id}", response_model=CampaignRead, status_code=status.HTTP_200_OK)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve a specific hiring campaign by ID.
    """
    return await CampaignService.get_campaign_by_id(db, campaign_id)


@router.patch("/{campaign_id}/status", response_model=CampaignRead, status_code=status.HTTP_200_OK)
async def update_campaign_status(
    campaign_id: uuid.UUID,
    payload: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update campaign status with state machine transition rules.
    """
    return await CampaignService.update_campaign_status(db, campaign_id, payload.status)


# --- Job Description Parsing Endpoints ---

@router.post("/{campaign_id}/analyze-jd", response_model=HiringProfileRead, status_code=status.HTTP_201_CREATED)
async def analyze_job_description(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Triggers AI parsing on raw job description.
    Extracts structured HiringProfile and advances campaign status to `JD_ANALYZED`.
    """
    return await JDParserService.analyze_and_save_jd(db, campaign_id)


@router.get("/{campaign_id}/hiring-profile", response_model=HiringProfileRead, status_code=status.HTTP_200_OK)
async def get_campaign_hiring_profile(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve parsed HiringProfile for a campaign.
    """
    return await JDParserService.get_hiring_profile(db, campaign_id)


# --- Recruiter Preference Endpoints ---

@router.get("/{campaign_id}/preference-defaults", response_model=RecruiterPreferenceDefaults, status_code=status.HTTP_200_OK)
async def get_preference_defaults(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generate intelligent default configuration options based on the parsed HiringProfile.
    """
    return await PreferenceService.get_preference_defaults(db, campaign_id)


@router.post("/{campaign_id}/preferences", response_model=RecruiterPreferenceRead, status_code=status.HTTP_201_CREATED)
async def save_recruiter_preferences(
    campaign_id: uuid.UUID,
    payload: RecruiterPreferenceCreate,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Save custom recruiter preferences into the database.
    Advances campaign status from `JD_ANALYZED` to `PREFERENCES_SET`.
    """
    return await PreferenceService.save_preferences(db, campaign_id, payload)


@router.get("/{campaign_id}/preferences", response_model=RecruiterPreferenceRead, status_code=status.HTTP_200_OK)
async def get_recruiter_preferences(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve configured recruiter preferences for a campaign.
    """
    return await PreferenceService.get_preferences(db, campaign_id)


# --- Job Post Generation Endpoints ---

@router.post("/{campaign_id}/generate-job-posts", response_model=JobPostRead, status_code=status.HTTP_201_CREATED)
async def generate_company_job_post(
    campaign_id: uuid.UUID,
    platform: str = Query("COMPANY_PORTAL", description="Target platform for job post generation"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generates AI job post Markdown for the Company Career Portal based on Hiring Profile and Preferences.
    Saves to the database and advances campaign status to `PUBLISHED`.
    """
    return await JobPostService.generate_and_save_job_post(db, campaign_id, platform=platform)


@router.get("/{campaign_id}/job-posts", response_model=Sequence[JobPostRead], status_code=status.HTTP_200_OK)
async def list_campaign_job_posts(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all generated job posts for a campaign.
    """
    return await JobPostService.get_job_posts_for_campaign(db, campaign_id)


# --- Candidate Management Endpoints ---

@router.get("/{campaign_id}/candidates", response_model=Sequence[CandidateRead], status_code=status.HTTP_200_OK)
async def list_campaign_candidates(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all candidate applications submitted for a campaign.
    """
    return await CandidateService.list_candidates_for_campaign(db, campaign_id)


# --- Candidate Evaluation & Evidence Verification Endpoints ---

@router.post("/{campaign_id}/evaluate-candidates", response_model=Sequence[CandidateEvaluationRead], status_code=status.HTTP_200_OK)
async def evaluate_campaign_candidates(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Triggers 4-pillar hybrid AI evaluation for all campaign applicants.
    Ranks candidates by overall score, auto-shortlists top N candidates,
    and advances campaign status to `SHORTLISTED`.
    """
    return await EvaluationService.evaluate_all_campaign_candidates(db, campaign_id)


@router.post("/{campaign_id}/verify-evidence", response_model=Sequence[dict[str, Any]], status_code=status.HTTP_200_OK)
async def verify_campaign_evidence(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Triggers multi-domain evidence verification for all submitted URLs (GitHub, Credly, Behance, Kaggle, LinkedIn).
    Updates portfolio_insights and refreshes candidate leaderboard badges.
    """
    return await EvidenceService.verify_all_campaign_evidence(db, campaign_id)


# --- Recruiter Dashboard & Export Endpoints ---

@router.get("/{campaign_id}/leaderboard", response_model=Sequence[EnrichedLeaderboardItem], status_code=status.HTTP_200_OK)
async def get_top_k_leaderboard(
    campaign_id: uuid.UUID,
    top_k: Optional[int] = Query(None, description="Limit to top K candidates", ge=1),
    is_shortlisted_only: bool = Query(False, description="Filter only shortlisted candidates"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieves dynamic, 1-indexed ranked candidate leaderboard with 4-pillar sub-scores,
    verified proof badges, and candidate links.
    """
    return await DashboardService.get_top_k_leaderboard(
        db, campaign_id, top_k=top_k, is_shortlisted_only=is_shortlisted_only
    )


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics, status_code=status.HTTP_200_OK)
async def get_campaign_analytics(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Computes campaign intelligence metrics: applicant volume, knockout attrition,
    score distribution histogram, top institutions, and skill frequencies.
    """
    return await DashboardService.get_campaign_analytics(db, campaign_id)


@router.get("/{campaign_id}/export/csv", status_code=status.HTTP_200_OK)
async def export_campaign_csv(
    campaign_id: uuid.UUID,
    top_k: Optional[int] = Query(None, description="Limit export to top K candidates", ge=1),
    is_shortlisted_only: bool = Query(False, description="Export only shortlisted candidates"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generates a downloadable CSV export of evaluated candidate rankings and scores.
    """
    csv_content = await DashboardService.export_campaign_csv(
        db, campaign_id, top_k=top_k, is_shortlisted_only=is_shortlisted_only
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_candidates.csv"}
    )


@router.get("/{campaign_id}/export/json", response_model=CampaignExportResponse, status_code=status.HTTP_200_OK)
async def export_campaign_json(
    campaign_id: uuid.UUID,
    top_k: Optional[int] = Query(None, description="Limit export to top K candidates", ge=1),
    is_shortlisted_only: bool = Query(False, description="Export only shortlisted candidates"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generates a comprehensive nested JSON document with complete candidate dossiers for ATS integrations.
    """
    return await DashboardService.export_campaign_json(
        db, campaign_id, top_k=top_k, is_shortlisted_only=is_shortlisted_only
    )


@router.patch("/{campaign_id}/candidates/{candidate_id}/status", response_model=CandidateRead, status_code=status.HTTP_200_OK)
async def update_candidate_stage_status(
    campaign_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: CandidateStatusUpdatePayload,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Allows hiring managers to manually override a candidate's status (e.g. INTERVIEW_SCHEDULED, HIRED, REJECTED).
    """
    return await DashboardService.update_candidate_status(
        db, campaign_id, candidate_id, new_status=payload.status, notes=payload.notes
    )


@router.post("/{campaign_id}/close", response_model=CampaignRead, status_code=status.HTTP_200_OK)
async def close_recruiter_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Finalizes the campaign and transitions status to `CLOSED`.
    """
    return await DashboardService.close_campaign(db, campaign_id)


# --- Milestone 7: Autonomous Campaign Monitoring & Re-Engagement Endpoints ---

@router.post("/{campaign_id}/monitor", response_model=CampaignMonitoringLogRead, status_code=status.HTTP_200_OK)
async def trigger_campaign_monitoring(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Triggers an autonomous AI health audit on the campaign.
    Diagnoses pacing bottlenecks, evaluates pipeline health, and logs proposed optimization actions.
    """
    return await MonitoringService.audit_campaign_health(db, campaign_id)


@router.get("/{campaign_id}/monitoring-logs", response_model=Sequence[CampaignMonitoringLogRead], status_code=status.HTTP_200_OK)
async def get_campaign_monitoring_logs(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieves chronological monitoring history and pending recommendation actions for a campaign.
    """
    return await MonitoringService.get_monitoring_history(db, campaign_id)


@router.post("/{campaign_id}/actions/{log_id}/approve", response_model=CampaignMonitoringLogRead, status_code=status.HTTP_200_OK)
async def approve_monitoring_action(
    campaign_id: uuid.UUID,
    log_id: uuid.UUID,
    payload: Optional[ActionDecisionPayload] = None,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Recruiter guardrail: Approves and executes a pending AI recommendation (e.g., job repost, requirement revision).
    """
    notes = payload.notes if payload else None
    return await MonitoringService.decide_proposed_action(
        db, campaign_id, log_id, approved=True, notes=notes
    )


@router.post("/{campaign_id}/actions/{log_id}/reject", response_model=CampaignMonitoringLogRead, status_code=status.HTTP_200_OK)
async def reject_monitoring_action(
    campaign_id: uuid.UUID,
    log_id: uuid.UUID,
    payload: Optional[ActionDecisionPayload] = None,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Recruiter guardrail: Declines a pending AI recommendation.
    """
    notes = payload.notes if payload else None
    return await MonitoringService.decide_proposed_action(
        db, campaign_id, log_id, approved=False, notes=notes
    )


@router.post("/monitor-all", response_model=Sequence[CampaignMonitoringLogRead], status_code=status.HTTP_200_OK)
async def batch_monitor_all_active_campaigns(
    db: AsyncSession = Depends(get_async_session),
):
    """
    Batch triggers health audit for all active campaigns across the system (Used by the 24-hour Night Cron).
    """
    return await MonitoringService.monitor_all_active_campaigns(db)
