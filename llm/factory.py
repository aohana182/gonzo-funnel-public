import os

from errors import ConfigError
from llm.anthropic_client import AnthropicClient
from llm.base import LLMClient

_SUPPORTED_PROVIDERS = {"anthropic", "openai", "openrouter", "openai_compatible"}


def get_client(role: str) -> LLMClient:
    prefix = role.upper()
    provider = os.environ.get(f"{prefix}_PROVIDER", "").strip()
    model = os.environ.get(f"{prefix}_MODEL", "").strip()
    api_key = os.environ.get(f"{prefix}_API_KEY", "").strip()
    base_url = os.environ.get(f"{prefix}_BASE_URL", "").strip() or None

    if not provider:
        raise ConfigError(f"{prefix}_PROVIDER is not set")
    if provider not in _SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"{prefix}_PROVIDER={provider!r} is not supported. "
            f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
        )
    if not model:
        raise ConfigError(f"{prefix}_MODEL is not set")
    if not api_key:
        raise ConfigError(f"{prefix}_API_KEY is not set")

    if provider == "anthropic":
        return AnthropicClient(model=model, api_key=api_key)

    if provider == "openai":
        from llm.openai_client import OpenAIClient
        return OpenAIClient(model=model, api_key=api_key, base_url=base_url)

    if provider == "openrouter":
        from llm.openrouter_client import OpenRouterClient
        return OpenRouterClient(model=model, api_key=api_key)

    if provider == "openai_compatible":
        from llm.openai_client import OpenAIClient
        if not base_url:
            raise ConfigError(f"{prefix}_BASE_URL is required for openai_compatible provider")
        return OpenAIClient(model=model, api_key=api_key, base_url=base_url)

    raise ConfigError(f"Unhandled provider: {provider!r}")
