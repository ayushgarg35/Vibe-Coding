"""
LangGraph Node Implementations — each node calls the appropriate agent.
Nodes are pure functions: AgentPMState → AgentPMState.
All nodes publish phase and event notifications to the Redis stream bus.
"""
import structlog

from agents import (
    BRDGeneratorAgent,
    FRDGeneratorAgent,
    GapDetectorAgent,
    HandoffPackAgent,
    IntakeAgent,
    POReviewAgent,
    PRDGeneratorAgent,
    StoryGeneratorAgent,
)
from orchestrator.state import AgentPMState, SessionPhase
from workflows.stream_bus import (
    publish_agent_complete,
    publish_agent_start,
    publish_clarification,
    publish_gate_reached,
    publish_phase_changed,
)

log = structlog.get_logger()

GATE_TITLES = {
    1: "Scope Approval",
    2: "BRD Review",
    3: "PRD Review",
    4: "FRD Review",
    5: "Stories & Specs Review",
    6: "Release Readiness",
}


def _get_model_override(state: AgentPMState, task_type: str) -> str | None:
    return state.get("user_model_overrides", {}).get(task_type)


def _update_costs(state: AgentPMState, result: dict) -> dict:
    cost = result.get("cost_usd", 0.0)
    agent = result.get("agent", "unknown")
    cost_by_agent = {
        **state.get("cost_by_agent", {}),
        agent: state.get("cost_by_agent", {}).get(agent, 0.0) + cost,
    }
    return {
        "total_cost_usd": state.get("total_cost_usd", 0.0) + cost,
        "cost_by_agent": cost_by_agent,
    }


async def run_intake(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.DISCOVERY)

    agent = IntakeAgent()
    result = await agent.run(
        context={
            "user_input": state.get("raw_user_input", ""),
            "history": state.get("messages", []),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "intake_conversation"),
    )
    intake_output = result.get("output", {})
    return {
        **state,
        "intake_output": intake_output,
        "confirmed_facts": {k: v for k, v in intake_output.items() if k not in ["open_questions", "assumptions"]},
        "assumptions": intake_output.get("assumptions", []),
        "current_phase": SessionPhase.DISCOVERY,
        **_update_costs(state, result),
    }


async def run_gap_detection(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    agent = GapDetectorAgent()
    result = await agent.run(
        context={
            "current_stage": state.get("current_phase", "discovery"),
            "confirmed_facts": state.get("confirmed_facts", {}),
            "assumptions": state.get("assumptions", []),
            "decisions": state.get("decisions", []),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "gap_detection"),
    )
    gap_report = result.get("output", {})

    # Notify frontend if clarification is needed
    if not gap_report.get("can_proceed") and gap_report.get("recommended_questions"):
        await publish_clarification(session_id, gap_report["recommended_questions"])

    return {
        **state,
        "gap_report": gap_report,
        "pending_questions": gap_report.get("recommended_questions", []),
        **_update_costs(state, result),
    }


async def generate_brd(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.BRD)

    agent = BRDGeneratorAgent()
    result = await agent.run(
        context={
            "intake_output": state.get("intake_output", {}),
            "approved_decisions": state.get("decisions", []),
            "assumptions": state.get("assumptions", []),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "brd_generation"),
    )
    return {**state, "brd": result.get("output", {}), "current_phase": SessionPhase.BRD, **_update_costs(state, result)}


async def generate_prd(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.PRD)

    agent = PRDGeneratorAgent()
    result = await agent.run(
        context={
            "approved_brd": state.get("brd", {}),
            "intake_output": state.get("intake_output", {}),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "prd_generation"),
    )
    return {**state, "prd": result.get("output", {}), "current_phase": SessionPhase.PRD, **_update_costs(state, result)}


async def generate_frd(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.FRD)

    agent = FRDGeneratorAgent()
    result = await agent.run(
        context={
            "approved_prd": state.get("prd", {}),
            "approved_brd": state.get("brd", {}),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "frd_generation"),
    )
    return {**state, "frd": result.get("output", {}), "current_phase": SessionPhase.FRD, **_update_costs(state, result)}


async def generate_stories_and_specs(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.STORIES_SPECS)

    agent = StoryGeneratorAgent()
    result = await agent.run(
        context={
            "approved_frd": state.get("frd", {}),
            "approved_prd": state.get("prd", {}),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "story_generation"),
    )
    return {
        **state,
        "stories": result.get("output", {}),
        "current_phase": SessionPhase.STORIES_SPECS,
        **_update_costs(state, result),
    }


async def run_po_review(state: AgentPMState, artifact_type: str) -> AgentPMState:
    session_id = state["session_id"]
    agent = POReviewAgent()

    artifact_map = {
        "BRD": state.get("brd", {}),
        "PRD": state.get("prd", {}),
        "FRD": state.get("frd", {}),
        "STORIES": state.get("stories", {}),
        "DEVELOPER_HANDOFF": state.get("handoff_pack", {}),
    }
    prior_map = {
        "PRD": {"brd": state.get("brd", {})},
        "FRD": {"brd": state.get("brd", {}), "prd": state.get("prd", {})},
        "STORIES": {"frd": state.get("frd", {}), "prd": state.get("prd", {})},
    }

    result = await agent.run(
        context={
            "artifact_type": artifact_type,
            "artifact_content": artifact_map.get(artifact_type, {}),
            "prior_artifacts": prior_map.get(artifact_type, {}),
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "po_review"),
    )

    updated_review_packs = {**state.get("review_packs", {}), artifact_type: result.get("output", {})}
    return {**state, "review_packs": updated_review_packs, **_update_costs(state, result)}


async def notify_gate(state: AgentPMState, gate_number: int) -> AgentPMState:
    """Publish a gate_reached event so the frontend can show the approval panel."""
    await publish_gate_reached(
        state["session_id"],
        gate_number,
        GATE_TITLES.get(gate_number, f"Gate {gate_number}"),
    )
    return state


async def assemble_handoff(state: AgentPMState) -> AgentPMState:
    session_id = state["session_id"]
    await publish_phase_changed(session_id, SessionPhase.HANDOFF)

    agent = HandoffPackAgent()
    result = await agent.run(
        context={
            "approved_artifacts": {
                "brd": state.get("brd", {}),
                "prd": state.get("prd", {}),
                "frd": state.get("frd", {}),
                "stories": state.get("stories", {}),
                "screen_specs": state.get("screen_specs", {}),
                "review_packs": state.get("review_packs", {}),
            }
        },
        session_id=session_id,
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "handoff_assembly"),
    )
    return {
        **state,
        "handoff_pack": result.get("output", {}).get("handoff_pack", {}),
        "current_phase": SessionPhase.HANDOFF,
        **_update_costs(state, result),
    }
