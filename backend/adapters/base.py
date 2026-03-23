"""
Model Adapter Base — all LLM providers implement this interface.
Separates prompt/schema logic from model vendor specifics.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class ModelRequest:
    task_type: str                    # maps to routing_policy.yaml
    messages: list[dict[str, str]]    # [{"role": "user"|"assistant"|"system", "content": "..."}]
    response_schema: dict | None = None  # JSON schema for structured output
    temperature: float = 0.3
    max_tokens: int = 4096
    user_model_override: str | None = None  # set when user picks model inline
    data_region: str = "US"           # drives region-aware routing


@dataclass
class ModelResponse:
    content: str
    model_used: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_type: str
    structured: dict | None = None    # populated when response_schema is set


class BaseModelAdapter(ABC):
    """
    All adapters must implement this contract.
    Swap providers by implementing a new adapter — nothing else changes.
    """

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Non-streaming completion."""
        ...

    @abstractmethod
    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """Streaming completion — yields text chunks."""
        ...

    @abstractmethod
    def supports_structured_output(self) -> bool:
        """Whether this adapter can enforce a JSON schema response."""
        ...

    @abstractmethod
    def available_models(self) -> list[str]:
        """List of model IDs this adapter supports."""
        ...
