import uuid
from typing import Any
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.evaluation import CandidateEvaluation
from app.utils.url_classifier import classify_url
from app.utils.url_inspector import inspect_url_async
from app.agents.evidence_verifier.agent import verify_evidence_claim
from app.services.candidate_service import CandidateService


class EvidenceService:
    """Service handling multi-domain evidence verification, fact-checking, and badge integration."""

    @staticmethod
    async def verify_candidate_evidence(
        db: AsyncSession, candidate_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Verifies all submitted evidence URLs for a single candidate,
        updates CandidateProfile.portfolio_insights, and refreshes candidate evaluation scores & badges.
        """
        # 1. Fetch Candidate & Profile
        candidate = await CandidateService.get_candidate_by_id(db, candidate_id)
        
        stmt = select(CandidateProfile).where(CandidateProfile.candidate_id == candidate_id)
        res = await db.execute(stmt)
        profile = res.scalars().first()

        if not profile:
            return {"candidate_id": candidate_id, "evidence_score": 0.0, "verified_badges": []}

        # 2. Gather all candidate evidence URLs
        urls_to_verify = []
        if candidate.github_url:
            urls_to_verify.append(candidate.github_url)
        if candidate.linkedin_url:
            urls_to_verify.append(candidate.linkedin_url)
        if candidate.portfolio_url:
            urls_to_verify.append(candidate.portfolio_url)

        # Extract any extra URLs found in parsed projects
        for project in (profile.parsed_projects or []):
            if isinstance(project, dict) and project.get("link"):
                link = project.get("link")
                if link not in urls_to_verify:
                    urls_to_verify.append(link)

        verified_sources = []
        broken_links = []
        verified_badges = []
        total_confidence = 0.0

        if not urls_to_verify:
            # Neutral base score if no external URLs submitted
            evidence_score = 60.0
        else:
            for url in urls_to_verify:
                category = classify_url(url)
                inspection = await inspect_url_async(url)

                if inspection.is_live:
                    fact_check = await verify_evidence_claim(
                        candidate_name=candidate.full_name,
                        url=url,
                        category=category,
                        page_title=inspection.page_title,
                        page_snippet=inspection.meta_description,
                        resume_skills=profile.parsed_skills or [],
                    )

                    badge = f"✅ {fact_check.verification_badge}"
                    verified_badges.append(badge)
                    total_confidence += fact_check.confidence_score

                    verified_sources.append({
                        "url": url,
                        "category": category,
                        "status": "LIVE",
                        "badge": fact_check.verification_badge,
                        "confidence_score": fact_check.confidence_score,
                        "reasoning": fact_check.reasoning,
                    })
                else:
                    broken_warning = f"⚠️ Submitted link '{url}' returned HTTP status or connection error."
                    broken_links.append(broken_warning)

                    verified_sources.append({
                        "url": url,
                        "category": category,
                        "status": "BROKEN",
                        "error": inspection.error_message or "HTTP 404 / Connection Error",
                    })

            valid_count = len([v for v in verified_sources if v["status"] == "LIVE"])
            if valid_count > 0:
                avg_confidence = total_confidence / valid_count
                evidence_score = round(min(100.0, avg_confidence * 100.0), 2)
            else:
                evidence_score = 30.0

        # 3. Update CandidateProfile.portfolio_insights
        insights = {
            "evidence_score": evidence_score,
            "verified_sources": verified_sources,
            "broken_links": broken_links,
            "verified_badges": verified_badges,
        }
        profile.portfolio_insights = insights
        db.add(profile)

        # 4. Refresh CandidateEvaluation DB Record if present
        eval_stmt = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == candidate_id)
        eval_res = await db.execute(eval_stmt)
        eval_rec = eval_res.scalars().first()

        if eval_rec:
            eval_rec.portfolio_score = evidence_score
            
            current_strengths = eval_rec.key_strengths or []
            for b in verified_badges:
                if b not in current_strengths:
                    current_strengths.append(b)
            eval_rec.key_strengths = current_strengths

            current_concerns = eval_rec.potential_concerns or []
            for bl in broken_links:
                if bl not in current_concerns:
                    current_concerns.append(bl)
            eval_rec.potential_concerns = current_concerns

            # Recalculate composite overall score with updated portfolio score
            w_tech, w_exp, w_portfolio, w_soft = 0.40, 0.35, 0.15, 0.10
            eval_rec.overall_match_score = round(
                (eval_rec.skill_match_score * w_tech) +
                (eval_rec.experience_score * w_exp) +
                (eval_rec.portfolio_score * w_portfolio) +
                (eval_rec.semantic_score * w_soft),
                2
            )
            db.add(eval_rec)

        await db.commit()
        await db.refresh(profile)

        return insights

    @staticmethod
    async def verify_all_campaign_evidence(
        db: AsyncSession, campaign_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """
        Batch verifies evidence for all candidates in a campaign.
        """
        candidates = await CandidateService.list_candidates_for_campaign(db, campaign_id)
        results = []
        for candidate in candidates:
            res = await EvidenceService.verify_candidate_evidence(db, candidate.id)
            results.append(res)
        return results
