"""
LiteLLM Adapter — unified interface to 100+ LLM providers.
Handles routing policy, region constraints, retries, and cost tracking.
"""
import json
from typing import AsyncIterator

import litellm
import structlog
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

from adapters.base import BaseModelAdapter, ModelRequest, ModelResponse
from adapters.pii_guard import PIIGuard
from config.settings import get_settings

log = structlog.get_logger()
settings = get_settings()


def _load_routing_policy() -> dict:
    with open("config/routing_policy.yaml") as f:
        return yaml.safe_load(f)


ROUTING_POLICY = _load_routing_policy()


class LiteLLMAdapter(BaseModelAdapter):
    """
    Primary adapter for all LLM calls.
    Selects model based on:
      1. User override (inline model picker)
      2. Task-type routing policy
      3. Data region constraints
    Applies PII guard before every call when enabled.
    """

    def __init__(self):
        self._pii_guard = PIIGuard() if settings.PII_DETECTION_ENABLED else None
        litellm.set_verbose = False
        litellm.drop_params = True  # silently drop unsupported params per model

    def _resolve_model(self, request: ModelRequest) -> str:
        """
        Priority: user override → policy primary → region fallback → global fallback.
        """
        if request.user_model_override:
            self._validate_region_constraint(request.user_model_override, request.data_region)
            return request.user_model_override

        task_config = ROUTING_POLICY["task_routing"].get(request.task_type)
        if not task_config:
            log.warning("No routing policy for task", task_type=request.task_type)
            return ROUTING_POLICY["defaults"]["fallback_model"]

        primary = task_config["primary"]
        fallback = task_config.get("fallback", ROUTING_POLICY["defaults"]["fallback_model"])

        region_constraints = ROUTING_POLICY["region_constraints"].get(request.data_region, {})
        denied = region_constraints.get("denied_providers", [])

        primary_provider = primary.split("/")[0] if "/" in primary else self._infer_provider(primary)
        if primary_provider in denied:
            log.info(
                "Primary model denied by region policy — using fallback",
                primary=primary,
                region=request.data_region,
                fallback=fallback,
            )
            return fallback

        return primary

    def _infer_provider(self, model: str) -> str:
        if model.startswith("claude"):
            return "anthropic"
        if model.startswith("gpt"):
            return "openai"
        if model.startswith("gemini"):
            return "google"
        return "unknown"

    def _validate_region_constraint(self, model: str, region: str) -> None:
        region_constraints = ROUTING_POLICY["region_constraints"].get(region, {})
        denied = region_constraints.get("denied_providers", [])
        provider = self._infer_provider(model)
        if provider in denied:
            raise ValueError(
                f"Model '{model}' uses provider '{provider}' which is denied "
                f"for region '{region}'. Choose a compliant model."
            )

    def _sanitize_messages(self, messages: list[dict]) -> list[dict]:
        if not self._pii_guard:
            return messages
        return [
            {**msg, "content": self._pii_guard.anonymize(msg.get("content", ""))}
            for msg in messages
        ]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def complete(self, request: ModelRequest) -> ModelResponse:
        model = self._resolve_model(request)
        messages = self._sanitize_messages(request.messages)

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.response_schema and self.supports_structured_output():
            kwargs["response_format"] = {"type": "json_object"}

        log.info("LLM call", model=model, task=request.task_type, region=request.data_region)

        response = await litellm.acompletion(**kwargs)

        content = response.choices[0].message.content or ""
        structured = None
        if request.response_schema:
            try:
                structured = json.loads(content)
            except json.JSONDecodeError:
                log.warning("Structured output parse failed", model=model)

        cost = litellm.completion_cost(completion_response=response)

        return ModelResponse(
            content=content,
            model_used=model,
            provider=self._infer_provider(model),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            cost_usd=cost,
            task_type=request.task_type,
            structured=structured,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        messages = self._sanitize_messages(request.messages)

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def supports_structured_output(self) -> bool:
        return True

    def available_models(self) -> list[str]:
        # TODO: Fetch dynamically from provider APIs for model picker UI
        return [
            "claude-opus-4",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]
