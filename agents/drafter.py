from pydantic import BaseModel

from agents.base import BaseAgent, read_spec
from agents.researcher import VCDossier
from agents.scorer import Score
from llm.base import LLMClient
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper


class Draft(BaseModel):
    channel: str
    subject: str
    body: str
    partner_name: str


class Drafts(BaseModel):
    drafts: list[Draft]


class DrafterAgent(BaseAgent):
    role = "DRAFTER"

    def __init__(self, client: LLMClient, logger: JsonlLogger, langfuse: LangfuseWrapper):
        super().__init__(client, logger, langfuse)

    def _build_system_prompt(self) -> str:
        company = read_spec("icegate.md")
        bio = read_spec("bio.md")
        return (
            "You are a fundraising outreach writer. Draft two outreach messages — one Email and one "
            "LinkedIn DM — from the founder to the VC partner.\n\n"
            f"## Company\n{company}\n\n"
            f"## Founder Voice and Rules\n{bio}\n\n"
            "Rules:\n"
            "- Email: subject line + body, body ≤120 words.\n"
            "- LinkedIn DM: no subject (empty string), body ≤60 words.\n"
            "- Reference one specific signal from the dossier: a portfolio company, a recent investment, "
            "or a direct quote from their stated thesis.\n"
            "- Factual register only. No fluff. No em-dashes. No AI-sounding phrases.\n"
            "- channel must be exactly 'email' or 'linkedin'."
        )

    def run(self, dossier: VCDossier, score: Score, run_id: str) -> Drafts | None:
        if not score.go:
            return None

        dossier_text = (
            f"VC Fund: {dossier.name}\n"
            f"Partners: {', '.join(dossier.partners)}\n"
            f"Thesis: {dossier.thesis_summary}\n"
            f"Stage Focus: {', '.join(dossier.stage_focus)}\n"
            f"Score: {score.total}/25 — {score.summary}"
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"Draft outreach for this VC:\n\n{dossier_text}\n\n"
                    "Produce one Email draft and one LinkedIn DM draft."
                ),
            }
        ]
        return self._call(
            messages=messages,
            output_model=Drafts,
            run_id=run_id,
            vc_name=dossier.name,
        )
