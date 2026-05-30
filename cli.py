import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

from errors import ConfigError
from orchestrator import run_pipeline


def _config_check() -> int:
    from rich.console import Console

    from llm.factory import get_client
    from search.factory import get_client as get_search_client

    console = Console()
    errors: list[str] = []

    for role in ["SCOUT", "RESEARCHER", "SCORER", "DRAFTER"]:
        try:
            get_client(role)
            console.print(f"[green]OK[/green] {role} LLM")
        except ConfigError as e:
            errors.append(str(e))
            console.print(f"[red]FAIL[/red] {role} LLM: {e}")

    try:
        get_search_client()
        console.print("[green]OK[/green] Search")
    except ConfigError as e:
        errors.append(str(e))
        console.print(f"[red]FAIL[/red] Search: {e}")

    for key in ["AIRTABLE_PAT", "AIRTABLE_BASE_ID"]:
        if os.environ.get(key, "").strip():
            console.print(f"[green]OK[/green] {key}")
        else:
            errors.append(f"{key} is not set")
            console.print(f"[red]FAIL[/red] {key}: not set")

    if errors:
        console.print(f"\n[red]{len(errors)} error(s). Fix above before running.[/red]")
        return 2
    console.print("\n[green]Config OK.[/green]")
    return 0


def _run_only(only: str, vc_name: str | None, run_id: str) -> None:
    from rich.console import Console

    from agents.drafter import DrafterAgent
    from agents.researcher import ResearcherAgent
    from agents.scorer import ScorerAgent
    from agents.scout import ScoutAgent, ScoutCandidate
    from llm.factory import get_client
    from observability.jsonl_logger import JsonlLogger
    from observability.langfuse_wrapper import LangfuseWrapper
    from search.factory import get_client as get_search_client
    from storage.sqlite_cache import SqliteCache

    console = Console()
    logger = JsonlLogger(run_id=run_id)
    langfuse = LangfuseWrapper(run_id=run_id)
    cache = SqliteCache()

    if only == "scout":
        seen = cache.get_all_seen_names()
        search = get_search_client()
        scout = ScoutAgent(client=get_client("SCOUT"), search=search, logger=logger, langfuse=langfuse)
        candidates = scout.run(run_id=run_id, seen_names=seen, limit=10)
        console.print_json(json.dumps([c.model_dump() for c in candidates]))
        return

    if not vc_name:
        console.print(f"[red]--vc NAME is required for --only {only}[/red]")
        sys.exit(2)

    candidate = ScoutCandidate(name=vc_name, url="", why_match="--only mode", source_urls=[])

    search = get_search_client()
    researcher = ResearcherAgent(
        client=get_client("RESEARCHER"), search=search, logger=logger, langfuse=langfuse
    )

    dossier = researcher.run(candidate, run_id=run_id)

    if only == "researcher":
        console.print_json(dossier.model_dump_json(indent=2))
        return

    scorer = ScorerAgent(client=get_client("SCORER"), logger=logger, langfuse=langfuse, cache=cache)
    score = scorer.run(dossier, run_id=run_id)

    if only == "scorer":
        console.print_json(score.model_dump_json(indent=2))
        return

    drafter = DrafterAgent(client=get_client("DRAFTER"), logger=logger, langfuse=langfuse)
    drafts = drafter.run(dossier, score, run_id=run_id)

    if drafts is None:
        console.print(f"[yellow]Score {score.total}/25 — go=False. No drafts produced.[/yellow]")
    else:
        console.print_json(drafts.model_dump_json(indent=2))


def _push_run(run_id: str) -> int:
    from rich.console import Console

    from storage.airtable import AirtableStorage
    from storage.results_log import ResultsLog
    from storage.sqlite_cache import SqliteCache

    console = Console()
    log_dir = os.environ.get("JSONL_LOG_DIR", "./logs")
    entries = ResultsLog(run_id=run_id, log_dir=log_dir).read_all()

    if not entries:
        console.print(f"[yellow]No results file found for run {run_id!r}. "
                      f"Expected: {log_dir}/{run_id}.results.jsonl[/yellow]")
        return 2

    cache = SqliteCache(path=os.environ.get("SQLITE_CACHE_PATH", "./cache.sqlite"))
    storage = AirtableStorage(cache=cache)
    pushed = 0
    errors: list[str] = []

    for entry in entries:
        name = entry["vc"].get("name", "?")
        try:
            vc_record_id = storage.upsert_vc(entry["vc"])
            for draft in entry.get("drafts", []):
                storage.upsert_draft({"_vc_record_id": vc_record_id, **draft})
            cache.add_vc_seen(name, entry["vc"].get("url") or None)
            cache.update_last_researched(name)
            pushed += 1
            console.print(f"[green]OK[/green] {name}")
        except Exception as e:
            errors.append(f"{name}: {e}")
            console.print(f"[red]FAIL[/red] {name}: {e}")

    console.print(f"\nPushed: {pushed} | Errors: {len(errors)}")
    return 0 if not errors else 3


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="gonzo-funnel",
        description="Multi-agent VC investor pipeline.",
    )
    parser.add_argument("--limit", type=int, default=10, metavar="N",
                        help="Max VCs to process (default 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No Airtable writes, no run_log writes")
    parser.add_argument("--only", choices=["scout", "researcher", "scorer", "drafter"],
                        help="Run a single agent and print output")
    parser.add_argument("--vc", type=str, metavar="NAME",
                        help="VC name for --only researcher/scorer/drafter")
    parser.add_argument("--refresh-older-than", type=int, dest="refresh_older_than", metavar="N",
                        help="Re-research VCs not updated in N days")
    parser.add_argument("--no-langfuse", action="store_true",
                        help="Disable Langfuse for this run")
    parser.add_argument("--config-check", action="store_true",
                        help="Validate env config and exit")
    parser.add_argument("--push-run", metavar="RUN_ID",
                        help="Push a saved results file to Airtable without re-running LLMs")
    args = parser.parse_args()

    if args.config_check:
        sys.exit(_config_check())

    if args.push_run:
        sys.exit(_push_run(args.push_run))

    if args.no_langfuse:
        os.environ["LANGFUSE_ENABLED"] = "false"

    if args.only:
        from observability.jsonl_logger import make_run_id
        _run_only(args.only, args.vc, run_id=make_run_id())
        return

    from rich.console import Console
    console = Console()

    try:
        result = asyncio.run(run_pipeline(
            limit=args.limit,
            dry_run=args.dry_run,
            refresh_older_than=args.refresh_older_than,
        ))
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(2)
    except Exception as exc:
        console.print(f"[red]Fatal error:[/red] {exc}")
        sys.exit(4)

    console.print(
        f"\n[bold]Done.[/bold] Scouted: {result.vcs_scouted} | "
        f"Researched: {result.vcs_researched} | Drafts: {result.drafts_written}"
    )
    if result.vcs_budget_halted:
        console.print(
            f"[yellow]Budget ceiling reached — {result.vcs_budget_halted} VC(s) skipped. "
            f"Raise MAX_COST_USD to process more.[/yellow]"
        )
    if result.errors:
        console.print(f"[yellow]Errors ({len(result.errors)}):[/yellow]")
        for e in result.errors:
            console.print(f"  {e}")

    _exit_codes = {
        "success": 0,
        "budget_ceiling": 0,
        "partial_failure": 3,
        "total_failure": 4,
    }
    sys.exit(_exit_codes.get(result.status, 0))


if __name__ == "__main__":
    main()
