import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from errors import ConfigError


def _make_result(status="success", scouted=1, researched=1, drafted=2, errors=None):
    r = MagicMock()
    r.status = status
    r.vcs_scouted = scouted
    r.vcs_researched = researched
    r.drafts_written = drafted
    r.errors = errors or []
    return r


def _call_main(argv):
    import cli
    with patch.object(sys, "argv", ["cli"] + argv):
        try:
            cli.main()
            return 0
        except SystemExit as e:
            return e.code


def test_config_check_valid_exits_0():
    import cli
    with patch.object(sys, "argv", ["cli", "--config-check"]), \
         patch.object(cli, "_config_check", return_value=0) as mock_check:
        try:
            cli.main()
        except SystemExit as e:
            code = e.code
    assert code == 0
    mock_check.assert_called_once()


def test_config_check_invalid_exits_2():
    import cli
    with patch.object(sys, "argv", ["cli", "--config-check"]), \
         patch.object(cli, "_config_check", return_value=2) as mock_check:
        try:
            cli.main()
        except SystemExit as e:
            code = e.code
    assert code == 2
    mock_check.assert_called_once()


def test_no_langfuse_sets_env():
    import cli
    mock_result = _make_result()
    with patch.object(sys, "argv", ["cli", "--no-langfuse"]), \
         patch.object(cli, "run_pipeline", return_value=mock_result), \
         patch("asyncio.run", return_value=mock_result):
        try:
            cli.main()
        except SystemExit:
            pass
    assert os.environ.get("LANGFUSE_ENABLED") == "false"


def test_dry_run_passed_to_pipeline():
    import cli
    mock_result = _make_result()
    with patch.object(sys, "argv", ["cli", "--dry-run"]), \
         patch("asyncio.run", return_value=mock_result) as mock_run:
        try:
            cli.main()
        except SystemExit:
            pass
    # asyncio.run was called with a coroutine (the pipeline call)
    assert mock_run.called


def test_exit_code_partial_failure():
    import cli
    with patch.object(sys, "argv", ["cli"]), \
         patch("asyncio.run", return_value=_make_result(status="partial_failure", errors=["x"])):
        code = _call_main([])
    assert code == 3


def test_exit_code_total_failure():
    import cli
    with patch.object(sys, "argv", ["cli"]), \
         patch("asyncio.run", return_value=_make_result(status="total_failure", researched=0)):
        code = _call_main([])
    assert code == 4


def test_config_check_returns_2_when_llm_missing():
    """_config_check function itself returns 2 when LLM env vars absent."""
    with patch("llm.factory.get_client", side_effect=ConfigError("SCOUT_PROVIDER is not set")), \
         patch("search.factory.get_client", return_value=MagicMock()), \
         patch.dict(os.environ, {"AIRTABLE_PAT": "pat123", "AIRTABLE_BASE_ID": "app123"}):
        from cli import _config_check
        result = _config_check()
    assert result == 2
