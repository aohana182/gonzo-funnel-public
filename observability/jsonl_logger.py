import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def make_run_id() -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"run_{date}_{short}"


class JsonlLogger:
    # Fields safe to log — never log api keys, prompts, or raw content
    _SAFE_FIELDS = {"ts", "run_id", "role", "provider", "model", "tokens_in",
                    "tokens_out", "cost_usd", "latency_ms", "status", "error"}

    def __init__(self, run_id: str, log_dir: str = "./logs"):
        self.run_id = run_id
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self._path = Path(log_dir) / f"{run_id}.jsonl"

    @property
    def log_path(self) -> str:
        return str(self._path)

    def log(
        self,
        role: str,
        provider: str | None,
        model: str | None,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
        status: str,
        error: str | None = None,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "role": role,
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "status": status,
            "error": error,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
