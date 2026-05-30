from pydantic import BaseModel

from agents.base import BaseAgent, read_spec
from agents.scout import ScoutCandidate
from llm.base import LLMClient
from observability.jsonl_logger import JsonlLogger
from observability.langfuse_wrapper import LangfuseWrapper
from search.base import SearchClient

_MAX_TOTAL_FETCH_URLS = 3
_MAX_PAGE_CHARS = 4000


class VCDossier(BaseModel):
    name: str
    url: str
    country: str
    thesis_summary: str
    stage_focus: list[str]
    ticket_size: str
    partners: list[str]
    sources: list[str]


class ResearcherAgent(BaseAgent):
    role = "RESEARCHER"

    def __init__(
        self,
        client: LLMClient,
        search: SearchClient,
        logger: JsonlLogger,
        langfuse: LangfuseWrapper,
    ):
        self._search = search
        super().__init__(client, logger, langfuse)

    def _build_system_prompt(self) -> str:
        company = read_spec("icegate.md")
        return (
            "You are a venture capital research analyst. Your task is to produce a factual dossier "
            "on a VC fund, based on the search results and page content provided.\n\n"
            f"## Company Seeking Funding\n{company}\n\n"
            "## What to Look For\n"
            "Gather verifiable evidence for these five areas:\n"
            "1. Mandate fit — does the funder explicitly fund anti-censorship or circumvention tools?\n"
            "2. Geographic reach — do they fund work serving users inside Russia, Iran, or China?\n"
            "3. Technology vs. advocacy — do they pay for software engineering and infrastructure, "
            "or only training, research, and advocacy?\n"
            "4. Disbursement speed — do they have a rapid-response or rolling grant mechanism, "
            "or only fixed annual cycles?\n"
            "5. Grant size — what is the typical grant range?\n\n"
            "Rules:\n"
            "- Record every source URL used in the `sources` list.\n"
            "- If a field cannot be determined from the provided content, use an empty string or empty list.\n"
            "- Do not invent facts. Only use what is in the provided search results and page content.\n"
            "- Factual register only. No fluff. No em-dashes."
        )

    def run(self, candidate: ScoutCandidate, run_id: str) -> VCDossier:
        name = candidate.name

        queries = [name, f"{name} portfolio", f"{name} investment thesis"]
        all_results = []
        for q in queries:
            all_results.extend(self._search.search(q, k=5))

        seen_urls: set[str] = set()
        fetch_urls: list[str] = []

        if candidate.url:
            fetch_urls.append(candidate.url)
            seen_urls.add(candidate.url)

        for r in all_results:
            if len(fetch_urls) >= _MAX_TOTAL_FETCH_URLS:
                break
            if r.url not in seen_urls:
                fetch_urls.append(r.url)
                seen_urls.add(r.url)

        fetched: list[tuple[str, str]] = []
        for url in fetch_urls:
            try:
                content = self._search.fetch(url)
                fetched.append((url, content[:_MAX_PAGE_CHARS]))
            except Exception:
                pass

        search_block = "\n".join(
            f"- [{r.url}] {r.title}: {r.snippet}" for r in all_results
        )
        page_block = "\n\n".join(
            f"### {url}\n{content}" for url, content in fetched
        )

        user_content = (
            f"Research this VC fund: {name}\nWebsite: {candidate.url}\n\n"
            f"## Search Results\n{search_block}\n\n"
            f"## Page Content\n{page_block}\n\n"
            "Produce a complete VCDossier."
        )

        return self._call(
            messages=[{"role": "user", "content": user_content}],
            output_model=VCDossier,
            run_id=run_id,
            vc_name=name,
        )
