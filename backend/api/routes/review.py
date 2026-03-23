"""
Review Routes — trigger PO review on any uploaded or existing artifact.
Supports both session-bound review (within pipeline) and standalone review mode.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents import POReviewAgent
from config.settings import get_settings
from storage.database import get_db

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class StandaloneReviewRequest(BaseModel):
    artifact_type: str       # BRD | PRD | FRD | STORY | HANDOFF
    artifact_content: dict   # the artifact JSON to review
    prior_artifacts: dict = {}  # optional — for consistency checks
    data_region: str = "US"
    model_override: str | None = None


@router.post("/standalone")
async def standalone_review(
    request: StandaloneReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Review an artifact outside of an active session pipeline.
    Entry point for POs who receive documents from external teams.
    """
    agent = POReviewAgent()
    result = await agent.run(
        context={
            "artifact_type": request.artifact_type,
            "artifact_content": request.artifact_content,
            "prior_artifacts": request.prior_artifacts,
        },
        session_id="standalone",
        data_region=request.data_region,
        user_model_override=request.model_override,
    )

    return {
        "artifact_type": request.artifact_type,
        "review_pack": result.get("output", {}),
        "model_used": result.get("model_used"),
        "cost_usd": result.get("cost_usd", 0.0),
    }


@router.get("/{session_id}/{artifact_type}")
async def get_session_review(
    session_id: str,
    artifact_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the review pack for a specific artifact in an active session."""
    from config.settings import get_settings
    from orchestrator import get_compiled_graph

    graph = await get_compiled_graph(get_settings().DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    review_pack = state.values.get("review_packs", {}).get(artifact_type.upper())
    if not review_pack:
        raise HTTPException(status_code=404, detail=f"No review pack for {artifact_type}")

    return {"session_id": session_id, "artifact_type": artifact_type, "review_pack": review_pack}
