import uuid
from datetime import datetime, timezone, timedelta
from typing import Sequence, Optional, Any
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.hiring_profile import HiringProfile
from app.models.preference import RecruiterPreference
from app.models.monitoring import CampaignMonitoringLog
from app.models.enums import CampaignStatus, ActionProposed, ActionStatus, PlatformType
from app.agents.campaign_monitor.graph import monitoring_graph, _normalize_platform
from app.services.campaign_service import CampaignService
from app.services.job_post_service import JobPostService


class MonitoringService:
    """Autonomous campaign health monitoring, pacing diagnosis, and LangGraph re-engagement loop service."""

    @staticmethod
    async def audit_campaign_health(
        db: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> CampaignMonitoringLog:
        """
        Executes an autonomous health audit for a campaign using the LangGraph StateGraph:
        1. Ingests pacing metrics and candidate pool statistics.
        2. Gemini reasons and routes to one of 4 tools:
           - propose_requirement_revision (HITL Guardrail)
           - repost_job_post (Autonomous Execution)
           - propose_deadline_extension (HITL Guardrail)
           - trigger_recruiter_alert (Autonomous Execution)
        3. Persists actionable log in campaign_monitoring_logs and returns the created log.
        """
        # Validate campaign exists
        await CampaignService.get_campaign_by_id(db, campaign_id)

        # Run LangGraph StateGraph
        final_state = await monitoring_graph.ainvoke(
            {"campaign_id": str(campaign_id)},
            config={"configurable": {"db": db}},
        )

        created_log_id = final_state.get("created_log_id")
        if not created_log_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Monitoring graph failed to create a log entry.",
            )

        stmt = select(CampaignMonitoringLog).where(CampaignMonitoringLog.id == uuid.UUID(created_log_id))
        res = await db.execute(stmt)
        log_entry = res.scalars().first()
        return log_entry

    @staticmethod
    async def monitor_all_active_campaigns(
        db: AsyncSession,
    ) -> Sequence[CampaignMonitoringLog]:
        """
        Batch monitors all active campaigns across the system (Used by the 24-hour Night Cron).
        """
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
        """
        Retrieves chronological monitoring and recommendation audit logs for a campaign.
        """
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
        """
        Recruiter guardrail execution: Approves or rejects a pending AI recommendation.
        """
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

        # Approved: Execute proposed action
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

            # Update Recruiter Preferences
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

            # Update Hiring Profile
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
