import pytest

from errors import ConfigError
from llm.anthropic_client import AnthropicClient
from llm.factory import get_client
from observability.cost import calculate_cost


def test_anthropic_provider_resolves(monkeypatch):
    monkeypatch.setenv("SCOUT_PROVIDER", "anthropic")
    monkeypatch.setenv("SCOUT_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("SCOUT_API_KEY", "sk-test-key")
    client = get_client("scout")
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-sonnet-4-6"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("SCOUT_PROVIDER", "grok")
    monkeypatch.setenv("SCOUT_MODEL", "grok-1")
    monkeypatch.setenv("SCOUT_API_KEY", "sk-test")
    with pytest.raises(ConfigError, match="not supported"):
        get_client("scout")


def test_missing_model_raises(monkeypatch):
    monkeypatch.setenv("SCOUT_PROVIDER", "anthropic")
    monkeypatch.delenv("SCOUT_MODEL", raising=False)
    monkeypatch.setenv("SCOUT_API_KEY", "sk-test")
    with pytest.raises(ConfigError, match="SCOUT_MODEL"):
        get_client("scout")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv("SCOUT_PROVIDER", "anthropic")
    monkeypatch.setenv("SCOUT_MODEL", "claude-sonnet-4-6")
    monkeypatch.delenv("SCOUT_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="SCOUT_API_KEY"):
        get_client("scout")


def test_calculate_cost_known_model():
    cost = calculate_cost("anthropic", "claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.0)  # 3.00 in + 15.00 out per million


def test_calculate_cost_unknown_model_returns_none():
    cost = calculate_cost("anthropic", "claude-unknown-99", 1000, 500)
    assert cost is None
