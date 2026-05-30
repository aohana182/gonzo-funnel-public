from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from agents.base import AgentError, read_spec
from agents.scout import ScoutAgent, ScoutCandidate, _ScoutOutput
from llm.base import LLMResponse
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper


def _make_agent():
    client = MagicMock()
    search = MagicMock()
    search.search.return_value = []
    logger = MagicMock(spec=JsonlLogger)
    langfuse = MagicMock(spec=LangfuseWrapper)
    langfuse.span.return_value = MagicMock()
    with patch("agents.scout.read_spec", return_value="[test content]"):
        agent = ScoutAgent(client=client, search=search, logger=logger, langfuse=langfuse)
    return agent, client, logger


def _make_response(candidates: list[dict]) -> LLMResponse:
    return LLMResponse(
        text="",
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.001,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": {"candidates": candidates}}],
    )


def test_scout_returns_candidates():
    agent, client, _ = _make_agent()
    client.complete.return_value = _make_response([
        {"name": "Accel", "url": "https://accel.com", "why_match": "deep tech focus", "source_urls": ["https://accel.com"]},
        {"name": "Sequoia", "url": "https://sequoiacap.com", "why_match": "infra focus", "source_urls": ["https://sequoiacap.com"]},
    ])

    results = agent.run(run_id="run_test", seen_names=[], limit=10)

    assert len(results) == 2
    assert results[0].name == "Accel"


def test_scout_excludes_seen_names():
    agent, client, _ = _make_agent()
    client.complete.return_value = _make_response([
        {"name": "Accel", "url": "https://accel.com", "why_match": "deep tech", "source_urls": []},
        {"name": "Already Seen Fund", "url": "https://example.com", "why_match": "fit", "source_urls": []},
    ])

    results = agent.run(run_id="run_test", seen_names=["Already Seen Fund"], limit=10)

    assert len(results) == 1
    assert results[0].name == "Accel"


def test_scout_excludes_seen_names_case_insensitive():
    agent, client, _ = _make_agent()
    client.complete.return_value = _make_response([
        {"name": "accel partners", "url": "https://accel.com", "why_match": "fit", "source_urls": []},
    ])

    results = agent.run(run_id="run_test", seen_names=["Accel Partners"])

    assert results == []


def test_scout_respects_limit():
    agent, client, _ = _make_agent()
    candidates = [
        {"name": f"Fund {i}", "url": f"https://fund{i}.com", "why_match": "fit", "source_urls": []}
        for i in range(10)
    ]
    client.complete.return_value = _make_response(candidates)

    results = agent.run(run_id="run_test", seen_names=[], limit=3)

    assert len(results) == 3


def test_scout_raises_agent_error_on_bad_tool_output():
    agent, client, _ = _make_agent()
    client.complete.return_value = LLMResponse(
        text="",
        tokens_in=10,
        tokens_out=10,
        cost_usd=None,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": {"wrong_key": []}}],
    )

    with pytest.raises(AgentError):
        agent.run(run_id="run_test", seen_names=[])


def test_scout_raises_agent_error_on_empty_response():
    agent, client, _ = _make_agent()
    client.complete.return_value = LLMResponse(
        text="",
        tokens_in=10,
        tokens_out=10,
        cost_usd=None,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[],
    )

    with pytest.raises(AgentError):
        agent.run(run_id="run_test", seen_names=[])


def test_read_spec_raises_on_missing_file():
    with pytest.raises(Exception, match="not found"):
        read_spec("nonexistent_file_xyz.md")


def test_read_spec_raises_on_unfilled_placeholder(tmp_path, monkeypatch):
    import agents.base as base_module
    monkeypatch.setattr(base_module, "_SPEC_DIR", tmp_path)
    (tmp_path / "test.md").write_text("## Section\n[FILL IN]")

    with pytest.raises(Exception, match="unfilled"):
        read_spec("test.md")
