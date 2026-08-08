import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import EmploymentType, CampaignStatus


class CampaignCreate(BaseModel):
    """Schema for creating a new hiring campaign."""
    company_name: str = Field(..., description="Name of the company hiring")
    company_description: Optional[str] = Field(None, description="Optional brief info about company")
    job_title: str = Field(..., description="Job title for the role")
    raw_job_description: str = Field(..., description="Full text of the Job Description")
    
    employment_type: EmploymentType = Field(
        default=EmploymentType.FULL_TIME, 
        description="Type of employment (FULL_TIME, PART_TIME, etc.)"
    )
    location: str = Field(..., description="Job location (e.g., Remote, New York, NY)")
    salary_range: Optional[str] = Field(None, description="Optional salary range text")
    
    target_shortlist_size: int = Field(default=5, ge=1, description="Number of candidates to shortlist (N)")
    min_target_applicants: int = Field(default=20, ge=1, description="Minimum expected applications count")
    desired_applicants: Optional[int] = Field(None, description="Optional target total applicant count")
    duration_days: int = Field(default=30, ge=1, description="Campaign duration in days")
    
    auto_close_on_deadline: bool = Field(default=True, description="Auto-close intake on deadline")
    auto_approve_reposts: bool = Field(default=False, description="Allow agent to auto-repost without HITL approval")


class CampaignUpdate(BaseModel):
    """Schema for updating campaign details."""
    company_name: Optional[str] = None
    company_description: Optional[str] = None
    job_title: Optional[str] = None
    raw_job_description: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    target_shortlist_size: Optional[int] = None
    min_target_applicants: Optional[int] = None
    duration_days: Optional[int] = None
    auto_approve_reposts: Optional[bool] = None


class CampaignStatusUpdate(BaseModel):
    """Schema for requesting a state machine transition."""
    target_status: CampaignStatus = Field(..., description="New campaign state requested")


class CampaignRead(BaseModel):
    """Schema for returning campaign details to the recruiter API."""
    id: uuid.UUID
    company_name: str
    company_description: Optional[str]
    job_title: str
    raw_job_description: str
    employment_type: EmploymentType
    location: str
    salary_range: Optional[str]
    
    status: CampaignStatus
    
    target_shortlist_size: int
    min_target_applicants: int
    desired_applicants: Optional[int]
    duration_days: int
    application_deadline: Optional[datetime]
    
    auto_close_on_deadline: bool
    auto_approve_reposts: bool
    
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
