"""
Resume Parser Agent — Extracts structured candidate data from raw resume text using Gemini.
"""

from typing import Optional
from app.core.llm import get_resume_parser_llm
from app.schemas.candidate import ParsedResumeData
from app.agents.resume_parser.prompts import resume_parser_prompt


async def parse_resume(
    raw_resume_text: str,
    model_name: Optional[str] = None,
) -> ParsedResumeData:
    """
    Sends raw extracted resume text to Gemini to parse into structured JSON data.

    Args:
        raw_resume_text: Extracted plain text string from PDF/DOCX resume.
        model_name: Optional LLM model override (defaults to settings.RESUME_PARSER_MODEL_NAME).

    Returns:
        ParsedResumeData: Pydantic model containing skills, work experience, education, and links.
    """
    # 1. Obtain centralized LLM instance
    llm = get_resume_parser_llm(model_name=model_name, temperature=0.1)

    # 2. Force Gemini to return data matching ParsedResumeData schema
    structured_llm = llm.with_structured_output(ParsedResumeData)

    # 3. Build chain
    chain = resume_parser_prompt | structured_llm

    # 4. Invoke chain asynchronously
    result = await chain.ainvoke({"resume_text": raw_resume_text})
    return result
