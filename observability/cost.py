import logging

logger = logging.getLogger(__name__)

# Prices per million tokens (input, output).
# This is the only place prices live — update here when model pricing changes.
_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7":   (15.00,  75.00),
    "claude-sonnet-4-6": (3.00,   15.00),
    "claude-haiku-4-5":  (0.80,    4.00),
    # OpenAI
    "gpt-4o":            (2.50,   10.00),
    "gpt-4o-mini":       (0.15,    0.60),
    "gpt-4.1":           (2.00,    8.00),
    "gpt-4.1-mini":      (0.40,    1.60),
    # OpenRouter — same model IDs but prefixed differently at the API level;
    # most operators configure the underlying model name directly.
    "openai/gpt-4o":               (2.50,  10.00),
    "anthropic/claude-sonnet-4-6": (3.00,  15.00),
    "anthropic/claude-opus-4-7":   (15.00, 75.00),
}


def calculate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float | None:
    if model not in _PRICES:
        logger.warning("No price entry for model %r (provider=%r) — cost will be null", model, provider)
        return None
    price_in, price_out = _PRICES[model]
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
