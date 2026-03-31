"""
Collaboration WebSocket routes.
Clients connect here to co-edit artifacts in real time using Yjs.
"""
import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketException, status

from api.auth import get_current_user
from config.settings import get_settings
from workflows.collab_server import get_room_presence, handle_collab_connection

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()

VALID_ARTIFACT_TYPES = {"BRD", "PRD", "FRD", "STORIES", "SCREEN_SPECS", "DEVELOPER_HANDOFF"}


@router.websocket("/{session_id}/{artifact_type}")
async def collab_websocket(
    websocket: WebSocket,
    session_id: str,
    artifact_type: str,
):
    """
    WebSocket endpoint for real-time artifact collaboration.
    URL: ws://host/api/v1/collab/{session_id}/{artifact_type}

    Protocol: Yjs binary sync (y-websocket compatible).
    Awareness updates (cursors, presence) are sent as JSON text frames.

    Auth: Clerk token passed as query param ?token=... (WS can't set headers).
    """
    if artifact_type.upper() not in VALID_ARTIFACT_TYPES:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Extract token from query params (WebSocket clients can't set Authorization headers)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate token manually (can't use Depends on WebSocket)
    try:
        from api.auth import _verify_clerk_token
        claims = await _verify_clerk_token(token)
        user_id = claims.get("sub", "unknown")
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await handle_collab_connection(
        websocket=websocket,
        session_id=session_id,
        artifact_type=artifact_type.upper(),
        user_id=user_id,
    )


@router.get("/{session_id}/{artifact_type}/presence")
async def get_presence(
    session_id: str,
    artifact_type: str,
    user=Depends(get_current_user),
):
    """Return the number of users currently editing this artifact."""
    count = await get_room_presence(session_id, artifact_type.upper())
    return {"session_id": session_id, "artifact_type": artifact_type, "active_editors": count}
