"""
Audit Log Middleware — logs every request/response for SOC2, GDPR, DPDPA compliance.
All sensitive operations are traceable to user + session + timestamp.
"""
import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import get_settings

log = structlog.get_logger()
settings = get_settings()

# Paths that don't need audit logging
SKIP_PATHS = {"/health", "/metrics", "/api/docs", "/api/redoc", "/openapi.json"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in SKIP_PATHS or not settings.AUDIT_LOG_ENABLED:
            return await call_next(request)

        start = time.perf_counter()
        request_id = str(uuid.uuid4())

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            log.info(
                "api_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                # TODO: Extract user_id from Clerk JWT and add here
            )

            # TODO: Write to audit_log table for durable compliance record
            # await write_audit_record(request, response, duration_ms, request_id)

        return response
