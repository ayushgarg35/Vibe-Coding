"""
LangGraph Orchestration Graph — the central workflow engine.
Defines all nodes, edges, and conditional routing between agents.
Human approval gates are implemented as interrupt() calls — execution pauses
until a human resumes the graph with an approval decision.
"""
import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from config.settings import get_settings
from orchestrator.nodes import (
    assemble_handoff,
    generate_brd,
    generate_frd,
    generate_prd,
    generate_stories_and_specs,
    run_gap_detection,
    run_intake,
    run_po_review,
)
from orchestrator.state import AgentPMState, ApprovalStatus, SessionPhase

log = structlog.get_logger()
settings = get_settings()


# ── Conditional routing functions ─────────────────────────────────

def route_after_gap_detection(state: AgentPMState) -> str:
    gap_report = state.get("gap_report", {})
    can_proceed = gap_report.get("can_proceed", False)
    rounds = state.get("clarification_rounds", 0)

    if not can_proceed and rounds < settings.MAX_CLARIFICATION_ROUNDS:
        return "await_clarification"
    return "gate_1_scope"


def route_after_gate_1(state: AgentPMState) -> str:
    status = state.get("gate_1_status")
    if status == ApprovalStatus.APPROVED:
        return "generate_brd"
    if status == ApprovalStatus.REVISION_REQUESTED:
        return "run_intake"  # loop back with user feedback
    return END  # rejected


def route_after_gate_2(state: AgentPMState) -> str:
    status = state.get("gate_2_status")
    review = state.get("review_packs", {}).get("BRD", {})
    if status == ApprovalStatus.APPROVED and review.get("verdict") != "HOLD":
        return "generate_prd"
    if status == ApprovalStatus.REVISION_REQUESTED:
        return "generate_brd"
    return END


def route_after_gate_3(state: AgentPMState) -> str:
    status = state.get("gate_3_status")
    if status == ApprovalStatus.APPROVED:
        return "generate_frd"
    if status == ApprovalStatus.REVISION_REQUESTED:
        return "generate_prd"
    return END


def route_after_gate_4(state: AgentPMState) -> str:
    status = state.get("gate_4_status")
    if status == ApprovalStatus.APPROVED:
        return "generate_stories_and_specs"
    if status == ApprovalStatus.REVISION_REQUESTED:
        return "generate_frd"
    return END


def route_after_gate_5(state: AgentPMState) -> str:
    status = state.get("gate_5_status")
    if status == ApprovalStatus.APPROVED:
        return "assemble_handoff"
    if status == ApprovalStatus.REVISION_REQUESTED:
        return "generate_stories_and_specs"
    return END


def route_after_gate_6(state: AgentPMState) -> str:
    status = state.get("gate_6_status")
    if status == ApprovalStatus.APPROVED:
        return END
    return "assemble_handoff"


# ── Gate nodes (human interrupts) ────────────────────────────────

def gate_1_scope(state: AgentPMState) -> AgentPMState:
    """
    Pause execution. Present scope summary to human for approval.
    Resumes when human calls /api/v1/approvals/{session_id}/gate/1
    """
    decision = interrupt({
        "gate": 1,
        "title": "Scope Approval",
        "description": "Review confirmed scope, assumptions, and open items before BRD generation.",
        "confirmed_facts": state.get("confirmed_facts"),
        "assumptions": state.get("assumptions"),
        "gap_report": state.get("gap_report"),
    })
    return {**state, "gate_1_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "1": decision.get("comments", "")}}


def gate_2_brd(state: AgentPMState) -> AgentPMState:
    decision = interrupt({
        "gate": 2,
        "title": "BRD Approval",
        "artifact": state.get("brd"),
        "review_pack": state.get("review_packs", {}).get("BRD"),
    })
    return {**state, "gate_2_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "2": decision.get("comments", "")}}


def gate_3_prd(state: AgentPMState) -> AgentPMState:
    decision = interrupt({
        "gate": 3,
        "title": "PRD Approval",
        "artifact": state.get("prd"),
        "review_pack": state.get("review_packs", {}).get("PRD"),
    })
    return {**state, "gate_3_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "3": decision.get("comments", "")}}


def gate_4_frd(state: AgentPMState) -> AgentPMState:
    decision = interrupt({
        "gate": 4,
        "title": "FRD Approval",
        "artifact": state.get("frd"),
        "review_pack": state.get("review_packs", {}).get("FRD"),
    })
    return {**state, "gate_4_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "4": decision.get("comments", "")}}


def gate_5_stories(state: AgentPMState) -> AgentPMState:
    decision = interrupt({
        "gate": 5,
        "title": "Stories & Specs Approval",
        "artifact": state.get("stories"),
        "review_pack": state.get("review_packs", {}).get("STORIES"),
    })
    return {**state, "gate_5_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "5": decision.get("comments", "")}}


def gate_6_release(state: AgentPMState) -> AgentPMState:
    decision = interrupt({
        "gate": 6,
        "title": "Release Readiness Review",
        "description": "Final sign-off before developer handoff package is published.",
        "review_pack": state.get("review_packs", {}).get("DEVELOPER_HANDOFF"),
    })
    return {**state, "gate_6_status": decision["status"], "gate_comments": {**state.get("gate_comments", {}), "6": decision.get("comments", "")}}


def await_clarification(state: AgentPMState) -> AgentPMState:
    """Pause to surface questions to user. Resumes when user submits answers."""
    questions = state.get("gap_report", {}).get("recommended_questions", [])
    answers = interrupt({
        "type": "clarification",
        "questions": questions,
        "clarification_round": state.get("clarification_rounds", 0) + 1,
    })
    updated_messages = state.get("messages", []) + [
        {"role": "user", "content": str(answers)}
    ]
    return {
        **state,
        "messages": updated_messages,
        "clarification_rounds": state.get("clarification_rounds", 0) + 1,
    }


# ── Build the graph ───────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(AgentPMState)

    # Agent nodes
    builder.add_node("run_intake", run_intake)
    builder.add_node("run_gap_detection", run_gap_detection)
    builder.add_node("await_clarification", await_clarification)
    builder.add_node("gate_1_scope", gate_1_scope)
    builder.add_node("generate_brd", generate_brd)
    builder.add_node("run_po_review_brd", lambda s: run_po_review(s, artifact_type="BRD"))
    builder.add_node("gate_2_brd", gate_2_brd)
    builder.add_node("generate_prd", generate_prd)
    builder.add_node("run_po_review_prd", lambda s: run_po_review(s, artifact_type="PRD"))
    builder.add_node("gate_3_prd", gate_3_prd)
    builder.add_node("generate_frd", generate_frd)
    builder.add_node("run_po_review_frd", lambda s: run_po_review(s, artifact_type="FRD"))
    builder.add_node("gate_4_frd", gate_4_frd)
    builder.add_node("generate_stories_and_specs", generate_stories_and_specs)
    builder.add_node("run_po_review_stories", lambda s: run_po_review(s, artifact_type="STORIES"))
    builder.add_node("gate_5_stories", gate_5_stories)
    builder.add_node("assemble_handoff", assemble_handoff)
    builder.add_node("run_po_review_handoff", lambda s: run_po_review(s, artifact_type="DEVELOPER_HANDOFF"))
    builder.add_node("gate_6_release", gate_6_release)

    # Edges
    builder.add_edge(START, "run_intake")
    builder.add_edge("run_intake", "run_gap_detection")
    builder.add_conditional_edges("run_gap_detection", route_after_gap_detection, {
        "await_clarification": "await_clarification",
        "gate_1_scope": "gate_1_scope",
    })
    builder.add_edge("await_clarification", "run_intake")  # re-process with new answers

    builder.add_conditional_edges("gate_1_scope", route_after_gate_1, {
        "generate_brd": "generate_brd",
        "run_intake": "run_intake",
        END: END,
    })

    builder.add_edge("generate_brd", "run_po_review_brd")
    builder.add_edge("run_po_review_brd", "gate_2_brd")
    builder.add_conditional_edges("gate_2_brd", route_after_gate_2, {
        "generate_prd": "generate_prd",
        "generate_brd": "generate_brd",
        END: END,
    })

    builder.add_edge("generate_prd", "run_po_review_prd")
    builder.add_edge("run_po_review_prd", "gate_3_prd")
    builder.add_conditional_edges("gate_3_prd", route_after_gate_3, {
        "generate_frd": "generate_frd",
        "generate_prd": "generate_prd",
        END: END,
    })

    builder.add_edge("generate_frd", "run_po_review_frd")
    builder.add_edge("run_po_review_frd", "gate_4_frd")
    builder.add_conditional_edges("gate_4_frd", route_after_gate_4, {
        "generate_stories_and_specs": "generate_stories_and_specs",
        "generate_frd": "generate_frd",
        END: END,
    })

    builder.add_edge("generate_stories_and_specs", "run_po_review_stories")
    builder.add_edge("run_po_review_stories", "gate_5_stories")
    builder.add_conditional_edges("gate_5_stories", route_after_gate_5, {
        "assemble_handoff": "assemble_handoff",
        "generate_stories_and_specs": "generate_stories_and_specs",
        END: END,
    })

    builder.add_edge("assemble_handoff", "run_po_review_handoff")
    builder.add_edge("run_po_review_handoff", "gate_6_release")
    builder.add_conditional_edges("gate_6_release", route_after_gate_6, {
        END: END,
        "assemble_handoff": "assemble_handoff",
    })

    return builder


async def get_compiled_graph(db_url: str):
    """Returns the compiled graph with PostgreSQL checkpointing for persistence."""
    checkpointer = await AsyncPostgresSaver.from_conn_string(db_url)
    await checkpointer.setup()
    graph = build_graph().compile(checkpointer=checkpointer, interrupt_before=[
        "gate_1_scope", "gate_2_brd", "gate_3_prd",
        "gate_4_frd", "gate_5_stories", "gate_6_release",
        "await_clarification",
    ])
    return graph
