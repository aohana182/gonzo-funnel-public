from unittest.mock import MagicMock, patch

import pytest

from agents.base import AgentError
from agents.drafter import Draft, Drafts, DrafterAgent
from agents.researcher import Citation, VCDossier
from agents.scorer import Score, ScoreDimension
from llm.base import LLMResponse
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper


def _make_agent():
    client = MagicMock()
    logger = MagicMock(spec=JsonlLogger)
    langfuse = MagicMock(spec=LangfuseWrapper)
    langfuse.span.return_value = MagicMock()
    with patch("agents.drafter.read_spec", return_value="[test content]"):
        agent = DrafterAgent(client=client, logger=logger, langfuse=langfuse)
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


def _make_score(total: int = 20, go: bool = True) -> Score:
    per = total // 5
    remainder = total % 5
    raw_scores = [per + (1 if i < remainder else 0) for i in range(5)]
    names = ["Thesis Fit", "Stage Fit", "Ticket Fit", "Geography", "Team Signal"]
    return Score(
        dimensions=[
            ScoreDimension(name=names[i], score=s, rationale="Reason.")
            for i, s in enumerate(raw_scores)
        ],
        total=total,
        go=go,
        summary="Good fit.",
    )


def _make_drafts_dict():
    return {
        "drafts": [
            {
                "channel": "Email",
                "subject": "Icegate — pre-seed round",
                "body": "Hi Sonali, saw your investment in DeepMind spinout — Icegate is similar.",
                "partner_name": "Sonali De Rycker",
            },
            {
                "channel": "LinkedIn DM",
                "subject": "",
                "body": "Hi Sonali, Icegate aligns with your deep tech thesis.",
                "partner_name": "Sonali De Rycker",
            },
        ]
    }


def _make_response(drafts_dict: dict) -> LLMResponse:
    return LLMResponse(
        text="",
        tokens_in=200,
        tokens_out=400,
        cost_usd=0.003,
        raw={},
        provider="anthropic",
        model="claude-sonnet-4-6",
        tool_calls=[{"name": "structured_output", "input": drafts_dict}],
    )


def test_drafter_returns_drafts_when_go_true():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_drafts_dict())

    result = agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")

    assert isinstance(result, Drafts)
    assert len(result.drafts) == 2


def test_drafter_returns_none_when_go_false():
    agent, client = _make_agent()

    result = agent.run(_make_dossier(), _make_score(total=10, go=False), run_id="run_test")

    assert result is None


def test_drafter_makes_no_llm_call_when_go_false():
    agent, client = _make_agent()

    agent.run(_make_dossier(), _make_score(total=10, go=False), run_id="run_test")

    client.complete.assert_not_called()


def test_drafter_produces_email_and_linkedin():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_drafts_dict())

    result = agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")

    channels = {d.channel for d in result.drafts}
    assert "Email" in channels
    assert "LinkedIn DM" in channels


def test_drafter_raises_agent_error_on_bad_output():
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
        agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")


def test_drafter_raises_agent_error_on_empty_response():
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
        agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")


def test_drafter_sends_vc_name_to_llm():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_drafts_dict())

    agent.run(_make_dossier(name="Benchmark Capital"), _make_score(go=True), run_id="run_test")

    call_messages = client.complete.call_args.kwargs["messages"]
    assert "Benchmark Capital" in call_messages[0]["content"]


def test_drafter_email_has_subject():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_drafts_dict())

    result = agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")

    email = next(d for d in result.drafts if d.channel == "Email")
    assert email.subject != ""


def test_drafter_linkedin_has_empty_subject():
    agent, client = _make_agent()
    client.complete.return_value = _make_response(_make_drafts_dict())

    result = agent.run(_make_dossier(), _make_score(go=True), run_id="run_test")

    linkedin = next(d for d in result.drafts if d.channel == "LinkedIn DM")
    assert linkedin.subject == ""
