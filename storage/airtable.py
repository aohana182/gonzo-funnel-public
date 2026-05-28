import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pyairtable import Api
from pyairtable.formulas import match

from errors import ConfigError

if TYPE_CHECKING:
    from storage.sqlite_cache import SqliteCache

# Fields the operator writes manually — agents never overwrite these.
OPERATOR_ONLY_FIELDS = frozenset({"notes", "sent_at"})


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_fields(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if k not in OPERATOR_ONLY_FIELDS}


class AirtableStorage:
    def __init__(self, cache: "SqliteCache | None" = None):
        pat = os.environ.get("AIRTABLE_PAT", "").strip()
        base_id = os.environ.get("AIRTABLE_BASE_ID", "").strip()
        vcs_table = os.environ.get("AIRTABLE_VCS_TABLE", "VCs").strip()
        drafts_table = os.environ.get("AIRTABLE_DRAFTS_TABLE", "Drafts").strip()

        if not pat:
            raise ConfigError("AIRTABLE_PAT is not set")
        if not base_id:
            raise ConfigError("AIRTABLE_BASE_ID is not set")

        api = Api(pat)
        self._vcs = api.table(base_id, vcs_table)
        self._drafts = api.table(base_id, drafts_table)
        self._cache = cache

    def upsert_vc(self, fields: dict) -> str:
        name = fields.get("name")
        if not name:
            raise ValueError("VC fields must include 'name'")

        safe = _safe_fields(fields)
        safe["last_updated"] = _now_date()

        existing = self._vcs.first(formula=match({"name": name}))
        if existing:
            record_id = existing["id"]
            self._vcs.update(record_id, safe)
        else:
            record = self._vcs.create(safe)
            record_id = record["id"]

        if self._cache:
            self._cache.update_airtable_record_id(name, record_id)

        return record_id

    def upsert_draft(self, fields: dict) -> str:
        vc_record_id = fields.get("_vc_record_id")
        partner = fields.get("partner_name", "")
        channel = fields.get("channel", "")

        existing = self._drafts.first(
            formula=match({"partner_name": partner, "channel": channel})
        )
        if existing:
            return existing["id"]

        draft_fields = _safe_fields({k: v for k, v in fields.items() if not k.startswith("_")})
        draft_fields.setdefault("status", "Draft")
        draft_fields.setdefault("created", _now_date())
        if vc_record_id:
            draft_fields["VC"] = [vc_record_id]

        record = self._drafts.create(draft_fields)
        return record["id"]
