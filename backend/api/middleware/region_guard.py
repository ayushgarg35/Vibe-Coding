"""
Region Guard Middleware — enforces data residency for GDPR and DPDPA.
Detects user's region from request headers/token and tags the request context.
LLM routing policy uses this to enforce compliant provider selection.
"""
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger()

REGION_HEADER = "X-Data-Region"
VALID_REGIONS = {"US", "EU", "IN"}


class RegionGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        region = request.headers.get(REGION_HEADER, "US").upper()

        if region not in VALID_REGIONS:
            log.warning("Invalid data region in request", region=region, path=request.url.path)
            region = "US"

        # Attach region to request state for use in route handlers
        request.state.data_region = region

        with structlog.contextvars.bound_contextvars(data_region=region):
            response = await call_next(request)

        response.headers[REGION_HEADER] = region
        return response
