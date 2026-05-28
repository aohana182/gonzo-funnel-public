import json
from unittest.mock import MagicMock, patch

import pytest

from llm.openai_client import OpenAIClient
from llm.openrouter_client import OpenRouterClient


def _make_oai_response(content="hello", tool_name=None, tool_args=None,
                        tokens_in=100, tokens_out=50):
    choice = MagicMock()
    choice.message.content = content
    if tool_name:
        tc = MagicMock()
        tc.function.name = tool_name
        tc.function.arguments = json.dumps(tool_args or {})
        choice.message.tool_calls = [tc]
    else:
        choice.message.tool_calls = None
    usage = MagicMock()
    usage.prompt_tokens = tokens_in
    usage.completion_tokens = tokens_out
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model_dump.return_value = {}
    return resp


def _make_client(base_url=None):
    with patch("openai.OpenAI"):
        client = OpenAIClient(model="gpt-4o", api_key="test-key", base_url=base_url)
    return client


def test_openai_client_returns_response():
    client = _make_client()
    client._client.chat.completions.create.return_value = _make_oai_response("hi")

    result = client.complete(system="sys", messages=[{"role": "user", "content": "hi"}])

    assert result.text == "hi"
    assert result.provider == "openai"
    assert result.model == "gpt-4o"


def test_openai_client_extracts_tool_calls():
    client = _make_client()
    client._client.chat.completions.create.return_value = _make_oai_response(
        content="", tool_name="structured_output", tool_args={"key": "val"}
    )

    result = client.complete(system="sys", messages=[])

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "structured_output"
    assert result.tool_calls[0]["input"] == {"key": "val"}


def test_openai_client_token_counts():
    client = _make_client()
    client._client.chat.completions.create.return_value = _make_oai_response(
        tokens_in=200, tokens_out=100
    )

    result = client.complete(system="sys", messages=[])

    assert result.tokens_in == 200
    assert result.tokens_out == 100


def test_openrouter_client_sets_provider():
    with patch("openai.OpenAI"):
        client = OpenRouterClient(model="openai/gpt-4o", api_key="test-key")
    client._inner._client.chat.completions.create.return_value = _make_oai_response("hi")

    result = client.complete(system="sys", messages=[])

    assert result.provider == "openrouter"
    assert result.model == "openai/gpt-4o"


def test_openai_compatible_uses_base_url():
    import os
    with patch.dict(os.environ, {
        "CUSTOM_PROVIDER": "openai_compatible",
        "CUSTOM_MODEL": "local-model",
        "CUSTOM_API_KEY": "key",
        "CUSTOM_BASE_URL": "http://localhost:8080/v1",
    }):
        from llm.factory import get_client
        with patch("openai.OpenAI") as mock_oai:
            client = get_client("CUSTOM")
        mock_oai.assert_called_once()
        call_kwargs = mock_oai.call_args.kwargs
        assert call_kwargs["base_url"] == "http://localhost:8080/v1"
