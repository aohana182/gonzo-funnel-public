# gonzo-funnel

**Raising a round? gonzo-funnel handles the research half of VC prospecting.**

Every week it scouts new funds, reads their websites and portfolio pages, scores each one against your thesis, and writes personalised cold outreach for the ones worth approaching. Output lands in Airtable for review. Nothing is sent without you.

```
Your thesis + company context
        │
        ▼
  scout ──► researcher ──► scorer ──► drafter
  (finds VCs)  (builds dossier)  (scores 0–25)  (writes email + LinkedIn)
        │                                               │
        └───────────────── Airtable ◄──────────────────┘
                        (you review, you send)
```

---

## Why this exists

Finding the right VCs is repetitive: search Google, scan portfolio pages, check stage and ticket size, write a personalised email, repeat 50 times. Most of that is pattern-matching that a pipeline can do faster and more consistently than a human.

gonzo-funnel doesn't replace the relationship. It replaces the spreadsheet.

---

## What it does

**Scout** searches the web for VC funds matching your thesis and returns a ranked list of candidates.

**Researcher** reads each fund's website, portfolio, and partner pages — up to several URL fetches per VC — and builds a structured dossier.

**Scorer** reads the dossier against your thesis and scores the fit on 5 dimensions (0–5 each, 25 total). Only VCs scoring 17+ proceed to drafting.

**Drafter** writes a personalised email and LinkedIn DM for each qualifying VC, using your founder bio and voice rules.

Everything lands in Airtable. You read the drafts, edit what needs editing, and send what's worth sending.

---

## Key properties

- **Spec-driven** — your company overview, thesis, and founder voice live in local markdown files that you write once. They never leave your machine.
- **Model-agnostic** — works with Anthropic, OpenAI, OpenRouter, or any OpenAI-compatible endpoint. Mix providers per role.
- **Human in the loop** — agents write to Airtable as "Draft" status. Nothing is sent without a human decision.
- **Cheap to run** — ~$0.54 for 10 VCs end-to-end at Sonnet 4.6 prices (~$2/month running weekly).
- **Staleness tracking** — SQLite cache records when each VC was last researched. Re-research on a schedule with `--refresh-older-than`.
- **Observable** — every LLM call logged to JSONL. Optional Langfuse tracing for deeper inspection.

---

## Quick start

**1. Install**

```bash
git clone https://github.com/aohana182/gonzo-funnel
cd gonzo-funnel
uv sync
```

**2. Configure API keys**

```bash
cp .env.example .env
```

Minimum to run: one LLM key + one search key + Airtable credentials. See [Configuration](#configuration) for the full table.

**3. Fill your spec files**

Copy the `.example` files in `spec/` and fill them in:

```bash
cp spec/company.md.example spec/company.md
cp spec/thesis.md.example spec/thesis.md
cp spec/exclusions.md.example spec/exclusions.md
cp spec/bio.md.example spec/bio.md
```

`spec/` is gitignored — your fundraise context stays local.

**4. Set up Airtable**

Create the VCs and Drafts tables (field list in [`docs/architecture.md`](docs/architecture.md)), then verify:

```bash
python setup_airtable.py
```

**5. Dry run first**

```bash
uv run python -m cli --dry-run --limit 3
```

No Airtable writes, no email. Confirms the pipeline runs end-to-end and shows a cost estimate.

**6. Real run**

```bash
uv run python -m cli --limit 10
```

---

## Configuration

```bash
cp .env.example .env
```

| Category | Key variables |
|---|---|
| LLM (per role) | `{ROLE}_PROVIDER`, `{ROLE}_MODEL`, `{ROLE}_API_KEY` — roles: SCOUT, RESEARCHER, SCORER, DRAFTER |
| Search | `SEARCH_PROVIDER` (`brave`/`serper`/`tavily`), matching API key |
| Airtable | `AIRTABLE_PAT`, `AIRTABLE_BASE_ID` |
| Email digest | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `DIGEST_FROM`, `DIGEST_TO` |
| Budget cap | `MAX_COST_USD` — halt the run if spend exceeds this |
| Concurrency | `MAX_CONCURRENCY` (default 4) |

Supported LLM providers: `anthropic`, `openai`, `openrouter`, `openai_compatible` (Ollama, vLLM, etc.).

Validate before running:

```bash
uv run python -m cli --config-check
```

---

## Spec files

The four files in `spec/` are the only project-specific input. Everything else is generic infrastructure.

| File | What to write |
|---|---|
| `company.md` | What you built, for whom, why now, the ask |
| `thesis.md` | What a matching VC looks like — sector focus, stage, ticket size, geography. Also defines the 5 scoring dimensions. |
| `exclusions.md` | VCs to never surface — already contacted, wrong fit, competitor investors |
| `bio.md` | Founder bio and voice rules — tone, what to lead with, signature |

Start from the `.example` files in `spec/`.

---

## CLI reference

```bash
uv run python -m cli [flags]
```

| Flag | Default | What it does |
|---|---|---|
| `--limit N` | 10 | Max VCs to research per run |
| `--dry-run` | off | No Airtable writes, no email |
| `--only ROLE` | — | Run one agent for debugging (`scout`, `researcher`, `scorer`, `drafter`) |
| `--vc NAME` | — | VC name, required with `--only researcher/scorer/drafter` |
| `--refresh-older-than DAYS` | — | Re-research VCs last updated more than N days ago |
| `--no-langfuse` | off | Disable Langfuse tracing for this run |
| `--config-check` | — | Validate env and exit |

Exit codes: `0` success / budget ceiling · `2` config error · `3` partial failure · `4` fatal failure

---

## Cost

At the end of every run, a cost table prints to stdout:

```
Role         Provider     Model              Calls   Tokens In   Tokens Out   Cost USD
scout        openrouter   claude-sonnet-4-6  1       3,200       1,100        0.027
researcher   openrouter   claude-sonnet-4-6  10      40,000      12,000       0.300
scorer       openrouter   claude-sonnet-4-6  10      15,000      3,500        0.097
drafter      openrouter   claude-sonnet-4-6  7       9,000       5,600        0.111
──────────────────────────────────────────────────────────────────────────────────
TOTAL                                        28      67,200      22,200       0.535
```

Assumes 7 of 10 VCs pass the scoring threshold. Scorer results are cached — re-runs on already-researched VCs cost $0 for that stage.

Full cost breakdown: [`docs/cost_model.md`](docs/cost_model.md)

---

## Observability

**JSONL logs** are always on. One file per run at `logs/{run_id}.jsonl`. Every LLM call, token count, and cost is recorded.

**Langfuse** is optional. Self-hosted via the included `docker-compose.yml`:

```bash
docker compose up -d   # starts Langfuse at localhost:3000
```

Then set in `.env`:
```
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

---

## Outbound connections

The pipeline connects only to the APIs you configure:

- LLM provider (Anthropic / OpenAI / OpenRouter / self-hosted)
- Search provider (Brave / Serper / Tavily)
- `api.airtable.com`
- Langfuse (self-hosted, local only)
- SMTP server of your choice

No telemetry elsewhere.

---

## Docs

- [`docs/architecture.md`](docs/architecture.md) — full system diagram, component map, Airtable field reference
- [`docs/model_routing.md`](docs/model_routing.md) — per-role model recommendations and provider compatibility
- [`docs/cost_model.md`](docs/cost_model.md) — cost estimates, budget levers, search API pricing
