import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class CandidateApplyForm(BaseModel):
    """
    Form schema for candidate application submission.
    """
    full_name: str = Field(description="Candidate's full name")
    email: str = Field(description="Candidate's primary email address")
    phone: Optional[str] = Field(default=None, description="Contact phone number")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile link")
    github_url: Optional[str] = Field(default=None, description="GitHub profile link")
    portfolio_url: Optional[str] = Field(default=None, description="Portfolio or personal site link")
    cgpa: Optional[float] = Field(default=None, description="Candidate's CGPA / Percentage")
    is_immediate_joiner: bool = Field(default=False, description="Whether candidate can join immediately")
    notice_period_days: Optional[int] = Field(default=None, description="Notice period duration in days")


class ParsedWorkExperience(BaseModel):
    job_title: str = Field(description="Title of position held")
    company_name: str = Field(description="Name of employer company")
    duration: Optional[str] = Field(default=None, description="Dates or duration of employment")
    description: Optional[str] = Field(default=None, description="Key responsibilities and achievements")


class ParsedEducation(BaseModel):
    degree: str = Field(description="Degree or qualification name (e.g. B.Tech in Computer Science)")
    institution: str = Field(description="University or college name")
    year_graduated: Optional[int] = Field(default=None, description="Graduation year")
    cgpa_or_percentage: Optional[str] = Field(default=None, description="CGPA or grade mentioned")


class ParsedProject(BaseModel):
    title: str = Field(description="Project name or headline")
    description: str = Field(description="Overview of technologies used and impact")
    link: Optional[str] = Field(default=None, description="Project repository or live demo URL")


class ParsedResumeData(BaseModel):
    """
    Structured output returned by the Resume Parser AI Agent.
    """
    candidate_name: Optional[str] = Field(default=None, description="Extracted candidate name")
    email: Optional[str] = Field(default=None, description="Extracted email address")
    phone: Optional[str] = Field(default=None, description="Extracted phone number")
    location: Optional[str] = Field(default=None, description="Current location or city")
    summary: Optional[str] = Field(default=None, description="Professional summary or bio")
    total_experience_years: float = Field(default=0.0, description="Estimated total years of work experience")
    skills: list[str] = Field(default_factory=list, description="Extracted technical and soft skills")
    work_experience: list[ParsedWorkExperience] = Field(default_factory=list)
    education: list[ParsedEducation] = Field(default_factory=list)
    projects: list[ParsedProject] = Field(default_factory=list)
    extracted_urls: list[str] = Field(default_factory=list, description="All GitHub, LinkedIn, or portfolio URLs found")


class CandidateProfileRead(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    parsed_skills: list[str] = Field(default_factory=list)
    parsed_work_experience: list[dict[str, Any]] = Field(default_factory=list)
    parsed_education: list[dict[str, Any]] = Field(default_factory=list)
    parsed_projects: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateRead(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    full_name: str
    email: str
    phone: Optional[str]
    raw_resume_url: str
    linkedin_url: Optional[str]
    github_url: Optional[str]
    portfolio_url: Optional[str]
    application_status: str
    applied_at: datetime

    model_config = {"from_attributes": True}
