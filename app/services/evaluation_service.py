import uuid
from datetime import datetime
from typing import Sequence, Optional, Any
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.evaluation import CandidateEvaluation
from app.models.enums import CampaignStatus, ApplicationStatus, ScreeningStrategy
from app.schemas.evaluation import LeaderboardItem, CandidateEvaluationRead
from app.services.campaign_service import CampaignService
from app.services.jd_parser_service import JDParserService
from app.services.preference_service import PreferenceService
from app.services.candidate_service import CandidateService
from app.agents.evaluator.agent import (
    compute_technical_depth_score,
    compute_soft_skills_similarity,
    evaluate_experience_against_requirements,
    evaluate_projects_and_brand,
)


class EvaluationService:
    """Service handling 4-pillar candidate evaluation, vector embeddings, fresher weight redistribution, and auto-shortlisting."""

    @staticmethod
    async def evaluate_candidate(
        db: AsyncSession, candidate_id: uuid.UUID
    ) -> CandidateEvaluation:
        """
        Evaluates a single candidate across the 4 pillars:
        1. Tech Depth: Deterministic Python skill mapping.
        2. Experience Fit: Scored against structured experience requirements.
        3. Projects & College Brand: College tier, live code links, awards.
        4. Soft Skills: Vector Embeddings Cosine Similarity.
        """
        # 1. Fetch Candidate & CandidateProfile
        candidate = await CandidateService.get_candidate_by_id(db, candidate_id)
        
        statement = select(CandidateProfile).where(CandidateProfile.candidate_id == candidate_id)
        result = await db.execute(statement)
        profile = result.scalars().first()

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parsed profile for candidate ID '{candidate_id}' not found.",
            )

        # 2. Fetch Campaign, HiringProfile & Recruiter Preferences
        campaign = await CampaignService.get_campaign_by_id(db, candidate.campaign_id)
        hiring_profile = await JDParserService.get_hiring_profile(db, candidate.campaign_id)

        try:
            recruiter_pref = await PreferenceService.get_preferences(db, candidate.campaign_id)
            skill_priorities = recruiter_pref.skill_priorities
        except HTTPException:
            skill_priorities = {}

        candidate_skills = profile.parsed_skills or []
        is_fresher_role = (hiring_profile.min_experience_years == 0)

        # 3. Dynamic Weight Assignment (Fresher vs Experienced Role)
        if is_fresher_role:
            w_tech = 0.40
            w_exp = 0.00
            w_portfolio = 0.45
            w_soft = 0.15
        else:
            w_tech = 0.40
            w_exp = 0.35
            w_portfolio = 0.15
            w_soft = 0.10

        # 4. Pillar 1: Technical Depth Score (Deterministic Python Mapping)
        tech_score, tech_breakdown = compute_technical_depth_score(
            candidate_skills=candidate_skills,
            recruiter_skill_priorities=skill_priorities,
        )

        # 5. Pillar 2: Experience Fit Score (Evaluated against structured experience_requirements)
        exp_eval_output = await evaluate_experience_against_requirements(
            job_title=campaign.job_title,
            experience_requirements=getattr(hiring_profile, "experience_requirements", []) or [],
            candidate_exp_years=float(len(profile.parsed_work_experience or []) * 1.5),
            candidate_experience=profile.parsed_work_experience or [],
            candidate_projects=profile.parsed_projects or [],
        )
        exp_score = exp_eval_output.score

        # 6. Pillar 3: Projects, Achievements & College Brand Score
        projects_brand_output = await evaluate_projects_and_brand(
            candidate_education=profile.parsed_education or [],
            candidate_projects=profile.parsed_projects or [],
            candidate_github_url=candidate.github_url,
        )
        portfolio_score = projects_brand_output.score

        # 7. Pillar 4: Soft Skills Score (Vector Embedding Cosine Similarity)
        soft_skills_score = await compute_soft_skills_similarity(
            candidate_skills=candidate_skills,
            job_soft_skills=hiring_profile.soft_skills or [],
        )

        # 8. Weighted Composite Score Calculation
        overall_score = round(
            (tech_score * w_tech) + (exp_score * w_exp) + (portfolio_score * w_portfolio) + (soft_skills_score * w_soft),
            2
        )

        # 9. Generate Match Reasons & Risk Factors
        match_reasons = []
        risk_factors = []

        if tech_breakdown["matched_skills"]:
            match_reasons.append(f"Matched core skills: {', '.join(tech_breakdown['matched_skills'][:4])}.")
        if projects_brand_output.key_highlights:
            match_reasons.extend(projects_brand_output.key_highlights)
        if exp_score >= 70.0 and not is_fresher_role:
            match_reasons.append(f"Strong experience alignment for '{campaign.job_title}'.")
        if soft_skills_score >= 75.0:
            match_reasons.append("High semantic alignment with target soft skills and culture.")

        if tech_breakdown["missing_must_have"]:
            risk_factors.append(f"Missing required MUST_HAVE skills: {', '.join(tech_breakdown['missing_must_have'])}.")
        if exp_score < 60.0 and not is_fresher_role:
            risk_factors.append(exp_eval_output.summary)

        now = datetime.utcnow()

        # 10. Create or Update CandidateEvaluation DB Record
        stmt = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == candidate_id)
        res = await db.execute(stmt)
        existing_eval = res.scalars().first()

        summary_reasoning = f"Overall score {overall_score}/100. {exp_eval_output.summary}"

        if existing_eval:
            existing_eval.overall_match_score = overall_score
            existing_eval.skill_match_score = tech_score
            existing_eval.experience_score = exp_score
            existing_eval.portfolio_score = portfolio_score
            existing_eval.semantic_score = soft_skills_score
            existing_eval.key_strengths = match_reasons
            existing_eval.potential_concerns = risk_factors
            existing_eval.summary_reasoning = summary_reasoning
            existing_eval.evaluated_at = now
            eval_record = existing_eval
        else:
            eval_record = CandidateEvaluation(
                id=uuid.uuid4(),
                candidate_id=candidate_id,
                campaign_id=candidate.campaign_id,
                screening_strategy=ScreeningStrategy.HYBRID,
                overall_match_score=overall_score,
                skill_match_score=tech_score,
                experience_score=exp_score,
                portfolio_score=portfolio_score,
                semantic_score=soft_skills_score,
                is_shortlisted=False,
                key_strengths=match_reasons,
                potential_concerns=risk_factors,
                summary_reasoning=summary_reasoning,
                evaluated_at=now,
            )
            db.add(eval_record)

        # 11. Update Candidate status from PARSED to EVALUATED (unless REJECTED by knockout)
        if candidate.application_status == ApplicationStatus.PARSED:
            candidate.application_status = ApplicationStatus.EVALUATED
            db.add(candidate)

        await db.commit()
        await db.refresh(eval_record)
        return eval_record

    @staticmethod
    async def evaluate_all_campaign_candidates(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> Sequence[CandidateEvaluation]:
        """
        Batch Evaluates all applicants for a campaign:
        1. Evaluates all un-evaluated candidates.
        2. Ranks candidates by overall_match_score.
        3. Auto-shortlists top N candidates (matching target_shortlist_size).
        4. Advances campaign status to SHORTLISTED.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        # 1. Fetch candidates for campaign
        candidates = await CandidateService.list_candidates_for_campaign(db, campaign_id)

        evaluations = []
        for candidate in candidates:
            # Skip candidates rejected by knockout filter
            if candidate.application_status == ApplicationStatus.REJECTED:
                continue

            eval_rec = await EvaluationService.evaluate_candidate(db, candidate.id)
            evaluations.append((candidate, eval_rec))

        # 2. Rank candidates by overall_match_score descending
        evaluations.sort(key=lambda item: item[1].overall_match_score, reverse=True)

        # 3. Auto-shortlist top N candidates & update rank
        shortlist_limit = campaign.target_shortlist_size or 5

        for idx, (cand, eval_rec) in enumerate(evaluations, 1):
            eval_rec.rank = idx
            if idx <= shortlist_limit:
                eval_rec.is_shortlisted = True
                cand.application_status = ApplicationStatus.SHORTLISTED
                db.add(cand)
            else:
                eval_rec.is_shortlisted = False

            db.add(eval_rec)

        # 4. Advance campaign status to SHORTLISTED
        if campaign.status in [CampaignStatus.PUBLISHED, CampaignStatus.EVALUATING]:
            campaign.status = CampaignStatus.SHORTLISTED
            campaign.updated_at = datetime.utcnow()
            db.add(campaign)

        await db.commit()
        return [eval_rec for _, eval_rec in evaluations]

    @staticmethod
    async def get_campaign_evaluations(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> Sequence[LeaderboardItem]:
        """
        Retrieves candidate evaluation leaderboard for recruiters, ordered by score descending.
        """
        candidates = await CandidateService.list_candidates_for_campaign(db, campaign_id)
        leaderboard = []

        for candidate in candidates:
            stmt = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == candidate.id)
            res = await db.execute(stmt)
            eval_rec = res.scalars().first()

            if eval_rec:
                leaderboard.append(LeaderboardItem(
                    candidate_id=candidate.id,
                    full_name=candidate.full_name,
                    email=candidate.email,
                    rank=eval_rec.rank,
                    is_shortlisted=eval_rec.is_shortlisted,
                    overall_match_score=eval_rec.overall_match_score,
                    skill_match_score=eval_rec.skill_match_score,
                    experience_score=eval_rec.experience_score,
                    semantic_score=eval_rec.semantic_score,
                    application_status=candidate.application_status.value if hasattr(candidate.application_status, "value") else str(candidate.application_status),
                    key_strengths=eval_rec.key_strengths or [],
                    potential_concerns=eval_rec.potential_concerns or [],
                    summary_reasoning=eval_rec.summary_reasoning,
                ))

        leaderboard.sort(key=lambda x: x.overall_match_score, reverse=True)
        return leaderboard
