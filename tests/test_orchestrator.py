from unittest.mock import MagicMock, patch
import pytest

from agents.drafter import Draft, Drafts
from agents.researcher import Citation, VCDossier
from agents.scorer import Score, ScoreDimension
from agents.scout import ScoutCandidate
from models import RunResult
from orchestrator import run_pipeline


# --- Helpers ---

def _candidate(name="Accel"):
    return ScoutCandidate(name=name, url=f"https://{name.lower()}.com",
                          why_match="fit", source_urls=[])


def _dossier(name="Accel"):
    return VCDossier(
        name=name, url=f"https://{name.lower()}.com", country="USA",
        thesis_summary="Deep tech.", stage_focus=["Seed"], ticket_size="$500K",
        partners=["Partner A"], score_preview="Good fit.",
        citations=[], sources=[f"https://{name.lower()}.com"],
    )


def _score(total=20, go=True):
    names = ["Thesis", "Stage", "Ticket", "Geo", "Team"]
    per, rem = divmod(total, 5)
    dims = [ScoreDimension(name=names[i], score=per + (1 if i < rem else 0),
                           rationale="r") for i in range(5)]
    return Score(dimensions=dims, total=total, go=go, summary="s")


def _drafts():
    return Drafts(drafts=[
        Draft(channel="Email", subject="Hi", body="body", partner_name="Partner A"),
        Draft(channel="LinkedIn DM", subject="", body="body", partner_name="Partner A"),
    ])


@pytest.fixture
def mocks():
    """Patch all orchestrator dependencies."""
    mock_cache = MagicMock()
    mock_cache.get_all_seen_names.return_value = []
    mock_cache.get_stale_vcs.return_value = []

    mock_storage = MagicMock()
    mock_storage.upsert_vc.return_value = "rec123"

    mock_scout = MagicMock()
    mock_scout.run.return_value = [_candidate()]

    mock_researcher = MagicMock()
    mock_researcher.run.return_value = _dossier()

    mock_scorer = MagicMock()
    mock_scorer.run.return_value = _score()

    mock_drafter = MagicMock()
    mock_drafter.run.return_value = _drafts()

    patches = {
        "orchestrator.make_run_id": MagicMock(return_value="run_test"),
        "orchestrator.JsonlLogger": MagicMock(),
        "orchestrator.LangfuseWrapper": MagicMock(),
        "orchestrator.SqliteCache": MagicMock(return_value=mock_cache),
        "orchestrator.AirtableStorage": MagicMock(return_value=mock_storage),
        "orchestrator.get_client": MagicMock(return_value=MagicMock()),
        "orchestrator.get_search_client": MagicMock(return_value=MagicMock()),
        "orchestrator.ScoutAgent": MagicMock(return_value=mock_scout),
        "orchestrator.ResearcherAgent": MagicMock(return_value=mock_researcher),
        "orchestrator.ScorerAgent": MagicMock(return_value=mock_scorer),
        "orchestrator.DrafterAgent": MagicMock(return_value=mock_drafter),
        "orchestrator._print_cost_table": MagicMock(return_value=(0.0, 0, 0)),
    }

    with patch("notify.email.send_digest"), \
         patch.multiple("orchestrator", **{k.split(".", 1)[1]: v for k, v in patches.items()}):
        yield {
            "cache": mock_cache,
            "storage": mock_storage,
            "scout": mock_scout,
            "researcher": mock_researcher,
            "scorer": mock_scorer,
            "drafter": mock_drafter,
        }


# --- Tests ---

async def test_pipeline_runs_all_agents(mocks):
    result = await run_pipeline()

    mocks["scout"].run.assert_called_once()
    mocks["researcher"].run.assert_called_once()
    mocks["scorer"].run.assert_called_once()
    mocks["drafter"].run.assert_called_once()


async def test_pipeline_result_counts(mocks):
    result = await run_pipeline()

    assert result.vcs_scouted == 1
    assert result.vcs_researched == 1
    assert result.drafts_written == 2
    assert result.errors == []
    assert result.status == "success"


async def test_pipeline_passes_seen_names_to_scout(mocks):
    mocks["cache"].get_all_seen_names.return_value = ["AlreadySeen Fund"]

    await run_pipeline()

    call_kwargs = mocks["scout"].run.call_args
    assert "Already Seen Fund" in call_kwargs.kwargs.get("seen_names",
                                                          call_kwargs.args[1] if len(call_kwargs.args) > 1 else []) \
           or "AlreadySeen Fund" in str(call_kwargs)


async def test_pipeline_vc_failure_doesnt_abort(mocks):
    mocks["scout"].run.return_value = [_candidate("Accel"), _candidate("Sequoia")]
    mocks["researcher"].run.side_effect = [Exception("timeout"), _dossier("Sequoia")]
    mocks["scorer"].run.return_value = _score()
    mocks["drafter"].run.return_value = _drafts()

    result = await run_pipeline()

    assert result.vcs_scouted == 2
    assert result.vcs_researched == 1
    assert len(result.errors) == 1
    assert result.status == "partial_failure"


async def test_pipeline_all_fail_gives_total_failure(mocks):
    mocks["researcher"].run.side_effect = Exception("all broken")

    result = await run_pipeline()

    assert result.vcs_researched == 0
    assert result.status == "total_failure"


async def test_pipeline_dry_run_skips_airtable(mocks):
    await run_pipeline(dry_run=True)

    mocks["storage"].upsert_vc.assert_not_called()
    mocks["storage"].upsert_draft.assert_not_called()


async def test_pipeline_dry_run_skips_run_log(mocks):
    await run_pipeline(dry_run=True)

    mocks["cache"].start_run.assert_not_called()
    mocks["cache"].end_run.assert_not_called()


async def test_pipeline_adds_vc_to_seen(mocks):
    await run_pipeline()

    mocks["cache"].add_vc_seen.assert_called_once_with("Accel", "https://accel.com")


async def test_pipeline_updates_last_researched(mocks):
    await run_pipeline()

    mocks["cache"].update_last_researched.assert_called_once_with("Accel")


async def test_pipeline_go_false_writes_no_drafts(mocks):
    mocks["scorer"].run.return_value = _score(total=10, go=False)
    mocks["drafter"].run.return_value = None

    result = await run_pipeline()

    assert result.drafts_written == 0
    mocks["storage"].upsert_draft.assert_not_called()


async def test_pipeline_respects_limit(mocks):
    mocks["scout"].run.return_value = [_candidate(f"Fund{i}") for i in range(20)]

    result = await run_pipeline(limit=3)

    assert result.vcs_scouted == 3


async def test_pipeline_seen_names_from_cache_passed_to_scout(mocks):
    mocks["cache"].get_all_seen_names.return_value = ["OldFund"]

    await run_pipeline()

    scout_call = mocks["scout"].run.call_args
    seen = scout_call.kwargs.get("seen_names") or scout_call.args[1]
    assert "OldFund" in seen
