from __future__ import annotations

import unittest

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
        service = SearchService(fetch_text=lambda url, headers: markup)
        result = service.search_web(query="test query", limit=2)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["title"], "Example One")
        self.assertEqual(result["results"][0]["snippet"], "First snippet")
        self.assertIn("Source:", result["summary_text"])
        self.assertIn("URL:", result["summary_text"])

    def test_search_reviews_extracts_rating_hints(self) -> None:
        markup = """
        <html>
          <body>
            <a class="result__a" href="https://www.yelp.com/biz/test-place">Test Place</a>
            <div class="result__snippet">Rated 4.7 stars with 128 reviews.</div>
          </body>
        </html>
        """
        service = SearchService(fetch_text=lambda url, headers: markup)
        result = service.search_reviews(query="best restaurants in Eugene", limit=1)
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
        service = SearchService(fetch_json=lambda url, headers: payload)
        result = service.search_places(query="coffee", location="Eugene", limit=1)
        self.assertEqual(result["results"][0]["title"], "Coffee Shop")
        self.assertIn("Eugene", result["results"][0]["address"])
        self.assertIn("Address:", result["summary_text"])
        self.assertIn("URL:", result["summary_text"])

    def test_search_places_requests_location_for_nearby_queries(self) -> None:
        service = SearchService(fetch_json=lambda url, headers: self.fail("provider should not be called"))
        result = service.search_places(query="restaurants", category="restaurants", needs_location=True)
        self.assertTrue(result["needs_location"])
        self.assertEqual(result["results"], [])
        self.assertIn("I need your location", result["summary_text"])


if __name__ == "__main__":
    unittest.main()
