import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hiring_profile import HiringProfile
from app.models.enums import CampaignStatus
from app.services.campaign_service import CampaignService
from app.agents.jd_parser.agent import parse_job_description


class JDParserService:
    """Service handling JD parsing execution, database persistence, and state transitions."""

    @staticmethod
    async def analyze_and_save_jd(db: AsyncSession, campaign_id: uuid.UUID) -> HiringProfile:
        """
        Parses raw JD text using Gemini 2.5 Flash, saves HiringProfile to database,
        and transitions campaign status to JD_ANALYZED.
        """
        # 1. Fetch target campaign
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        # 2. Check existing profile (if already analyzed, overwrite or return)
        statement = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
        result = await db.execute(statement)
        existing_profile = result.scalars().first()

        # 3. Call Gemini agent to extract structured JSON from raw JD
        parsed_data = await parse_job_description(campaign.raw_job_description)

        # Convert list of ParsedSkill models into dictionaries for JSON column storage
        tech_skills_list = [skill.model_dump() for skill in parsed_data.technical_skills]

        now = datetime.utcnow()

        if existing_profile:
            # Update existing profile row
            existing_profile.technical_skills = tech_skills_list
            existing_profile.preferred_skills = parsed_data.preferred_skills
            existing_profile.min_experience_years = parsed_data.min_experience_years
            existing_profile.educational_requirements = parsed_data.educational_requirements
            existing_profile.key_responsibilities = parsed_data.key_responsibilities
            existing_profile.soft_skills = parsed_data.soft_skills
            existing_profile.role_expectations = parsed_data.role_expectations
            hiring_profile = existing_profile
        else:
            # Create new HiringProfile database row
            hiring_profile = HiringProfile(
                campaign_id=campaign_id,
                technical_skills=tech_skills_list,
                preferred_skills=parsed_data.preferred_skills,
                min_experience_years=parsed_data.min_experience_years,
                educational_requirements=parsed_data.educational_requirements,
                key_responsibilities=parsed_data.key_responsibilities,
                soft_skills=parsed_data.soft_skills,
                role_expectations=parsed_data.role_expectations,
                created_at=now,
            )
            db.add(hiring_profile)

        # 4. Transition campaign state machine status to JD_ANALYZED if currently in SETUP
        if campaign.status == CampaignStatus.SETUP:
            campaign.status = CampaignStatus.JD_ANALYZED
            campaign.updated_at = now
            db.add(campaign)

        await db.commit()
        await db.refresh(hiring_profile)
        return hiring_profile

    @staticmethod
    async def get_hiring_profile(db: AsyncSession, campaign_id: uuid.UUID) -> HiringProfile:
        """
        Fetches the parsed HiringProfile for a campaign. Raises 404 if missing.
        """
        statement = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
        result = await db.execute(statement)
        profile = result.scalars().first()

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hiring profile for campaign ID '{campaign_id}' has not been generated yet.",
            )
        return profile
