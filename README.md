# gonzo-funnel — Icegate VC pipeline

Weekly automated pipeline: finds VCs, researches them, scores against the Icegate thesis, writes outreach drafts. Output lands in Airtable. Nothing is sent automatically.

**Status:** Live as of 2026-05-28. 102 tests passing. First real run pending.

---

## Run it

```powershell
$env:Path = "C:\Users\avioh\.local\bin;$env:Path"
cd C:\Users\avioh\gonzo-funnel
uv run python -m cli --limit 10
```

Dry run first (no Airtable writes, no email):

```powershell
uv run python -m cli --dry-run --limit 10
```

After a run, check Airtable. New VCs appear in VC_TABLE; qualifying drafts appear in DRAFTS with status "Draft".

---

## Key numbers

| Thing | Value |
|---|---|
| Scoring threshold | 17/25 — only VCs at or above this get drafts |
| Cost per 10 VCs | ~$0.54 (Sonnet 4.6 via OpenRouter) |
| Search rate limit | 1 req/sec — Brave free tier, automatically enforced |
| Concurrency | 4 parallel VC pipelines |
| Scorer cache | SQLite — repeated runs on the same VC cost $0 for scoring |

---

## Spec files

All agent context lives in `spec/`. These files are gitignored and never leave this machine.

| File | What's in it | When to update |
|---|---|---|
| `spec/icegate.md` | Company overview, tech, market, team, the ask | When the pitch changes |
| `spec/thesis.md` | Matching VC profile + 5 scoring dimension definitions | When targeting criteria change |
| `spec/exclusions.md` | VCs to skip — already contacted, wrong fit | After each outreach wave |
| `spec/bio.md` | Founder bio and voice rules for drafts | Rarely |

---

## Airtable

Base: `apperqHgWUi0qBkMg`

**VC_TABLE** fields: `name`, `url`, `country`, `thesis_summary`, `stage_focus`, `ticket_size`, `partners`, `score`, `score_breakdown`, `status`, `last_updated`, `dossier`, `sources`, `notes`

**DRAFTS** fields: `VC` (link), `partner_name`, `channel`, `subject`, `body`, `status`, `created`, `sent_at`

`notes` and `sent_at` are operator-only — agents never touch them.

---

## Common commands

```powershell
# Verify setup
uv run python -m cli --config-check
uv run python setup_airtable.py

# Debug one agent
uv run python -m cli --only scout
uv run python -m cli --only researcher --vc "Sequoia Capital"
uv run python -m cli --only scorer --vc "Sequoia Capital"
uv run python -m cli --only drafter --vc "Sequoia Capital"

# Re-research VCs older than 30 days
uv run python -m cli --refresh-older-than 30

# Run tests
uv run python -m pytest tests/ -q
```

---

## Logs and cost

Every run writes a JSONL file to `logs/{run_id}.jsonl`. Cost table prints to stdout at the end of each run.

Optional: Langfuse traces at `localhost:3000` — start with `docker compose up -d`.

---

## Two-repo setup

Changes go in this repo. To publish to the public repo:

```powershell
Copy-Item "C:\Users\avioh\gonzo-funnel\<changed>" "C:\Users\avioh\gonzo-funnel-public\<changed>" -Recurse -Force
cd C:\Users\avioh\gonzo-funnel-public
git add .
git commit -m "sync: <what changed>"
git push
```

Never sync: `spec/`, `docs/PRD.md`, `docs/PLAN.md`, `memory.md`, `HANDOFF.md`.

---

## Docs

- [`docs/architecture.md`](docs/architecture.md) — pipeline diagram, component map
- [`docs/model_routing.md`](docs/model_routing.md) — per-role model config
- [`docs/cost_model.md`](docs/cost_model.md) — cost estimates and budget levers
- [`docs/PRD.md`](docs/PRD.md) — full product spec
- `memory.md` — session decisions, deferred items, open questions
- `HANDOFF.md` — current state, environment, traps to avoid
