import html
import re
import time
from datetime import datetime, timezone

import httpx

from search.base import SearchResult

_SEARCH_URL = "https://api.tavily.com/search"
_TIMEOUT = 30.0
_BACKOFF = (1, 4, 16)
_TAG_RE = re.compile(r"<[^>]+>")


class TavilyClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                resp = httpx.post(
                    _SEARCH_URL,
                    json={
                        "api_key": self._api_key,
                        "query": query,
                        "max_results": min(k, 10),
                        "include_answer": False,
                    },
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                retrieved_at = datetime.now(timezone.utc).isoformat()
                results = []
                for item in data.get("results", [])[:k]:
                    results.append(SearchResult(
                        title=html.unescape(item.get("title", "")),
                        url=item.get("url", ""),
                        snippet=html.unescape(item.get("content", "")),
                        retrieved_at=retrieved_at,
                    ))
                return results
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in (429,) and e.response.status_code < 500:
                    raise
                last_exc = e
                if attempt < len(_BACKOFF) - 1:
                    time.sleep(backoff)
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    def fetch(self, url: str) -> str:
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
                resp.raise_for_status()
                text = _TAG_RE.sub(" ", resp.text)
                return html.unescape(" ".join(text.split()))
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in (429,) and e.response.status_code < 500:
                    raise
                last_exc = e
                if attempt < len(_BACKOFF) - 1:
                    time.sleep(backoff)
                    continue
                raise
        raise last_exc  # type: ignore[misc]
