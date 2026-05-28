from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    raw: dict
    provider: str
    model: str
    tool_calls: list[dict] = field(default_factory=list)


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse: ...
