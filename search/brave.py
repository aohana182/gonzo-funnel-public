import html
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from search.base import SearchResult

_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_HEADERS_BASE = {"Accept": "application/json", "Accept-Encoding": "gzip"}
_TAG_RE = re.compile(r"<[^>]+>")
_TIMEOUT = 30.0
_BACKOFF = (1, 4, 16)

# TODO: remove once on a paid Brave plan (free tier = 1 req/sec)
_RATE_LOCK = threading.Lock()
_RATE_MIN_INTERVAL = 1.1  # seconds between search() calls, across all threads
_last_search_time: float = 0.0


def _rate_limit() -> None:
    global _last_search_time
    with _RATE_LOCK:
        wait = _RATE_MIN_INTERVAL - (time.monotonic() - _last_search_time)
        _last_search_time = time.monotonic() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


class BraveClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        _rate_limit()
        headers = {**_HEADERS_BASE, "X-Subscription-Token": self._api_key}
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF):
            try:
                resp = httpx.get(
                    _SEARCH_URL,
                    params={"q": query, "count": min(k, 20)},
                    headers=headers,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                retrieved_at = datetime.now(timezone.utc).isoformat()
                results = []
                for item in data.get("web", {}).get("results", [])[:k]:
                    results.append(SearchResult(
                        title=html.unescape(item.get("title", "")),
                        url=item.get("url", ""),
                        snippet=html.unescape(item.get("description", "")),
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
