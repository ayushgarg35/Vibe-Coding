"""
Base Agent — all specialist agents extend this.
Enforces the contract: task_type, prompt template, structured output schema.
Publishes streaming tokens to Redis SSE bus during stream calls.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator

import structlog
import yaml

from adapters.base import ModelRequest, ModelResponse
from adapters.litellm_adapter import LiteLLMAdapter

log = structlog.get_logger()


class BaseAgent(ABC):
    task_type: str           # must match routing_policy.yaml key
    prompt_template_path: str

    def __init__(self, adapter: LiteLLMAdapter | None = None):
        self._adapter = adapter or LiteLLMAdapter()
        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> dict:
        path = Path("prompts") / self.prompt_template_path
        if not path.exists():
            log.warning("Prompt template not found", path=str(path))
            return {}
        with open(path) as f:
            return yaml.safe_load(f)

    def _build_system_prompt(self, context: dict) -> str:
        template = self._prompt_template.get("system_prompt", "")
        try:
            return template.format(**context) if context else template
        except KeyError:
            return template

    def _build_user_message(self, context: dict) -> str:
        template = self._prompt_template.get("user_message", "")
        try:
            return template.format(**context) if context else template
        except KeyError:
            return template

    @abstractmethod
    async def run(
        self,
        context: dict,
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> dict:
        """
        Execute the agent's primary task.
        Returns a structured dict — always include:
          - output: the primary artifact or result
          - agent: self.task_type
          - model_used: which model was selected
          - cost_usd: cost of this call
        """
        ...

    async def _call_model(
        self,
        messages: list[dict],
        context: dict,
        response_schema: dict | None = None,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> ModelResponse:
        request = ModelRequest(
            task_type=self.task_type,
            messages=messages,
            response_schema=response_schema,
            data_region=data_region,
            user_model_override=user_model_override,
        )
        return await self._adapter.complete(request)

    async def _stream_to_bus(
        self,
        messages: list[dict],
        session_id: str,
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> str:
        """
        Stream model output token-by-token, publishing each token to the Redis bus.
        Returns the full assembled content string.
        Used for agents where the user watches the output being written live.
        """
        from workflows.stream_bus import publish_agent_complete, publish_agent_start, publish_token

        request = ModelRequest(
            task_type=self.task_type,
            messages=messages,
            data_region=data_region,
            user_model_override=user_model_override,
        )

        # Resolve which model will be used (for display in UI)
        model_id = user_model_override or self.task_type  # bus shows task_type if no override

        await publish_agent_start(session_id, self.task_type, model=model_id)

        full_content = ""
        async for token in self._adapter.stream(request):
            full_content += token
            await publish_token(session_id, self.task_type, token, model=model_id)

        await publish_agent_complete(session_id, self.task_type)
        return full_content

    async def _stream_model(
        self,
        messages: list[dict],
        data_region: str = "US",
        user_model_override: str | None = None,
    ) -> AsyncIterator[str]:
        """Raw streaming iterator — use when caller handles publishing."""
        request = ModelRequest(
            task_type=self.task_type,
            messages=messages,
            data_region=data_region,
            user_model_override=user_model_override,
        )
        async for chunk in self._adapter.stream(request):
            yield chunk
