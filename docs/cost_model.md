# Cost Model

## Per-Run Estimate (10 VCs, recommended model config)

| Role | Model | Calls | Tokens In | Tokens Out | Cost USD |
|---|---|---|---|---|---|
| scout | claude-sonnet-4-6 | 1 | ~3,200 | ~1,100 | ~$0.027 |
| researcher | claude-sonnet-4-6 | 10 | ~40,000 | ~12,000 | ~$0.300 |
| scorer | claude-sonnet-4-6 | 10 | ~15,000 | ~3,500 | ~$0.097 |
| drafter | claude-sonnet-4-6 | 7 | ~9,000 | ~5,600 | ~$0.111 |
| **TOTAL** | | **28** | **~67,200** | **~22,200** | **~$0.54** |

Assumes 7 of 10 VCs score `go=True` (drafter fires for those only). Researcher input is high because fetched web page content is included in context. Scorer results are cached by SHA256 of (thesis + dossier) — repeated runs on the same VCs cost $0 for scoring.

## Weekly Cost (4 runs/month)

~$2.15/month at 10 VCs/run with the recommended config.

## Budget Levers

| To reduce cost | Change |
|---|---|
| Researcher is the token sink | Reduce `_MAX_TOTAL_FETCH_URLS` (default 3) or `_MAX_PAGE_CHARS` (default 4000) in `agents/researcher.py` |
| Scorer cache miss cost | Scorer results are cached — only new VCs incur an LLM call. No action needed. |
| Increase volume cheaply | Use `openrouter` provider with `anthropic/claude-sonnet-4-6` — same model, typically lower price |
| Max budget reduction | Swap all roles to `gpt-4.1-mini` — ~$0.04/run; quality degrades significantly |

## Cost Tracking

Every LLM call logs `tokens_in`, `tokens_out`, `cost_usd` to `logs/{run_id}.jsonl`.

At run end, the orchestrator reads the JSONL and prints a cost table:

```
Role         Provider     Model              Calls   Tokens In   Tokens Out   Cost USD
scout        openrouter   claude-sonnet-4-6  1       3,200       1,100        0.027
researcher   openrouter   claude-sonnet-4-6  10      40,000      12,000       0.300
scorer       openrouter   claude-sonnet-4-6  10      15,000      3,500        0.097
drafter      openrouter   claude-sonnet-4-6  7       9,000       5,600        0.111
──────────────────────────────────────────────────────────────────────────────────
TOTAL                                        28      67,200      22,200       0.535
```

The table is the authoritative cost figure for the run. The email digest also includes the duration.

## Search API Cost

Not tracked by the cost table (no LLM). Budget separately:

| Provider | Per 1000 queries | Per 10-VC run (3 queries × 10 VCs = 30) |
|---|---|---|
| Brave | ~$3.00 | ~$0.09 |
| Serper | ~$1.00 | ~$0.03 |
| Tavily | ~$4.00 | ~$0.12 |
