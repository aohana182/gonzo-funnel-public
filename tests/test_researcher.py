from unittest.mock import MagicMock, call, patch

import pytest

from agents.base import AgentError
from agents.researcher import Citation, ResearcherAgent, VCDossier
from agents.scout import ScoutCandidate
from llm.base import LLMResponse
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper
from search.base import SearchResult


def _make_agent():
    client = MagicMock()
    search = MagicMock()
    search.search.return_value = [
        SearchResult(
            title="Accel",
            url="https://accel.com/about",
            snippet="Deep tech VC",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    ]
    search.fetch.return_value = "Accel Partners is a global VC firm."
    logger = MagicMock(spec=JsonlLogger)
    langfuse = MagicMock(spec=LangfuseWrapper)
    langfuse.span.return_value = MagicMock()
    with patch("agents.researcher.read_spec", return_value="[test content]"):
        agent = ResearcherAgent(client=client, search=search, logger=logger, langfuse=langfuse)
    return agent, client, search


def _make_candidate(name="Accel", url="https://accel.com"):
    return ScoutCandidate(name=name, url=url, why_match="deep tech focus", source_urls=[url])


def _valid_dossier_dict(name="Accel"):
    return {
        "name": name,
        "url": "https://accel.com",
        "country": "USA",
        "thesis_summary": "Deep tech investor focused on B2B.",
        "stage_focus": ["Seed", "Series A"],
        "ticket_size": "$500K–$3M",
        "partners": ["Sonali De Rycker"],
        "score_preview": "Strong thesis overlap with enterprise software.",
        "citations": [{"claim": "Invests in deep tech", "source_url": "https://accel.com", "quote": ""}],
        "sources": ["https://accel.com"],
    }


def _make_response(dossier_dict: dict) -> LLMResponse:
    return LLMResponse(
        text="",
        tokens_in=200,
        tokens_out=600,
        cost_usd=0.005,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": dossier_dict}],
    )


def test_researcher_returns_dossier():
    agent, client, _ = _make_agent()
    client.complete.return_value = _make_response(_valid_dossier_dict())

    result = agent.run(_make_candidate(), run_id="run_test")

    assert isinstance(result, VCDossier)
    assert result.name == "Accel"
    assert result.country == "USA"


def test_researcher_runs_three_search_queries():
    agent, client, search = _make_agent()
    client.complete.return_value = _make_response(_valid_dossier_dict())

    agent.run(_make_candidate(name="Accel"), run_id="run_test")

    assert search.search.call_count == 3
    calls = [c.args[0] for c in search.search.call_args_list]
    assert "Accel" in calls
    assert "Accel portfolio" in calls
    assert "Accel investment thesis" in calls


def test_researcher_fetches_candidate_url_first():
    agent, client, search = _make_agent()
    search.search.return_value = [
        SearchResult(title="Other", url="https://other.com", snippet="x", retrieved_at="2026-01-01T00:00:00Z")
    ]
    client.complete.return_value = _make_response(_valid_dossier_dict())

    agent.run(_make_candidate(url="https://accel.com"), run_id="run_test")

    first_fetch_url = search.fetch.call_args_list[0].args[0]
    assert first_fetch_url == "https://accel.com"


def test_researcher_fetches_at_most_three_urls():
    agent, client, search = _make_agent()
    search.search.return_value = [
        SearchResult(title=f"R{i}", url=f"https://site{i}.com", snippet="x", retrieved_at="2026-01-01T00:00:00Z")
        for i in range(10)
    ]
    client.complete.return_value = _make_response(_valid_dossier_dict())

    agent.run(_make_candidate(), run_id="run_test")

    assert search.fetch.call_count <= 3


def test_researcher_deduplicates_fetch_urls():
    agent, client, search = _make_agent()
    search.search.return_value = [
        SearchResult(title="Same", url="https://accel.com", snippet="x", retrieved_at="2026-01-01T00:00:00Z"),
        SearchResult(title="Other", url="https://other.com", snippet="y", retrieved_at="2026-01-01T00:00:00Z"),
    ]
    client.complete.return_value = _make_response(_valid_dossier_dict())

    agent.run(_make_candidate(url="https://accel.com"), run_id="run_test")

    fetched_urls = [c.args[0] for c in search.fetch.call_args_list]
    assert fetched_urls.count("https://accel.com") == 1


def test_researcher_raises_agent_error_on_bad_tool_output():
    agent, client, _ = _make_agent()
    client.complete.return_value = LLMResponse(
        text="",
        tokens_in=10,
        tokens_out=10,
        cost_usd=None,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": {"wrong_key": "bad"}}],
    )

    with pytest.raises(AgentError):
        agent.run(_make_candidate(), run_id="run_test")


def test_researcher_raises_agent_error_on_empty_response():
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
        agent.run(_make_candidate(), run_id="run_test")


def test_researcher_skips_failed_fetches():
    agent, client, search = _make_agent()
    search.search.return_value = [
        SearchResult(title="Other", url="https://other.com", snippet="y", retrieved_at="2026-01-01T00:00:00Z")
    ]
    search.fetch.side_effect = Exception("timeout")
    client.complete.return_value = _make_response(_valid_dossier_dict())

    result = agent.run(_make_candidate(), run_id="run_test")

    assert isinstance(result, VCDossier)
