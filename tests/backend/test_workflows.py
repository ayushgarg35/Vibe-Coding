"""
Workflow integration tests — validates the full orchestration graph logic.
Run: pytest tests/backend/test_workflows.py -v
"""
import pytest

from orchestrator.state import AgentPMState, ApprovalStatus, SessionPhase
from orchestrator.graph import route_after_gap_detection, route_after_gate_1, route_after_gate_2


def make_state(**overrides) -> AgentPMState:
    base: AgentPMState = {
        "session_id": "test-session",
        "org_id": "test-org",
        "user_id": "test-user",
        "data_region": "US",
        "current_phase": SessionPhase.DISCOVERY,
        "entry_mode": "freeform",
        "messages": [],
        "pending_questions": [],
        "clarification_rounds": 0,
        "raw_user_input": "Test product",
        "intake_output": {},
        "confirmed_facts": {},
        "assumptions": [],
        "decisions": [],
        "gap_report": {},
        "brd": {},
        "prd": {},
        "frd": {},
        "stories": {},
        "screen_specs": {},
        "review_packs": {},
        "gate_1_status": ApprovalStatus.PENDING,
        "gate_2_status": ApprovalStatus.PENDING,
        "gate_3_status": ApprovalStatus.PENDING,
        "gate_4_status": ApprovalStatus.PENDING,
        "gate_5_status": ApprovalStatus.PENDING,
        "gate_6_status": ApprovalStatus.PENDING,
        "gate_comments": {},
        "approver_id": None,
        "user_model_overrides": {},
        "total_cost_usd": 0.0,
        "cost_by_agent": {},
        "error": None,
        "retry_count": 0,
    }
    return {**base, **overrides}


def test_gap_detection_routes_to_clarification_when_gaps():
    state = make_state(
        gap_report={"can_proceed": False, "blocking_gaps": ["gap-1"]},
        clarification_rounds=0,
    )
    assert route_after_gap_detection(state) == "await_clarification"


def test_gap_detection_routes_to_gate1_when_clear():
    state = make_state(
        gap_report={"can_proceed": True, "blocking_gaps": []},
        clarification_rounds=0,
    )
    assert route_after_gap_detection(state) == "gate_1_scope"


def test_gap_detection_routes_to_gate1_after_max_clarification_rounds():
    """After max rounds, proceed even if gaps remain (rather than infinite loop)."""
    state = make_state(
        gap_report={"can_proceed": False, "blocking_gaps": ["gap-1"]},
        clarification_rounds=5,  # MAX_CLARIFICATION_ROUNDS = 5
    )
    assert route_after_gap_detection(state) == "gate_1_scope"


def test_gate1_approved_routes_to_brd():
    state = make_state(gate_1_status=ApprovalStatus.APPROVED)
    assert route_after_gate_1(state) == "generate_brd"


def test_gate1_revision_routes_back_to_intake():
    state = make_state(gate_1_status=ApprovalStatus.REVISION_REQUESTED)
    assert route_after_gate_1(state) == "run_intake"


def test_gate2_approved_with_go_verdict_routes_to_prd():
    state = make_state(
        gate_2_status=ApprovalStatus.APPROVED,
        review_packs={"BRD": {"verdict": "GO"}},
    )
    assert route_after_gate_2(state) == "generate_prd"


def test_gate2_approved_with_hold_verdict_does_not_advance():
    """HOLD verdict from PO review should not advance even if human approved."""
    state = make_state(
        gate_2_status=ApprovalStatus.APPROVED,
        review_packs={"BRD": {"verdict": "HOLD"}},
    )
    # Should return END since PO review says HOLD
    from langgraph.graph import END
    assert route_after_gate_2(state) == END
