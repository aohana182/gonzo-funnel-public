import pytest

from errors import ConfigError
from search.brave import BraveClient
from search.factory import get_client


def test_brave_provider_resolves(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    client = get_client()
    assert isinstance(client, BraveClient)


def test_missing_provider_raises(monkeypatch):
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    with pytest.raises(ConfigError, match="SEARCH_PROVIDER is not set"):
        get_client()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
    with pytest.raises(ConfigError, match="not supported"):
        get_client()


def test_brave_missing_key_raises(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "brave")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="BRAVE_API_KEY"):
        get_client()


def test_anthropic_native_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "anthropic_native")
    with pytest.raises(ConfigError, match="not yet implemented"):
        get_client()
