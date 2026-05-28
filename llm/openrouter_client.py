from llm.base import LLMResponse
from llm.openai_client import OpenAIClient
from observability.cost import calculate_cost

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """OpenRouter via the OpenAI-compatible API."""

    def __init__(self, model: str, api_key: str, timeout: float = 60.0):
        self.model = model
        self._inner = OpenAIClient(
            model=model,
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
            timeout=timeout,
        )

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        resp = self._inner.complete(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        cost = calculate_cost("openrouter", self.model, resp.tokens_in, resp.tokens_out)
        return LLMResponse(
            text=resp.text,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_usd=cost,
            raw=resp.raw,
            provider="openrouter",
            model=self.model,
            tool_calls=resp.tool_calls,
        )
