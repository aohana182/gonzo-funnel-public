from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from agents.base import AgentError
from agents.researcher import VCDossier, Citation
from agents.scorer import Score, ScoreDimension, ScorerAgent
from llm.base import LLMResponse
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper


def _make_agent():
    client = MagicMock()
    logger = MagicMock(spec=JsonlLogger)
    langfuse = MagicMock(spec=LangfuseWrapper)
    langfuse.span.return_value = MagicMock()
    with patch("agents.scorer.read_spec", return_value="[test content]"):
        agent = ScorerAgent(client=client, logger=logger, langfuse=langfuse)
    return agent, client


def _make_dossier(name="Accel"):
    return VCDossier(
        name=name,
        url="https://accel.com",
        country="USA",
        thesis_summary="Deep tech investor.",
        stage_focus=["Seed"],
        ticket_size="$500K–$3M",
        partners=["Sonali De Rycker"],
        score_preview="Strong thesis overlap.",
        citations=[Citation(claim="Invests in deep tech", source_url="https://accel.com", quote="")],
        sources=["https://accel.com"],
    )


def _make_dimensions(scores: list[int]) -> list[dict]:
    names = ["Thesis Fit", "Stage Fit", "Ticket Fit", "Geography", "Team Signal"]
    return [
        {"name": names[i], "score": s, "rationale": f"Reason {i}."}
        for i, s in enumerate(scores)
    ]


def _make_score_dict(scores: list[int], go: bool | None = None) -> dict:
    total = sum(scores)
    return {
        "dimensions": _make_dimensions(scores),
        "total": total,
        "go": go if go is not None else total >= 17,
        "summary": "Good overall fit.",
    }


def _make_response(score_dict: dict) -> LLMResponse:
    return LLMResponse(
        text="",
        tokens_in=150,
        tokens_out=300,
        cost_usd=0.002,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": score_dict}],
    )


def test_scorer_returns_score():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_score_dict([4, 4, 3, 3, 3]))

    result = agent.run(_make_dossier(), run_id="run_test")

    assert isinstance(result, Score)
    assert result.total == 17
    assert result.go is True


def test_scorer_go_true_when_total_gte_17():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_score_dict([4, 4, 3, 3, 3]))

    result = agent.run(_make_dossier(), run_id="run_test")

    assert result.total == 17
    assert result.go is True


def test_scorer_go_false_when_total_lt_17():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_score_dict([2, 2, 2, 2, 3]))

    result = agent.run(_make_dossier(), run_id="run_test")

    assert result.total == 11
    assert result.go is False


def test_scorer_raises_on_inconsistent_total():
    agent, client = _make_agent()
    bad = _make_score_dict([3, 3, 3, 3, 3])
    bad["total"] = 99
    client.complete.return_value = _make_response(bad)

    with pytest.raises(AgentError):
        agent.run(_make_dossier(), run_id="run_test")


def test_scorer_raises_on_inconsistent_go():
    agent, client = _make_agent()
    bad = _make_score_dict([4, 4, 3, 3, 3])  # total=17, go=True
    bad["go"] = False  # inconsistent — should be True at threshold 17
    client.complete.return_value = _make_response(bad)

    with pytest.raises(AgentError):
        agent.run(_make_dossier(), run_id="run_test")


def test_scorer_raises_agent_error_on_bad_output():
    agent, client = _make_agent()
    client.complete.return_value = LLMResponse(
        text="",
        tokens_in=10,
        tokens_out=10,
        cost_usd=None,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": {"wrong": "data"}}],
    )

    with pytest.raises(AgentError):
        agent.run(_make_dossier(), run_id="run_test")


def test_scorer_raises_agent_error_on_empty_response():
    agent, client = _make_agent()
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
        agent.run(_make_dossier(), run_id="run_test")


def test_scorer_sends_dossier_name_to_llm():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_score_dict([3, 3, 3, 3, 3]))

    agent.run(_make_dossier(name="Benchmark Capital"), run_id="run_test")

    call_messages = client.complete.call_args.kwargs["messages"]
    assert "Benchmark Capital" in call_messages[0]["content"]


def test_scorer_returns_cached_score_without_llm_call():
    cached_score = Score(
        dimensions=[ScoreDimension(name=f"D{i}", score=4, rationale="ok") for i in range(5)],
        total=20,
        go=True,
        summary="Cached.",
    )
    mock_cache = MagicMock()
    mock_cache.get_cached_score.return_value = cached_score.model_dump_json()

    with patch("agents.scorer.read_spec", return_value="[thesis]"):
        agent = ScorerAgent(
            client=MagicMock(),
            logger=MagicMock(spec=JsonlLogger),
            langfuse=MagicMock(spec=LangfuseWrapper),
            cache=mock_cache,
        )

    result = agent.run(_make_dossier(), run_id="run_test")

    assert result.total == 20
    agent._client.complete.assert_not_called()


def test_scorer_stores_result_in_cache_on_miss():
    mock_cache = MagicMock()
    mock_cache.get_cached_score.return_value = None

    with patch("agents.scorer.read_spec", return_value="[thesis]"):
        agent = ScorerAgent(
            client=MagicMock(),
            logger=MagicMock(spec=JsonlLogger),
            langfuse=MagicMock(spec=LangfuseWrapper),
            cache=mock_cache,
        )
    agent._client.complete.return_value = _make_response(_make_score_dict([3, 3, 3, 3, 3]))
    langfuse_span = MagicMock()
    agent._langfuse.span.return_value = langfuse_span

    agent.run(_make_dossier(), run_id="run_test")

    mock_cache.set_cached_score.assert_called_once()
    args = mock_cache.set_cached_score.call_args[0]
    assert args[0] == "Accel"
