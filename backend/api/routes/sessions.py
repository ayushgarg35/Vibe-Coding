"""
Session Routes — create, list, get, and stream sessions.
Sessions are the top-level container for a product's artifact pipeline.
"""
import uuid
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from orchestrator import AgentPMState, SessionPhase, get_compiled_graph
from storage.database import get_db

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class CreateSessionRequest(BaseModel):
    product_description: str
    entry_mode: str = "freeform"  # freeform | upload | template
    data_region: str = "US"       # US | EU | IN
    model_overrides: dict = {}    # task_type → model_id


class SessionResponse(BaseModel):
    session_id: str
    current_phase: str
    status: str
    pending_questions: list
    cost_usd: float


@router.post("/", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new product session.
    Runs intake + gap detection, then pauses at first clarification point or Gate 1.
    """
    session_id = str(uuid.uuid4())

    # TODO: Extract org_id and user_id from Clerk auth token
    org_id = "00000000-0000-0000-0000-000000000000"
    user_id = "00000000-0000-0000-0000-000000000001"

    initial_state: AgentPMState = {
        "session_id": session_id,
        "org_id": org_id,
        "user_id": user_id,
        "data_region": request.data_region,
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
        "brd": {},
        "prd": {},
        "frd": {},
        "stories": {},
        "screen_specs": {},
        "review_packs": {},
        "gate_1_status": "pending",
        "gate_2_status": "pending",
        "gate_3_status": "pending",
        "gate_4_status": "pending",
        "gate_5_status": "pending",
        "gate_6_status": "pending",
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

    return SessionResponse(
        session_id=session_id,
        current_phase=result.get("current_phase", SessionPhase.DISCOVERY),
        status="awaiting_input",
        pending_questions=result.get("pending_questions", []),
        cost_usd=result.get("total_cost_usd", 0.0),
    )


@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get current session state."""
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state.values


@router.post("/{session_id}/answer")
async def submit_clarification_answers(
    session_id: str,
    answers: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit answers to pending clarification questions.
    Resumes the graph from the await_clarification interrupt.
    """
    graph = await get_compiled_graph(settings.DATABASE_URL)
    config = {"configurable": {"thread_id": session_id}}

    result = await graph.ainvoke(
        {"type": "clarification_answers", "answers": answers},
        config=config,
    )

    return {
        "session_id": session_id,
        "current_phase": result.get("current_phase"),
        "pending_questions": result.get("pending_questions", []),
        "gap_report": result.get("gap_report", {}),
    }


@router.get("/{session_id}/stream")
async def stream_session(session_id: str):
    """
    SSE endpoint — streams agent output tokens to the frontend in real time.
    Frontend subscribes to this when a session is active.
    """
    async def event_generator() -> AsyncIterator[str]:
        # TODO: Subscribe to Redis pub/sub channel for this session_id
        # and yield SSE events as agents produce output
        yield f"data: {{\"type\": \"connected\", \"session_id\": \"{session_id}\"}}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
