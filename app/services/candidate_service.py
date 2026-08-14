import os
import uuid
from datetime import datetime
from typing import Sequence, Optional
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.enums import CampaignStatus, ApplicationStatus
from app.schemas.candidate import CandidateApplyForm
from app.services.campaign_service import CampaignService
from app.services.preference_service import PreferenceService
from app.utils.pdf_parser import extract_text_from_pdf
from app.agents.resume_parser.agent import parse_resume

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "resumes")


class CandidateService:
    """Service handling candidate applications, resume file storage, AI parsing, and knockout rules."""

    @staticmethod
    async def apply_candidate(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        form_data: CandidateApplyForm,
        file_bytes: bytes,
        filename: str = "resume.pdf",
    ) -> Candidate:
        """
        Processes a candidate application:
        1. Validates campaign status (must be PUBLISHED).
        2. Saves resume PDF file to disk.
        3. Extracts plain text & calls Resume Parser AI Agent.
        4. Evaluates RecruiterPreference knockout rules (min_cgpa, immediate_joiner).
        5. Saves Candidate and CandidateProfile records to PostgreSQL.
        """
        # 1. Fetch & validate campaign
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        if campaign.status != CampaignStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Campaign '{campaign.job_title}' is not currently accepting applications (Status: {campaign.status}).",
            )

        # 2. Generate Candidate UUID
        candidate_id = uuid.uuid4()
        now = datetime.utcnow()

        # 3. Save resume PDF to disk storage
        campaign_upload_dir = os.path.join(UPLOAD_DIR, str(campaign_id))
        os.makedirs(campaign_upload_dir, exist_ok=True)
        
        file_ext = os.path.splitext(filename)[1] or ".pdf"
        file_path = os.path.join(campaign_upload_dir, f"{candidate_id}{file_ext}")

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # 4. Extract raw text from PDF
        try:
            raw_text = extract_text_from_pdf(file_bytes)
        except Exception as e:
            raw_text = f"Failed to extract text from PDF: {str(e)}"

        # 5. Call Resume Parser AI Agent
        parsed_resume = await parse_resume(raw_text)

        # 6. Check Recruiter Preference Knockout Filters
        app_status = ApplicationStatus.PARSED

        try:
            recruiter_pref = await PreferenceService.get_preferences(db, campaign_id)
            
            # CGPA Knockout check
            if recruiter_pref.min_cgpa is not None and form_data.cgpa is not None:
                if form_data.cgpa < recruiter_pref.min_cgpa:
                    app_status = ApplicationStatus.REJECTED

            # Immediate Joiner Knockout check
            if recruiter_pref.immediate_joiner_only and not form_data.is_immediate_joiner:
                app_status = ApplicationStatus.REJECTED

        except HTTPException:
            # Preferences not set; accept application normally
            pass

        # 7. Create Candidate DB Record
        candidate_record = Candidate(
            id=candidate_id,
            campaign_id=campaign_id,
            full_name=form_data.full_name,
            email=form_data.email,
            phone=form_data.phone,
            raw_resume_url=file_path,
            linkedin_url=form_data.linkedin_url,
            github_url=form_data.github_url,
            portfolio_url=form_data.portfolio_url,
            application_status=app_status,
            applied_at=now,
        )
        db.add(candidate_record)

        # 8. Convert Pydantic objects to dicts for JSON columns
        experience_dicts = [exp.model_dump() for exp in parsed_resume.work_experience]
        education_dicts = [edu.model_dump() for edu in parsed_resume.education]
        project_dicts = [proj.model_dump() for proj in parsed_resume.projects]

        # 9. Create CandidateProfile DB Record
        profile_record = CandidateProfile(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            parsed_skills=parsed_resume.skills,
            parsed_work_experience=experience_dicts,
            parsed_education=education_dicts,
            parsed_projects=project_dicts,
            created_at=now,
        )
        db.add(profile_record)

        await db.commit()
        await db.refresh(candidate_record)
        return candidate_record

    @staticmethod
    async def list_candidates_for_campaign(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> Sequence[Candidate]:
        """
        Retrieves all candidate applications for a campaign.
        """
        statement = select(Candidate).where(Candidate.campaign_id == campaign_id)
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_candidate_by_id(
        db: AsyncSession, candidate_id: uuid.UUID
    ) -> Candidate:
        """
        Retrieves a single candidate application. Raises 404 if not found.
        """
        statement = select(Candidate).where(Candidate.id == candidate_id)
        result = await db.execute(statement)
        candidate = result.scalars().first()
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate with ID '{candidate_id}' not found.",
            )
        return candidate
