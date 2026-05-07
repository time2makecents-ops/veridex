from __future__ import annotations

import unittest

from office_app.server.request_response_helpers import request_text_from_response


class RequestResponseHelpersTests(unittest.TestCase):
    def test_request_text_from_response_numbers_room_memory_items(self) -> None:
        response = {
            "structuredContent": {
                "items": [
                    {"index": 1, "description": "First memory"},
                    {"index": 2, "description": "Second memory"},
                ]
            }
        }
        text = request_text_from_response(response)
        self.assertEqual(text, "1. First memory\n2. Second memory")


if __name__ == "__main__":
    unittest.main()
