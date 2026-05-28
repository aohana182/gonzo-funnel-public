import time

import openai

from llm.base import LLMResponse
from observability.cost import calculate_cost

_BACKOFF = (1, 4, 16)
_DEFAULT_TIMEOUT = 60.0


class OpenAIClient:
    def __init__(self, model: str, api_key: str, base_url: str | None = None,
                 timeout: float = _DEFAULT_TIMEOUT):
        self.model = model
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or None,
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
        oai_messages = [{"role": "system", "content": system}] + messages

        kwargs: dict = dict(
            model=self.model,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if tools:
            oai_tools = [
                {"type": "function", "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                }}
                for t in tools
            ]
            kwargs["tools"] = oai_tools
        if tool_choice and tools:
            tc_name = tool_choice.get("name")
            kwargs["tool_choice"] = (
                {"type": "function", "function": {"name": tc_name}} if tc_name else "auto"
            )
        if response_format:
            kwargs["response_format"] = response_format

        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                response = self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                text = choice.message.content or ""
                tool_calls: list[dict] = []
                if choice.message.tool_calls:
                    import json
                    for tc in choice.message.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as exc:
                            raise ValueError(
                                f"malformed tool arguments from model: {tc.function.arguments!r}"
                            ) from exc
                        tool_calls.append({"name": tc.function.name, "input": args})
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens
                return LLMResponse(
                    text=text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=calculate_cost("openai", self.model, tokens_in, tokens_out),
                    raw=response.model_dump(),
                    provider="openai",
                    model=self.model,
                    tool_calls=tool_calls,
                )
            except openai.RateLimitError as e:
                last_exc = e
                if attempt < len(_BACKOFF) - 1:
                    time.sleep(backoff)
                    continue
                raise
            except openai.APIStatusError as e:
                if e.status_code >= 500:
                    last_exc = e
                    if attempt < len(_BACKOFF) - 1:
                        time.sleep(backoff)
                        continue
                raise
            except (openai.APITimeoutError, openai.APIConnectionError) as e:
                last_exc = e
                if attempt < len(_BACKOFF) - 1:
                    time.sleep(backoff)
                    continue
                raise

        raise last_exc  # type: ignore[misc]
