import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GeneratedJobPost(BaseModel):
    """
    Structured output returned by the Job Post Generator AI Agent.
    """
    title: str = Field(
        description="Clear, professional job post headline (e.g. 'Senior Full-Stack Python & AI Engineer')"
    )
    content: str = Field(
        description="Complete, well-formatted Markdown job description tailored for a company career portal"
    )
    platform: str = Field(
        default="COMPANY_PORTAL",
        description="Target posting channel (e.g. COMPANY_PORTAL)"
    )


class JobPostRead(BaseModel):
    """
    Database schema representation for returning job posts to recruiters.
    """
    id: uuid.UUID
    campaign_id: uuid.UUID
    platform: str
    title: str
    content: str
    is_published: bool
    repost_count: int
    published_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicJobPostRead(BaseModel):
    """
    Clean public DTO for company career pages to fetch and render job descriptions.
    """
    campaign_id: uuid.UUID
    company_name: str
    job_title: str
    employment_type: str
    location: str
    salary_range: Optional[str]
    title: str
    content: str
    application_deadline: Optional[datetime]

    model_config = {"from_attributes": True}
