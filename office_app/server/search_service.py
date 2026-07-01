from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, urlencode, unquote, urlparse
from urllib.request import Request, urlopen

from office_app.server.env_loader import load_env_files


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

    def __init__(
        self,
        *,
        fetch_text: Optional[Callable[[str, Dict[str, str]], str]] = None,
        fetch_json: Optional[Callable[[str, Dict[str, str]], Any]] = None,
        serpapi_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        google_search_engine_id: Optional[str] = None,
    ) -> None:
        server_dir = Path(__file__).resolve().parent
        pkg_dir = server_dir.parent
        root_dir = pkg_dir.parent
        load_env_files(
            (
                root_dir / ".env",
                root_dir / ".env.local",
                pkg_dir / ".env",
                pkg_dir / ".env.local",
            )
        )
        self._fetch_text = fetch_text or self._default_fetch_text
        self._fetch_json = fetch_json or self._default_fetch_json
        self.serpapi_api_key = (
            serpapi_api_key if serpapi_api_key is not None else os.getenv("SERPAPI_API_KEY", "")
        ).strip()
        self.google_api_key = (
            google_api_key
            if google_api_key is not None
            else os.getenv("GOOGLE_SEARCH_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        ).strip()
        self.google_search_engine_id = (
            google_search_engine_id
            if google_search_engine_id is not None
            else os.getenv("GOOGLE_SEARCH_ENGINE_ID", "") or os.getenv("GOOGLE_CSE_ID", "")
        ).strip()

    def search_web(self, *, query: str, limit: int = 5, recency_days: Optional[int] = None) -> Dict[str, Any]:
        search_query = query.strip()
        if not search_query:
            raise SearchServiceError("Search query required.")
        if recency_days:
            search_query = f"{search_query} past {int(recency_days)} days"
        results, provider, fallback_reason = self._web_search(search_query, limit=limit, recency_days=recency_days)
        response: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "provider": provider,
            "results": [result.as_dict() for result in results],
            "summary_text": self._format_web_summary(query, results),
        }
        if fallback_reason:
            response["fallback_reason"] = fallback_reason
        return response

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
        results, provider, fallback_reason = self._web_search(" ".join(review_query_parts), limit=limit)
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
        response = {
            "query": query,
            "location": inferred_location,
            "time_window": time_window,
            "limit": limit,
            "provider": provider,
            "results": normalized,
            "summary_text": self._format_review_summary(query, normalized),
        }
        if fallback_reason:
            response["fallback_reason"] = fallback_reason
        return response

    def _web_search(
        self,
        query: str,
        *,
        limit: int,
        recency_days: Optional[int] = None,
    ) -> tuple[List[SearchResult], str, Optional[str]]:
        fallback_reasons: List[str] = []
        if self.serpapi_api_key:
            try:
                return self._serpapi_search(query, limit=limit, recency_days=recency_days), "serpapi", None
            except Exception as exc:
                fallback_reasons.append(f"SerpAPI search failed: {exc}")
        if self.google_api_key and self.google_search_engine_id:
            try:
                return self._google_search(query, limit=limit, recency_days=recency_days), "google", None
            except Exception as exc:
                fallback_reasons.append(f"Google search failed: {exc}")
        reason = "; ".join(fallback_reasons) if fallback_reasons else None
        return self._duckduckgo_search(query, limit=limit), "duckduckgo", reason

    def _serpapi_search(
        self,
        query: str,
        *,
        limit: int,
        recency_days: Optional[int] = None,
    ) -> List[SearchResult]:
        params: Dict[str, Any] = {
            "engine": "google",
            "q": query,
            "api_key": self.serpapi_api_key,
            "num": max(1, min(limit, 10)),
            "hl": "en",
            "gl": "us",
        }
        if recency_days:
            params["tbs"] = f"qdr:d{max(1, int(recency_days))}"
        url = f"https://serpapi.com/search.json?{urlencode(params)}"
        payload = self._fetch_json(url, {"Accept": "application/json"})
        if isinstance(payload, dict) and payload.get("error"):
            raise SearchServiceError(str(payload["error"]))
        items = payload.get("organic_results") if isinstance(payload, dict) else None
        results: List[SearchResult] = []
        for item in items or []:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            source = str(item.get("source") or "").strip() or self._source_from_url(link)
            if not title or not link:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=link,
                    snippet=snippet,
                    source=source,
                )
            )
        return results

    def _google_search(
        self,
        query: str,
        *,
        limit: int,
        recency_days: Optional[int] = None,
    ) -> List[SearchResult]:
        params: Dict[str, Any] = {
            "key": self.google_api_key,
            "cx": self.google_search_engine_id,
            "q": query,
            "num": max(1, min(limit, 10)),
        }
        if recency_days:
            params["dateRestrict"] = f"d{max(1, int(recency_days))}"
        url = f"https://www.googleapis.com/customsearch/v1?{urlencode(params)}"
        payload = self._fetch_json(url, {"Accept": "application/json"})
        items = payload.get("items") if isinstance(payload, dict) else None
        results: List[SearchResult] = []
        for item in items or []:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not title or not link:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=link,
                    snippet=snippet,
                    source=self._source_from_url(link),
                )
            )
        return results

    def search_places(
        self,
        *,
        query: str,
        location: Optional[str] = None,
        category: Optional[str] = None,
        needs_location: bool = False,
        limit: int = 5,
    ) -> Dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise SearchServiceError("Place query required.")
        inferred_location = location or self._extract_location(cleaned_query)
        if needs_location and not inferred_location:
            category_text = category or cleaned_query or "places"
            clarification = f"I need your location or a city/area to search nearby {category_text}."
            return {
                "query": cleaned_query,
                "location": None,
                "category": category,
                "limit": limit,
                "needs_location": True,
                "results": [],
                "summary_text": clarification,
            }
        results = []
        searched_queries = self._place_query_variants(cleaned_query, inferred_location, category)
        for index, full_query in enumerate(searched_queries):
            url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit={max(1, min(limit, 10))}&q={quote_plus(full_query)}"
            payload = self._fetch_json(url, {"Accept": "application/json"})
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
            if results:
                break
        if not results:
            ddg_results = self._place_web_fallback_results(cleaned_query, inferred_location, category, limit=limit)
            if ddg_results:
                results = ddg_results
        return {
            "query": query,
            "location": inferred_location,
            "category": category,
            "limit": limit,
            "needs_location": needs_location,
            "results": results,
            "summary_text": self._format_places_summary(query, results),
        }

    def _place_query_variants(self, query: str, location: Optional[str], category: Optional[str]) -> List[str]:
        base_query = re.sub(r"\s+", " ", str(query or "").strip())
        normalized_category = str(category or "").strip().lower()
        normalized_location = re.sub(r"\s+", " ", str(location or "").strip()) or None
        category_variants = {
            "malls": ["shopping mall", "shopping center", "shopping centre", "mall", "malls"],
            "bars": ["bar", "bars", "pub", "pubs"],
            "hotels": ["hotel", "hotels", "inn", "lodging"],
            "restaurants": ["restaurant", "restaurants", "dining"],
            "cafe": ["cafe", "cafes", "coffee shop", "coffee shops"],
            "coffee": ["coffee shop", "coffee shops", "cafe", "cafes"],
            "thai": ["thai restaurant", "thai restaurants", "thai food"],
        }
        variants: List[str] = []
        if base_query:
            variants.append(base_query)
        for candidate in category_variants.get(normalized_category, []):
            parts = [candidate]
            if normalized_location:
                parts.append(normalized_location)
            variants.append(" ".join(parts))
        if normalized_location:
            variants.append(" ".join(part for part in [base_query, normalized_location] if part))
        deduped: List[str] = []
        seen = set()
        for candidate in variants:
            cleaned = re.sub(r"\s+", " ", candidate).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped[:6]

    def _place_web_fallback_results(
        self,
        query: str,
        location: Optional[str],
        category: Optional[str],
        *,
        limit: int,
    ) -> List[Dict[str, Any]]:
        category_text = str(category or query or "places").strip().lower()
        location_text = str(location or "").strip()
        search_terms = [category_text]
        if location_text:
            search_terms.append(location_text)
        search_query = " ".join(part for part in search_terms if part).strip()
        if not search_query:
            return []
        results = self._duckduckgo_search(search_query, limit=limit)
        if not results:
            return []
        place_like = []
        for result in results:
            text = f"{result.title} {result.snippet}".lower()
            if category_text == "malls":
                if not any(marker in text for marker in ("mall", "center", "centre", "shopping")):
                    continue
            elif category_text in {"restaurants", "bars", "hotels", "coffee", "cafe", "thai"}:
                if not any(marker in text for marker in (category_text.rstrip("s"), category_text, "restaurant", "bar", "hotel", "coffee", "cafe", "thai")):
                    continue
            place_like.append(
                {
                    "title": result.title,
                    "address": result.snippet or result.url,
                    "lat": "",
                    "lon": "",
                    "type": "web_result",
                    "source": result.source,
                    "url": result.url,
                }
            )
            if len(place_like) >= limit:
                break
        return place_like

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
            lines.append(f"{index}. {result.title}")
            lines.append(f"   Source: {result.source}")
            if summary:
                lines.append(f"   Snippet: {summary}")
            if result.url:
                lines.append(f"   URL: {result.url}")
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
            lines.append(f"{index}. {result['title']}")
            lines.append(f"   Source: {result.get('source') or 'web'}")
            if extras:
                lines.append(f"   Notes: {', '.join(extras)}")
            summary = result.get("snippet") or result.get("url") or ""
            if summary:
                lines.append(f"   Snippet: {summary}")
            if result.get("url"):
                lines.append(f"   URL: {result['url']}")
        return "\n".join(lines)

    def _format_places_summary(self, query: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return f"No place results found for '{query}'."
        lines = [f"Place results for '{query}':"]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result['title']}")
            if result.get("address"):
                lines.append(f"   Address: {result['address']}")
            if result.get("source"):
                lines.append(f"   Source: {result['source']}")
            if result.get("url"):
                lines.append(f"   URL: {result['url']}")
        return "\n".join(lines)
