"""
Candidate Evaluator Agent — Implements 3-pillar hybrid scoring:
1. Technical Depth: Deterministic Python skill mapping.
2. Soft Skills: Vector Embeddings Cosine Similarity using text-embedding-004.
3. Experience Fit: Rule-constrained Gemini 3.6 Flash agent.
"""

import math
from typing import Optional, Any
from app.core.llm import get_llm, get_embeddings
from app.schemas.evaluation import ExperienceEvaluationOutput
from app.agents.evaluator.prompts import experience_eval_prompt


def compute_technical_depth_score(
    candidate_skills: list[str],
    recruiter_skill_priorities: dict[str, str],
) -> tuple[float, dict[str, Any]]:
    """
    Deterministic Python mapping: Evaluates candidate skills against recruiter priorities.

    Weights:
        MUST_HAVE: 10.0 points
        PREFERRED: 5.0 points
        BONUS: 2.0 points

    Returns:
        tuple[float, dict]: (Score from 0.0 to 100.0, Breakdown dict)
    """
    if not recruiter_skill_priorities:
        return 100.0, {"matched_skills": candidate_skills, "missing_must_have": []}

    candidate_skills_lower = {s.lower().strip() for s in candidate_skills}

    MUST_HAVE_WEIGHT = 10.0
    PREFERRED_WEIGHT = 5.0
    BONUS_WEIGHT = 2.0

    total_possible = 0.0
    earned_points = 0.0

    matched_skills = []
    missing_must_have = []

    for skill, priority in recruiter_skill_priorities.items():
        p_upper = priority.upper()
        if p_upper == "MUST_HAVE":
            w = MUST_HAVE_WEIGHT
        elif p_upper == "PREFERRED":
            w = PREFERRED_WEIGHT
        else:
            w = BONUS_WEIGHT

        total_possible += w

        if skill.lower().strip() in candidate_skills_lower:
            earned_points += w
            matched_skills.append(skill)
        elif p_upper == "MUST_HAVE":
            missing_must_have.append(skill)

    score = (earned_points / total_possible * 100.0) if total_possible > 0 else 100.0
    
    breakdown = {
        "matched_skills": matched_skills,
        "missing_must_have": missing_must_have,
        "earned_points": earned_points,
        "total_possible": total_possible,
    }

    return round(score, 2), breakdown


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Computes mathematical cosine similarity between two float vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


async def compute_soft_skills_similarity(
    candidate_skills: list[str],
    job_soft_skills: list[str],
    candidate_summary: str = "",
) -> float:
    """
    Vector Embeddings Similarity Search:
    Embeds job soft skills and candidate text using text-embedding-004,
    then computes Cosine Similarity.

    Returns:
        float: Similarity Score from 0.0 to 100.0
    """
    if not job_soft_skills:
        return 80.0  # Default neutral score if job specified no soft skills

    # Combine texts
    job_text = "Soft skills required: " + ", ".join(job_soft_skills)
    candidate_text = "Candidate skills and bio: " + ", ".join(candidate_skills) + " " + candidate_summary

    try:
        embeddings_model = get_embeddings()
        vectors = await embeddings_model.aembed_documents([job_text, candidate_text])
        
        sim = cosine_similarity(vectors[0], vectors[1])
        # Map similarity from range [0.0, 1.0] to [0.0, 100.0]
        score = max(0.0, min(100.0, sim * 100.0))
        return round(score, 2)
    except Exception:
        # Fallback keyword overlap if API call fails
        candidate_set = {s.lower() for s in candidate_skills}
        matched = sum(1 for s in job_soft_skills if s.lower() in candidate_set)
        score = (matched / len(job_soft_skills) * 100.0) if job_soft_skills else 80.0
        return round(score, 2)


async def evaluate_experience_with_llm(
    job_title: str,
    required_min_exp: float,
    candidate_exp_years: float,
    candidate_experience: list[Any],
    candidate_projects: list[Any],
    model_name: Optional[str] = None,
) -> ExperienceEvaluationOutput:
    """
    Rule-Constrained Gemini 3.6 Flash Evaluator:
    Calculates Experience Fit Score following explicit duration, title match, and scope rubrics.
    """
    llm = get_llm(model_name=model_name, temperature=0.1)
    structured_llm = llm.with_structured_output(ExperienceEvaluationOutput)
    chain = experience_eval_prompt | structured_llm

    result = await chain.ainvoke({
        "job_title": job_title,
        "required_min_exp": required_min_exp,
        "candidate_exp_years": candidate_exp_years,
        "candidate_experience_json": str(candidate_experience),
        "candidate_projects_json": str(candidate_projects),
    })

    return result
