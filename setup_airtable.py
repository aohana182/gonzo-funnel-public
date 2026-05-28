"""
Verify that the Airtable base schema matches the expected schema from spec/PRD.md.
Prints pass/fail per field. Makes no changes to the base.
Exit 0 if clean, exit 2 if mismatch.
"""
import os
import sys

from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

# Expected fields per table — name: airtable field type
_EXPECTED_VCS = {
    "name":           "singleLineText",
    "url":            "url",
    "country":        "singleLineText",
    "thesis_summary": "multilineText",
    "stage_focus":    "multilineText",
    "ticket_size":    "singleLineText",
    "partners":       "multilineText",
    "score":          "number",
    "score_breakdown":"multilineText",
    "status":         "singleSelect",
    "last_updated":   "date",
    "dossier":        "multilineText",
    "sources":        "multilineText",
    "notes":          "multilineText",
}

_EXPECTED_DRAFTS = {
    "VC":           "multipleRecordLinks",
    "partner_name": "singleLineText",
    "channel":      "singleSelect",
    "subject":      "singleLineText",
    "body":         "multilineText",
    "status":       "singleSelect",
    "created":      "date",
    "sent_at":      "date",
}


def check_table(table_schema, expected: dict, table_name: str) -> int:
    actual = {f.name: f.type for f in table_schema.fields}
    errors = 0
    print(f"\n  Table: {table_name}")
    for field, ftype in expected.items():
        if field not in actual:
            print(f"    MISSING  {field!r} (expected type: {ftype})")
            errors += 1
        elif actual[field] != ftype:
            print(f"    MISMATCH {field!r}: got {actual[field]!r}, expected {ftype!r}")
            errors += 1
        else:
            print(f"    OK       {field!r}")
    return errors


def main() -> None:
    pat = os.environ.get("AIRTABLE_PAT", "").strip()
    base_id = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    vcs_table = os.environ.get("AIRTABLE_VCS_TABLE", "VCs").strip()
    drafts_table = os.environ.get("AIRTABLE_DRAFTS_TABLE", "Drafts").strip()

    if not pat or not base_id:
        print("ERROR: AIRTABLE_PAT and AIRTABLE_BASE_ID must be set in .env")
        sys.exit(2)

    print("Connecting to Airtable base...")
    api = Api(pat)
    base = api.base(base_id)

    try:
        schema = base.schema()
    except Exception as e:
        print(f"ERROR: Could not fetch schema: {e}")
        sys.exit(2)

    table_schemas = {t.name: t for t in schema.tables}
    total_errors = 0

    for table_name, expected in [(vcs_table, _EXPECTED_VCS), (drafts_table, _EXPECTED_DRAFTS)]:
        if table_name not in table_schemas:
            print(f"\n  MISSING TABLE: {table_name!r}")
            total_errors += 1
        else:
            total_errors += check_table(table_schemas[table_name], expected, table_name)

    print()
    if total_errors == 0:
        print("Schema check PASSED — all fields present and correct.")
        sys.exit(0)
    else:
        print(f"Schema check FAILED — {total_errors} issue(s) found.")
        print("Fix the Airtable base manually, then re-run this script.")
        sys.exit(2)


if __name__ == "__main__":
    main()
