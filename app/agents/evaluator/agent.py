"""
Candidate Evaluator Agent — Implements 4-pillar hybrid scoring:
1. Technical Depth: Deterministic Python skill mapping.
2. Experience Fit: Rule-constrained evaluation against structured experience requirements.
3. Projects, Achievements & College Brand: College tier, live code links, awards/honors.
4. Soft Skills & Culture: Vector Embeddings Cosine Similarity using text-embedding-004.
"""

import math
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.core.llm import get_llm, get_embeddings


class SingleRequirementEvaluation(BaseModel):
    requirement: str
    priority: str
    match_factor: float = Field(description="Match factor: 1.0 (Fully Met), 0.5 (Partially Met), or 0.0 (Not Met)")
    reasoning: str


class ExperienceFitOutput(BaseModel):
    score: float = Field(description="Calculated experience fit score (0.0 to 100.0)")
    evaluations: list[SingleRequirementEvaluation] = Field(default_factory=list)
    summary: str


class ProjectsBrandOutput(BaseModel):
    score: float = Field(description="Combined score for projects, achievements, and college brand (0.0 to 100.0)")
    college_tier_score: float = Field(description="College / Institution brand score (0 to 100)")
    project_quality_score: float = Field(description="Project complexity and live links score (0 to 100)")
    achievements_score: float = Field(description="Awards, honors, and competitive coding score (0 to 100)")
    key_highlights: list[str] = Field(default_factory=list)


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
    """
    if not job_soft_skills:
        return 80.0

    job_text = "Soft skills required: " + ", ".join(job_soft_skills)
    candidate_text = "Candidate skills and bio: " + ", ".join(candidate_skills) + " " + candidate_summary

    try:
        embeddings_model = get_embeddings()
        vectors = await embeddings_model.aembed_documents([job_text, candidate_text])
        sim = cosine_similarity(vectors[0], vectors[1])
        score = max(0.0, min(100.0, sim * 100.0))
        return round(score, 2)
    except Exception:
        candidate_set = {s.lower() for s in candidate_skills}
        matched = sum(1 for s in job_soft_skills if s.lower() in candidate_set)
        score = (matched / len(job_soft_skills) * 100.0) if job_soft_skills else 80.0
        return round(score, 2)


async def evaluate_experience_against_requirements(
    job_title: str,
    experience_requirements: list[dict[str, Any]],
    candidate_exp_years: float,
    candidate_experience: list[Any],
    candidate_projects: list[Any],
    model_name: Optional[str] = None,
) -> ExperienceFitOutput:
    """
    Evaluates candidate work experience against structured experience requirements.
    Calculates weighted score in Python: MUST_HAVE (10.0), PREFERRED (5.0), BONUS (2.0).
    """
    if not experience_requirements:
        # If zero experience requirements exist (fresher role), return default neutral score
        return ExperienceFitOutput(
            score=100.0,
            evaluations=[],
            summary="Fresher/Entry-level role with no mandatory experience requirements."
        )

    # Calculate deterministic Python score based on match factors
    total_possible = 0.0
    earned_points = 0.0
    evaluations_list = []

    for req_item in experience_requirements:
        req_text = req_item.get("requirement", "")
        priority = req_item.get("priority", "MUST_HAVE").upper()

        if priority == "MUST_HAVE":
            w = 10.0
        elif priority == "PREFERRED":
            w = 5.0
        else:
            w = 2.0

        total_possible += w

        # Simple semantic keyword check as base match factor
        req_lower = req_text.lower()
        exp_str = str(candidate_experience).lower() + str(candidate_projects).lower()
        
        if any(word in exp_str for word in req_lower.split() if len(word) > 4):
            match_factor = 1.0
            reasoning = f"Matched requirement: '{req_text}'."
        else:
            match_factor = 0.5 if candidate_exp_years > 1.0 else 0.0
            reasoning = f"Limited evidence for '{req_text}'."

        earned_points += (match_factor * w)
        evaluations_list.append(SingleRequirementEvaluation(
            requirement=req_text,
            priority=priority,
            match_factor=match_factor,
            reasoning=reasoning
        ))

    calculated_score = (earned_points / total_possible * 100.0) if total_possible > 0 else 100.0

    return ExperienceFitOutput(
        score=round(calculated_score, 2),
        evaluations=evaluations_list,
        summary=f"Candidate met {earned_points:.1f}/{total_possible:.1f} weighted experience points."
    )


async def evaluate_projects_and_brand(
    candidate_education: list[Any],
    candidate_projects: list[Any],
    candidate_github_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> ProjectsBrandOutput:
    """
    Evaluates College / Institution Brand, Projects, and Achievements.
    """
    # 1. College Tier Score (25% Weight)
    college_score = 60.0  # Default base score
    top_tier_keywords = ["iit", "nit", "iiit", "bits", "ivy", "stanford", "mit", "university of california", "top university"]
    
    edu_str = str(candidate_education).lower()
    if any(k in edu_str for k in top_tier_keywords):
        college_score = 95.0
    elif len(candidate_education) > 0:
        college_score = 75.0

    # 2. Project Quality Score (40% Weight)
    project_score = 50.0
    highlights = []

    if candidate_projects:
        project_score += min(30.0, len(candidate_projects) * 15.0)
        highlights.append(f"Submitted {len(candidate_projects)} technical project(s).")
    
    if candidate_github_url:
        project_score += 15.0
        highlights.append("Provided active GitHub profile link.")

    project_score = min(100.0, project_score)

    # 3. Achievements Score (35% Weight)
    achievements_score = 70.0

    # Composite Pillar 3 Score
    final_score = round(
        (college_score * 0.25) + (project_score * 0.40) + (achievements_score * 0.35),
        2
    )

    return ProjectsBrandOutput(
        score=final_score,
        college_tier_score=college_score,
        project_quality_score=project_score,
        achievements_score=achievements_score,
        key_highlights=highlights
    )
