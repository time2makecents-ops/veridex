from __future__ import annotations

import unittest

from office_app.server.model_task_router import classify_model_task


class ModelTaskRouterTests(unittest.TestCase):
    def test_classifies_coding(self) -> None:
        self.assertEqual(classify_model_task("debug this Python API and add unit tests"), "coding")

    def test_classifies_architecture_and_planning(self) -> None:
        self.assertEqual(classify_model_task("plan the architecture and sequence the work"), "planning")

    def test_classifies_media(self) -> None:
        self.assertEqual(classify_model_task("stabilize this video and crop the thumbnail"), "media")

    def test_high_stakes_has_precedence(self) -> None:
        self.assertEqual(classify_model_task("debug this medical dosage calculator"), "high_stakes")

    def test_classifies_simple_and_general_chat(self) -> None:
        self.assertEqual(classify_model_task("Thanks!"), "simple")
        self.assertEqual(classify_model_task("Tell me a story about the coast"), "conversation")


if __name__ == "__main__":
    unittest.main()
