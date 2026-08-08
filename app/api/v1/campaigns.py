import uuid
from typing import Sequence, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.models.enums import CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignStatusUpdate
from app.services.campaign_service import CampaignService

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
