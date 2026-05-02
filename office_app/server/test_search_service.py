from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from office_app.server.search_service import SearchService


class SearchServiceTests(unittest.TestCase):
    def test_search_web_parses_duckduckgo_results(self) -> None:
        markup = """
        <html>
          <body>
            <a class="result__a" href="https://example.com/one">Example One</a>
            <div class="result__snippet">First snippet</div>
            <a class="result__a" href="https://example.com/two">Example Two</a>
            <div class="result__snippet">Second snippet</div>
          </body>
        </html>
        """
        service = SearchService(
            fetch_text=lambda url, headers: markup,
            serpapi_api_key="",
            google_api_key="",
            google_search_engine_id="",
        )
        result = service.search_web(query="test query", limit=2)
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["title"], "Example One")
        self.assertEqual(result["results"][0]["snippet"], "First snippet")
        self.assertIn("Source:", result["summary_text"])
        self.assertIn("URL:", result["summary_text"])

    def test_search_web_uses_serpapi_when_configured(self) -> None:
        seen_urls = []

        def fetch_json(url, headers):
            seen_urls.append(url)
            return {
                "organic_results": [
                    {
                        "title": "SerpAPI Result",
                        "link": "https://example.com/serpapi",
                        "snippet": "SerpAPI snippet",
                        "source": "Example",
                    }
                ]
            }

        service = SearchService(
            fetch_json=fetch_json,
            serpapi_api_key="serp-key",
            google_api_key="",
            google_search_engine_id="",
        )
        result = service.search_web(query="test query", limit=1)
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["results"][0]["title"], "SerpAPI Result")
        self.assertEqual(result["results"][0]["snippet"], "SerpAPI snippet")
        self.assertIn("serpapi.com/search.json", seen_urls[0])
        self.assertIn("engine=google", seen_urls[0])
        self.assertIn("api_key=serp-key", seen_urls[0])

    def test_search_web_uses_google_when_configured(self) -> None:
        seen_urls = []

        def fetch_json(url, headers):
            seen_urls.append(url)
            return {
                "items": [
                    {
                        "title": "Google Result",
                        "link": "https://example.com/google",
                        "snippet": "Google snippet",
                    }
                ]
            }

        service = SearchService(
            fetch_json=fetch_json,
            serpapi_api_key="",
            google_api_key="test-key",
            google_search_engine_id="test-cx",
        )
        result = service.search_web(query="test query", limit=1)
        self.assertEqual(result["provider"], "google")
        self.assertEqual(result["results"][0]["title"], "Google Result")
        self.assertEqual(result["results"][0]["snippet"], "Google snippet")
        self.assertIn("customsearch/v1", seen_urls[0])
        self.assertIn("key=test-key", seen_urls[0])
        self.assertIn("cx=test-cx", seen_urls[0])

    def test_search_web_can_reuse_gemini_key_for_google(self) -> None:
        seen_urls = []

        def fetch_json(url, headers):
            seen_urls.append(url)
            return {"items": [{"title": "Result", "link": "https://example.com", "snippet": "Snippet"}]}

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=False):
            service = SearchService(
                fetch_json=fetch_json,
                serpapi_api_key="",
                google_search_engine_id="test-cx",
            )
        result = service.search_web(query="test query", limit=1)
        self.assertEqual(result["provider"], "google")
        self.assertIn("key=gemini-key", seen_urls[0])

    def test_search_web_falls_back_to_duckduckgo_if_google_fails(self) -> None:
        markup = """
        <html>
          <body>
            <a class="result__a" href="https://example.com/fallback">Fallback Result</a>
            <div class="result__snippet">Fallback snippet</div>
          </body>
        </html>
        """

        def fetch_json(url, headers):
            raise RuntimeError("Google unavailable")

        service = SearchService(
            fetch_text=lambda url, headers: markup,
            fetch_json=fetch_json,
            serpapi_api_key="",
            google_api_key="test-key",
            google_search_engine_id="test-cx",
        )
        result = service.search_web(query="test query", limit=1)
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertIn("fallback_reason", result)
        self.assertIn("Google search failed", result["fallback_reason"])
        self.assertEqual(result["results"][0]["title"], "Fallback Result")

    def test_search_web_falls_back_to_google_if_serpapi_fails(self) -> None:
        seen_urls = []

        def fetch_json(url, headers):
            seen_urls.append(url)
            if "serpapi.com" in url:
                raise RuntimeError("SerpAPI unavailable")
            return {
                "items": [
                    {
                        "title": "Google Fallback",
                        "link": "https://example.com/google-fallback",
                        "snippet": "Google fallback snippet",
                    }
                ]
            }

        service = SearchService(
            fetch_json=fetch_json,
            serpapi_api_key="serp-key",
            google_api_key="google-key",
            google_search_engine_id="google-cx",
        )
        result = service.search_web(query="test query", limit=1)
        self.assertEqual(result["provider"], "google")
        self.assertNotIn("fallback_reason", result)
        self.assertEqual(result["results"][0]["title"], "Google Fallback")
        self.assertTrue(any("serpapi.com" in url for url in seen_urls))
        self.assertTrue(any("googleapis.com" in url for url in seen_urls))

    def test_search_reviews_extracts_rating_hints(self) -> None:
        markup = """
        <html>
          <body>
            <a class="result__a" href="https://www.yelp.com/biz/test-place">Test Place</a>
            <div class="result__snippet">Rated 4.7 stars with 128 reviews.</div>
          </body>
        </html>
        """
        service = SearchService(
            fetch_text=lambda url, headers: markup,
            serpapi_api_key="",
            google_api_key="",
            google_search_engine_id="",
        )
        result = service.search_reviews(query="best restaurants in Eugene", limit=1)
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertEqual(result["results"][0]["rating_hint"], "4.7")
        self.assertEqual(result["results"][0]["review_count_hint"], "128")
        self.assertIn("Notes:", result["summary_text"])
        self.assertIn("URL:", result["summary_text"])

    def test_search_places_formats_nominatim_results(self) -> None:
        payload = [
            {
                "name": "Coffee Shop",
                "display_name": "Coffee Shop, Eugene, Oregon, USA",
                "lat": "44.0",
                "lon": "-123.0",
                "type": "cafe",
                "osm_type": "node",
                "osm_id": 123,
            }
        ]
        service = SearchService(
            fetch_json=lambda url, headers: payload,
            serpapi_api_key="",
            google_api_key="",
            google_search_engine_id="",
        )
        result = service.search_places(query="coffee", location="Eugene", limit=1)
        self.assertEqual(result["results"][0]["title"], "Coffee Shop")
        self.assertIn("Eugene", result["results"][0]["address"])
        self.assertIn("Address:", result["summary_text"])
        self.assertIn("URL:", result["summary_text"])

    def test_search_places_requests_location_for_nearby_queries(self) -> None:
        service = SearchService(
            fetch_json=lambda url, headers: self.fail("provider should not be called"),
            serpapi_api_key="",
            google_api_key="",
            google_search_engine_id="",
        )
        result = service.search_places(query="restaurants", category="restaurants", needs_location=True)
        self.assertTrue(result["needs_location"])
        self.assertEqual(result["results"], [])
        self.assertIn("I need your location", result["summary_text"])


if __name__ == "__main__":
    unittest.main()
