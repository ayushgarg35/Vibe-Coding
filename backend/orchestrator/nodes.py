"""
LangGraph Node Implementations — each node calls the appropriate agent.
Nodes are pure functions: AgentPMState → AgentPMState.
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
from orchestrator.state import AgentPMState

log = structlog.get_logger()


def _get_model_override(state: AgentPMState, task_type: str) -> str | None:
    return state.get("user_model_overrides", {}).get(task_type)


def _update_costs(state: AgentPMState, result: dict) -> dict:
    cost = result.get("cost_usd", 0.0)
    agent = result.get("agent", "unknown")
    cost_by_agent = {**state.get("cost_by_agent", {}), agent: state.get("cost_by_agent", {}).get(agent, 0.0) + cost}
    return {"total_cost_usd": state.get("total_cost_usd", 0.0) + cost, "cost_by_agent": cost_by_agent}


async def run_intake(state: AgentPMState) -> AgentPMState:
    agent = IntakeAgent()
    result = await agent.run(
        context={
            "user_input": state.get("raw_user_input", ""),
            "history": state.get("messages", []),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "intake_conversation"),
    )
    intake_output = result.get("output", {})
    return {
        **state,
        "intake_output": intake_output,
        "confirmed_facts": {k: v for k, v in intake_output.items() if k not in ["open_questions", "assumptions"]},
        "assumptions": intake_output.get("assumptions", []),
        **_update_costs(state, result),
    }


async def run_gap_detection(state: AgentPMState) -> AgentPMState:
    agent = GapDetectorAgent()
    result = await agent.run(
        context={
            "current_stage": state.get("current_phase", "discovery"),
            "confirmed_facts": state.get("confirmed_facts", {}),
            "assumptions": state.get("assumptions", []),
            "decisions": state.get("decisions", []),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "gap_detection"),
    )
    return {
        **state,
        "gap_report": result.get("output", {}),
        "pending_questions": result.get("output", {}).get("recommended_questions", []),
        **_update_costs(state, result),
    }


async def generate_brd(state: AgentPMState) -> AgentPMState:
    agent = BRDGeneratorAgent()
    result = await agent.run(
        context={
            "intake_output": state.get("intake_output", {}),
            "approved_decisions": state.get("decisions", []),
            "assumptions": state.get("assumptions", []),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "brd_generation"),
    )
    return {**state, "brd": result.get("output", {}), **_update_costs(state, result)}


async def generate_prd(state: AgentPMState) -> AgentPMState:
    agent = PRDGeneratorAgent()
    result = await agent.run(
        context={
            "approved_brd": state.get("brd", {}),
            "intake_output": state.get("intake_output", {}),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "prd_generation"),
    )
    return {**state, "prd": result.get("output", {}), **_update_costs(state, result)}


async def generate_frd(state: AgentPMState) -> AgentPMState:
    agent = FRDGeneratorAgent()
    result = await agent.run(
        context={
            "approved_prd": state.get("prd", {}),
            "approved_brd": state.get("brd", {}),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "frd_generation"),
    )
    return {**state, "frd": result.get("output", {}), **_update_costs(state, result)}


async def generate_stories_and_specs(state: AgentPMState) -> AgentPMState:
    agent = StoryGeneratorAgent()
    result = await agent.run(
        context={
            "approved_frd": state.get("frd", {}),
            "approved_prd": state.get("prd", {}),
        },
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "story_generation"),
    )
    return {**state, "stories": result.get("output", {}), **_update_costs(state, result)}


async def run_po_review(state: AgentPMState, artifact_type: str) -> AgentPMState:
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
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "po_review"),
    )

    updated_review_packs = {**state.get("review_packs", {}), artifact_type: result.get("output", {})}
    return {**state, "review_packs": updated_review_packs, **_update_costs(state, result)}


async def assemble_handoff(state: AgentPMState) -> AgentPMState:
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
        session_id=state["session_id"],
        data_region=state.get("data_region", "US"),
        user_model_override=_get_model_override(state, "handoff_assembly"),
    )
    return {**state, "handoff_pack": result.get("output", {}).get("handoff_pack", {}), **_update_costs(state, result)}
