import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.schemas.job_post import PublicJobPostRead
from app.schemas.candidate import CandidateApplyForm, CandidateRead
from app.services.job_post_service import JobPostService
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/public", tags=["Public Career API"])


@router.get("/campaigns/{campaign_id}/job-post", response_model=PublicJobPostRead, status_code=status.HTTP_200_OK)
async def get_public_career_page_job_post(
    campaign_id: uuid.UUID,
    platform: str = Query("COMPANY_PORTAL", description="Target platform channel"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Public API Endpoint: Allows company career pages or third-party web apps
    to fetch published Job Descriptions without requiring authentication.
    """
    return await JobPostService.get_public_job_post(db, campaign_id, platform=platform)


@router.post("/campaigns/{campaign_id}/apply", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
async def apply_to_campaign(
    campaign_id: uuid.UUID,
    full_name: str = Form(..., description="Candidate's full name"),
    email: str = Form(..., description="Candidate's email address"),
    phone: Optional[str] = Form(None, description="Candidate's phone number"),
    linkedin_url: Optional[str] = Form(None, description="LinkedIn profile URL"),
    github_url: Optional[str] = Form(None, description="GitHub profile URL"),
    portfolio_url: Optional[str] = Form(None, description="Portfolio URL"),
    cgpa: Optional[float] = Form(None, description="Candidate's CGPA"),
    is_immediate_joiner: bool = Form(False, description="Is candidate an immediate joiner"),
    notice_period_days: Optional[int] = Form(None, description="Notice period in days"),
    resume: UploadFile = File(..., description="Candidate's PDF resume file"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Public API Endpoint: Allows candidates to submit applications and upload PDF resumes.
    Parses resume using Gemini and evaluates hard knockout filters automatically.
    """
    if not resume.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF resume files (.pdf) are currently supported.",
        )

    file_bytes = await resume.read()

    form_data = CandidateApplyForm(
        full_name=full_name,
        email=email,
        phone=phone,
        linkedin_url=linkedin_url,
        github_url=github_url,
        portfolio_url=portfolio_url,
        cgpa=cgpa,
        is_immediate_joiner=is_immediate_joiner,
        notice_period_days=notice_period_days,
    )

    return await CandidateService.apply_candidate(
        db,
        campaign_id=campaign_id,
        form_data=form_data,
        file_bytes=file_bytes,
        filename=resume.filename,
    )
