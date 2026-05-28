from unittest.mock import MagicMock, patch

import pytest

from storage.airtable import OPERATOR_ONLY_FIELDS, AirtableStorage


def _make_storage():
    with patch("storage.airtable.Api") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_vcs_table = MagicMock()
        mock_drafts_table = MagicMock()
        mock_api.table.side_effect = lambda base, name: (
            mock_vcs_table if name == "VCs" else mock_drafts_table
        )
        with patch.dict("os.environ", {
            "AIRTABLE_PAT": "pat-test",
            "AIRTABLE_BASE_ID": "appTest",
            "AIRTABLE_VCS_TABLE": "VCs",
            "AIRTABLE_DRAFTS_TABLE": "Drafts",
        }):
            storage = AirtableStorage()
    return storage, mock_vcs_table, mock_drafts_table


def test_upsert_vc_creates_when_not_found():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = None
    vcs_table.create.return_value = {"id": "recABC"}

    record_id = storage.upsert_vc({"name": "Sequoia Capital", "score": 20})

    assert record_id == "recABC"
    vcs_table.create.assert_called_once()
    created_fields = vcs_table.create.call_args[0][0]
    assert created_fields["name"] == "Sequoia Capital"


def test_upsert_vc_updates_when_found():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = {"id": "recEXIST", "fields": {"name": "Sequoia Capital"}}

    record_id = storage.upsert_vc({"name": "Sequoia Capital", "score": 22})

    assert record_id == "recEXIST"
    vcs_table.update.assert_called_once()
    vcs_table.create.assert_not_called()


def test_upsert_vc_idempotent_second_call_updates():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = {"id": "recEXIST", "fields": {}}

    storage.upsert_vc({"name": "Benchmark", "score": 18})
    storage.upsert_vc({"name": "Benchmark", "score": 19})

    assert vcs_table.update.call_count == 2
    assert vcs_table.create.call_count == 0


def test_notes_never_in_upsert_payload():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = None
    vcs_table.create.return_value = {"id": "recXYZ"}

    storage.upsert_vc({
        "name": "Andreessen Horowitz",
        "score": 21,
        "notes": "DO NOT OVERWRITE — operator note",
    })

    created_fields = vcs_table.create.call_args[0][0]
    assert "notes" not in created_fields


def test_notes_in_operator_only_fields():
    assert "notes" in OPERATOR_ONLY_FIELDS


def test_upsert_draft_creates_when_not_found():
    storage, _, drafts_table = _make_storage()
    drafts_table.first.return_value = None
    drafts_table.create.return_value = {"id": "recDRAFT1"}

    record_id = storage.upsert_draft({
        "_vc_name": "Sequoia",
        "partner_name": "Roelof Botha",
        "channel": "Email",
        "body": "Hi Roelof...",
    })

    assert record_id == "recDRAFT1"
    drafts_table.create.assert_called_once()
    created = drafts_table.create.call_args[0][0]
    assert "_vc_name" not in created


def test_upsert_draft_skips_duplicate():
    storage, _, drafts_table = _make_storage()
    drafts_table.first.return_value = {"id": "recDRAFT1", "fields": {}}

    record_id = storage.upsert_draft({
        "_vc_name": "Sequoia",
        "partner_name": "Roelof Botha",
        "channel": "Email",
    })

    assert record_id == "recDRAFT1"
    drafts_table.create.assert_not_called()


def test_sent_at_in_operator_only_fields():
    assert "sent_at" in OPERATOR_ONLY_FIELDS


def test_sent_at_never_in_upsert_payload():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = None
    vcs_table.create.return_value = {"id": "recXYZ"}

    storage.upsert_vc({
        "name": "Benchmark",
        "score": 18,
        "sent_at": "2026-05-20",
    })

    created_fields = vcs_table.create.call_args[0][0]
    assert "sent_at" not in created_fields


def test_upsert_draft_vc_record_link():
    storage, _, drafts_table = _make_storage()
    drafts_table.first.return_value = None
    drafts_table.create.return_value = {"id": "recDRAFT2"}

    storage.upsert_draft({
        "_vc_name": "Sequoia",
        "_vc_record_id": "recVCABC",
        "partner_name": "Roelof Botha",
        "channel": "Email",
    })

    created = drafts_table.create.call_args[0][0]
    assert created["VC"] == ["recVCABC"]


def test_upsert_draft_safe_fields_applied():
    storage, _, drafts_table = _make_storage()
    drafts_table.first.return_value = None
    drafts_table.create.return_value = {"id": "recDRAFT3"}

    storage.upsert_draft({
        "_vc_name": "Benchmark",
        "partner_name": "Peter Fenton",
        "channel": "Email",
        "sent_at": "2026-05-20",
    })

    created = drafts_table.create.call_args[0][0]
    assert "sent_at" not in created


def test_upsert_vc_writes_record_id_to_cache():
    storage, vcs_table, _ = _make_storage()
    vcs_table.first.return_value = None
    vcs_table.create.return_value = {"id": "recNEW"}

    mock_cache = MagicMock()
    storage._cache = mock_cache

    storage.upsert_vc({"name": "Accel Partners", "score": 20})

    mock_cache.update_airtable_record_id.assert_called_once_with("Accel Partners", "recNEW")
