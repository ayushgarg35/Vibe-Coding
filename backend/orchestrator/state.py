"""
LangGraph Session State — the single source of truth passed between all nodes.
Everything the orchestrator knows lives here.
"""
from enum import Enum
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SessionPhase(str, Enum):
    DISCOVERY = "discovery"
    GATE_1_SCOPE = "gate_1_scope"
    BRD = "brd"
    GATE_2_BRD = "gate_2_brd"
    PRD = "prd"
    GATE_3_PRD = "gate_3_prd"
    FRD = "frd"
    GATE_4_FRD = "gate_4_frd"
    STORIES_SPECS = "stories_specs"
    GATE_5_STORIES = "gate_5_stories"
    HANDOFF = "handoff"
    GATE_6_RELEASE = "gate_6_release"
    COMPLETE = "complete"
    PAUSED = "paused"
    ERROR = "error"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


class AgentPMState(TypedDict):
    # ── Session metadata ──────────────────────────────────────────
    session_id: str
    org_id: str
    user_id: str
    data_region: str                  # US | EU | IN — drives LLM routing
    current_phase: SessionPhase
    entry_mode: str                   # freeform | upload | template

    # ── Conversation ──────────────────────────────────────────────
    messages: Annotated[list, add_messages]   # full conversation history
    pending_questions: list[dict]             # questions awaiting user response
    clarification_rounds: int                 # counter — stops at MAX_CLARIFICATION_ROUNDS

    # ── Intake & discovery ────────────────────────────────────────
    raw_user_input: str
    intake_output: dict               # structured output from IntakeAgent
    confirmed_facts: dict
    assumptions: list[dict]
    decisions: list[dict]             # decision ledger
    gap_report: dict                  # latest GapDetectorAgent output

    # ── Artifacts (versioned) ─────────────────────────────────────
    brd: dict
    prd: dict
    frd: dict
    stories: dict
    screen_specs: dict
    review_packs: dict                # keyed by artifact_type

    # ── Approval states ───────────────────────────────────────────
    gate_1_status: ApprovalStatus
    gate_2_status: ApprovalStatus
    gate_3_status: ApprovalStatus
    gate_4_status: ApprovalStatus
    gate_5_status: ApprovalStatus
    gate_6_status: ApprovalStatus

    # ── Approval metadata ─────────────────────────────────────────
    gate_comments: dict               # keyed by gate number, stores redlines/comments
    approver_id: str | None

    # ── Model configuration ───────────────────────────────────────
    user_model_overrides: dict        # task_type → model_id — set by inline picker

    # ── Cost tracking ─────────────────────────────────────────────
    total_cost_usd: float
    cost_by_agent: dict

    # ── Error / retry ─────────────────────────────────────────────
    error: str | None
    retry_count: int
