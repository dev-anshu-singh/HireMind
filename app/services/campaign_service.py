import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence, Optional
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.enums import CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignUpdate


# State Machine Transition Rules Map
# Defines the allowed NEXT states from any given CURRENT state.
VALID_TRANSITIONS: dict[CampaignStatus, list[CampaignStatus]] = {
    CampaignStatus.SETUP: [CampaignStatus.JD_ANALYZED, CampaignStatus.CLOSED],
    CampaignStatus.JD_ANALYZED: [CampaignStatus.PREFERENCES_SET, CampaignStatus.CLOSED],
    CampaignStatus.PREFERENCES_SET: [CampaignStatus.PUBLISHED, CampaignStatus.CLOSED],
    CampaignStatus.PUBLISHED: [CampaignStatus.MONITORING, CampaignStatus.EVALUATING, CampaignStatus.CLOSED],
    CampaignStatus.MONITORING: [CampaignStatus.EVALUATING, CampaignStatus.CLOSED],
    CampaignStatus.EVALUATING: [CampaignStatus.SHORTLISTED, CampaignStatus.CLOSED],
    CampaignStatus.SHORTLISTED: [CampaignStatus.CLOSED],
    CampaignStatus.CLOSED: [],  # Closed is terminal state
}


def validate_status_transition(current_status: CampaignStatus, target_status: CampaignStatus) -> None:
    """
    Validates if transitioning from current_status to target_status is allowed.
    Raises HTTP 400 Bad Request if the transition is invalid.
    """
    # A campaign can stay in its current status
    if current_status == target_status:
        return

    # Recruiter can manually close a campaign from any state except already CLOSED
    if target_status == CampaignStatus.CLOSED and current_status != CampaignStatus.CLOSED:
        return

    allowed_next_states = VALID_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_next_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from '{current_status.value}' to '{target_status.value}'. "
                f"Allowed next states: {[s.value for s in allowed_next_states]}"
            ),
        )


class CampaignService:
    """Service layer containing business logic for Hiring Campaigns."""

    @staticmethod
    async def create_campaign(db: AsyncSession, payload: CampaignCreate) -> Campaign:
        """
        Creates a new hiring campaign in SETUP status.
        Calculates application deadline based on duration_days.
        """
        now = datetime.utcnow()
        deadline = now + timedelta(days=payload.duration_days)

        # Convert Pydantic input schema into SQLModel database entity
        campaign = Campaign(
            company_name=payload.company_name,
            company_description=payload.company_description,
            job_title=payload.job_title,
            raw_job_description=payload.raw_job_description,
            employment_type=payload.employment_type,
            location=payload.location,
            salary_range=payload.salary_range,
            target_shortlist_size=payload.target_shortlist_size,
            min_target_applicants=payload.min_target_applicants,
            desired_applicants=payload.desired_applicants,
            duration_days=payload.duration_days,
            application_deadline=deadline,
            auto_close_on_deadline=payload.auto_close_on_deadline,
            auto_approve_reposts=payload.auto_approve_reposts,
            status=CampaignStatus.SETUP,  # Always starts in SETUP
            created_at=now,
            updated_at=now,
        )

        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def get_campaign_by_id(db: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
        """
        Fetches a campaign by UUID. Raises 404 Not Found if missing.
        """
        statement = select(Campaign).where(Campaign.id == campaign_id)
        result = await db.execute(statement)
        campaign = result.scalars().first()

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign with ID '{campaign_id}' not found.",
            )
        return campaign

    @staticmethod
    async def list_campaigns(
        db: AsyncSession, skip: int = 0, limit: int = 20, status_filter: Optional[CampaignStatus] = None
    ) -> Sequence[Campaign]:
        """
        Retrieves a list of campaigns with optional pagination and status filtering.
        """
        statement = select(Campaign)
        if status_filter:
            statement = statement.where(Campaign.status == status_filter)
        
        statement = statement.offset(skip).limit(limit).order_by(Campaign.created_at.desc())
        result = await db.execute(statement)
        return result.scalars().all()

    @staticmethod
    async def update_status(
        db: AsyncSession, campaign_id: uuid.UUID, target_status: CampaignStatus
    ) -> Campaign:
        """
        Validates state transition and updates campaign status.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        
        # Enforce state machine rules
        validate_status_transition(campaign.status, target_status)
        
        campaign.status = target_status
        campaign.updated_at = datetime.utcnow()
        
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign
