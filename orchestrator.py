import asyncio
import json
import os
import time
from pathlib import Path

from agents.drafter import DrafterAgent, Drafts
from agents.researcher import ResearcherAgent, VCDossier
from agents.scorer import Score, ScorerAgent
from agents.scout import ScoutAgent, ScoutCandidate
from errors import BudgetExceededError
from llm.factory import get_client
from models import RunResult
from observability.jsonl_logger import JsonlLogger, make_run_id
from observability.langfuse_wrapper import LangfuseWrapper
from search.factory import get_client as get_search_client
from storage.airtable import AirtableStorage
from storage.sqlite_cache import SqliteCache

_DEFAULT_CONCURRENCY = 4


def _read_run_stats(log_path: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = entry.get("role", "UNKNOWN")
                if role not in stats:
                    stats[role] = {
                        "calls": 0, "tokens_in": 0, "tokens_out": 0,
                        "cost_usd": 0.0, "latency_ms": 0,
                    }
                stats[role]["calls"] += 1
                stats[role]["tokens_in"] += entry.get("tokens_in") or 0
                stats[role]["tokens_out"] += entry.get("tokens_out") or 0
                stats[role]["cost_usd"] += entry.get("cost_usd") or 0.0
                stats[role]["latency_ms"] += entry.get("latency_ms") or 0
    except FileNotFoundError:
        pass
    return stats


def _print_cost_table(run_id: str, log_dir: str = "./logs") -> tuple[float, int, int]:
    from rich.console import Console
    from rich.table import Table

    stats = _read_run_stats(str(Path(log_dir) / f"{run_id}.jsonl"))

    table = Table(title=f"Run: {run_id}")
    table.add_column("Agent")
    table.add_column("Calls", justify="right")
    table.add_column("Tokens In", justify="right")
    table.add_column("Tokens Out", justify="right")
    table.add_column("Cost (USD)", justify="right")
    table.add_column("Avg Latency (ms)", justify="right")

    total_cost = 0.0
    total_in = 0
    total_out = 0

    for role, s in sorted(stats.items()):
        avg_latency = s["latency_ms"] // s["calls"] if s["calls"] else 0
        table.add_row(
            role,
            str(s["calls"]),
            str(s["tokens_in"]),
            str(s["tokens_out"]),
            f"${s['cost_usd']:.4f}",
            str(avg_latency),
        )
        total_cost += s["cost_usd"]
        total_in += s["tokens_in"]
        total_out += s["tokens_out"]

    if stats:
        table.add_section()
        table.add_row("TOTAL", "", str(total_in), str(total_out), f"${total_cost:.4f}", "", style="bold")

    Console().print(table)
    return total_cost, total_in, total_out


async def run_pipeline(
    limit: int = 10,
    dry_run: bool = False,
    refresh_older_than: int | None = None,
) -> RunResult:
    run_id = make_run_id()
    _log_dir = os.environ.get("JSONL_LOG_DIR", "./logs")
    logger = JsonlLogger(run_id=run_id, log_dir=_log_dir)
    langfuse = LangfuseWrapper(run_id=run_id)
    cache = SqliteCache(path=os.environ.get("SQLITE_CACHE_PATH", "./cache.sqlite"))

    scout_client = get_client("SCOUT")
    researcher_client = get_client("RESEARCHER")
    scorer_client = get_client("SCORER")
    drafter_client = get_client("DRAFTER")
    search = get_search_client()

    scout = ScoutAgent(client=scout_client, logger=logger, langfuse=langfuse)
    researcher = ResearcherAgent(
        client=researcher_client, search=search, logger=logger, langfuse=langfuse
    )
    scorer = ScorerAgent(client=scorer_client, logger=logger, langfuse=langfuse, cache=cache)
    drafter = DrafterAgent(client=drafter_client, logger=logger, langfuse=langfuse)

    storage = None if dry_run else AirtableStorage(cache=cache)

    if not dry_run:
        cache.start_run(run_id)

    seen_names = cache.get_all_seen_names()

    refresh_candidates: list[ScoutCandidate] = []
    if refresh_older_than is not None:
        stale = cache.get_stale_vcs(refresh_older_than)
        refresh_candidates = [
            ScoutCandidate(
                name=r["name"],
                url=r.get("url") or "",
                why_match="refresh",
                source_urls=[],
            )
            for r in stale
        ]

    new_limit = max(0, limit - len(refresh_candidates))
    new_candidates = scout.run(run_id=run_id, seen_names=seen_names, limit=new_limit)
    all_candidates = (refresh_candidates + new_candidates)[:limit]

    result = RunResult(run_id=run_id, vcs_scouted=len(all_candidates))
    _t0 = time.monotonic()
    _top_vcs: list[tuple[VCDossier, Score]] = []

    max_concurrency = int(os.environ.get("MAX_CONCURRENCY", str(_DEFAULT_CONCURRENCY)))
    semaphore = asyncio.Semaphore(max_concurrency)

    _max_cost = float(os.environ["MAX_COST_USD"]) if os.environ.get("MAX_COST_USD", "").strip() else None
    _log_path = logger.log_path
    _budget_lock = asyncio.Lock()

    def _process_vc(candidate: ScoutCandidate) -> tuple[bool, int, VCDossier, Score]:
        dossier: VCDossier = researcher.run(candidate, run_id=run_id)
        score: Score = scorer.run(dossier, run_id=run_id)
        drafts: Drafts | None = drafter.run(dossier, score, run_id=run_id)

        drafts_count = len(drafts.drafts) if drafts else 0
        if storage is not None:
            vc_fields = {
                "name": dossier.name,
                "url": dossier.url,
                "country": dossier.country,
                "thesis_summary": dossier.thesis_summary,
                "stage_focus": ", ".join(dossier.stage_focus),
                "ticket_size": dossier.ticket_size,
                "partners": ", ".join(dossier.partners),
                "score": score.total,
                "score_breakdown": "\n".join(
                    f"{d.name}: {d.score}/5 — {d.rationale}" for d in score.dimensions
                ),
                "dossier": f"{dossier.thesis_summary}\n\n{dossier.score_preview}",
                "sources": "\n".join(dossier.sources),
                "status": "Draft Ready" if score.go else "Researched",
            }
            vc_record_id = storage.upsert_vc(vc_fields)

            if drafts:
                for draft in drafts.drafts:
                    storage.upsert_draft({
                        "_vc_record_id": vc_record_id,
                        "partner_name": draft.partner_name,
                        "channel": draft.channel,
                        "subject": draft.subject,
                        "body": draft.body,
                    })

            # Mark seen only after Airtable write succeeds — prevents orphaned cache entries
            cache.add_vc_seen(candidate.name, candidate.url or None)
            cache.update_last_researched(candidate.name)

        return True, drafts_count, dossier, score

    async def _process_vc_async(candidate: ScoutCandidate):
        async with semaphore:
            if _max_cost is not None:
                async with _budget_lock:
                    stats = _read_run_stats(_log_path)
                    spent = sum(s["cost_usd"] for s in stats.values())
                    if spent >= _max_cost:
                        raise BudgetExceededError(
                            f"budget ${_max_cost:.2f} reached (spent ${spent:.2f}) — skipping"
                        )
            return await asyncio.to_thread(_process_vc, candidate)

    task_results = await asyncio.gather(
        *[_process_vc_async(c) for c in all_candidates],
        return_exceptions=True,
    )

    for i, res in enumerate(task_results):
        if isinstance(res, BudgetExceededError):
            result.vcs_budget_halted += 1
        elif isinstance(res, Exception):
            result.errors.append(f"{all_candidates[i].name}: {res}")
        else:
            _, drafts_count, dossier, score = res
            result.vcs_researched += 1
            result.drafts_written += drafts_count
            if score.go:
                _top_vcs.append((dossier, score))

    _top_vcs.sort(key=lambda x: x[1].total, reverse=True)
    duration_s = time.monotonic() - _t0

    total_cost, total_in, total_out = _print_cost_table(run_id, log_dir=_log_dir)

    langfuse.flush()

    if not dry_run:
        cache.end_run(
            run_id=run_id,
            status=result.status,
            total_cost_usd=total_cost,
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            vcs_scouted=result.vcs_scouted,
            vcs_researched=result.vcs_researched,
            drafts_written=result.drafts_written,
        )

        from notify.email import send_digest
        send_digest(result, _top_vcs[:5], duration_s)

    return result
