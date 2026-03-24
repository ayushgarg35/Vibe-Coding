"""
Session Routes — create, list, get, stream sessions.
All routes are authenticated via Clerk JWT.
"""
import uuid
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import AuthContext, get_current_user
from config.settings import get_settings
from orchestrator import AgentPMState, SessionPhase, get_compiled_graph
from storage.database import get_db
from storage.repositories import ArtifactRepository, DecisionRepository, SessionRepository

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class CreateSessionRequest(BaseModel):
    product_description: str
    entry_mode: str = "freeform"
    model_overrides: dict = {}


class SessionResponse(BaseModel):
    session_id: str
    current_phase: str
    status: str
    pending_questions: list
    cost_usd: float
    product_name: str | None = None


class AnswerRequest(BaseModel):
    answers: dict[str, str]


@router.post("/", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new product session.
    Runs intake + gap detection, pauses at first clarification or Gate 1.
    """
    session_repo = SessionRepository(db)
    session = await session_repo.create(
        org_id=user.org_id,
        created_by=user.user_id,
        entry_mode=request.entry_mode,
        data_region=user.data_region,
    )
    session_id = str(session.id)

    initial_state: AgentPMState = {
        "session_id": session_id,
        "org_id": user.org_id,
        "user_id": user.user_id,
        "data_region": user.data_region,
        "current_phase": SessionPhase.DISCOVERY,
        "entry_mode": request.entry_mode,
        "messages": [],
        "pending_questions": [],
        "clarification_rounds": 0,
        "raw_user_input": request.product_description,
        "intake_output": {},
        "confirmed_facts": {},
        "assumptions": [],
        "decisions": [],
        "gap_report": {},
        "brd": {}, "prd": {}, "frd": {}, "stories": {}, "screen_specs": {},
        "review_packs": {},
        "gate_1_status": "pending", "gate_2_status": "pending", "gate_3_status": "pending",
        "gate_4_status": "pending", "gate_5_status": "pending", "gate_6_status": "pending",
        "gate_comments": {},
        "approver_id": None,
        "user_model_overrides": request.model_overrides,
        "total_cost_usd": 0.0,
        "cost_by_agent": {},
        "error": None,
        "retry_count": 0,
    }

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(initial_state, config=config)

    # Persist intake output to DB
    intake_output = result.get("intake_output", {})
    product_name = intake_output.get("product_name")
    if product_name:
        await session_repo.update_product_name(session_id, product_name)

    # Persist artifacts generated so far
    artifact_repo = ArtifactRepository(db)
    decision_repo = DecisionRepository(db)

    if intake_output:
        await artifact_repo.create(
            session_id=session_id,
            artifact_type="INTAKE",
            content=intake_output,
            created_by=user.user_id,
        )

    assumptions = result.get("assumptions", [])
    if assumptions:
        await decision_repo.sync_assumptions_from_agent(session_id, assumptions)

    await session_repo.update_phase(session_id, result.get("current_phase", SessionPhase.DISCOVERY))
    await session_repo.update_cost(session_id, result.get("total_cost_usd", 0.0))

    return SessionResponse(
        session_id=session_id,
        current_phase=result.get("current_phase", SessionPhase.DISCOVERY),
        status="awaiting_input",
        pending_questions=result.get("pending_questions", []),
        cost_usd=result.get("total_cost_usd", 0.0),
        product_name=product_name,
    )


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions for the authenticated user's org."""
    session_repo = SessionRepository(db)
    sessions = await session_repo.list_for_org(user.org_id)
    return [
        SessionResponse(
            session_id=str(s.id),
            current_phase=s.current_phase,
            status=s.status,
            pending_questions=[],
            cost_usd=float(s.total_cost_usd or 0),
            product_name=s.product_name,
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current session state from graph checkpoint."""
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state or not state.values:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    v = state.values
    return SessionResponse(
        session_id=session_id,
        current_phase=v.get("current_phase", "discovery"),
        status="active",
        pending_questions=v.get("pending_questions", []),
        cost_usd=v.get("total_cost_usd", 0.0),
        product_name=v.get("intake_output", {}).get("product_name"),
    )


@router.post("/{session_id}/answer")
async def submit_clarification_answers(
    session_id: str,
    body: AnswerRequest,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit answers to pending clarification questions. Resumes the paused graph."""
    session_repo = SessionRepository(db)
    await session_repo.touch(session_id)

    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}

    result = await graph.ainvoke(
        {"type": "clarification_answers", "answers": body.answers},
        config=config,
    )

    await session_repo.update_phase(session_id, result.get("current_phase", "discovery"))

    return {
        "session_id": session_id,
        "current_phase": result.get("current_phase"),
        "pending_questions": result.get("pending_questions", []),
        "gap_report": result.get("gap_report", {}),
        "confirmed_facts": result.get("confirmed_facts", {}),
        "assumptions": result.get("assumptions", []),
    }


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """
    SSE endpoint — streams agent output to the frontend in real time.
    Frontend subscribes via EventSource when a session is active.
    """
    async def event_generator() -> AsyncIterator[str]:
        import asyncio
        import json
        # TODO: Subscribe to Redis pub/sub channel for this session
        # and yield SSE events as agents produce tokens
        yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
        # Keep-alive ping every 15s
        while True:
            await asyncio.sleep(15)
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
