import io
import csv
import uuid
import statistics
from datetime import datetime
from typing import Sequence, Optional, Any
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.evaluation import CandidateEvaluation
from app.models.hiring_profile import HiringProfile
from app.models.preference import RecruiterPreference
from app.models.enums import CampaignStatus, ApplicationStatus
from app.schemas.dashboard import (
    EnrichedLeaderboardItem,
    ScoreDistribution,
    CampaignAnalytics,
    CandidateExportDossier,
    CampaignExportResponse,
)
from app.services.campaign_service import CampaignService
from app.services.candidate_service import CandidateService


class DashboardService:
    """Service handling recruiter leaderboard rankings, campaign analytics, CSV/JSON exports, and lifecycle controls."""

    @staticmethod
    async def get_top_k_leaderboard(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        top_k: Optional[int] = None,
        is_shortlisted_only: bool = False,
    ) -> Sequence[EnrichedLeaderboardItem]:
        """
        Retrieves enriched candidate leaderboard ordered by overall_match_score descending.
        Dynamically assigns 1-indexed ranks and syncs is_shortlisted flags.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        candidates = await CandidateService.list_candidates_for_campaign(db, campaign_id)

        candidate_data = []
        for candidate in candidates:
            # Fetch evaluation
            stmt = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == candidate.id)
            res = await db.execute(stmt)
            eval_rec = res.scalars().first()

            # Fetch candidate profile
            stmt_prof = select(CandidateProfile).where(CandidateProfile.candidate_id == candidate.id)
            res_prof = await db.execute(stmt_prof)
            cand_profile = res_prof.scalars().first()

            if eval_rec:
                candidate_data.append((candidate, eval_rec, cand_profile))

        # 1. Sort by overall_match_score descending
        candidate_data.sort(key=lambda item: item[1].overall_match_score, reverse=True)

        # 2. Update dynamic ranks & auto-shortlist
        shortlist_size = campaign.target_shortlist_size or 5
        items = []

        for idx, (cand, eval_rec, prof) in enumerate(candidate_data, 1):
            eval_rec.rank = idx
            
            # Update shortlist flag if in top K limit and not explicitly rejected
            if cand.application_status != ApplicationStatus.REJECTED:
                if idx <= shortlist_size:
                    eval_rec.is_shortlisted = True
                    if cand.application_status in [ApplicationStatus.EVALUATED, ApplicationStatus.PARSED]:
                        cand.application_status = ApplicationStatus.SHORTLISTED
                        db.add(cand)
                else:
                    if cand.application_status == ApplicationStatus.EVALUATED:
                        eval_rec.is_shortlisted = False
            
            db.add(eval_rec)

            # Extract proof insights
            portfolio_insights = prof.portfolio_insights if prof and prof.portfolio_insights else {}
            evidence_score = portfolio_insights.get("evidence_score")
            verified_badges = portfolio_insights.get("verified_badges", [])
            broken_links = portfolio_insights.get("broken_links", [])

            if is_shortlisted_only and not eval_rec.is_shortlisted:
                continue

            items.append(EnrichedLeaderboardItem(
                candidate_id=cand.id,
                rank=idx,
                full_name=cand.full_name,
                email=cand.email,
                phone=cand.phone,
                application_status=cand.application_status.value if hasattr(cand.application_status, "value") else str(cand.application_status),
                is_shortlisted=eval_rec.is_shortlisted,
                overall_match_score=eval_rec.overall_match_score,
                skill_match_score=eval_rec.skill_match_score,
                experience_score=eval_rec.experience_score,
                portfolio_score=eval_rec.portfolio_score,
                semantic_score=eval_rec.semantic_score,
                evidence_score=evidence_score,
                verified_badges=verified_badges,
                broken_links=broken_links,
                raw_resume_url=cand.raw_resume_url,
                github_url=cand.github_url,
                linkedin_url=cand.linkedin_url,
                portfolio_url=cand.portfolio_url,
                key_strengths=eval_rec.key_strengths or [],
                potential_concerns=eval_rec.potential_concerns or [],
                summary_reasoning=eval_rec.summary_reasoning,
            ))

        await db.commit()

        if top_k and top_k > 0:
            return items[:top_k]
        return items

    @staticmethod
    async def get_campaign_analytics(
        db: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> CampaignAnalytics:
        """
        Computes aggregate metrics, score distributions, and candidate pool insights.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        candidates = await CandidateService.list_candidates_for_campaign(db, campaign_id)

        total_applicants = len(candidates)
        knockout_rejected = sum(1 for c in candidates if c.application_status == ApplicationStatus.REJECTED)

        scores = []
        shortlisted_count = 0
        evaluated_count = 0
        distribution = ScoreDistribution()
        top_skills = {}
        top_institutions = {}
        evidence_stats = {"github_verified": 0, "linkedin_verified": 0, "credentials_verified": 0, "broken_links": 0}

        for cand in candidates:
            # Fetch evaluation
            stmt = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == cand.id)
            res = await db.execute(stmt)
            eval_rec = res.scalars().first()

            # Fetch profile
            stmt_prof = select(CandidateProfile).where(CandidateProfile.candidate_id == cand.id)
            res_prof = await db.execute(stmt_prof)
            cand_profile = res_prof.scalars().first()

            if eval_rec:
                evaluated_count += 1
                score = eval_rec.overall_match_score
                scores.append(score)

                if eval_rec.is_shortlisted or cand.application_status == ApplicationStatus.SHORTLISTED:
                    shortlisted_count += 1

                # Score distribution buckets
                if score >= 90.0:
                    distribution.tier_90_100 += 1
                elif score >= 80.0:
                    distribution.tier_80_89 += 1
                elif score >= 70.0:
                    distribution.tier_70_79 += 1
                elif score >= 60.0:
                    distribution.tier_60_69 += 1
                else:
                    distribution.tier_below_60 += 1

            if cand_profile:
                # Skill frequency
                for skill in (cand_profile.parsed_skills or []):
                    top_skills[skill] = top_skills.get(skill, 0) + 1

                # Institution frequency
                for edu in (cand_profile.parsed_education or []):
                    inst = edu.get("institution") or "Unknown"
                    top_institutions[inst] = top_institutions.get(inst, 0) + 1

                # Evidence verification stats
                insights = cand_profile.portfolio_insights or {}
                for src in insights.get("verified_sources", []):
                    cat = src.get("category", "")
                    if cat == "CODE_REPOSITORY" and src.get("status") == "LIVE":
                        evidence_stats["github_verified"] += 1
                    elif cat == "PROFESSIONAL_SOCIAL" and src.get("status") == "LIVE":
                        evidence_stats["linkedin_verified"] += 1
                    elif cat == "CERTIFICATE_CREDENTIAL" and src.get("status") == "LIVE":
                        evidence_stats["credentials_verified"] += 1
                
                evidence_stats["broken_links"] += len(insights.get("broken_links", []))

        # Score aggregates
        avg_score = round(statistics.mean(scores), 2) if scores else 0.0
        med_score = round(statistics.median(scores), 2) if scores else 0.0
        max_score = round(max(scores), 2) if scores else 0.0
        min_score = round(min(scores), 2) if scores else 0.0
        pass_rate = round(((total_applicants - knockout_rejected) / total_applicants * 100), 2) if total_applicants > 0 else 0.0

        # Sort top 10 skills and institutions
        sorted_skills = dict(sorted(top_skills.items(), key=lambda x: x[1], reverse=True)[:10])
        sorted_institutions = dict(sorted(top_institutions.items(), key=lambda x: x[1], reverse=True)[:10])

        return CampaignAnalytics(
            campaign_id=campaign.id,
            campaign_title=campaign.job_title,
            company_name=campaign.company_name,
            status=campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status),
            target_shortlist_size=campaign.target_shortlist_size,
            total_applicants=total_applicants,
            knockout_rejected_count=knockout_rejected,
            evaluated_count=evaluated_count,
            shortlisted_count=shortlisted_count,
            pass_through_rate_pct=pass_rate,
            average_match_score=avg_score,
            median_match_score=med_score,
            highest_match_score=max_score,
            lowest_match_score=min_score,
            score_distribution=distribution,
            top_skills_represented=sorted_skills,
            top_institutions_represented=sorted_institutions,
            evidence_verification_stats=evidence_stats,
        )

    @staticmethod
    async def export_campaign_csv(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        top_k: Optional[int] = None,
        is_shortlisted_only: bool = False,
    ) -> str:
        """
        Generates a flat CSV text export of campaign candidates.
        """
        items = await DashboardService.get_top_k_leaderboard(
            db, campaign_id, top_k=top_k, is_shortlisted_only=is_shortlisted_only
        )

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # CSV Header
        writer.writerow([
            "Rank",
            "Full Name",
            "Email",
            "Phone",
            "Application Status",
            "Is Shortlisted",
            "Overall Match Score",
            "Technical Depth Score",
            "Experience Fit Score",
            "Projects & Brand Score",
            "Soft Skills Score",
            "Evidence Authenticity Score",
            "Verified Badges",
            "Potential Concerns",
            "Key Strengths",
            "AI Reasoning",
            "Resume URL",
            "GitHub URL",
            "LinkedIn URL",
            "Portfolio URL",
        ])

        for item in items:
            writer.writerow([
                item.rank,
                item.full_name,
                item.email,
                item.phone or "",
                item.application_status,
                "YES" if item.is_shortlisted else "NO",
                item.overall_match_score,
                item.skill_match_score,
                item.experience_score,
                item.portfolio_score,
                item.semantic_score,
                item.evidence_score if item.evidence_score is not None else "",
                " | ".join(item.verified_badges),
                " | ".join(item.potential_concerns),
                " | ".join(item.key_strengths),
                item.summary_reasoning,
                item.raw_resume_url or "",
                item.github_url or "",
                item.linkedin_url or "",
                item.portfolio_url or "",
            ])

        return output.getvalue()

    @staticmethod
    async def export_campaign_json(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        top_k: Optional[int] = None,
        is_shortlisted_only: bool = False,
    ) -> CampaignExportResponse:
        """
        Generates a comprehensive nested JSON document of the campaign and candidate profiles.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        
        # Hiring profile & preferences
        stmt_hp = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
        res_hp = await db.execute(stmt_hp)
        hp = res_hp.scalars().first()

        stmt_pref = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
        res_pref = await db.execute(stmt_pref)
        pref = res_pref.scalars().first()

        leaderboard_items = await DashboardService.get_top_k_leaderboard(
            db, campaign_id, top_k=top_k, is_shortlisted_only=is_shortlisted_only
        )

        candidate_dossiers = []
        for item in leaderboard_items:
            # Fetch raw candidate & profile
            stmt_cand = select(Candidate).where(Candidate.id == item.candidate_id)
            res_cand = await db.execute(stmt_cand)
            cand = res_cand.scalars().first()

            stmt_prof = select(CandidateProfile).where(CandidateProfile.candidate_id == item.candidate_id)
            res_prof = await db.execute(stmt_prof)
            prof = res_prof.scalars().first()

            portfolio_insights = prof.portfolio_insights if prof and prof.portfolio_insights else {}

            candidate_dossiers.append(CandidateExportDossier(
                candidate_id=item.candidate_id,
                rank=item.rank,
                full_name=item.full_name,
                email=item.email,
                phone=item.phone,
                application_status=item.application_status,
                is_shortlisted=item.is_shortlisted,
                applied_at=cand.applied_at if cand else datetime.utcnow(),
                scores={
                    "overall_match_score": item.overall_match_score,
                    "skill_match_score": item.skill_match_score,
                    "experience_score": item.experience_score,
                    "portfolio_score": item.portfolio_score,
                    "semantic_score": item.semantic_score,
                    "evidence_score": item.evidence_score or 0.0,
                },
                parsed_skills=prof.parsed_skills if prof else [],
                parsed_education=prof.parsed_education if prof else [],
                parsed_work_experience=prof.parsed_work_experience if prof else [],
                parsed_projects=prof.parsed_projects if prof else [],
                certifications=prof.certifications if prof else [],
                evidence_score=portfolio_insights.get("evidence_score"),
                verified_sources=portfolio_insights.get("verified_sources", []),
                verified_badges=portfolio_insights.get("verified_badges", []),
                raw_resume_url=item.raw_resume_url,
                github_url=item.github_url,
                linkedin_url=item.linkedin_url,
                portfolio_url=item.portfolio_url,
                key_strengths=item.key_strengths,
                potential_concerns=item.potential_concerns,
                summary_reasoning=item.summary_reasoning,
            ))

        hp_dict = {
            "technical_skills": hp.technical_skills,
            "soft_skills": hp.soft_skills,
            "min_experience_years": hp.min_experience_years,
            "experience_requirements": hp.experience_requirements,
        } if hp else None

        pref_dict = {
            "skill_priorities": pref.skill_priorities,
            "evaluation_weights": pref.evaluation_weights,
            "min_cgpa": pref.min_cgpa,
            "immediate_joiner_only": pref.immediate_joiner_only,
        } if pref else None

        return CampaignExportResponse(
            campaign_id=campaign.id,
            company_name=campaign.company_name,
            job_title=campaign.job_title,
            status=campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status),
            target_shortlist_size=campaign.target_shortlist_size,
            exported_at=datetime.utcnow(),
            total_candidates_exported=len(candidate_dossiers),
            hiring_profile=hp_dict,
            recruiter_preferences=pref_dict,
            candidates=candidate_dossiers,
        )

    @staticmethod
    async def update_candidate_status(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        candidate_id: uuid.UUID,
        new_status: ApplicationStatus,
        notes: Optional[str] = None,
    ) -> Candidate:
        """
        Allows recruiters to manually override a candidate's application stage.
        """
        # Validate campaign exists
        await CampaignService.get_campaign_by_id(db, campaign_id)

        stmt = select(Candidate).where(Candidate.id == candidate_id, Candidate.campaign_id == campaign_id)
        res = await db.execute(stmt)
        candidate = res.scalars().first()

        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate with ID '{candidate_id}' not found in campaign '{campaign_id}'.",
            )

        candidate.application_status = new_status
        db.add(candidate)

        # Update evaluation shortlist flag accordingly
        stmt_eval = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == candidate_id)
        res_eval = await db.execute(stmt_eval)
        eval_rec = res_eval.scalars().first()

        if eval_rec:
            if new_status == ApplicationStatus.SHORTLISTED:
                eval_rec.is_shortlisted = True
            elif new_status == ApplicationStatus.REJECTED:
                eval_rec.is_shortlisted = False
            
            if notes:
                eval_rec.summary_reasoning = f"{eval_rec.summary_reasoning} [Recruiter Note: {notes}]"

            db.add(eval_rec)

        await db.commit()
        await db.refresh(candidate)
        return candidate

    @staticmethod
    async def close_campaign(
        db: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> Campaign:
        """
        Transitions campaign status to CLOSED.
        """
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)
        campaign.status = CampaignStatus.CLOSED
        campaign.updated_at = datetime.utcnow()
        
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign
