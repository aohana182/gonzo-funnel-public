"""
Sync Airtable pipeline output to Google Sheet via GAS webhook.

Tabs:
  targets    -- GO investors (score >= 17). Fully replaced each run.
  tracker    -- Append-only outreach log. New GO names appended; existing rows untouched.
  no_go      -- Below-threshold records. Fully replaced each run.
  changelog  -- One row appended per run.

Setup (one-time):
  1. Deploy gas_webhook.js in the Sheet (see HANDOFF.md for step-by-step)
  2. Set GAS_WEBHOOK_URL and GAS_WEBHOOK_SECRET in .env

Run:
  uv run python sync_to_sheets.py
"""

import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()


def _get_drafts(drafts_table) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for record in drafts_table.all():
        f = record["fields"]
        vc_links = f.get("VC", [])
        if not vc_links:
            continue
        vc_id = vc_links[0]
        out.setdefault(vc_id, {})[f.get("channel", "")] = f.get("body", "")
    return out


def _target_row(record: dict, drafts_by_vc: dict) -> dict:
    f = record["fields"]
    drafts = drafts_by_vc.get(record["id"], {})
    contact = f.get("dossier", "") or ""
    return {
        "name": f.get("name", ""),
        "investor_type": f.get("investor_type", ""),
        "score": f.get("score", ""),
        "country": f.get("country", ""),
        "stage_focus": f.get("stage_focus", ""),
        "ticket_size": f.get("ticket_size", ""),
        "contact_info": contact,
        "score_breakdown": f.get("score_breakdown", "") or "",
        "email_draft": drafts.get("Email", ""),
        "linkedin_draft": drafts.get("LinkedIn DM", ""),
        "last_updated": f.get("last_updated", ""),
    }


def _tracker_candidate(record: dict, drafts_by_vc: dict) -> dict:
    f = record["fields"]
    contact = f.get("dossier", "") or ""
    return {
        "organization": f.get("name", "").strip(),
        "type": "angel",
        "tier": "",
        "score": f.get("score", ""),
        "status": "pending",
        "date": "",
        "comments": contact[:120] if contact else "",
        "last_action": "",
    }


def _nogo_row(record: dict) -> dict:
    f = record["fields"]
    return {
        "name": f.get("name", ""),
        "investor_type": f.get("investor_type", ""),
        "score": f.get("score", ""),
        "country": f.get("country", ""),
        "stage_focus": f.get("stage_focus", ""),
        "last_updated": f.get("last_updated", ""),
    }


def main() -> None:
    gas_url = os.environ.get("GAS_WEBHOOK_URL", "").strip()
    gas_secret = os.environ.get("GAS_WEBHOOK_SECRET", "").strip()
    pat = os.environ.get("AIRTABLE_PAT", "").strip()
    base_id = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    vcs_table_name = os.environ.get("AIRTABLE_VCS_TABLE", "VCs").strip()
    drafts_table_name = os.environ.get("AIRTABLE_DRAFTS_TABLE", "Drafts").strip()

    if not gas_url:
        raise SystemExit("GAS_WEBHOOK_URL not set in .env")
    if not gas_secret:
        raise SystemExit("GAS_WEBHOOK_SECRET not set in .env")

    print("Connecting to Airtable...")
    api = Api(pat)
    vcs_table = api.table(base_id, vcs_table_name)
    drafts_table = api.table(base_id, drafts_table_name)

    print("Reading drafts...")
    drafts_by_vc = _get_drafts(drafts_table)

    print("Reading VC records...")
    vc_records = vcs_table.all()
    print(f"  {len(vc_records)} total records")

    go_records = [r for r in vc_records if r["fields"].get("status") == "draft_ready"]
    nogo_records = [r for r in vc_records if r["fields"].get("status") != "draft_ready"]
    go_records.sort(key=lambda r: -(r["fields"].get("score") or 0))
    nogo_records.sort(key=lambda r: -(r["fields"].get("score") or 0))
    print(f"  GO: {len(go_records)}  no-go: {len(nogo_records)}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload = {
        "secret": gas_secret,
        "timestamp": now,
        "targets": [_target_row(r, drafts_by_vc) for r in go_records],
        "no_go": [_nogo_row(r) for r in nogo_records],
        "tracker_candidates": [_tracker_candidate(r, drafts_by_vc) for r in go_records],
    }

    print(f"POSTing to GAS ({len(go_records)} targets, {len(nogo_records)} no-go)...")
    resp = httpx.post(gas_url, json=payload, timeout=60, follow_redirects=True)
    resp.raise_for_status()

    result = resp.json()
    if "error" in result:
        raise SystemExit(f"GAS error: {result['error']}")

    print(f"  targets written:  {result.get('targets_written', '?')}")
    print(f"  no_go written:    {result.get('nogo_written', '?')}")
    print(f"  tracker appended: {result.get('tracker_appended', '?')}")
    print("Done.")


if __name__ == "__main__":
    main()
