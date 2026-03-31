"""
Agentic PM System — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api.middleware.audit import AuditLogMiddleware
from api.middleware.region_guard import RegionGuardMiddleware
from api.routes import artifacts, approvals, collab, models, review, sessions
from config.settings import get_settings
from storage.database import init_db

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Agentic PM System", env=settings.APP_ENV)
    await init_db()
    yield
    log.info("Shutting down Agentic PM System")


app = FastAPI(
    title="Agentic PM System",
    description="Interactive, model-agnostic product management agent system",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
)

# ── Middleware ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RegionGuardMiddleware)

# ── Observability ─────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Routes ────────────────────────────────────────────────────────
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["Sessions"])
app.include_router(artifacts.router, prefix="/api/v1/artifacts", tags=["Artifacts"])
app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["Approvals"])
app.include_router(review.router, prefix="/api/v1/review", tags=["Review"])
app.include_router(models.router, prefix="/api/v1/models", tags=["Models"])
app.include_router(collab.router, prefix="/api/v1/collab", tags=["Collaboration"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
