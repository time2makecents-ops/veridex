from __future__ import annotations

import unittest

from office_app.server.conversation_planner import ConversationPlanner


class ConversationPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ConversationPlanner()

    def test_list_request_uses_generic_complete_list_plan(self) -> None:
        plan = self.planner.plan_model_prompt("what are the main ways cellphone stores increase repeat customers?")
        self.assertEqual(plan.answer_type, "list")
        self.assertIn("User request: what are the main ways cellphone stores increase repeat customers?", plan.user_prompt)
        self.assertIn("Provide a complete numbered list of 5 substantive items", plan.user_prompt)
        self.assertIn("Do not stop after the first item.", plan.user_prompt)
        self.assertIn("no markdown tables", plan.user_prompt)
        self.assertIn("Do not invent study numbers", plan.user_prompt)

    def test_risk_sensitive_list_plan_deprioritizes_incentive_shortcuts(self) -> None:
        plan = self.planner.plan_model_prompt("what are the main ways bars increase repeat customers?")
        self.assertEqual(plan.answer_type, "list")
        self.assertIn("regulated_or_high_risk", plan.risk_flags)
        self.assertIn("do not lead with incentives, discounts, claims, or shortcuts", plan.user_prompt)

    def test_choose_one_request_uses_generic_recommendation_plan(self) -> None:
        plan = self.planner.plan_model_prompt("which strategy is most effective for selling phones?")
        self.assertEqual(plan.answer_type, "recommendation")
        self.assertIn("Choose one answer first.", plan.user_prompt)
        self.assertIn("State the criteria you used", plan.user_prompt)
        self.assertIn("compare it with the next strongest alternative", plan.user_prompt)
        self.assertIn("Keep the answer to 2 or 3 short paragraphs", plan.user_prompt)
        self.assertIn("no markdown tables", plan.user_prompt)

    def test_followup_rewrites_plain_sentence_list_for_any_industry(self) -> None:
        plan = self.planner.rewrite_followup(
            "which one is most effective?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways cellphone stores increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Cellphone stores increase repeat customers through device setup help, trade-in support, "
                        "repair guidance, family-plan reviews, and accessory bundles."
                    ),
                },
            ],
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.answer_type, "contextual_followup")
        self.assertIn("cellphone stores increase repeat customers", plan.user_prompt)
        self.assertIn("choose the single strongest option", plan.user_prompt)
        self.assertIn("device setup help", plan.user_prompt)
        self.assertIn("Use plain text only, not a table", plan.user_prompt)

    def test_partial_list_feedback_is_generic(self) -> None:
        plan = self.planner.rewrite_followup(
            "you only listed one",
            [
                {"role": "user", "text": "what are the main ways restaurants increase lunch sales?"},
                {"role": "assistant", "text": "1. Speed of service"},
            ],
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.answer_type, "continuation")
        self.assertIn("restaurants increase lunch sales", plan.user_prompt)
        self.assertIn("Provide items 2 through 5", plan.user_prompt)
        self.assertIn("Use plain text only", plan.user_prompt)

    def test_meta_followup_uses_plain_text_reasoning(self) -> None:
        plan = self.planner.rewrite_followup(
            "why that one?",
            [
                {"role": "user", "text": "what are the main ways cellphone stores increase repeat customers?"},
                {"role": "assistant", "text": "1. Device setup\n2. Post-purchase support\n3. Upgrade reminders"},
                {"role": "user", "text": "which one is most effective?"},
                {"role": "assistant", "text": "Post-purchase support is the strongest option because it keeps customers engaged."},
            ],
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.answer_type, "reasoning_followup")
        self.assertIn("Use plain text only, not a table", plan.user_prompt)
        self.assertIn("Do not invent statistics", plan.user_prompt)

    def test_what_about_followup_applies_prior_thread_to_new_industry(self) -> None:
        plan = self.planner.rewrite_followup(
            "what about cellphone companies?",
            [
                {"role": "user", "text": "what are the main ways bars increase repeat customers?"},
                {
                    "role": "assistant",
                    "text": "1. Service quality\n2. Atmosphere\n3. Community\n4. Consistency\n5. Events",
                },
                {"role": "user", "text": "which one is most effective?"},
                {"role": "assistant", "text": "Service quality is the strongest option."},
            ],
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.answer_type, "comparative_followup")
        self.assertIn("previous discussion about bars increase repeat customers", plan.user_prompt)
        self.assertIn("cellphone companies", plan.user_prompt)
        self.assertIn("same thread", plan.user_prompt)
        self.assertIn("what carries over", plan.user_prompt)

    def test_what_about_followup_prefers_current_insurance_thread_over_older_cellphone_topic(self) -> None:
        plan = self.planner.rewrite_followup(
            "what about cold calling?",
            [
                {"role": "user", "text": "what are the main ways cellphone stores increase repeat customers?"},
                {"role": "assistant", "text": "1. Promotions\n2. Loyalty programs\n3. Service quality"},
                {"role": "user", "text": "whats the most effective one of those?"},
                {"role": "assistant", "text": "Service quality is the strongest option."},
                {"role": "user", "text": "whats the best way for an insurance agent to find new customers?"},
                {"role": "assistant", "text": "The best way is building a strong referral network."},
                {"role": "user", "text": "list the top 5 ways"},
                {
                    "role": "assistant",
                    "text": (
                        "Here are the top 5 ways for an insurance agent to find new customers, ranked by effectiveness:\n"
                        "1. Build a strong referral network\n"
                        "2. Targeted digital marketing\n"
                        "3. Networking at local events"
                    ),
                },
            ],
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.answer_type, "comparative_followup")
        self.assertIn("insurance agent to find new customers", plan.user_prompt)
        self.assertIn("cold calling", plan.user_prompt)
        self.assertNotIn("cellphone", plan.user_prompt)


if __name__ == "__main__":
    unittest.main()
