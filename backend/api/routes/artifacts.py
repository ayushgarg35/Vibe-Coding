"""
Artifact Routes — read, export, and version artifacts.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from orchestrator import get_compiled_graph
from storage.database import get_db

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()

ARTIFACT_TYPES = ["BRD", "PRD", "FRD", "STORIES", "SCREEN_SPECS", "DEVELOPER_HANDOFF"]


@router.get("/{session_id}/{artifact_type}")
async def get_artifact(
    session_id: str,
    artifact_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest version of a specific artifact for a session."""
    if artifact_type.upper() not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type. Valid: {ARTIFACT_TYPES}")

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    artifact_map = {
        "BRD": state.values.get("brd", {}),
        "PRD": state.values.get("prd", {}),
        "FRD": state.values.get("frd", {}),
        "STORIES": state.values.get("stories", {}),
        "SCREEN_SPECS": state.values.get("screen_specs", {}),
        "DEVELOPER_HANDOFF": state.values.get("handoff_pack", {}),
    }

    artifact = artifact_map.get(artifact_type.upper())
    if not artifact:
        raise HTTPException(status_code=404, detail=f"{artifact_type} has not been generated yet")

    return {"session_id": session_id, "artifact_type": artifact_type, "content": artifact}


@router.get("/{session_id}/lineage")
async def get_artifact_lineage(session_id: str, db: AsyncSession = Depends(get_db)):
    """Return the full artifact lineage — what was derived from what."""
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    v = state.values
    lineage = {
        "intake": {"status": "completed" if v.get("intake_output") else "pending"},
        "BRD": {"status": "completed" if v.get("brd") else "pending", "derived_from": ["intake"]},
        "PRD": {"status": "completed" if v.get("prd") else "pending", "derived_from": ["BRD"]},
        "FRD": {"status": "completed" if v.get("frd") else "pending", "derived_from": ["PRD", "BRD"]},
        "STORIES": {"status": "completed" if v.get("stories") else "pending", "derived_from": ["FRD"]},
        "DEVELOPER_HANDOFF": {"status": "completed" if v.get("handoff_pack") else "pending", "derived_from": ["BRD", "PRD", "FRD", "STORIES"]},
    }
    return {"session_id": session_id, "lineage": lineage}


@router.get("/{session_id}/decisions")
async def get_decision_ledger(session_id: str, db: AsyncSession = Depends(get_db)):
    """Return the full decision ledger for a session."""
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "decisions": state.values.get("decisions", []),
        "assumptions": state.values.get("assumptions", []),
    }
