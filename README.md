# gonzo-funnel

Multi-agent pipeline that discovers, researches, scores, and drafts VC outreach for a fundraise. Output lands in Airtable. Nothing is sent automatically.

```
scout → researcher (parallel) → scorer → drafter → Airtable
```

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Airtable account with a base configured (see [Airtable setup](#airtable-setup))
- At minimum: one LLM API key (Anthropic recommended) and one search API key (Brave recommended)

---

## Install

```bash
git clone https://github.com/aohana182/gonzo-funnel
cd gonzo-funnel
uv sync
```

---

## Configure

```bash
cp .env.example .env
chmod 600 .env   # on Linux/macOS; on Windows restrict via file properties
```

Fill in `.env`. Required fields depend on which providers you use:

| What you need | Required keys |
|---|---|
| Anthropic LLM | `{ROLE}_PROVIDER=anthropic`, `{ROLE}_API_KEY`, `{ROLE}_MODEL` |
| Brave search | `SEARCH_PROVIDER=brave`, `BRAVE_API_KEY` |
| Airtable | `AIRTABLE_PAT`, `AIRTABLE_BASE_ID` |
| Email digest | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `DIGEST_FROM`, `DIGEST_TO` |

Validate your config before running:

```bash
python -m cli --config-check
```

Fill `spec/` files with your fundraise context before the first real run. Copy the `.example` files and fill them in:

| File | What to fill in |
|---|---|
| `spec/company.md` | Company overview, tech, market, team, the ask |
| `spec/thesis.md` | What a matching VC looks like; scoring dimension definitions |
| `spec/exclusions.md` | VCs to never surface (already contacted, wrong fit, competitor investors) |
| `spec/bio.md` | Founder bio and voice rules for outreach drafts |

`spec/` is gitignored — your fundraise context never leaves your machine.

---

## Airtable setup

Create two tables manually in your Airtable base:

- **VCs** — fields described in `docs/architecture.md` (Data Flow section)
- **Drafts** — same

Then verify the schema matches:

```bash
python setup_airtable.py
```

The script checks field parity and exits 0 if clean, 2 if anything is missing or mismatched. It makes no changes to your base.

---

## Run

**Dry run** (no Airtable writes, no email):

```bash
python -m cli --dry-run --limit 3
```

**Real run:**

```bash
python -m cli --limit 10
```

**Debug a single agent:**

```bash
python -m cli --only scout
python -m cli --only researcher --vc "Sequoia Capital"
python -m cli --only scorer --vc "Sequoia Capital"
python -m cli --only drafter --vc "Sequoia Capital"
```

**Re-research stale VCs:**

```bash
python -m cli --refresh-older-than 30
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--limit N` | `DEFAULT_RUN_LIMIT` | Cap candidates sent to researcher |
| `--dry-run` | off | No Airtable writes, no email |
| `--only ROLE` | off | Run one agent for debugging |
| `--vc NAME` | — | Required with `--only researcher/scorer/drafter` |
| `--refresh-older-than DAYS` | — | Re-research VCs older than N days |
| `--no-langfuse` | off | Disable Langfuse for this run |
| `--config-check` | — | Validate env and exit |

**Exit codes:** 0 success · 0 budget_ceiling · 2 config error · 3 partial failure · 4 fatal failure

---

## Cost

At the end of every run, a cost table prints to stdout:

```
Role         Provider     Model              Calls   Tokens In   Tokens Out   Cost USD
scout        openrouter   sonnet-4-6         1       3,200       1,100        0.027
researcher   openrouter   sonnet-4-6         10      40,000      12,000       0.300
scorer       openrouter   sonnet-4-6         10      15,000      3,500        0.097
drafter      openrouter   sonnet-4-6         7       9,000       5,600        0.111
-----------------------------------------------------------------------------------
TOTAL                                        28      67,200      22,200       0.535
```

Pricing lives in `observability/cost.py`. Update it when model prices change.

---

## Observability

**JSONL logs** are always on. One file per run at `logs/{run_id}.jsonl`.

**Langfuse** is optional. To enable:

```bash
# In .env:
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

Run Langfuse locally:

```bash
docker compose up -d
```

Access at `http://localhost:3000`.

---

## Outbound network

This pipeline connects only to:

- Anthropic API (`api.anthropic.com`)
- OpenAI API (`api.openai.com`) — if configured
- OpenRouter (`openrouter.ai`) — if configured
- Brave Search API (`api.search.brave.com`) — if configured
- Serper (`google.serper.dev`) — if configured
- Tavily (`api.tavily.com`) — if configured
- Airtable (`api.airtable.com`)
- Langfuse (self-hosted, local only)
- SMTP server of your choice

No telemetry anywhere else.

---

## Project structure

```
gonzo-funnel/
  spec/               # Your fundraise context — gitignored, never committed
    company.md        # Company overview (copy from company.md.example)
    thesis.md         # Scoring criteria (copy from thesis.md.example)
    exclusions.md     # VCs to never surface (copy from exclusions.md.example)
    bio.md            # Founder voice for outreach (copy from bio.md.example)
  llm/                # LLM provider abstraction
  search/             # Search provider abstraction
  agents/             # Scout, researcher, scorer, drafter
  storage/            # Airtable + SQLite cache
  notify/             # Email digest
  observability/      # JSONL logger, Langfuse wrapper, cost table
  tests/              # Unit tests
  docs/               # Architecture, model routing, cost model
  orchestrator.py     # Pipeline stitching + concurrency
  cli.py              # Entry point + flags
  setup_airtable.py   # Schema verification
  docker-compose.yml  # Langfuse (local)
```

---

## Tests

```bash
uv run pytest
```

Key test coverage:

| Test | What it covers |
|---|---|
| `test_llm_factory.py` | Provider resolution, bad config raises |
| `test_search_factory.py` | Same for search |
| `test_orchestrator.py` | Full pipeline with mocks, no Airtable write, exit 0 |
| `test_budget_ceiling.py` | Budget halt, no errors counted for halted VCs |
| `test_airtable_upsert.py` | Idempotent upsert, operator-only fields never overwritten |
| `test_base_agent_retry.py` | Validation error triggers one retry; two failures raise AgentError |
| `test_scorer.py` | Score invariants, go threshold, SQLite cache hit/miss |

---

## Security

- `.env` contains all secrets. Never commit it. `chmod 600` on Linux/macOS.
- `spec/` is gitignored. Your fundraise context stays local.
- Airtable PAT should be scoped to this base only.
- The `notes` and `sent_at` fields in Airtable are operator-only. Agents never overwrite them.

---

## Docs

- [`docs/architecture.md`](docs/architecture.md) — system diagram + narrative
- [`docs/model_routing.md`](docs/model_routing.md) — per-role model table + rationale
- [`docs/cost_model.md`](docs/cost_model.md) — example runs, cost ranges
