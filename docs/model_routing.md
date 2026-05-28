# Model Routing

Each agent role configures its LLM independently via `{ROLE}_PROVIDER` and `{ROLE}_MODEL` env vars. There is no global model setting.

## Recommended Configuration

| Role | Provider | Model | Rationale |
|---|---|---|---|
| `SCOUT` | anthropic | claude-sonnet-4-6 | Fast reasoning + large context for spec files |
| `RESEARCHER` | anthropic | claude-sonnet-4-6 | High throughput (runs in parallel per VC); long context for fetched pages |
| `SCORER` | anthropic | claude-sonnet-4-6 | Structured task with Pydantic validation safety net — Sonnet is sufficient |
| `DRAFTER` | anthropic | claude-sonnet-4-6 | Drafts need good writing, not frontier reasoning |

This is the default used in cost estimates. Adjust per budget vs quality tradeoffs.

## Supported Providers

| Provider | `{ROLE}_PROVIDER` value | Required env vars |
|---|---|---|
| Anthropic | `anthropic` | `{ROLE}_API_KEY`, `{ROLE}_MODEL` |
| OpenAI | `openai` | `{ROLE}_API_KEY`, `{ROLE}_MODEL` |
| OpenRouter | `openrouter` | `{ROLE}_API_KEY`, `{ROLE}_MODEL` |
| OpenAI-compatible | `openai_compatible` | `{ROLE}_API_KEY`, `{ROLE}_MODEL`, `{ROLE}_BASE_URL` |

`openai_compatible` covers any local endpoint (Ollama, vLLM, LM Studio, etc.) that speaks the OpenAI chat completions API.

## Per-Role Override Example

To run scorer on Opus via OpenRouter while keeping other roles on Anthropic Sonnet:

```bash
SCOUT_PROVIDER=anthropic
SCOUT_MODEL=claude-sonnet-4-6
SCOUT_API_KEY=sk-ant-...

RESEARCHER_PROVIDER=anthropic
RESEARCHER_MODEL=claude-sonnet-4-6
RESEARCHER_API_KEY=sk-ant-...

SCORER_PROVIDER=openrouter
SCORER_MODEL=anthropic/claude-opus-4-7
SCORER_API_KEY=sk-or-...

DRAFTER_PROVIDER=anthropic
DRAFTER_MODEL=claude-sonnet-4-6
DRAFTER_API_KEY=sk-ant-...
```

## Structured Output Compatibility

All agents use `tool_choice` forcing for structured output. This requires the model to support tool use. Confirmed working:

- All Anthropic Claude models (Haiku, Sonnet, Opus — any generation)
- OpenAI GPT-4o, GPT-4.1, GPT-4.1-mini
- OpenRouter with the above models as backends

Local models (via `openai_compatible`) must support tool calling. Llama 3.1 70B+ and Qwen2.5 72B+ are reliable; smaller models vary.

## Cost Table (from `observability/cost.py`)

Prices in USD per million tokens (input / output):

| Model | Input | Output |
|---|---|---|
| claude-haiku-4-5 | 0.80 | 4.00 |
| claude-sonnet-4-6 | 3.00 | 15.00 |
| claude-opus-4-7 | 15.00 | 75.00 |
| gpt-4o | 2.50 | 10.00 |
| gpt-4.1 | 2.00 | 8.00 |
| gpt-4.1-mini | 0.40 | 1.60 |

Update `observability/cost.py` when prices change.
