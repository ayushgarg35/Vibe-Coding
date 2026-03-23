"""
Model Routes — powers the inline per-task model picker in the UI.
Returns available models, routing policy, and cost estimates.
"""
import structlog
from fastapi import APIRouter

from adapters import LiteLLMAdapter

log = structlog.get_logger()
router = APIRouter()


@router.get("/available")
async def list_available_models():
    """Return all models available for user selection in the inline picker."""
    adapter = LiteLLMAdapter()
    return {
        "models": [
            {"id": "claude-opus-4", "name": "Claude Opus 4", "provider": "Anthropic", "tier": "strong", "best_for": ["po_review", "gap_detection", "orchestration"]},
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "Anthropic", "tier": "strong", "best_for": ["brd_generation", "prd_generation", "frd_generation"]},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "Anthropic", "tier": "fast", "best_for": ["matrix_generation", "retrieval"]},
            {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI", "tier": "strong", "best_for": ["general"]},
            {"id": "gpt-4o-mini", "name": "GPT-4o mini", "provider": "OpenAI", "tier": "fast", "best_for": ["formatting", "extraction"]},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "provider": "Google", "tier": "strong", "best_for": ["general"]},
        ]
    }


@router.get("/routing-policy")
async def get_routing_policy():
    """Return the current routing policy — shown in UI for transparency."""
    import yaml
    with open("config/routing_policy.yaml") as f:
        return yaml.safe_load(f)


@router.get("/region-constraints/{region}")
async def get_region_constraints(region: str):
    """Return which models are allowed for a given data region."""
    import yaml
    with open("config/routing_policy.yaml") as f:
        policy = yaml.safe_load(f)
    constraints = policy.get("region_constraints", {}).get(region.upper(), {})
    if not constraints:
        return {"region": region, "allowed_providers": ["all"], "denied_providers": []}
    return {"region": region, **constraints}
