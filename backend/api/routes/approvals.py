"""
Approval Gate Routes — human decisions that resume the LangGraph workflow.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import AuthContext, get_current_user
from config.settings import get_settings
from orchestrator import ApprovalStatus, get_compiled_graph
from storage.database import get_db
from storage.repositories import ApprovalGateRepository, SessionRepository

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class ApprovalDecision(BaseModel):
    status: ApprovalStatus
    comments: str = ""
    redlines: list[dict] = []
    model_overrides: dict = {}


@router.post("/{session_id}/gate/{gate_number}")
async def submit_gate_decision(
    session_id: str,
    gate_number: int,
    decision: ApprovalDecision,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a human gate decision. Resumes the paused graph.
    Gate 1=Scope, 2=BRD, 3=PRD, 4=FRD, 5=Stories, 6=Release.
    """
    if gate_number not in range(1, 7):
        raise HTTPException(status_code=400, detail="Gate number must be 1-6")

    # Persist the decision
    approval_repo = ApprovalGateRepository(db)
    await approval_repo.submit_decision(
        session_id=session_id,
        gate_number=gate_number,
        status=decision.status.value,
        reviewer_id=user.user_id,
        comments=decision.comments,
        redlines={"items": decision.redlines} if decision.redlines else None,
        org_id=user.org_id,
    )

    # Resume graph
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}

    # Apply any model overrides the user set before approving
    resume_payload = {
        "status": decision.status.value,
        "comments": decision.comments,
        "redlines": decision.redlines,
    }
    if decision.model_overrides:
        # Merge new overrides into graph state
        state = await graph.aget_state(config)
        existing_overrides = state.values.get("user_model_overrides", {}) if state else {}
        resume_payload["user_model_overrides"] = {**existing_overrides, **decision.model_overrides}

    result = await graph.ainvoke(resume_payload, config=config)

    # Update session phase in DB
    session_repo = SessionRepository(db)
    await session_repo.update_phase(session_id, result.get("current_phase", ""))

    log.info(
        "Gate decision submitted",
        session_id=session_id,
        gate=gate_number,
        status=decision.status,
        reviewer=user.user_id,
    )

    return {
        "session_id": session_id,
        "gate": gate_number,
        "decision": decision.status,
        "current_phase": result.get("current_phase"),
        "next_artifact": _next_artifact_label(gate_number, decision.status),
        "pending_questions": result.get("pending_questions", []),
    }


@router.get("/{session_id}/gate/{gate_number}/review-pack")
async def get_gate_review_pack(
    session_id: str,
    gate_number: int,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the auto-generated PO review pack attached to a gate."""
    artifact_map = {2: "BRD", 3: "PRD", 4: "FRD", 5: "STORIES", 6: "DEVELOPER_HANDOFF"}

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    artifact_type = artifact_map.get(gate_number)
    review_pack = state.values.get("review_packs", {}).get(artifact_type)
    if not review_pack:
        raise HTTPException(status_code=404, detail=f"No review pack for gate {gate_number}")

    return {"gate": gate_number, "artifact_type": artifact_type, "review_pack": review_pack}


@router.get("/{session_id}/gates")
async def get_all_gates(
    session_id: str,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of all 6 approval gates for a session."""
    approval_repo = ApprovalGateRepository(db)
    gates = await approval_repo.get_all_for_session(session_id)
    return {
        "session_id": session_id,
        "gates": [
            {
                "gate_number": g.gate_number,
                "status": g.status,
                "reviewer_id": str(g.reviewer_id) if g.reviewer_id else None,
                "reviewed_at": g.reviewed_at.isoformat() if g.reviewed_at else None,
                "comments": g.comments,
            }
            for g in gates
        ],
    }


def _next_artifact_label(gate: int, status: ApprovalStatus) -> str:
    if status == ApprovalStatus.APPROVED:
        return {1: "BRD", 2: "PRD", 3: "FRD", 4: "Stories & Specs", 5: "Developer Handoff", 6: "Complete"}.get(gate, "")
    if status == ApprovalStatus.REVISION_REQUESTED:
        return {1: "Discovery revision", 2: "BRD revision", 3: "PRD revision", 4: "FRD revision", 5: "Stories revision", 6: "Handoff revision"}.get(gate, "")
    return "Session closed"
