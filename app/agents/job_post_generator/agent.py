"""
Job Post Generator Agent — Formats structured hiring profile & preferences into Markdown.
"""

from typing import Optional, Any
from app.core.llm import get_job_post_llm
from app.schemas.job_post import GeneratedJobPost
from app.agents.job_post_generator.prompts import job_post_prompt


async def generate_job_post(
    campaign_info: dict[str, Any],
    hiring_profile: Any,
    recruiter_preference: Optional[Any] = None,
    model_name: Optional[str] = None,
) -> GeneratedJobPost:
    """
    Sends hiring profile & recruiter preferences to Gemini to generate a formatted Job Post.

    Args:
        campaign_info: Dict containing basic campaign info (job_title, company_name, location, employment_type).
        hiring_profile: HiringProfile DB model or dictionary.
        recruiter_preference: RecruiterPreference DB model or dictionary (optional).
        model_name: Optional LLM model override (defaults to settings.JOB_POST_GENERATOR_MODEL_NAME).

    Returns:
        GeneratedJobPost: Pydantic model with title, content_markdown, platform.
    """
    # 1. Obtain centralized LLM instance
    llm = get_job_post_llm(model_name=model_name, temperature=0.2)

    # 2. Force Gemini to return data matching GeneratedJobPost schema
    structured_llm = llm.with_structured_output(GeneratedJobPost)

    # 3. Build chain
    chain = job_post_prompt | structured_llm

    # 4. Safely extract preference values
    skill_priorities = getattr(recruiter_preference, "skill_priorities", {}) if recruiter_preference else {}
    min_cgpa = getattr(recruiter_preference, "min_cgpa", None) if recruiter_preference else "None"
    immediate_joiner = getattr(recruiter_preference, "immediate_joiner_only", False) if recruiter_preference else False
    work_auth = getattr(recruiter_preference, "work_authorization", "None") if recruiter_preference else "None"

    # 5. Invoke chain asynchronously
    result = await chain.ainvoke({
        "job_title": campaign_info.get("job_title", ""),
        "company_name": campaign_info.get("company_name", ""),
        "location": campaign_info.get("location", ""),
        "employment_type": str(campaign_info.get("employment_type", "")),
        "technical_skills": getattr(hiring_profile, "technical_skills", []),
        "preferred_skills": getattr(hiring_profile, "preferred_skills", []),
        "min_experience_years": getattr(hiring_profile, "min_experience_years", 0),
        "educational_requirements": getattr(hiring_profile, "educational_requirements", []),
        "key_responsibilities": getattr(hiring_profile, "key_responsibilities", []),
        "soft_skills": getattr(hiring_profile, "soft_skills", []),
        "role_expectations": getattr(hiring_profile, "role_expectations", ""),
        "skill_priorities": skill_priorities,
        "min_cgpa": min_cgpa,
        "immediate_joiner_only": immediate_joiner,
        "work_authorization": work_auth,
    })

    return result
