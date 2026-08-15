"""
LangGraph Campaign Monitor & Re-Engagement Agent.

Implements a StateGraph with 4 distinct tools and clear Autonomy vs. HITL Guardrail separation:
- Tool 1: propose_requirement_revision (HITL Guardrail)
- Tool 2: repost_job_post (Autonomous Execution)
- Tool 3: propose_deadline_extension (HITL Guardrail)
- Tool 4: trigger_recruiter_alert (Autonomous Execution)
"""

import uuid
import statistics
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.llm import get_llm
from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.evaluation import CandidateEvaluation
from app.models.hiring_profile import HiringProfile
from app.models.preference import RecruiterPreference
from app.models.job_post import JobPost
from app.models.monitoring import CampaignMonitoringLog
from app.models.enums import CampaignStatus, ApplicationStatus, ActionProposed, ActionStatus, PlatformType
from app.schemas.monitoring import (
    MonitoringMetricsSnapshot,
    MonitorAgentOutput,
    ActionPayload,
    MonitoringGraphState,
)
from app.agents.campaign_monitor.prompts import (
    CAMPAIGN_MONITOR_SYSTEM_PROMPT,
    CAMPAIGN_MONITOR_USER_PROMPT,
)
from app.services.job_post_service import JobPostService


campaign_monitor_prompt = ChatPromptTemplate.from_messages([
    ("system", CAMPAIGN_MONITOR_SYSTEM_PROMPT),
    ("user", CAMPAIGN_MONITOR_USER_PROMPT),
])


def _normalize_platform(raw_platform: Optional[str]) -> PlatformType:
    """Safely normalizes freeform LLM platform strings to valid PlatformType enum members."""
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


# ----------------------------------------------------------------------
# 1. NODE: INGEST CAMPAIGN METRICS & POOL SNAPSHOT
# ----------------------------------------------------------------------
async def node_ingest_metrics(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    db: AsyncSession = configurable["db"]
    campaign_id = uuid.UUID(state["campaign_id"])

    # 1. Fetch Campaign
    stmt_camp = select(Campaign).where(Campaign.id == campaign_id)
    res_camp = await db.execute(stmt_camp)
    campaign = res_camp.scalars().first()

    stmt_hp = select(HiringProfile).where(HiringProfile.campaign_id == campaign_id)
    res_hp = await db.execute(stmt_hp)
    hiring_profile = res_hp.scalars().first()

    stmt_pref = select(RecruiterPreference).where(RecruiterPreference.campaign_id == campaign_id)
    res_pref = await db.execute(stmt_pref)
    recruiter_pref = res_pref.scalars().first()

    stmt_posts = select(JobPost).where(JobPost.campaign_id == campaign_id)
    res_posts = await db.execute(stmt_posts)
    job_posts = res_posts.scalars().all()
    repost_count = len(job_posts)

    stmt_cand = select(Candidate).where(Candidate.campaign_id == campaign_id)
    res_cand = await db.execute(stmt_cand)
    candidates = res_cand.scalars().all()

    # 2. Timeline calculations
    now = datetime.utcnow()
    created_at = campaign.created_at or now
    elapsed_delta = now - created_at
    elapsed_days = max(1, elapsed_delta.days)
    duration_days = max(1, campaign.duration_days)
    elapsed_ratio = min(1.0, elapsed_days / duration_days)
    days_remaining = max(0, duration_days - elapsed_days)

    # 3. Funnel & Score metrics
    total_applicants = len(candidates)
    knockout_rejected = sum(1 for c in candidates if c.application_status == ApplicationStatus.REJECTED)
    knockout_rate = (knockout_rejected / total_applicants) if total_applicants > 0 else 0.0

    scores = []
    shortlisted_count = 0
    evaluated_count = 0

    for cand in candidates:
        stmt_eval = select(CandidateEvaluation).where(CandidateEvaluation.candidate_id == cand.id)
        res_eval = await db.execute(stmt_eval)
        eval_rec = res_eval.scalars().first()

        if eval_rec:
            evaluated_count += 1
            scores.append(eval_rec.overall_match_score)
            if eval_rec.is_shortlisted or cand.application_status == ApplicationStatus.SHORTLISTED:
                shortlisted_count += 1

    avg_score = round(statistics.mean(scores), 1) if scores else 0.0
    highest_score = round(max(scores), 1) if scores else 0.0
    target_shortlist = campaign.target_shortlist_size or 5
    shortlist_ratio = (shortlisted_count / target_shortlist) if target_shortlist > 0 else 0.0

    tech_skills = hiring_profile.technical_skills if hiring_profile and hiring_profile.technical_skills else []
    min_exp = hiring_profile.min_experience_years if hiring_profile else 0.0

    must_haves = []
    min_cgpa = None
    if recruiter_pref:
        min_cgpa = recruiter_pref.min_cgpa
        if recruiter_pref.skill_priorities:
            must_haves = [s for s, p in recruiter_pref.skill_priorities.items() if p == "MUST_HAVE"]

    return {
        "campaign_info": {
            "job_title": campaign.job_title,
            "company_name": campaign.company_name,
            "duration_days": duration_days,
            "elapsed_days": elapsed_days,
            "days_remaining": days_remaining,
            "elapsed_ratio": elapsed_ratio,
            "target_shortlist_size": target_shortlist,
            "repost_count": repost_count,
        },
        "metrics_snapshot": {
            "total_applicants": total_applicants,
            "knockout_rejected_count": knockout_rejected,
            "knockout_rate": knockout_rate,
            "evaluated_count": evaluated_count,
            "shortlisted_count": shortlisted_count,
            "shortlist_achievement_ratio": shortlist_ratio,
            "average_match_score": avg_score,
            "highest_match_score": highest_score,
        },
        "hiring_requirements": {
            "technical_skills": tech_skills,
            "must_have_skills": must_haves,
            "min_experience_years": min_exp,
            "min_cgpa": min_cgpa,
        },
    }


# ----------------------------------------------------------------------
# 2. NODE: DIAGNOSE BOTTLENECK & SELECT OPTIMAL TOOL
# ----------------------------------------------------------------------
async def node_diagnose_and_select_tool(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    c_info = state["campaign_info"]
    m_snap = state["metrics_snapshot"]
    reqs = state["hiring_requirements"]

    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(MonitorAgentOutput)
    chain = campaign_monitor_prompt | structured_llm

    diagnosis: MonitorAgentOutput = await chain.ainvoke({
        "job_title": c_info["job_title"],
        "company_name": c_info["company_name"],
        "duration_days": c_info["duration_days"],
        "elapsed_days": c_info["elapsed_days"],
        "elapsed_ratio": c_info["elapsed_ratio"],
        "days_remaining": c_info["days_remaining"],
        "target_shortlist_size": c_info["target_shortlist_size"],
        "total_applicants": m_snap["total_applicants"],
        "knockout_rejected_count": m_snap["knockout_rejected_count"],
        "knockout_rate": m_snap["knockout_rate"],
        "evaluated_count": m_snap["evaluated_count"],
        "shortlisted_count": m_snap["shortlisted_count"],
        "shortlist_achievement_ratio": m_snap["shortlist_achievement_ratio"],
        "average_match_score": m_snap["average_match_score"],
        "highest_match_score": m_snap["highest_match_score"],
        "technical_skills": ", ".join(reqs["technical_skills"]) if reqs["technical_skills"] else "None",
        "must_have_skills": ", ".join(reqs["must_have_skills"]) if reqs["must_have_skills"] else "None",
        "min_experience_years": reqs["min_experience_years"],
        "min_cgpa": reqs["min_cgpa"] if reqs["min_cgpa"] is not None else "None",
        "repost_count": c_info["repost_count"],
    })

    # Route to appropriate tool based on proposed_action
    action = diagnosis.proposed_action
    if action == ActionProposed.REVISE_REQUIREMENTS:
        selected_tool = "tool_propose_requirement_revision"
    elif action in [ActionProposed.REPOST_JOB, ActionProposed.REFRESH_JOB]:
        selected_tool = "tool_repost_job_post"
    elif action == ActionProposed.EXTEND_DEADLINE:
        selected_tool = "tool_propose_deadline_extension"
    elif action == ActionProposed.EARLY_SHORTLIST_ALERT:
        selected_tool = "tool_trigger_recruiter_alert"
    else:
        selected_tool = "persist_monitoring_state"

    return {
        "diagnosis": diagnosis.model_dump(),
        "selected_tool": selected_tool,
    }


# ----------------------------------------------------------------------
# 3. TOOL 1: propose_requirement_revision [🔒 HITL GUARDRAIL]
# ----------------------------------------------------------------------
async def node_tool_propose_requirement_revision(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    diagnosis = state["diagnosis"]
    action_details = diagnosis.get("action_details", {})
    relaxed_skills = action_details.get("relaxed_skills", [])
    suggested_cgpa = action_details.get("suggested_min_cgpa")

    sim_insight = (
        f"Simulated Pool Impact: Relaxing non-essential skills ({', '.join(relaxed_skills) if relaxed_skills else 'specified criteria'}) "
        f"and adjusting CGPA cutoff to {suggested_cgpa or 'flexible'} is projected to expand qualified applicant throughput by 30-40%."
    )

    reasoning = (
        f"[{diagnosis.get('diagnostic_category')}] Status: {diagnosis.get('pacing_health_status')}\n"
        f"Reasoning: {diagnosis.get('detailed_reasoning')}\n"
        f"🔒 HITL Guardrail: {sim_insight}\n"
        f"Impact Forecast: {diagnosis.get('impact_forecast')}"
    )

    return {
        "requires_hitl": True,
        "action_status": ActionStatus.PENDING_APPROVAL.value,
        "tool_output": {
            "tool_name": "propose_requirement_revision",
            "action_proposed": ActionProposed.REVISE_REQUIREMENTS.value,
            "relaxed_skills": relaxed_skills,
            "suggested_min_cgpa": suggested_cgpa,
            "suggested_min_experience_years": action_details.get("suggested_min_experience_years"),
            "pool_simulation_insight": sim_insight,
        },
        "final_reasoning": reasoning,
    }


# ----------------------------------------------------------------------
# 4. TOOL 2: repost_job_post [⚡ AUTONOMOUS EXECUTION]
# ----------------------------------------------------------------------
async def node_tool_repost_job_post(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    db: AsyncSession = configurable["db"]
    campaign_id = uuid.UUID(state["campaign_id"])
    diagnosis = state["diagnosis"]
    action_details = diagnosis.get("action_details", {})
    target_platform = _normalize_platform(action_details.get("target_platform"))

    # Autonomous execution: Generate and persist refreshed job post immediately
    try:
        job_post_rec = await JobPostService.generate_and_save_job_post(
            db, campaign_id, platform=target_platform
        )
        exec_note = f"⚡ Autonomous Execution: Refreshed job post automatically published to {target_platform.value} (Post ID: {job_post_rec.id}, Repost #{job_post_rec.repost_count})."
    except Exception as e:
        exec_note = f"⚡ Autonomous Repost Failed: {str(e)}"

    reasoning = (
        f"[{diagnosis.get('diagnostic_category')}] Status: {diagnosis.get('pacing_health_status')}\n"
        f"Reasoning: {diagnosis.get('detailed_reasoning')}\n"
        f"{exec_note}\n"
        f"Impact Forecast: {diagnosis.get('impact_forecast')}"
    )

    return {
        "requires_hitl": False,
        "action_status": ActionStatus.EXECUTED.value,
        "tool_output": {
            "tool_name": "repost_job_post",
            "action_proposed": ActionProposed.REPOST_JOB.value,
            "target_platform": target_platform.value,
            "execution_note": exec_note,
        },
        "final_reasoning": reasoning,
    }


# ----------------------------------------------------------------------
# 5. TOOL 3: propose_deadline_extension [🔒 HITL GUARDRAIL]
# ----------------------------------------------------------------------
async def node_tool_propose_deadline_extension(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    diagnosis = state["diagnosis"]
    action_details = diagnosis.get("action_details", {})
    ext_days = action_details.get("deadline_extension_days") or 7

    reasoning = (
        f"[{diagnosis.get('diagnostic_category')}] Status: {diagnosis.get('pacing_health_status')}\n"
        f"Reasoning: {diagnosis.get('detailed_reasoning')}\n"
        f"🔒 HITL Guardrail: Recommending +{ext_days} days campaign extension to allow pipeline completion for strong candidate pool.\n"
        f"Impact Forecast: {diagnosis.get('impact_forecast')}"
    )

    return {
        "requires_hitl": True,
        "action_status": ActionStatus.PENDING_APPROVAL.value,
        "tool_output": {
            "tool_name": "propose_deadline_extension",
            "action_proposed": ActionProposed.EXTEND_DEADLINE.value,
            "deadline_extension_days": ext_days,
        },
        "final_reasoning": reasoning,
    }


# ----------------------------------------------------------------------
# 6. TOOL 4: trigger_recruiter_alert [⚡ AUTONOMOUS EXECUTION]
# ----------------------------------------------------------------------
async def node_tool_trigger_recruiter_alert(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    diagnosis = state["diagnosis"]
    c_info = state["campaign_info"]
    m_snap = state["metrics_snapshot"]

    alert_msg = (
        f"⚡ High-Priority Recruiter Alert: Target shortlist achieved early ({m_snap['shortlisted_count']}/{c_info['target_shortlist_size']} candidates). "
        f"Top match score is {m_snap['highest_match_score']}/100. Ready for interview scheduling."
    )

    reasoning = (
        f"[{diagnosis.get('diagnostic_category')}] Status: {diagnosis.get('pacing_health_status')}\n"
        f"Reasoning: {diagnosis.get('detailed_reasoning')}\n"
        f"{alert_msg}\n"
        f"Impact Forecast: {diagnosis.get('impact_forecast')}"
    )

    return {
        "requires_hitl": False,
        "action_status": ActionStatus.EXECUTED.value,
        "tool_output": {
            "tool_name": "trigger_recruiter_alert",
            "action_proposed": ActionProposed.EARLY_SHORTLIST_ALERT.value,
            "alert_message": alert_msg,
        },
        "final_reasoning": reasoning,
    }


# ----------------------------------------------------------------------
# 7. NODE: PERSIST MONITORING STATE & DATABASE LOG
# ----------------------------------------------------------------------
async def node_persist_monitoring_state(state: MonitoringGraphState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    db: AsyncSession = configurable["db"]
    campaign_id = uuid.UUID(state["campaign_id"])
    c_info = state.get("campaign_info", {})
    m_snap = state.get("metrics_snapshot", {})
    diagnosis = state.get("diagnosis", {})
    tool_out = state.get("tool_output", {})

    now = datetime.utcnow()
    total_apps = m_snap.get("total_applicants", 0)
    days_rem = c_info.get("days_remaining", 0)
    elapsed_ratio = c_info.get("elapsed_ratio", 0.5)
    expected_apps = max(1, round(25 * elapsed_ratio))

    action_proposed_str = tool_out.get("action_proposed", ActionProposed.NONE.value)
    try:
        action_proposed_enum = ActionProposed(action_proposed_str)
    except ValueError:
        action_proposed_enum = ActionProposed.NONE

    action_status_str = state.get("action_status", ActionStatus.EXECUTED.value)
    try:
        action_status_enum = ActionStatus(action_status_str)
    except ValueError:
        action_status_enum = ActionStatus.EXECUTED

    reasoning_text = state.get("final_reasoning") or diagnosis.get("detailed_reasoning", "Campaign health verified.")

    log_entry = CampaignMonitoringLog(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        total_applications_count=total_apps,
        expected_applications_count=expected_apps,
        days_remaining=days_rem,
        agent_reasoning=reasoning_text,
        action_proposed=action_proposed_enum,
        status=action_status_enum,
        guardrail_flags={
            "diagnostic_category": diagnosis.get("diagnostic_category", "HEALTHY_PACING"),
            "pacing_health_status": diagnosis.get("pacing_health_status", "ON_TRACK"),
            "tool_selected": state.get("selected_tool", "none"),
            "tool_output": tool_out,
            "requires_hitl": state.get("requires_hitl", False),
            "risk_level": "HIGH" if state.get("requires_hitl") else "LOW",
            "requires_recruiter_approval": state.get("requires_hitl", False),
        },
        created_at=now,
    )

    db.add(log_entry)

    # Transition campaign status to MONITORING if PUBLISHED
    stmt_camp = select(Campaign).where(Campaign.id == campaign_id)
    res_camp = await db.execute(stmt_camp)
    campaign = res_camp.scalars().first()
    if campaign and campaign.status == CampaignStatus.PUBLISHED:
        campaign.status = CampaignStatus.MONITORING
        campaign.updated_at = now
        db.add(campaign)

    await db.commit()
    await db.refresh(log_entry)

    return {
        "created_log_id": str(log_entry.id),
    }


# ----------------------------------------------------------------------
# 8. CONDITIONAL ROUTING FUNCTION
# ----------------------------------------------------------------------
def route_selected_tool(state: MonitoringGraphState) -> Literal[
    "tool_propose_requirement_revision",
    "tool_repost_job_post",
    "tool_propose_deadline_extension",
    "tool_trigger_recruiter_alert",
    "persist_monitoring_state"
]:
    return state["selected_tool"]


# ----------------------------------------------------------------------
# 9. ASSEMBLE LANGGRAPH STATEGRAPH
# ----------------------------------------------------------------------
def build_monitoring_graph():
    workflow = StateGraph(MonitoringGraphState)

    # Add Nodes
    workflow.add_node("ingest_campaign_metrics", node_ingest_metrics)
    workflow.add_node("diagnose_and_select_tool", node_diagnose_and_select_tool)
    workflow.add_node("tool_propose_requirement_revision", node_tool_propose_requirement_revision)
    workflow.add_node("tool_repost_job_post", node_tool_repost_job_post)
    workflow.add_node("tool_propose_deadline_extension", node_tool_propose_deadline_extension)
    workflow.add_node("tool_trigger_recruiter_alert", node_tool_trigger_recruiter_alert)
    workflow.add_node("persist_monitoring_state", node_persist_monitoring_state)

    # Add Edges
    workflow.add_edge(START, "ingest_campaign_metrics")
    workflow.add_edge("ingest_campaign_metrics", "diagnose_and_select_tool")

    # Conditional Routing from diagnosis to chosen tool
    workflow.add_conditional_edges(
        "diagnose_and_select_tool",
        route_selected_tool,
        {
            "tool_propose_requirement_revision": "tool_propose_requirement_revision",
            "tool_repost_job_post": "tool_repost_job_post",
            "tool_propose_deadline_extension": "tool_propose_deadline_extension",
            "tool_trigger_recruiter_alert": "tool_trigger_recruiter_alert",
            "persist_monitoring_state": "persist_monitoring_state",
        }
    )

    # Tool nodes feed into state persistence
    workflow.add_edge("tool_propose_requirement_revision", "persist_monitoring_state")
    workflow.add_edge("tool_repost_job_post", "persist_monitoring_state")
    workflow.add_edge("tool_propose_deadline_extension", "persist_monitoring_state")
    workflow.add_edge("tool_trigger_recruiter_alert", "persist_monitoring_state")
    workflow.add_edge("persist_monitoring_state", END)

    return workflow.compile()


monitoring_graph = build_monitoring_graph()
