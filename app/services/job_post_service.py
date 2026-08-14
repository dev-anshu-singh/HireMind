import uuid
from datetime import datetime
from typing import Sequence, Optional
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_post import JobPost
from app.models.enums import CampaignStatus
from app.schemas.job_post import PublicJobPostRead
from app.services.campaign_service import CampaignService
from app.services.jd_parser_service import JDParserService
from app.services.preference_service import PreferenceService
from app.agents.job_post_generator.agent import generate_job_post


class JobPostService:
    """Service handling job post generation, database persistence, and career page exposure."""

    @staticmethod
    async def generate_and_save_job_post(
        db: AsyncSession, 
        campaign_id: uuid.UUID, 
        platform: str = "COMPANY_PORTAL"
    ) -> JobPost:
        """
        Generates AI job post content for company portal, saves to job_posts table,
        and transitions campaign status to PUBLISHED.
        """
        # 1. Fetch Campaign, HiringProfile, and Preferences from DB
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        hiring_profile = await JDParserService.get_hiring_profile(db, campaign_id)
        
        # Recruiter preference is optional
        try:
            recruiter_pref = await PreferenceService.get_preferences(db, campaign_id)
        except HTTPException:
            recruiter_pref = None

        # 2. Package campaign details
        campaign_info = {
            "job_title": campaign.job_title,
            "company_name": campaign.company_name,
            "location": campaign.location,
            "employment_type": campaign.employment_type.value if hasattr(campaign.employment_type, "value") else str(campaign.employment_type),
        }

        # 3. Call AI agent to generate formatted Markdown job post
        generated_data = await generate_job_post(
            campaign_info=campaign_info,
            hiring_profile=hiring_profile,
            recruiter_preference=recruiter_pref,
        )

        # 4. Check for existing job post for this campaign and platform
        statement = select(JobPost).where(
            JobPost.campaign_id == campaign_id,
            JobPost.platform == platform
        )
        result = await db.execute(statement)
        existing_post = result.scalars().first()

        now = datetime.utcnow()

        if existing_post:
            # Update existing record
            existing_post.title = generated_data.title
            existing_post.content = generated_data.content
            existing_post.is_published = True
            existing_post.published_at = now
            job_post_record = existing_post
        else:
            # Create new record
            job_post_record = JobPost(
                campaign_id=campaign_id,
                platform=platform,
                title=generated_data.title,
                content=generated_data.content,
                is_published=True,
                published_at=now,
                created_at=now,
            )
            db.add(job_post_record)

        # 5. Advance campaign state machine to PUBLISHED
        if campaign.status in [CampaignStatus.PREFERENCES_SET, CampaignStatus.JD_ANALYZED]:
            campaign.status = CampaignStatus.PUBLISHED
            campaign.updated_at = now
            db.add(campaign)

        await db.commit()
        await db.refresh(job_post_record)
        return job_post_record

    @staticmethod
    async def get_job_posts_for_campaign(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> Sequence[JobPost]:
        """
        Retrieves all created job posts for a campaign.
        """
        statement = select(JobPost).where(JobPost.campaign_id == campaign_id)
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def get_public_job_post(
        db: AsyncSession, campaign_id: uuid.UUID, platform: str = "COMPANY_PORTAL"
    ) -> PublicJobPostRead:
        """
        Public endpoint fetcher allowing company career pages to retrieve published job descriptions.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        
        statement = select(JobPost).where(
            JobPost.campaign_id == campaign_id,
            JobPost.platform == platform,
            JobPost.is_published == True
        )
        result = await db.execute(statement)
        job_post = result.scalars().first()

        if not job_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No published job post found for campaign ID '{campaign_id}' on platform '{platform}'.",
            )

        emp_type_str = campaign.employment_type.value if hasattr(campaign.employment_type, "value") else str(campaign.employment_type)

        return PublicJobPostRead(
            campaign_id=campaign.id,
            company_name=campaign.company_name,
            job_title=campaign.job_title,
            employment_type=emp_type_str,
            location=campaign.location,
            salary_range=campaign.salary_range,
            title=job_post.title,
            content=job_post.content,
            application_deadline=campaign.application_deadline,
        )
