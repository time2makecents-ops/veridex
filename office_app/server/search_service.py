from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


class SearchServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }


class SearchService:
    RESULT_LINK_RE = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    RESULT_SNIPPET_RE = re.compile(
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet_div>.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    TAG_RE = re.compile(r"<[^>]+>")
    REVIEW_SCORE_RE = re.compile(r"\b([1-5](?:\.\d)?)\s*(?:/5|stars?)\b", re.IGNORECASE)
    REVIEW_COUNT_RE = re.compile(r"\b(\d[\d,]*)\s+reviews?\b", re.IGNORECASE)
    LOCATION_RE = re.compile(r"\bin\s+([A-Za-z][A-Za-z0-9 .,'&-]{1,60})", re.IGNORECASE)

    def __init__(self, *, fetch_text: Optional[Callable[[str, Dict[str, str]], str]] = None, fetch_json: Optional[Callable[[str, Dict[str, str]], Any]] = None) -> None:
        self._fetch_text = fetch_text or self._default_fetch_text
        self._fetch_json = fetch_json or self._default_fetch_json

    def search_web(self, *, query: str, limit: int = 5, recency_days: Optional[int] = None) -> Dict[str, Any]:
        search_query = query.strip()
        if not search_query:
            raise SearchServiceError("Search query required.")
        if recency_days:
            search_query = f"{search_query} past {int(recency_days)} days"
        results = self._duckduckgo_search(search_query, limit=limit)
        return {
            "query": query,
            "limit": limit,
            "results": [result.as_dict() for result in results],
            "summary_text": self._format_web_summary(query, results),
        }

    def search_reviews(
        self,
        *,
        query: str,
        location: Optional[str] = None,
        time_window: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise SearchServiceError("Review query required.")
        inferred_location = location or self._extract_location(cleaned_query)
        review_query_parts = [cleaned_query]
        if inferred_location:
            review_query_parts.append(inferred_location)
        if time_window:
            review_query_parts.append(time_window)
        review_query_parts.extend(["reviews", "yelp", "tripadvisor"])
        results = self._duckduckgo_search(" ".join(review_query_parts), limit=limit)
        normalized = []
        for result in results:
            snippet = result.snippet
            score_match = self.REVIEW_SCORE_RE.search(snippet)
            count_match = self.REVIEW_COUNT_RE.search(snippet)
            normalized.append(
                {
                    **result.as_dict(),
                    "rating_hint": score_match.group(1) if score_match else None,
                    "review_count_hint": count_match.group(1) if count_match else None,
                }
            )
        return {
            "query": query,
            "location": inferred_location,
            "time_window": time_window,
            "limit": limit,
            "results": normalized,
            "summary_text": self._format_review_summary(query, normalized),
        }

    def search_places(
        self,
        *,
        query: str,
        location: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise SearchServiceError("Place query required.")
        inferred_location = location or self._extract_location(cleaned_query)
        full_query = " ".join(part for part in [category, cleaned_query, inferred_location] if part).strip()
        url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit={max(1, min(limit, 10))}&q={quote_plus(full_query)}"
        payload = self._fetch_json(url, {"Accept": "application/json"})
        results = []
        for item in payload or []:
            display_name = str(item.get("display_name") or "").strip()
            title = str(item.get("name") or display_name.split(",")[0] or "Unknown place").strip()
            results.append(
                {
                    "title": title,
                    "address": display_name,
                    "lat": str(item.get("lat") or ""),
                    "lon": str(item.get("lon") or ""),
                    "type": str(item.get("type") or ""),
                    "source": "OpenStreetMap",
                    "url": self._place_url(item),
                }
            )
        return {
            "query": query,
            "location": inferred_location,
            "category": category,
            "limit": limit,
            "results": results,
            "summary_text": self._format_places_summary(query, results),
        }

    def _duckduckgo_search(self, query: str, *, limit: int) -> List[SearchResult]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        markup = self._fetch_text(url, {"Content-Type": "text/html; charset=utf-8"})
        results: List[SearchResult] = []
        snippets = list(self.RESULT_SNIPPET_RE.finditer(markup))
        for index, match in enumerate(self.RESULT_LINK_RE.finditer(markup)):
            if len(results) >= limit:
                break
            href = self._normalize_result_url(match.group("href"))
            title = self._clean_html(match.group("title"))
            snippet_match = snippets[index] if index < len(snippets) else None
            snippet_raw = ""
            if snippet_match:
                snippet_raw = snippet_match.group("snippet") or snippet_match.group("snippet_div") or ""
            snippet = self._clean_html(snippet_raw)
            if not title or not href:
                continue
            results.append(SearchResult(title=title, url=href, snippet=snippet, source=self._source_from_url(href)))
        return results

    def _default_fetch_text(self, url: str, extra_headers: Dict[str, str]) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "Veridex/1.0 (+https://127.0.0.1)",
                "Accept-Language": "en-US,en;q=0.9",
                **extra_headers,
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise SearchServiceError(f"Search request failed: {exc}") from exc

    def _default_fetch_json(self, url: str, extra_headers: Dict[str, str]) -> Any:
        text = self._default_fetch_text(url, extra_headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SearchServiceError(f"Search provider returned invalid JSON: {exc}") from exc

    def _normalize_result_url(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.path == "/l/":
            params = parse_qs(parsed.query)
            uddg = params.get("uddg")
            if uddg:
                return unquote(uddg[0])
        return html.unescape(href)

    def _source_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        return host or "web"

    def _clean_html(self, value: str) -> str:
        if not value:
            return ""
        value = self.TAG_RE.sub(" ", value)
        value = html.unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    def _extract_location(self, query: str) -> Optional[str]:
        match = self.LOCATION_RE.search(query)
        if not match:
            return None
        return match.group(1).strip(" .")

    def _place_url(self, item: Dict[str, Any]) -> str:
        osm_type = str(item.get("osm_type") or "").strip()
        osm_id = str(item.get("osm_id") or "").strip()
        if not osm_type or not osm_id:
            return ""
        prefix = {"node": "node", "way": "way", "relation": "relation"}.get(osm_type, osm_type)
        return f"https://www.openstreetmap.org/{prefix}/{osm_id}"

    def _format_web_summary(self, query: str, results: List[SearchResult]) -> str:
        if not results:
            return f"No web results found for '{query}'."
        lines = [f"Web results for '{query}':"]
        for index, result in enumerate(results, start=1):
            summary = result.snippet or result.url
            lines.append(f"{index}. {result.title} [{result.source}] - {summary}")
        return "\n".join(lines)

    def _format_review_summary(self, query: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return f"No review results found for '{query}'."
        lines = [f"Review-oriented results for '{query}':"]
        for index, result in enumerate(results, start=1):
            extras = []
            if result.get("rating_hint"):
                extras.append(f"rating {result['rating_hint']}")
            if result.get("review_count_hint"):
                extras.append(f"{result['review_count_hint']} reviews")
            extra_text = f" ({', '.join(extras)})" if extras else ""
            lines.append(f"{index}. {result['title']} [{result['source']}] - {result['snippet'] or result['url']}{extra_text}")
        return "\n".join(lines)

    def _format_places_summary(self, query: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return f"No place results found for '{query}'."
        lines = [f"Place results for '{query}':"]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result['title']} - {result['address']}")
        return "\n".join(lines)
