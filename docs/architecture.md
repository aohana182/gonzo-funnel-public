# Architecture

## Overview

Gonzo Funnel is a multi-agent pipeline that runs weekly to discover, research, score, and draft VC outreach for a fundraise.

```
┌─────────────────────────────────────────────────────────────┐
│                        cli.py / cron                        │
└───────────────────────┬─────────────────────────────────────┘
                        │ asyncio
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      orchestrator.py                         │
│                                                             │
│  1. ScoutAgent.run()           (serial, 1 LLM call)         │
│  2. asyncio.gather(            (parallel, up to N workers)  │
│       for each candidate:                                   │
│         ResearcherAgent.run()                               │
│         ScorerAgent.run()                                   │
│         DrafterAgent.run()   ← skips if score.go == False   │
│         AirtableStorage.upsert_vc()                         │
│         AirtableStorage.upsert_drafts()                     │
│     )                                                       │
│  3. send_digest()              (email top-5 scored VCs)      │
└─────────────────────────────────────────────────────────────┘
```

Concurrency is bounded by `MAX_CONCURRENCY` (default 4) via `asyncio.Semaphore`. Failures are isolated per VC via `return_exceptions=True` — one bad VC does not abort the run.

---

## Component Map

```
gonzo-funnel/
  cli.py                 Entry point. Argparse, config-check, --only debug mode.
  orchestrator.py        Pipeline stitching. RunResult, cost table, digest call.

  agents/
    base.py              BaseAgent ABC: _call() wraps LLM + tool_choice structured output. One retry on validation error.
    scout.py             Reads spec/, searches for VC candidates, returns list.
    researcher.py        3 searches + up to _MAX_TOTAL_FETCH_URLS URL fetches per VC → VCDossier.
    scorer.py            Pure LLM scoring of dossier against thesis → Score. SHA256-keyed SQLite cache.
    drafter.py           Outreach drafts (email + LinkedIn DM) → Drafts | None.

  llm/
    base.py              LLMClient ABC, LLMResponse, tool schema conversion.
    anthropic_client.py  Anthropic SDK. tool_choice={"type":"tool"} for structured output.
    openai_client.py     OpenAI SDK. Converts Anthropic-style tool schema to OpenAI format.
    openrouter_client.py Thin delegate to openai_client with base_url=openrouter.ai.
    factory.py           Reads {ROLE}_PROVIDER env var, returns the right client.

  search/
    base.py              SearchClient ABC, SearchResult.
    brave.py             Brave Search API.
    serper.py            Google Serper API.
    tavily.py            Tavily AI search.
    factory.py           Reads SEARCH_PROVIDER, returns the right client.

  storage/
    airtable.py          Upsert VCs and Drafts. OPERATOR_ONLY_FIELDS = {"notes", "sent_at"} never overwritten.
    sqlite_cache.py      VCDossier cache (name, freshness_days) + scorer cache (vc_name, thesis_hash, dossier_hash).

  notify/
    email.py             HTML digest via SMTP TLS. Skips gracefully when unconfigured.

  observability/
    jsonl_logger.py      Always-on JSONL log per run. Structured events per LLM call.
    langfuse_wrapper.py  Optional Langfuse tracing (self-hosted).
    cost.py              Per-model price table. calculate_cost() → USD.

  spec/                  Fundraise context — gitignored, human-maintained (company.md, thesis.md, exclusions.md, bio.md).
  systemd/               gonzo-funnel.service + .timer for Linux deployment.
  docker-compose.yml     Langfuse v3 + Postgres 15 + ClickHouse 24 (local only).
```

---

## Data Flow

```
spec/company.md + spec/thesis.md + spec/exclusions.md
        │
        ▼
  ScoutAgent  ──── search API ──→  [VCCandidate, ...]
        │
        ▼ (parallel)
  ResearcherAgent ─── search API + httpx fetch ──→  VCDossier
        │
        ▼
  ScorerAgent (pure LLM) ──→  Score(total, go, dimensions, summary)
        │
        ├─── go=False ──→  AirtableStorage.upsert_vc()  (score stored, no draft)
        │
        └─── go=True  ──→  DrafterAgent ──→  Drafts(email, linkedin_dm)
                                   │
                                   ▼
                        AirtableStorage.upsert_vc() + upsert_drafts()
```

---

## Structured Output Pattern

All agents use `tool_choice` forcing to extract typed output from the LLM:

1. Agent defines a Pydantic model (e.g., `VCDossier`, `Score`, `Drafts`)
2. `BaseAgent._call()` converts it to a tool schema and passes `tool_choice={"type":"tool", "name": model.__name__}`
3. LLM is forced to call the tool (never returns free text)
4. `_call()` extracts `tool_calls[0]["input"]` and validates it into the Pydantic model
5. Validation errors surface as `AgentError` with the raw LLM output for debugging

This pattern eliminates JSON parsing fragility and gives runtime type guarantees on all agent outputs.

---

## Failure Modes

| Failure | Behavior |
|---|---|
| Single VC research fails | Logged, counted in `result.errors`, pipeline continues |
| All VCs fail | `result.status == "total_failure"`, exit code 4 |
| >0 but <all VCs fail | `result.status == "partial_failure"`, exit code 3 |
| Airtable upsert fails | Same as above |
| Budget ceiling hit | `result.status == "budget_ceiling"`, exit code 0; halted VCs not counted as errors |
| SMTP not configured | Warning emitted, run succeeds |
| Langfuse down | Warning emitted, run succeeds |
| LLM validation error | One retry with error text appended; `AgentError` raised after second failure |

---

## Deployment

**Local / one-shot:**
```bash
uv run python -m cli --limit 10
```

**Linux systemd (weekly):**
```bash
cp systemd/gonzo-funnel.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gonzo-funnel.timer
```

The timer fires Mondays at 06:00 UTC with up to 5 minutes of random jitter. `Persistent=true` re-fires if the machine was off at trigger time.
