# CLAUDE.md — gonzo-funnel

## What this is

Multi-agent VC investor pipeline. Agents discover, research, score, and draft outreach to VCs. Output lands in Airtable. No agent sends anything.

## Rules

- No em-dashes. No AI markers. No flattery. Factual register only.
- No scope creep. If something is not in the PRD, stop and ask before building.
- Ambiguities go in QUESTIONS.md before any code is written.
- MECE outputs. Every agent returns a typed Pydantic model.
- One direction: spec/ and raw inputs feed agents. Agents write to Airtable. Nothing flows backwards.

## Architecture decisions (baked in)

- LLM clients are sync. Orchestrator uses asyncio.to_thread for bounded concurrency.
- setup_airtable.py is verify-only — no destructive Meta API calls.
- OPERATOR_ONLY_FIELDS = frozenset({"notes", "sent_at"}) — excluded from all Airtable upsert payloads, always.
- Local-first deployment. No systemd/VPS until pipeline is proven.

## Source of truth

This file is the engineering rules. spec/ files are the fundraise context. If they conflict, ask the operator.

## Before every commit

1. git diff --staged — confirm intent
2. Scan for secrets: api_key, token, password, secret, Bearer
3. Run pytest
