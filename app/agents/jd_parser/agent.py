"""
JD Parser Agent — Extracts structured hiring profile from raw Job Description text.

Uses centralized get_llm(), separated prompts, and centralized schemas.
"""

from typing import Optional

from app.core.llm import get_jd_parser_llm
from app.schemas.hiring_profile import ParsedHiringProfile
from app.agents.jd_parser.prompts import jd_parser_prompt


async def parse_job_description(
    job_description: str, 
    model_name: Optional[str] = None
) -> ParsedHiringProfile:
    """
    Sends a raw Job Description to Gemini and returns a structured ParsedHiringProfile.

    Args:
        job_description: The raw text of the job posting.
        model_name: Optional model override (defaults to settings.JD_PARSER_MODEL_NAME).

    Returns:
        ParsedHiringProfile: Structured extraction of skills, experience, responsibilities, etc.
    """
    # 1. Obtain centralized Gemini LLM instance
    llm = get_jd_parser_llm(model_name=model_name, temperature=0.1)

    # 2. Force Gemini to return data matching centralized ParsedHiringProfile schema
    structured_llm = llm.with_structured_output(ParsedHiringProfile)

    # 3. Chain: Prompt Template -> Structured LLM
    chain = jd_parser_prompt | structured_llm

    # 4. Execute chain asynchronously
    result = await chain.ainvoke({"job_description": job_description})
    return result
