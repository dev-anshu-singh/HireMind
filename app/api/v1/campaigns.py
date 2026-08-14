import uuid
from typing import Sequence, Optional
from fastapi import APIRouter, Depends, Query, status
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
from app.services.campaign_service import CampaignService
from app.services.jd_parser_service import JDParserService
from app.services.preference_service import PreferenceService
from app.services.job_post_service import JobPostService
from app.services.candidate_service import CandidateService
from app.services.evaluation_service import EvaluationService

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


@router.get("/", response_model=Sequence[CampaignRead])
async def list_campaigns(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    status_filter: Optional[CampaignStatus] = Query(None, alias="status", description="Filter by campaign status"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List hiring campaigns with optional pagination and status filter.
    """
    return await CampaignService.list_campaigns(db, skip=skip, limit=limit, status_filter=status_filter)


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed information about a specific campaign by ID.
    """
    return await CampaignService.get_campaign_by_id(db, campaign_id)


@router.patch("/{campaign_id}/status", response_model=CampaignRead)
async def update_campaign_status(
    campaign_id: uuid.UUID,
    payload: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Request a state transition for a campaign.
    Validates state machine transition rules before updating database.
    """
    return await CampaignService.update_status(db, campaign_id, payload.target_status)


# --- JD Parser Endpoints ---

@router.post("/{campaign_id}/analyze-jd", response_model=HiringProfileRead, status_code=status.HTTP_200_OK)
async def analyze_job_description(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Analyze campaign's raw Job Description using Google Gemini.
    Extracts structured technical skills, experience, responsibilities, and soft skills.
    Saves the profile to the database and advances status to `JD_ANALYZED`.
    """
    return await JDParserService.analyze_and_save_jd(db, campaign_id)


@router.get("/{campaign_id}/hiring-profile", response_model=HiringProfileRead, status_code=status.HTTP_200_OK)
async def get_hiring_profile(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve the analyzed structured Hiring Profile for a campaign.
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


# --- Candidate Evaluation Endpoints ---

@router.post("/{campaign_id}/evaluate-candidates", response_model=Sequence[CandidateEvaluationRead], status_code=status.HTTP_200_OK)
async def evaluate_campaign_candidates(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Triggers 3-pillar hybrid AI evaluation for all campaign applicants.
    Ranks candidates by overall score, auto-shortlists top N candidates,
    and advances campaign status to `SHORTLISTED`.
    """
    return await EvaluationService.evaluate_all_campaign_candidates(db, campaign_id)


@router.get("/{campaign_id}/evaluations", response_model=Sequence[LeaderboardItem], status_code=status.HTTP_200_OK)
async def get_candidate_leaderboard(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retrieve candidate evaluation leaderboard for recruiters, ranked by score descending.
    """
    return await EvaluationService.get_campaign_evaluations(db, campaign_id)
