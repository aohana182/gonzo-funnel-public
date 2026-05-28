from dataclasses import dataclass, field


@dataclass
class RunResult:
    run_id: str
    vcs_scouted: int = 0
    vcs_researched: int = 0
    drafts_written: int = 0
    vcs_budget_halted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.vcs_scouted > 0 and self.vcs_researched == 0:
            if self.vcs_budget_halted > 0 and not self.errors:
                return "budget_ceiling"
            return "total_failure"
        if self.errors:
            return "partial_failure"
        return "success"
