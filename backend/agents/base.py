"""
Base Agent — all specialist agents extend this.
Enforces the contract: task_type, prompt template, structured output schema.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml
import structlog

from adapters.base import ModelRequest, ModelResponse
from adapters.litellm_adapter import LiteLLMAdapter

log = structlog.get_logger()


class BaseAgent(ABC):
    """
    All agents share:
    - A task_type that maps to the routing policy
    - A prompt template loaded from /prompts/
    - A structured output schema (Pydantic or JSON schema)
    - Access to the shared LiteLLM adapter
    """

    task_type: str  # must match routing_policy.yaml key
    prompt_template_path: str  # relative to /prompts/

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
        return template.format(**context) if context else template

    def _build_user_message(self, context: dict) -> str:
        template = self._prompt_template.get("user_message", "")
        return template.format(**context) if context else template

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
          - assumptions: any assumptions made
          - open_questions: questions for the user (if any)
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

    async def _stream_model(
        self,
        messages: list[dict],
        data_region: str = "US",
        user_model_override: str | None = None,
    ):
        request = ModelRequest(
            task_type=self.task_type,
            messages=messages,
            data_region=data_region,
            user_model_override=user_model_override,
        )
        async for chunk in self._adapter.stream(request):
            yield chunk
