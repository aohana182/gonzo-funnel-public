# gonzo-funnel -- Agent Context

## What this is

Multi-agent VC investor pipeline for fundraise outreach. Four agents run in sequence: Scout discovers VC candidates (Brave search + LLM recall), Researcher builds a web-sourced dossier per candidate (parallel), Scorer rates each on 5 dimensions against a configurable thesis, Drafter writes channel-specific outreach. All output goes to Airtable. No agent sends anything automatically.

The operator controls who gets contacted by reviewing Airtable before any outreach.

## Stack

- Python 3.11, Pydantic v2, asyncio
- LLM: any OpenAI-compatible provider via `llm/factory.py` (OpenRouter recommended)
- Search: Brave Search (free tier), Serper, or Tavily -- configured via `SEARCH_PROVIDER` env var
- Storage: Airtable (pyairtable) for output, SQLite for scorer cache and seen-names
- Observability: JSONL run logs in `logs/`, optional Langfuse traces
- Package manager: uv

## Structure

```
agents/         -- Scout, Researcher, Scorer, Drafter -- each returns a Pydantic model
llm/            -- LLM client abstraction + per-role factory
search/         -- SearchClient protocol + Brave/Serper/Tavily implementations
storage/        -- AirtableStorage, SqliteCache, ResultsLog
observability/  -- JsonlLogger, LangfuseWrapper
notify/         -- Email digest after each run
spec/           -- Operator-owned config files (gitignored): icegate.md, thesis.md, exclusions.md, bio.md
docs/           -- Architecture, cost model, model routing docs
cli.py          -- Entry point; --only, --dry-run, --push-run, --config-check flags
orchestrator.py -- Pipeline logic: scout -> parallel researcher/scorer/drafter -> Airtable
setup_airtable.py -- Schema verify-only (no destructive API calls)
```

## How to run

```sh
uv sync --extra dev
cp .env.example .env  # fill in values
uv run python -m cli --config-check
uv run python -m pytest tests/ -q
uv run python -m cli --dry-run --limit 5
uv run python -m cli --limit 10
```

## Key decisions

- **Sync LLM clients + asyncio.to_thread**: agents are sync; orchestrator uses `to_thread` for bounded concurrency. Do not make agents async-native.
- **Tool-forcing for JSON output**: `response_format` does nothing on the Anthropic API. All structured output is via tool-use forcing only (`_call` in `agents/base.py`).
- **OPERATOR_ONLY_FIELDS = frozenset({"notes", "sent_at"})**: these fields are never written by any agent. Applied in all upsert paths.
- **setup_airtable.py is verify-only**: it checks schema but makes no destructive Airtable Meta API calls.
- **Local-first**: no systemd or VPS. Run manually or on a schedule from the local machine.
- **Scorer cache keyed by (vc_name, thesis_hash, dossier_hash)**: repeated runs on the same VC with unchanged thesis cost $0 for scoring.

## Out of scope

- Auto-sending emails or LinkedIn messages -- agents write drafts only
- Web UI or dashboard -- Airtable is the UI
- Multi-company / multi-thesis support -- spec/ is configured for one company at a time

## Gotchas

- **uv PATH on Windows**: uv is not in the default bash PATH. Use PowerShell and prepend `$env:Path = "C:\Users\avioh\.local\bin;$env:Path"`.
- **ASCII-only in Python agent prompt strings**: non-ASCII chars (`--`, `<=`, etc.) in Python source strings cause `UnicodeEncodeError: charmap` on Windows when stdout is redirected. Spec files read with `encoding='utf-8'` are safe.
- **spec/ must be filled**: running with `[FILL IN]` placeholders in any spec file raises an error at agent startup (`read_spec` checks for unfilled placeholders).
- **Brave free tier**: 1 req/sec rate limit, enforced globally. All search calls are serialized.
- **Score variability**: borderline VCs (15-18/25) score differently on consecutive runs because Brave returns different snippets. Don't treat a single score as definitive for this range.
- **Dead Airtable fields**: `_vc_old` and `_channel_old` exist in DRAFTS from a past type migration. They are harmless; do not delete them.
- **Session start**: always read `HANDOFF.md` (gitignored, local only) before touching code. It has current Airtable state, run log, and the exact next action.
