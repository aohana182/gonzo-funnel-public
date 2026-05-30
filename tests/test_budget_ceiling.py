import os
from unittest.mock import MagicMock, patch

import pytest

from agents.drafter import Draft, Drafts
from agents.researcher import VCDossier
from agents.scorer import Score, ScoreDimension
from agents.scout import ScoutCandidate
from models import RunResult
from orchestrator import run_pipeline


def _candidate(name="Accel"):
    return ScoutCandidate(name=name, url=f"https://{name.lower()}.com",
                          why_match="fit", source_urls=[])


def _dossier(name="Accel"):
    return VCDossier(
        name=name, url=f"https://{name.lower()}.com", country="USA",
        thesis_summary="Deep tech.", stage_focus=["Seed"], ticket_size="$500K",
        partners=["Partner A"], sources=[],
    )


def _score():
    dims = [ScoreDimension(name=n, score=3, rationale="r")
            for n in ["A", "B", "C", "D", "E"]]
    return Score(dimensions=dims, total=15, go=False, summary="s")


def _drafts():
    return Drafts(drafts=[
        Draft(channel="Email", subject="Hi", body="body", partner_name="Partner A"),
    ])


@pytest.fixture
def base_mocks():
    mock_cache = MagicMock()
    mock_cache.get_all_seen_names.return_value = []
    mock_cache.get_stale_vcs.return_value = []

    mock_scout = MagicMock()
    mock_scout.run.return_value = [_candidate("A"), _candidate("B"), _candidate("C")]

    mock_researcher = MagicMock()
    mock_researcher.run.return_value = _dossier()

    mock_scorer = MagicMock()
    mock_scorer.run.return_value = _score()

    mock_drafter = MagicMock()
    mock_drafter.run.return_value = _drafts()

    patches = {
        "make_run_id": MagicMock(return_value="run_test"),
        "JsonlLogger": MagicMock(),
        "LangfuseWrapper": MagicMock(),
        "SqliteCache": MagicMock(return_value=mock_cache),
        "AirtableStorage": MagicMock(),
        "get_client": MagicMock(return_value=MagicMock()),
        "get_search_client": MagicMock(return_value=MagicMock()),
        "ScoutAgent": MagicMock(return_value=mock_scout),
        "ResearcherAgent": MagicMock(return_value=mock_researcher),
        "ScorerAgent": MagicMock(return_value=mock_scorer),
        "DrafterAgent": MagicMock(return_value=mock_drafter),
        "_print_cost_table": MagicMock(return_value=(0.0, 0, 0)),
    }

    with patch.multiple("orchestrator", **patches):
        yield {"scout": mock_scout, "researcher": mock_researcher}


async def test_no_budget_limit_processes_all(base_mocks):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MAX_COST_USD", None)
        with patch("orchestrator._read_run_stats", return_value={}):
            result = await run_pipeline(dry_run=True)

    assert result.vcs_researched == 3
    assert result.vcs_budget_halted == 0


async def test_budget_ceiling_halts_remaining_vcs(base_mocks):
    # Budget is already blown before any VC starts
    with patch.dict(os.environ, {"MAX_COST_USD": "0.01"}):
        with patch("orchestrator._read_run_stats", return_value={
            "SCORER": {"calls": 1, "tokens_in": 0, "tokens_out": 0,
                       "cost_usd": 5.00, "latency_ms": 0}
        }):
            result = await run_pipeline(dry_run=True)

    assert result.vcs_budget_halted == 3
    assert result.vcs_researched == 0


async def test_budget_not_exceeded_allows_run(base_mocks):
    with patch.dict(os.environ, {"MAX_COST_USD": "100.00"}):
        with patch("orchestrator._read_run_stats", return_value={}):
            result = await run_pipeline(dry_run=True)

    assert result.vcs_researched == 3
    assert result.vcs_budget_halted == 0


async def test_budget_halted_not_counted_as_error(base_mocks):
    with patch.dict(os.environ, {"MAX_COST_USD": "0.01"}):
        with patch("orchestrator._read_run_stats", return_value={
            "SCORER": {"calls": 1, "tokens_in": 0, "tokens_out": 0,
                       "cost_usd": 5.00, "latency_ms": 0}
        }):
            result = await run_pipeline(dry_run=True)

    assert result.errors == []
    assert result.vcs_budget_halted > 0
