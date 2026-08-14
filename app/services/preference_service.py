import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preference import RecruiterPreference
from app.models.enums import CampaignStatus
from app.schemas.preference import (
    RecruiterPreferenceCreate,
    RecruiterPreferenceDefaults,
)
from app.services.campaign_service import CampaignService
from app.services.jd_parser_service import JDParserService


class PreferenceService:
    """Service managing recruiter preference defaults, configuration saving, and state transitions."""

    @staticmethod
    async def get_preference_defaults(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> RecruiterPreferenceDefaults:
        """
        Analyzes the campaign's HiringProfile and generates intelligent default preferences
        for the recruiter to review and customize.
        """
        # 1. Fetch analyzed HiringProfile for the campaign
        hiring_profile = await JDParserService.get_hiring_profile(db, campaign_id)

        # 2. Build default skill priority map from extracted technical skills
        suggested_skill_priorities = {}
        if isinstance(hiring_profile.technical_skills, list):
            for skill_item in hiring_profile.technical_skills:
                if isinstance(skill_item, dict):
                    name = skill_item.get("name")
                    cat = skill_item.get("category", "PREFERRED").upper()
                    # Map LLM categories to Recruiter Priority levels
                    if cat == "CRITICAL":
                        suggested_skill_priorities[name] = "MUST_HAVE"
                    elif cat == "BONUS":
                        suggested_skill_priorities[name] = "BONUS"
                    else:
                        suggested_skill_priorities[name] = "PREFERRED"

        # 3. Standard default evaluation weights & evidence sources
        suggested_evaluation_weights = {
            "technical_depth": 0.50,
            "experience": 0.30,
            "soft_skills": 0.20,
        }

        suggested_evidence_sources = ["GITHUB_REPOS", "WORK_EXPERIENCE", "PROJECTS"]

        return RecruiterPreferenceDefaults(
            campaign_id=campaign_id,
            suggested_skill_priorities=suggested_skill_priorities,
            suggested_evaluation_weights=suggested_evaluation_weights,
            suggested_evidence_sources=suggested_evidence_sources,
            min_experience_years=hiring_profile.min_experience_years,
        )

    @staticmethod
    async def save_preferences(
        db: AsyncSession, campaign_id: uuid.UUID, payload: RecruiterPreferenceCreate
    ) -> RecruiterPreference:
        """
        Saves recruiter's custom preference choices into the database
        and transitions campaign status to PREFERENCES_SET.
        """
        # 1. Fetch target campaign
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        # 2. Verify campaign state (must have completed JD analysis)
        if campaign.status not in [CampaignStatus.JD_ANALYZED, CampaignStatus.PREFERENCES_SET]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot set preferences for campaign in '{campaign.status}' state. Must complete JD analysis first.",
            )

        # 3. Check for existing preference row
        statement = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
        result = await db.execute(statement)
        existing_pref = result.scalars().first()

        now = datetime.utcnow()

        if existing_pref:
            # Update existing preferences
            existing_pref.skill_priorities = payload.skill_priorities
            existing_pref.experience_weights = payload.experience_weights
            existing_pref.evaluation_weights = payload.evaluation_weights
            existing_pref.evidence_sources = payload.evidence_sources
            existing_pref.min_cgpa = payload.min_cgpa
            existing_pref.immediate_joiner_only = payload.immediate_joiner_only
            existing_pref.work_authorization = payload.work_authorization
            pref_record = existing_pref
        else:
            # Create new RecruiterPreference database row
            pref_record = RecruiterPreference(
                campaign_id=campaign_id,
                skill_priorities=payload.skill_priorities,
                experience_weights=payload.experience_weights,
                evaluation_weights=payload.evaluation_weights,
                evidence_sources=payload.evidence_sources,
                min_cgpa=payload.min_cgpa,
                immediate_joiner_only=payload.immediate_joiner_only,
                work_authorization=payload.work_authorization,
                created_at=now,
            )
            db.add(pref_record)

        # 4. Advance campaign status to PREFERENCES_SET if in JD_ANALYZED
        if campaign.status == CampaignStatus.JD_ANALYZED:
            campaign.status = CampaignStatus.PREFERENCES_SET
            campaign.updated_at = now
            db.add(campaign)

        await db.commit()
        await db.refresh(pref_record)
        return pref_record

    @staticmethod
    async def get_preferences(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> RecruiterPreference:
        """
        Retrieves stored recruiter preferences for a campaign. Raises 404 if not found.
        """
        statement = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
        result = await db.execute(statement)
        pref = result.scalars().first()

        if not pref:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recruiter preferences for campaign ID '{campaign_id}' have not been configured yet.",
            )
        return pref
