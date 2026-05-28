import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from agents.base import AgentError
from agents.scorer import Score, ScoreDimension, ScorerAgent
from agents.researcher import VCDossier, Citation
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


def _dims(scores: list[int]) -> list[dict]:
    names = ["Thesis Fit", "Stage Fit", "Ticket Fit", "Geography", "Team Signal"]
    return [{"name": names[i], "score": s, "rationale": "r"} for i, s in enumerate(scores)]


def _good_response(scores=(4, 4, 3, 3, 3)):
    total = sum(scores)
    payload = {
        "dimensions": _dims(list(scores)),
        "total": total,
        "go": total >= 17,
        "summary": "ok",
    }
    resp = MagicMock(spec=LLMResponse)
    resp.tool_calls = [{"name": "structured_output", "input": payload}]
    resp.text = ""
    resp.provider = "anthropic"
    resp.model = "claude-sonnet-4-6"
    resp.tokens_in = 100
    resp.tokens_out = 50
    resp.cost_usd = 0.001
    return resp


def _bad_response():
    # total deliberately wrong (says 20, sum is 15)
    payload = {
        "dimensions": _dims([3, 3, 3, 3, 3]),
        "total": 20,
        "go": True,
        "summary": "bad",
    }
    resp = MagicMock(spec=LLMResponse)
    resp.tool_calls = [{"name": "structured_output", "input": payload}]
    resp.text = ""
    resp.provider = "anthropic"
    resp.model = "claude-sonnet-4-6"
    resp.tokens_in = 100
    resp.tokens_out = 50
    resp.cost_usd = 0.001
    return resp


def _make_dossier():
    return VCDossier(
        name="Accel", url="https://accel.com", country="USA",
        thesis_summary="Deep tech.", stage_focus=["Seed"], ticket_size="$500K",
        partners=["Partner A"], score_preview="Good.",
        citations=[], sources=["https://accel.com"],
    )


def test_no_retry_on_clean_first_response():
    agent, client = _make_agent()
    client.complete.return_value = _good_response()

    agent.run(_make_dossier(), run_id="r")

    assert client.complete.call_count == 1


def test_retries_once_on_validation_error():
    agent, client = _make_agent()
    client.complete.side_effect = [_bad_response(), _good_response()]

    result = agent.run(_make_dossier(), run_id="r")

    assert client.complete.call_count == 2
    assert result.total == 17


def test_retry_message_contains_error_text():
    agent, client = _make_agent()
    client.complete.side_effect = [_bad_response(), _good_response()]

    agent.run(_make_dossier(), run_id="r")

    retry_call_messages = client.complete.call_args_list[1][1]["messages"]
    last_msg = retry_call_messages[-1]
    assert last_msg["role"] == "user"
    assert "validation" in last_msg["content"].lower()


def test_raises_agent_error_after_two_failures():
    agent, client = _make_agent()
    client.complete.side_effect = [_bad_response(), _bad_response()]

    with pytest.raises(AgentError):
        agent.run(_make_dossier(), run_id="r")

    assert client.complete.call_count == 2


def test_no_third_attempt_after_two_failures():
    agent, client = _make_agent()
    client.complete.side_effect = [_bad_response(), _bad_response(), _good_response()]

    with pytest.raises(AgentError):
        agent.run(_make_dossier(), run_id="r")

    assert client.complete.call_count == 2
