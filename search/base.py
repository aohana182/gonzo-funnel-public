from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    retrieved_at: str  # ISO UTC


class SearchClient(Protocol):
    def search(self, query: str, k: int = 10) -> list[SearchResult]: ...
    def fetch(self, url: str) -> str: ...
