import os

from errors import ConfigError
from search.base import SearchClient
from search.brave import BraveClient

_SUPPORTED_PROVIDERS = {"brave", "anthropic_native", "serper", "tavily"}


def get_client() -> SearchClient:
    provider = os.environ.get("SEARCH_PROVIDER", "").strip()

    if not provider:
        raise ConfigError("SEARCH_PROVIDER is not set")

    if provider not in _SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"SEARCH_PROVIDER={provider!r} is not supported. "
            f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    if provider == "anthropic_native":
        raise ConfigError(
            "anthropic_native search is not yet implemented. Use brave, serper, or tavily."
        )

    if provider == "brave":
        api_key = os.environ.get("BRAVE_API_KEY", "").strip()
        if not api_key:
            raise ConfigError("BRAVE_API_KEY is not set")
        return BraveClient(api_key=api_key)

    if provider == "serper":
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if not api_key:
            raise ConfigError("SERPER_API_KEY is not set")
        from search.serper import SerperClient
        return SerperClient(api_key=api_key)

    if provider == "tavily":
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise ConfigError("TAVILY_API_KEY is not set")
        from search.tavily import TavilyClient
        return TavilyClient(api_key=api_key)

    raise ConfigError(f"Unhandled search provider: {provider!r}")
