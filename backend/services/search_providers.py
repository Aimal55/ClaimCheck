"""Replaceable web-search providers for the live investigation pipeline."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__) 


class SearchProviderError(RuntimeError):
    pass


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return normalized {title,url,snippet,published_at} results."""


class WikipediaSearchProvider(SearchProvider):
    """Low-cost key-free provider using Wikipedia's public API."""

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": max(1, min(limit, 50)),
                    "prop": "extracts|info|pageimages",
                    "exintro": 1,
                    "explaintext": 1,
                    "inprop": "url",
                    "format": "json",
                },
                headers={"User-Agent": "ClaimCheck/1.0 (educational research app)"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
        except requests.RequestException as exc:
            raise SearchProviderError("Wikipedia search failed.") from exc

        results: list[dict[str, Any]] = []
        for page in pages.values():
            url = page.get("fullurl")
            if not url:
                continue
            results.append(
                {
                    "title": page.get("title") or url,
                    "url": url,
                    "snippet": page.get("extract") or "",
                    "published_at": None,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return results[:limit]


class TavilySearchProvider(SearchProvider):
    """Optional Tavily web search provider; requires TAVILY_API_KEY."""

    def __init__(self, api_key: str, timeout: float = 12.0) -> None:
        if not api_key:
            raise SearchProviderError("TAVILY_API_KEY is not configured.")
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": limit},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise SearchProviderError("Tavily search failed.") from exc

        results: list[dict[str, Any]] = []
        for item in payload.get("results", [])[:limit]:
            results.append(
                {
                    "title": item.get("title") or item.get("url") or "Unknown source",
                    "url": item.get("url"),
                    "snippet": item.get("content") or "",
                    "published_at": item.get("published_date"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return [result for result in results if result["url"]]


def create_search_provider(
    provider_name: str,
    tavily_api_key: str,
    timeout: float = 12.0,
) -> SearchProvider:
    name = (provider_name or "wikipedia").strip().lower()
    if name == "wikipedia":
        return WikipediaSearchProvider(timeout=timeout)
    if name == "tavily":
        return TavilySearchProvider(api_key=tavily_api_key, timeout=timeout)
    raise SearchProviderError(f"Unknown SEARCH_PROVIDER '{provider_name}'.")
