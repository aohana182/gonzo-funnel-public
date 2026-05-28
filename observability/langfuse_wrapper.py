import os
from typing import Any


class _NoopSpan:
    def end(self, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class LangfuseWrapper:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._enabled = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
        self._trace: Any = None

        if self._enabled:
            try:
                from langfuse import Langfuse
                self._lf = Langfuse()
                self._trace = self._lf.trace(name=run_id, tags=[run_id])
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Langfuse init failed: %s", e)
                self._enabled = False

    def span(self, name: str, role: str, vc_name: str | None = None) -> Any:
        if not self._enabled or self._trace is None:
            return _NoopSpan()
        try:
            return self._trace.span(
                name=name,
                metadata={"role": role, "vc_name": vc_name, "run_id": self.run_id},
            )
        except Exception:
            return _NoopSpan()

    def flush(self) -> None:
        if self._enabled:
            try:
                self._lf.flush()
            except Exception:
                pass
