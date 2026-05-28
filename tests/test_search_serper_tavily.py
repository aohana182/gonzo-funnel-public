import os
from unittest.mock import MagicMock, patch

import pytest


def _mock_httpx_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = "<html>page</html>"
    resp.raise_for_status = MagicMock()
    return resp


# --- Serper ---

def test_serper_search_returns_results():
    from search.serper import SerperClient
    client = SerperClient(api_key="test-key")
    mock_resp = _mock_httpx_response({
        "organic": [
            {"title": "Accel", "link": "https://accel.com", "snippet": "VC firm"},
        ]
    })
    with patch("httpx.post", return_value=mock_resp):
        results = client.search("Accel", k=5)
    assert len(results) == 1
    assert results[0].title == "Accel"
    assert results[0].url == "https://accel.com"


def test_serper_factory_resolves():
    with patch.dict(os.environ, {"SEARCH_PROVIDER": "serper", "SERPER_API_KEY": "key123"}):
        from search.factory import get_client
        with patch("search.serper.SerperClient.__init__", return_value=None):
            client = get_client()
    assert client is not None


def test_serper_factory_missing_key_raises():
    with patch.dict(os.environ, {"SEARCH_PROVIDER": "serper"}, clear=False):
        os.environ.pop("SERPER_API_KEY", None)
        from errors import ConfigError
        from search.factory import get_client
        with pytest.raises(ConfigError, match="SERPER_API_KEY"):
            get_client()


# --- Tavily ---

def test_tavily_search_returns_results():
    from search.tavily import TavilyClient
    client = TavilyClient(api_key="test-key")
    mock_resp = _mock_httpx_response({
        "results": [
            {"title": "Sequoia", "url": "https://sequoiacap.com", "content": "VC firm"},
        ]
    })
    with patch("httpx.post", return_value=mock_resp):
        results = client.search("Sequoia", k=5)
    assert len(results) == 1
    assert results[0].title == "Sequoia"
    assert results[0].url == "https://sequoiacap.com"


def test_tavily_factory_resolves():
    with patch.dict(os.environ, {"SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "key456"}):
        from search.factory import get_client
        with patch("search.tavily.TavilyClient.__init__", return_value=None):
            client = get_client()
    assert client is not None


def test_tavily_factory_missing_key_raises():
    with patch.dict(os.environ, {"SEARCH_PROVIDER": "tavily"}, clear=False):
        os.environ.pop("TAVILY_API_KEY", None)
        from errors import ConfigError
        from search.factory import get_client
        with pytest.raises(ConfigError, match="TAVILY_API_KEY"):
            get_client()
