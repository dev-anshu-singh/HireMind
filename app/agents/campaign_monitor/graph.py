"""
LangGraph Campaign Monitor Agent.

A clean, beginner-friendly LangGraph state machine with 4 tools:
1. tool_repost_job (⚡ Autonomous)
2. tool_revise_requirements (🔒 HITL Guardrail)
3. tool_extend_deadline (🔒 HITL Guardrail)
4. tool_alert_recruiter (⚡ Autonomous)
"""

from typing import Optional, Any, TypedDict, Literal
from langgraph.graph import StateGraph, START, END

from app.core.llm import get_campaign_monitor_llm
from app.models.enums import ActionProposed, ActionStatus, PlatformType
from app.schemas.monitoring import MonitorDecision
from app.agents.campaign_monitor.prompts import campaign_monitor_prompt


# ----------------------------------------------------------------------
# 1. State Definition (Simple TypedDict)
# ----------------------------------------------------------------------
class MonitoringState(TypedDict, total=False):
    campaign_data: dict[str, Any]
    decision: Optional[MonitorDecision]
    tool_result: dict[str, Any]
    requires_hitl: bool
    action_status: ActionStatus


# ----------------------------------------------------------------------
# 2. Node: Diagnose Campaign (Calls Gemini with Structured Output)
# ----------------------------------------------------------------------
async def diagnose_campaign(state: MonitoringState) -> dict[str, Any]:
    """Uses Gemini to evaluate campaign health and select an action."""
    data = state["campaign_data"]

    llm = get_campaign_monitor_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(MonitorDecision)
    chain = campaign_monitor_prompt | structured_llm

    decision: MonitorDecision = await chain.ainvoke(data)
    return {"decision": decision}


# ----------------------------------------------------------------------
# 3. Tool Nodes (4 Actions with Clear Autonomy vs HITL Guardrails)
# ----------------------------------------------------------------------
def tool_repost_job(state: MonitoringState) -> dict[str, Any]:
    """⚡ Autonomous Tool: Prepares job repost action."""
    decision = state["decision"]
    platform = decision.target_platform or "LINKEDIN"

    return {
        "requires_hitl": False,
        "action_status": ActionStatus.EXECUTED,
        "tool_result": {
            "tool_name": "repost_job_post",
            "action": ActionProposed.REPOST_JOB,
            "target_platform": platform,
        },
    }


def tool_revise_requirements(state: MonitoringState) -> dict[str, Any]:
    """🔒 HITL Guardrail: Prepares criteria relaxation for recruiter approval."""
    decision = state["decision"]
    skills = decision.relaxed_skills

    sim_text = (
        f"Simulated Pool Impact: Relaxing ({', '.join(skills) if skills else 'criteria'}) "
        f"and setting min CGPA to {decision.suggested_min_cgpa or 'flexible'} is projected to expand qualified applicants by 30-40%."
    )

    return {
        "requires_hitl": True,
        "action_status": ActionStatus.PENDING_APPROVAL,
        "tool_result": {
            "tool_name": "propose_requirement_revision",
            "action": ActionProposed.REVISE_REQUIREMENTS,
            "relaxed_skills": skills,
            "suggested_min_cgpa": decision.suggested_min_cgpa,
            "suggested_min_experience_years": decision.suggested_min_experience_years,
            "pool_simulation_insight": sim_text,
        },
    }


def tool_extend_deadline(state: MonitoringState) -> dict[str, Any]:
    """🔒 HITL Guardrail: Proposes deadline extension for recruiter approval."""
    decision = state["decision"]
    days = decision.deadline_extension_days or 7

    return {
        "requires_hitl": True,
        "action_status": ActionStatus.PENDING_APPROVAL,
        "tool_result": {
            "tool_name": "propose_deadline_extension",
            "action": ActionProposed.EXTEND_DEADLINE,
            "deadline_extension_days": days,
        },
    }


def tool_alert_recruiter(state: MonitoringState) -> dict[str, Any]:
    """⚡ Autonomous Tool: Generates high-priority interview alert."""
    decision = state["decision"]
    msg = decision.alert_message or "Target shortlist reached early! Candidates are ready for interviews."

    return {
        "requires_hitl": False,
        "action_status": ActionStatus.EXECUTED,
        "tool_result": {
            "tool_name": "trigger_recruiter_alert",
            "action": ActionProposed.EARLY_SHORTLIST_ALERT,
            "alert_message": msg,
        },
    }


# ----------------------------------------------------------------------
# 4. Conditional Router
# ----------------------------------------------------------------------
def route_by_action(state: MonitoringState) -> Literal["repost", "revise", "extend", "alert", "__end__"]:
    decision = state.get("decision")
    if not decision:
        return "__end__"

    action = decision.action
    if action in [ActionProposed.REPOST_JOB, ActionProposed.REFRESH_JOB]:
        return "repost"
    elif action == ActionProposed.REVISE_REQUIREMENTS:
        return "revise"
    elif action == ActionProposed.EXTEND_DEADLINE:
        return "extend"
    elif action == ActionProposed.EARLY_SHORTLIST_ALERT:
        return "alert"
    return "__end__"


# ----------------------------------------------------------------------
# 5. Build and Compile the Graph
# ----------------------------------------------------------------------
def build_monitoring_graph():
    workflow = StateGraph(MonitoringState)

    workflow.add_node("diagnose", diagnose_campaign)
    workflow.add_node("repost", tool_repost_job)
    workflow.add_node("revise", tool_revise_requirements)
    workflow.add_node("extend", tool_extend_deadline)
    workflow.add_node("alert", tool_alert_recruiter)

    workflow.add_edge(START, "diagnose")
    workflow.add_conditional_edges("diagnose", route_by_action)

    workflow.add_edge("repost", END)
    workflow.add_edge("revise", END)
    workflow.add_edge("extend", END)
    workflow.add_edge("alert", END)

    return workflow.compile()


monitoring_graph = build_monitoring_graph()


async def run_monitoring_agent(campaign_data: dict[str, Any]) -> dict[str, Any]:
    """Clean public runner function to execute the LangGraph monitoring agent."""
    return await monitoring_graph.ainvoke({"campaign_data": campaign_data})
