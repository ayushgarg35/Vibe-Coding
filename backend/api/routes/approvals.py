"""
Approval Gate Routes — human approval/rejection at each stage gate.
These endpoints resume the paused LangGraph graph with the human's decision.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from orchestrator import ApprovalStatus, get_compiled_graph
from storage.database import get_db

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class ApprovalDecision(BaseModel):
    status: ApprovalStatus           # approved | revision_requested | rejected
    comments: str = ""
    redlines: list[dict] = []        # structured redline comments from UI
    model_overrides: dict = {}       # allow user to change model before next stage


@router.post("/{session_id}/gate/{gate_number}")
async def submit_gate_decision(
    session_id: str,
    gate_number: int,
    decision: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a human approval decision for a specific gate.
    Resumes the LangGraph graph with the decision payload.
    Gate numbers: 1=Scope, 2=BRD, 3=PRD, 4=FRD, 5=Stories, 6=Release
    """
    if gate_number not in range(1, 7):
        raise HTTPException(status_code=400, detail="Gate number must be 1-6")

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}

    state = await graph.aget_state(config)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    # Resume graph with human decision
    result = await graph.ainvoke(
        {
            "status": decision.status,
            "comments": decision.comments,
            "redlines": decision.redlines,
        },
        config=config,
    )

    log.info(
        "Gate decision submitted",
        session_id=session_id,
        gate=gate_number,
        status=decision.status,
    )

    return {
        "session_id": session_id,
        "gate": gate_number,
        "decision": decision.status,
        "current_phase": result.get("current_phase"),
        "next_artifact": _next_artifact(gate_number, decision.status),
    }


@router.get("/{session_id}/gate/{gate_number}/review-pack")
async def get_gate_review_pack(
    session_id: str,
    gate_number: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the auto-generated PO review pack for a specific gate."""
    artifact_map = {2: "BRD", 3: "PRD", 4: "FRD", 5: "STORIES", 6: "DEVELOPER_HANDOFF"}

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    artifact_type = artifact_map.get(gate_number)
    review_pack = state.values.get("review_packs", {}).get(artifact_type)

    if not review_pack:
        raise HTTPException(status_code=404, detail=f"No review pack found for gate {gate_number}")

    return {"gate": gate_number, "artifact_type": artifact_type, "review_pack": review_pack}


def _next_artifact(gate: int, status: ApprovalStatus) -> str:
    if status == ApprovalStatus.APPROVED:
        return {1: "BRD", 2: "PRD", 3: "FRD", 4: "Stories & Specs", 5: "Developer Handoff", 6: "Complete"}.get(gate, "")
    if status == ApprovalStatus.REVISION_REQUESTED:
        return {1: "Discovery", 2: "BRD revision", 3: "PRD revision", 4: "FRD revision", 5: "Stories revision", 6: "Handoff revision"}.get(gate, "")
    return "Session closed"
