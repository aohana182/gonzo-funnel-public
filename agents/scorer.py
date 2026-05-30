import hashlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

from agents.base import BaseAgent, read_spec
from agents.researcher import VCDossier
from llm.base import LLMClient
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper

if TYPE_CHECKING:
    from storage.sqlite_cache import SqliteCache

_GO_THRESHOLD = 17


class ScoreDimension(BaseModel):
    name: str
    score: int
    rationale: str

    @model_validator(mode="after")
    def _check_bounds(self) -> "ScoreDimension":
        if not (0 <= self.score <= 5):
            raise ValueError(f"dimension score {self.score!r} is out of range 0–5")
        return self


class Score(BaseModel):
    dimensions: list[ScoreDimension]
    total: int
    go: bool
    summary: str

    @model_validator(mode="after")
    def _enforce_invariants(self) -> "Score":
        expected_total = sum(d.score for d in self.dimensions)
        if self.total != expected_total:
            raise ValueError(
                f"total {self.total} != sum of dimension scores {expected_total}"
            )
        if self.go != (self.total >= _GO_THRESHOLD):
            raise ValueError(
                f"go={self.go} inconsistent with total={self.total} (threshold {_GO_THRESHOLD})"
            )
        return self


class ScorerAgent(BaseAgent):
    role = "SCORER"

    def __init__(
        self,
        client: LLMClient,
        logger: JsonlLogger,
        langfuse: LangfuseWrapper,
        cache: "SqliteCache | None" = None,
    ):
        self._score_cache = cache
        super().__init__(client, logger, langfuse)

    def _build_system_prompt(self) -> str:
        thesis = read_spec("thesis.md")
        return (
            "You are a venture capital investment analyst. Score the VC fund dossier below "
            "against the target investor profile.\n\n"
            f"## Scoring Rubric\n{thesis}\n\n"
            "Rules:\n"
            "- Produce exactly 5 ScoreDimension entries matching the dimension names in the rubric.\n"
            "- Each score is 0–5.\n"
            f"- total must equal the arithmetic sum of all dimension scores.\n"
            f"- go must be true if and only if total >= {_GO_THRESHOLD}.\n"
            "- rationale is one sentence per dimension.\n"
            "- summary is one sentence overall."
        )

    def run(self, dossier: VCDossier, run_id: str) -> Score:
        thesis_hash = hashlib.sha256(read_spec("thesis.md").encode()).hexdigest()[:16]
        dossier_hash = hashlib.sha256(dossier.model_dump_json().encode()).hexdigest()[:16]

        if self._score_cache:
            cached = self._score_cache.get_cached_score(dossier.name, thesis_hash, dossier_hash)
            if cached:
                return Score.model_validate_json(cached)

        dossier_text = (
            f"Name: {dossier.name}\n"
            f"URL: {dossier.url}\n"
            f"Country: {dossier.country}\n"
            f"Thesis: {dossier.thesis_summary}\n"
            f"Stage Focus: {', '.join(dossier.stage_focus)}\n"
            f"Ticket Size: {dossier.ticket_size}\n"
            f"Partners: {', '.join(dossier.partners)}\n"
            f"Sources: {', '.join(dossier.sources)}"
        )
        messages = [{"role": "user", "content": f"Score this VC fund:\n\n{dossier_text}"}]
        score = self._call(
            messages=messages,
            output_model=Score,
            run_id=run_id,
            vc_name=dossier.name,
        )

        if self._score_cache:
            self._score_cache.set_cached_score(dossier.name, thesis_hash, dossier_hash, score.model_dump_json())

        return score
