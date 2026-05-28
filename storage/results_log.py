import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class ResultsLog:
    def __init__(self, run_id: str, log_dir: str = "./logs"):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self._path = Path(log_dir) / f"{run_id}.results.jsonl"
        self.run_id = run_id
        self._lock = threading.Lock()

    @property
    def path(self) -> str:
        return str(self._path)

    def append(self, vc_fields: dict, draft_fields: list[dict]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "vc": vc_fields,
            "drafts": draft_fields,
        }
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        results = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                results.append(json.loads(line))
        return results
