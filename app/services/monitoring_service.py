import uuid
import statistics
from datetime import datetime, timezone, timedelta
from typing import Sequence, Optional, Any
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.evaluation import CandidateEvaluation
from app.models.hiring_profile import HiringProfile
from app.models.preference import RecruiterPreference
from app.models.job_post import JobPost
from app.models.monitoring import CampaignMonitoringLog
from app.models.enums import CampaignStatus, ApplicationStatus, ActionProposed, ActionStatus, PlatformType
from app.agents.campaign_monitor import run_monitoring_agent
from app.services.campaign_service import CampaignService
from app.services.job_post_service import JobPostService


def _normalize_platform(raw_platform: Optional[str]) -> PlatformType:
    """Helper to convert string platform names to PlatformType enum."""
    if not raw_platform:
        return PlatformType.LINKEDIN
    val = str(raw_platform).upper()
    if "INDEED" in val:
        return PlatformType.INDEED
    elif "COMPANY" in val or "PORTAL" in val or "CAREER" in val:
        return PlatformType.COMPANY_PORTAL
    elif "LINKEDIN" in val or "LINKED_IN" in val:
        return PlatformType.LINKEDIN
    return PlatformType.GENERIC_WEB


class MonitoringService:
    """Simplified Campaign Monitoring Service using LangGraph Agent."""

    @staticmethod
    async def _gather_metrics(db: AsyncSession, campaign_id: uuid.UUID) -> dict[str, Any]:
        """Collects timeline, applicant funnel, and candidate scores into a plain dictionary."""
        # 1. Fetch Campaign & Hiring Details
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        stmt_hp = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
        res_hp = await db.execute(stmt_hp)
        hiring_profile = res_hp.scalars().first()

        stmt_pref = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
        res_pref = await db.execute(stmt_pref)
        recruiter_pref = res_pref.scalars().first()

        stmt_posts = select(JobPost).where(JobPost.campaign_id == campaign_id)
        res_posts = await db.execute(stmt_posts)
        job_posts = res_posts.scalars().all()

        stmt_cand = select(Candidate).where(Candidate.campaign_id == campaign_id)
        res_cand = await db.execute(stmt_cand)
        candidates = res_cand.scalars().all()

        # 2. Timeline calculations
        now = datetime.utcnow()
        created_at = campaign.created_at or now
        elapsed_days = max(1, (now - created_at).days)
        duration_days = max(1, campaign.duration_days)
        elapsed_ratio = min(1.0, elapsed_days / duration_days)
        days_remaining = max(0, duration_days - elapsed_days)

        # 3. Funnel & Score metrics
        total_applicants = len(candidates)
        knockouts = sum(1 for c in candidates if c.application_status == ApplicationStatus.REJECTED)
        knockout_rate = (knockouts / total_applicants) if total_applicants > 0 else 0.0

        scores = []
        shortlisted = 0
        evaluated = 0

        for cand in candidates:
            stmt_eval = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == cand.id)
            res_eval = await db.execute(stmt_eval)
            ev = res_eval.scalars().first()
            if ev:
                evaluated += 1
                scores.append(ev.overall_match_score)
                if ev.is_shortlisted or cand.application_status == ApplicationStatus.SHORTLISTED:
                    shortlisted += 1

        avg_score = round(statistics.mean(scores), 1) if scores else 0.0
        max_score = round(max(scores), 1) if scores else 0.0

        tech_skills = hiring_profile.technical_skills if hiring_profile and hiring_profile.technical_skills else []
        min_exp = hiring_profile.min_experience_years if hiring_profile else 0.0
        must_haves = []
        min_cgpa = None

        if recruiter_pref:
            min_cgpa = recruiter_pref.min_cgpa
            if recruiter_pref.skill_priorities:
                must_haves = [s for s, p in recruiter_pref.skill_priorities.items() if p == "MUST_HAVE"]

        return {
            "job_title": campaign.job_title,
            "company_name": campaign.company_name,
            "duration_days": duration_days,
            "elapsed_days": elapsed_days,
            "days_remaining": days_remaining,
            "elapsed_ratio": elapsed_ratio,
            "target_shortlist_size": campaign.target_shortlist_size or 5,
            "total_applicants": total_applicants,
            "knockout_rejected_count": knockouts,
            "knockout_rate": knockout_rate,
            "evaluated_count": evaluated,
            "shortlisted_count": shortlisted,
            "average_match_score": avg_score,
            "highest_match_score": max_score,
            "technical_skills": ", ".join(tech_skills) if tech_skills else "None",
            "must_have_skills": ", ".join(must_haves) if must_haves else "None",
            "min_experience_years": min_exp,
            "min_cgpa": min_cgpa if min_cgpa is not None else "None",
            "repost_count": len(job_posts),
        }

    @staticmethod
    async def audit_campaign_health(
        db: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> CampaignMonitoringLog:
        """Runs the LangGraph agent on campaign metrics and saves the result."""
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        # 1. Gather metrics
        metrics = await MonitoringService._gather_metrics(db, campaign_id)

        # 2. Run LangGraph Monitoring Agent
        result = await run_monitoring_agent(metrics)
        decision = result.get("decision")
        tool_result = result.get("tool_result", {})
        requires_hitl = result.get("requires_hitl", False)
        action_status = result.get("action_status", ActionStatus.EXECUTED)

        action_proposed = decision.action if decision else ActionProposed.NONE
        reasoning_text = decision.reasoning if decision else "Campaign is on track."
        if decision and decision.impact_forecast:
            reasoning_text += f"\nImpact Forecast: {decision.impact_forecast}"

        # 3. If Autonomous Action (REPOST_JOB), auto-execute now
        if action_proposed in [ActionProposed.REPOST_JOB, ActionProposed.REFRESH_JOB] and not requires_hitl:
            target_platform = _normalize_platform(decision.target_platform)
            try:
                job_post_rec = await JobPostService.generate_and_save_job_post(
                    db, campaign_id, platform=target_platform
                )
                reasoning_text += f"\n⚡ Autonomous Execution: Refreshed job post published to {target_platform.value} (Post ID: {job_post_rec.id})."
            except Exception as e:
                reasoning_text += f"\n⚡ Autonomous Repost Note: {e}"

        # 4. Save audit log to database
        now = datetime.utcnow()
        log_entry = CampaignMonitoringLog(
            id=uuid.uuid4(),
            campaign_id=campaign_id,
            total_applications_count=metrics["total_applicants"],
            expected_applications_count=max(1, round(25 * metrics["elapsed_ratio"])),
            days_remaining=metrics["days_remaining"],
            agent_reasoning=reasoning_text,
            action_proposed=action_proposed,
            status=action_status,
            guardrail_flags={
                "tool_selected": tool_result.get("tool_name", "none"),
                "tool_output": tool_result,
                "requires_hitl": requires_hitl,
                "requires_recruiter_approval": requires_hitl,
            },
            created_at=now,
        )

        db.add(log_entry)

        # 5. Update campaign status to MONITORING if PUBLISHED
        if campaign.status == CampaignStatus.PUBLISHED:
            campaign.status = CampaignStatus.MONITORING
            campaign.updated_at = now
            db.add(campaign)

        await db.commit()
        await db.refresh(log_entry)
        return log_entry

    @staticmethod
    async def monitor_all_active_campaigns(
        db: AsyncSession,
    ) -> Sequence[CampaignMonitoringLog]:
        """Batch audits all active campaigns (used by the nightly cron)."""
        stmt = select(Campaign).where(
            Campaign.status.in_([
                CampaignStatus.PUBLISHED,
                CampaignStatus.MONITORING,
                CampaignStatus.SHORTLISTED,
            ])
        )
        res = await db.execute(stmt)
        active_campaigns = res.scalars().all()

        logs = []
        for camp in active_campaigns:
            try:
                log_entry = await MonitoringService.audit_campaign_health(db, camp.id)
                logs.append(log_entry)
            except Exception as e:
                print(f"[MonitoringService] Error auditing campaign {camp.id}: {e}")

        return logs

    @staticmethod
    async def get_monitoring_history(
        db: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> Sequence[CampaignMonitoringLog]:
        """Retrieves history of monitoring logs for a campaign."""
        await CampaignService.get_campaign_by_id(db, campaign_id)

        stmt = select(CampaignMonitoringLog).where(
            CampaignMonitoringLog.campaign_id == campaign_id
        ).order_by(CampaignMonitoringLog.created_at.desc())
        
        res = await db.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def decide_proposed_action(
        db: AsyncSession,
        campaign_id: uuid.UUID,
        log_id: uuid.UUID,
        approved: bool,
        notes: Optional[str] = None,
    ) -> CampaignMonitoringLog:
        """Recruiter guardrail: Approves or declines a pending recommendation."""
        campaign = await CampaignService.get_campaign_by_id(db, campaign_id)

        stmt = select(CampaignMonitoringLog).where(
            CampaignMonitoringLog.id == log_id,
            CampaignMonitoringLog.campaign_id == campaign_id,
        )
        res = await db.execute(stmt)
        log_entry = res.scalars().first()

        if not log_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring log '{log_id}' not found for campaign '{campaign_id}'.",
            )

        if log_entry.status != ActionStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Monitoring action is already in state '{log_entry.status}'.",
            )

        if not approved:
            log_entry.status = ActionStatus.DECLINED_BY_RECRUITER
            if notes:
                log_entry.agent_reasoning += f"\n[Recruiter Declined]: {notes}"
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)
            return log_entry

        # Approved: Apply the proposed changes
        flags = log_entry.guardrail_flags or {}
        tool_output = flags.get("tool_output", {})
        action = log_entry.action_proposed

        if action in [ActionProposed.REPOST_JOB, ActionProposed.REFRESH_JOB]:
            target_platform = _normalize_platform(tool_output.get("target_platform"))
            await JobPostService.generate_and_save_job_post(db, campaign_id, platform=target_platform)
            log_entry.agent_reasoning += f"\n[Recruiter Approved]: Refreshed job post published to {target_platform.value}."

        elif action == ActionProposed.REVISE_REQUIREMENTS:
            relaxed = tool_output.get("relaxed_skills", [])
            sugg_cgpa = tool_output.get("suggested_min_cgpa")
            sugg_exp = tool_output.get("suggested_min_experience_years")

            stmt_pref = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
            res_pref = await db.execute(stmt_pref)
            pref = res_pref.scalars().first()
            if pref:
                if relaxed and pref.skill_priorities:
                    for s in relaxed:
                        if s in pref.skill_priorities:
                            pref.skill_priorities[s] = "PREFERRED"
                if sugg_cgpa is not None:
                    pref.min_cgpa = sugg_cgpa
                db.add(pref)

            if sugg_exp is not None:
                stmt_hp = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
                res_hp = await db.execute(stmt_hp)
                hp = res_hp.scalars().first()
                if hp:
                    hp.min_experience_years = sugg_exp
                    db.add(hp)

            log_entry.agent_reasoning += f"\n[Recruiter Approved]: Requirements relaxed (Skills: {relaxed}, CGPA: {sugg_cgpa}, Exp: {sugg_exp})."

        elif action == ActionProposed.EXTEND_DEADLINE:
            ext_days = tool_output.get("deadline_extension_days") or 7
            campaign.duration_days += ext_days
            if campaign.application_deadline:
                campaign.application_deadline += timedelta(days=ext_days)
            campaign.updated_at = datetime.utcnow()
            db.add(campaign)
            log_entry.agent_reasoning += f"\n[Recruiter Approved]: Campaign duration extended by +{ext_days} days."

        log_entry.status = ActionStatus.EXECUTED
        if notes:
            log_entry.agent_reasoning += f"\n[Recruiter Notes]: {notes}"

        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        return log_entry
