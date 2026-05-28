import time
import anthropic

from llm.base import LLMResponse
from observability.cost import calculate_cost

_BACKOFF = (1, 4, 16)
_DEFAULT_TIMEOUT = 60.0


class AnthropicClient:
    def __init__(self, model: str, api_key: str, timeout: float = _DEFAULT_TIMEOUT):
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

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
        # Anthropic has no native response_format param — JSON enforced via tool-forcing.
        # response_format kept for Protocol compatibility; tool_choice drives structured output.
        kwargs: dict = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                response = self._client.messages.create(**kwargs)
                text = next((b.text for b in response.content if b.type == "text"), "")
                tool_calls = [
                    {"name": b.name, "input": b.input}
                    for b in response.content
                    if b.type == "tool_use"
                ]
                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens
                return LLMResponse(
                    text=text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=calculate_cost("anthropic", self.model, tokens_in, tokens_out),
                    raw=response.model_dump(),
                    provider="anthropic",
                    model=self.model,
                    tool_calls=tool_calls,
                )
            except anthropic.APIStatusError as e:
                if e.status_code == 429 or e.status_code >= 500:
                    last_exc = e
                    if attempt < len(_BACKOFF) - 1:
                        time.sleep(backoff)
                        continue
                raise
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                last_exc = e
                if attempt < len(_BACKOFF) - 1:
                    time.sleep(backoff)
                    continue
                raise

        raise last_exc  # type: ignore[misc]
