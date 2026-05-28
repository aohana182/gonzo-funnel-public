import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from errors import ConfigError
from llm.base import LLMClient, LLMResponse
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper

T = TypeVar("T", bound=BaseModel)

_SPEC_DIR = Path(__file__).parent.parent / "spec"
_TOOL_NAME = "structured_output"


class AgentError(Exception):
    pass


def read_spec(filename: str) -> str:
    path = _SPEC_DIR / filename
    if not path.exists():
        raise ConfigError(f"spec/{filename} not found — fill in this file before running agents")
    content = path.read_text(encoding="utf-8").strip()
    if "[FILL IN]" in content:
        raise ConfigError(f"spec/{filename} contains unfilled [FILL IN] placeholders")
    return content


class BaseAgent(ABC):
    role: str  # set at class level in each subclass, e.g. "SCOUT"

    def __init__(self, client: LLMClient, logger: JsonlLogger, langfuse: LangfuseWrapper):
        self._client = client
        self._logger = logger
        self._langfuse = langfuse
        self._system = self._build_system_prompt()

    @abstractmethod
    def _build_system_prompt(self) -> str: ...

    def _parse(self, response: LLMResponse, output_model: Type[T]) -> T:
        if response.tool_calls:
            return output_model.model_validate(response.tool_calls[0]["input"])
        if response.text:
            return output_model.model_validate_json(response.text)
        raise AgentError(f"{self.role}: no structured output block in response")

    def _call(
        self,
        messages: list[dict],
        output_model: Type[T],
        run_id: str,
        vc_name: str = "",
    ) -> T:
        tool_def = {
            "name": _TOOL_NAME,
            "description": "Return structured output matching the required schema exactly.",
            "input_schema": output_model.model_json_schema(),
        }
        tool_choice = {"type": "tool", "name": _TOOL_NAME}

        span = self._langfuse.span(name=self.role, role=self.role, vc_name=vc_name)
        t0 = time.monotonic()
        response: LLMResponse | None = None
        _tokens_in = 0
        _tokens_out = 0
        _cost_usd = 0.0

        try:
            response = self._client.complete(
                system=self._system,
                messages=messages,
                tools=[tool_def],
                tool_choice=tool_choice,
            )
            _tokens_in = response.tokens_in or 0
            _tokens_out = response.tokens_out or 0
            _cost_usd = response.cost_usd or 0.0

            try:
                result = self._parse(response, output_model)
            except (ValidationError, AgentError) as first_exc:
                # Retry once: send the validation error back so the model can self-correct.
                retry_messages = messages + [{
                    "role": "user",
                    "content": (
                        f"Your previous output failed validation with this error: {first_exc}. "
                        f"Please correct your output and try again."
                    ),
                }]
                response = self._client.complete(
                    system=self._system,
                    messages=retry_messages,
                    tools=[tool_def],
                    tool_choice=tool_choice,
                )
                _tokens_in += response.tokens_in or 0
                _tokens_out += response.tokens_out or 0
                _cost_usd += response.cost_usd or 0.0
                result = self._parse(response, output_model)

            latency_ms = int((time.monotonic() - t0) * 1000)
            self._logger.log(
                role=self.role,
                provider=response.provider,
                model=response.model,
                tokens_in=_tokens_in,
                tokens_out=_tokens_out,
                cost_usd=_cost_usd,
                latency_ms=latency_ms,
                status="ok",
            )
            span.end(status="ok")
            return result

        except (ValidationError, AgentError) as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._logger.log(
                role=self.role,
                provider=response.provider if response else None,
                model=response.model if response else None,
                tokens_in=_tokens_in or None,
                tokens_out=_tokens_out or None,
                cost_usd=_cost_usd or None,
                latency_ms=latency_ms,
                status="error",
                error=str(exc),
            )
            span.end(status="error")
            raise AgentError(f"{self.role} output error: {exc}") from exc

        except Exception:
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._logger.log(
                role=self.role,
                provider=response.provider if response else None,
                model=response.model if response else None,
                tokens_in=_tokens_in or None,
                tokens_out=_tokens_out or None,
                cost_usd=_cost_usd or None,
                latency_ms=latency_ms,
                status="error",
                error="unexpected error",
            )
            span.end(status="error")
            raise
