from pydantic import BaseModel

from agents.base import AgentError, BaseAgent, read_spec
from llm.base import LLMClient
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper

_MAX_SEEN_IN_PROMPT = 200


class ScoutCandidate(BaseModel):
    name: str
    url: str
    why_match: str
    source_urls: list[str]


class _ScoutOutput(BaseModel):
    candidates: list[ScoutCandidate]


class ScoutAgent(BaseAgent):
    role = "SCOUT"

    def __init__(self, client: LLMClient, logger: JsonlLogger, langfuse: LangfuseWrapper):
        super().__init__(client, logger, langfuse)

    def _build_system_prompt(self) -> str:
        company = read_spec("icegate.md")
        thesis = read_spec("thesis.md")
        exclusions = read_spec("exclusions.md")
        return (
            "You are a venture capital researcher. Your task is to identify VC funds and angel investors "
            "that are a strong match for the company described below.\n\n"
            f"## Company\n{company}\n\n"
            f"## Target Profile\n{thesis}\n\n"
            f"## Exclusions\n{exclusions}\n\n"
            "Rules:\n"
            "- Only surface real, verifiable funds or investors.\n"
            "- For each candidate, explain concisely why they match the thesis.\n"
            "- Do not repeat any name from the exclusion list.\n"
            "- Provide at least one source URL per candidate (fund website, Crunchbase, LinkedIn, AngelList).\n"
            "- Focus on fit quality over quantity."
        )

    def run(self, run_id: str, seen_names: list[str], limit: int = 20) -> list[ScoutCandidate]:
        truncated = seen_names[:_MAX_SEEN_IN_PROMPT]
        seen_block = (
            f"\n\nAlready seen (do not repeat these):\n{chr(10).join(f'- {n}' for n in truncated)}"
            if truncated else ""
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"Find up to {limit} VC funds or investors that match the thesis. "
                    f"Return them as structured output.{seen_block}"
                ),
            }
        ]

        output: _ScoutOutput = self._call(
            messages=messages,
            output_model=_ScoutOutput,
            run_id=run_id,
        )

        seen_set = {n.lower() for n in seen_names}
        filtered = [c for c in output.candidates if c.name.lower() not in seen_set]
        return filtered[:limit]
