from __future__ import annotations

import unittest

from office_app.server.conversation_planner import ConversationPlanner


class ConversationPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ConversationPlanner()

    def test_pasted_output_gets_evidence_mode_prompt(self) -> None:
        plan = self.planner.plan_model_prompt(
            "Here is the output from the last attempt:\nSales Director\nI cannot provide a list of major malls in Eugene."
        )
        self.assertIn("The user pasted prior assistant output", plan.user_prompt)
        self.assertIn("Treat that text as evidence", plan.user_prompt)
        self.assertEqual(plan.answer_type, "chat")

