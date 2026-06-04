<p align="center">
  <img src="assets/banner.png" alt="gonzo-funnel" width="100%">
</p>

# gonzo-funnel

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/aohana182/gonzo-funnel/issues"><img src="https://img.shields.io/badge/Issues-welcome-yellow?style=for-the-badge" alt="Issues"></a>
</p>

**Automated pipeline that scouts VCs, researches them, scores fit against your fundraise thesis, and writes outreach drafts -- output lands in Airtable, nothing is sent without your review.**

<table>
<tr><td><b>Search-augmented scout</b></td><td>Brave queries surface funders outside LLM training data; a seen-names cache prevents repeats across runs.</td></tr>
<tr><td><b>Parallel researcher</b></td><td>Up to 4 concurrent web-research pipelines produce structured dossiers per VC.</td></tr>
<tr><td><b>Scored go/no-go</b></td><td>5-dimension LLM scoring (0-5 each); only candidates at or above a configurable threshold get drafts written.</td></tr>
<tr><td><b>Channel-specific drafts</b></td><td>Email and LinkedIn outreach written in the founder's voice; stored in Airtable, never auto-sent.</td></tr>
<tr><td><b>Budget controls</b></td><td>Per-run cost ceiling, SQLite scorer cache (repeated VCs cost $0 to score), cost table after every run.</td></tr>
</table>

---

## Quick start

```sh
git clone https://github.com/aohana182/gonzo-funnel
cd gonzo-funnel
uv sync --extra dev
cp .env.example .env   # fill in values
uv run python -m cli --config-check
uv run python -m cli --dry-run --limit 5
```

---

## Spec files

All agent context lives in `spec/`. Fill these before running.

| File | Contents | When to update |
|---|---|---|
| `spec/company.md` | Company overview, tech, market, team, the ask | When the pitch changes |
| `spec/thesis.md` | Angel investor scoring rubric (5 dimensions, go threshold) | When angel targeting criteria change |
| `spec/thesis_vc.md` | VC fund scoring rubric (5 dimensions, go threshold) | When fund targeting criteria change |
| `spec/exclusions.md` | Investors to skip -- already contacted, wrong fit | After each outreach wave |
| `spec/bio.md` | Founder bio and voice rules for drafts | Rarely |

The researcher infers `investor_type` ("angel" or "vc_fund") from evidence. The scorer
automatically picks the matching rubric file. New projects: copy both thesis files and edit.

---

## Airtable schema

**VC_TABLE** fields: `name`, `investor_type`, `url`, `country`, `thesis_summary`, `stage_focus`, `ticket_size`, `partners`, `score`, `score_breakdown`, `status`, `last_updated`, `dossier`, `sources`, `notes`

`investor_type` is a single-select field with values `angel` and `vc_fund`. Add it to your base before running.

**DRAFTS** fields: `VC` (link to VC_TABLE), `partner_name`, `channel`, `subject`, `body`, `status`, `created`, `sent_at`

`notes` and `sent_at` are operator-only -- agents never overwrite them.

Run `uv run python setup_airtable.py` to verify your schema matches.

---

## Environment variables

| Variable | Description |
|---|---|
| `{ROLE}_PROVIDER` | LLM provider per agent role: `scout`, `researcher`, `scorer`, `drafter`. Use `openrouter`, `anthropic`, etc. |
| `{ROLE}_MODEL` | Model ID per role, e.g. `anthropic/claude-sonnet-4-6` |
| `{ROLE}_API_KEY` | API key for that provider |
| `SEARCH_PROVIDER` | `brave`, `serper`, or `tavily` |
| `BRAVE_API_KEY` | Brave Search API key (free tier works) |
| `AIRTABLE_PAT` | Airtable personal access token |
| `AIRTABLE_BASE_ID` | Airtable base ID |
| `MAX_COST_USD` | Optional per-run budget ceiling -- pipeline halts if exceeded |
| `MAX_CONCURRENCY` | Parallel VC pipelines (default 4) |
| `LANGFUSE_ENABLED` | `true` to enable Langfuse tracing (requires `LANGFUSE_HOST`, `_PUBLIC_KEY`, `_SECRET_KEY`) |
| `GOOGLE_SHEETS_ID` | ID of the native Google Sheet used as the tracker working surface |
| `GAS_WEBHOOK_URL` | Deployment URL of the Google Apps Script web app that writes to the Sheet |
| `GAS_WEBHOOK_SECRET` | Secret token included in every POST to the GAS webhook |

Copy `.env.example` and fill in values.

---

## Tracker (working surface)

The pipeline writes to Airtable only. A separate sync script pushes pipeline output to a Google Sheet for operator use:

```
Airtable (pipeline DB, append-only)
    |
    v
sync_to_sheets.py  --  reads Airtable, POSTs JSON to a Google Apps Script webhook
    |
    v
Google Sheet: 4 tabs
  targets    GO investors (score >= threshold), full detail. Replaced each sync.
  tracker    Outreach log. New GO names appended; existing rows never touched.
  no_go      Below-threshold records, summary only. Replaced each sync.
  changelog  One row per run: date, counts.
```

**Auth:** The sync uses a Google Apps Script web app deployed inside the Sheet itself. GAS runs with the sheet owner's permissions -- no GCP project, no service account, no OAuth flow required.

**Setup (one-time):**
1. Open the Sheet -> Extensions -> Apps Script -> paste `gas_webhook.js` -> deploy as web app (Execute as: Me, Access: Anyone)
2. Add `GAS_WEBHOOK_URL` and `GAS_WEBHOOK_SECRET` to `.env`
3. Run `uv run python _migrate_ngo_tracker.py` to seed the tracker with any existing NGO/grant rows (skip if starting fresh)
4. Run `uv run python sync_to_sheets.py`

**Tracker tab** is a unified outreach log: NGO grant rows and angel investor rows coexist, distinguished by the `type` column. Columns: `Organization | Type | Tier | Score | Status | Date | Comments | Last Action`. New GO investors are appended on each sync; existing rows are never touched.

**Rule:** Never add manual-tracking columns to Airtable. Airtable is append-only pipeline output; the Sheet is the operator's working surface.

---

## Tech stack

- Python 3.11 + Pydantic v2 -- typed agent I/O throughout
- asyncio + `to_thread` -- bounded parallel VC pipelines
- OpenRouter (recommended) -- per-role LLM routing without provider lock-in
- Brave Search -- web discovery for scout and researcher agents
- Airtable (pyairtable) -- output storage
- SQLite -- scorer cache and seen-names deduplication
- Langfuse (optional) -- LLM trace observability
- uv -- package and virtualenv management

---

## Scripts

**Windows (PowerShell) — run this first every session:**
```powershell
$env:Path = "C:\Users\avioh\.local\bin;$env:Path"
cd C:\Users\avioh\gonzo-funnel
```

| Command | Description |
|---|---|
| `uv run python -m cli --limit 10` | Full pipeline run, up to 10 VCs |
| `uv run python -m cli --dry-run --limit 5` | No Airtable writes, no email |
| `uv run python -m cli --only scout` | Scout only -- print candidates as JSON |
| `uv run python -m cli --only researcher --vc "Name"` | Research a single named VC |
| `uv run python -m cli --only scorer --vc "Name"` | Score a single named VC |
| `uv run python -m cli --only drafter --vc "Name"` | Draft outreach for a single named VC |
| `uv run python -m cli --refresh-older-than 30` | Re-research VCs not updated in N days |
| `uv run python -m cli --push-run RUN_ID` | Push a saved results file to Airtable |
| `uv run python -m cli --config-check` | Validate env config and exit |
| `uv run python setup_airtable.py` | Verify Airtable schema |
| `uv run python logs/dump_airtable.py` | Print current Airtable counts (total / GO / no-go) |
| `uv run python sync_to_sheets.py` | Sync Airtable output to Google Sheet (4 tabs) |
| `uv run python _migrate_ngo_tracker.py` | One-time: seed tracker tab with existing NGO/grant rows |
| `uv run python -m pytest tests/ -q` | Run test suite |

---

## Key numbers

| Metric | Value |
|---|---|
| Scoring threshold | 17/25 (code enforced) -- only investors at or above this get drafts |
| Cost per 5 VCs | ~$0.21 (Sonnet 4.6 via OpenRouter, measured) |
| Search rate limit | 1 req/sec -- Brave free tier, enforced automatically |
| Concurrency | 4 parallel VC pipelines |
| Scorer cache | SQLite -- repeated runs on the same VC cost $0 for scoring |

---

## Design decisions (baked in, applies to all forks)

**1. `investor_type` field is set by the researcher, not the operator.**
The model infers from evidence whether the subject is an individual angel or a fund. This drives which scoring rubric is loaded (`thesis.md` vs `thesis_vc.md`) and which contact-discovery path the researcher follows. It also lets you filter the Airtable view by type. New projects: add both thesis files; the rest is automatic.

**2. Scorer picks rubric per dossier, not per run.**
A single run can produce a mixed batch (angels + funds). The scorer selects `thesis.md` or `thesis_vc.md` at score time based on `investor_type`. This is thread-safe: the system prompt is passed per-call via `BaseAgent._call(system=...)` rather than mutating shared state. Cache keys include a hash of the selected thesis, so changing either rubric auto-invalidates only the relevant entries.

**3. Reachability is a first-class research output, not a post-processing step.**
`contact_info` is a required field on `VCDossier`, populated by the researcher's 4th search query and 7th research area. Adding it as an afterthought requires a full `--refresh-older-than 0` re-run (~$2.60 for 53 records). Build it in from day one on any fork. Contact discovery differs by type: angels need LinkedIn/Twitter/email/AngelList; funds need partner LinkedIn, pitch form URL, and warm-intro path.

---

## Pitfalls

**ASCII-only in agent prompt strings.** Non-ASCII characters in Python source strings (`<=`, `>=`, `--`, etc.) cause `UnicodeEncodeError: charmap codec` on Windows when stdout is redirected. Spec files are read with `encoding='utf-8'` and are safe; only Python source strings in agent prompts are at risk.

**Score variability on borderline candidates.** A VC scoring 16-17 on two consecutive runs is not a reliable go. Brave returns different search results each time, so dossier content changes and scores swing 3-4 points. Treat 15-18 as "worth a manual look."

**Add `investor_type` to Airtable before running.** The pipeline writes this field on every record. If the field is missing in your base, `uv run python setup_airtable.py` will report the mismatch. Add it as a single-select with options `angel` and `vc_fund`.

---

## Docs

- [`docs/architecture.md`](docs/architecture.md) -- pipeline diagram, component map
- [`docs/model_routing.md`](docs/model_routing.md) -- per-role model config
- [`docs/cost_model.md`](docs/cost_model.md) -- cost estimates and budget levers

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, commit format, and PR process.

---

## License

MIT -- see [LICENSE](LICENSE).
