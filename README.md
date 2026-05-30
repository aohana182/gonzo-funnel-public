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
| `spec/icegate.md` | Company overview, tech, market, team, the ask | When the pitch changes |
| `spec/thesis.md` | Target VC profile + 5 scoring dimension definitions | When targeting criteria change |
| `spec/exclusions.md` | VCs to skip -- already contacted, wrong fit | After each outreach wave |
| `spec/bio.md` | Founder bio and voice rules for drafts | Rarely |

---

## Airtable schema

**VC_TABLE** fields: `name`, `url`, `country`, `thesis_summary`, `stage_focus`, `ticket_size`, `partners`, `score`, `score_breakdown`, `status`, `last_updated`, `dossier`, `sources`, `notes`

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

Copy `.env.example` and fill in values.

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
| `uv run python -m pytest tests/ -q` | Run test suite |

---

## Key numbers

| Metric | Value |
|---|---|
| Scoring threshold | 17/25 -- only VCs at or above this get drafts |
| Cost per 5 VCs | ~$0.21 (Sonnet 4.6 via OpenRouter, measured) |
| Search rate limit | 1 req/sec -- Brave free tier, enforced automatically |
| Concurrency | 4 parallel VC pipelines |
| Scorer cache | SQLite -- repeated runs on the same VC cost $0 for scoring |

---

## Pitfalls

**ASCII-only in agent prompt strings.** Non-ASCII characters in Python source strings (`<=`, `>=`, `--`, etc.) cause `UnicodeEncodeError: charmap codec` on Windows when stdout is redirected. Spec files are read with `encoding='utf-8'` and are safe; only Python source strings in agent prompts are at risk.

**Score variability on borderline candidates.** A VC scoring 16-17 on two consecutive runs is not a reliable go. Brave returns different search results each time, so dossier content changes and scores swing 3-4 points. Treat 15-18 as "worth a manual look."

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
